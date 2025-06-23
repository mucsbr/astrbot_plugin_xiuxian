import os
import time
from pathlib import Path
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont

from .service import UserDate, BuffInfo, XiuxianService
from .item_manager import Items
from .utils import format_percentage

# 定义资源文件和临时文件路径
ASSETS_PATH = Path(__file__).parent / "assets"
TMP_PATH = Path(__file__).parent / "tmp" # 确保与 utils.py 一致
FONT_PATH = str(ASSETS_PATH / "sarasa-mono-sc-regular.ttf")

# 确保tmp目录存在
os.makedirs(TMP_PATH, exist_ok=True)

# 检查字体文件是否存在
if not os.path.exists(FONT_PATH):
    raise FileNotFoundError(f"字体文件未找到，请确保 {FONT_PATH} 存在！")

#def get_user_info_img(user_info: UserDate, user_buff_info: BuffInfo, service: XiuxianService) -> Path:
#    """
#    生成用户修仙信息图片, 保存到本地并返回文件路径(Path)
#    """
#    font_size = 32
#    font = ImageFont.truetype(FONT_PATH, font_size)
#    
#    black, white, red, blue = (0, 0, 0), (255, 255, 255), (255, 0, 0), (0, 0, 255)
#
#    img_w, img_h = 1000, 800
#    img = Image.new('RGB', (img_w, img_h), white)
#    draw = ImageDraw.Draw(img)
#
#    title = f"{user_info.user_name} 的修仙信息"
#    title_bbox = draw.textbbox((0, 0), title, font=font)
#    title_w = title_bbox[2] - title_bbox[0]
#    draw.text(((img_w - title_w) / 2, 30), title, font=font, fill=black)
#    
#    x, y = 60, 120
#    line_height = 50
#
#    draw.text((x, y), f"道号: {user_info.user_name}", font=font, fill=black)
#    y += line_height
#    draw.text((x, y), f"境界: {user_info.level}", font=font, fill=black)
#    y += line_height
#    draw.text((x, y), f"灵根: {user_info.root} ({user_info.root_type})", font=font, fill=black)
#    y += line_height
#    draw.text((x, y), f"修为: {user_info.exp}", font=font, fill=black)
#    y += line_height
#    draw.text((x, y), f"灵石: {user_info.stone}", font=font, fill=black)
#    
#    y += line_height * 1.5
#    
#    # 假设 user_buff_info 可能没有这些属性，提供默认值
#    hp_buff = getattr(user_buff_info, 'hp_buff', 0)
#    mp_buff = getattr(user_buff_info, 'mp_buff', 0)
#    
#    user_real_info = service.get_user_real_info(user_info.user_id)
#    if not user_real_info:
#        # 在获取真实信息失败时提供一个回退，防止崩溃
#        user_real_info = {
#            "max_hp": service.cal_max_hp(user_info, 0),
#            "max_mp": service.cal_max_mp(user_info, 0),
#            "atk": user_info.atk
#        }
#
#    draw.text((x, y), f"生命: {user_info.hp}/{user_real_info['max_hp']}", font=font, fill=red)
#    y += line_height
#    draw.text((x, y), f"真元: {user_info.mp}/{user_real_info['max_mp']}", font=font, fill=blue)
#    y += line_height
#    draw.text((x, y), f"攻击: {user_real_info['atk']}", font=font, fill=black)
#    y += line_height
#    draw.text((x, y), f"战力: {user_info.power}", font=font, fill=black)
#
#    
#    y = 120
#    x = 550
#    draw.text((x, y), "功法 & 装备:", font=font, fill=black)
#    y += line_height
#
#    items_manager = Items()
#    
#    main_ex = items_manager.get_data_by_item_id(user_buff_info.main_buff)
#    sec_ex = items_manager.get_data_by_item_id(user_buff_info.sec_buff)
#    weapon = items_manager.get_data_by_item_id(user_buff_info.fabao_weapon)
#    armor = items_manager.get_data_by_item_id(user_buff_info.armor_buff)
#
#    draw.text((x + 20, y), f"主修: {main_ex.get('name', '无') if main_ex else '无'}", font=font, fill=black)
#    y += line_height
#    draw.text((x + 20, y), f"辅修: {sec_ex.get('name', '无') if sec_ex else '无'}", font=font, fill=black)
#    y += line_height
#    draw.text((x + 20, y), f"武器: {weapon.get('name', '无') if weapon else '无'}", font=font, fill=black)
#    y += line_height
#    draw.text((x + 20, y), f"防具: {armor.get('name', '无') if armor else '无'}", font=font, fill=black)
#
#    save_path = TMP_PATH / f"user_info_{int(time.time() * 1000)}.png"
#    img.save(save_path)
#    return save_path

