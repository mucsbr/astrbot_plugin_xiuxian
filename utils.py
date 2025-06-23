import math
import re
from io import BytesIO
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from wcwidth import wcwidth
import os
import time

from astrbot.api.event import AstrMessageEvent
from astrbot.api import logger
from functools import wraps
import asyncio

from .service import XiuxianService
from .data_manager import jsondata
from .config import XiuConfig
from .item_manager import Items

ASSETS_PATH = Path(__file__).parent / "assets"
TMP_PATH = Path(__file__).parent / "tmp" # 新增tmp目录路径
FONT_FILE = ASSETS_PATH / "sarasa-mono-sc-regular.ttf"
BACKGROUND_FILE = ASSETS_PATH / "background.png"
BANNER_FILE = ASSETS_PATH / "banner.png"

# 确保tmp目录存在
os.makedirs(TMP_PATH, exist_ok=True)

def check_user(service: XiuxianService, user_id: str):
    is_user, user_info, msg = False, None, "修仙界没有道友的信息，请输入【我要修仙】加入！"
    user_info = service.get_user_message(user_id)
    if user_info:
        is_user, msg = True, ''
    return is_user, user_info, msg


class Txt2Img:
    def __init__(self, size=30):
        self.font_family = str(FONT_FILE)
        self.user_font_size = int(size * 1.5)
        self.lrc_font_size = int(size)
        self.line_space = int(size)
        self.lrc_line_space = int(size / 2)
        self.share_img_width = 1080

    def _wrap(self, string):
        max_width = int(1850 / self.lrc_font_size)
        temp_len, result = 0, ''
        for ch in string:
            result += ch
            temp_len += wcwidth(ch)
            if ch == '\n': temp_len = 0
            if temp_len >= max_width:
                temp_len = 0
                result += '\n'
        return result.rstrip()

    def save(self, title, lrc) -> Path:
        if not os.path.exists(self.font_family):
            logger.error(f"字体文件未找到: {self.font_family}")
            raise FileNotFoundError(f"字体文件丢失: {self.font_family}")

        border_color, text_color = (220, 211, 196), (125, 101, 89)
        out_padding, padding, banner_size = 30, 45, 20

        user_font = ImageFont.truetype(self.font_family, self.user_font_size)
        lyric_font = ImageFont.truetype(self.font_family, self.lrc_font_size)

        lrc = self._wrap(lrc)
        lrc_lines = lrc.split('\n')
        lrc_rows = len(lrc_lines)

        w = self.share_img_width
        
        # --- 这是本次修复的核心：调整代码顺序 ---
        
        # 1. 为了计算文本高度，我们先创建一个临时的、不可见的 ImageDraw 对象
        temp_img = Image.new('RGB', (1, 1))
        temp_draw = ImageDraw.Draw(temp_img)

        h_title = self.user_font_size + self.line_space if title and title.strip() else 0
        # 2. 使用临时的 ImageDraw 对象来计算精确高度
        lrc_h = sum([temp_draw.textbbox((0, 0), line, font=lyric_font)[3] for line in lrc_lines]) + max(0, lrc_rows - 1) * self.lrc_line_space
        
        # --- 修复结束 ---

        inner_h = padding * 2 + h_title + lrc_h
        h = out_padding * 2 + inner_h

        # 3. 现在创建我们真正要用的 Image 和 ImageDraw 对象
        out_img = Image.new(mode="RGB", size=(int(w), int(h)), color=(255, 255, 255))
        draw = ImageDraw.Draw(out_img)

        # ... (绘制背景和边框的代码保持不变)
        if BACKGROUND_FILE.exists() and BANNER_FILE.exists():
            mi_img = Image.open(BACKGROUND_FILE)
            mi_banner = Image.open(BANNER_FILE).resize((banner_size, banner_size), resample=Image.Resampling.LANCZOS)
            for x in range(int(math.ceil(h / 100))):
                out_img.paste(mi_img, (0, x * 100))
            def draw_rectangle(draw_instance, rect, width):
                for i in range(width):
                    draw_instance.rectangle((rect[0] + i, rect[1] + i, rect[2] - i, rect[3] - i), outline=border_color)
            draw_rectangle(draw, (out_padding, out_padding, w - out_padding, h - out_padding), 2)
            out_img.paste(mi_banner, (out_padding, out_padding))
            out_img.paste(mi_banner.transpose(Image.FLIP_TOP_BOTTOM), (out_padding, int(h - out_padding - banner_size + 1)))
            out_img.paste(mi_banner.transpose(Image.FLIP_LEFT_RIGHT), (int(w - out_padding - banner_size + 1), out_padding))
            out_img.paste(mi_banner.transpose(Image.FLIP_LEFT_RIGHT).transpose(Image.FLIP_TOP_BOTTOM), (int(w - out_padding - banner_size + 1), int(h - out_padding - banner_size + 1)))

        current_y = out_padding + padding
        
        if title and title.strip():
            title_bbox = draw.textbbox((0,0), title, font=user_font)
            title_w = title_bbox[2] - title_bbox[0]
            draw.text(((w - title_w) / 2, current_y), title, font=user_font, fill=text_color)
            current_y += self.user_font_size + self.line_space

        for line in lrc_lines:
            draw.text((out_padding + padding, current_y), line, font=lyric_font, fill=text_color)
            line_bbox = draw.textbbox((0,0), line, font=lyric_font)
            current_y += (line_bbox[3] - line_bbox[1]) + self.lrc_line_space

        save_path = TMP_PATH / f"{int(time.time() * 1000)}.png"
        out_img.save(save_path)
        return save_path


