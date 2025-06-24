import os
from datetime import datetime, timedelta
import re
from pathlib import Path
import random
import json

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
import astrbot.api.message_components as Comp
from astrbot.api import logger

from .service import XiuxianService, BuffInfo
from .config import XiuConfig, USERRANK
from .scheduler import XianScheduler
from .utils import get_msg_pic, pic_msg_format, check_user, command_lock, format_percentage, format_item_details
from .data_manager import jsondata
from .info_draw import get_user_info_img
from .bounty_manager import BountyManager
from .alchemy_manager import AlchemyManager
from .rift_manager import RiftManager
from .fishing.service import FishingService
from .fishing import enhancement_config
from .fishing.draw import draw_fishing_ranking
from .pvp_manager import PvPManager
from .gacha_manager import GachaManager

def get_coins_name():
    """获取金币名称"""
    return "灵石"

def get_fish_pond_inventory_grade(fish_pond_inventory):
    """计算鱼塘背包的等级"""
    total_value = fish_pond_inventory
    if total_value == 480:
        return "初级"
    elif total_value < 1000:
        return "中级"
    elif total_value < 10000:
        return "高级"
    else:
        return "顶级"

@register(
    "修仙模拟器", 
    "astr-xiuxian", 
    "一个文字修仙模拟器", 
    "1.0.0", 
    "s52047qwas & YourName"
)
class XiuxianPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.data_dir = "data/xiuxian/"
        os.makedirs(self.data_dir, exist_ok=True)
        db_path = os.path.join(self.data_dir, "xiuxian.db")
        self.XiuXianService = XiuxianService(db_path)
        self.xiu_config = XiuConfig()
        self.groups = set() 
        self.user_bounties = {}
        self.group_boss = {}
        self.world_boss = None
        self.refreshnum = {}
        self.market_goods = {}
        self.auction_data = None
        self.MANUAL_ADMIN_WXIDS = ["qq--666666", "another_admin_wxid"]
        self.last_battle_details_log = {}

        fishing_db_path = os.path.join(self.data_dir, "fish.db")
        self.FishingService = FishingService(fishing_db_path, self.XiuXianService)

        # 实例化所有管理器
        self.alchemy_manager = AlchemyManager(self.XiuXianService)
        self.bounty_manager = BountyManager()
        self.rift_manager = RiftManager()
        self.scheduler = XianScheduler(self.context, self.XiuXianService, self)
        # GachaManager 需要 XiuXianService, Items (通过 XiuXianService.items 获取), 和 XiuConfig 实例
        self.gacha_manager = GachaManager(self.XiuXianService, self.XiuXianService.items, self.xiu_config)

    async def initialize(self):
        logger.info("修仙插件加载成功！")
        # v-- 加载全局BOSS，而非分群BOSS --v
        self.world_boss = self.XiuXianService.get_active_boss()
        if self.world_boss:
            logger.info(f"成功从数据库加载世界BOSS【{self.world_boss['name']}】。")
        else:
            logger.info("数据库中无活跃的世界BOSS。")
        # v-- 从数据库加载活跃的群组到内存 --v
        self.groups = self.XiuXianService.get_all_active_groups()
        logger.info(f"成功从数据库加载 {len(self.groups)} 个活跃群组。")
        # ^-- 从数据库加载活跃的群组到内存 --^

        self.scheduler.start()

    async def _update_active_groups(self, event: AstrMessageEvent):
        """动态更新互动过的群聊列表，并存入数据库"""
        session_id = event.unified_msg_origin
        if session_id and len(session_id) > 5:
            if session_id not in self.groups:
                self.groups.add(session_id) # 添加到内存
                self.XiuXianService.add_active_group(session_id) # 添加到数据库
                logger.info(f"已将新群聊 {session_id} 添加到推送列表并持久化。")

    async def _store_last_battle_details(self, user_id: str, detailed_log: list):
        """存储指定用户的最近一次战斗详细日志"""
        if not detailed_log: # 如果没有详细日志，就不存储
            if user_id in self.last_battle_details_log:
                del self.last_battle_details_log[user_id] # 清除旧的，如果有的话
            return
        self.last_battle_details_log[user_id] = detailed_log

    @filter.command("我要修仙")
    @command_lock
    async def start_xiuxian(self, event: AstrMessageEvent):
        await self._update_active_groups(event)
        user_id = event.get_sender_id()
        user_name = event.get_sender_name() if event.get_sender_name() else str(user_id)
        result = self.XiuXianService.register_user(user_id, user_name)
        
        if self.xiu_config.img:
            message = await pic_msg_format(result["message"], event)
            image_path = await get_msg_pic(message)
            yield event.chain_result([
                Comp.Image.fromFileSystem(str(image_path))
            ])
        else:
            yield event.plain_result(result["message"])

    @filter.command("修仙帮助")
    @command_lock
    async def help_xiuxian(self, event: AstrMessageEvent):
        await self._update_active_groups(event)
        
        help_notes = f"""
======= 基础指令 =======
【我要修仙】：开启你的修仙之旅
【我的修仙信息】：查看个人详细数据
【修仙签到】：每日获取灵石和修为
【改名 [新道号]】：更换你的道号
【重入仙途】：消耗灵石重置灵根 (CD: 30分钟)

======= 修炼与成长 =======
【闭关】：持续获得修为 (离线挂机)
【出关】：结束闭关状态，结算收益
【突破】：当修为足够时，尝试突破至下一境界

======= 战斗与交互 =======
【抢劫 [@用户]】：强制PVP，胜利可夺取少量灵石 (CD: 10分钟)
【切磋 [@用户]】：友好比试，无惩罚 (CD: 5分钟)
【送灵石 [@用户] [数量]】：赠予他人灵石
【排行榜 [修为/灵石/战力]】：查看服务器内排名

======= 物品与装备 =======
【背包】：查看你拥有的所有物品
【使用 [物品名] [数量]】：使用丹药等消耗品
【穿戴 [装备名]】：装备背包中的法器或防具
【卸下 [法器/防具]】：卸下已穿戴的装备
【丢弃 [物品名] [数量]】：从背包中移除物品
【物品信息】：查看物品简介

======= 坊市与交易 (玩家市场) =======
【坊市】：浏览当前坊市中其他玩家上架的商品
【坊市上架 [物品名] [价格]】：将你的物品上架出售
【坊市购买 [商品编号]】：购买坊市中的指定商品
【坊市下架 [商品编号]】：取回你上架的物品
【出价 [金额]】：参与正在进行的拍卖会

======= 核心玩法系统 =======
【世界boss帮助】：查看世界BOSS相关指令
【悬赏帮助】：查看悬赏令任务相关指令
【秘境帮助】：查看秘境探险相关指令
【炼丹帮助】：查看炼丹与灵田相关指令
【功法帮助】：查看功法神通相关指令
【宗门帮助】：查看宗门相关指令
【灵庄帮助】：查看灵庄存取款相关指令
【万法宝鉴】：查看神通抽奖池子相关指令
【神兵宝库】：查看法器抽奖池子相关指令
【万古功法阁】：查看主修功法抽奖池子相关指令
【玄甲宝殿】：查看防具抽奖池子相关指令
【银行帮助】：查看物品抵押贷款相关指令
"""
        title = '修仙模拟器帮助信息'
        font_size = 24 # 减小字体以容纳更多内容
        image_path = await get_msg_pic(help_notes.strip(), title, font_size)
        yield event.chain_result([
            Comp.Image.fromFileSystem(str(image_path))
        ]) 

    async def _get_at_user_id(self, event: AstrMessageEvent) -> str | None:
        """
        从消息事件中解析出被@用户的ID
        这是一个适配微信平台的特定解析方法
        """
        try:
            if raw_msg := getattr(event.message_obj, "raw_message", None):
                if isinstance(raw_msg, dict) and 'msg_source' in raw_msg:
                    msg_source = raw_msg['msg_source']
                    match = re.search(r"<atuserlist>(.*?)</atuserlist>", msg_source)
                    if match:
                        cdata_content = match.group(1).strip()
                        wxids_string = cdata_content[9:-3] if cdata_content.startswith('<![CDATA[') else cdata_content
                        wxid_list = [wxid for wxid in wxids_string.split(',') if wxid]
                        if wxid_list:
                            return wxid_list[0]
        except Exception as e:
            logger.error(f"解析 @ 用户失败: {e}")
        return None

    async def _send_response(self, event: AstrMessageEvent, msg: str, title: str = ' ', font_size: int = 40):
        """
        统一响应发送器，根据配置发送图片或文本
        :param font_size: 生成图片时使用的字体大小
        """
        if self.xiu_config.cmd_img:
            formatted_msg = await pic_msg_format(msg, event)
            # v-- 这是本次修正的核心：将 font_size 参数传递给图片生成函数 --v
            image_path = await get_msg_pic(formatted_msg, title, font_size)
            # ^-- 这是本次修正的核心 --^
            yield event.chain_result([Comp.Image.fromFileSystem(str(image_path))])
        else:
            yield event.plain_result(msg)
        
    @filter.command("修仙签到")
    @command_lock
    async def sign_in_xiuxian(self, event: AstrMessageEvent):
        await self._update_active_groups(event)
        user_id = event.get_sender_id()
        is_user, _, msg = check_user(self.XiuXianService, user_id)
        if not is_user:
            if self.xiu_config.img:
                image_path = await get_msg_pic(await pic_msg_format(msg, event))
                yield event.chain_result([
                    Comp.Image.fromFileSystem(str(image_path))
                ])
            else:
                yield event.plain_result(msg)
            return
            
        result = self.XiuXianService.get_sign(user_id)
        if self.xiu_config.img:
            image_path = await get_msg_pic(await pic_msg_format(result["message"], event))
            yield event.chain_result([
                Comp.Image.fromFileSystem(str(image_path))
            ])
        else:
            yield event.plain_result(result["message"])

    @filter.command("我的修仙信息", alias={"信息", "存档"})
    @command_lock
    async def my_xiuxian_info(self, event: AstrMessageEvent):
        await self._update_active_groups(event)
        user_id = event.get_sender_id()
        is_user, user_info, msg = check_user(self.XiuXianService, user_id)
        if not is_user:
            if self.xiu_config.img:
                image_path = await get_msg_pic(await pic_msg_format(msg, event))
                yield event.chain_result([Comp.Image.fromFileSystem(str(image_path))])
            else:
                yield event.plain_result(msg)
            return

        # 获取计算后的真实属性
        user_real_info = self.XiuXianService.get_user_real_info(user_id)
        if not user_real_info:
            error_msg = "道友的信息获取失败，请稍后再试或联系管理员。"
            if self.xiu_config.img:
                formatted_msg = await pic_msg_format(error_msg, event)
                image_path = await get_msg_pic(formatted_msg, "错误")
                yield event.chain_result([Comp.Image.fromFileSystem(str(image_path))])
            else:
                yield event.plain_result(error_msg)
            return

        # 调用新的绘图函数，并传入计算好的属性和 Items 实例
        try:
            # 注意：get_user_info_img 现在是同步函数
            info_img_path = get_user_info_img(user_id, user_real_info, self.XiuXianService.items)
            if info_img_path:
                 yield event.chain_result([
                    Comp.Image.fromFileSystem(str(info_img_path))
                ])
            else:
                yield event.plain_result("生成用户信息图片失败，请联系管理员。")
        except Exception as e:
            logger.error(f"生成用户信息图失败: {e}")
            yield event.plain_result(f"生成图片时遇到问题，请联系管理员查看日志。错误: {str(e)[:100]}") # 只显示部分错误信息

    @filter.command("闭关")
    @command_lock
    async def start_closing_cmd(self, event: AstrMessageEvent):
        await self._update_active_groups(event)
        user_id = event.get_sender_id()
        is_user, _, msg = check_user(self.XiuXianService, user_id)
        if not is_user:
            async for r in self._send_response(event, msg): yield r
            return

        user_cd_info = self.XiuXianService._get_user_cd_by_type(user_id, 1) # 精确查询闭关状态
        if user_cd_info:
            msg = "道友已在闭关中，请勿重复闭关！"
        else:
            self.XiuXianService.start_closing(user_id, str(datetime.now()))
            msg = "道友已开始闭关，每分钟都会增加修为！"

        async for r in self._send_response(event, msg):
            yield r

    @filter.command("出关")
    async def end_closing_cmd(self, event: AstrMessageEvent):
        await self._update_active_groups(event)
        user_id = event.get_sender_id()
        is_user, user_info, msg = check_user(self.XiuXianService, user_id)
        if not is_user:
            async for r in self._send_response(event, msg): yield r
            return

        closing_info = self.XiuXianService.get_closing_info(user_id)
        if not closing_info:
            msg = "道友尚未闭关，无需出关！"
        else:
            # 1. 计算闭关时长
            close_time = datetime.fromisoformat(closing_info.create_time)
            now_time = datetime.now()
            diff_minutes = int((now_time - close_time).total_seconds() / 60)

            if diff_minutes < 1:
                msg = "闭关时间不足1分钟，未能有所精进。"
                self.XiuXianService.end_closing(user_id) # 即使没收益也要结束闭关状态
                async for r in self._send_response(event, msg): yield r
                return

            # 2. 获取玩家的最终修炼效率
            user_real_info = self.XiuXianService.get_user_real_info(user_id)
            if not user_real_info:
                msg = "错误：无法获取道友的修炼信息，出关失败！"
                async for r in self._send_response(event, msg): yield r
                return
            final_exp_rate = user_real_info.get("final_exp_rate", 1.0)

            # 3. 计算本次闭关获得的修为
            # 总收益 = 闭关时长 * 基础闭关经验 * 最终综合效率
            added_exp = int(diff_minutes * self.xiu_config.closing_exp * final_exp_rate)

            # 4. 检查是否达到修为上限
            next_level_info = self.XiuXianService.get_next_level_info(user_info.level)
            if next_level_info:
                max_exp_limit = int(next_level_info['power'] * self.xiu_config.closing_exp_upper_limit)
                exp_can_gain = max(0, max_exp_limit - user_info.exp)

                if added_exp > exp_can_gain:
                    added_exp = exp_can_gain # 不能超出上限
                    limit_msg = "（已达当前境界瓶颈）"
                else:
                    limit_msg = ""
            else: # 已是最高境界
                 added_exp = 0
                 limit_msg = "（已达世界之巅，闭关无法再精进分毫！）"


            hp_healed = diff_minutes * self.xiu_config.closing_hp_heal_rate
            self.XiuXianService.update_hp(user_id, hp_healed, 1) # 1代表增加
            heal_msg = f"期间共恢复了 {hp_healed} 点生命。"

            # 5. 更新数据并结束闭关
            self.XiuXianService.update_exp(user_id, added_exp)
            self.XiuXianService.end_closing(user_id)

            # 刷新属性，但只在获得修为时才刷新，避免满级时也刷新
            if added_exp > 0:
                self.XiuXianService.refresh_user_base_attributes(user_id)
                self.XiuXianService.update_power2(user_id)

            msg = f"道友本次闭关 {diff_minutes} 分钟，共获得 {added_exp} 点修为！{limit_msg}\n{heal_msg}"

        async for r in self._send_response(event, msg):
            yield r

    @filter.command("突破")
    async def level_up_cmd(self, event: AstrMessageEvent):
        await self._update_active_groups(event)
        user_id = event.get_sender_id()
        is_user, user_info, msg = check_user(self.XiuXianService, user_id)
        if not is_user:
            async for r in self._send_response(event, msg): yield r
            return

        # 检查是否在CD中，现在只有成功才会有CD
        #level_up_cd_str = user_info.level_up_cd
        #if level_up_cd_str:
        #    cd_time = datetime.fromisoformat(level_up_cd_str)
        #    if (datetime.now() - cd_time).total_seconds() < self.xiu_config.level_up_cd * 60:
        #        remaining_time = int(self.xiu_config.level_up_cd * 60 - (datetime.now() - cd_time).total_seconds())
        #        msg = f"道友刚突破不久，气息尚不稳固，请等待 {remaining_time // 60}分{remaining_time % 60}秒 后再尝试。"
        #        async for r in self._send_response(event, msg): yield r
        #        return
        
        # ... (获取下一境界和所需修为的逻辑保持不变)
        all_levels = self.xiu_config.level
        if user_info.level == all_levels[-1]:
             msg = f"道友已是当前世界的巅峰，无法再突破！"
             async for r in self._send_response(event, msg): yield r
             return

        current_level_index = all_levels.index(user_info.level)
        next_level = all_levels[current_level_index + 1]
        level_data = jsondata.level_data()
        required_exp = level_data.get(next_level, {}).get("power")
        if not required_exp or user_info.exp < required_exp:
            msg = f"道友的修为不足以冲击【{next_level}】！\n所需修为: {required_exp} (还需 {required_exp - user_info.exp})"
            async for r in self._send_response(event, msg): yield r
            return
        
        # 1. 判定是否触发死劫
        death_config = self.xiu_config.death_calamity_config
        base_death_rate = death_config['probability'] # 基础死劫概率，例如 0.01 (1%)
        user_real_info = self.XiuXianService.get_user_real_info(user_id)
        if not user_real_info: # 如果获取失败，则不增加概率
             final_death_rate = base_death_rate
        else:
            # b. 如果玩家处于重伤状态（例如HP低于最大值的10%），则大幅增加死劫概率
            if user_real_info['hp'] <= user_real_info['max_hp'] * 0.1:
                final_death_rate = base_death_rate * 10  # 死劫概率变为10倍！
                msg_lines = ["\n道友身负重伤竟敢强行渡劫，此举逆天而行，死劫概率大增！"]
            else:
                final_death_rate = base_death_rate
                msg_lines = [] # 如果不是重伤，则清空提示

        if random.random() < final_death_rate:
            # --- 死劫触发 ---
            msg_lines = [f"天劫之中竟暗藏九天寂灭神雷！道友未能抵挡，身死道消..."]
            reduce_penalty_buff_active = self.XiuXianService.check_and_consume_temp_buff(user_id, "reduce_breakthrough_penalty")
            if reduce_penalty_buff_active:
                msg_lines.append(f"幸得【渡厄丹】庇佑，本次突破失败未损失修为！")
                async for r in self._send_response(event, "\n".join(msg_lines), "天道无情"):
                    yield r
                return
            
            # a. 散播遗产
            exp_to_give = int(user_info.exp / 2)
            stone_to_give = int(user_info.stone / 2)
            all_other_users = [uid for uid in self.XiuXianService.get_all_user_ids() if uid != user_id]
            if all_other_users:
                exp_per_user = exp_to_give // len(all_other_users)
                stone_per_user = stone_to_give // len(all_other_users)
                for other_user_id in all_other_users:
                    self.XiuXianService.update_exp(other_user_id, exp_per_user)
                    self.XiuXianService.update_ls(other_user_id, stone_per_user, 1)
                msg_lines.append(f"你毕生修为与财富化作漫天霞光，福泽了此界 {len(all_other_users)} 位道友！")

            # b. 执行转世重置
            reincarnation_buff = death_config['reincarnation_buff']
            reset_result = self.XiuXianService.reset_user_for_reincarnation(user_id, user_info.user_name, reincarnation_buff['修炼速度加成'])
            
            if reset_result['success']:
                msg_lines.append(f"但天道有轮回，你的一缕真灵得以保留，带着【{reincarnation_buff['name']}】转世重生！")
                msg_lines.append(f"你的新灵根为：【{reset_result['root']}】，修炼速度永久提升 {reincarnation_buff['修炼速度加成']*100}%！")
            
            async for r in self._send_response(event, "\n".join(msg_lines), "天道无情"):
                yield r
            return

        # 2. 如果未触发死劫，则正常进行突破判定
        base_rate = jsondata.level_rate_data().get(user_info.level, 30)
        bonus_rate = user_info.level_up_rate
        final_rate = min(100, base_rate + bonus_rate)
        msg_lines = [f"道友准备冲击【{next_level}】，当前成功率为 {final_rate}%..."]

        if random.randint(1, 100) <= final_rate:
            # --- 突破成功 ---
            self.XiuXianService.update_level(user_id, next_level)
            self.XiuXianService.reset_user_level_up_rate(user_id)
            self.XiuXianService.update_j_exp(user_id, required_exp)
            self.XiuXianService.refresh_user_base_attributes(user_id)
            self.XiuXianService.update_power2(user_id)
            self.XiuXianService.set_user_cd(user_id, self.xiu_config.level_up_cd, 1) # type=1 代表突破CD
            msg_lines.append(f"天降祥瑞，恭喜道友成功突破至【{next_level}】！")
        else:
            # --- 突破失败 ---
            self.XiuXianService.update_hp(user_id, 999999999, 2) # HP置为1
            # 确保至少剩1点血
            cur = self.XiuXianService.conn.cursor()
            cur.execute("UPDATE user_xiuxian SET hp = 1 WHERE user_id = ? and hp <= 0", (user_id,))
            self.XiuXianService.conn.commit()

            rate_gain = max(1, int(base_rate * self.xiu_config.level_up_probability))
            self.XiuXianService.update_user_level_up_rate(user_id, rate_gain)
            msg_lines.append(f"天劫降临，道友渡劫失败，身受重伤，气血仅剩1点！")
            msg_lines.append(f"不过，这次失败让你对天道感悟更深，下次突破成功率增加了 {rate_gain}%！")
            
        async for r in self._send_response(event, "\n".join(msg_lines)):
            yield r

    @filter.command("背包")
    @command_lock
    async def my_backpack_cmd(self, event: AstrMessageEvent):
        """处理我的背包指令"""
        await self._update_active_groups(event)
        user_id = event.get_sender_id()
        is_user, _, msg = check_user(self.XiuXianService, user_id)
        if not is_user:
            yield event.chain_result([Comp.Image.fromFileSystem(str(await get_msg_pic(await pic_msg_format(msg, event))))])
            return

        items = self.XiuXianService.get_user_back_msg(user_id)
        # --- 新增过滤逻辑：剔除药材 ---
        items_to_display = []
        for item in items:
            if item.goods_type != "药材":
                items_to_display.append(item)

        # --- 结束新增过滤逻辑 ---
        if not items_to_display:
            msg = "道友的背包空空如也！"
        else:
            msg_lines = ["\n道友的背包里有："]
            for item in items_to_display:
                msg_lines.append(f"【{item.goods_type}】{item.goods_name} x {item.goods_num}")


        msg = "\n".join(
            " ".join(msg_lines[i:i+4]) 
            for i in range(0, len(msg_lines), 4)
        )

        async for r in self._send_response(event, msg):
            yield r


    @filter.command("丢弃")
    @command_lock
    async def drop_item_cmd(self, event: AstrMessageEvent):
        """处理丢弃物品指令"""
        await self._update_active_groups(event)
        user_id = event.get_sender_id()
        is_user, _, msg = check_user(self.XiuXianService, user_id)
        if not is_user:
            yield event.chain_result([Comp.Image.fromFileSystem(str(await get_msg_pic(await pic_msg_format(msg, event))))])
            return

        # v-- 采用您提供的 split 方案 --v
        args = event.message_str.split()
        if len(args) < 3:
            msg = "指令格式错误，请输入“丢弃 [物品名] [数量]”"
        else:
            item_name = args[1]
            try:
                num = int(args[2])
                if num <= 0: raise ValueError
                result = self.XiuXianService.remove_item(user_id, item_name, num)
                msg = f"成功丢弃 {item_name} x{num}" if result else f"背包中的【{item_name}】数量不足！"
            except ValueError:
                msg = "丢弃数量必须是一个大于0的整数！"
        # ^-- 修正参数解析 --^

        #args = event.message_str.strip().split()
        #if len(args) < 2:
        #    msg = "指令格式错误，请输入“丢弃 [物品名] [数量]”，例如：丢弃 下品灵石 10"
        #    yield event.chain_result([Comp.Image.fromFileSystem(str(await get_msg_pic(await pic_msg_format(msg, event))))])
        #    return

        #item_name = args[0]
        #try:
        #    item_num_to_drop = int(args[1])
        #    if item_num_to_drop <= 0:
        #        raise ValueError
        #except ValueError:
        #    msg = "丢弃数量必须是一个大于0的整数！"
        #    yield event.chain_result([Comp.Image.fromFileSystem(str(await get_msg_pic(await pic_msg_format(msg, event))))])
        #    return

        #user_item = self.XiuXianService.get_item_by_name(user_id, item_name)
        #if not user_item or user_item.goods_num < item_num_to_drop:
        #    msg = f"道友的背包里没有足够的 {item_name}！"
        #    yield event.chain_result([Comp.Image.fromFileSystem(str(await get_msg_pic(await pic_msg_format(msg, event))))])
        #    return

        ## 执行丢弃
        #self.XiuXianService.remove_item(user_id, item_name, item_num_to_drop)
        #msg = f"道友成功丢弃了 {item_name} x {item_num_to_drop}。"
        yield event.chain_result([Comp.Image.fromFileSystem(str(await get_msg_pic(await pic_msg_format(msg, event))))])

    # v-- 新增指令处理器 --v
    @filter.command("穿戴")
    @command_lock
    async def equip_item_cmd(self, event: AstrMessageEvent):
        """处理穿戴装备指令"""
        await self._update_active_groups(event)
        user_id = event.get_sender_id()
        is_user, _, msg = check_user(self.XiuXianService, user_id)
        if not is_user:
            yield event.chain_result([Comp.Image.fromFileSystem(str(await get_msg_pic(await pic_msg_format(msg, event))))])
            return
        args = event.message_str.split()
        item_name = args[1] if len(args) >= 2 else ""
        if not item_name:
            msg = "请输入要穿戴的装备名，例如：穿戴 木剑"
            yield event.chain_result([Comp.Image.fromFileSystem(str(await get_msg_pic(await pic_msg_format(msg, event))))])
            return

        item_in_backpack = self.XiuXianService.get_item_by_name(user_id, item_name)
        if not item_in_backpack:
            msg = f"道友的背包里没有 {item_name} 哦！"
            yield event.chain_result([Comp.Image.fromFileSystem(str(await get_msg_pic(await pic_msg_format(msg, event))))])
            return

        result = self.XiuXianService.equip_item(user_id, item_in_backpack.goods_id)
        if result["success"]:
            self.XiuXianService.update_power2(user_id)  # 更新战力等
        yield event.chain_result([Comp.Image.fromFileSystem(str(await get_msg_pic(await pic_msg_format(result["message"], event))))])

    @filter.command("卸下")
    @command_lock
    async def unequip_item_cmd(self, event: AstrMessageEvent):
        """处理卸下装备指令"""
        await self._update_active_groups(event)
        user_id = event.get_sender_id()
        is_user, _, msg = check_user(self.XiuXianService, user_id)
        if not is_user:
            yield event.chain_result([Comp.Image.fromFileSystem(str(await get_msg_pic(await pic_msg_format(msg, event))))])
            return
        args = event.message_str.split()
        item_type_to_unequip = args[1] if len(args) >= 2 else ""
        if not item_type_to_unequip:
            msg = "请输入要卸下的装备类型，例如：卸下 法器 或 卸下 防具"
            yield event.chain_result([Comp.Image.fromFileSystem(str(await get_msg_pic(await pic_msg_format(msg, event))))])
            return

        result = self.XiuXianService.unequip_item(user_id, item_type_to_unequip)
        yield event.chain_result([Comp.Image.fromFileSystem(str(await get_msg_pic(await pic_msg_format(result["message"], event))))])

    @filter.command("坊市")
    @command_lock
    async def view_market_cmd(self, event: AstrMessageEvent):
        await self._update_active_groups(event)
        is_user, _, msg = check_user(self.XiuXianService, event.get_sender_id())
        if not is_user:
            async for r in self._send_response(event, msg): yield r
            return

        group_id = event.get_session_id()
        goods_list = self.XiuXianService.get_market_goods_by_group()

        if not goods_list:
            msg = "现在的坊市空空如也，等待有缘人上架第一件商品！"
            async for r in self._send_response(event, msg): yield r
            return

        msg_lines = ["\n坊市正在出售以下商品："]
        for item in goods_list:
            item_info = self.XiuXianService.items.get_data_by_item_id(item.goods_id)
            desc = item_info.get('desc', '效果未知')
            s = f"编号:{item.id}【{item.goods_name}】({item.goods_type})\n - 效果: {desc}\n - 价格: {item.price} 灵石\n - 卖家: {item.user_name}"
            msg_lines.append(s)

        msg = "\n\n".join(msg_lines)
        async for r in self._send_response(event, msg, "坊市商品列表", font_size=24):
            yield r

    @filter.command("坊市上架")
    @command_lock
    async def list_item_cmd(self, event: AstrMessageEvent):
        await self._update_active_groups(event)
        user_id = event.get_sender_id()
        is_user, _, msg = check_user(self.XiuXianService, user_id)
        if not is_user:
            async for r in self._send_response(event, msg): yield r
            return

        args = event.message_str.split()
        if len(args) < 3:
            msg = "指令格式错误！请输入：坊市上架 [物品名] [价格]"
            async for r in self._send_response(event, msg): yield r
            return

        item_name = args[1]
        try:
            price = int(args[2])
            if price <= 0: raise ValueError
        except ValueError:
            msg = "价格必须是一个大于0的整数！"
            async for r in self._send_response(event, msg): yield r
            return

        item_in_backpack = self.XiuXianService.get_item_by_name(user_id, item_name)
        if not item_in_backpack:
            msg = f"道友的背包里没有【{item_name}】！"
            async for r in self._send_response(event, msg): yield r
            return

        # 消耗背包中的物品
        if not self.XiuXianService.remove_item(user_id, item_name, 1):
            msg = "错误：扣除背包物品失败！" # 理论上不会发生
            async for r in self._send_response(event, msg): yield r
            return

        # 上架到坊市
        group_id = event.get_session_id()
        self.XiuXianService.add_market_goods(user_id, item_in_backpack.goods_id, item_in_backpack.goods_type, price)

        msg = f"道友已成功将【{item_name}】以 {price} 灵石的价格上架到坊市！"
        async for r in self._send_response(event, msg):
            yield r

    @filter.command("坊市购买")
    @command_lock
    async def buy_item_cmd(self, event: AstrMessageEvent):
        await self._update_active_groups(event)
        user_id = event.get_sender_id()
        is_user, user_info, msg = check_user(self.XiuXianService, user_id)
        if not is_user:
            async for r in self._send_response(event, msg): yield r
            return

        args = event.message_str.split()
        if len(args) < 2:
            msg = "指令格式错误！请输入：坊市购买 [商品编号]"
            async for r in self._send_response(event, msg): yield r
            return

        try:
            market_id = int(args[1])
        except ValueError:
            msg = "商品编号必须是数字！"
            async for r in self._send_response(event, msg): yield r
            return

        group_id = event.get_session_id()
        target_good = self.XiuXianService.get_market_goods_by_id(market_id)

        if not target_good:
            msg = "坊市中没有这个编号的商品！"
            async for r in self._send_response(event, msg): yield r
            return

        if user_info.stone < target_good.price:
            msg = f"灵石不足！购买此物品需要 {target_good.price} 灵石。"
            async for r in self._send_response(event, msg): yield r
            return

        if target_good.user_id == user_id:
            msg = "道友为何要购买自己上架的物品？"
            async for r in self._send_response(event, msg): yield r
            return

        # 执行交易
        # 1. 从坊市移除商品
        if not self.XiuXianService.remove_market_goods_by_id(market_id):
            msg = "手慢了，这件商品刚刚被别人买走了！"
            async for r in self._send_response(event, msg): yield r
            return

        # 2. 扣除买家灵石
        self.XiuXianService.update_ls(user_id, target_good.price, 2)

        # 3. 物品入买家背包
        self.XiuXianService.add_item(user_id, target_good.goods_id, target_good.goods_type, 1)

        # 4. 灵石给卖家 (有手续费)
        tax = int(target_good.price * 0.05) # 5%手续费
        income = target_good.price - tax
        self.XiuXianService.update_ls(target_good.user_id, income, 1)

        msg = f"交易成功！你花费 {target_good.price} 灵石购买了【{target_good.goods_name}】。"
        async for r in self._send_response(event, msg):
            yield r

    @filter.command("坊市下架")
    @command_lock
    async def unlist_item_cmd(self, event: AstrMessageEvent):
        await self._update_active_groups(event)
        user_id = event.get_sender_id()
        is_user, _, msg = check_user(self.XiuXianService, user_id)
        if not is_user:
            async for r in self._send_response(event, msg): yield r
            return

        args = event.message_str.split()
        if len(args) < 2:
            msg = "指令格式错误！请输入：坊市下架 [商品编号]"
            async for r in self._send_response(event, msg): yield r
            return
            
        try:
            market_id = int(args[1])
        except ValueError:
            msg = "商品编号必须是数字！"
            async for r in self._send_response(event, msg): yield r
            return

        group_id = event.get_session_id()
        target_good = self.XiuXianService.get_market_goods_by_id(market_id)
        
        if not target_good:
            msg = "坊市中没有这个编号的商品！"
            async for r in self._send_response(event, msg): yield r
            return
            
        # 权限检查：只有物主或管理员可以下架
        if target_good.user_id != user_id: # 假设平台没有管理员角色，暂不实现
            msg = "这不是你上架的物品，无法下架！"
            async for r in self._send_response(event, msg): yield r
            return
            
        # 执行下架
        if self.XiuXianService.remove_market_goods_by_id(market_id):
            # 物品返还背包
            self.XiuXianService.add_item(user_id, target_good.goods_id, target_good.goods_type, 1)
            msg = f"你已成功将【{target_good.goods_name}】从坊市下架。"
        else:
            msg = "下架失败，可能物品已被购买或不存在。"
        
        async for r in self._send_response(event, msg):
            yield r

    @filter.command("宗门帮助")
    @command_lock
    async def sect_help_cmd(self, event: AstrMessageEvent):
        await self._update_active_groups(event)
        help_notes = """
宗门指令：
1、创建宗门 [宗门名称]：建立自己的宗门
2、加入宗门 [宗门ID/名称]：加入心仪的宗门
3.、退出宗门：脱离当前宗门
4、宗门列表：查看当前所有宗门
5、我的宗门：查看自己所在宗门的详细信息
(更多宗门功能如任务、升级等敬请期待)
"""
        title = '宗门系统帮助'
        font_size = 30
        image_path = await get_msg_pic(await pic_msg_format(help_notes, event), title, font_size)
        yield event.chain_result([Comp.Image.fromFileSystem(str(image_path))])

    @filter.command("创建宗门")
    @command_lock
    async def create_sect_cmd(self, event: AstrMessageEvent):
        await self._update_active_groups(event)
        user_id = event.get_sender_id()
        is_user, _, msg = check_user(self.XiuXianService, user_id)
        if not is_user:
            yield event.chain_result([Comp.Image.fromFileSystem(str(await get_msg_pic(await pic_msg_format(msg, event))))])
            return

        args = event.message_str.split()
        sect_name = args[1] if len(args) >= 2 else ""
        if not sect_name:
            msg = "请输入一个响亮的宗门名称！例如：创建宗门 凌霄阁"
        else:
            result = self.XiuXianService.create_sect(user_id, sect_name)
            msg = result["message"]

        yield event.chain_result([Comp.Image.fromFileSystem(str(await get_msg_pic(await pic_msg_format(msg, event))))])

    @filter.command("宗门列表")
    @command_lock
    async def list_sects_cmd(self, event: AstrMessageEvent):
        await self._update_active_groups(event)
        all_sects = self.XiuXianService.get_all_sects()
        if not all_sects:
            msg = "当前仙界尚未有任何宗门建立。道友何不使用【创建宗门】指令，成为开宗立派第一人？"
        else:
            msg_lines = ["\n仙界宗门林立，详情如下："]
            for sect in all_sects:
                owner_info = self.XiuXianService.get_user_message(sect.sect_owner)
                owner_name = owner_info.user_name if owner_info else "未知"
                member_count = self.XiuXianService.get_sect_member_count(sect.sect_id)
                msg_lines.append(f"ID:{sect.sect_id} 【{sect.sect_name}】宗主:{owner_name} 等级:{sect.sect_scale}级 人数:{member_count}/{sect.sect_scale*10}")
            msg = "\n".join(msg_lines)

        yield event.chain_result([Comp.Image.fromFileSystem(str(await get_msg_pic(await pic_msg_format(msg, event))))])

    @filter.command("加入宗门")
    @command_lock
    async def join_sect_cmd(self, event: AstrMessageEvent):
        await self._update_active_groups(event)
        user_id = event.get_sender_id()
        is_user, _, msg = check_user(self.XiuXianService, user_id)
        if not is_user:
            yield event.chain_result([Comp.Image.fromFileSystem(str(await get_msg_pic(await pic_msg_format(msg, event))))])
            return

        args = event.message_str.split()
        sect_identifier = args[1] if len(args) >= 2 else ""
        if not sect_identifier:
            msg = "请输入想加入的宗门ID或名称！"
            yield event.chain_result([Comp.Image.fromFileSystem(str(await get_msg_pic(await pic_msg_format(msg, event))))])
            return

        target_sect = None
        if sect_identifier.isdigit():
            target_sect = self.XiuXianService.get_sect_info_by_id(int(sect_identifier))

        if not target_sect:
            target_sect = self.XiuXianService.get_sect_info_by_name(sect_identifier)

        if not target_sect:
            msg = f"未找到ID或名称为【{sect_identifier}】的宗门。"
        else:
            result = self.XiuXianService.join_sect(user_id, target_sect.sect_id)
            msg = result["message"]

        yield event.chain_result([Comp.Image.fromFileSystem(str(await get_msg_pic(await pic_msg_format(msg, event))))])

    @filter.command("退出宗门")
    @command_lock
    async def leave_sect_cmd(self, event: AstrMessageEvent):
        await self._update_active_groups(event)
        user_id = event.get_sender_id()
        is_user, _, msg = check_user(self.XiuXianService, user_id)
        if not is_user:
            yield event.chain_result([Comp.Image.fromFileSystem(str(await get_msg_pic(await pic_msg_format(msg, event))))])
            return

        result = self.XiuXianService.leave_sect(user_id)
        yield event.chain_result([Comp.Image.fromFileSystem(str(await get_msg_pic(await pic_msg_format(result['message'], event))))])

    @filter.command("我的宗门")
    @command_lock
    async def my_sect_cmd(self, event: AstrMessageEvent):
        await self._update_active_groups(event)
        user_id = event.get_sender_id()
        is_user, user_info, msg = check_user(self.XiuXianService, user_id)
        if not is_user:
            async for r in self._send_response(event, msg):
                yield r
            return

        if user_info.sect_id == 0:
            msg = "道友尚未加入任何宗门。"
            async for r in self._send_response(event, msg):
                yield r
            return

        sect_info = self.XiuXianService.get_sect_info_by_id(user_info.sect_id)

        # v-- 这是本次修正的核心：增加安全检查 --v
        if not sect_info:
            msg = "发生错误：你所属的宗门信息已不存在，已自动为你脱离宗门。"
            self.XiuXianService.reset_user_sect_info(user_id)
            async for r in self._send_response(event, msg):
                yield r
            return
        # ^-- 这是本次修正的核心 --^

        owner_info = self.XiuXianService.get_user_message(sect_info.sect_owner)
        owner_name = owner_info.user_name if owner_info else "未知"
        member_count = self.XiuXianService.get_sect_member_count(sect_info.sect_id)

        position_map = {0: "弟子", 1: "外门执事", 2: "内门执事", 3: "长老", 4: "宗主"}

        msg = f"""
宗门名称：【{sect_info.sect_name}】
宗门ID：{sect_info.sect_id}
宗主：{owner_name}
你的职位：{position_map.get(user_info.sect_position, '未知')}
宗门等级：{sect_info.sect_scale}
宗门人数：{member_count}/{sect_info.sect_scale*10}
宗门资材：{sect_info.sect_materials}
        """
        async for r in self._send_response(event, msg.strip()):
            yield r

        # v-- 新增指令处理器 --v
    @filter.command("世界boss帮助")
    @command_lock
    async def boss_help_cmd(self, event: AstrMessageEvent):
        await self._update_active_groups(event)
        help_notes = """
世界BOSS指令：
1、查看boss：查看当前世界BOSS的状态
2、攻击boss：对当前世界BOSS造成伤害
(BOSS由系统定时自动刷新)
"""
        title = '世界BOSS帮助'
        font_size = 30
        image_path = await get_msg_pic(await pic_msg_format(help_notes, event), title, font_size)
        yield event.chain_result([Comp.Image.fromFileSystem(str(image_path))])

    @filter.command("查看boss")
    @command_lock
    async def view_boss_cmd(self, event: AstrMessageEvent):
        await self._update_active_groups(event)
        group_id = event.get_session_id()

        if not self.world_boss:
            # v-- 这是本次修正的核心：查询并显示倒计时 --v
            boss_job = self.scheduler.scheduler.get_job("world_boss_job")
            if boss_job and boss_job.next_run_time:
                now_time = datetime.now(boss_job.next_run_time.tzinfo)
                remaining_seconds = (boss_job.next_run_time - now_time).total_seconds()
                minutes = int(remaining_seconds // 60)
                seconds = int(remaining_seconds % 60)
                msg = f"本界域一片祥和，暂无BOSS作乱。\n下只BOSS预计在【{minutes}分{seconds}秒】后出现。"
            else:
                msg = "本界域一片祥和，暂无BOSS作乱，且刷新时间未知。"
            # ^-- 这是本次修正的核心 --^
        else:
            msg = f"""
--【世界BOSS情报】--
名号：{self.world_boss['name']}
境界：{self.world_boss['jj']}
剩余血量：{self.world_boss['hp']}
修为奖励：{self.world_boss['exp']}
灵石奖励：{self.world_boss['stone']}
"""
        # ^-- 修改 --^
        async for r in self._send_response(event, msg.strip()):
            yield r

    @filter.command("攻击boss")
    @command_lock
    async def attack_boss_cmd(self, event: AstrMessageEvent):
        await self._update_active_groups(event)
        user_id = event.get_sender_id()
        is_user, user_info, msg = check_user(self.XiuXianService, user_id)
        if not is_user:
            async for r in self._send_response(event, msg): yield r
            return

        if not self.world_boss:
            msg = "本界域一片祥和，暂无BOSS可供攻击。"
            async for r in self._send_response(event, msg): yield r
            return

        # 检查CD
        boss_cd_type = 2 # 与抢劫共用CD类型
        boss_cd_duration = self.xiu_config.battle_boss_cd / 60 # 配置中是秒，这里转分钟
        remaining_cd = self.XiuXianService.check_user_cd_specific_type(user_id, boss_cd_type)
        if remaining_cd > 0:
            msg = f"道友的真气尚未平复，请等待 {remaining_cd // 60}分{remaining_cd % 60}秒 后再战！"
            async for r in self._send_response(event, msg): yield r
            return

        current_world_boss_data = self.world_boss
        boss_hp_before = current_world_boss_data['hp']
        # 记录攻击者
        current_world_boss_data.setdefault('attackers', set()).add(user_id)

       # 获取玩家和BOSS的完整战斗属性
        player_real_info = self.XiuXianService.get_user_real_info(user_id)
        if not player_real_info:
            msg = "无法获取道友的详细信息，请稍后再试。"
            async for r in self._send_response(event, msg): yield r
            return

        # BOSS信息也应该是一个与 player_real_info 结构类似的字典
        # 在 self.service.create_boss() 中已经返回了这样的字典
        boss_combat_info = current_world_boss_data # 直接使用内存中的BOSS数据

        # 执行战斗模拟 (玩家 vs BOSS)
        # 注意：simulate_player_vs_player_fight 的参数顺序是 p1_info, p2_info
        battle_result = PvPManager.simulate_player_vs_player_fight(player_real_info, boss_combat_info)
        # --- 存储详细战斗日志 ---
        if battle_result.get("battle_round_details_log"):
            # 为双方都存储同一份详细日志
            await self._store_last_battle_details(user_id, battle_result["battle_round_details_log"])
        # --- 结束存储 ---
        
        msg_lines = battle_result['log'] # 获取战斗日志
        boss_hp_after = battle_result['p2_hp_final']
        damage_this_round = boss_hp_before - boss_hp_after

        # 更新玩家实际HP (BOSS战是真实伤害)
        # battle_result['p1_hp_final'] 是玩家战斗后的模拟HP
        self.XiuXianService.update_hp_to_value(user_id, battle_result['p1_hp_final'])
        self.XiuXianService.update_mp_to_value(user_id, battle_result['p1_mp_final'])

        # 更新BOSS实际HP (数据库和内存)
        boss_new_hp = battle_result['p2_hp_final'] # p2 是BOSS
        self.XiuXianService.update_boss_hp(current_world_boss_data['id'], boss_new_hp)
        current_world_boss_data['hp'] = boss_new_hp # 更新内存中的BOSS血量

        # 记录伤害日志 (确保'damage_log'字典存在)
        current_world_boss_data.setdefault('damage_log', {})
        current_world_boss_data['damage_log'][user_id] = current_world_boss_data['damage_log'].get(user_id, 0) + damage_this_round
        msg_lines.append(f"道友对世界BOSS造成伤害：{damage_this_round}点")

        # 设置玩家CD
        self.XiuXianService.set_user_cd(user_id, boss_cd_duration, boss_cd_type)

        # 检查战斗结果
        if battle_result['winner'] == player_real_info['user_id']: # 玩家击败了BOSS
            msg_lines.append(f"\n🎉🎉🎉 恭喜道友【{player_real_info['user_name']}】神威盖世，成功击败了世界BOSS【{boss_combat_info['name']}】！ 🎉🎉🎉")


            total_exp_reward_pool = boss_combat_info.get('exp', 1000)
            total_stone_reward_pool = boss_combat_info.get('stone', 1000)
            final_hit_rewards, participant_drops = self.XiuXianService.get_boss_drop(
                {"jj": boss_combat_info['jj'], "exp": total_exp_reward_pool, "stone": total_stone_reward_pool}
            )

            damage_log = current_world_boss_data.get('damage_log', {})
            # 1. 计算总伤害
            total_damage_dealt = sum(damage_log.values())
            if total_damage_dealt <= 0:  # 防止除以零错误
                total_damage_dealt = 1

            # 2. 构建伤害贡献榜和分发奖励
            reward_details_lines = ["\n--- 伤害贡献榜 ---"]
            sorted_damagers = sorted(damage_log.items(), key=lambda item: item[1], reverse=True)

            for rank, (damager_id, damage_dealt) in enumerate(sorted_damagers, 1):
                damager_info = self.XiuXianService.get_user_message(damager_id)
                if not damager_info: continue

                damage_percentage = damage_dealt / total_damage_dealt

                # 计算并分发奖励
                exp_reward = int(final_hit_rewards["exp"] * damage_percentage)
                stone_reward = int(final_hit_rewards["stone"] * damage_percentage)

                reward_str_parts = []
                if exp_reward > 0:
                    self.XiuXianService.update_exp(damager_id, exp_reward)
                    reward_str_parts.append(f"修为+{exp_reward}")
                if stone_reward > 0:
                    self.XiuXianService.update_ls(damager_id, stone_reward, 1)
                    reward_str_parts.append(f"灵石+{stone_reward}")

                # 格式化榜单消息
                reward_details_lines.append(
                    f"第{rank}名:【{damager_info.user_name}】造成 {damage_dealt} 伤害 (占比: {damage_percentage:.2%})\n"
                    f"  奖励: {', '.join(reward_str_parts) if reward_str_parts else '无'}"
                )

            msg_lines.extend(reward_details_lines)

            #
            # # a. 处理最后一击奖励 (当前攻击者即为最后一击者)
            # if final_hit_rewards["exp"] > 0:
            #     self.XiuXianService.update_exp(user_id, final_hit_rewards["exp"])
            #     msg_lines.append(f"最后一击额外奖励：修为+{final_hit_rewards['exp']}")
            # if final_hit_rewards["stone"] > 0:
            #     self.XiuXianService.update_ls(user_id, final_hit_rewards["stone"], 1)
            #     msg_lines.append(f"最后一击额外奖励：灵石+{final_hit_rewards['stone']}")
            for item_reward in final_hit_rewards["items"]:
                self.XiuXianService.add_item(user_id, item_reward['id'], item_reward['type'], item_reward['quantity'])
                msg_lines.append(f"最后一击奇遇：获得【{item_reward['name']}】x{item_reward['quantity']}")

            # b. 处理所有参与者的奖励
            attackers = current_world_boss_data.get('attackers', {user_id})
            if participant_drops and attackers:
                msg_lines.append("\n--- 所有参与战斗的道友均获得了以下战利品 ---")
                for attacker_player_id in attackers:
                    player_drop_details = []
                    for drop in participant_drops:
                        is_for_current_player = (attacker_player_id == user_id)

                        if drop['type'] == "灵石":
                            self.XiuXianService.update_ls(attacker_player_id, drop['quantity'], 1)
                            if is_for_current_player: player_drop_details.append(f"灵石+{drop['quantity']}")
                        else:
                            self.XiuXianService.add_item(attacker_player_id, drop['id'], drop['type'], drop['quantity'])
                            if is_for_current_player: player_drop_details.append(f"【{drop['name']}】x{drop['quantity']}")

                    if is_for_current_player and player_drop_details:
                        msg_lines.append(f"参与奖励: {', '.join(player_drop_details)}")
                    elif not is_for_current_player: # 对其他攻击者可以简单记录日志
                         logger.info(f"BOSS战参与者 {attacker_player_id} 获得奖励: {', '.join(player_drop_details)}")

              # 构造简单的广播消息
            broadcast_final_message = (
                f"🎉 世界BOSS【{boss_combat_info['name']}】已被道友【{player_real_info['user_name']}】成功讨伐！🎉\n"
                "感谢各位道友的英勇奋战！详细奖励已发放给最后一击者及贡献者。"
            )
            await self.scheduler._broadcast_to_groups(broadcast_final_message, "世界BOSS已被讨伐")
            # 清理BOSS
            self.XiuXianService.delete_boss(current_world_boss_data['id'])
            self.world_boss = None # 清理插件实例中的BOSS缓存

        elif battle_result['winner'] == boss_combat_info['user_id']: # 玩家被BOSS击败
            msg_lines.append(f"\n💨 可惜，道友不敌【{boss_combat_info['name']}】，重伤败退！请勤加修炼再来挑战！")
            # 玩家HP已在上面更新为0或1

        elif battle_result['winner'] is None: # 平局或达到最大回合
            msg_lines.append(f"\n⚔️ 道友与【{boss_combat_info['name']}】鏖战许久，未分胜负，只能暂作休整。")

        final_msg = "\n".join(msg_lines)
        async for r in self._send_response(event, final_msg, "BOSS战报"):
            yield r

    @filter.command("悬赏帮助")
    @command_lock
    async def bounty_help_cmd(self, event: AstrMessageEvent):
        await self._update_active_groups(event)
        help_notes = """
悬赏令指令：
1、刷新悬赏：刷新可接取的悬赏任务(每日3次)
2、接取悬赏 [编号]：接取刷新列表中的任务
3、我的悬赏：查看当前已接取的任务信息
4、放弃悬赏：放弃当前任务(有惩罚)
5、完成悬赏：攻击讨伐目标或提交收集品
"""
        title = '悬赏令帮助'
        image_path = await get_msg_pic(await pic_msg_format(help_notes, event), title, 30)
        yield event.chain_result([Comp.Image.fromFileSystem(str(image_path))])

    @filter.command("刷新悬赏")
    @command_lock
    async def refresh_bounties_cmd(self, event: AstrMessageEvent):
        await self._update_active_groups(event)
        user_id = event.get_sender_id()
        is_user, user_info, msg = check_user(self.XiuXianService, user_id)
        if not is_user:
            yield event.chain_result([Comp.Image.fromFileSystem(str(await get_msg_pic(await pic_msg_format(msg, event))))])
            return

        # 检查每日刷新次数
        refresh_count = self.refreshnum.get(user_id, 0)
        if refresh_count >= 3:
            msg = "道友今日的悬赏刷新次数已用尽，请明日再来！"
            yield event.chain_result([Comp.Image.fromFileSystem(str(await get_msg_pic(await pic_msg_format(msg, event))))])
            return

        bounties = self.bounty_manager.generate_bounties(user_info.level)
        if not bounties:
            msg = "似乎没有适合道友当前境界的悬赏，请提升境界后再来吧！"
        else:
            self.user_bounties[user_id] = bounties # 缓存刷出的任务
            self.refreshnum[user_id] = refresh_count + 1

            msg_lines = ["\n本次为道友刷出以下悬赏："]
            for i, bounty in enumerate(bounties):
                msg_lines.append(f"编号{i+1}：【{bounty['type']}】{bounty['name']}")
            msg_lines.append("\n请使用【接取悬赏 编号】来接取任务")
            msg = "\n".join(msg_lines)

        yield event.chain_result([Comp.Image.fromFileSystem(str(await get_msg_pic(await pic_msg_format(msg, event))))])

    @filter.command("我的悬赏")
    @command_lock
    async def my_bounty_cmd(self, event: AstrMessageEvent):
        await self._update_active_groups(event)
        user_id = event.get_sender_id()
        is_user, _, msg = check_user(self.XiuXianService, user_id)
        if not is_user:
            yield event.chain_result([Comp.Image.fromFileSystem(str(await get_msg_pic(await pic_msg_format(msg, event))))])
            return

        bounty = self.XiuXianService.get_user_bounty(user_id)
        if not bounty:
            msg = "道友当前没有接取任何悬赏任务。"
        else:
            msg = f"道友当前的悬赏任务是：\n【{bounty['bounty_type']}】{bounty['bounty_name']}"

        yield event.chain_result([Comp.Image.fromFileSystem(str(await get_msg_pic(await pic_msg_format(msg, event))))])

    @filter.command("接取悬赏")
    @command_lock
    async def accept_bounty_cmd(self, event: AstrMessageEvent):
        await self._update_active_groups(event)
        user_id = event.get_sender_id()
        is_user, _, msg = check_user(self.XiuXianService, user_id)
        if not is_user:
            yield event.chain_result([Comp.Image.fromFileSystem(str(await get_msg_pic(await pic_msg_format(msg, event))))])
            return

        if self.XiuXianService.get_user_bounty(user_id):
            msg = "道友身上已有悬赏任务，请先完成或放弃！"
            yield event.chain_result([Comp.Image.fromFileSystem(str(await get_msg_pic(await pic_msg_format(msg, event))))])
            return

        if user_id not in self.user_bounties:
            msg = "请先使用【刷新悬赏】来获取任务列表！"
            yield event.chain_result([Comp.Image.fromFileSystem(str(await get_msg_pic(await pic_msg_format(msg, event))))])
            return

        try:
            # 从消息中移除指令部分，只保留参数
            arg_str = re.sub(r'接取悬赏', '', event.message_str, 1).strip()
            if not arg_str:
                raise ValueError("未提供编号")
            bounty_index = int(arg_str) - 1

            if not (0 <= bounty_index < len(self.user_bounties[user_id])):
                raise ValueError("编号越界")
        except:
            msg = "请输入正确的悬赏编号！"
            yield event.chain_result([Comp.Image.fromFileSystem(str(await get_msg_pic(await pic_msg_format(msg, event))))])
            return

        chosen_bounty = self.user_bounties[user_id][bounty_index]
        self.XiuXianService.accept_bounty(user_id, chosen_bounty)
        del self.user_bounties[user_id] # 接取后清除缓存

        msg = f"已成功接取悬赏任务：【{chosen_bounty['name']}】！"
        yield event.chain_result([Comp.Image.fromFileSystem(str(await get_msg_pic(await pic_msg_format(msg, event))))])

    @filter.command("放弃悬赏")
    @command_lock
    async def abandon_bounty_cmd(self, event: AstrMessageEvent):
        await self._update_active_groups(event)
        user_id = event.get_sender_id()
        is_user, _, msg = check_user(self.XiuXianService, user_id)
        if not is_user:
            yield event.chain_result([Comp.Image.fromFileSystem(str(await get_msg_pic(await pic_msg_format(msg, event))))])
            return

        if not self.XiuXianService.get_user_bounty(user_id):
            msg = "道友并无悬赏在身，无需放弃。"
        else:
            self.XiuXianService.abandon_bounty(user_id)
            # 放弃任务的惩罚：扣除少量灵石
            cost = 100
            self.XiuXianService.update_ls(user_id, cost, 2)
            msg = f"道友已放弃当前悬赏，并因违约损失了 {cost} 灵石。"

        yield event.chain_result([Comp.Image.fromFileSystem(str(await get_msg_pic(await pic_msg_format(msg, event))))])

    @filter.command("完成悬赏")
    @command_lock
    async def complete_bounty_cmd(self, event: AstrMessageEvent):
        """处理完成悬赏指令，根据任务类型不同有不同行为"""
        await self._update_active_groups(event)
        user_id = event.get_sender_id()
        is_user, user_info, msg = check_user(self.XiuXianService, user_id)
        if not is_user:
            async for r in self._send_response(event, msg): yield r
            return

        bounty = self.XiuXianService.get_user_bounty(user_id)
        if not bounty:
            msg = "道友尚未接取任何悬赏，无法完成。"
            async for r in self._send_response(event, msg): yield r
            return

        bounty_type = bounty.get("bounty_type") # 获取真实的类型，如："捉妖", "采药", "暗杀"
        bounty_name = bounty.get("bounty_name")
        msg = ""

        # v-- 这是本次修正的核心：从正确的数据源 jsondata 获取悬赏信息 --v
        all_bounties_data = jsondata.get_bounty_data()
        work_info = all_bounties_data.get(bounty_type, {}).get(bounty_name)

        if not work_info:
            msg = f"错误：在悬赏令数据中找不到【{bounty_name}】的详细信息！"
            self.XiuXianService.abandon_bounty(user_id) # 清理错误的任务
            async for r in self._send_response(event, msg): yield r
            return

        # --- 战斗类任务（全自动模拟） ---
        if bounty_type in ["捉妖", "暗杀"]:
            user_real_info = self.XiuXianService.get_user_real_info(user_id)
            monster_info = {
                "name": bounty.get('monster_name', '未知妖兽'),
                "hp": bounty.get('monster_hp'), # 现在可以正确获取
                "atk": bounty.get('monster_atk') # 现在可以正确获取
            }

            battle_result = PvPManager.simulate_full_bounty_fight(user_real_info, monster_info)

            if battle_result['success']:
                reward = self.XiuXianService.get_bounty_reward(work_info)
                self.XiuXianService.update_exp(user_id, reward['exp'])
                self.XiuXianService.update_ls(user_id, reward['stone'], 1)
                battle_result['log'].append(f"获得奖励：修为 +{reward['exp']}，灵石 +{reward['stone']}！")

            self.XiuXianService.abandon_bounty(user_id)
            msg = "\n".join(battle_result['log'])

        # --- 概率成功类任务 ---
        elif bounty_type == "采药":
            success_rate = work_info.get("rate", 100)
            if random.randint(0, 100) <= success_rate:
                reward = work_info.get("succeed_thank", 0)
                self.XiuXianService.update_ls(user_id, reward, 1)
                msg = f"{random.choice(work_info.get('succeed', ['任务成功！']))}\n你获得了 {reward} 灵石！"
            else:
                penalty = work_info.get("fail_thank", 0)
                self.XiuXianService.update_ls(user_id, penalty, 1)
                msg = f"{random.choice(work_info.get('fail', ['任务失败...']))}\n但你聊以慰藉地拿到了 {penalty} 灵石作为补偿。"

            self.XiuXianService.abandon_bounty(user_id)

        else:
            msg = "此类型的悬赏任务暂未支持完成方式，请联系管理员。"


        self.XiuXianService.refresh_user_base_attributes(user_id)

        async for r in self._send_response(event, msg):
            yield r

    # v-- 新增指令处理器 --v
    @filter.command("秘境帮助")
    async def rift_help_cmd(self, event: AstrMessageEvent):
        await self._update_active_groups(event)
        help_notes = """
秘境探险指令：
1、探索秘境：进入新的秘境或探索当前秘境
2、走出秘境：放弃当前进度，退出秘境
"""
        title = '秘境探险帮助'
        image_path = await get_msg_pic(await pic_msg_format(help_notes, event), title, 30)
        yield event.chain_result([Comp.Image.fromFileSystem(str(image_path))])

    @filter.command("探索秘境")
    @command_lock
    async def explore_rift_cmd(self, event: AstrMessageEvent):
        await self._update_active_groups(event)
        user_id = event.get_sender_id()
        is_user, user_info, msg = check_user(self.XiuXianService, user_id)
        if not is_user:
            async for r in self._send_response(event, msg): yield r
            return

        # --- 1. 检查是否已在秘境中 (理论上自动探索模式下不会发生) ---
        if self.XiuXianService.get_user_rift(user_id):
            msg = "道友似乎已在一个秘境中了，请先使用【走出秘境】或等待它自动结束。"
            async for r in self._send_response(event, msg): yield r
            return

        # --- 2. 检查CD和进入条件 ---
        remaining_cd = self.XiuXianService.check_user_rift_cd(user_id)
        if remaining_cd > 0:
            minutes = remaining_cd // 60
            seconds = remaining_cd % 60
            msg = f"道友刚从秘境中出来，气息未定，请等待 {minutes}分{seconds}秒 后再来探索吧。"
            async for r in self._send_response(event, msg): yield r
            return

        if user_info.hp <= 0:
            msg = "道友已身受重伤，无法进行探索，请先恢复状态！"
            async for r in self._send_response(event, msg): yield r
            return

        if user_info.stone < self.xiu_config.rift_cost:
            msg = f"进入秘境需要 {self.xiu_config.rift_cost} 灵石作为引路费，道友的灵石不足！"
            async for r in self._send_response(event, msg): yield r
            return

        # --- 3. 创建新秘境并设置CD ---
        new_rift_template = self.rift_manager.generate_rift(user_info.level)
        if not new_rift_template:
            msg = "系统错误，生成秘境失败！"
            async for r in self._send_response(event, msg): yield r
            return

        self.XiuXianService.update_ls(user_id, self.xiu_config.rift_cost, 2)
        # 注意：我们不再将秘境存入数据库，因为是即时探索
        self.XiuXianService.set_user_rift_cd(user_id)

        # --- 4. 开始自动探索循环 ---
        rift_map = new_rift_template['map']
        total_floors = new_rift_template['total_floors']
        current_floor_num = 1
        exploration_log = [f"=== 秘境【{new_rift_template['name']}】探索记录 ==="]

        while current_floor_num <= total_floors:
            # 获取当前玩家信息，因为HP可能会在战斗中变化
            current_user_info = self.XiuXianService.get_user_message(user_id)
            if not current_user_info or current_user_info.hp <= 0:
                exploration_log.append(f"\n在第 {current_floor_num-1} 层后，你因伤势过重，被迫退出了秘境。")
                break # 玩家死亡，结束探索

            event_data = rift_map[current_floor_num - 1]
            log_entry = [f"\n--- 第 {event_data['floor']} 层 ---", event_data['desc']]
            event_type = event_data['event_type']

            if event_type == 'reward':
                reward_info = event_data.get('reward', {'exp': 10, 'stone': 10})
                exp, stone = reward_info['exp'], reward_info['stone']
                self.XiuXianService.update_exp(user_id, exp)
                self.XiuXianService.update_ls(user_id, stone, 1)
                log_entry.append(f"获得奖励：修为+{exp}，灵石+{stone}！")

            elif event_type == 'punish':
                punish_info = self.rift_manager.rift_event_data[event_data['event_name']]['punish']
                hp_lost = random.randint(*punish_info['hp'])
                self.XiuXianService.update_hp(user_id, hp_lost, 2)
                user_info_after_punish = self.XiuXianService.get_user_message(user_id)
                log_entry.append(f"道友因此损失了 {hp_lost} 点生命！当前生命：{user_info_after_punish.hp}")
                if user_info_after_punish.hp <= 0:
                    log_entry.append("你身受重伤，探索被迫中止！")
                    exploration_log.extend(log_entry)
                    break

            elif event_type == 'combat':
                monster = event_data['monster']
                user_real_info = self.XiuXianService.get_user_real_info(user_id)
                battle_result = PvPManager.simulate_full_bounty_fight(user_real_info, monster)

                log_entry.extend(battle_result['log']) # 添加战斗日志

                player_hp_after_fight = battle_result.get("player_hp", 0)
                # 直接设置玩家战斗后的HP
                self.XiuXianService.conn.cursor().execute("UPDATE user_xiuxian SET hp = ? WHERE user_id = ?", (player_hp_after_fight, user_id))
                self.XiuXianService.conn.commit()

                if battle_result['success']:
                    reward_info = event_data.get('reward', {'exp': 10, 'stone': 10})
                    exp, stone = reward_info['exp'], reward_info['stone']
                    self.XiuXianService.update_exp(user_id, exp)
                    self.XiuXianService.update_ls(user_id, stone, 1)
                    log_entry.append(f"战斗胜利！获得奖励：修为+{exp}，灵石+{stone}！")
                else:
                    log_entry.append("你被击败了，探索被迫中止！")
                    exploration_log.extend(log_entry)
                    break

            exploration_log.extend(log_entry)
            current_floor_num += 1

        # --- 5. 探索结束，发送总结报告 ---
        if current_floor_num > total_floors:
            exploration_log.append(f"\n恭喜道友，成功探索完【{new_rift_template['name']}】的所有 {total_floors} 层！")

        # 刷新最终属性
        self.XiuXianService.refresh_user_base_attributes(user_id)
        self.XiuXianService.update_power2(user_id)


        msg = "\n".join(exploration_log)
        async for r in self._send_response(event, msg):
            yield r

    #@filter.command("探索秘境")
    #@command_lock
    #async def explore_rift_cmd(self, event: AstrMessageEvent):
    #    await self._update_active_groups(event)
    #    user_id = event.get_sender_id()
    #    is_user, user_info, msg = check_user(self.XiuXianService, user_id)
    #    if not is_user:
    #        async for r in self._send_response(event, msg): yield r
    #        return

    #    user_rift = self.XiuXianService.get_user_rift(user_id)

    #    # --- 核心逻辑重构 ---

    #    if not user_rift:
    #        # --- 情况A：玩家不在秘境中，准备开启新秘境 ---

    #        # 1. 在这里检查CD
    #        remaining_cd = self.XiuXianService.check_user_rift_cd(user_id)
    #        if remaining_cd > 0:
    #            minutes = remaining_cd // 60
    #            seconds = remaining_cd % 60
    #            msg = f"道友刚从秘境中出来，气息未定，请等待 {minutes}分{seconds}秒 后再来探索吧。"
    #            async for r in self._send_response(event, msg): yield r
    #            return

    #        # 2. 检查其他前置条件
    #        if user_info.hp <= 0:
    #            msg = "道友已身受重伤，无法进行探索，请先恢复状态！"
    #            async for r in self._send_response(event, msg): yield r
    #            return

    #        if user_info.stone < self.xiu_config.rift_cost:
    #            msg = f"进入秘境需要 {self.xiu_config.rift_cost} 灵石作为引路费，道友的灵石不足！"
    #            async for r in self._send_response(event, msg): yield r
    #            return

    #        # 3. 创建新秘境并设置CD
    #        new_rift = self.rift_manager.generate_rift(user_info.level)
    #        if not new_rift:
    #            msg = "系统错误，生成秘境失败！"
    #        else:
    #            self.XiuXianService.update_ls(user_id, self.xiu_config.rift_cost, 2)
    #            self.XiuXianService.create_user_rift(user_id, new_rift)
    #            self.XiuXianService.set_user_rift_cd(user_id) # 成功进入后，立刻设置CD
    #            msg = f"道友花费 {self.xiu_config.rift_cost} 灵石，成功进入了【{new_rift['name']}】！\n此秘境共 {new_rift['total_floors']} 层，充满了未知的机遇与危险。\n请再次使用【探索秘境】指令深入其中！"

    #        async for r in self._send_response(event, msg): yield r
    #        return

    #    else:
    #        # --- 情况B：玩家已在秘境中，继续探索 ---
    #        # 在这种情况下，我们不检查CD，直接处理楼层事件

    #        current_floor_index = user_rift['current_floor'] - 1
    #        rift_map = user_rift['rift_map']

    #        if current_floor_index >= len(rift_map):
    #             msg = f"恭喜道友，已经成功探索完【{user_rift['rift_name']}】的所有楼层！"
    #             self.XiuXianService.delete_user_rift(user_id)
    #             async for r in self._send_response(event, msg): yield r
    #             return

    #        event_data = rift_map[current_floor_index]
    #        msg_lines = [f"道友踏入了第 {event_data['floor']} 层，{event_data['desc']}"]

    #        event_type = event_data['event_type']

    #        # (这里的事件处理逻辑保持不变，为了完整性，我全部复制过来)
    #        if event_type == 'reward' and not event_data['is_finished']:
    #            reward_info = event_data.get('reward', {'exp': 10, 'stone': 10}) # 从事件数据中直接获取奖励
    #            exp, stone = reward_info['exp'], reward_info['stone']
    #            self.XiuXianService.update_exp(user_id, exp)
    #            self.XiuXianService.update_ls(user_id, stone, 1)
    #            msg_lines.append(f"获得奖励：修为+{exp}，灵石+{stone}！")
    #            rift_map[current_floor_index]['is_finished'] = True
    #            user_rift['current_floor'] += 1
    #        elif event_type == 'punish' and not event_data['is_finished']:
    #            punish_info = self.rift_manager.rift_event_data[event_data['event_name']]['punish']
    #            hp_lost = random.randint(*punish_info['hp'])
    #            self.XiuXianService.update_hp(user_id, hp_lost, 2)
    #            user_info_after_punish = self.XiuXianService.get_user_message(user_id)
    #            msg_lines.append(f"道友因此损失了 {hp_lost} 点生命！当前生命：{user_info_after_punish.hp}")
    #            if user_info_after_punish.hp <= 0:
    #                msg_lines.append("你身受重伤，被传送回了秘境之外！")
    #                self.XiuXianService.delete_user_rift(user_id)
    #            else:
    #                rift_map[current_floor_index]['is_finished'] = True
    #                user_rift['current_floor'] += 1
    #        elif event_type == 'combat':
    #            monster = event_data['monster']
    #            user_real_info = self.XiuXianService.get_user_real_info(user_id)
    #            from .pvp_manager import PvPManager
    #            battle_result = PvPManager.simulate_full_bounty_fight(user_real_info, monster)
    #            msg_lines.extend(battle_result['log'])
    #            if battle_result['success']:
    #                reward_info = event_data.get('reward', {'exp': 10, 'stone': 10}) # 从事件数据中直接获取奖励
    #                exp, stone = reward_info['exp'], reward_info['stone']
    #                self.XiuXianService.update_exp(user_id, exp)
    #                self.XiuXianService.update_ls(user_id, stone, 1)
    #                msg_lines.append(f"获得奖励：修为+{exp}，灵石+{stone}！")
    #                rift_map[current_floor_index]['is_finished'] = True
    #                user_rift['current_floor'] += 1
    #            else:
    #                player_hp_after_fight = battle_result.get("player_hp", 0)
    #                self.XiuXianService.update_hp(user_id, user_info.hp - player_hp_after_fight, 2)
    #                self.XiuXianService.delete_user_rift(user_id)

    #        if self.XiuXianService.get_user_rift(user_id):
    #            new_map_str = json.dumps(rift_map)
    #            self.XiuXianService.update_user_rift(user_id, user_rift['current_floor'], new_map_str)

    #        msg = "\n".join(msg_lines)
    #        async for r in self._send_response(event, msg):
    #            yield r

    @filter.command("走出秘境")
    @command_lock
    async def leave_rift_cmd(self, event: AstrMessageEvent):
        await self._update_active_groups(event)
        user_id = event.get_sender_id()
        is_user, _, msg = check_user(self.XiuXianService, user_id)
        if not is_user:
            yield event.chain_result([Comp.Image.fromFileSystem(str(await get_msg_pic(await pic_msg_format(msg, event))))])
            return

        if not self.XiuXianService.get_user_rift(user_id):
            msg = "道友尚未进入任何秘境。"
        else:
            self.XiuXianService.delete_user_rift(user_id)
            msg = "道友已从秘境中走出，虽未得机缘，但保全自身以图后事，亦是明智之举。"

        yield event.chain_result([Comp.Image.fromFileSystem(str(await get_msg_pic(await pic_msg_format(msg, event))))])

    @filter.command("炼丹帮助")
    @command_lock
    async def alchemy_help_cmd(self, event: AstrMessageEvent):
        await self._update_active_groups(event)
        help_notes = """
炼丹帮助信息:
指令：
1、炼丹 [丹药名称]：根据丹方尝试炼制指定丹药。
2、查看丹方：查看所有已知的丹药配方。
3、可炼丹药：检测背包药材，列出当前可炼制的丹药。
4、灵田收取、灵田结算：收取你洞天福地中的药材。
5、我的炼丹信息：查询自己的炼丹等级、经验和记录。
6、升级收取等级：提升灵田收取的药材数量。
7、升级丹药控火：提升炼丹的产出数量。
8、炼丹配方帮助：查看炼丹的基本规则。
"""
        title = '炼丹帮助'
        async for r in self._send_response(event, help_notes, title, font_size=30):
            yield r

    @filter.command("炼丹配方帮助")
    @command_lock
    async def alchemy_recipe_help_cmd(self, event: AstrMessageEvent):
        await self._update_active_groups(event)
        help_notes = """
炼丹配方基本规则：
1、炼丹需要 炼丹炉、主药、药引、辅药 和 修为。
2、主药和药引的冷热属性需要调和，否则会失败。
3、主药和辅药的药性共同决定产出丹药的种类。
4、更高等级的丹药控火可以增加丹药产出数量。
"""
        title = '炼丹配方帮助'
        async for r in self._send_response(event, help_notes, title, font_size=30):
            yield r

    @filter.command("查看丹方")
    async def view_recipes_cmd(self, event: AstrMessageEvent):
        await self._update_active_groups(event)

        recipes = self.alchemy_manager.get_all_recipes()
        if not recipes:
            msg = "仙界似乎还没有可供炼制的丹方。"
        else:
            msg_lines = ["\n目前已知的丹方如下："]
            
            # 定义药力类型到名称的映射，以便显示
            YAOCAI_TYPE_MAP = {
                "2": "生息", "3": "养气", "4": "炼气",
                "5": "聚元", "6": "凝神"
            }

            for recipe in recipes:
                materials_config = recipe.get("elixir_config", {})
                materials_list = []
                for material_type_id, required_power in materials_config.items():
                    # 将药力类型ID转换为可读的名称
                    type_name = YAOCAI_TYPE_MAP.get(str(material_type_id), f"未知类型({material_type_id})")
                    materials_list.append(f"{type_name}药力x{required_power}")

                materials_str = "、".join(materials_list) if materials_list else "无需材料"
                desc = recipe.get('desc', '效果未知')

                msg_lines.append(
                    f"【{recipe['name']}】\n"
                    f"  效果：{desc}\n"
                    f"  所需药力：{materials_str}\n"
                    f"  消耗修为：{recipe.get('mix_exp', 0)}"
                )
            msg = "\n\n".join(msg_lines)
        

        yield event.plain_result(msg)
        #async for r in self._send_response(event, msg, "丹方列表", font_size=24):
        #    yield r


    @filter.command("可炼丹药")
    @command_lock
    async def view_craftable_pills_cmd(self, event: AstrMessageEvent):
        await self._update_active_groups(event)
        user_id = event.get_sender_id()
        is_user, _, msg = check_user(self.XiuXianService, user_id)
        if not is_user:
            async for r in self._send_response(event, msg): yield r
            return

        user_backpack_items_list = self.XiuXianService.get_user_back_msg(user_id) # 获取原始背包列表

        if not any(item.goods_type == "药材" for item in user_backpack_items_list): # 检查是否有药材
            msg = "道友背包里没有药材，无法推演丹方！"
            async for r in self._send_response(event, msg): yield r
            return

        possible_recipes = self.alchemy_manager.find_possible_recipes(user_backpack_items_list)

        if not possible_recipes:
            msg = "根据道友背包中的药材，似乎无法炼制任何已知的丹药。"
        else:
            msg_lines = ["根据道友的药材，可尝试炼制以下丹药："]
            for pill_id, info in possible_recipes.items():
                msg_lines.append(f"【{info['name']}】\n  效果: {info.get('effect_desc', '未知')}\n  所需材料: {info['materials_str']}")
            msg_lines.append("\n请使用【炼丹 丹药名称】进行炼制。")
            msg = "\n\n".join(msg_lines)

        async for r in self._send_response(event, msg, "可炼丹药列表", font_size=24):
            yield r

    @filter.command("炼丹")
    async def craft_pill_cmd(self, event: AstrMessageEvent):
        await self._update_active_groups(event)
        user_id = event.get_sender_id()
        is_user, user_info, msg = check_user(self.XiuXianService, user_id)
        if not is_user:
            async for r in self._send_response(event, msg): yield r
            return

        args = event.message_str.split()
        recipe_name = args[1] if len(args) >= 2 else ""
        if not recipe_name:
            msg = "请输入要炼制的丹药名称，如：炼丹 筑基丹"
            async for r in self._send_response(event, msg): yield r
            return

        user_backpack = self.XiuXianService.get_user_back_msg(user_id)
        user_alchemy_info = self.XiuXianService.get_user_alchemy_info(user_id)
        
        # 将 service 实例传递给 manager
        self.alchemy_manager.service = self.XiuXianService
        result = self.alchemy_manager.craft_pill(user_info, user_backpack, user_alchemy_info, recipe_name)
        
        # 处理消耗
        if result.get("consume"):
            self.XiuXianService.update_j_exp(user_id, result['consume']['exp'])
            for mat_id, num in result['consume']['materials'].items():
                mat_info = self.XiuXianService.items.get_data_by_item_id(int(mat_id))
                self.XiuXianService.remove_item(user_id, mat_info['name'], num)
        
        # 处理产出和经验
        if result['success'] and result.get('produce'):
            produce_info = result['produce']
            item_full_info = self.XiuXianService.items.get_data_by_item_id(produce_info['item_id'])
            self.XiuXianService.add_item(user_id, produce_info['item_id'], item_full_info.get('item_type', '丹药'), produce_info['num'])

            if result.get('exp_gain', 0) > 0:
                current_alchemy_info = self.XiuXianService.get_user_alchemy_info(user_id)
                new_exp = current_alchemy_info.alchemy_exp + result['exp_gain']
                
                alchemy_record = json.loads(current_alchemy_info.alchemy_record)
                pill_id_str = str(produce_info['item_id'])
                if pill_id_str not in alchemy_record:
                    alchemy_record[pill_id_str] = {'num': 0, 'name': recipe_name}
                alchemy_record[pill_id_str]['num'] += produce_info['num']

                updated_info = current_alchemy_info._replace(
                    alchemy_exp=new_exp,
                    alchemy_record=json.dumps(alchemy_record, ensure_ascii=False)
                )
                self.XiuXianService.update_user_alchemy_info(user_id, updated_info)
        
        async for r in self._send_response(event, result['message']):
            yield r


    @filter.command("灵田收取", alias={"灵田结算"})
    @command_lock
    async def gather_herbs_cmd(self, event: AstrMessageEvent):
        await self._update_active_groups(event)
        is_user, user_info, msg = check_user(self.XiuXianService, event.get_sender_id())
        if not is_user:
            async for r in self._send_response(event, msg): yield r
            return

        user_id = user_info.user_id
        if not user_info.blessed_spot_flag:
            msg = "道友还没有洞天福地，无法开垦灵田。请使用【洞天福地购买】开启！"
            async for r in self._send_response(event, msg): yield r
            return

        # 获取炼丹和聚灵旗信息
        alchemy_info = self.XiuXianService.get_user_alchemy_info(user_id)
        buff_info = self.XiuXianService.get_user_buff_info(user_id)
        jlq_level = buff_info.blessed_spot if buff_info else 0 # 聚灵旗等级

        last_time_str = alchemy_info.last_collection_time
        # 如果 last_collection_time 为空或格式不正确，则给予一个默认的过去时间
        try:
            last_time = datetime.fromisoformat(last_time_str)
        except (TypeError, ValueError):
            last_time = datetime.now() - timedelta(days=2)

        now_time = datetime.now()

        gather_config = self.xiu_config.herb_gathering_config
        # 计算加速后的收取周期
        speed_up_bonus = gather_config['speed_up_rate'] * jlq_level
        required_hours = gather_config['time_cost'] * (1 - speed_up_bonus)

        # 计算从上次收取到现在过去了多少个周期
        time_diff_hours = (now_time - last_time).total_seconds() / 3600
        logger.info(time_diff_hours)
        if time_diff_hours < required_hours:
            remaining_time = required_hours - time_diff_hours
            msg = f"灵田中的药材尚未成熟，还需等待 {remaining_time:.2f} 小时。"
        else:
            # 计算可收取的批次数
            batches = int(time_diff_hours // required_hours)
            # 计算本次收取的药材数量
            num_to_get = (1 + alchemy_info.collection_level) * batches

            # 随机获取药材
            herb_id_list = list(self.XiuXianService.items.get_data_by_item_type(['药材']).keys())
            if not herb_id_list:
                msg = "错误：药材库为空，无法收取！"
                async for r in self._send_response(event, msg): yield r
                return

            herbs_got = {}
            for _ in range(num_to_get):
                herb_id = random.choice(herb_id_list)
                herbs_got[herb_id] = herbs_got.get(herb_id, 0) + 1

            msg_lines = ["灵田大丰收！"]
            for herb_id, num in herbs_got.items():
                herb_info = self.XiuXianService.items.get_data_by_item_id(herb_id)
                self.XiuXianService.add_item(user_id, int(herb_id), "药材", num)
                msg_lines.append(f"你收获了【{herb_info['name']}】x{num}！")
            msg = "\n".join(msg_lines)

            # 更新下一次可以收取的时间点（不是现在，而是用掉的周期之后的时间点）
            new_last_collection_time = last_time + timedelta(hours=required_hours * batches)
            updated_info = alchemy_info._replace(
                last_collection_time=str(new_last_collection_time)
            )
            self.XiuXianService.update_user_alchemy_info(user_id, updated_info)

        async for r in self._send_response(event, msg):
            yield r

    @filter.command("我的炼丹信息")
    @command_lock
    async def my_alchemy_info_cmd(self, event: AstrMessageEvent):
        await self._update_active_groups(event)
        is_user, _, msg = check_user(self.XiuXianService, event.get_sender_id())
        if not is_user:
            async for r in self._send_response(event, msg): yield r
            return

        alchemy_info = self.XiuXianService.get_user_alchemy_info(event.get_sender_id())
        msg_lines = [
            "道友的炼丹信息如下：",
            f"炼丹经验：{alchemy_info.alchemy_exp}",
            f"收取等级：{alchemy_info.collection_level}级",
            f"丹药控火：{alchemy_info.fire_level}级",
        ]
        alchemy_record = json.loads(alchemy_info.alchemy_record)
        if alchemy_record:
            msg_lines.append("\n已掌握的丹方：")
            for pill_id, record in alchemy_record.items():
                pill_info = self.XiuXianService.items.get_data_by_item_id(int(pill_id))
                msg_lines.append(f" - {pill_info['name']}: 已炼制 {record.get('num', 0)} 次")

        async for r in self._send_response(event, "\n".join(msg_lines), "炼丹信息"):
            yield r

    @filter.command("升级收取等级")
    @command_lock
    async def upgrade_collection_level_cmd(self, event: AstrMessageEvent):
        await self._update_active_groups(event)
        user_id = event.get_sender_id()
        is_user, _, msg = check_user(self.XiuXianService, user_id)
        if not is_user:
            async for r in self._send_response(event, msg): yield r
            return

        alchemy_info = self.XiuXianService.get_user_alchemy_info(user_id)
        level_config = self.xiu_config.alchemy_level_up_config["收取等级"]
        current_level = alchemy_info.collection_level

        if str(current_level + 1) not in level_config:
            msg = "收取等级已达满级，无法再提升！"
        else:
            cost = level_config[str(current_level + 1)]['level_up_cost']
            if alchemy_info.alchemy_exp < cost:
                msg = f"炼丹经验不足！提升至下一级需要 {cost} 点经验，道友目前只有 {alchemy_info.alchemy_exp} 点。"
            else:
                updated_info = alchemy_info._replace(
                    collection_level=current_level + 1,
                    alchemy_exp=alchemy_info.alchemy_exp - cost
                )
                self.XiuXianService.update_user_alchemy_info(user_id, updated_info)
                msg = f"恭喜道友！收取等级提升至 {current_level + 1} 级，灵田产出增加了！"

        async for r in self._send_response(event, msg):
            yield r

    @filter.command("升级丹药控火")
    @command_lock
    async def upgrade_fire_level_cmd(self, event: AstrMessageEvent):
        await self._update_active_groups(event)
        user_id = event.get_sender_id()
        is_user, _, msg = check_user(self.XiuXianService, user_id)
        if not is_user:
            async for r in self._send_response(event, msg): yield r
            return

        alchemy_info = self.XiuXianService.get_user_alchemy_info(user_id)
        level_config = self.xiu_config.alchemy_level_up_config["丹药控火"]
        current_level = alchemy_info.fire_level

        if str(current_level + 1) not in level_config:
            msg = "丹药控火已达满级，无法再提升！"
        else:
            cost = level_config[str(current_level + 1)]['level_up_cost']
            if alchemy_info.alchemy_exp < cost:
                msg = f"炼丹经验不足！提升至下一级需要 {cost} 点经验，道友目前只有 {alchemy_info.alchemy_exp} 点。"
            else:
                updated_info = alchemy_info._replace(
                    fire_level=current_level + 1,
                    alchemy_exp=alchemy_info.alchemy_exp - cost
                )
                self.XiuXianService.update_user_alchemy_info(user_id, updated_info)
                msg = f"恭喜道友！丹药控火提升至 {current_level + 1} 级，炼丹时产出更多丹药的几率提高了！"

        async for r in self._send_response(event, msg):
            yield r

    # 洞天福地相关指令
    @filter.command("洞天福地购买")
    @command_lock
    async def purchase_blessed_spot_cmd(self, event: AstrMessageEvent):
        await self._update_active_groups(event)
        is_user, user_info, msg = check_user(self.XiuXianService, event.get_sender_id())
        if not is_user:
            async for r in self._send_response(event, msg): yield r
            return

        if user_info.blessed_spot_flag:
            msg = "道友已拥有洞天福地，无需重复购买！"
        elif user_info.stone < self.xiu_config.blessed_spot_cost:
            msg = f"购买洞天福地需要 {self.xiu_config.blessed_spot_cost} 灵石，道友的灵石不足！"
        else:
            self.XiuXianService.update_ls(user_info.user_id, self.xiu_config.blessed_spot_cost, 2)
            self.XiuXianService.purchase_blessed_spot(user_info.user_id)
            msg = "恭喜道友！你已成功开辟属于自己的洞天福地，现在可以开垦灵田了！"

        async for r in self._send_response(event, msg): yield r

    # ^-- 追加结束 --^


    @filter.command("功法帮助")
    @command_lock
    async def exercises_help_cmd(self, event: AstrMessageEvent):
        await self._update_active_groups(event)
        help_notes = """
功法/神通指令：
1、我的功法：查看当前已装备的功法
2、装备功法 [功法名]：装备背包中的功法
3、卸下功法 [主修/辅修]：卸下已装备的功法
(功法和神通秘籍可在坊市购买或通过奇遇获得)
"""
        title = '功法神通帮助'
        image_path = await get_msg_pic(await pic_msg_format(help_notes, event), title, 30)
        yield event.chain_result([Comp.Image.fromFileSystem(str(image_path))])

    @filter.command("我的功法")
    @command_lock
    async def my_exercises_cmd(self, event: AstrMessageEvent):
        await self._update_active_groups(event)
        user_id = event.get_sender_id()
        is_user, _, msg = check_user(self.XiuXianService, user_id)
        if not is_user:
            yield event.chain_result([Comp.Image.fromFileSystem(str(await get_msg_pic(await pic_msg_format(msg, event))))])
            return

        buff_info = self.XiuXianService.get_user_buff_info(user_id)
        if not buff_info:
            yield event.plain_result("错误：无法获取道友的功法信息！")
            return

        items_manager = self.XiuXianService.items
        main_ex = items_manager.get_data_by_item_id(buff_info.main_buff)
        sec_ex = items_manager.get_data_by_item_id(buff_info.sec_buff)

        msg = f"""
道友当前装备的功法：
主修功法：{main_ex['name'] if main_ex else '无'}
辅修功法：{sec_ex['name'] if sec_ex else '无'}
"""
        yield event.chain_result([Comp.Image.fromFileSystem(str(await get_msg_pic(await pic_msg_format(msg.strip(), event))))])

    @filter.command("装备功法")
    @command_lock
    async def equip_exercise_cmd(self, event: AstrMessageEvent):
        await self._update_active_groups(event)
        user_id = event.get_sender_id()
        is_user, _, msg = check_user(self.XiuXianService, user_id)
        if not is_user:
            yield event.chain_result([Comp.Image.fromFileSystem(str(await get_msg_pic(await pic_msg_format(msg, event))))])
            return

        args = event.message_str.split()
        exercise_name = args[1] if len(args) >= 2 else ""
        if not exercise_name:
            msg = "请输入要装备的功法名称！"
            yield event.chain_result([Comp.Image.fromFileSystem(str(await get_msg_pic(await pic_msg_format(msg, event))))])
            return

        item_in_backpack = self.XiuXianService.get_item_by_name(user_id, exercise_name)
        if not item_in_backpack:
            msg = f"道友的背包里没有【{exercise_name}】这本秘籍。"
            yield event.chain_result([Comp.Image.fromFileSystem(str(await get_msg_pic(await pic_msg_format(msg, event))))])
            return

        item_info = self.XiuXianService.items.get_data_by_item_id(item_in_backpack.goods_id)
        item_type = item_info.get("item_type")

        # buff_info = self.XiuXianService.get_user_buff_info(user_id)
        # buff_type_to_set = None
        #
        # if item_type == "功法":
        #     if buff_info.main_buff != 0:
        #         msg = "道友已装备了主修功法，请先卸下！"
        #         yield event.chain_result([Comp.Image.fromFileSystem(str(await get_msg_pic(await pic_msg_format(msg, event))))])
        #         return
        #     buff_type_to_set = 'main_buff'
        # elif item_type == "辅修功法":
        #     if buff_info.sub_buff != 0:
        #         msg = "道友已装备了辅修功法，请先卸下！"
        #         yield event.chain_result([Comp.Image.fromFileSystem(str(await get_msg_pic(await pic_msg_format(msg, event))))])
        #         return
        #     buff_type_to_set = 'sub_buff'
        # elif item_type == "神通": # <<< 新增对神通的处理
        #     if buff_info.sec_buff != 0: # 检查神通槽位 (sec_buff)
        #         msg = "道友已装备了神通，请先卸下！"
        #         yield event.chain_result([Comp.Image.fromFileSystem(str(await get_msg_pic(await pic_msg_format(msg, event))))])
        #         return
        #     buff_type_to_set = 'sec_buff' # 告诉 service 更新 sec_buff 字段
        # else:
        #     msg = f"【{exercise_name}】似乎不是可以装备的功法秘籍。"
        #     yield event.chain_result([Comp.Image.fromFileSystem(str(await get_msg_pic(await pic_msg_format(msg, event))))])
        #     return
        allowed_skill_types = ["功法", "辅修功法", "神通"]
        if item_type not in allowed_skill_types:
            msg = f"【{exercise_name}】似乎不是可以装备的功法秘籍或神通。"
            async for r in self._send_response(event, msg): yield r
            return

        # self.XiuXianService.remove_item(user_id, item_info["name"])
        # 执行装备
        # self.XiuXianService.set_user_buff(user_id, buff_type_to_set, item_in_backpack.goods_id, 1)
        if not self.XiuXianService.remove_item(user_id, item_info["name"], 1):
            msg = f"错误：从背包移除【{exercise_name}】失败！"
            async for r in self._send_response(event, msg): yield r
            return
        success, message = self.XiuXianService.smart_equip_gongfa_or_skill(user_id, item_in_backpack.goods_id,
                                                                           item_type)
        if success:
            self.XiuXianService.update_power2(user_id)  # 更新战力等

        async for r in self._send_response(event, message): yield r
        # msg = f"道友已成功装备功法【{exercise_name}】！"
        # yield event.chain_result([Comp.Image.fromFileSystem(str(await get_msg_pic(await pic_msg_format(msg, event))))])

    @filter.command("卸下功法", alias={"卸载功法"})
    @command_lock
    async def unequip_exercise_cmd(self, event: AstrMessageEvent):
        await self._update_active_groups(event)
        user_id = event.get_sender_id()
        is_user, _, msg = check_user(self.XiuXianService, user_id)
        if not is_user:
            yield event.chain_result([Comp.Image.fromFileSystem(str(await get_msg_pic(await pic_msg_format(msg, event))))])
            return

        args = event.message_str.split()
        unequip_type = args[1] if len(args) >= 2 else ""

        buff_type_to_clear = None
        if unequip_type == "主修":
            buff_type_to_clear = "main_buff"
            msg = "已卸下主修功法。"
        elif unequip_type == "辅修":
            buff_type_to_clear = "sub_buff"
            msg = "已卸下辅修功法。"
        elif unequip_type == "神通": # <<< 新增对神通的卸下
            buff_type_to_clear = "sec_buff"
            msg = "已遗忘当前神通。"
        else:
            msg = "指令错误，请输入“卸下功法 主修”或“卸下功法 辅修”。"
            yield event.chain_result([Comp.Image.fromFileSystem(str(await get_msg_pic(await pic_msg_format(msg, event))))])
            return

        self.XiuXianService.unequip_item(user_id, unequip_type)
        self.XiuXianService.set_user_buff(user_id, buff_type_to_clear, 0)
        yield event.chain_result([Comp.Image.fromFileSystem(str(await get_msg_pic(await pic_msg_format(msg, event))))])

    @filter.command("重入仙途")
    @command_lock
    async def remake_cmd(self, event: AstrMessageEvent):
        await self._update_active_groups(event)
        user_id = event.get_sender_id()
        is_user, _, msg = check_user(self.XiuXianService, user_id)
        if not is_user:
            async for r in self._send_response(event, msg): yield r
            return

        #remaining_time = self.XiuXianService.check_remake_cd(user_id)
        #if remaining_time > 0:
        #    minutes = remaining_time // 60
        #    seconds = remaining_time % 60
        #    msg = f"重入仙途机缘未到，还需等待 {minutes}分{seconds}秒。"
        #    async for r in self._send_response(event, msg): yield r
        #    return
        
        # v-- 这是本次修正的核心：使用正确的方法名 remake_user_root --v
        result = self.XiuXianService.remake_user_root(user_id)
        # ^-- 这是本次修正的核心 --^
        msg = result["message"] + "限时1元喽！！傻逼浅月"
        
        if result["success"]:
            # 成功后才设置CD
            self.XiuXianService.set_remake_cd(user_id)

        async for r in self._send_response(event, msg):
            yield r

    @filter.command("改名")
    @command_lock
    async def change_name_cmd(self, event: AstrMessageEvent):
        """处理改名指令"""
        await self._update_active_groups(event)
        user_id = event.get_sender_id()
        is_user, _, msg = check_user(self.XiuXianService, user_id)
        if not is_user:
            yield event.chain_result([Comp.Image.fromFileSystem(str(await get_msg_pic(await pic_msg_format(msg, event))))])
            return
        # v-- 采用您提供的 split 方案 --v
        args = event.message_str.split()
        if len(args) < 2:
            new_name = ""
        else:
            new_name = args[1]
        # ^-- 修正参数解析 --^
        if not new_name:
            msg = "请输入你的新道号，例如：改名 叶凡"
        elif len(new_name) > 8:
            msg = "道号过长，不利于扬名立万！请换个短一些的吧。"
        else:
            self.XiuXianService.update_user_name(user_id, new_name)
            msg = f"道友已成功改名为【{new_name}】！"

        yield event.chain_result([Comp.Image.fromFileSystem(str(await get_msg_pic(await pic_msg_format(msg, event))))])

    @filter.command("切磋")
    @command_lock
    async def pvp_spar_cmd(self, event: AstrMessageEvent):
        await self._update_active_groups(event)
        user_id = event.get_sender_id()
        is_user, user_info_p1, msg = check_user(self.XiuXianService, user_id)
        if not is_user:
            async for r in self._send_response(event, msg): yield r
            return

        target_user_id = await self._get_at_user_id(event)
        if not target_user_id:
            msg = "道友想与谁切磋呢？请@一位仙友吧！"
            async for r in self._send_response(event, msg): yield r
            return

        is_target_user, user_info_p2, msg_target = check_user(self.XiuXianService, target_user_id)
        if not is_target_user:
            async for r in self._send_response(event, msg_target): yield r
            return

        if user_id == target_user_id:
            msg = "道友无法与自己切磋！"
            async for r in self._send_response(event, msg): yield r
            return

        # 检查切磋CD (type=6 代表切磋CD，假设5分钟)
        spar_cd_type = 6
        spar_cd_duration = 5 # 分钟
        remaining_cd = self.XiuXianService.check_user_cd_specific_type(user_id, spar_cd_type) # 需要在Service中实现
        if remaining_cd > 0:
            minutes = remaining_cd // 60
            seconds = remaining_cd % 60
            msg = f"道友切磋过于频繁，请等待 {minutes}分{seconds}秒 后再试！"
            async for r in self._send_response(event, msg): yield r
            return

        # 获取双方真实数据
        user_real_info_p1 = self.XiuXianService.get_user_real_info(user_id)
        user_real_info_p2 = self.XiuXianService.get_user_real_info(target_user_id)

        if not user_real_info_p1 or not user_real_info_p2:
            msg = "获取切磋双方信息失败，请稍后再试。"
            async for r in self._send_response(event, msg): yield r
            return

        # 执行战斗模拟
        battle_result = PvPManager.simulate_player_vs_player_fight(user_real_info_p1, user_real_info_p2)

        # --- 存储详细战斗日志 ---
        if battle_result.get("battle_round_details_log"):
            # 为双方都存储同一份详细日志
            await self._store_last_battle_details(user_id, battle_result["battle_round_details_log"])
        # --- 结束存储 ---

        # 设置切磋CD
        #self.XiuXianService.set_user_cd(user_id, spar_cd_duration, spar_cd_type)


        # 切磋不改变实际HP/MP，只显示战斗日志
        # 但为了演示，我们可以将模拟后的HP显示在日志末尾（如果需要）
        # final_log_message = "\n".join(battle_result['log'])
        # final_log_message += f"\n--- 模拟战后状态 ---"
        # final_log_message += f"\n【{user_real_info_p1['user_name']}】剩余HP: {battle_result['p1_hp_final']}"
        # final_log_message += f"\n【{user_real_info_p2['user_name']}】剩余HP: {battle_result['p2_hp_final']}"

        # astrbot平台好像没有直接的转发消息组件，如果日志太长，可能需要分段发送或优化显示
        # 暂时先合并发送
        full_battle_log = "\n".join(battle_result['log'])
        #async for r in self._send_response(event, full_battle_log, "切磋战报"): # 使用_send_response
        #    yield r

        yield event.chain_result([Comp.Image.fromFileSystem(str(await get_msg_pic(await pic_msg_format(full_battle_log, event))))])

    @filter.command("灵庄帮助")
    @command_lock
    async def bank_help_cmd(self, event: AstrMessageEvent):
        await self._update_active_groups(event)
        help_notes = """
灵庄指令：
1、我的灵石：查看自己和他人的灵石及存款
2、存款 [数量]：将灵石存入灵庄
3、取款 [数量]：从灵庄取出灵石
(灵庄收取的利息为0)
"""
        title = '灵庄帮助'
        image_path = await get_msg_pic(await pic_msg_format(help_notes, event), title, 30)
        yield event.chain_result([Comp.Image.fromFileSystem(str(image_path))])

    @filter.command("我的灵石")
    @command_lock
    async def my_stone_cmd(self, event: AstrMessageEvent):
        await self._update_active_groups(event)
        user_id = event.get_sender_id()
        is_user, user_info, msg = check_user(self.XiuXianService, user_id)
        if not is_user:
            yield event.chain_result([Comp.Image.fromFileSystem(str(await get_msg_pic(await pic_msg_format(msg, event))))])
            return

        bank_info = self.XiuXianService.get_bank_info(user_id)
        msg = f"道友目前身怀 {user_info.stone} 灵石，灵庄存款 {bank_info['savings']} 灵石。"
        yield event.chain_result([Comp.Image.fromFileSystem(str(await get_msg_pic(await pic_msg_format(msg, event))))])

    @filter.command("存款")
    @command_lock
    async def save_stone_cmd(self, event: AstrMessageEvent):
        await self._update_active_groups(event)
        user_id = event.get_sender_id()
        is_user, user_info, msg = check_user(self.XiuXianService, user_id)
        if not is_user:
            yield event.chain_result([Comp.Image.fromFileSystem(str(await get_msg_pic(await pic_msg_format(msg, event))))])
            return

        try:
             # 从消息中移除指令部分，只保留参数
            arg_str = re.sub(r'存款', '', event.message_str, 1).strip()
            if not arg_str:
                raise ValueError("未提供金额")
            amount_to_save = int(arg_str)

            if amount_to_save <= 0: raise ValueError
        except ValueError:
            msg = "请输入一个正确的存款金额！"
            yield event.chain_result([Comp.Image.fromFileSystem(str(await get_msg_pic(await pic_msg_format(msg, event))))])
            return

        if user_info.stone < amount_to_save:
            msg = "道友身上的灵石不够哦！"
        else:
            self.XiuXianService.update_ls(user_id, amount_to_save, 2) # 2-减少
            bank_info = self.XiuXianService.get_bank_info(user_id)
            new_savings = bank_info['savings'] + amount_to_save
            self.XiuXianService.update_bank_savings(user_id, new_savings)
            msg = f"成功向灵庄存入 {amount_to_save} 灵石！"

        yield event.chain_result([Comp.Image.fromFileSystem(str(await get_msg_pic(await pic_msg_format(msg, event))))])

    @filter.command("取款")
    @command_lock
    async def get_stone_cmd(self, event: AstrMessageEvent):
        await self._update_active_groups(event)
        user_id = event.get_sender_id()
        is_user, _, msg = check_user(self.XiuXianService, user_id)
        if not is_user:
            yield event.chain_result([Comp.Image.fromFileSystem(str(await get_msg_pic(await pic_msg_format(msg, event))))])
            return

        try:
             # 从消息中移除指令部分，只保留参数
            arg_str = re.sub(r'取款', '', event.message_str, 1).strip()
            if not arg_str:
                raise ValueError("未提供金额")
            amount_to_get = int(arg_str)

            if amount_to_get <= 0: raise ValueError
        except ValueError:
            msg = "请输入一个正确的取款金额！"
            yield event.chain_result([Comp.Image.fromFileSystem(str(await get_msg_pic(await pic_msg_format(msg, event))))])
            return

        bank_info = self.XiuXianService.get_bank_info(user_id)
        if bank_info['savings'] < amount_to_get:
            msg = "道友在灵庄的存款不够哦！"
        else:
            self.XiuXianService.update_ls(user_id, amount_to_get, 1) # 1-增加
            new_savings = bank_info['savings'] - amount_to_get
            self.XiuXianService.update_bank_savings(user_id, new_savings)
            msg = f"成功从灵庄取出 {amount_to_get} 灵石！"

        yield event.chain_result([Comp.Image.fromFileSystem(str(await get_msg_pic(await pic_msg_format(msg, event))))])


    @filter.command("排行榜")
    @command_lock
    async def ranking_cmd(self, event: AstrMessageEvent):
        """处理排行榜指令"""
        await self._update_active_groups(event)

         # v-- 采用您提供的 split 方案 --v
        args = event.message_str.split()
        if len(args) < 2:
            rank_type = ""
        else:
            rank_type = args[1]
        # ^-- 修正参数解析 --^

        title = ""
        data = []

        if rank_type == "修为":
            title = "修仙界修为排行榜"
            data = self.XiuXianService.get_exp_ranking()

        elif rank_type == "灵石":
            title = "修仙界财富排行榜"
            data = self.XiuXianService.get_stone_ranking()

        elif rank_type == "战力":
            title = "修仙界战力排行榜"
            data = self.XiuXianService.get_power_ranking()

        else:
            msg = "请输入想查看的排行榜类型，例如：排行榜 修为 | 灵石 | 战力"
            yield event.chain_result([Comp.Image.fromFileSystem(str(await get_msg_pic(await pic_msg_format(msg, event))))])
            return

        if not data:
            msg = "排行榜上 अभी空空如也，等待道友们一展身手！"
        else:
            msg_lines = [f"🏆 {title} 🏆"]
            for i, item in enumerate(data):
                user_name, level, value = item
                msg_lines.append(f"No.{i+1} {user_name} ({level}) - {value}")
            msg = "\n".join(msg_lines)

        yield event.chain_result([Comp.Image.fromFileSystem(str(await get_msg_pic(await pic_msg_format(msg, event), title, 30)))])

    @filter.command("抢劫")
    @command_lock
    async def pvp_rob_cmd(self, event: AstrMessageEvent):
        await self._update_active_groups(event)
        user_id = event.get_sender_id()
        is_user, user_info_attacker, msg = check_user(self.XiuXianService, user_id)
        if not is_user:
            async for r in self._send_response(event, msg): yield r
            return

        # 抢劫CD (type=2 代表抢劫/BOSS战CD，假设10分钟)
        rob_cd_type = 2
        rob_cd_duration = self.xiu_config.rob_cd_minutes # 从配置读取CD
        remaining_cd = self.XiuXianService.check_user_cd_specific_type(user_id, rob_cd_type)
        if remaining_cd > 0:
            minutes = remaining_cd // 60
            seconds = remaining_cd % 60
            msg = f"道友杀气过重，请等待 {minutes}分{seconds}秒 后再出手！"
            async for r in self._send_response(event, msg): yield r
            return

        target_user_id = await self._get_at_user_id(event)
        if not target_user_id:
            msg = "道友想抢谁？请@一位仙友！"
            async for r in self._send_response(event, msg): yield r
            return

        is_target_user, user_info_defender, msg_target = check_user(self.XiuXianService, target_user_id)
        if not is_target_user:
            async for r in self._send_response(event, msg_target): yield r
            return

        if user_id == target_user_id:
            msg = "道友为何要与自己过不去？"
            async for r in self._send_response(event, msg): yield r
            return

        # 抢劫前置检查 (境界压制)
        # 假设 USERRANK 在 XiuConfig 中定义，且数值越小境界越高
        # from .config import USERRANK # 确保导入
        attacker_rank = USERRANK.get(user_info_attacker.level, 99)
        defender_rank = USERRANK.get(user_info_defender.level, 99)
        # 如果攻击方境界比防御方低太多（例如，rank值大超过2个大境界，约等于差6-9个小境界）
        if attacker_rank > defender_rank + 6: # 调整这个数值以控制压制程度
            msg = "道友的境界远低于对方，还是不要自取其辱了。"
            async for r in self._send_response(event, msg): yield r
            return

        # 检查防守方是否处于保护期（例如刚被打劫过）
        defender_rob_cd_type = 7 # 假设 type=7 是被打劫保护CD
        defender_remaining_rob_cd = self.XiuXianService.check_user_cd_specific_type(target_user_id, defender_rob_cd_type)
        if defender_remaining_rob_cd > 0:
            minutes = defender_remaining_rob_cd // 60
            seconds = defender_remaining_rob_cd % 60
            msg = f"【{user_info_defender.user_name}】道友刚经历一场恶战，元气未复，请{minutes}分{seconds}秒后再来吧。"
            async for r in self._send_response(event, msg): yield r
            return


        # 获取双方真实数据
        user_real_info_attacker = self.XiuXianService.get_user_real_info(user_id)
        user_real_info_defender = self.XiuXianService.get_user_real_info(target_user_id)

        if not user_real_info_attacker or not user_real_info_defender:
            msg = "获取对战双方信息失败，请稍后再试。"
            async for r in self._send_response(event, msg): yield r
            return

        # 执行战斗模拟
        battle_result = PvPManager.execute_robbery_fight(user_real_info_attacker, user_real_info_defender)

        # 战斗结算
        # 1. 更新双方实际HP (抢劫会真实扣血)
        self.XiuXianService.update_hp_to_value(user_id, battle_result["attacker_hp_final"])
        self.XiuXianService.update_hp_to_value(target_user_id, battle_result["defender_hp_final"])
        self.XiuXianService.update_mp_to_value(user_id, battle_result["attacker_mp_final"])
        self.XiuXianService.update_mp_to_value(target_user_id, battle_result["defender_mp_final"])


        # 2. 处理灵石和通缉状态
        stolen_amount = battle_result['stolen_amount']
        if battle_result['winner'] == user_id: # 攻击方胜利
            self.XiuXianService.update_ls(user_id, stolen_amount, 1)
            self.XiuXianService.update_ls(target_user_id, stolen_amount, 2)
            self.XiuXianService.update_wanted_status(user_id, 1) # 增加通缉值
            # 给被抢的人也设置一个短的保护CD
            self.XiuXianService.set_user_cd(target_user_id, self.xiu_config.robbed_protection_cd_minutes, defender_rob_cd_type)

        elif battle_result['winner'] == target_user_id: # 防守方胜利 (攻击方失败)
            self.XiuXianService.update_ls(user_id, abs(stolen_amount), 2) # 攻击方损失灵石

        # 设置攻击方抢劫CD
        self.XiuXianService.set_user_cd(user_id, rob_cd_duration, rob_cd_type)

        full_battle_log = "\n".join(battle_result['log'])
        #async for r in self._send_response(event, full_battle_log, "抢劫战报"):
        #    yield r

        yield event.chain_result([Comp.Image.fromFileSystem(str(await get_msg_pic(await pic_msg_format(full_battle_log, event))))])

    @filter.command("送灵石")
    @command_lock
    async def give_stones_cmd(self, event: AstrMessageEvent):
        """处理赠送灵石指令"""
        await self._update_active_groups(event)
        sender_id = event.get_sender_id()
        is_sender, sender_info, msg = check_user(self.XiuXianService, sender_id)
        if not is_sender:
            async for r in self._send_response(event, msg): yield r
            return

        target_id = await self._get_at_user_id(event)
        if not target_id:
            msg = "道友想赠予谁灵石呢？请@一位仙友并说明数量。例如：送灵石 @张三 100"
            async for r in self._send_response(event, msg): yield r
            return

        is_target, target_info, msg = check_user(self.XiuXianService, target_id)
        if not is_target:
            msg = "对方尚未踏入仙途，无法接收你的好意。"
            async for r in self._send_response(event, msg): yield r
            return

        if sender_id == target_id:
            msg = "道友无需左右倒右手，平白损失机缘。"
            async for r in self._send_response(event, msg): yield r
            return

        args = event.message_str.split()
        try:
            # 通常数量在参数的最后
            amount_to_give = int(args[-1])
            if amount_to_give <= 0: raise ValueError
        except (ValueError, IndexError):
            msg = "请输入一个正确的赠送数量！例如：送灵石 @张三 100"
            async for r in self._send_response(event, msg): yield r
            return

        if sender_info.stone < amount_to_give:
            msg = f"道友的灵石不足，无法赠送 {amount_to_give} 灵石！"
        else:
            # 执行交易
            self.XiuXianService.update_ls(sender_id, amount_to_give, 2) # 2代表减少
            self.XiuXianService.update_ls(target_id, amount_to_give, 1) # 1代表增加
            msg = f"你成功赠予了【{target_info.user_name}】 {amount_to_give} 块灵石！"

        async for r in self._send_response(event, msg):
            yield r

    @filter.command("使用")
    @command_lock
    async def use_item_cmd(self, event: AstrMessageEvent):
        await self._update_active_groups(event)
        user_id = event.get_sender_id()
        is_user, user_info, msg = check_user(self.XiuXianService, user_id)
        if not is_user:
            async for r in self._send_response(event, msg): yield r
            return

        args = event.message_str.split()
        if len(args) < 2:
            msg = "指令格式错误，请输入“使用 [物品名] [数量]”，数量可选，默认为1。"
            async for r in self._send_response(event, msg): yield r
            return

        item_name = args[1]
        try:
            use_num = int(args[2]) if len(args) > 2 else 1
            if use_num <= 0: raise ValueError
        except ValueError:
            msg = "使用数量必须是一个大于0的整数！"
            async for r in self._send_response(event, msg): yield r
            return

        # 1. 检查背包
        item_in_backpack = self.XiuXianService.get_item_by_name(user_id, item_name)
        if not item_in_backpack or item_in_backpack.goods_num < use_num:
            msg = f"背包中没有足够的【{item_name}】！"
            async for r in self._send_response(event, msg): yield r
            return

        item_info = self.XiuXianService.items.get_data_by_item_id(item_in_backpack.goods_id)
        if not item_info:
            msg = "错误：找不到该物品的详细信息。"
            async for r in self._send_response(event, msg): yield r
            return

        # 2. 根据物品类型分流
        item_type = item_info.get("item_type")
        if item_type in ["丹药", "合成丹药", "商店丹药"]:
            # 调用炼丹管理器处理
            # 传递service实例给manager
            self.alchemy_manager.XiuXianService = self.XiuXianService
            result = self.alchemy_manager.use_pill(user_info, item_in_backpack, item_info, use_num)

            if result['success']:
                # 更新数据库
                self.XiuXianService.remove_item(user_id, item_name, result['consume_num'])
                self.XiuXianService.update_item_usage_counts(
                    user_id,
                    item_in_backpack.goods_id,
                    result['consume_num']
                )

                update_data = result.get("update_data", {})
                if 'exp_add' in update_data:
                    self.XiuXianService.update_exp(user_id, update_data['exp_add'])
                if 'hp_add' in update_data:
                    self.XiuXianService.update_hp(user_id, update_data['hp_add'], 1)
                if 'mp_add' in update_data:
                    self.XiuXianService.update_mp(user_id, update_data['mp_add'], 1)
                if 'atk_add' in update_data:
                    self.XiuXianService.set_user_buff(user_id, "atk_buff", update_data['atk_add'], is_additive=True)
                if 'level_up_rate_add' in update_data:
                    self.XiuXianService.update_user_level_up_rate(user_id, update_data['level_up_rate_add'])
                if 'set_temp_buff' in update_data:
                    temp_buff_data = update_data['set_temp_buff']
                    self.XiuXianService.set_user_temp_buff(
                        user_id,
                        temp_buff_data['key'],
                        temp_buff_data['value'],
                        temp_buff_data.get('duration') # 如果丹药配置了持续时间，则传递
                    )

            msg = result['message']

        elif item_type == "聚灵旗":
            if not user_info.blessed_spot_flag:
                msg = "道友尚未开辟洞天福地，无法安插聚灵旗！"
            else:
                user_buff_info = self.XiuXianService.get_user_buff_info(user_id)
                current_jlq_level = user_buff_info.blessed_spot if user_buff_info else 0

                new_jlq_level = item_info.get("修炼速度", 0) # 聚灵旗的等级就是它的修炼速度加成值

                if current_jlq_level >= new_jlq_level:
                    msg = f"道友的洞天福地已是更高级的聚灵旗，无需更换这面【{item_name}】。"
                else:
                    # 使用成功，消耗物品并更新等级
                    self.XiuXianService.remove_item(user_id, item_name, 1)
                    self.XiuXianService.update_user_blessed_spot_level(user_id, new_jlq_level)
                    msg = f"你将【{item_name}】安插入洞天福地的灵眼之中，顿时感觉灵气浓郁了数倍！\n修炼速度提升至 {new_jlq_level * 100}%！"
        else:
            msg = f"【{item_name}】似乎不能直接使用。"

        async for r in self._send_response(event, msg):
            yield r

    @filter.command("出价")
    @command_lock
    async def bid_auction_cmd(self, event: AstrMessageEvent):
        await self._update_active_groups(event)
        user_id = event.get_sender_id()
        is_user, user_info, msg = check_user(self.XiuXianService, user_id)
        if not is_user:
            async for r in self._send_response(event, msg): yield r
            return

        if not self.auction_data:
            msg = "当前没有正在进行的拍卖会。"
            async for r in self._send_response(event, msg): yield r
            return

        args = event.message_str.split()
        try:
            bid_price = int(args[1]) if len(args) > 1 else 0
            if bid_price <= 0: raise ValueError
        except ValueError:
            msg = "请输入一个正确的出价金额！"
            async for r in self._send_response(event, msg): yield r
            return

        # 检查出价是否合法
        if bid_price <= self.auction_data['current_price']:
            msg = f"你的出价必须高于当前价格 {self.auction_data['current_price']} 灵石！"
            async for r in self._send_response(event, msg): yield r
            return

        if user_info.stone < bid_price:
            msg = "你的灵石不足以支撑你的出价！"
            async for r in self._send_response(event, msg): yield r
            return

        # 更新拍卖信息
        self.auction_data['current_price'] = bid_price
        self.auction_data['top_bidder_id'] = user_id
        self.auction_data['top_bidder_name'] = user_info.user_name

        # 检查是否需要延长拍卖时间
        config = self.xiu_config.auction_config
        time_remaining = (self.auction_data['end_time'] - datetime.now()).total_seconds()
        if time_remaining < config['extension_seconds']:
            self.auction_data['end_time'] = datetime.now() + timedelta(seconds=config['extension_seconds'])
            extension_msg = f"拍卖进入白热化，结束时间已延长至 {config['extension_seconds']} 秒后！"
        else:
            extension_msg = ""

        msg = f"道友【{user_info.user_name}】出价 {bid_price} 灵石！目前为最高价！\n{extension_msg}"
        yield event.plain_result(msg)

    @filter.command("修复所有秘境异常数据")
    async def admin_batch_rollback_cmd(self, event: AstrMessageEvent):
        # 权限检查：只有 SUPERUSER 可以执行
        if event.get_sender_id() not in self.MANUAL_ADMIN_WXIDS:
            msg = "汝非天选之人，无权执此法旨！"
            async for r in self._send_response(event, msg): yield r
            return

        # 执行批量回滚操作
        log_messages = self.XiuXianService.rollback_high_exp_users()

        # 将日志通过转发消息发送出来，避免刷屏
        # 平台适配：如果平台不支持转发，需要用其他方式发送长消息
            #from astrbot.api.message_components import Forward
            #forward_node_list = []
            #for log_msg in log_messages:
            #    forward_node_list.append(
            #        Comp.ForwardNode(
            #            bot_id=self.context.self_id,
            #            user_id=self.context.self_id,
            #            user_name="数据修复日志",
            #            content=MessageChain(log_msg)
            #        )
            #    )
            #yield event.chain_result([Forward(forward_node_list)])
        full_log = "\n\n".join(log_messages)
        async for r in self._send_response(event, full_log, "数据修复报告"):
            yield r

    @filter.command("修复用户数据")
    async def admin_fix_data_cmd(self, event: AstrMessageEvent):
        # 权限检查：只有 SUPERUSER 可以执行
        if event.get_sender_id() not in self.MANUAL_ADMIN_WXIDS:
            msg = "汝非天选之人，无权执此法旨！"
            async for r in self._send_response(event, msg): yield r
            return

        target_id = await self._get_at_user_id(event)

        if target_id:
            # --- 修复单个用户 ---
            is_target, _, msg = check_user(self.XiuXianService, target_id)
            if not is_target:
                async for r in self._send_response(event, msg): yield r
                return

            success, log = self.XiuXianService.fix_user_data(target_id)
            async for r in self._send_response(event, log, "单用户数据修复报告"):
                yield r
        else:
            # --- 修复所有用户 ---
            log_messages = self.XiuXianService.fix_all_users_data()
            full_log = "\n\n".join(log_messages)

            async for r in self._send_response(event, full_log, "全服数据修复报告"):
                yield r

    @filter.command("手动刷新世界boss")
    async def admin_refresh_boss_cmd(self, event: AstrMessageEvent):
        # 权限检查
        if event.get_sender_id() not in self.MANUAL_ADMIN_WXIDS:
            msg = "汝非天选之人，无权执此法旨！"
            async for r in self._send_response(event, msg): yield r
            return

        log_messages = ["收到刷新指令，开始执行..."]

        # 1. 检查并清理内存和数据库中的旧BOSS
        if self.world_boss:
            log_messages.append(f"检测到旧的世界BOSS【{self.world_boss['name']}】，正在进行天罚...")
            # 从数据库删除
            deleted_count = self.XiuXianService.clear_all_bosses()
            # 从内存中清除
            self.world_boss = None
            log_messages.append(f"天罚成功，清除了 {deleted_count} 个旧BOSS记录。")
        else:
            log_messages.append("当前无世界BOSS，直接进入生成流程。")

        # 2. 调用已有的BOSS生成和广播任务
        # 我们不再需要后台执行，因为管理员指令可以接受少量延迟
        try:
            await self.scheduler._create_world_boss_task()
            log_messages.append("新的世界BOSS已召唤成功，并已向所有群聊广播！")
        except Exception as e:
            log_messages.append(f"错误：在生成新的世界BOSS时发生异常：{e}")

        # 3. 发送最终的执行报告给管理员
        final_report = "\n".join(log_messages)
        async for r in self._send_response(event, final_report, "BOSS刷新报告"):
            yield r

    @filter.command("开启钓鱼生涯")
    @command_lock
    async def start_fishing_career(self, event: AstrMessageEvent):
        """为修仙玩家解锁钓鱼功能"""
        user_id = event.get_sender_id()

        is_user, user_info, msg = check_user(self.XiuXianService, user_id)
        if not is_user:
            async for r in self._send_response(event, msg): yield r
            return

        if self.FishingService.db.check_user_registered(user_id):
            msg = "道友早已是钓鱼好手，无需重复开启。"
            async for r in self._send_response(event, msg): yield r
            return

        success = self.FishingService.db.register_user(user_id, user_info.user_name)
        if success:
            msg = "恭喜道友！你在修炼之余，领悟了垂钓的乐趣，成功开启了钓鱼生涯！\n现在就试试发送【钓鱼帮助】吧！"
        else:
            msg = "开启钓鱼生涯失败，似乎是遇到了某种阻碍。"

        async for r in self._send_response(event, msg): yield r

    @filter.command("钓鱼", alias={"fish"})  # ok
    @command_lock
    async def go_fishing(self, event: AstrMessageEvent):
        """进行一次钓鱼"""
        user_id = event.get_sender_id()
        if not self.FishingService.db.check_user_registered(user_id):
            async for r in self._send_response(event, "请先发送【开启钓鱼生涯】解锁钓鱼玩法！"): yield r
            return
        # 检查CD时间
        last_fishing_time = self.FishingService.db.get_last_fishing_time(user_id)
        utc_time = datetime.utcnow()
        utc_plus_4 = utc_time + timedelta(hours=4)
        current_time = utc_plus_4.timestamp()
        # 查看用户是否装备了海洋之心
        equipped_rod = self.FishingService.db.get_user_equipped_accessories(user_id)
        if equipped_rod and equipped_rod.get("name") == "海洋之心":
            # 如果装备了海洋之心，CD时间减少到1分钟
            last_fishing_time = max(0, last_fishing_time - 40)
            logger.info(f"用户 {user_id} 装备了海洋之心，{last_fishing_time}")
        # logger.info(f"用户 {user_id} 上次钓鱼时间: {last_fishing_time}, 当前时间: {current_time}")
        # 3分钟CD (180秒)
        base_cd = 120
        # 获取锻造等级带来的CD减少
        forging_level = self.FishingService.db.get_user_forging_level(user_id)
        bonuses = enhancement_config.get_bonuses_for_level(forging_level)
        cd_reduction = bonuses['fishing_cd_reduction']

        final_cd = base_cd - cd_reduction
        if last_fishing_time > 0 and current_time - last_fishing_time < final_cd:
            remaining_seconds = int(final_cd - (current_time - last_fishing_time))
            remaining_minutes = remaining_seconds // 60
            remaining_secs = remaining_seconds % 60
            yield event.plain_result(f"⏳ 钓鱼冷却中，请等待 {remaining_minutes}分{remaining_secs}秒后再试")
            return

        # 钓鱼需要消耗金币
        fishing_cost = 10  # 每次钓鱼消耗10金币
        user_coins = self.FishingService.db.get_user_coins(user_id)

        if user_coins < fishing_cost:
            yield event.plain_result(f"💰 灵石不足，钓鱼需要 {fishing_cost} 灵石")
            return

        # 扣除金币
        self.FishingService.db.update_user_coins(user_id, -fishing_cost)

        # 进行钓鱼
        result = self.FishingService.fish(user_id)

        # 如果钓鱼成功，显示钓到的鱼的信息
        if result.get("success"):
            fish_info = result.get("fish", {})
            message = f"🎣 恭喜你钓到了 {fish_info.get('name', '未知鱼类')}！\n"
            message += f"✨ 品质：{'★' * fish_info.get('rarity', 1)}\n"
            message += f"⚖️ 重量：{fish_info.get('weight', 0)}g\n"
            message += f"💰 价值：{fish_info.get('value', 0)}灵石"
            yield event.plain_result(message)
        else:
            yield event.plain_result(result.get("message", "💨 什么都没钓到..."))

    @filter.command("鱼全卖")
    async def sell_fish(self, event: AstrMessageEvent):
        """出售背包中所有鱼"""
        user_id = event.get_sender_id()
        result = self.FishingService.sell_all_fish(user_id)

        # 替换普通文本消息为带表情的消息
        original_message = result.get("message", "出售失败！")
        if "成功" in original_message:
            # 如果是成功消息，添加成功相关表情
            coins_earned = 0
            if "获得" in original_message:
                # 尝试从消息中提取获得的金币数量
                try:
                    coins_part = original_message.split("获得")[1]
                    coins_str = ''.join(filter(str.isdigit, coins_part))
                    if coins_str:
                        coins_earned = int(coins_str)
                except:
                    pass

            if coins_earned > 0:
                message = f"💰 成功出售所有鱼！获得 {coins_earned} 灵石"
            else:
                message = f"💰 {original_message}"
        else:
            # 如果是失败消息，添加失败相关表情
            message = f"❌ {original_message}"

        yield event.plain_result(message)

    @filter.command("卖鱼稀有度", alias={"sellr"})
    async def sell_fish_by_rarity(self, event: AstrMessageEvent):
        """出售特定稀有度的鱼"""
        user_id = event.get_sender_id()
        args = event.message_str.split(' ')

        if len(args) < 2:
            yield event.plain_result("⚠️ 请指定要出售的鱼的稀有度（1-5）")
            return

        try:
            rarity = int(args[1])
            if rarity < 1 or rarity > 5:
                yield event.plain_result("⚠️ 稀有度必须在1-5之间")
                return

            result = self.FishingService.sell_fish_by_rarity(user_id, rarity)

            # 替换普通文本消息为带表情的消息
            original_message = result.get("message", "出售失败！")
            if "成功" in original_message:
                # 如果是成功消息，添加成功相关表情
                coins_earned = 0
                if "获得" in original_message:
                    # 尝试从消息中提取获得的金币数量
                    try:
                        coins_part = original_message.split("获得")[1]
                        coins_str = ''.join(filter(str.isdigit, coins_part))
                        if coins_str:
                            coins_earned = int(coins_str)
                    except:
                        pass

                if coins_earned > 0:
                    message = f"💰 成功出售稀有度 {rarity} 的鱼！获得 {coins_earned} "
                else:
                    message = f"💰 {original_message}"
            else:
                # 如果是失败消息，添加失败相关表情
                message = f"❌ {original_message}"

            yield event.plain_result(message)
        except ValueError:
            yield event.plain_result("⚠️ 请输入有效的稀有度数值（1-5）")

    @filter.command("鱼塘")  # ok
    async def show_inventory(self, event: AstrMessageEvent):
        """显示用户的鱼背包"""
        user_id = event.get_sender_id()

        # 检查用户是否注册
        if not self.FishingService.is_registered(user_id):
            yield event.plain_result("请先注册才能使用此功能")
            return

        # 获取用户鱼背包
        fish_inventory = self.FishingService.get_fish_pond(user_id)

        if not fish_inventory.get("success"):
            yield event.plain_result(fish_inventory.get("message", "获取背包失败！"))
            return

        fishes = fish_inventory.get("fishes", [])
        total_value = fish_inventory.get("stats", {}).get("total_value", 0)

        if not fishes:
            yield event.plain_result("你的鱼塘是空的，快去钓鱼吧！")
            return

        # 按稀有度分组
        fishes_by_rarity = {}
        for fish in fishes:
            rarity = fish.get("rarity", 1)
            if rarity not in fishes_by_rarity:
                fishes_by_rarity[rarity] = []
            fishes_by_rarity[rarity].append(fish)

        # 构建消息
        message = "【🐟 鱼塘】\n"

        for rarity in sorted(fishes_by_rarity.keys(), reverse=True):
            message += f"\n{'★' * rarity} 稀有度 {rarity}:\n"
            for fish in fishes_by_rarity[rarity]:
                message += f"- {fish.get('name')} x{fish.get('quantity')} ({fish.get('base_value', 0)}金币/个)\n"

        message += f"\n💰 总价值: {total_value}灵石"

        yield event.plain_result(message)

    @filter.command("不开放签到")  # ok
    async def daily_sign_in(self, event: AstrMessageEvent):
        """每日签到领取奖励"""
        user_id = event.get_sender_id()
        result = self.FishingService.daily_sign_in(user_id)

        # 替换普通文本消息为带表情的消息
        original_message = result.get("message", "签到失败！")
        if "成功" in original_message:
            # 如果是成功消息，添加成功相关表情
            coins_earned = 0
            if "获得" in original_message:
                # 尝试从消息中提取获得的金币数量
                try:
                    coins_part = original_message.split("获得")[1]
                    coins_str = ''.join(filter(str.isdigit, coins_part))
                    if coins_str:
                        coins_earned = int(coins_str)
                except:
                    pass

            if coins_earned > 0:
                message = f"📅 签到成功！获得 {coins_earned} 灵石 💰"
            else:
                message = f"📅 {original_message}"
        elif "已经" in original_message and "签到" in original_message:
            # 如果是已经签到的消息
            message = f"📅 你今天已经签到过了，明天再来吧！"
        else:
            # 如果是其他失败消息
            message = f"❌ {original_message}"

        yield event.plain_result(message)

    @filter.command("鱼饵", alias={"baits"})
    async def show_baits(self, event: AstrMessageEvent):
        """显示用户拥有的鱼饵"""
        user_id = event.get_sender_id()

        # 检查用户是否注册
        if not self.FishingService.is_registered(user_id):
            yield event.plain_result("请先注册才能使用此功能")
            return

        # 获取用户鱼饵
        baits = self.FishingService.get_user_baits(user_id)

        if not baits.get("success"):
            yield event.plain_result(baits.get("message", "获取鱼饵失败！"))
            return

        user_baits = baits.get("baits", [])

        if not user_baits:
            yield event.plain_result("🎣 你没有任何鱼饵，可以通过商店购买！")
            return

        # 构建消息
        message = "【🎣 鱼饵背包】\n"

        has_baits = False
        for bait in user_baits:
            # 只显示数量大于0的鱼饵
            if bait.get("quantity", 0) > 0:
                has_baits = True
                bait_id = bait.get("bait_id")
                message += f"ID: {bait_id} - {bait.get('name')} x{bait.get('quantity')}"
                if bait.get("effect_description"):
                    message += f" ({bait.get('effect_description')})"
                message += "\n"

        if not has_baits:
            yield event.plain_result("🎣 你没有任何鱼饵，可以通过商店购买！")
            return

        # 获取当前使用的鱼饵
        current_bait = self.FishingService.get_current_bait(user_id)
        if current_bait.get("success") and current_bait.get("bait"):
            bait = current_bait.get("bait")
            message += f"\n⭐ 当前使用的鱼饵: {bait.get('name')}"
            if bait.get("remaining_time"):
                message += f" (⏱️  剩余时间: {bait.get('remaining_time')}分钟)"

        yield event.plain_result(message)

    @filter.command("使用鱼饵", alias={"usebait"})
    async def use_bait(self, event: AstrMessageEvent):
        """使用特定的鱼饵"""
        user_id = event.get_sender_id()
        args = event.message_str.split(' ')

        if len(args) < 2:
            yield event.plain_result("⚠️ 请指定要使用的鱼饵ID")
            return

        try:
            bait_id = int(args[1])
            result = self.FishingService.use_bait(user_id, bait_id)

            # 增加表情符号
            original_message = result.get("message", "使用鱼饵失败！")
            if "成功" in original_message:
                message = f"🎣 {original_message}"
            else:
                message = f"❌ {original_message}"

            yield event.plain_result(message)
        except ValueError:
            yield event.plain_result("⚠️ 请输入有效的鱼饵ID")

    @filter.command("购买鱼饵", alias={"buybait"})
    async def buy_bait(self, event: AstrMessageEvent):
        """购买鱼饵"""
        user_id = event.get_sender_id()
        args = event.message_str.split(' ')

        if len(args) < 2:
            yield event.plain_result("⚠️ 请指定要购买的鱼饵ID和数量，格式：购买鱼饵 <ID> [数量]")
            return

        try:
            bait_id = int(args[1])

            # 增加数量参数支持
            quantity = 1  # 默认数量为1
            if len(args) >= 3:
                quantity = int(args[2])
                if quantity <= 0:
                    yield event.plain_result("⚠️ 购买数量必须大于0")
                    return

            result = self.FishingService.buy_bait(user_id, bait_id, quantity)

            # 增加表情符号
            original_message = result.get("message", "购买鱼饵失败！")
            if "成功" in original_message:
                message = f"🛒 {original_message}"
            elif "不足" in original_message:
                message = f"💸 {original_message}"
            else:
                message = f"❌ {original_message}"

            yield event.plain_result(message)
        except ValueError:
            yield event.plain_result("⚠️ 请输入有效的鱼饵ID和数量")

    @filter.command("系统鱼店")
    async def show_shop(self, event: AstrMessageEvent):
        """显示商店中可购买的物品"""
        user_id = event.get_sender_id()

        # 检查用户是否注册
        if not self.FishingService.is_registered(user_id):
            yield event.plain_result("请先注册才能使用此功能")
            return

        # 获取所有鱼饵
        all_baits = self.FishingService.get_all_baits()

        # 获取所有鱼竿
        all_rods = self.FishingService.get_all_rods()

        # 构建消息
        message = "【🏪 钓鱼商店】\n"

        # 显示鱼饵
        message += "\n【🎣 鱼饵】\n"
        for bait in all_baits.get("baits", []):
            if bait.get("cost", 0) > 0:  # 只显示可购买的
                message += f"ID:{bait.get('bait_id')} - {bait.get('name')} (💰 {bait.get('cost')}灵石)"
                if bait.get("description"):
                    message += f" - {bait.get('description')}"
                message += "\n"

        # 显示鱼竿
        message += "\n【🎣 鱼竿】\n"
        for rod in all_rods.get("rods", []):
            if rod.get("source") == "shop" and rod.get("purchase_cost", 0) > 0:
                message += f"ID:{rod.get('rod_id')} - {rod.get('name')} (💰 {rod.get('purchase_cost')}灵石)"
                message += f" - 稀有度:{'★' * rod.get('rarity', 1)}"
                if rod.get("bonus_fish_quality_modifier", 1.0) > 1.0:
                    message += f" - 品质加成:⬆️ {int((rod.get('bonus_fish_quality_modifier', 1.0) - 1) * 100)}%"
                if rod.get("bonus_fish_quantity_modifier", 1.0) > 1.0:
                    message += f" - 数量加成:⬆️ {int((rod.get('bonus_fish_quantity_modifier', 1.0) - 1) * 100)}%"
                if rod.get("bonus_rare_fish_chance", 0.0) > 0:
                    message += f" - 稀有度加成:⬆️ {int(rod.get('bonus_rare_fish_chance', 0.0) * 100)}%"
                message += "\n"

        message += "\n💡 使用「购买鱼饵 ID nums」或「购买鱼竿 ID」命令购买物品"
        yield event.plain_result(message)

    @filter.command("购买鱼竿", alias={"buyrod"})
    async def buy_rod(self, event: AstrMessageEvent):
        """购买鱼竿"""
        user_id = event.get_sender_id()
        args = event.message_str.split(' ')

        if len(args) < 2:
            yield event.plain_result("⚠️ 请指定要购买的鱼竿ID")
            return

        try:
            rod_id = int(args[1])
            result = self.FishingService.buy_rod(user_id, rod_id)

            # 增加表情符号
            original_message = result.get("message", "购买鱼竿失败！")
            if "成功" in original_message:
                message = f"🛒 {original_message}"
            elif "不足" in original_message:
                message = f"💸 {original_message}"
            else:
                message = f"❌ {original_message}"

            yield event.plain_result(message)
        except ValueError:
            yield event.plain_result("⚠️ 请输入有效的鱼竿ID")

    @filter.command("使用鱼竿", alias={"userod"})
    async def use_rod(self, event: AstrMessageEvent):
        """装备指定的鱼竿"""
        user_id = event.get_sender_id()
        args = event.message_str.split(' ')

        # 检查用户是否注册
        if not self.FishingService.is_registered(user_id):
            yield event.plain_result("请先注册才能使用此功能")
            return

        if len(args) < 2:
            yield event.plain_result("⚠️ 请指定要装备的鱼竿ID")
            return

        try:
            rod_instance_id = int(args[1])
            result = self.FishingService.equip_rod(user_id, rod_instance_id)

            # 增加表情符号
            original_message = result.get("message", "装备鱼竿失败！")
            if "成功" in original_message:
                message = f"🎣 {original_message}"
            else:
                message = f"❌ {original_message}"

            yield event.plain_result(message)
        except ValueError:
            yield event.plain_result("⚠️ 请输入有效的鱼竿ID")

    @filter.command("鱼竿", alias={"rods"})
    async def show_rods(self, event: AstrMessageEvent):
        """显示用户拥有的鱼竿"""
        user_id = event.get_sender_id()

        # 检查用户是否注册
        if not self.FishingService.is_registered(user_id):
            yield event.plain_result("请先注册才能使用此功能")
            return

        # 获取用户鱼竿
        rods = self.FishingService.get_user_rods(user_id)

        if not rods.get("success"):
            yield event.plain_result(rods.get("message", "获取鱼竿失败！"))
            return

        user_rods = rods.get("rods", [])

        if not user_rods:
            yield event.plain_result("你没有任何鱼竿，可以通过商店购买！")
            return

        # 构建消息
        message = "【🎣 鱼竿背包】\n"

        # 获取当前装备信息
        equipment_info = self.FishingService.get_user_equipment(user_id)
        if not equipment_info.get("success"):
            # 如果获取装备信息失败，直接显示鱼竿信息，但不标记已装备状态
            for rod in user_rods:
                message += f"ID:{rod.get('rod_instance_id')}- {rod.get('name')} (稀有度:{'★' * rod.get('rarity', 1)})\n"
                if rod.get("description"):
                    message += f"  描述: {rod.get('description')}\n"
                if rod.get("bonus_fish_quality_modifier", 1.0) != 1.0:
                    message += f"  品质加成: {(rod.get('bonus_fish_quality_modifier', 1.0) - 1) * 100:.0f}%\n"
                if rod.get("bonus_fish_quantity_modifier", 1.0) != 1.0:
                    message += f"  数量加成: {(rod.get('bonus_fish_quantity_modifier', 1.0) - 1) * 100:.0f}%\n"
                if rod.get("bonus_rare_fish_chance", 0.0) > 0:
                    message += f"  稀有度加成: +{rod.get('bonus_rare_fish_chance', 0.0) * 100:.0f}%\n"
        else:
            # 正常显示包括已装备状态
            equipped_rod = equipment_info.get("rod")
            equipped_rod_id = equipped_rod.get("rod_instance_id") if equipped_rod else None

            for rod in user_rods:
                rod_instance_id = rod.get("rod_instance_id")
                is_equipped = rod_instance_id == equipped_rod_id or rod.get("is_equipped", False)

                message += f"ID:{rod_instance_id} - {rod.get('name')} (稀有度:{'★' * rod.get('rarity', 1)})"
                if is_equipped:
                    message += " [已装备]"
                message += "\n"
                if rod.get("description"):
                    message += f"  描述: {rod.get('description')}\n"
                if rod.get("bonus_fish_quality_modifier", 1.0) != 1.0:
                    message += f"  品质加成: {(rod.get('bonus_fish_quality_modifier', 1.0) - 1) * 100:.0f}%\n"
                if rod.get("bonus_fish_quantity_modifier", 1.0) != 1.0:
                    message += f"  数量加成: {(rod.get('bonus_fish_quantity_modifier', 1.0) - 1) * 100:.0f}%\n"
                if rod.get("bonus_rare_fish_chance", 0.0) > 0:
                    message += f"  稀有度加成: +{rod.get('bonus_rare_fish_chance', 0.0) * 100:.0f}%\n"

        yield event.plain_result(message)

    @filter.command("出售鱼竿", alias={"sellrod"})
    async def sell_rod(self, event: AstrMessageEvent):
        """出售指定的鱼竿"""
        user_id = event.get_sender_id()
        args = event.message_str.split(' ')

        if len(args) < 2:
            yield event.plain_result("⚠️ 请指定要出售的鱼竿ID")
            return

        try:
            rod_instance_id = int(args[1])
            result = self.FishingService.sell_rod(user_id, rod_instance_id)

            # 增加表情符号
            original_message = result.get("message", "出售鱼竿失败！")
            if "成功" in original_message:
                message = f"🛒 {original_message}"
            else:
                message = f"❌ {original_message}"

            yield event.plain_result(message)
        except ValueError:
            yield event.plain_result("⚠️ 请输入有效的鱼竿ID")

    @filter.command("鱼乐乐")
    async def do_gacha(self, event: AstrMessageEvent):
        """进行单次抽卡"""
        user_id = event.get_sender_id()
        args = event.message_str.split(' ')

        # 检查用户是否注册
        if not self.FishingService.is_registered(user_id):
            yield event.plain_result("请先注册才能使用此功能")
            return

        if len(args) < 2:
            # 获取所有抽卡池
            pools = self.FishingService.get_all_gacha_pools()
            if pools.get("success"):
                message = "【🎮 可用的抽卡池】\n\n"
                for pool in pools.get("pools", []):
                    message += f"ID:{pool.get('gacha_pool_id')} - {pool.get('name')}"
                    if pool.get("description"):
                        message += f" - {pool.get('description')}"
                    message += f"    💰 花费: {pool.get('cost_coins')}/次\n\n"

                # 添加卡池详细信息
                message += "【📋 卡池详情】使用「查看鱼乐乐 ID」命令查看详细物品概率\n"
                message += "【🎲 抽卡命令】使用「鱼乐乐 ID」命令选择抽卡池进行单次抽卡\n"
                message += "【🎯 十连命令】使用「十鱼乐 ID」命令进行十连抽卡"
                yield event.plain_result(message)
                return
            else:
                yield event.plain_result("❌ 获取抽卡池失败！")
                return
        try:
            pool_id = int(args[1])
            result = self.FishingService.gacha(user_id, pool_id)
            logger.info(f"用户 {user_id} 抽卡结果: {result}")
            if result.get("success"):
                item = result.get("item", {})

                # 根据稀有度添加不同的表情
                rarity = item.get('rarity', 1)
                rarity_emoji = "✨" if rarity >= 4 else "🌟" if rarity >= 3 else "⭐" if rarity >= 2 else "🔹"

                message = f"{rarity_emoji} 抽卡结果: {item.get('name', '未知物品')}"
                if item.get("rarity"):
                    message += f" (稀有度:{'★' * item.get('rarity', 1)})"
                if item.get("quantity", 1) > 1:
                    message += f" x{item.get('quantity', 1)}"
                message += "\n"

                # 获取物品的详细信息
                item_type = item.get('type')
                item_id = item.get('id')

                # 根据物品类型获取详细信息
                details = None
                if item_type == 'rod':
                    details = self.FishingService.db.get_rod_info(item_id)
                elif item_type == 'accessory':
                    details = self.FishingService.db.get_accessory_info(item_id)
                elif item_type == 'bait':
                    details = self.FishingService.db.get_bait_info(item_id)

                # 显示物品描述
                if details and details.get('description'):
                    message += f"📝 描述: {details.get('description')}\n"

                # 显示物品属性
                if details:
                    # 显示品质加成
                    quality_modifier = details.get('bonus_fish_quality_modifier', 1.0)
                    if quality_modifier > 1.0:
                        message += f"✨ 品质加成: +{(quality_modifier - 1) * 100:.0f}%\n"

                    # 显示数量加成
                    quantity_modifier = details.get('bonus_fish_quantity_modifier', 1.0)
                    if quantity_modifier > 1.0:
                        message += f"📊 数量加成: +{(quantity_modifier - 1) * 100:.0f}%\n"

                    # 显示稀有度加成
                    rare_chance = details.get('bonus_rare_fish_chance', 0.0)
                    if rare_chance > 0:
                        message += f"🌟 稀有度加成: +{rare_chance * 100:.0f}%\n"

                    # 显示效果说明(鱼饵)
                    if item_type == 'bait' and details.get('effect_description'):
                        message += f"🎣 效果: {details.get('effect_description')}\n"

                    # 显示饰品特殊效果
                    if item_type == 'accessory' and details.get('other_bonus_description'):
                        message += f"🔮 特殊效果: {details.get('other_bonus_description')}\n"
                yield event.plain_result(message)
            else:
                original_message = result.get("message", "抽卡失败！")
                if "不足" in original_message:
                    yield event.plain_result(f"💸 {original_message}")
                else:
                    yield event.plain_result(f"❌ {original_message}")
        except ValueError:
            yield event.plain_result("⚠️ 请输入有效的抽卡池ID")

    @filter.command("查看鱼乐乐")
    async def view_gacha_pool(self, event: AstrMessageEvent):
        """查看卡池详细信息"""
        user_id = event.get_sender_id()
        args = event.message_str.split(' ')

        if len(args) < 2:
            yield event.plain_result("请指定要查看的卡池ID，如：查看卡池 1")
            return

        try:
            pool_id = int(args[1])
            pool_details = self.FishingService.db.get_gacha_pool_details(pool_id)

            if not pool_details:
                yield event.plain_result(f"卡池ID:{pool_id} 不存在")
                return

            message = f"【{pool_details.get('name')}】{pool_details.get('description', '')}\n\n"
            message += f"抽取花费: {pool_details.get('cost_coins', 0)}灵石\n\n"

            message += "可抽取物品:\n"
            # 按稀有度分组
            items_by_rarity = {}
            for item in pool_details.get('items', []):
                rarity = item.get('item_rarity', 1)
                if rarity not in items_by_rarity:
                    items_by_rarity[rarity] = []
                items_by_rarity[rarity].append(item)

            # 按稀有度从高到低显示
            for rarity in sorted(items_by_rarity.keys(), reverse=True):
                message += f"\n稀有度 {rarity} ({'★' * rarity}):\n"
                for item in items_by_rarity[rarity]:
                    item_name = item.get('item_name', f"{item.get('item_type')}_{item.get('item_id')}")
                    probability = item.get('probability', 0)
                    quantity = item.get('quantity', 1)

                    if item.get('item_type') == 'coins':
                        item_name = f"{quantity}灵石"
                    elif quantity > 1:
                        item_name = f"{item_name} x{quantity}"

                    message += f"- {item_name} ({probability:.2f}%)\n"

                    # 添加物品描述
                    item_description = item.get('item_description')
                    if item_description:
                        message += f"  描述: {item_description}\n"

                    # 添加属性加成信息
                    item_type = item.get('item_type')
                    if item_type in ['rod', 'accessory']:
                        # 品质加成
                        quality_modifier = item.get('quality_modifier', 1.0)
                        if quality_modifier > 1.0:
                            message += f"  品质加成: +{(quality_modifier - 1) * 100:.0f}%\n"

                        # 数量加成
                        quantity_modifier = item.get('quantity_modifier', 1.0)
                        if quantity_modifier > 1.0:
                            message += f"  数量加成: +{(quantity_modifier - 1) * 100:.0f}%\n"

                        # 稀有度加成
                        rare_chance = item.get('rare_chance', 0.0)
                        if rare_chance > 0:
                            message += f"  稀有度加成: +{rare_chance * 100:.0f}%\n"

                    # 添加效果说明
                    effect_description = item.get('effect_description')
                    if effect_description:
                        message += f"  效果: {effect_description}\n"
            yield event.plain_result(message)

        except ValueError:
            yield event.plain_result("请输入有效的卡池ID")

    @filter.command("十鱼乐", alias={"multi"})
    async def do_multi_gacha(self, event: AstrMessageEvent):
        """进行十连抽卡"""
        user_id = event.get_sender_id()
        args = event.message_str.split(' ')

        # 检查用户是否注册
        if not self.FishingService.is_registered(user_id):
            yield event.plain_result("请先注册才能使用此功能")
            return

        if len(args) < 2:
            yield event.plain_result("⚠️ 请指定要抽卡的池子ID")
            return

        try:
            pool_id = int(args[1])
            result = self.FishingService.multi_gacha(user_id, pool_id)

            if result.get("success"):
                results = result.get("results", [])
                rewards_by_rarity = result.get("rewards_by_rarity", {})
                message = "【🎮 十连抽卡结果】\n\n"

                # 先显示高稀有度的物品
                for rarity in sorted(rewards_by_rarity.keys(), reverse=True):
                    items = rewards_by_rarity[rarity]

                    # 根据稀有度显示不同的表情
                    rarity_emoji = "✨" if rarity >= 4 else "🌟" if rarity >= 3 else "⭐" if rarity >= 2 else "🔹"
                    message += f"{rarity_emoji} 稀有度 {rarity} ({'★' * rarity}):\n"

                    for item in items:
                        item_name = item.get('name', '未知物品')
                        quantity = item.get('quantity', 1)

                        if quantity > 1:
                            message += f"- {item_name} x{quantity}\n"
                        else:
                            message += f"- {item_name}\n"

                        # 获取物品的详细信息
                        item_type = item.get('type')
                        item_id = item.get('id')

                        # 只为稀有度3及以上的物品显示详细信息
                        if rarity >= 3:
                            details = None
                            if item_type == 'rod':
                                details = self.FishingService.db.get_rod_info(item_id)
                            elif item_type == 'accessory':
                                details = self.FishingService.db.get_accessory_info(item_id)
                            elif item_type == 'bait':
                                details = self.FishingService.db.get_bait_info(item_id)

                            # 显示物品描述
                            if details and details.get('description'):
                                message += f"  📝 描述: {details.get('description')}\n"

                            # 显示物品属性
                            if details:
                                # 显示品质加成
                                quality_modifier = details.get('bonus_fish_quality_modifier', 1.0)
                                if quality_modifier > 1.0:
                                    message += f"  ✨ 品质加成: +{(quality_modifier - 1) * 100:.0f}%\n"

                                # 显示数量加成
                                quantity_modifier = details.get('bonus_fish_quantity_modifier', 1.0)
                                if quantity_modifier > 1.0:
                                    message += f"  📊 数量加成: +{(quantity_modifier - 1) * 100:.0f}%\n"

                                # 显示稀有度加成
                                rare_chance = details.get('bonus_rare_fish_chance', 0.0)
                                if rare_chance > 0:
                                    message += f"  🌟 稀有度加成: +{rare_chance * 100:.0f}%\n"

                                # 显示效果说明(鱼饵)
                                if item_type == 'bait' and details.get('effect_description'):
                                    message += f"  🎣 效果: {details.get('effect_description')}\n"

                                # 显示饰品特殊效果
                                if item_type == 'accessory' and details.get('other_bonus_description'):
                                    message += f"  🔮 特殊效果: {details.get('other_bonus_description')}\n"

                    message += "\n"
                yield event.plain_result(message)
            else:
                original_message = result.get("message", "十连抽卡失败！")
                if "不足" in original_message:
                    yield event.plain_result(f"💸 {original_message}")
                else:
                    yield event.plain_result(f"❌ {original_message}")
        except ValueError:
            yield event.plain_result("⚠️ 请输入有效的抽卡池ID")

    @filter.command("鱼鱼排行榜", alias={"rank", "钓鱼排行"})
    async def show_ranking(self, event: AstrMessageEvent):
        """显示钓鱼排行榜"""
        try:

            info = self.FishingService.db.get_leaderboard_with_details(limit=1000)

            ouput_path = os.path.join(os.path.dirname(__file__), "fishing_ranking.png")

            if not info:
                yield event.plain_result("📊 暂无排行榜数据，快去争当第一名吧！")
                return
            draw_fishing_ranking(info, ouput_path)
            # 发送图片
            yield event.image_result(ouput_path)
        except Exception as e:
            logger.error(f"获取排行榜失败: {e}")
            yield event.plain_result(f"❌ 获取排行榜时出错，请稍后再试！")

    @filter.command("自动钓鱼")
    async def toggle_auto_fishing(self, event: AstrMessageEvent):
        """开启或关闭自动钓鱼"""
        user_id = event.get_sender_id()
        result = self.FishingService.toggle_auto_fishing(user_id)

        # 增加表情符号
        original_message = result.get("message", "操作失败！")
        if "开启" in original_message:
            message = f"🤖 {original_message}"
        elif "关闭" in original_message:
            message = f"⏹️  {original_message}"
        else:
            message = f"❌ {original_message}"

        yield event.plain_result(message)

    @filter.command("鱼竿强化查询")
    async def show_forge_status(self, event: AstrMessageEvent):
        """显示用户的锻造等级和属性"""
        user_id = event.get_sender_id()
        if not self.FishingService.is_registered(user_id):
            yield event.plain_result("请先注册才能使用此功能")
            return

        level = self.FishingService.db.get_user_forging_level(user_id)
        bonuses = enhancement_config.get_bonuses_for_level(level)

        message = f"【⚔️ 你的锻造详情】\n\n"
        message += f"当前等级: +{level}\n\n"
        message += "当前总加成:\n"
        message += f"  - 品质加成: +{bonuses['quality_bonus']}%\n"
        message += f"  - 稀有度加成: +{bonuses['rare_bonus']}%\n"
        message += f"  - 钓鱼CD减少: {bonuses['fishing_cd_reduction']}秒\n"
        message += f"  - 偷鱼CD减少: {bonuses['steal_cd_reduction']}分钟\n\n"

        next_level_config = enhancement_config.get_config_for_next_level(level)
        if next_level_config:
            message += f"鱼竿强化到 +{level + 1}:\n"
            message += f"  - 成功率: {next_level_config['probability']}%\n"
            message += f"  - 所需金币: {next_level_config['cost']}\n\n"
            message += "💡 使用「/鱼竿强化」命令进行强化！"
        else:
            message += "恭喜你，已达到最高锻造等级！"

        yield event.plain_result(message)

    @filter.command("鱼竿强化", alias={"forge"})
    async def enhance_forge(self, event: AstrMessageEvent):
        """进行一次锻造强化"""
        user_id = event.get_sender_id()

        # 再次检查注册
        if not self.FishingService.is_registered(user_id):
            yield event.plain_result("请先注册才能使用此功能")
            return


        use_luck_charm = "使用幸运符" in event.message_str

        result = self.FishingService.perform_enhancement(user_id, use_luck_charm)
        # <<< 修复结束 >>>
        #result = self.FishingService.perform_enhancement(user_id)

        # 构造并发送结果消息
        final_message = ""
        if result["success"]:
            final_message += f"🎉 {result['message']}\n"
        else:
            # 对于金币不足或已满级的特殊失败情况，直接显示消息
            if "金币不足" in result['message'] or "最高" in result['message']:
                yield event.plain_result(f"⚠️ {result['message']}")
                return
            final_message += f"💧 {result['message']}\n"

        old_level = result.get('old_level', 0)
        new_level_config = enhancement_config.get_config_for_next_level(old_level)

        if new_level_config:
            final_message += f"\n下次强化到 +{old_level + 1}:\n"
            final_message += f"  - 成功率: {new_level_config['probability']}%\n"
            final_message += f"  - 成本: {new_level_config['cost']} 金币"
        else:
            final_message += "\n你已达到最高强化等级！"

        yield event.plain_result(final_message)

    @filter.command("不开放职业")
    async def show_classes(self, event: AstrMessageEvent):
        """显示所有可选的职业"""
        message = "【⚔️ 渔夫的传承】\n\n"
        message += "当你的锻造等级达到+5，即可选择一个职业，走向不同的巅峰之路！\n\n"
        for key, info in class_config.CLASSES.items():
            message += f"【{info['name']}】\n"
            message += f"特色: {info['description']}\n"
            for passive in info['passives']:
                message += f"- {passive}\n"
            message += f"- {info['active_skill']['description']}\n\n"
        message += "使用「/选择职业 <职业名>」来选择你的道路！"
        yield event.plain_result(message)

    @filter.command("不开放选择职业")
    async def choose_class(self, event: AstrMessageEvent):
        """选择一个职业"""
        user_id = event.get_sender_id()
        args = event.message_str.split(' ')
        if len(args) < 2:
            yield event.plain_result("⚠️ 请输入你想选择的职业名称，例如：/选择职业 巨物猎手")
            return

        class_name = args[1]
        result = self.FishingService.choose_player_class(user_id, class_name)
        yield event.plain_result(f"✨ {result['message']}")

    @filter.command("不开放发动技能")
    async def use_class_active_skill(self, event: AstrMessageEvent):
        """统一的主动技能发动入口"""
        user_id = event.get_sender_id()

        # 调用服务层
        result = self.FishingService.use_active_skill(user_id)

        # 根据结果向用户发送消息
        if result['success']:
            yield event.plain_result(f"✨ {result['message']}")
        else:
            yield event.plain_result(f"⚠️ {result['message']}")

    @filter.command("不开放我的职业")
    async def show_my_class(self, event: AstrMessageEvent):
        """显示当前职业信息"""
        user_id = event.get_sender_id()
        player_class_key = self.FishingService.db.get_player_class(user_id)

        if player_class_key == '无':
            yield event.plain_result("你尚未选择任何职业。使用「/职业」查看可选职业。")
            return

        info = class_config.CLASSES.get(player_class_key)
        if not info:
            yield event.plain_result("发生未知错误，无法找到你的职业信息。")
            return

        message = f"【你当前的传承：{info['name']}】\n\n"
        message += f"特色: {info['description']}\n\n"
        message += "被动技能:\n"
        for passive in info['passives']:
            message += f"- {passive}\n"
        message += "\n主动技能:\n"
        message += f"- {info['active_skill']['description']}\n"
        message += f"  (统一使用命令: /发动技能)"
        #message += f"  (使用命令: {info['active_skill']['command']})"
        yield event.plain_result(message)

    @filter.command("打开鱼箱", alias={"openchest"})
    async def open_chest(self, event: AstrMessageEvent):
        """
        打开一个或多个宝箱。
        用法:
        /打开鱼箱 [数量]
        (若不指定数量，默认为1)
        """
        args = event.message_str.split()
        user_id = event.get_sender_id()
        quantity = 1 # 默认数量
        result = None

        try:
            # --- 核心修改：智能解析参数 ---
            if len(args) == 1: # /打开宝箱
                logger.info(user_id)
                result = self.FishingService.open_treasure_chest(user_id, 1)

            elif len(args) == 2:
                # 可能是 /打开宝箱 5，也可能是 /打开宝箱 鱼竿
                if args[1].isdigit():
                    quantity = int(args[1])
                    result = self.FishingService.open_treasure_chest(user_id, quantity)
                elif args[1] in ['鱼竿', '饰品']:
                    chest_type = 'rod' if args[1] == '鱼竿' else 'accessory'
                    result = self.FishingService.open_equipment_chest(user_id, chest_type, 1)
                else:
                    yield event.plain_result(f"❌ 参数错误！未知宝箱类型: {args[1]}")
                    return

            elif len(args) == 3:
                # /打开宝箱 鱼竿 5
                if args[1] in ['鱼竿', '饰品'] and args[2].isdigit():
                    chest_type = 'rod' if args[1] == '鱼竿' else 'accessory'
                    quantity = int(args[2])
                    result = self.FishingService.open_equipment_chest(user_id, chest_type, quantity)
                else:
                    yield event.plain_result("❌ 格式错误！请使用: /打开宝箱 鱼竿/饰品 <数量>")
                    return

            else:
                yield event.plain_result("❌ 命令格式不正确。请查看帮助。")
                return

            # --- 统一发送结果 ---
            if result:
                yield event.plain_result(f"🎉 {result['message']}" if result.get('success') else f"⚠️ {result.get('message', '操作失败')}")

        except ValueError:
            yield event.plain_result("❌ 数量必须是一个有效的数字。")
        except Exception as e:
            logger.error(f"打开宝箱时发生未知错误: {e}", exc_info=True)
            yield event.plain_result("❌ 打开宝箱时发生内部错误，请联系管理员。")

    @filter.command("不开放遗忘河之水")
    async def change_class(self, event: AstrMessageEvent):
        """花费50000金币进行转职，重置当前职业"""
        user_id = event.get_sender_id()

        # 为了防止误操作，可以增加一个二次确认的步骤
        # 这里为了简化，直接执行转职逻辑
        result = self.FishingService.change_player_class(user_id)

        if result['success']:
            yield event.plain_result(f"✨ {result['message']}")
        else:
            yield event.plain_result(f"⚠️ {result['message']}")

    @filter.command("不开放角斗")
    async def duel(self, event: AstrMessageEvent):
        """向另一名玩家发起一场PVP对决（一次性发送完整战报）"""
        attacker_id = event.get_sender_id()

        # --- 使用您提供的、经过验证的target_id提取逻辑 ---
        target_id = None
        message_obj = event.message_obj

        if hasattr(message_obj, 'raw_message'):
            raw_message_dict = message_obj.raw_message
            if isinstance(raw_message_dict, dict) and 'msg_source' in raw_message_dict:
                msg_source = raw_message_dict['msg_source']
                logger.info(f"角斗命令: 获取到 msg_source: {msg_source}")

                match = re.search(r"<atuserlist>(.*?)</atuserlist>", msg_source)
                if match:
                    inner_content = match.group(1).strip()
                    if inner_content.startswith('<![CDATA[') and inner_content.endswith(']]>'):
                        wxids_string = inner_content[9:-3]
                    else:
                        wxids_string = inner_content

                    wxid_list = [wxid for wxid in wxids_string.split(',') if wxid]

                    if wxid_list:
                        target_id = wxid_list[0]
                        logger.info(f"角斗命令: 成功提取到目标 target_id: {target_id}")
                    else:
                        logger.warning("角斗命令: 在 <atuserlist> 中解析出了空的 wxid 列表")

        if not target_id:
            yield event.plain_result("⚠️ 请@一个你想挑战的玩家。")
            return

        # 发送等待消息
        yield event.plain_result("⚔️ 角斗场的大门已经打开... 正在进行一场史诗般的对决！请稍候...")

        try:
            # 调用Service层处理核心逻辑
            result = self.FishingService.initiate_duel(attacker_id, target_id)

            # --- 核心修改：直接发送结果 ---
            if not result['success']:
                yield event.plain_result(f"❌ 决斗未能开始: {result['message']}")
            else:
                # 无论战报长短，都一次性发送
                yield event.plain_result(result['message'])
            # --- 修改结束 ---

        except Exception as e:
            logger.error(f"执行决斗时发生未知错误: {e}", exc_info=True)
            yield event.plain_result("❌ 执行决斗时发生未知错误，请联系管理员。")

    @filter.command("不开放我的道具")
    async def show_my_items(self, event: AstrMessageEvent):
        """显示玩家的特殊道具背包"""
        user_id = event.get_sender_id()
        message = self.FishingService.get_my_items_message(user_id)
        yield event.plain_result(message)

    @filter.command("gsend")
    async def global_send(self, event: AstrMessageEvent):
        """
        [管理员] 全局发放指令 (使用手动wxid判断)。
        格式: /gsend <目标> <物品名> <数量>
        ... (帮助文档不变)
        """

        # <<< 新增代码开始：手动进行wxid权限检查 >>>
        sender_id = event.get_sender_id()

        # 这里的 self.MANUAL_ADMIN_WXIDS 是我们在 __init__ 方法中定义的列表
        # !! 重要：请确保您已在 __init__ 方法中定义并填写真实的管理员wxid
        if sender_id not in getattr(self, 'MANUAL_ADMIN_WXIDS', []):
            yield event.plain_result("❌ [手动校验] 你没有权限使用此命令。")
            return
        # <<< 新增代码结束 >>>

        # --- 后续的指令解析和执行逻辑完全不变 ---
        args = event.message_str.split()
        if len(args) < 4:
            help_text = "格式错误！\n\n" + self.global_send.__doc__
            yield event.plain_result(help_text)
            return
        target_str = args[1]
        item_name = args[2]
        try:
            quantity = int(args[3])
            if quantity <= 0:
                yield event.plain_result("❌ 数量必须是正整数。")
                return
        except ValueError:
            yield event.plain_result("❌ 数量必须是一个有效的数字。")
            return

        yield event.plain_result(f"⚙️ [手动校验通过] 正在执行发放任务...\n目标: {target_str}\n物品: {item_name} x {quantity}")
        await asyncio.sleep(1)

        result = self.FishingService.global_send_item(target_str, item_name, quantity)

        if result['success']:
            yield event.plain_result(f"✅ {result['message']}")
        else:
            yield event.plain_result(f"❌ 发放失败: {result['message']}")

    @filter.command("钓鱼帮助", alias={"钓鱼指南"})
    async def show_help(self, event: AstrMessageEvent):
        """显示钓鱼游戏帮助信息"""
        prefix = """前言：使用/注册指令即可开始，鱼饵是一次性的（每次钓鱼随机使用），可以一次买多个鱼饵例如：/购买鱼饵 3 200。鱼竿购买后可以通过/鱼
竿查看，如果你嫌钓鱼慢，可以玩玩/擦弹 金币数量，随机获得0-10倍收益"""
        message = f"""【🎣 钓鱼系统帮助】
    📋 基础命令:
     - /开启钓鱼生涯: 开启修仙钓鱼生涯
     - /钓鱼: 进行一次钓鱼(消耗10灵石，3分钟CD)

    🎒 背包相关:
     - /鱼塘: 查看鱼类背包
     - /偷鱼 @用户: 偷取指定用户的鱼
     - /鱼塘容量: 查看当前鱼塘容量
     - /升级鱼塘: 升级鱼塘容量
     - /鱼饵: 查看鱼饵背包
     - /鱼竿: 查看鱼竿背包
     - /鱼饰: 查看饰品背包

    🏪 商店与购买:
     - /系统鱼店: 查看可购买的物品
     - /购买鱼饵 ID [数量]: 购买指定ID的鱼饵，可选择数量
     - /购买鱼竿 ID: 购买指定ID的鱼竿
     - /使用鱼饵 ID: 使用指定ID的鱼饵
     - /使用鱼竿 ID: 装备指定ID的鱼竿
     - /出售鱼竿 ID: 出售指定ID的鱼竿
     - /使用鱼饰 ID: 装备指定ID的饰品
     - /出售鱼饰 ID: 出售指定ID的饰品

    🏪 市场与购买:
        - /鱼市: 查看市场中的物品
        - /上架鱼饰 ID: 上架指定ID的饰品到市场
        - /上架鱼竿 ID: 上架指定ID的鱼竿到市场
        - /鱼市购买 ID: 购买市场中的指定物品ID

    🎒 道具Item:
     - /打开鱼箱: 打开沉没的宝箱
     - /打开鱼箱 [数量]

    💰 出售鱼类:
     - /鱼全卖: 出售背包中所有鱼
     - /卖鱼稀有度 <1-5>: 出售特定稀有度的鱼


    🎮 抽卡系统:
     - /鱼乐乐 ID: 进行单次鱼乐乐
     - /十鱼乐 ID: 进行十连鱼乐乐
     - /查看鱼乐乐 ID: 查看鱼乐乐详细信息和概率
     - /鱼乐乐记录: 查看鱼乐乐历史记录

     ⚔️ 成长与PK:
     - /鱼竿强化: 提升锻造等级
     - /鱼竿强化查询: 查看强化属性

    🔧 其他功能:
     - /自动钓鱼: 开启/关闭自动钓鱼功能
     - /鱼鱼排行榜: 查看钓鱼排行榜
     - /鱼类图鉴: 查看所有鱼的详细信息
     - /查看钓鱼称号: 查看已获得的称号
     - /使用钓鱼称号 ID: 使用指定ID称号
     - /查看钓鱼成就: 查看可达成的成就
     - /钓鱼记录: 查看最近的钓鱼记录
     - /税收记录: 查看税收记录
    """
        # message = prefix + "\n" + message

        yield event.plain_result(message)

    @filter.command("鱼类图鉴", alias={"鱼图鉴", "图鉴"})
    async def show_fish_catalog(self, event: AstrMessageEvent):
        """显示所有鱼的图鉴"""
        user_id = event.get_sender_id()

        # 检查用户是否注册
        if not self.FishingService.is_registered(user_id):
            yield event.plain_result("请先注册才能使用此功能")
            return

        # 调用服务获取所有鱼类信息
        cursor = self.FishingService.db._get_connection().cursor()
        cursor.execute("""
            SELECT fish_id, name, description, rarity, base_value, min_weight, max_weight
            FROM fish
            ORDER BY rarity DESC, base_value DESC
        """)
        fishes = cursor.fetchall()

        if not fishes:
            yield event.plain_result("鱼类图鉴中暂无数据")
            return

        # 按稀有度分组
        fishes_by_rarity = {}
        for fish in fishes:
            rarity = fish['rarity']
            if rarity not in fishes_by_rarity:
                fishes_by_rarity[rarity] = []
            fishes_by_rarity[rarity].append(dict(fish))

        # 构建消息
        message = "【📖 鱼类图鉴】\n\n"

        for rarity in sorted(fishes_by_rarity.keys(), reverse=True):
            message += f"★ 稀有度 {rarity} ({'★' * rarity}):\n"

            # 只显示每个稀有度的前5条，太多会导致消息过长
            fish_list = fishes_by_rarity[rarity][:5]
            for fish in fish_list:
                message += f"- {fish['name']} (💰 价值: {fish['base_value']}金币)\n"
                if fish['description']:
                    message += f"  📝 {fish['description']}\n"
                message += f"  ⚖️ 重量范围: {fish['min_weight']}~{fish['max_weight']}g\n"

            # 如果该稀有度鱼类超过5种，显示省略信息
            if len(fishes_by_rarity[rarity]) > 5:
                message += f"  ... 等共{len(fishes_by_rarity[rarity])}种\n"

            message += "\n"

        # 添加总数统计和提示
        total_fish = sum(len(group) for group in fishes_by_rarity.values())
        message += f"📊 图鉴收录了共计 {total_fish} 种鱼类。\n"
        message += "💡 提示：钓鱼可能会钓到鱼以外的物品，比如各种特殊物品和神器！"

        yield event.plain_result(message)

    @filter.command("不开放擦弹", alias={"wipe"})
    async def do_wipe_bomb(self, event: AstrMessageEvent):
        """进行擦弹，投入金币并获得随机倍数的奖励"""
        user_id = event.get_sender_id()

        # 检查用户是否注册
        if not self.FishingService.is_registered(user_id):
            yield event.plain_result("请先注册才能使用此功能")
            return

        # 解析参数
        args = event.message_str.split(' ')

        if len(args) < 2:
            yield event.plain_result("💸 请指定要投入的金币数量，例如：擦弹 100")
            return

        try:
            amount = int(args[1])
            if amount <= 0:
                yield event.plain_result("⚠️ 投入金币必须大于0")
                return

            # 调用服务执行擦弹操作
            result = self.FishingService.perform_wipe_bomb(user_id, amount)

            # 替换普通文本消息为带表情的消息
            original_message = result.get("message", "擦弹失败，请稍后再试")

            if result.get("success"):
                # 尝试从结果中提取倍数和奖励
                multiplier = result.get("multiplier", 0)
                reward = result.get("reward", 0)
                profit = reward - amount

                if multiplier > 0:
                    # 根据倍数和盈利情况选择不同的表情
                    if multiplier >= 2:
                        if profit > 0:
                            message = f"🎰 大成功！你投入 {amount} 灵石，获得了 {multiplier}倍 回报！\n💰 奖励: {reward} 灵石 (盈利: +{profit})"
                        else:
                            message = f"🎰 你投入 {amount} {get_coins_name()}，获得了 {multiplier}倍 回报！\n💰 奖励: {reward} {get_coins_name()} (亏损: {profit})"
                    else:
                        if profit > 0:
                            message = f"🎲 你投入 {amount} {get_coins_name()}，获得了 {multiplier}倍 回报！\n💰 奖励: {reward} {get_coins_name()} (盈利: +{profit})"
                        else:
                            message = f"💸 你投入 {amount} {get_coins_name()}，获得了 {multiplier}倍 回报！\n💰 奖励: {reward} {get_coins_name()} (亏损: {profit})"
                else:
                    message = f"🎲 {original_message}"
            else:
                # 如果是失败消息
                if "不足" in original_message:
                    message = f"💸 金币不足，无法进行擦弹"
                else:
                    message = f"❌ {original_message}"

            yield event.plain_result(message)

        except ValueError:
            yield event.plain_result("⚠️ 请输入有效的金币数量")

    @filter.command("不开放擦弹历史")
    async def show_wipe_history(self, event: AstrMessageEvent):
        """显示用户的擦弹历史记录"""
        user_id = event.get_sender_id()

        # 检查用户是否注册
        if not self.FishingService.is_registered(user_id):
            yield event.plain_result("请先注册才能使用此功能")
            return


        # 获取擦弹历史
        result = self.FishingService.get_wipe_bomb_history(user_id)

        if not result.get("success"):
            yield event.plain_result("❌ 获取擦弹历史失败")
            return

        records = result.get("records", [])

        if not records:
            yield event.plain_result("📝 你还没有进行过擦弹操作")
            return

        # 构建消息
        message = "【📊 擦弹历史记录】\n\n"

        for idx, record in enumerate(records, 1):
            timestamp = record.get('timestamp', '未知时间')
            contribution = record.get('contribution_amount', 0)
            multiplier = record.get('reward_multiplier', 0)
            reward = record.get('reward_amount', 0)
            profit = record.get('profit', 0)

            # 根据盈亏状况显示不同表情
            if profit > 0:
                profit_text = f"📈 盈利 {profit}"
                if multiplier >= 2:
                    emoji = "🎉"  # 高倍率盈利用庆祝表情
                else:
                    emoji = "✅"  # 普通盈利用勾选表情
            else:
                profit_text = f"📉 亏损 {-profit}"
                emoji = "💸"  # 亏损用钱飞走表情

            message += f"{idx}. ⏱️  {timestamp}\n"
            message += f"   {emoji} 投入: {contribution} {get_coins_name()}，获得 {multiplier}倍 ({reward} {get_coins_name()})\n"
            message += f"   {profit_text}\n"

        # 添加是否可以再次擦弹的提示
        can_wipe_today = result.get("available_today", False)
        if can_wipe_today:
            message += "\n🎮 今天你还可以进行擦弹"
        else:
            message += "\n⏳ 今天你已经进行过擦弹了，明天再来吧"

        yield event.plain_result(message)

    @filter.command("查看钓鱼称号", alias={"称号", "titles"})
    async def show_titles(self, event: AstrMessageEvent):
        """显示用户已获得的称号"""
        user_id = event.get_sender_id()

        # 检查用户是否注册
        if not self.FishingService.is_registered(user_id):
            yield event.plain_result("请先注册才能使用此功能")
            return

        # 获取用户称号
        result = self.FishingService.get_user_titles(user_id)

        if not isinstance(result, dict) or not result.get("success", False):
            yield event.plain_result("获取称号信息失败")
            return

        titles = result.get("titles", [])

        if not titles:
            yield event.plain_result("🏆 你还没有获得任何称号，努力完成成就以获取称号吧！")
            return

        # 构建消息
        message = "【🏆 已获得称号】\n\n"

        for title in titles:
            message += f"ID:{title.get('title_id')} - {title.get('name')}\n"
            if title.get('description'):
                message += f"  📝 {title.get('description')}\n"

        message += "\n💡 提示：完成特定成就可以获得更多称号！"

        yield event.plain_result(message)

    @filter.command("使用钓鱼称号")
    async def use_title(self, event: AstrMessageEvent):
        """使用指定称号"""
        user_id = event.get_sender_id()
        args = event.message_str.split(' ')

        # 检查用户是否注册
        if not self.FishingService.is_registered(user_id):
            yield event.plain_result("请先注册才能使用此功能")
            return

        if len(args) < 2:
            yield event.plain_result("请指定要使用的称号ID，例如：/使用称号 1")
            return

        try:
            title_id = int(args[1])
            result = self.FishingService.use_title(user_id, title_id)

            if result.get("success"):
                yield event.plain_result(result.get("message", "使用称号成功！"))
            else:
                yield event.plain_result(result.get("message", "使用称号失败"))
        except ValueError:
            yield event.plain_result("请输入有效的称号ID")

    @filter.command("查看钓鱼成就", alias={"成就", "achievements"})
    async def show_achievements(self, event: AstrMessageEvent):
        """显示用户的成就进度"""
        user_id = event.get_sender_id()

        # 检查用户是否注册
        if not self.FishingService.is_registered(user_id):
            yield event.plain_result("请先注册才能使用此功能")
            return

        # 获取成就进度（这里需要修改FishingService添加获取成就进度的方法）
        # 临时解决方案：直接从数据库查询
        try:
            user_progress = self.FishingService.db.get_user_achievement_progress(user_id)

            if not user_progress:
                # 如果没有进度记录，至少显示一些可用的成就
                cursor = self.FishingService.db._get_connection().cursor()
                cursor.execute("""
                    SELECT achievement_id, name, description, target_type, target_value, reward_type, reward_value
                    FROM achievements
                    LIMIT 10
                """)
                achievements = [dict(row) for row in cursor.fetchall()]

                message = "【🏅 成就列表】\n\n"
                message += "你还没有开始任何成就的进度，这里是一些可以完成的成就：\n\n"

                for ach in achievements:
                    message += f"- {ach['name']}: {ach['description']}\n"
                    message += f"  🎯 目标: {ach['target_value']} ({ach['target_type']})\n"
                    reward_text = f"{ach['reward_type']} (ID: {ach['reward_value']})"
                    message += f"  🎁 奖励: {reward_text}\n"

                yield event.plain_result(message)
                return

            # 筛选出有进度的成就和完成但未领取奖励的成就
            in_progress = []
            completed = []

            for progress in user_progress:
                is_completed = progress.get('completed_at') is not None
                is_claimed = progress.get('claimed_at') is not None

                if is_completed and not is_claimed:
                    completed.append(progress)
                elif progress.get('current_progress', 0) > 0:
                    in_progress.append(progress)

            # 构建消息
            message = "【🏅 成就进度】\n\n"

            if completed:
                message += "✅ 已完成的成就:\n"
                for ach in completed:
                    message += f"- {ach['name']}: {ach['description']}\n"
                    reward_text = f"{ach['reward_type']} (ID: {ach['reward_value']})"
                    message += f"  🎁 奖励: {reward_text}\n"
                message += "\n"

            if in_progress:
                message += "⏳ 进行中的成就:\n"
                for ach in in_progress:
                    progress_percent = min(100, int(ach['current_progress'] / ach['target_value'] * 100))
                    message += f"- {ach['name']} ({progress_percent}%)\n"
                    message += f"  📝 {ach['description']}\n"
                    message += f"  📊 进度: {ach['current_progress']}/{ach['target_value']}\n"
                message += "\n"

            if not completed and not in_progress:
                message += "你还没有进行中的成就，继续钓鱼和使用其他功能来完成成就吧！\n"

            message += "💡 提示：完成成就可以获得各种奖励，包括金币、称号、特殊物品等！"

            yield event.plain_result(message)
        except Exception as e:
            logger.error(f"获取成就进度失败: {e}")
            yield event.plain_result("获取成就进度时出错，请稍后再试")

    @filter.command("钓鱼记录", "查看记录")
    async def fishing_records(self, event: AstrMessageEvent):
        """查看钓鱼记录"""
        user_id = event.get_sender_id()

        result = self.FishingService.get_user_fishing_records(user_id)
        if not result["success"]:
            yield event.plain_result(result["message"])
            return

        records = result["records"]
        if not records:
            yield event.plain_result("📝 你还没有任何钓鱼记录，快去钓鱼吧！")
            return

        # 格式化记录显示
        message = "【📝 最近钓鱼记录】\n"
        for idx, record in enumerate(records, 1):
            time_str = record.get('timestamp', '未知时间')
            if isinstance(time_str, str) and len(time_str) > 16:
                time_str = time_str[:16]  # 简化时间显示

            fish_name = record.get('fish_name', '未知鱼类')
            rarity = record.get('rarity', 0)
            weight = record.get('weight', 0)
            value = record.get('value', 0)

            rod_name = record.get('rod_name', '无鱼竿')
            bait_name = record.get('bait_name', '无鱼饵')

            # 稀有度星星显示
            rarity_stars = '★' * rarity

            # 判断是否为大型鱼
            king_size = "👑 " if record.get('is_king_size', 0) else ""

            message += f"{idx}. ⏱️  {time_str} {king_size}{fish_name} {rarity_stars}\n"
            message += f"   ⚖️ 重量: {weight}g | 💰 价值: {value}{get_coins_name()}\n"
            message += f"   🔧 装备: {rod_name} | 🎣 鱼饵: {bait_name}\n"
        yield event.plain_result(message)

    @filter.command("不开放用户列表")
    async def show_all_users(self, event: AstrMessageEvent):
        """显示所有注册用户的信息"""
        try:
            # 获取所有用户ID
            all_users = self.FishingService.db.get_all_users()

            if not all_users:
                yield event.plain_result("📊 暂无注册用户")
                return

            # 构建消息
            message = "【👥 用户列表】\n\n"

            # 获取每个用户的详细信息
            for idx, user_id in enumerate(all_users, 1):
                # 获取用户基本信息
                user_stats = self.FishingService.db.get_user_fishing_stats(user_id)
                user_currency = self.FishingService.db.get_user_currency(user_id)

                if not user_stats or not user_currency:
                    continue

                # 获取用户昵称
                cursor = self.FishingService.db._get_connection().cursor()
                cursor.execute("SELECT nickname FROM users WHERE user_id = ?", (user_id,))
                result = cursor.fetchone()
                nickname = result[0] if result else "未知用户"

                # 获取用户装备信息
                equipment = self.FishingService.db.get_user_equipment(user_id)
                rod_name = equipment.get("rod", {}).get("name", "无鱼竿") if equipment.get("success") else "无鱼竿"

                # 获取用户鱼塘信息
                fish_inventory = self.FishingService.db.get_user_fish_inventory(user_id)
                total_fish = sum(fish.get("quantity", 0) for fish in fish_inventory)

                # 格式化用户信息
                message += f"{idx}. 👤 {nickname} (ID: {user_id})\n"
                message += f"   💰 {get_coins_name()}: {user_currency.get('coins', 0)}\n"
                message += f"   🎣 钓鱼次数: {user_stats.get('total_fishing_count', 0)}\n"
                message += f"   🐟 鱼塘数量: {total_fish}\n"
                message += f"   ⚖️ 总重量: {user_stats.get('total_weight_caught', 0)}g\n"
                message += f"   🎯 当前装备: {rod_name}\n"
                message += "\n"

            # 添加统计信息
            total_users = len(all_users)
            message += f"📊 总用户数: {total_users}"

            yield event.plain_result(message)
        except Exception as e:
            logger.error(f"获取用户列表失败: {e}")
            yield event.plain_result(f"❌ 获取用户列表时出错，请稍后再试！错误信息：{str(e)}")

    @filter.command("鱼乐乐记录", alias={"gacha_history"})
    async def show_gacha_history(self, event: AstrMessageEvent):
        """查看用户的抽卡记录"""
        user_id = event.get_sender_id()

        # 检查用户是否注册
        if not self.FishingService.is_registered(user_id):
            yield event.plain_result("请先注册才能使用此功能")
            return

        # 获取抽卡记录
        records = self.FishingService.db.get_user_gacha_records(user_id)

        if not records:
            yield event.plain_result("📝 你还没有任何抽卡记录，快去抽卡吧！")
            return

        # 构建消息
        message = "【🎮 抽卡记录】\n\n"

        for idx, record in enumerate(records, 1):
            time_str = record.get('timestamp', '未知时间')
            if isinstance(time_str, str) and len(time_str) > 16:
                time_str = time_str[:16]  # 简化时间显示

            item_name = record.get('item_name', '未知物品')
            rarity = record.get('rarity', 1)
            quantity = record.get('quantity', 1)

            # 稀有度星星显示
            rarity_stars = '★' * rarity

            # 根据稀有度选择表情
            rarity_emoji = "✨" if rarity >= 4 else "🌟" if rarity >= 3 else "⭐" if rarity >= 2 else "🔹"

            message += f"{idx}. ⏱️  {time_str}\n"
            message += f"   {rarity_emoji} {item_name} {rarity_stars}\n"
            if quantity > 1:
                message += f"   📦 数量: x{quantity}\n"

        yield event.plain_result(message)

    @filter.command("鱼饰", alias={"accessories"})
    async def show_accessories(self, event: AstrMessageEvent):
        """显示用户拥有的饰品"""
        user_id = event.get_sender_id()

        # 检查用户是否注册
        if not self.FishingService.is_registered(user_id):
            yield event.plain_result("请先注册才能使用此功能")
            return

        # 获取用户饰品
        accessories = self.FishingService.get_user_accessories(user_id)

        if not accessories["success"]:
            yield event.plain_result(accessories["message"])
            return

        user_accessories = accessories["accessories"]

        if not user_accessories:
            yield event.plain_result("🎭 你没有任何饰品，可以通过抽卡获得！")
            return

        # 获取当前装备的饰品
        equipped = self.FishingService.get_user_equipped_accessory(user_id)
        equipped_id = equipped["accessory"]["accessory_instance_id"] if equipped["accessory"] else None

        # 构建消息
        message = "【🎭 饰品背包】\n\n"

        for accessory in user_accessories:
            accessory_instance_id = accessory["accessory_instance_id"]
            is_equipped = accessory_instance_id == equipped_id

            message += f"ID:{accessory_instance_id} - {accessory['name']} (稀有度:{'★' * accessory['rarity']})"
            if is_equipped:
                message += " [已装备]"
            message += "\n"

            if accessory["description"]:
                message += f"  📝 描述: {accessory['description']}\n"

            # 显示属性加成
            if accessory["bonus_fish_quality_modifier"] != 1.0:
                message += f"  ✨ 品质加成: +{(accessory['bonus_fish_quality_modifier'] - 1) * 100:.0f}%\n"
            if accessory["bonus_fish_quantity_modifier"] != 1.0:
                message += f"  📊 数量加成: +{(accessory['bonus_fish_quantity_modifier'] - 1) * 100:.0f}%\n"
            if accessory["bonus_rare_fish_chance"] > 0:
                message += f"  🌟 稀有度加成: +{accessory['bonus_rare_fish_chance'] * 100:.0f}%\n"
            if accessory["other_bonus_description"]:
                message += f"  🔮 特殊效果: {accessory['other_bonus_description']}\n"

        message += "\n💡 使用「使用饰品 ID」命令装备饰品"
        yield event.plain_result(message)

    @filter.command("使用鱼饰", alias={"useaccessory"})
    async def use_accessory(self, event: AstrMessageEvent):
        """装备指定的饰品"""
        user_id = event.get_sender_id()
        args = event.message_str.split(' ')

        # 检查用户是否注册
        if not self.FishingService.is_registered(user_id):
            yield event.plain_result("请先注册才能使用此功能")
            return

        if len(args) < 2:
            yield event.plain_result("⚠️ 请指定要装备的饰品ID")
            return

        try:
            accessory_instance_id = int(args[1])
            result = self.FishingService.equip_accessory(user_id, accessory_instance_id)

            # 增加表情符号
            original_message = result.get("message", "装备饰品失败！")
            if "成功" in original_message:
                message = f"🎭 {original_message}"
            else:
                message = f"❌ {original_message}"

            yield event.plain_result(message)
        except ValueError:
            yield event.plain_result("⚠️ 请输入有效的饰品ID")

    @filter.command("出售鱼饰", alias={"sellaccessory"})
    async def sell_accessory(self, event: AstrMessageEvent):
        """出售指定的饰品"""
        user_id = event.get_sender_id()
        args = event.message_str.split(' ')

        # 检查用户是否注册
        if not self.FishingService.is_registered(user_id):
            yield event.plain_result("请先注册才能使用此功能")
            return

        if len(args) < 2:
            yield event.plain_result("⚠️ 请指定要出售的饰品ID")
            return

        try:
            accessory_instance_id = int(args[1])
            result = self.FishingService.sell_accessory(user_id, accessory_instance_id)

            # 增加表情符号
            original_message = result.get("message", "出售饰品失败！")
            if "成功" in original_message:
                message = f"💰 {original_message}"
            else:
                message = f"❌ {original_message}"

            yield event.plain_result(message)
        except ValueError:
            yield event.plain_result("⚠️ 请输入有效的饰品ID")

    @filter.command("鱼市", alias={"market"})
    async def show_market(self, event: AstrMessageEvent):
        """显示商店中的所有商品"""
        user_id = event.get_sender_id()

        # 检查用户是否注册
        if not self.FishingService.is_registered(user_id):
            yield event.plain_result("请先注册才能使用此功能")
            return

        # 获取市场商品
        market_items = self.FishingService.get_market_items()

        if not market_items["success"]:
            yield event.plain_result("❌ 获取市场商品失败，请稍后再试")
            return
        rods = market_items.get("rods", [])
        accessories = market_items.get("accessories", [])
        if not rods and not accessories:
            yield event.plain_result("🛒 市场中暂无商品，欢迎稍后再来！")
            return
        # 构建消息
        message = "【🛒 市场】\n\n"
        if rods:
            message += "【🎣 鱼竿】\n"
                       #返回市场上架的饰品信息，包括市场ID、用户昵称、饰品ID、饰品名称、数量、价格和上架时间
            for rod in rods:
                message += f"ID:{rod['market_id']} - {rod['rod_name']} (价格: {rod['price']} {get_coins_name()})\n"
                message += f"  📝 上架者: {rod['nickname']} | 数量: {rod['quantity']} | 上架时间: {rod['listed_at']}\n"
                if rod.get('description'):
                    message += f"  📝 描述: {rod['description']}\n"
            message += "\n"
        if accessories:
            message += "【🎭 饰品】\n"
            for accessory in accessories:
                message += f"ID:{accessory['market_id']} - {accessory['accessory_name']} (价格: {accessory['price']} {get_coins_name()})\n"
                message += f"  📝 上架者: {accessory['nickname']} | 数量: {accessory['quantity']} | 上架时间: {accessory['listed_at']}\n"
                if accessory.get('description'):
                    message += f"  📝 描述: {accessory['description']}\n"
            message += "\n"
        message += "💡 使用「购买 ID」命令购买商品"
        yield event.plain_result(message)

    @filter.command("鱼市购买", alias={"buy"})
    async def buy_item(self, event: AstrMessageEvent):
        """购买市场上的商品"""
        user_id = event.get_sender_id()
        args = event.message_str.split(' ')

        # 检查用户是否注册
        if not self.FishingService.is_registered(user_id):
            yield event.plain_result("请先注册才能使用此功能")
            return

        if len(args) < 2:
            yield event.plain_result("⚠️ 请指定要购买的商品ID，例如：/购买 1")
            return

        try:
            market_id = int(args[1])
            result = self.FishingService.buy_item_from_market(user_id, market_id)

            if result["success"]:
                yield event.plain_result(f"✅ {result['message']}")
            else:
                yield event.plain_result(f"❌ {result['message']}")
        except ValueError:
            yield event.plain_result("⚠️ 请输入有效的商品ID")

    @filter.command("上架鱼饰", alias={"put_accessory_on_sale"})
    async def put_accessory_on_sale(self, event: AstrMessageEvent):
        """将饰品的ID和价格上架到商店"""
        user_id = event.get_sender_id()
        args = event.message_str.split(' ')

        # 检查用户是否注册
        if not self.FishingService.is_registered(user_id):
            yield event.plain_result("请先注册才能使用此功能")
            return

        if len(args) < 3:
            yield event.plain_result("⚠️ 请指定饰品ID和上架价格，例如：/上架饰品 1 100")
            return

        try:
            accessory_instance_id = int(args[1])
            price = int(args[2])

            if price <= 0:
                yield event.plain_result("⚠️ 上架价格必须大于0")
                return

            result = self.FishingService.put_accessory_on_sale(user_id, accessory_instance_id, price)

            if result["success"]:
                yield event.plain_result(f"✅ 成功将饰品 ID {accessory_instance_id} 上架到市场，价格为 {price} {get_coins_name()}")
            else:
                yield event.plain_result(f"❌ {result['message']}")
        except ValueError:
            yield event.plain_result("⚠️ 请输入有效的饰品ID和价格")

    # 将鱼竿上架到商店
    @filter.command("上架鱼竿")
    async def put_rod_on_sale(self, event: AstrMessageEvent):
        """将鱼竿的ID和价格上架到商店"""
        user_id = event.get_sender_id()
        args = event.message_str.split(' ')

        # 检查用户是否注册
        if not self.FishingService.is_registered(user_id):
            yield event.plain_result("请先注册才能使用此功能")
            return

        if len(args) < 3:
            yield event.plain_result("⚠️ 请指定鱼竿ID和上架价格，例如：/上架鱼竿 1 100")
            return

        try:
            rod_instance_id = int(args[1])
            price = int(args[2])

            if price <= 0:
                yield event.plain_result("⚠️ 上架价格必须大于0")
                return

            result = self.FishingService.put_rod_on_sale(user_id, rod_instance_id, price)

            if result["success"]:
                yield event.plain_result(f"✅ 成功将鱼竿 ID {rod_instance_id} 上架到市场，价格为 {price} {get_coins_name()}")
            else:
                yield event.plain_result(f"❌ {result['message']}")
        except ValueError:
            yield event.plain_result("⚠️ 请输入有效的鱼竿ID和价格")

    @filter.command("税收记录")
    async def show_tax_records(self, event: AstrMessageEvent):
        """显示税收记录"""
        user_id = event.get_sender_id()

        # 检查用户是否注册
        if not self.FishingService.is_registered(user_id):
            yield event.plain_result("请先注册才能使用此功能")
            return

        # 获取税收记录
        records = self.FishingService.db.get_tax_records(user_id)

        if not records:
            yield event.plain_result("📝 你还没有任何税收记录")
            return

        # 构建消息
        message = "【📊 税收记录】\n\n"

        for idx, record in enumerate(records, 1):
            time_str = record.get('timestamp', '未知时间')
            if isinstance(time_str, str) and len(time_str) > 16:
                time_str = time_str[:16]
            tax_amount = record.get('tax_amount', 0)
            reason = record.get('reason', '无')
            message += f"{idx}. ⏱️  {time_str}\n"
            message += f"   💰 税收金额: {tax_amount} {get_coins_name()}\n"
            message += f"   📝 原因: {reason}\n"
        yield event.plain_result(message)

    @filter.command("鱼塘容量")
    async def show_fish_inventory_capacity(self, event: AstrMessageEvent):
        """显示用户鱼塘的容量"""
        user_id = event.get_sender_id()

        # 检查用户是否注册
        if not self.FishingService.is_registered(user_id):
            yield event.plain_result("请先注册才能使用此功能")
            return

        # 获取用户鱼塘容量
        capacity = self.FishingService.get_user_fish_inventory_capacity(user_id)

        if not capacity["success"]:
            yield event.plain_result(capacity["message"])
            return

        current_capacity = capacity["current_count"]
        max_capacity = capacity["capacity"]

        message = f"🐟 你的鱼塘当前容量（{get_fish_pond_inventory_grade(max_capacity)}）: {current_capacity}/{max_capacity} 只鱼"
        yield event.plain_result(message)

    @filter.command("升级鱼塘")
    async def upgrade_fish_inventory(self, event: AstrMessageEvent):
        """升级用户的鱼塘容量"""
        user_id = event.get_sender_id()

        # 检查用户是否注册
        if not self.FishingService.is_registered(user_id):
            yield event.plain_result("请先注册才能使用此功能")
            return

        result = self.FishingService.upgrade_fish_inventory(user_id)

        if result["success"]:
            yield event.plain_result(f"✅ 成功升级鱼塘！当前容量: {result['new_capacity']} , 💴花费: {result['cost']} {get_coins_name()}")
        else:
            yield event.plain_result(f"❌ {result['message']}")

    @filter.regex(r".*[偷][鱼].*")
    #@filter.command("偷鱼", alias={"steal_fish"})
    async def steal_fish(self, event: AstrMessageEvent):
        """尝试偷取其他用户的鱼"""
        #logger.info(dir(event))
        user_id = event.get_sender_id()
        logger.info(user_id + "要偷鱼")

        # 检查用户是否注册
        if not self.FishingService.is_registered(user_id):
            yield event.plain_result("请先注册才能使用此功能")
            return

        message_obj = event.message_obj
        logger.info(message_obj)
        target_id = None
        if hasattr(message_obj, 'raw_message'):

            # 2. 获取 raw_message 属性，它应该是一个字典
            raw_message_dict = message_obj.raw_message

            # 3. 检查 raw_message_dict 是不是一个字典，并且检查 'msg_source' 这个“键”是否存在于字典中
            if isinstance(raw_message_dict, dict) and 'msg_source' in raw_message_dict:

                # 4. 从字典中获取 msg_source 的值
                msg_source = raw_message_dict['msg_source']
                logger.info(f"成功获取 msg_source: {msg_source}")
                # 5. 在 msg_source 字符串上执行正则匹配
                match = re.search(r"<atuserlist>(.*?)</atuserlist>", msg_source)

                if match:
                    # 4. ★★★【核心逻辑升级】★★★
                    inner_content = match.group(1).strip() # 获取括号内的内容，并去除首尾空白
                    # 4.1. 如果内容被 CDATA 包裹，则剥去 CDATA 外壳
                    if inner_content.startswith('<![CDATA[') and inner_content.endswith(']]>'):
                        # 提取 CDATA 内部的真正内容
                        wxids_string = inner_content[9:-3] # 从第9个字符开始，到倒数第3个字符结束
                    else:
                        # 如果没有 CDATA，内容就是我们想要的
                        wxids_string = inner_content

                    logger.info(f"清洗后的 wxids 字符串: '{wxids_string}'")
                    # 4.2. 用逗号分割，并过滤掉所有空字符串
                    # list comprehension: [item for item in list if condition]
                    wxid_list = [wxid for wxid in wxids_string.split(',') if wxid]

                    logger.info(f"分割并过滤后的 wxid 列表: {wxid_list}")
                    # 4.3. 如果列表不为空，则安全地取第一个元素
                    if wxid_list:
                        target_id = wxid_list[0]
                        logger.info(f"成功提取到最终目标 target_id: {target_id}")
                    else:
                        logger.warning("在 <atuserlist> 中解析出了空的 wxid 列表")
            else:
                logger.warning("属性 'raw_message' 不是字典或其中不包含 'msg_source' 键")
        else:
            logger.warning("在 'AstrBotMessage' 对象上未找到 'raw_message' 属性")
                      #    #     break
        if target_id is None:
            yield event.plain_result("请在消息中@要偷鱼的用户")
            return

        result = self.FishingService.steal_fish(user_id, target_id)
        if result["success"]:
            yield event.plain_result(f"✅ {result['message']}")
        else:
            yield event.plain_result(f"❌ {result['message']}")

    # v-- 在 XiuxianPlugin 类的末尾追加以下新方法 --v
    @filter.command("手动开启拍卖")
    async def admin_start_auction_cmd(self, event: AstrMessageEvent):
        # 权限检查
        if event.get_sender_id() not in self.MANUAL_ADMIN_WXIDS:
            msg = "汝非天选之人，无权执此法旨！"
            async for r in self._send_response(event, msg): yield r
            return

        args = event.message_str.split()
        specified_id = None
        if len(args) > 1:
            try:
                specified_id = int(args[1])
            except ValueError:
                msg = "指令格式错误！请使用：手动开启拍卖 [可选的物品ID]"
                async for r in self._send_response(event, msg): yield r
                return

        # 调用任务方法
        # 使用 await 等待结果，因为我们希望管理员能立刻看到反馈
        result = await self.scheduler._start_auction_task(specified_item_id=specified_id)

        # 将结果发送给操作的管理员
        async for r in self._send_response(event, result['message']):
            yield r

    # 如果你需要一个文本版的“我的状态”，可以添加如下指令
    @filter.command("我的面板") # 新指令名，避免与你的现有指令冲突
    @command_lock
    async def my_panel_status_cmd(self, event: AstrMessageEvent):
        """显示核心战斗面板属性"""
        await self._update_active_groups(event)
        user_id = event.get_sender_id()
        is_user, _, msg_check = check_user(self.XiuXianService, user_id)
        if not is_user:
            async for r in self._send_response(event, msg_check): yield r
            return

        user_real_info = self.XiuXianService.get_user_real_info(user_id)
        if not user_real_info:
            msg = "道友的状态信息获取失败，请稍后再试或联系管理员。"
            async for r in self._send_response(event, msg): yield r
            return

        user_name = user_real_info.get('user_name', "道友")
        hp = user_real_info.get('hp', 0)
        max_hp = user_real_info.get('max_hp', 1)
        mp = user_real_info.get('mp', 0)
        max_mp = user_real_info.get('max_mp', 1)
        atk = user_real_info.get('atk', 0)

        crit_rate_percent = format_percentage(user_real_info.get('crit_rate', 0.05))
        crit_damage_percent = format_percentage(user_real_info.get('crit_damage', 0.5), plus_sign=True)
        defense_rate_percent = format_percentage(user_real_info.get('defense_rate', 0.0))

        atk_practice_level = user_real_info.get('atk_practice_level', 0)
        atk_practice_buff_per_level = self.xiu_config.atk_practice_buff_per_level
        atk_practice_display = f"{atk_practice_level}级 (攻击加成: {format_percentage(atk_practice_level * atk_practice_buff_per_level)})"


        status_msg = f"""
道号：{user_name}
气血：{hp}/{max_hp}
真元：{mp}/{max_mp}
攻击：{atk}
攻击修炼：{atk_practice_display}
暴击率：{crit_rate_percent}
暴击伤害：{crit_damage_percent}
减伤率：{defense_rate_percent}
""".strip()

        async for r in self._send_response(event, status_msg, f"{user_name}的面板"):
            yield r

    @filter.command("后台发放")
    @command_lock
    async def admin_give_item_cmd(self, event: AstrMessageEvent):
        """
        [管理员] 向指定用户发放物品。
        严格格式: /后台发放 <物品名(单个词)> <数量> @用户
        示例: /后台发放 生骨丹 5 @李四
        """
        sender_id = event.get_sender_id()
        if sender_id not in self.MANUAL_ADMIN_WXIDS:
            msg = "❌ 道友权限不足，无法使用此指令。"
            async for r in self._send_response(event, msg): yield r
            return

        args_list = event.message_str.split()
        # args_list[0] 是指令本身，例如 "/后台发放"
        # args_list[1] 应该是物品名
        # args_list[2] 应该是数量
        # args_list[3] (或之后) 应该包含 @用户

        if len(args_list) < 4: # /后台发放 物品名 数量 @用户 (至少4个部分)
            target_user_id = sender_id
        else:
            target_user_id = await self._get_at_user_id(event) # 这个方法需要能从 event 中正确解析出@用户
            if not target_user_id:
                # 如果 _get_at_user_id 依赖于@在特定位置，而简单split后@信息丢失，这里会出问题
                # 再次强调 _get_at_user_id 的健壮性对所有方案都很重要
                msg = "未能从指令中解析出@用户，请确保正确@了目标用户。\n格式: /后台发放 <物品名> <数量> @用户"
                async for r in self._send_response(event, msg, "目标缺失"): yield r
                return

        # 1. 按固定位置取物品名和数量
        item_name = args_list[1]
        quantity_str = args_list[2]

        try:
            quantity = int(quantity_str)
            if quantity <= 0:
                msg = "数量必须是大于0的整数！"
                async for r in self._send_response(event, msg, "数量错误"): yield r
                return
        except ValueError:
            msg = f"数量部分 “{quantity_str}” 不是一个有效的数字！"
            async for r in self._send_response(event, msg, "数量格式错误"): yield r
            return


        is_target_user, target_user_info, msg_target_check = check_user(self.XiuXianService, target_user_id)
        if not is_target_user:
            async for r in self._send_response(event, msg_target_check, "目标无效"): yield r
            return

        logger.info(f"后台发放解析（严格版）：目标用户ID: {target_user_id}, 物品名称: '{item_name}', 数量: {quantity}")

        # 3. 后续的物品查找、类型检查、发放逻辑 (与之前版本一致)
        item_data = None
        item_id_found = None
        # get_all_items() 返回的是 { item_id_str: item_data_dict, ... }
        for item_id_str_key, data_val in self.XiuXianService.items.get_all_items().items():
            if data_val.get('name') == item_name:
                item_data = data_val
                item_id_found = item_id_str_key
                break

        if not item_data:
            msg = f"❌ 未在物品库中找到名为【{item_name}】的物品。"
            async for r in self._send_response(event, msg, "物品不存在"): yield r
            return

        allowed_types = ["功法", "辅修功法", "神通", "法器", "防具", "丹药", "商店丹药", "药材", "合成丹药", "炼丹炉", "聚灵旗"]
        item_actual_type = item_data.get('item_type', '未知')

        if item_actual_type not in allowed_types:
            msg = f"❌ 物品【{item_name}】的类型 ({item_actual_type}) 不允许通过此指令发放。"
            async for r in self._send_response(event, msg, "类型错误"): yield r
            return

        self.XiuXianService.add_item(target_user_id, int(item_id_found), item_actual_type, quantity)

        msg = f"✅ 已成功向用户【{target_user_info.user_name}】发放物品【{item_name}】x {quantity}。"

        async for r in self._send_response(event, msg, "发放结果"): yield r

    @filter.command("物品信息", alias={"查物品", "物品详情"}) # 调整指令名和别名
    @command_lock
    async def get_item_info_cmd(self, event: AstrMessageEvent):
        """
        查询指定物品的详细信息。
        用法: /物品信息 <物品全名>
        示例: /物品信息 离地焰光旗
        """
        await self._update_active_groups(event)

        args = event.message_str.split(maxsplit=1) # 只分割一次，获取指令后的所有内容
        if len(args) < 2 or not args[1].strip():
            msg = "请输入要查询的物品名称！\n用法: /物品信息 <物品全名>"
            async for r in self._send_response(event, msg, "参数错误"): yield r
            return

        item_name_to_query = args[1].strip()

        # 从 Items 实例获取所有物品数据
        all_items_data = self.XiuXianService.items.get_all_items()

        found_item_data = None
        # 精确匹配物品名称
        for item_id, data in all_items_data.items():
            if data.get('name') == item_name_to_query:
                found_item_data = data
                # 为 found_item_data 补充 item_id，因为 format_item_details 可能需要
                found_item_data['_id_for_display'] = item_id
                break

        if not found_item_data:
            # 如果精确匹配失败，可以尝试模糊匹配 (可选)
            possible_matches = []
            for item_id, data in all_items_data.items():
                if item_name_to_query in data.get('name', ''):
                    data['_id_for_display'] = item_id
                    possible_matches.append(data)

            if not possible_matches:
                msg = f"未能找到名为【{item_name_to_query}】的物品。"
                async for r in self._send_response(event, msg, "查询无果"): yield r
                return
            elif len(possible_matches) == 1:
                found_item_data = possible_matches[0]
            else:
                suggestions = "\n".join([f"- {d['name']} (ID: {d['_id_for_display']})" for d in possible_matches[:5]]) # 最多显示5个建议
                msg = f"找到了多个可能的物品，请提供更精确的名称：\n{suggestions}"
                async for r in self._send_response(event, msg, "模糊匹配结果"): yield r
                return


        # 调用格式化函数获取描述
        detailed_desc = format_item_details(found_item_data)

        if not detailed_desc: # 以防万一格式化失败
            detailed_desc = f"无法生成【{item_name_to_query}】的详细描述。"

        async for r in self._send_response(event, detailed_desc, f"物品信息-{item_name_to_query}", font_size=28): # 使用稍小字体
            yield r

    # astrbot_plugin_xiuxian/main.py (在 XiuxianPlugin 类中)
    @filter.command("万法宝鉴", alias={"神通抽奖", "抽神通"})
    @command_lock
    async def gacha_wanfa_baojian_info(self, event: AstrMessageEvent):
        """显示万法宝鉴卡池信息及抽奖指令"""
        await self._update_active_groups(event)
        is_user, _, msg_check = check_user(self.XiuXianService, event.get_sender_id())
        if not is_user:
            async for r in self._send_response(event, msg_check): yield r
            return
    
        pool_id = "wanfa_baojian" # 卡池内部ID
        pool_config = self.xiu_config.gacha_pools_config.get(pool_id)
        if not pool_config:
            async for r in self._send_response(event, "错误：万法宝鉴卡池配置未找到。"): yield r
            return
    
        help_msg = (
            f"⛩️【{pool_config['name']}】⛩️\n"
            f"道友可在此寻求无上神通，窥探天机奥秘！\n\n"
            f"单次探寻：消耗 {pool_config['single_cost']} 灵石\n"
            f"  - 指令：【万法宝鉴单抽】\n"
            f"十次探寻：消耗 {pool_config['multi_cost']} 灵石 (享九折优惠，且必得至少一道神通！)\n"
            f"  - 指令：【万法宝鉴十连"
        )
        async for r in self._send_response(event, help_msg.strip(), "万法宝鉴指引"): yield r
    
    # async def _handle_gacha_pull(self, event: AstrMessageEvent, is_ten_pull: bool):
    #     """统一处理单抽和十连抽的通用逻辑"""
    #
    #     pool_id = "wanfa_baojian" # 卡池内部ID
    #     pool_config = self.xiu_config.gacha_pools_config.get(pool_id)
    #     if not pool_config:
    #         async for r in self._send_response(event, "错误：万法宝鉴卡池配置未找到。"): yield r
    #         return
    #
    #     user_id = event.get_sender_id()
    #     is_user, user_info, msg_check = check_user(self.XiuXianService, user_id)
    #     if not is_user:
    #         async for r in self._send_response(event, msg_check): yield r
    #         return
    #
    #     pool_id = "wanfa_baojian"
    #
    #     # 调用 GachaManager 执行抽奖
    #     # 注意：gacha_manager.perform_gacha 现在应该是一个同步方法，因为它不涉及异步IO
    #     # 如果它是异步的，这里需要 await
    #     # 根据我们之前的设计，GachaManager 的方法都是同步的
    #     try:
    #         # 模拟一些处理时间，让用户感觉机器人正在“抽奖”
    #         processing_msg = "正在沟通天地，演算天机..." if not is_ten_pull else "大法力运转，十方天机尽在掌握..."
    #         async for r_wait in self._send_response(event, processing_msg, "请稍候"): yield r_wait
    #         # await asyncio.sleep(random.uniform(1, 2.5)) # 实际机器人中避免不必要的sleep
    #
    #         result = self.gacha_manager.perform_gacha(user_id, pool_id, is_ten_pull)
    #     except Exception as e:
    #         logger.error(f"万法宝鉴抽奖时发生严重错误: {e}", exc_info=True)
    #         async for r in self._send_response(event, f"抽奖过程中发生未知异常，请联系管理员！错误: {type(e).__name__}"): yield r
    #         return
    #
    #     title_prefix = "十连结果" if is_ten_pull else "抽奖结果"
    #     if result["success"]:
    #         # 刷新用户数据，因为灵石和物品发生了变化
    #         self.XiuXianService.refresh_user_base_attributes(user_id) # 如果灵石影响属性
    #         self.XiuXianService.update_power2(user_id) # 重新计算战力
    #
    #         # 为了更好的显示效果，十连抽的结果可以考虑分行或用更丰富的格式
    #         # 但 _send_response 目前是基于简单文本或单张图片的
    #         # 对于长文本，可以考虑是否需要换行处理
    #         response_message = result["message"]
    #         # 简单的换行处理，让结果更易读
    #         if is_ten_pull and result.get("rewards"):
    #             formatted_rewards = []
    #             for reward in result["rewards"]:
    #                 # 可以根据 reward['category'] 和 reward['data'] 来定制更详细的显示
    #                 if reward['category'] == 'shengtong':
    #                     st_data = reward['data']
    #                     st_rank = st_data.get('rank', '未知品阶') # 从神通完整数据中获取品阶
    #                     formatted_rewards.append(f"✨ 神通【{reward['name']}】({st_rank})")
    #                 else: # 灵石
    #                     formatted_rewards.append(f"💰 {reward['name']}")
    #
    #             header = response_message.split('\n')[0] # 保留第一行“恭喜道友...”
    #             response_message = header + "\n" + "\n".join(formatted_rewards)
    #             if "(十连保底已触发)" in result["message"]: # 把保底提示加回来
    #                 response_message += "\n(十连保底已触发)"
    #
    #
    #         async for r in self._send_response(event, response_message, f"{title_prefix} - {pool_config.get('name', '万法宝鉴')}", font_size=28):
    #             yield r
    #     else:
    #         async for r in self._send_response(event, result["message"], f"{title_prefix}失败"):
    #             yield r

    async def _handle_gacha_pull(self, event: AstrMessageEvent, pool_id: str, is_ten_pull: bool):
        """统一处理单抽和十连抽的通用逻辑"""
        pool_config = self.xiu_config.gacha_pools_config.get(pool_id)
        if not pool_config:
            async for r in self._send_response(event, f"错误：卡池 {pool_id} 配置未找到。"): yield r
            return

        user_id = event.get_sender_id()
        is_user, user_info, msg_check = check_user(self.XiuXianService, user_id)
        if not is_user:
            async for r in self._send_response(event, msg_check): yield r
            return

        try:
            processing_msg = "正在沟通天地，演算天机..." if not is_ten_pull else "大法力运转，十方天机尽在掌握..."
            async for r_wait in self._send_response(event, processing_msg, "请稍候"): yield r_wait

            result = self.gacha_manager.perform_gacha(user_id, pool_id, is_ten_pull)
        except Exception as e:
            logger.error(f"卡池 {pool_id} 抽奖时发生严重错误: {e}", exc_info=True)
            async for r in self._send_response(event,
                                               f"抽奖过程中发生未知异常，请联系管理员！错误: {type(e).__name__}"): yield r
            return

        title_prefix = "十连结果" if is_ten_pull else "抽奖结果"
        if result["success"]:
            self.XiuXianService.refresh_user_base_attributes(user_id)
            self.XiuXianService.update_power2(user_id)

            response_message = result["message"]
            if is_ten_pull and result.get("rewards"):
                formatted_rewards = []
                for reward in result["rewards"]:
                    item_data = reward['data']
                    item_category = reward['category'].lower()
                    category_display_name = {
                           "shengtong": "神通",
                           "faqi": "法器",
                           "gongfa": "功法",
                           "fangju": "防具",
                           "lingshi": "灵石"  # 虽然灵石通常直接显示数量，但以防万一
                    }.get(item_category, item_category.capitalize())  # 未知类别则首字母大写

                    # 通用化显示，适用于神通、法器、功法、防具等
                    if item_category in ['shengtong', 'faqi', 'gongfa', 'fangju']:
                        # 功法/神通的品阶在 item_data['level'] (交换后)
                        # 法器/防具的品阶在 item_data['level'] (json中的level字段，是字符串)
                        # 或者统一使用 item_data['rank'] (json中的rank字段，是数字，越小越好)
                        # 为了统一显示，我们优先用 item_data['level'] (字符串品阶)
                        item_rank_display = item_data.get('level', '未知品阶')
                        if item_category == 'shengtong':
                            item_rank_display = item_data.get('rank', '未知品阶')

                        formatted_rewards.append(
                            f"✨{category_display_name}【{reward['name']}】({item_rank_display})")
                    else:  # 灵石
                        formatted_rewards.append(f"💰 {reward['name']}")

                header = response_message.split('\n')[0]
                response_message = header + "\n" + "\n".join(formatted_rewards)
                # 保底提示已在 GachaManager 中加入 message
                # if "(十连保底已触发" in result["message"]:
                #     response_message += "\n(十连保底已触发)"

            async for r in self._send_response(event, response_message,
                                               f"{title_prefix} - {pool_config.get('name', '神秘宝库')}", font_size=28):
                yield r
        else:
            async for r in self._send_response(event, result["message"], f"{title_prefix}失败"):
                yield r

    @filter.command("万法宝鉴单抽", alias={"神通单抽"})
    @command_lock
    async def gacha_wanfa_baojian_single(self, event: AstrMessageEvent):
        async for response in self._handle_gacha_pull(event, pool_id="wanfa_baojian", is_ten_pull=False):
            yield response

    @filter.command("万法宝鉴十连", alias={"神通十连"})
    @command_lock
    async def gacha_wanfa_baojian_multi(self, event: AstrMessageEvent):
        async for response in self._handle_gacha_pull(event, pool_id="wanfa_baojian", is_ten_pull=True):
            yield response

    # --- 新增：神兵宝库 (法器池) 指令 ---
    @filter.command("神兵宝库", alias={"法器抽奖", "抽法器"})
    @command_lock
    async def gacha_shenbing_baoku_info(self, event: AstrMessageEvent):
        """显示神兵宝库卡池信息及抽奖指令"""
        await self._update_active_groups(event)
        is_user, _, msg_check = check_user(self.XiuXianService, event.get_sender_id())
        if not is_user:
            async for r in self._send_response(event, msg_check): yield r
            return

        pool_id = "shenbing_baoku"
        pool_config = self.xiu_config.gacha_pools_config.get(pool_id)
        if not pool_config:
            async for r in self._send_response(event, "错误：神兵宝库卡池配置未找到。"): yield r
            return

        help_msg = (
            f"⚔️【{pool_config['name']}】⚔️\n"
            f"此地汇聚天下神兵，等待有缘人前来获取！\n\n"
            f"单次寻访：消耗 {pool_config['single_cost']} 灵石\n"
            f"  - 指令：【神兵宝库单抽】\n"
            f"十次寻访：消耗 {pool_config['multi_cost']} 灵石 (享九折优惠，且必得至少一件稀有法器！)\n"
            f"  - 指令：【神兵宝库十连】"
        )
        async for r in self._send_response(event, help_msg.strip(), "神兵宝库指引"): yield r

    @filter.command("神兵宝库单抽", alias={"法器单抽"})
    @command_lock
    async def gacha_shenbing_baoku_single(self, event: AstrMessageEvent):
        """执行神兵宝库单次抽取"""
        async for response in self._handle_gacha_pull(event, pool_id="shenbing_baoku", is_ten_pull=False):
            yield response

    @filter.command("神兵宝库十连", alias={"法器十连"})
    @command_lock
    async def gacha_shenbing_baoku_multi(self, event: AstrMessageEvent):
        """执行神兵宝库十连抽取"""
        async for response in self._handle_gacha_pull(event, pool_id="shenbing_baoku", is_ten_pull=True):
            yield response
    

    @filter.command("丹药商店", alias={"丹药坊"})
    @command_lock
    async def shop_dan_yao_cmd(self, event: AstrMessageEvent):
        """显示丹药商店的商品列表"""
        await self._update_active_groups(event)
        is_user, _, msg_check = check_user(self.XiuXianService, event.get_sender_id())
        if not is_user:
            async for r in self._send_response(event, msg_check): yield r
            return

        # --- 修改点：从 ItemManager 获取商店数据 ---
        shop_items = self.XiuXianService.items.get_shop_dan_yao_items()
        # --- 结束修改点 ---

        if not shop_items:
            async for r in self._send_response(event, "丹药坊今日暂未开张或无丹药可售。"): yield r
            return

        msg_lines = ["欢迎光临丹药坊，今日售卖以下灵丹：\n"]
        for idx, item in enumerate(shop_items):
            msg_lines.append(
                f"编号 {idx + 1}: 【{item['name']}】\n" # item['name'] 等字段由 get_shop_dan_yao_items 保证存在
                f"  价格: {item['price']} 灵石\n"
                f"  效果: {item['desc']}\n"
                f"  境界要求: {item['require_level']}\n"
            )
        msg_lines.append("请输入【购买丹药 编号 [数量]】进行购买 (数量可选，默认为1)")

        full_msg = "\n".join(msg_lines)
        async for r in self._send_response(event, full_msg, "丹药坊", font_size=26): yield r

    @filter.command("购买丹药")
    @command_lock
    async def buy_dan_yao_cmd(self, event: AstrMessageEvent):
        """从丹药商店购买丹药"""
        await self._update_active_groups(event)
        user_id = event.get_sender_id()
        is_user, user_info, msg_check = check_user(self.XiuXianService, user_id)
        if not is_user:
            async for r in self._send_response(event, msg_check): yield r
            return

        args = event.message_str.split()
        if len(args) < 2:
            msg = "指令格式错误！请输入：购买丹药 <编号> [数量]"
            async for r in self._send_response(event, msg): yield r
            return

        # --- 修改点：从 ItemManager 获取商店数据 ---
        shop_items = self.XiuXianService.items.get_shop_dan_yao_items()
        # --- 结束修改点 ---

        if not shop_items:
            async for r in self._send_response(event, "丹药坊今日暂无丹药可售。"): yield r
            return

        try:
            item_shop_index = int(args[1]) - 1
            quantity = 1
            if len(args) > 2:
                quantity = int(args[2])

            if not (0 <= item_shop_index < len(shop_items)):
                raise ValueError("无效的商品编号")
            if quantity <= 0:
                raise ValueError("购买数量必须大于0")

        except ValueError as e:
            error_msg = str(e) if str(e) else "请输入有效的商品编号和数量！"
            async for r in self._send_response(event, error_msg): yield r
            return

        selected_item = shop_items[item_shop_index]
        total_cost = selected_item["price"] * quantity

        if user_info.stone < total_cost:
            msg = f"灵石不足！购买 {quantity}颗【{selected_item['name']}】共需要 {total_cost} 灵石，道友只有 {user_info.stone} 灵石。"
            async for r in self._send_response(event, msg): yield r
            return

        try:
            self.XiuXianService.update_ls(user_id, total_cost, 2)
            # 使用从 ItemManager 获取的物品类型
            # selected_item["item_type_from_data"] 是原始JSON中的type，例如"丹药"
            # selected_item["item_type_internal"] 是ItemManager赋予的，例如"商店丹药"
            # add_item 通常期望的是物品的通用大类，所以用 item_type_from_data 更合适
            self.XiuXianService.add_item(
                user_id,
                int(selected_item["id"]),
                selected_item["item_type_from_data"], # 使用从JSON中读取的原始type
                quantity
            )

            self.XiuXianService.refresh_user_base_attributes(user_id)
            self.XiuXianService.update_power2(user_id)

            msg = f"成功购买 {quantity}颗【{selected_item['name']}】，花费 {total_cost} 灵石！"
            async for r in self._send_response(event, msg): yield r
        except Exception as e:
            logger.error(f"购买丹药时发生错误: {e}", exc_info=True)
            async for r in self._send_response(event, "购买过程中发生未知错误，请联系管理员检查。"): yield r

    @filter.command("战斗详情", alias={"查看战报", "上场回顾"})
    @command_lock
    async def view_battle_details_cmd(self, event: AstrMessageEvent):
        """查看最近一次战斗的详细回合日志"""
        await self._update_active_groups(event)
        user_id = event.get_sender_id()
        is_user, _, msg_check = check_user(self.XiuXianService, user_id)
        if not is_user:
            async for r in self._send_response(event, msg_check): yield r
            return

        detailed_log = self.last_battle_details_log.get(user_id)

        if not detailed_log:
            msg = "道友近期未曾酣战，或战报已随风而逝。"
        else:
            # 可以在日志开头加上一些提示信息
            log_header = [
                "📜 上一场战斗详细回顾 📜",
                "（仅保留最近一场，且回合数过多可能无法完全显示）",
                "----------------------------------"
            ]
            msg_lines = log_header + detailed_log
            msg = "\n".join(msg_lines)

        message = await pic_msg_format(msg, event)
        image_path = await get_msg_pic(message)
        yield event.chain_result([
            Comp.Image.fromFileSystem(str(image_path))
        ])

    @filter.command("万古功法阁", alias={"功法抽奖", "抽功法"})
    @command_lock
    async def gacha_wanggu_gongfa_ge_info(self, event: AstrMessageEvent):
        """显示万古功法阁卡池信息及抽奖指令"""
        await self._update_active_groups(event)
        is_user, _, msg_check = check_user(self.XiuXianService, event.get_sender_id())
        if not is_user:
            async for r in self._send_response(event, msg_check): yield r
            return

        pool_id = "wanggu_gongfa_ge"
        pool_config = self.xiu_config.gacha_pools_config.get(pool_id)
        if not pool_config:
            async for r in self._send_response(event, "错误：万古功法阁卡池配置未找到。"): yield r
            return

        help_msg = (
            f"📜【{pool_config['name']}】📜\n"
            f"此处藏有万千修行法门，助道友登临大道之巅！\n\n"
            f"单次参悟：消耗 {pool_config['single_cost']} 灵石\n"
            f"  - 指令：【万古功法阁单抽】\n"
            f"十次参悟：消耗 {pool_config['multi_cost']} 灵石 (享九折优惠，且必得至少一部稀有功法！)\n"
            f"  - 指令：【万古功法阁十连】"
        )
        async for r in self._send_response(event, help_msg.strip(), "万古功法阁指引"): yield r

    @filter.command("万古功法阁单抽", alias={"功法单抽"})
    @command_lock
    async def gacha_wanggu_gongfa_ge_single(self, event: AstrMessageEvent):
        """执行万古功法阁单次抽取"""
        async for response in self._handle_gacha_pull(event, pool_id="wanggu_gongfa_ge", is_ten_pull=False):
            yield response

    @filter.command("万古功法阁十连", alias={"功法十连"})
    @command_lock
    async def gacha_wanggu_gongfa_ge_multi(self, event: AstrMessageEvent):
        """执行万古功法阁十连抽取"""
        async for response in self._handle_gacha_pull(event, pool_id="wanggu_gongfa_ge", is_ten_pull=True):
            yield response

    @filter.command("玄甲宝殿", alias={"防具抽奖", "抽防具"})
    @command_lock
    async def gacha_xuanjia_baodian_info(self, event: AstrMessageEvent):
        """显示玄甲宝殿卡池信息及抽奖指令"""
        await self._update_active_groups(event)
        is_user, _, msg_check = check_user(self.XiuXianService, event.get_sender_id())
        if not is_user:
            async for r in self._send_response(event, msg_check): yield r
            return

        pool_id = "xuanjia_baodian"
        pool_config = self.xiu_config.gacha_pools_config.get(pool_id)
        if not pool_config:
            async for r in self._send_response(event, "错误：玄甲宝殿卡池配置未找到。"): yield r
            return

        help_msg = (
            f"🛡️【{pool_config['name']}】🛡️\n"
            f"此殿珍藏历代仙甲，披之可御万法！\n\n"
            f"单次铸造：消耗 {pool_config['single_cost']} 灵石\n"
            f"  - 指令：【玄甲宝殿单抽】\n"
            f"十次铸造：消耗 {pool_config['multi_cost']} 灵石 (享九折优惠，且必得至少一件稀有防具！)\n"
            f"  - 指令：【玄甲宝殿十连】"
        )
        async for r in self._send_response(event, help_msg.strip(), "玄甲宝殿指引"): yield r

    @filter.command("玄甲宝殿单抽", alias={"防具单抽"})
    @command_lock
    async def gacha_xuanjia_baodian_single(self, event: AstrMessageEvent):
        """执行玄甲宝殿单次抽取"""
        async for response in self._handle_gacha_pull(event, pool_id="xuanjia_baodian", is_ten_pull=False):
            yield response

    @filter.command("玄甲宝殿十连", alias={"防具十连"})
    @command_lock
    async def gacha_xuanjia_baodian_multi(self, event: AstrMessageEvent):
        """执行玄甲宝殿十连抽取"""
        async for response in self._handle_gacha_pull(event, pool_id="xuanjia_baodian", is_ten_pull=True):
            yield response

    @filter.command("后台送灵石")
    @command_lock
    async def admin_give_stones_cmd(self, event: AstrMessageEvent):
        """处理赠送灵石指令"""
        if event.get_sender_id() not in self.MANUAL_ADMIN_WXIDS:
            msg = "汝非天选之人，无权执此法旨！"
            async for r in self._send_response(event, msg): yield r
            return

        target_id = await self._get_at_user_id(event)
        if not target_id:
            target_id = "qq--666666"

        is_target, target_info, msg = check_user(self.XiuXianService, target_id)
        if not is_target:
            msg = "对方尚未踏入仙途，无法接收你的好意。"
            async for r in self._send_response(event, msg): yield r
            return

        args = event.message_str.split()
        try:
            # 通常数量在参数的最后
            amount_to_give = int(args[-1])
            if amount_to_give <= 0: raise ValueError
        except (ValueError, IndexError):
            msg = "请输入一个正确的赠送数量！例如：送灵石 @张三 100"
            async for r in self._send_response(event, msg): yield r
            return

        # 执行交易
        self.XiuXianService.update_ls(target_id, amount_to_give, 1)  # 1代表增加
        msg = f"你成功赠予了【{target_info.user_name}】 {amount_to_give} 块灵石！"

        async for r in self._send_response(event, msg):
            yield r

    @filter.command("抵押帮助")
    @command_lock
    async def bank_mortgage_help_cmd(self, event: AstrMessageEvent):
        await self._update_active_groups(event)
        help_text = """
🏦【银行抵押系统帮助】🏦
道友可将符合条件的闲置珍宝抵押给银行换取灵石周转。

可用指令:
1. 【抵押列表】：查看背包中可用于抵押的物品及其预估贷款额。
2. 【抵押 [列表编号]】：选择“抵押列表”中的物品进行抵押。
   - 示例: 抵押 1
3. 【我的抵押】：查看当前已抵押的物品、贷款额及到期时间。
4. 【赎回 [抵押编号]】：选择“我的抵押”中的记录进行赎回。
   - 示例: 赎回 123

注意事项:
- 目前可抵押类型：法器、功法、防具、神通。
- 抵押期限：默认为30天。
- 利息：当前版本暂无利息。
- 逾期处理：逾期未赎回的物品将被银行没收。
        """.strip()
        async for r in self._send_response(event, help_text, "银行抵押帮助", font_size=28):
            yield r

    @filter.command("抵押列表")
    @command_lock
    async def view_mortgageable_items_cmd(self, event: AstrMessageEvent):
        await self._update_active_groups(event)
        user_id = event.get_sender_id()
        is_user, _, msg_check = check_user(self.XiuXianService, user_id)
        if not is_user:
            async for r in self._send_response(event, msg_check): yield r
            return

        backpack_items = self.XiuXianService.get_user_back_msg(user_id)
        if not backpack_items:
            async for r in self._send_response(event, "道友背包空空如也，无可抵押之物。"): yield r
            return

        mortgageable_items_display = []
        self.temp_mortgageable_list = {}  # 临时存储可抵押物品，方便后续按编号抵押

        allowed_types = ["法器", "功法", "辅修功法", "防具", "神通"]
        item_display_idx = 1
        for item_in_back in backpack_items:
            # 从 self.XiuXianService.items 获取物品的权威定义
            item_definition = self.XiuXianService.items.get_data_by_item_id(item_in_back.goods_id)
            if item_definition and item_definition.get('item_type') in allowed_types:
                loan_amount = self.XiuXianService.get_item_mortgage_loan_amount(
                    str(item_in_back.goods_id),
                    item_definition
                )
                if loan_amount > 0:
                    mortgageable_items_display.append(
                        f"编号 {item_display_idx}: 【{item_definition.get('name')}】({item_definition.get('item_type')}) "
                        f"- 可贷: {loan_amount} 灵石 (拥有: {item_in_back.goods_num}件)"
                    )
                    # 存储关键信息以便按编号抵押，只抵押一件
                    self.temp_mortgageable_list[str(item_display_idx)] = {
                        "original_item_id": str(item_in_back.goods_id),
                        "name": item_definition.get('name'),
                        "type": item_definition.get('item_type')
                    }
                    item_display_idx += 1

        if not mortgageable_items_display:
            msg = "道友背包中暂无可抵押的珍宝。"
        else:
            msg = "道友背包中可抵押的物品如下 (仅显示可产生贷款额的物品)：\n" + "\n".join(mortgageable_items_display)
            msg += "\n\n请使用【抵押 列表编号】进行操作。"

        async for r in self._send_response(event, msg, "可抵押物品列表", font_size=26):
            yield r

    @filter.command("抵押")
    @command_lock
    async def mortgage_item_cmd(self, event: AstrMessageEvent):
        await self._update_active_groups(event)
        user_id = event.get_sender_id()
        is_user, _, msg_check = check_user(self.XiuXianService, user_id)
        if not is_user:
            async for r in self._send_response(event, msg_check): yield r
            return

        args = event.message_str.split()
        if len(args) < 2:
            async for r in self._send_response(event, "指令格式错误！请使用：抵押 [列表编号]"): yield r
            return

        list_idx_str = args[1]
        if not hasattr(self, 'temp_mortgageable_list') or list_idx_str not in self.temp_mortgageable_list:
            async for r in self._send_response(event, "无效的列表编号，请先使用【抵押列表】查看。"): yield r
            return

        item_to_mortgage_info = self.temp_mortgageable_list[list_idx_str]

        success, message = self.XiuXianService.create_mortgage(
            user_id,
            item_to_mortgage_info["original_item_id"],
            item_to_mortgage_info["name"]
            # due_days 默认是30天
        )
        if success:
            del self.temp_mortgageable_list[list_idx_str]  # 成功后清除，避免重复抵押同一编号
        async for r in self._send_response(event, message): yield r

    @filter.command("我的抵押")
    @command_lock
    async def view_my_mortgages_cmd(self, event: AstrMessageEvent):
        await self._update_active_groups(event)
        user_id = event.get_sender_id()
        is_user, _, msg_check = check_user(self.XiuXianService, user_id)
        if not is_user:
            async for r in self._send_response(event, msg_check): yield r
            return

        # 检查并处理该用户的逾期抵押
        self.XiuXianService.check_and_handle_expired_mortgages(user_id)

        active_mortgages = self.XiuXianService.get_user_active_mortgages(user_id)
        if not active_mortgages:
            async for r in self._send_response(event, "道友在银行暂无抵押物品。"): yield r
            return

        msg_lines = ["道友当前的抵押物品："]
        for mortgage in active_mortgages:
            due_time_obj = datetime.fromisoformat(mortgage['due_time'])
            msg_lines.append(
                f"抵押编号 {mortgage['mortgage_id']}: 【{mortgage['item_name']}】({mortgage['item_type']})\n"
                f"  贷款额: {mortgage['loan_amount']} 灵石\n"
                f"  到期时间: {due_time_obj.strftime('%Y-%m-%d %H:%M')}"
            )
        msg_lines.append("\n请使用【赎回 抵押编号】进行赎回。")
        async for r in self._send_response(event, "\n".join(msg_lines), "我的抵押品", font_size=26): yield r

    @filter.command("赎回")
    @command_lock
    async def redeem_mortgage_cmd(self, event: AstrMessageEvent):
        await self._update_active_groups(event)
        user_id = event.get_sender_id()
        is_user, _, msg_check = check_user(self.XiuXianService, user_id)
        if not is_user:
            async for r in self._send_response(event, msg_check): yield r
            return

        args = event.message_str.split()
        if len(args) < 2:
            async for r in self._send_response(event, "指令格式错误！请使用：赎回 [抵押编号]"): yield r
            return

        try:
            mortgage_id_to_redeem = int(args[1])
        except ValueError:
            async for r in self._send_response(event, "抵押编号必须是数字！"): yield r
            return

        success, message = self.XiuXianService.redeem_mortgage(user_id, mortgage_id_to_redeem)
        async for r in self._send_response(event, message): yield r

    # 可以在每日任务或特定时机调用，清理所有用户的逾期抵押

    @filter.command("一键抵押")
    @command_lock
    async def mass_mortgage_cmd(self, event: AstrMessageEvent):
        await self._update_active_groups(event)
        user_id = event.get_sender_id()
        is_user, _, msg_check = check_user(self.XiuXianService, user_id)
        if not is_user:
            async for r in self._send_response(event, msg_check): yield r
            return

        args = event.message_str.split()
        item_type_to_mass_mortgage = None
        if len(args) > 1:
            item_type_to_mass_mortgage = args[1]
            allowed_types_for_filter = ["法器", "功法", "防具", "神通"]
            if item_type_to_mass_mortgage not in allowed_types_for_filter:
                msg = f"指定抵押的物品类型【{item_type_to_mass_mortgage}】无效。可选类型：法器, 功法, 防具, 神通。"
                async for r in self._send_response(event, msg): yield r
                return

        # 调用服务层执行一键抵押
        num_success, total_loan, detail_messages = self.XiuXianService.mortgage_all_items_by_type(user_id, item_type_to_mass_mortgage)

        if not detail_messages: # 理论上至少会有一条消息
            final_message = "一键抵押执行完毕，但似乎没有产生任何操作。"
        else:
            final_message = "\n".join(detail_messages)

        async for r in self._send_response(event, final_message, "一键抵押报告", font_size=24): yield r