#def get_user_info_img(user_id: str, user_real_info: dict, service: XiuxianService) -> Path: # 修改参数，直接接收计算好的 real_info
#    """
#    【修正版】生成用户修仙信息图片, 保存到本地并返回文件路径(Path)
#    :param user_id: 用户QQ号
#    :param user_real_info: 经过service.get_user_real_info()计算后的完整用户属性字典
#    :param service: XiuxianService 实例，用于获取物品名称等
#    """
#    font_size_title = 40
#    font_size_header = 36
#    font_size_text = 30
#    font_size_small = 24
#
#    font_title = ImageFont.truetype(FONT_PATH, font_size_title)
#    font_header = ImageFont.truetype(FONT_PATH, font_size_header)
#    font_text = ImageFont.truetype(FONT_PATH, font_size_text)
#    font_small = ImageFont.truetype(FONT_PATH, font_size_small)
#
#    # 颜色
#    black = (30, 30, 30)
#    grey = (100, 100, 100)
#    white = (255, 255, 255)
#    bg_color = (245, 248, 250) # 淡雅背景色
#    card_bg_color = (255, 255, 255)
#    border_color = (220, 220, 220)
#    accent_color = (0, 123, 255) # 蓝色强调
#
#    # 布局
#    img_w, img_h_base = 1000, 900 # 基础高度，会根据内容动态增加
#    padding = 40
#    line_height_text = font_size_text + 15
#    line_height_header = font_size_header + 10
#    avatar_size = 150
#
#    # 提取信息 (从 user_real_info 中获取)
#    user_name = user_real_info.get('user_name', "道友")
#    level = user_real_info.get('level', "未知")
#    exp = user_real_info.get('exp', 0)
#    stone = user_real_info.get('stone', 0)
#    root = user_real_info.get('root', "凡体")
#    root_type = user_real_info.get('root_type', "无")
#    # 修炼效率直接从 real_info 获取
#    exp_rate_percent = format_percentage(user_real_info.get('final_exp_rate', 1.0) -1) # 显示超出100%的部分
#
#    hp = user_real_info.get('hp', 0)
#    max_hp = user_real_info.get('max_hp', 1)
#    mp = user_real_info.get('mp', 0)
#    max_mp = user_real_info.get('max_mp', 1)
#    atk = user_real_info.get('atk', 0)
#
#    crit_rate_percent = format_percentage(user_real_info.get('crit_rate', 0))
#    crit_damage_percent = format_percentage(user_real_info.get('crit_damage', 0), plus_sign=True) # 暴伤通常显示为额外伤害
#    defense_rate_percent = format_percentage(user_real_info.get('defense_rate', 0))
#
#    power = user_real_info.get('power', 0) # 使用计算后的战力
#
#    # 获取功法和装备名称
#    items_manager = service.items # 使用传入的 service 中的 items 实例
#    buff_info = user_real_info.get('buff_info') # BuffInfo对象
#
#    main_ex_name = "无"
#    if buff_info and buff_info.main_buff != 0:
#        main_ex = items_manager.get_data_by_item_id(buff_info.main_buff)
#        if main_ex: main_ex_name = f"{main_ex.get('name', '未知功法')} ({main_ex.get('level', '未知品阶')})"
#
#    sub_ex_name = "无"
#    if buff_info and buff_info.sub_buff != 0:
#        sub_ex = items_manager.get_data_by_item_id(buff_info.sub_buff)
#        if sub_ex: sub_ex_name = f"{sub_ex.get('name', '未知辅修')} ({sub_ex.get('level', '未知品阶')})"
#
#    sec_ex_name = "无" # 神通
#    if buff_info and buff_info.sec_buff != 0:
#        sec_ex = items_manager.get_data_by_item_id(buff_info.sec_buff)
#        if sec_ex: sec_ex_name = f"{sec_ex.get('name', '未知神通')} ({sec_ex.get('level', '未知品阶')})"
#
#    weapon_name = "无"
#    if buff_info and buff_info.fabao_weapon != 0:
#        weapon = items_manager.get_data_by_item_id(buff_info.fabao_weapon)
#        if weapon: weapon_name = f"{weapon.get('name', '未知法器')} ({weapon.get('level', '未知品阶')})"
#
#    armor_name = "无"
#    if buff_info and buff_info.armor_buff != 0:
#        armor = items_manager.get_data_by_item_id(buff_info.armor_buff)
#        if armor: armor_name = f"{armor.get('name', '未知防具')} ({armor.get('level', '未知品阶')})"
#
#    # 动态计算图片高度
#    # 基础信息部分：7行
#    # 战斗属性部分：5行
#    # 功法装备部分：5行
#    # 假设每部分之间有额外间距
#    num_lines = 7 + 5 + 5 + 3 # 3是标题和部分间隔
#    img_h = padding * 2 + font_size_title + 20 + num_lines * line_height_text + 2 * (padding / 2)
#
#    img = Image.new('RGB', (img_w, int(img_h)), bg_color)
#    draw = ImageDraw.Draw(img)
#
#    # 标题
#    title_text = f"{user_name} 的修仙信息"
#    title_bbox = draw.textbbox((0,0), title_text, font=font_title)
#    title_w = title_bbox[2] - title_bbox[0]
#    draw.text(((img_w - title_w) / 2, padding), title_text, font=font_title, fill=black)
#    current_y = padding + font_size_title + 20
#
#    # 分割线函数
#    def draw_separator(y_pos):
#        draw.line([(padding, y_pos), (img_w - padding, y_pos)], fill=border_color, width=1)
#        return y_pos + padding / 2
#
#    # 基础信息
#    draw.text((padding, current_y), "基础信息", font=font_header, fill=accent_color)
#    current_y += line_height_header
#    info_list_base = [
#        f"道号: {user_name}",
#        f"境界: {level}",
#        f"灵根: {root} ({root_type})",
#        f"修为: {exp}",
#        f"灵石: {stone}",
#        f"战力: {power}",
#        f"修炼效率加成: {exp_rate_percent}",
#    ]
#    for item in info_list_base:
#        draw.text((padding + 20, current_y), item, font=font_text, fill=black)
#        current_y += line_height_text
#
#    current_y = draw_separator(current_y)
#
#    # 战斗属性
#    draw.text((padding, current_y), "战斗属性", font=font_header, fill=accent_color)
#    current_y += line_height_header
#    info_list_combat = [
#        f"生命: {hp}/{max_hp}",
#        f"真元: {mp}/{max_mp}",
#        f"攻击: {atk}",
#        f"暴击率: {crit_rate_percent} | 暴击伤害: {crit_damage_percent}", # 合并显示
#        f"减伤率: {defense_rate_percent}",
#    ]
#    for item in info_list_combat:
#        draw.text((padding + 20, current_y), item, font=font_text, fill=black)
#        current_y += line_height_text
#
#    current_y = draw_separator(current_y)
#
#    # 功法装备
#    draw.text((padding, current_y), "功法装备", font=font_header, fill=accent_color)
#    current_y += line_height_header
#    info_list_equip = [
#        f"主修功法: {main_ex_name}",
#        f"辅修功法: {sub_ex_name}",
#        f"神 通: {sec_ex_name}",
#        f"武 器: {weapon_name}",
#        f"防 具: {armor_name}",
#    ]
#    for item in info_list_equip:
#        draw.text((padding + 20, current_y), item, font=font_text, fill=black)
#        current_y += line_height_text
#    # (可选) 尝试绘制头像 - 这部分代码依赖你的 get_avatar_by_user_id_and_save 实现
#    # try:
#    #     avatar_img = await get_avatar_by_user_id_and_save(user_id, TMP_PATH) # 假设返回PIL.Image
#    #     avatar_img = avatar_img.resize((avatar_size, avatar_size))
#        
#    #     # 创建圆形遮罩
#    #     mask = Image.new('L', (avatar_size, avatar_size), 0)
#    #     mask_draw = ImageDraw.Draw(mask)
#    #     mask_draw.ellipse((0, 0, avatar_size, avatar_size), fill=255)
#        
#    #     # 粘贴头像
#    #     avatar_x = img_w - padding - avatar_size
#    #     avatar_y = padding + font_size_title + 20 
#    #     img.paste(avatar_img, (avatar_x, avatar_y), mask)
#    # except Exception as e:
#    #     logger.error(f"绘制头像失败 for {user_id}: {e}")
#
#
#    save_path = TMP_PATH / f"user_info_{user_id}_{int(time.time() * 1000)}.png"
#    img.save(save_path)
#    return save_path