async def get_msg_pic(msg: str, title: str = ' ', font_size: int = 55) -> Path:
    img_creator = Txt2Img(font_size)
    return img_creator.save(title, msg)

async def pic_msg_format(msg: str, event: AstrMessageEvent) -> str:
    user_name = event.get_sender_name() if event.get_sender_name() else event.get_sender_id()
    return f"@{user_name}\n{msg}"
# 用于存储正在处理指令的用户ID集合
_user_locks = set()

def command_lock(func):
    """
    一个装饰器，用于防止用户在上一条指令处理完成前发送新指令。
    """
    @wraps(func)
    async def decorated_function(plugin_instance, event: AstrMessageEvent, *args, **kwargs):
        #user_id = event.get_sender_id()
        #if user_id in _user_locks:
        #    # 如果用户已在处理列表中，发送提示并直接返回
        #    msg = "道友的指令正在处理中，请稍安勿躁..."
        #    # 注意：这里我们直接使用 plugin_instance 的方法来发送消息
        #    async for r in plugin_instance._send_response(event, msg):
        #        yield r
        #    return

        #_user_locks.add(user_id)
        try:
            # 异步生成器需要特殊处理
            async for result in func(plugin_instance, event, *args, **kwargs):
                yield result
        finally:
            pass
            # 确保无论成功还是异常，都能解除锁定
            #if user_id in _user_locks:
            #    _user_locks.remove(user_id)

    return decorated_function

def format_percentage(value: float, plus_sign: bool = False) -> str:
    """将小数转换为百分比字符串，例如 0.05 -> 5% """
    s = f"{value * 100:.1f}%".replace(".0%", "%") # 去掉不必要的 .0
    if plus_sign and value > 0 and not s.startswith('+'):
        return f"+{s}"
    return s

