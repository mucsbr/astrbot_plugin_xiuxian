import datetime
import os
import re
import threading
import asyncio
import aiohttp
from hypercorn.config import Config
from hypercorn.asyncio import serve

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api.message_components import Node, Plain, At
from astrbot.api import logger
from astrbot.core import AstrBotConfig
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
from astrbot.core.star.filter.permission import PermissionType
import random
from . import enhancement_config
from . import class_config
from . import pve_config

from .po import UserFishing
from .service import FishingService, get_coins_name
from .draw import draw_fishing_ranking

def get_Node(user_id: str, name: str, message: str) -> Node:
    """将消息转换为Node对象"""
    return Node(uin=user_id, name=name, content=[Plain(message)])

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

@register("fish2.0", "tinker", "升级版的钓鱼插件，附带后台管理界面（个性化钓鱼游戏！）", "1.2.2",
          "https://github.com/tinkerbellqwq/astrbot_plugin_fishing")
class FishingPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)

        # 初始化数据目录
        self.data_dir = "data/"
        os.makedirs(self.data_dir, exist_ok=True)
        # 初始化数据库和钓鱼系统
        db_path = os.path.join(self.data_dir, "fish.db")
        self.FishingService = FishingService(db_path)

        self.web_admin_task = None
        self.secret_key = config.get("secret_key", "default_secret_key")
        self.port = config.get("port", 7777)
        self.MANUAL_ADMIN_WXIDS = ["qq--666666", "another_admin_wxid"]

    async def initialize(self):
        """可选择实现异步的插件初始化方法，当实例化该插件类之后会自动调用该方法。"""
        logger.info("""
_____ _     _     _             
|  ___(_)___| |__ (_)_ __   __ _ 
| |_  | / __| '_ \| | '_ \ / _` |
|  _| | \__ \ | | | | | | | (_| |
|_|   |_|___/_| |_|_|_| |_|\__, |
                           |___/ 
                           """)

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("开启钓鱼后台管理")
    async def start_admin(self, event: AstrMessageEvent):
        """开启钓鱼后台管理"""
        if hasattr(self, 'web_admin_task') and self.web_admin_task and not self.web_admin_task.done():
            yield event.plain_result("❌ 钓鱼后台管理已经在运行中")
            return

        yield event.plain_result("🔄 正在启动钓鱼插件Web管理后台...")

        try:
            from .manager.server import create_app
            app = create_app(self.FishingService.db, self.secret_key)

            hypercorn_config = Config()
            hypercorn_config.bind = [f"0.0.0.0:{self.port}"]
            hypercorn_config.accesslog = "-"

            self.web_admin_task = asyncio.create_task(serve(app, hypercorn_config))

            # 等待服务器就绪（轮询检测端口激活）
            for i in range(10):
                if await self._check_port_active():
                    break
                await asyncio.sleep(1)
            else:
                raise RuntimeError("⌛ 启动超时，请检查防火墙设置")

            public_ip = await self.get_public_ip()
            # 等待1s
            await asyncio.sleep(1)
            logger.info(f"钓鱼插件Web管理后台已启动，正在监听 http://0.0.0.0:{self.port}")

            yield event.plain_result(f"✅ 钓鱼后台已启动！\n🔗 请访问: http://{public_ip}:{self.port}/admin\n🔑 密钥请到配置文件中查看")

        except Exception as e:
            logger.error(f"启动钓鱼后台管理失败: {e}")
            yield event.plain_result(f"❌ 启动钓鱼后台管理失败: {e}")

    async def _check_port_active(self):
        """验证端口是否实际已激活"""
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection('127.0.0.1', self.port),
                timeout=1
            )
            writer.close()
            return True
        except:
            return False

    async def get_public_ip(self):
        """异步获取公网IPv4地址"""
        ipv4_apis = [
            'http://ipv4.ifconfig.me/ip',  # IPv4专用接口
            'http://api-ipv4.ip.sb/ip',  # 樱花云IPv4接口
            'http://v4.ident.me',  # IPv4专用
            'http://ip.qaros.com',  # 备用国内服务
            'http://ipv4.icanhazip.com',  # IPv4专用
            'http://4.icanhazip.com'  # 另一个变种地址
        ]

        async with aiohttp.ClientSession() as session:
            for api in ipv4_apis:
                try:
                    async with session.get(api, timeout=5) as response:
                        if response.status == 200:
                            ip = (await response.text()).strip()
                            # 添加二次验证确保是IPv4格式
                            if re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', ip):
                                return ip
                except:
                    continue

        return "[服务器公网ip]"

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("关闭钓鱼后台管理")
    async def stop_admin(self, event: AstrMessageEvent):
        """关闭钓鱼后台管理"""
        if not hasattr(self, 'web_admin_task') or not self.web_admin_task or self.web_admin_task.done():
            yield event.plain_result("❌ 钓鱼后台管理没有在运行中")
            return

        try:
            # 1. 请求取消任务
            self.web_admin_task.cancel()
            # 2. 等待任务实际被取消
            await self.web_admin_task
        except asyncio.CancelledError:
            # 3. 捕获CancelledError，这是成功关闭的标志
            logger.info("钓鱼插件Web管理后台已成功关闭。")
            yield event.plain_result("✅ 钓鱼后台已关闭。")
        except Exception as e:
            # 4. 捕获其他可能的意外错误
            logger.error(f"关闭钓鱼后台管理时发生意外错误: {e}", exc_info=True)
            yield event.plain_result(f"❌ 关闭钓鱼后台管理失败: {e}")

    @filter.command("注册")  # ok
    async def register_user(self, event: AstrMessageEvent):
        """注册钓鱼用户"""
        user_id = event.get_sender_id()
        # 如果用户昵称为空，则使用用户ID
        result = self.FishingService.register(user_id,
                                              event.get_sender_name() if event.get_sender_name() else str(user_id))
        yield event.plain_result(result["message"])

    @filter.command("钓鱼", alias={"fish"})  # ok
    async def go_fishing(self, event: AstrMessageEvent):
        """进行一次钓鱼"""
        user_id = event.get_sender_id()

        # 检查用户是否注册
        if not self.FishingService.is_registered(user_id):
            yield event.plain_result("请先注册才能使用此功能")
            return

        # 检查CD时间
        last_fishing_time = self.FishingService.db.get_last_fishing_time(user_id)
        utc_time = datetime.datetime.utcnow()
        utc_plus_4 = utc_time + datetime.timedelta(hours=4)
        current_time = utc_plus_4.timestamp()
        # 查看用户是否装备了海洋之心
        equipped_rod = self.FishingService.db.get_user_equipped_accessories(user_id)
        if equipped_rod and equipped_rod.get("name") == "海洋之心":
            # 如果装备了海洋之心，CD时间减少到1分钟
            last_fishing_time = max(0, last_fishing_time - 40)
            logger.info(f"用户 {user_id} 装备了海洋之心，{last_fishing_time}")
        # logger.info(f"用户 {user_id} 上次钓鱼时间: {last_fishing_time}, 当前时间: {current_time}")
        # 3分钟CD (180秒)
        base_cd = 60
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
        #if last_fishing_time > 0 and current_time - last_fishing_time < 180:
        #    remaining_seconds = int(180 - (current_time - last_fishing_time))
        #    remaining_minutes = remaining_seconds // 60
        #    remaining_secs = remaining_seconds % 60
        #    yield event.plain_result(f"⏳ 钓鱼冷却中，请等待 {remaining_minutes}分{remaining_secs}秒后再试")
        #    return

        # 钓鱼需要消耗金币
        fishing_cost = 10  # 每次钓鱼消耗10金币
        user_coins = self.FishingService.db.get_user_coins(user_id)

        if user_coins < fishing_cost:
            yield event.plain_result(f"💰 {get_coins_name()}不足，钓鱼需要 {fishing_cost} {get_coins_name()}")
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
            message += f"💰 价值：{fish_info.get('value', 0)}{get_coins_name()}"
            yield event.plain_result(message)
        else:
            yield event.plain_result(result.get("message", "💨 什么都没钓到..."))

    @filter.command("全部卖出")  # ok
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
                message = f"💰 成功出售所有鱼！获得 {coins_earned} {get_coins_name()}"
            else:
                message = f"💰 {original_message}"
        else:
            # 如果是失败消息，添加失败相关表情
            message = f"❌ {original_message}"

        yield event.plain_result(message)

    @filter.command("出售稀有度", alias={"sellr"})
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
                    message = f"💰 成功出售稀有度 {rarity} 的鱼！获得 {coins_earned} {get_coins_name()}"
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

        message += f"\n💰 总价值: {total_value}{get_coins_name()}"

        yield event.plain_result(message)

    @filter.command("签到", alias={"signin"})  # ok
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
                message = f"📅 签到成功！获得 {coins_earned} {get_coins_name()} 💰"
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
                message += f" (⏱️ 剩余时间: {bait.get('remaining_time')}分钟)"

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

    @filter.command("商店", alias={"shop"})
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
                message += f"ID:{bait.get('bait_id')} - {bait.get('name')} (💰 {bait.get('cost')}{get_coins_name()})"
                if bait.get("description"):
                    message += f" - {bait.get('description')}"
                message += "\n"

        # 显示鱼竿
        message += "\n【🎣 鱼竿】\n"
        for rod in all_rods.get("rods", []):
            if rod.get("source") == "shop" and rod.get("purchase_cost", 0) > 0:
                message += f"ID:{rod.get('rod_id')} - {rod.get('name')} (💰 {rod.get('purchase_cost')}{get_coins_name()})"
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

    @filter.command("抽卡", alias={"gacha", "抽奖"})
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
                    message += f"    💰 花费: {pool.get('cost_coins')}{get_coins_name()}/次\n\n"

                # 添加卡池详细信息
                message += "【📋 卡池详情】使用「查看卡池 ID」命令查看详细物品概率\n"
                message += "【🎲 抽卡命令】使用「抽卡 ID」命令选择抽卡池进行单次抽卡\n"
                message += "【🎯 十连命令】使用「十连 ID」命令进行十连抽卡"
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

    @filter.command("查看卡池", alias={"pool", "查看奖池"})
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
            message += f"抽取花费: {pool_details.get('cost_coins', 0)}{get_coins_name()}金币\n\n"

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
                        item_name = f"{quantity}{get_coins_name()}"
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

    @filter.command("十连", alias={"multi"})
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

    @filter.command("金币")
    async def check_coins(self, event: AstrMessageEvent):
        """查看用户金币数量"""
        user_id = event.get_sender_id()

        # 检查用户是否注册
        if not self.FishingService.is_registered(user_id):
            yield event.plain_result("请先注册才能使用此功能")
            return

        # 获取用户货币信息
        result = self.FishingService.get_user_currency(user_id)

        if not result.get("success"):
            yield event.plain_result("获取货币信息失败！")
            return

        coins = result.get("coins", 0)

        message = f"💰 你的{get_coins_name()}: {coins}"
        yield event.plain_result(message)

    @filter.command("排行榜", alias={"rank", "排行"})
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

    @filter.command("自动钓鱼", alias={"auto"})
    async def toggle_auto_fishing(self, event: AstrMessageEvent):
        """开启或关闭自动钓鱼"""
        user_id = event.get_sender_id()
        result = self.FishingService.toggle_auto_fishing(user_id)

        # 增加表情符号
        original_message = result.get("message", "操作失败！")
        if "开启" in original_message:
            message = f"🤖 {original_message}"
        elif "关闭" in original_message:
            message = f"⏹️ {original_message}"
        else:
            message = f"❌ {original_message}"

        yield event.plain_result(message)

    @filter.command("锻造查询")
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
            message += f"强化到 +{level + 1}:\n"
            message += f"  - 成功率: {next_level_config['probability']}%\n"
            message += f"  - 所需金币: {next_level_config['cost']}\n\n"
            message += "💡 使用「/强化」命令进行强化！"
        else:
            message += "恭喜你，已达到最高锻造等级！"

        yield event.plain_result(message)


    @filter.command("强化", alias={"forge"})
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

    @filter.command("职业")
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

    @filter.command("选择职业")
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

    @filter.command("发动技能")
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

    @filter.command("我的职业")
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

   # @filter.command("打开宝箱", alias={"openchest"})
   # async def open_chest(self, event: AstrMessageEvent):
   #     """打开一个宝箱（沉没的、鱼竿或饰品）"""
   #     args = event.message_str.split()
   #     user_id = event.get_sender_id()

   #     if len(args) == 1: # /打开宝箱
   #         result = self.FishingService.open_treasure_chest(user_id)
   #     elif len(args) == 2 and args[1] in ['鱼竿', '饰品']:
   #         chest_type = 'rod' if args[1] == '鱼竿' else 'accessory'
   #         result = self.FishingService.open_equipment_chest(user_id, chest_type)
   #     else:
   #         yield event.plain_result("格式错误！请使用：/打开宝箱 或 /打开宝箱 鱼竿/饰品")
   #         return

   #     yield event.plain_result(f"🎉 {result['message']}" if result.get('success') else f"⚠️ {result.get('message', '操作失败')}")

    @filter.command("打开宝箱", alias={"openchest"})
    async def open_chest(self, event: AstrMessageEvent):
        """
        打开一个或多个宝箱。
        用法:
        /打开宝箱 [数量]
        /打开宝箱 鱼竿 [数量]
        /打开宝箱 饰品 [数量]
        (若不指定数量，默认为1)
        """
        args = event.message_str.split()
        user_id = event.get_sender_id()
        quantity = 1 # 默认数量
        result = None

        try:
            # --- 核心修改：智能解析参数 ---
            if len(args) == 1: # /打开宝箱
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

    @filter.command("遗忘河之水")
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

    @filter.command("角斗", alias={"决斗"})
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

    @filter.command("我的道具", alias={"myitems"})
    async def show_my_items(self, event: AstrMessageEvent):
        """显示玩家的特殊道具背包"""
        user_id = event.get_sender_id()
        message = self.FishingService.get_my_items_message(user_id)
        yield event.plain_result(message)

    @filter.command("回廊商店")
    async def show_corridor_shop(self, event: AstrMessageEvent):
        """查看镜像回廊的碎片商店"""
        message = self.FishingService.get_shop_info_message(event.get_sender_id())
        yield event.plain_result(message)

    # --- PVE系统：镜像回廊 ---
    @filter.command("回廊牌组")
    async def show_corridor_deck(self, event: AstrMessageEvent):
        """查看镜像回廊的传说牌库"""
        message = self.FishingService.pve_handler.get_deck_list_message()
        # 考虑到列表可能很长，可以分段发送，但按要求先一次性输出
        yield event.plain_result(message)

    @filter.command("挑战回廊")
    async def start_corridor_challenge(self, event: AstrMessageEvent):
        """使用固定ID快捷开始回廊挑战"""
        args = event.message_str.split()
        if len(args) < 2:
            yield event.plain_result("格式错误！请使用：/挑战回廊 id1,id2,id3,id4,id5")
            return

        lineup_ids = [id.strip() for id in args[1].split(',')]
        if len(lineup_ids) != 5:
            yield event.plain_result("格式错误！阵容必须包含5个ID，用逗号隔开。")
            return

        yield event.plain_result("🛡️ 正在构筑镜像阵容并进入回廊...请稍候...")

        result = self.FishingService.pve_handler.start_challenge(event.get_sender_id(), lineup_ids)

        yield event.plain_result(result['message'])

    @filter.command("回廊购买")
    async def buy_from_corridor_shop(self, event: AstrMessageEvent):
        """从回廊商店购买物品"""
        args = event.message_str.split()
        if len(args) < 2:
            yield event.plain_result("格式错误！请使用：/回廊购买 <商品编号> [数量]")
            return

        item_id_str = args[1]
        quantity = 1
        if len(args) > 2:
            try:
                quantity = int(args[2])
            except ValueError:
                yield event.plain_result("❌ 数量必须是一个有效的数字。")
                return

        result = self.FishingService.purchase_from_shop(event.get_sender_id(), item_id_str, quantity)
        yield event.plain_result(f"🛍️ {result['message']}")

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

    @filter.command("发放贷款")
    async def grant_loan(self, event: AstrMessageEvent):
        """[管理员] 为指定玩家发放其当前额度的贷款"""
        sender_id = event.get_sender_id()

        # 这里的 self.MANUAL_ADMIN_WXIDS 是我们在 __init__ 方法中定义的列表
        # !! 重要：请确保您已在 __init__ 方法中定义并填写真实的管理员wxid
        if sender_id not in getattr(self, 'MANUAL_ADMIN_WXIDS', []):
            yield event.plain_result("❌ [手动校验] 你没有权限使用此命令。")
            return

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


        args = event.message_str.split()
        quantity = 0
        if len(args) >= 2:
            if args[1].isdigit():
                quantity = int(args[1])
            else:
                yield event.plain_result(f"贷款发放失败")
                return
        else:
            yield event.plain_result(f"贷款发放失败")
            return
        result = self.FishingService.grant_loan_to_user(target_id, quantity)
        yield event.plain_result(f"🏦 {result['message']}")

    @filter.command("我的贷款")
    async def my_loan(self, event: AstrMessageEvent):
        """查询自己的贷款状态和可贷款额度"""
        user_id = event.get_sender_id()
        message = self.FishingService.get_loan_status_message(user_id)
        yield event.plain_result(message)

    @filter.command("初始化贷款数据")
    async def initialize_loans(self, event: AstrMessageEvent):
        """
        [管理员] 一次性为所有无贷款记录的用户，根据其当前碎片数量，设定初始贷款额度。
        这是一个危险操作，请在确认后执行。
        """
        sender_id = event.get_sender_id()

        # 这里的 self.MANUAL_ADMIN_WXIDS 是我们在 __init__ 方法中定义的列表
        # !! 重要：请确保您已在 __init__ 方法中定义并填写真实的管理员wxid
        if sender_id not in getattr(self, 'MANUAL_ADMIN_WXIDS', []):
            yield event.plain_result("❌ [手动校验] 你没有权限使用此命令。")
            return

        try:
            result = self.FishingService.initialize_all_user_loans()
        except asyncio.TimeoutError:
            yield event.plain_result("操作已超时取消。")
        except Exception as e:
            logger.error(f"执行贷款初始化时发生未知错误: {e}", exc_info=True)
            yield event.plain_result("❌ 执行时发生内部错误，请联系技术人员查看后台日志。")

        yield event.plain_result(result["message"])

    @filter.command("钓鱼帮助", alias={"钓鱼指南"})
    async def show_help(self, event: AstrMessageEvent):
        """显示钓鱼游戏帮助信息"""
        prefix = """前言：使用/注册指令即可开始，鱼饵是一次性的（每次钓鱼随机使用），可以一次买多个鱼饵例如：/购买鱼饵 3 200。鱼竿购买后可以通过/鱼竿查看，如果你嫌钓鱼慢，可以玩玩/擦弹 金币数量，随机获得0-10倍收益"""
        message = f"""【🎣 钓鱼系统帮助】
    📋 基础命令:
     - /注册: 注册钓鱼用户
     - /钓鱼: 进行一次钓鱼(消耗10{get_coins_name()}，3分钟CD)
     - /签到: 每日签到领取奖励
     - /金币: 查看当前{get_coins_name()}
     - /我的贷款: 查看当前贷款额度
    
    🎒 背包相关:
     - /鱼塘: 查看鱼类背包
     - /偷鱼 @用户: 偷取指定用户的鱼
     - /鱼塘容量: 查看当前鱼塘容量
     - /升级鱼塘: 升级鱼塘容量
     - /鱼饵: 查看鱼饵背包
     - /鱼竿: 查看鱼竿背包
     - /饰品: 查看饰品背包
    
    🏪 商店与购买:
     - /商店: 查看可购买的物品
     - /购买鱼饵 ID [数量]: 购买指定ID的鱼饵，可选择数量
     - /购买鱼竿 ID: 购买指定ID的鱼竿
     - /使用鱼饵 ID: 使用指定ID的鱼饵
     - /使用鱼竿 ID: 装备指定ID的鱼竿
     - /出售鱼竿 ID: 出售指定ID的鱼竿
     - /使用饰品 ID: 装备指定ID的饰品
     - /出售饰品 ID: 出售指定ID的饰品
    
    🏪 市场与购买:
        - /市场: 查看市场中的物品
        - /上架饰品 ID: 上架指定ID的饰品到市场
        - /上架鱼竿 ID: 上架指定ID的鱼竿到市场
        - /购买 ID: 购买市场中的指定物品ID

    🎒 道具Item:
     - /打开宝箱: 打开沉没的宝箱
     - /打开宝箱 [数量]
     - /打开宝箱 鱼竿 [数量]
     - /打开宝箱 饰品 [数量]
     - /我的道具: 查看你的宝箱、幸运符等
    
    💰 出售鱼类:
     - /全部卖出: 出售背包中所有鱼
     - /保留卖出: 出售背包中所有鱼（但会保留1条）
     - /出售稀有度 <1-5>: 出售特定稀有度的鱼
    
    🎮 抽卡系统:
     - /抽卡 ID: 进行单次抽卡
     - /十连 ID: 进行十连抽卡
     - /查看卡池 ID: 查看卡池详细信息和概率
     - /抽卡记录: 查看抽卡历史记录

     ⚔️ 成长与PK:
     - /强化: 提升锻造等级
     - /强化 使用幸运符: 使用幸运符强化
     - /锻造查询: 查看强化属性
     - /职业: 查看所有可选职业
     - /选择职业 <名称>: 选择你的职业
     - /我的职业: 查看当前职业详情
     - /遗忘河之水: 重置职业为无
     - /决斗 @用户: 双方都需要收取被挑战者的金币的10%手续费
     - /PK排行榜, /战报 (开发中)

     🛡️ PVE副本:
     - /回廊牌组: 查看所有可用的传说鱼
     - /挑战回廊 id1,id2..: 开始PVE挑战
     - /回廊商店: 使用镜像碎片兑换道具
     - /回廊购买 <编号>: 从商店购买
    
    🔧 其他功能:
     - /自动钓鱼: 开启/关闭自动钓鱼功能
     - /排行榜: 查看钓鱼排行榜
     - /鱼类图鉴: 查看所有鱼的详细信息
     - /擦弹 [金币数]: 向公共奖池投入{get_coins_name()}，获得随机倍数回报（0-10倍）
     - /擦弹历史： 查看擦弹历史记录
     - /查看称号: 查看已获得的称号
     - /使用称号 ID: 使用指定ID称号
     - /查看成就: 查看可达成的成就
     - /钓鱼记录: 查看最近的钓鱼记录
     - /税收记录: 查看税收记录
     - /开启钓鱼后台管理: 开启钓鱼后台管理功能（仅管理员可用）
     - /关闭钓鱼后台管理: 关闭钓鱼后台管理功能（仅管理员可用）
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

    @filter.command("擦弹", alias={"wipe"})
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
                            message = f"🎰 大成功！你投入 {amount} {get_coins_name()}，获得了 {multiplier}倍 回报！\n💰 奖励: {reward} {get_coins_name()} (盈利: +{profit})"
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

    @filter.command("擦弹历史", alias={"wipe_history", "擦弹记录"})
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

            message += f"{idx}. ⏱️ {timestamp}\n"
            message += f"   {emoji} 投入: {contribution} {get_coins_name()}，获得 {multiplier}倍 ({reward} {get_coins_name()})\n"
            message += f"   {profit_text}\n"

        # 添加是否可以再次擦弹的提示
        can_wipe_today = result.get("available_today", False)
        if can_wipe_today:
            message += "\n🎮 今天你还可以进行擦弹"
        else:
            message += "\n⏳ 今天你已经进行过擦弹了，明天再来吧"

        yield event.plain_result(message)

    @filter.command("查看称号", alias={"称号", "titles"})
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

    @filter.command("使用称号")
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

    @filter.command("查看成就", alias={"成就", "achievements"})
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

            message += f"{idx}. ⏱️ {time_str} {king_size}{fish_name} {rarity_stars}\n"
            message += f"   ⚖️ 重量: {weight}g | 💰 价值: {value}{get_coins_name()}\n"
            message += f"   🔧 装备: {rod_name} | 🎣 鱼饵: {bait_name}\n"
        yield event.plain_result(message)
    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("用户列表", alias={"users"})
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

    @filter.command("抽卡记录", alias={"gacha_history"})
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

            message += f"{idx}. ⏱️ {time_str}\n"
            message += f"   {rarity_emoji} {item_name} {rarity_stars}\n"
            if quantity > 1:
                message += f"   📦 数量: x{quantity}\n"

        yield event.plain_result(message)

    @filter.command("饰品", alias={"accessories"})
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

    @filter.command("使用饰品", alias={"useaccessory"})
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

    @filter.command("出售饰品", alias={"sellaccessory"})
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

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("增加金币", alias={"addcoins"})
    async def add_coins(self, event: AstrMessageEvent):
        """给指定用户增加金币（管理员命令）"""
        args = event.message_str.split(' ')
        
        if len(args) < 3:
            yield event.plain_result("⚠️ 请使用正确的格式：增加金币 <用户ID> <金币数量>")
            return
            
        try:
            user_id = args[1]
            amount = int(args[2])
            
            if amount <= 0:
                yield event.plain_result("⚠️ 金币数量必须大于0")
                return
                
            # 检查用户是否存在
            if not self.FishingService.is_registered(user_id):
                yield event.plain_result("❌ 该用户未注册")
                return
                
            # 增加金币
            result = self.FishingService.db.update_user_coins(user_id, amount)
            
            if result:
                # 获取用户当前金币数
                user_currency = self.FishingService.db.get_user_currency(user_id)
                current_coins = user_currency.get('coins', 0)
                
                message = f"✅ 成功为用户 {user_id} 增加 {amount} {get_coins_name()}\n"
                message += f"💰 当前{get_coins_name()}数：{current_coins}"
            else:
                message = "❌ 增加金币失败，请稍后重试"
                
            yield event.plain_result(message)
            
        except ValueError:
            yield event.plain_result("⚠️ 请输入有效的金币数量")
        except Exception as e:
            logger.error(f"增加金币时出错: {e}")
            yield event.plain_result(f"❌ 操作失败：{str(e)}")

    @filter.permission_type(PermissionType.ADMIN)
    @filter.command("导入数据")
    async def import_data(self, event: AstrMessageEvent):
        """导入数据（管理员命令）"""
        # 这里可以实现数据导入的逻辑
        OLD_DATABASE = "data/fishing.db"
        if not os.path.exists(OLD_DATABASE):
            yield event.plain_result("⚠️ 旧数据库文件不存在")
            return
        old_data = self.FishingService.get_old_database_data(OLD_DATABASE)
        # 批量插入用户数据
        yield event.plain_result(f"获取到旧数据{len(old_data)}条, 开始导入数据...")
        if old_data:
            import_users = []
            for data in old_data:
                user_id = data.get("user_id")
                coins = data.get("coins", 0)
                nickname = None
                if isinstance(event, AiocqhttpMessageEvent):
                    bot = event.bot
                    try:
                        # 如果user_id里面有QQ号，获取用户信息
                        if isinstance(user_id, str) and user_id.isdigit():
                            info = await bot.get_stranger_info(user_id=int(user_id))
                            nickname = info.get("nickname")
                            logger.info(f"获取到用户昵称: {nickname}")
                        else:
                            nickname = None
                            logger.info(f"获取用户信息失败: {user_id} 不是有效的QQ号")
                    except Exception as e:
                        logger.error(f"获取用户信息失败: {e}")
                        nickname = None
                    # 休眠1秒，避免频繁请求
                    # await asyncio.sleep(1)
                if nickname is None:
                    nickname = data.get("user_id")
                user = UserFishing(user_id, nickname, coins)
                import_users.append(user)
            result = self.FishingService.insert_users(import_users)
            yield event.plain_result(result.get("message", "导入数据失败"))

    @filter.command("市场", alias={"market"})
    async def show_market(self, event: AstrMessageEvent):
        """显示商店中的所有商品"""
        user_id = event.get_sender_id()

        # 检查用户是否注册
        if not self.FishingService.is_registered(user_id):
            yield event.plain_result("请先注册才能使用此功能")
            return

        # 获取市场商品
        market_items = self.FishingService.get_market_items()

        # return {
        #     "success": True,
        #     "rods": rods,
        #     "accessories": accessories
        # }
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

    @filter.command("购买", alias={"buy"})
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
            result = self.FishingService.buy_item(user_id, market_id)

            if result["success"]:
                yield event.plain_result(f"✅ {result['message']}")
            else:
                yield event.plain_result(f"❌ {result['message']}")
        except ValueError:
            yield event.plain_result("⚠️ 请输入有效的商品ID")

    @filter.command("上架饰品", alias={"put_accessory_on_sale"})
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
            message += f"{idx}. ⏱️ {time_str}\n"
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
           #     if hasattr(message_obj, 'raw_message') and hasattr(message_obj.raw_message, 'msg_source'):
            
           # logger.info("要偷鱼source")
           # # 检查消息中是否有At对象
           # if "\u2005" in message_obj.message_str:
           #     logger.info("要偷鱼2005")
           #     match = re.search(r"<atuserlist>(.*?)</atuserlist>",message_obj.raw_message.msg_source)
           #     if match:
           #       wxids_string = match.group(1)
           #       logger.info("要偷鱼ssssssssss")
           #       target_id = wxids_string.split(',')[0]
           #    # if isinstance(comp, At):
           #    #     target_id = comp.qq
           #    #     break
        if target_id is None:
            yield event.plain_result("请在消息中@要偷鱼的用户")
            return
        # logger.info(f"用户 {user_id} 尝试偷鱼，目标用户ID: {target_id}")
        #if int(target_id) == int(user_id):
        #    yield event.plain_result("不能偷自己的鱼哦！")
        #    return
        # 执行偷鱼逻辑
        result = self.FishingService.steal_fish(user_id, target_id)
        if result["success"]:
            yield event.plain_result(f"✅ {result['message']}")
        else:
            yield event.plain_result(f"❌ {result['message']}")



    async def terminate(self):
        """插件被卸载/停用时调用"""
        logger.info("钓鱼插件正在终止...")
        # 停止自动钓鱼线程
        self.FishingService.stop_auto_fishing_task()
        self.FishingService.stop_achievement_check_task()
        if hasattr(self, 'web_admin_task'):
            try:
                # 1. 请求取消任务
                #self.web_admin_task.cancel()
                # 2. 等待任务实际被取消
                #await self.web_admin_task
            except asyncio.CancelledError:
                # 3. 捕获CancelledError，这是成功关闭的标志
                logger.info("钓鱼插件Web管理后台已成功关闭。")
        logger.info("钓鱼插件已成功终止。")


        
    @filter.command("保留卖出", alias={"safe_sell"})
    async def safe_sell_all_fish(self, event: AstrMessageEvent):
        user_id = event.get_sender_id()
        
        # 记录卖出前总价值（用于验证）
        before_value = self.FishingService.db.get_user_fish_total_value(user_id)
        
        result = self.FishingService.sell_all_fish_keep_one_batch(user_id)
        
        if result["success"]:
            # 验证卖出金额
            after_value = self.FishingService.db.get_user_fish_total_value(user_id)
            actual_diff = before_value - after_value
            
            # 添加警告日志（如果差异过大）
            if abs(actual_diff - result["total_value"]) > 1.0:
                logger.warning(
                    f"价值计算异常！用户:{user_id}\n"
                    f"计算值:{result['total_value']} 实际差值:{actual_diff}"
                )
            
            # 如果消息太长，分段发送
            if len(result["message"]) > 500000:
                yield event.plain_result(f"✅ 成功卖出！获得 {result['total_value']} 水晶")
                yield event.plain_result("🐟 卖出明细：")
                for op in result["details"][:5]:  # 只显示前5条
                    yield event.plain_result(
                        f"- {op['name']}×{op['sell_count']} ({op['value_per']}水晶/个)"
                    )
                if len(result["details"]) > 5:
                    yield event.plain_result(f"...等共{len(result['details'])}种鱼")
            else:
                yield event.plain_result(result["message"])
        else:
            yield event.plain_result(f"❌ {result['message']}")