def get_user_info_img(user_id: str, user_real_info: dict, service_items_instance: Items) -> Path:
    """
    【AstrBot 平台修正版】生成用户修仙信息图片, 保存到本地并返回文件路径(Path)
    :param user_id: 用户ID (主要用于头像和文件名)
    :param user_real_info: 经过service.get_user_real_info()计算后的完整用户属性字典
    :param service_items_instance: Items 类的实例，用于获取物品名称
    """
    font_size_title = 38
    font_size_header = 32
    font_size_text = 28
    font_size_small = 22

    try:
        font_title = ImageFont.truetype(FONT_PATH, font_size_title)
        font_header = ImageFont.truetype(FONT_PATH, font_size_header)
        font_text = ImageFont.truetype(FONT_PATH, font_size_text)
        font_small = ImageFont.truetype(FONT_PATH, font_size_small)
    except IOError: # 字体加载失败则使用默认字体
        font_title = ImageFont.load_default()
        font_header = ImageFont.load_default()
        font_text = ImageFont.load_default()
        font_small = ImageFont.load_default()


    # 颜色
    black = (40, 40, 40)
    grey = (100, 100, 100)
    white = (255, 255, 255)
    bg_color = (240, 242, 245)
    card_bg_color = (255, 255, 255)
    border_color = (210, 215, 220)
    accent_color = (23, 125, 220)

    # 布局
    img_w = 1000
    padding = 35
    line_height_text = font_size_text + 18
    line_height_header = font_size_header + 12
    avatar_size = 160 # 头像大小

    # 提取信息
    user_name = user_real_info.get('user_name', "道友")
    level = user_real_info.get('level', "未知")
    exp = user_real_info.get('exp', 0)
    stone = user_real_info.get('stone', 0)
    root = user_real_info.get('root', "凡体")
    root_type = user_real_info.get('root_type', "无")
    exp_rate_percent = format_percentage(user_real_info.get('final_exp_rate', 1.0) - 1.0, plus_sign=True)

    hp = user_real_info.get('hp', 0)
    max_hp = user_real_info.get('max_hp', 1)
    mp = user_real_info.get('mp', 0)
    max_mp = user_real_info.get('max_mp', 1)
    atk = user_real_info.get('atk', 0)

    crit_rate_percent = format_percentage(user_real_info.get('crit_rate', 0.05)) # 基础5%
    crit_damage_percent = format_percentage(user_real_info.get('crit_damage', 0.5), plus_sign=True) # 基础+50%
    defense_rate_percent = format_percentage(user_real_info.get('defense_rate', 0.0))

    power = user_real_info.get('power', 0)
    atk_practice_level = user_real_info.get('atk_practice_level', 0)


    items_manager = service_items_instance # 使用传入的 Items 实例
    buff_info_raw = user_real_info.get('buff_info')

    def get_item_display_name(item_id):
        if item_id == 0: return "无"
        item = items_manager.get_data_by_item_id(item_id)
        if item:
            # 原版数据中功法的 rank 是品阶，level 是等级（可能是装备要求或功法自身等级）
            # 你在 item_manager 中交换了它们，所以 item['level'] 现在是品阶
            item_level_display = item.get('level', '未知品阶') # 确保有默认值
            return f"{item.get('name', '未知物品')} ({item_level_display})"
        return "查询失败"

    main_ex_name = get_item_display_name(buff_info_raw.main_buff if buff_info_raw else 0)
    sub_ex_name = get_item_display_name(buff_info_raw.sub_buff if buff_info_raw else 0)
    sec_ex_name = get_item_display_name(buff_info_raw.sec_buff if buff_info_raw else 0) # 神通
    weapon_name = get_item_display_name(buff_info_raw.fabao_weapon if buff_info_raw else 0)
    armor_name = get_item_display_name(buff_info_raw.armor_buff if buff_info_raw else 0)

    # 动态计算图片高度
    sections = [
        ["基础信息", [f"道号: {user_name}", f"境界: {level}", f"灵根: {root} ({root_type})", f"修为: {exp}", f"灵石: {stone}", f"战力: {power}", f"修炼效率: {exp_rate_percent}"]],
        ["战斗属性", [f"生命: {hp}/{max_hp}", f"真元: {mp}/{max_mp}", f"攻击: {atk} (攻修: {atk_practice_level}级)", f"暴击率: {crit_rate_percent}", f"暴击伤害: {crit_damage_percent}", f"减伤率: {defense_rate_percent}"]],
        ["功法装备", [f"主修: {main_ex_name}", f"辅修: {sub_ex_name}", f"神通: {sec_ex_name}", f"武器: {weapon_name}", f"防具: {armor_name}"]]
    ]

    img_h = padding * 2 + font_size_title + 20 # 标题高度
    for header, content_list in sections:
        img_h += line_height_header # 区域头高度
        img_h += len(content_list) * line_height_text # 内容高度
        img_h += padding / 2 # 区域间隔

    img = Image.new('RGB', (img_w, int(img_h)), bg_color)
    draw = ImageDraw.Draw(img)

    # 标题
    title_text = f"道友『{user_name}』的修行之路"
    title_bbox = draw.textbbox((0,0), title_text, font=font_title)
    title_w = title_bbox[2] - title_bbox[0]
    draw.text(((img_w - title_w) / 2, padding), title_text, font=font_title, fill=black)
    current_y = padding + font_size_title + 20

    # 头像 (放在右上角)
    # avatar_img = await get_avatar_by_user_id_and_save(user_id, TMP_PATH) # 假设是同步的或已提前获取
    # avatar_x = img_w - padding - avatar_size
    # avatar_y = padding
    # img.paste(avatar_img, (avatar_x, avatar_y), avatar_img) # 假设avatar_img是RGBA带透明

    # 绘制各个部分
    for header_text, content_list in sections:
        draw.text((padding, current_y), header_text, font=font_header, fill=accent_color)
        current_y += line_height_header
        for item_text in content_list:
            draw.text((padding + 20, current_y), item_text, font=font_text, fill=black)
            current_y += line_height_text
        current_y += padding / 2 # 区域间隔
        if header_text != sections[-1][0]: # 最后一部分后不画分割线
             draw.line([(padding, current_y - padding / 4), (img_w - padding, current_y - padding / 4)], fill=border_color, width=1)


    save_path = TMP_PATH / f"user_info_{user_id}_{int(time.time() * 1000)}.png"
    try:
        img.save(save_path)
    except Exception as e:
        print(f"图片保存失败: {e}") # 在实际插件中用 logger.error
        # 可以考虑保存一个错误提示图片或返回None
        return None # 或者抛出异常
    return save_path