def format_item_details(item_data: dict) -> str | None:
    """
    根据物品数据字典，格式化该物品的详细描述字符串。
    :param item_data: 从 Items().get_data_by_item_id() 获取到的物品信息字典。
    :return: 格式化后的字符串，如果item_data无效则返回None。
    """
    if not item_data or not isinstance(item_data, dict):
        return "未能找到该物品的详细信息。"

    name = item_data.get('name', '未知物品')
    item_true_type = item_data.get('item_type', '未知类别') # 这是加载时赋予的内部类型

    # 统一从item_data中获取品阶信息
    # 功法类交换过，所以 'level' 是品阶；其他类是 'rank'
    if item_true_type in ["功法", "辅修功法", "神通"]:
        rank_display = item_data.get('level', '未知品阶') # 对于技能类，'level'字段现在是品阶
    else:
        rank_display = item_data.get('rank', '未知品阶') # 其他物品，'rank'字段是品阶
        if isinstance(rank_display, int): # 如果rank是数字，可能需要映射为文本，或直接显示
            # 你可能有一个 USERRANK 的反向映射，或者直接显示数字等级对应的品阶名
            # 为了简化，我们先直接用rank值，如果它是文本就直接用
            pass


    desc_lines = [f"【{name}】"]
    desc_lines.append(f"类型: {item_true_type} | 品阶: {rank_display}")

    description_field = item_data.get('desc') # 物品本身的描述字段
    if description_field:
        desc_lines.append(f"描述: {description_field}")

    # 根据不同类型添加特定信息
    if item_true_type == "法器": # 武器
        atk_buff = item_data.get('atk_buff', 0.0) * 100
        crit_buff = item_data.get('crit_buff', 0.0) * 100
        effects = []
        if atk_buff > 0: effects.append(f"攻击力+{atk_buff:.0f}%")
        if crit_buff > 0: effects.append(f"暴击率+{crit_buff:.0f}%")
        if effects: desc_lines.append(f"效果: {', '.join(effects)}")

    elif item_true_type == "防具":
        def_buff = item_data.get('def_buff', 0.0) * 100
        if def_buff > 0: desc_lines.append(f"效果: 减伤率+{def_buff:.0f}%")

    elif item_true_type == "功法": # 主修功法
        effects = []
        if item_data.get('hpbuff', 0) != 0: effects.append(f"生命+{item_data['hpbuff']*100:.0f}%")
        if item_data.get('mpbuff', 0) != 0: effects.append(f"真元+{item_data['mpbuff']*100:.0f}%")
        if item_data.get('atkbuff', 0) != 0: effects.append(f"攻击+{item_data['atkbuff']*100:.0f}%")
        if item_data.get('ratebuff', 0) != 0: effects.append(f"修炼速度+{item_data['ratebuff']*100:.0f}%")
        if effects: desc_lines.append(f"效果: {', '.join(effects)}")

    elif item_true_type == "辅修功法":
        buff_type_str = item_data.get('buff_type')
        buff_val_str = item_data.get('buff', "0")
        effect_desc = "未知效果"
        if buff_type_str == '1': effect_desc = f"攻击力+{buff_val_str}%"
        elif buff_type_str == '2': effect_desc = f"暴击率+{buff_val_str}%"
        elif buff_type_str == '3': effect_desc = f"暴击伤害+{buff_val_str}%"
        elif buff_type_str == '4': effect_desc = f"每回合气血回复+{buff_val_str}%"
        elif buff_type_str == '5': effect_desc = f"每回合真元回复+{buff_val_str}%"
        elif buff_type_str == '6': effect_desc = f"气血吸取+{buff_val_str}%"
        elif buff_type_str == '7': effect_desc = f"真元吸取+{buff_val_str}%"
        elif buff_type_str == '8': effect_desc = f"对敌中毒效果+{buff_val_str}%"
        desc_lines.append(f"效果: {effect_desc}")

    elif item_true_type == "神通":
        # 神通的描述比较复杂，直接使用原版 get_sec_msg 的逻辑（如果适用）或简化
        # 这里我先用它自带的 desc 字段，并指出其消耗
        hpcost_p = item_data.get('hpcost', 0) * 100
        mpcost_p = item_data.get('mpcost', 0) * 100 # 假设原版mpcost是基于exp的百分比，这里简化
        skill_type = item_data.get('skill_type')

        cost_str_parts = []
        if hpcost_p > 0: cost_str_parts.append(f"消耗当前生命{hpcost_p:.0f}%")
        if mpcost_p > 0: cost_str_parts.append(f"消耗当前真元{mpcost_p:.0f}%") # 或者 "消耗最大真元xx%"

        effect_details = []
        if skill_type == 1: # 直接伤害类
            atk_values_str = ", ".join([f"{v}倍" for v in item_data.get('atkvalue', [])])
            effect_details.append(f"造成 {len(item_data.get('atkvalue', []))} 次伤害，分别为基础攻击的 {atk_values_str}")
            if item_data.get('turncost', 0) > 0 : effect_details.append(f"释放后休息 {item_data['turncost']} 回合")
        elif skill_type == 2: # 持续伤害
             effect_details.append(f"造成 {item_data.get('atkvalue',0)} 倍攻击的持续伤害，持续 {item_data.get('turncost',0)} 回合")
        elif skill_type == 3: # Buff类
            buff_type_val = item_data.get('bufftype')
            buff_val = item_data.get('buffvalue',0)
            if buff_type_val == 1: effect_details.append(f"提升自身 {buff_val*100:.0f}% 攻击力")
            elif buff_type_val == 2: effect_details.append(f"提升自身 {buff_val*100:.0f}% 减伤率")
            effect_details.append(f"持续 {item_data.get('turncost',0)} 回合")
        elif skill_type == 4: # 封印类
            effect_details.append(f"尝试封印对手，成功率 {item_data.get('success', 100)}%，持续 {item_data.get('turncost',0)} 回合")

        if item_data.get('desc'): # 神通自带的描述通常是flavor text
             desc_lines.append(f"lore: {item_data.get('desc')}")
        if effect_details:
            desc_lines.append(f"战斗效果: {'; '.join(effect_details)}")
        if cost_str_parts:
            desc_lines.append(f"使用条件: {', '.join(cost_str_parts)}")
        desc_lines.append(f"释放概率: {item_data.get('rate', 100)}%")


    elif item_true_type == "丹药" or item_true_type == "合成丹药":
        # 'desc' 字段通常已经包含了效果描述
        if 'buff_type' in item_data: # 更详细的说明
            bt = item_data['buff_type']
            bv = item_data.get('buff', 0)
            if bt == "hp": desc_lines.append(f"  具体: 回复最大生命 {bv*100:.0f}%")
            elif bt == "exp_up": desc_lines.append(f"  具体: 增加修为 {bv} 点")
            elif bt == "atk_buff": desc_lines.append(f"  具体: 永久增加攻击力 {bv} 点")
            elif bt == "level_up_rate": desc_lines.append(f"  具体: 下次突破成功率 +{bv}%")
            elif bt == "level_up_big": desc_lines.append(f"  具体: 冲击大境界时突破成功率 +{bv}%")
        if 'day_num' in item_data: desc_lines.append(f"  每日使用上限: {item_data.get('day_num', '无限制')}")
        if 'all_num' in item_data: desc_lines.append(f"  总使用上限: {item_data.get('all_num', '无限制')}")
        if '境界' in item_data: desc_lines.append(f"  使用境界: {item_data['境界']}")


    elif item_true_type == "药材":
        # 主药、药引、辅药的冷热、药性、效力
        # YAOCAIINFOMSG 需定义或从原版引入
        YAOCAIINFOMSG = { "-1": "性寒", "0": "性平", "1": "性热", "2": "生息", "3": "养气", "4": "炼气", "5": "聚元", "6": "凝神" }
        main_herb = item_data.get('主药')
        catalyst_herb = item_data.get('药引')
        aux_herb = item_data.get('辅药')
        if main_herb:
            desc_lines.append(f"  主药效用: {YAOCAIINFOMSG.get(str(main_herb.get('h_a_c',{}).get('type')),'')} {main_herb.get('h_a_c',{}).get('power','')} | {YAOCAIINFOMSG.get(str(main_herb.get('type')),'')} {main_herb.get('power','')}")
        if catalyst_herb:
             desc_lines.append(f"  药引效用: {YAOCAIINFOMSG.get(str(catalyst_herb.get('h_a_c',{}).get('type')),'')} {catalyst_herb.get('h_a_c',{}).get('power','')}") #药引只有冷热
        if aux_herb:
            desc_lines.append(f"  辅药效用: {YAOCAIINFOMSG.get(str(aux_herb.get('type')),'')} {aux_herb.get('power','')}")

    elif item_true_type == "炼丹炉":
        buff = item_data.get('buff', 0)
        desc_lines.append(f"  效果: 炼丹时额外产出丹药 +{buff} 枚")

    elif item_true_type == "聚灵旗":
        speed_buff = item_data.get('修炼速度', 0)
        herb_speed_buff = item_data.get('药材速度', 0)
        effects = []
        if speed_buff > 0 : effects.append(f"洞天修炼速度提升等级 {speed_buff}") # 原版似乎是等级，不是百分比
        if herb_speed_buff > 0 : effects.append(f"灵田药材生长速度提升等级 {herb_speed_buff}")
        if effects: desc_lines.append(f"  效果: {', '.join(effects)}")

    return "\n".join(desc_lines)
