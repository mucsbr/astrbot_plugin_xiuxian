from apscheduler.schedulers.asyncio import AsyncIOScheduler
from astrbot.api import logger
from datetime import datetime, timedelta
# v-- 这是Context唯一的、正确的导入路径 --v
from astrbot.api.star import Context
# ^-- 这是Context唯一的、正确的导入路径 --^
from astrbot.api.event import MessageChain 
from astrbot.api.message_components import Image
import asyncio
import random
import astrbot.api.message_components as Comp

from .service import XiuxianService
from .utils import get_msg_pic

class XianScheduler:
    """
    修仙插件的定时任务调度器类 (已修正所有导入)
    """
    def __init__(self, context: Context, service: XiuxianService, plugin_instance):
        self.context = context
        self.service = service
        self.plugin_instance = plugin_instance
        self.scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")

    def start(self):
        try:
            self._add_jobs()
            self.scheduler.start()
            asyncio.create_task(self._refresh_market_task())
           # 检查是否有从数据库加载到BOSS，如果没有，则立即生成一个
            if not self.plugin_instance.world_boss:
                logger.info("未从数据库加载到世界BOSS，将立即生成一个新的。")
                asyncio.create_task(self._create_world_boss_task())

            logger.info("修仙插件定时任务已启动。")
        except Exception as e:
            logger.error(f"修仙插件定时任务启动失败: {e}")

    def _add_jobs(self):
        self.scheduler.add_job(self._daily_reset_tasks, "cron", hour=0, minute=0)

        # 每日0点0分10秒刷新坊市
        self.scheduler.add_job(self._refresh_market_task, "cron", hour=0, minute=0, second=10)
        
        sect_config = self.service.get_sect_config()
        if sect_config:
            time_str = sect_config.get("发放宗门资材", {}).get("时间", "12-00")
            hour, minute = time_str.split('-')
            self.scheduler.add_job(self._sect_materials_update_task, "cron", hour=int(hour), minute=int(minute))

        boss_config = self.service.get_boss_config()
        if boss_config:
            boss_time = boss_config.get("Boss生成时间参数", {"hours": 0, "minutes": 50})
            if boss_time.get('hours', 0) > 0 or boss_time.get('minutes', 0) > 0:
                self.scheduler.add_job(
                    self._create_world_boss_task,
                    "interval",
                    hours=boss_time['hours'],
                    minutes=boss_time['minutes'],
                    id="world_boss_job"
                )

        # 坊市自动上架
        market_config = self.plugin_instance.xiu_config.market_auto_add_config
        if market_config.get("is_enabled"):
            self.scheduler.add_job(
                self._market_auto_add_task, "cron",
                minute=market_config.get("cron_hours", "*/3"), id="market_auto_add"
            )

        # 定时拍卖行
        auction_config = self.plugin_instance.xiu_config.auction_config
        if auction_config.get("is_enabled"):
            self.scheduler.add_job(
                self._start_auction_task, "cron",
                hour=auction_config.get("cron_hour", 18), minute=auction_config.get("cron_minute", 0), id="auction_start"
            )

    async def _market_auto_add_task(self):
        """定时自动上架商品"""
        logger.info("开始执行坊市自动上架任务...")
        # 1. 定义上限
        MARKET_SIZE_LIMIT = 70

        # 2. 检查当前商品数量 (全局)
        current_item_count = self.service.get_market_goods_count()

        # 3. 如果达到或超过上限，则记录日志并直接退出
        if current_item_count >= MARKET_SIZE_LIMIT:
            logger.info(f"全局坊市商品数量已达上限 ({current_item_count}/{MARKET_SIZE_LIMIT})，本次自动上架任务跳过。")
            return

        config = self.plugin_instance.xiu_config.market_auto_add_config
        item_pool = config.get("item_pool")
        if not item_pool:
            logger.warning("自动上架物品池为空，任务跳过。")
            return

        item_to_add = random.choice(item_pool)
        item_info = self.service.items.get_data_by_item_id(item_to_add['id'])

        for group_id in self.plugin_instance.groups:
            self.service.add_market_goods(
                user_id="0", # 0 代表系统
                goods_id=item_to_add['id'],
                goods_type=item_info.get('item_type', '未知'),
                price=item_to_add['price'],
            )

        msg = f"一位神秘的商人来到了坊市，悄悄上架了【{item_info['name']}】！"
        logger.info(f"已为所有活跃群组自动上架商品：{item_info['name']}")
        await self._broadcast_to_groups(msg, "坊市播报")

    async def _start_auction_task(self, specified_item_id: int = None):
        """
        开始一场拍卖会。
        :param specified_item_id: 如果提供，则直接拍卖此物品；否则从池中随机选择。
        """
        try:
            if self.plugin_instance.auction_data:
                logger.info("当前已有拍卖正在进行，新的拍卖任务跳过。")
                # 如果是手动触发，可以返回一个信息
                return {"success": False, "message": "当前已有拍卖正在进行中！"}

            logger.info("开始执行拍卖任务...")
            config = self.plugin_instance.xiu_config.auction_config
            item_pool = config.get("item_pool")

            item_to_auction = None
            if specified_item_id:
                # 查找指定的物品
                for item in item_pool:
                    if item['id'] == specified_item_id:
                        item_to_auction = item
                        break
                if not item_to_auction:
                    return {"success": False, "message": f"在拍卖池中找不到ID为 {specified_item_id} 的物品。"}
            else:
                # 从池中随机选择
                if not item_pool:
                    logger.warning("拍卖物品池为空，任务跳过。")
                    return {"success": False, "message": "拍卖物品池为空！"}
                item_to_auction = random.choice(item_pool)

            item_info = self.service.items.get_data_by_item_id(item_to_auction['id'])

            end_time = datetime.now() + timedelta(seconds=config['duration_seconds'])

            self.plugin_instance.auction_data = {
                "item_id": item_to_auction['id'],
                "item_name": item_info['name'],
                "start_price": item_to_auction['start_price'],
                "current_price": item_to_auction['start_price'],
                "top_bidder_id": None,
                "top_bidder_name": "无人出价",
                "end_time": end_time
            }

            msg = f"""
    铛铛铛！一场特别的拍卖会现在开始！
    本次拍卖的珍品是：【{item_info['name']}】
    起拍价：{item_to_auction['start_price']} 灵石
    请使用【出价 [金额]】参与竞拍！
    拍卖将于 {config['duration_seconds'] // 60} 分钟后结束！
    """
            await self._broadcast_to_groups(msg.strip(), "拍卖公告")

            asyncio.create_task(self._auction_countdown_task())
        except Exception as e:
            logger.error(f"向群 广播消息失败: {e}")

        return {"success": True, "message": f"已成功开启【{item_info['name']}】的拍卖会！"}

    async def _auction_countdown_task(self):
        """监控拍卖倒计时的任务"""
        try:
            while True:
                await asyncio.sleep(1)
                if not self.plugin_instance.auction_data: # 拍卖被提前结束
                    return

                if datetime.now() >= self.plugin_instance.auction_data['end_time']:
                    # 时间到，结算拍卖
                    auction_result = self.plugin_instance.auction_data
                    self.plugin_instance.auction_data = None # 清空拍卖数据

                    if not auction_result['top_bidder_id']:
                        msg = f"很遗憾，本次【{auction_result['item_name']}】的拍卖流拍了！"
                    else:
                        winner_id = auction_result['top_bidder_id']
                        winner_name = auction_result['top_bidder_name']
                        price = auction_result['current_price']

                        # 结算
                        self.service.update_ls(winner_id, price, 2)
                        item_info = self.service.items.get_data_by_item_id(auction_result['item_id'])
                        self.service.add_item(winner_id, auction_result['item_id'], item_info['item_type'], 1)

                        msg = f"拍卖结束！恭喜道友【{winner_name}】以 {price} 灵石的价格成功拍下【{auction_result['item_name']}】！"

                    await self._broadcast_to_groups(msg, "拍卖结果")
                    return # 结束监控
        except Exception as e:
            logger.error(f"向群 {group_id} 广播消息失败: {e}")

    async def _broadcast_to_groups(self, msg: str, title: str = "公告"):
        """向所有活跃群组广播消息"""
        if not hasattr(self.plugin_instance, 'groups') or not self.plugin_instance.groups:
            return

        for group_id in self.plugin_instance.groups:
            if "35001036638" in str(group_id):
                continue
            logger.info(group_id)
            try:
                if self.plugin_instance.xiu_config.img:
                    pic = await get_msg_pic(msg, title)
                    message_chain = MessageChain([Image.fromFileSystem(str(pic))])
                else:
                    message_chain = MessageChain(msg)

                await self.context.send_message(group_id, message_chain)
                await asyncio.sleep(0.5) # 防止风控
            except Exception as e:
                logger.error(f"向群 {group_id} 广播消息失败: {e}")

    async def _refresh_market_task(self):
        """刷新坊市商品，基于goods.json"""
        try:
            # v-- 这是本次修正的核心：从 goods.json 读取商品池 --v
            goods_data = self.plugin_instance.XiuXianService.get_goods_data()
            if not goods_data:
                logger.warning("坊市刷新失败：无法从data_manager获取到goods.json的数据。")
                return

            # 从商品池中随机抽取一部分作为当日商品
            num_of_items_to_sell = 20 # 每日上架20种商品

            # 如果总商品数量少于20，则全部上架
            if len(goods_data) < num_of_items_to_sell:
                items_for_sale_keys = list(goods_data.keys())
            else:
                items_for_sale_keys = random.sample(list(goods_data.keys()), num_of_items_to_sell)

            refreshed_market = {}
            for key in items_for_sale_keys:
                item_info = goods_data[key]
                item_info['id'] = key
                # 为商品添加随机库存和价格浮动
                item_info['quantity'] = random.randint(1, 10)
                price_float = random.uniform(0.8, 1.2)
                item_info['price'] = int(item_info.get('price', 100) * price_float)
                refreshed_market[item_info['name']] = item_info
            # ^-- 这是本次修正的核心 --^

            self.plugin_instance.market_goods = refreshed_market
            logger.info(f"坊市已刷新，本次从goods.json上架 {len(refreshed_market)} 件商品。")
        except Exception as e:
            logger.error(f"坊市刷新任务执行失败: {e}")

    async def _daily_reset_tasks(self):
        try:
            self.service.singh_remake()
            logger.info("每日修仙签到重置成功！")
            self.plugin_instance.refreshnum = {}
            logger.info("用户悬赏令刷新次数重置成功")
        except Exception as e:
            logger.error(f"每日0点重置任务聚合执行失败: {e}")

    async def _sect_materials_update_task(self):
        try:
            all_sects = self.service.get_all_sects_id_scale()
            if not all_sects: return
            
            sect_config = self.service.get_sect_config()
            rate = sect_config.get("发放宗门资材", {}).get("倍率", 1)
            
            for sect_id, sect_scale, _ in all_sects:
                materials_to_add = int(sect_scale * rate)
                self.service.update_sect_materials(sect_id=sect_id, sect_materials=materials_to_add, key=1)
            logger.info('已更新所有宗门的资材')
        except Exception as e:
            logger.error(f"更新宗门资材任务执行失败: {e}")

    async def _create_world_boss_task(self):
        """【修正版】定时生成世界BOSS并写入数据库及内存"""
        logger.info("定时任务：开始尝试生成世界BOSS...")

        # plugin_instance 持有当前的 world_boss 数据
        if self.plugin_instance.world_boss:
            logger.info("已有世界BOSS存在，本次生成任务跳过。")
            return {"success": False, "message": "已有世界BOSS存在，无法重复生成。"}


        try:
            # 1. 调用 service 生成BOSS的完整信息模板
            # self.service 是 XiuxianService 的实例
            boss_info_template = self.service.create_boss()
            if not boss_info_template:
                logger.error("生成BOSS模板失败，任务中止。")
                return {"success": False, "message": "生成BOSS模板失败。"}

            # 2. 调用 service 将BOSS信息存入数据库，并获取数据库中的主键ID
            # spawn_new_boss 方法需要接收完整的 boss_info_template
            boss_db_id = self.service.spawn_new_boss(boss_info_template) # 确保 spawn_new_boss 能处理所有新字段
            if not boss_db_id:
                logger.error("将BOSS存入数据库失败，任务中止。")
                return {"success": False, "message": "BOSS数据存储失败。"}

            logger.info(f"已生成新的世界BOSS【{boss_info_template['name']}】(境界: {boss_info_template['jj']})，数据库ID: {boss_db_id}")

            # 3. 从数据库重新获取一次，确保数据一致性，并作为内存中的当前BOSS
            # 或者，可以直接使用 boss_info_template 并补充数据库ID
            # 为了简单和一致，推荐从数据库获取
            self.plugin_instance.world_boss = self.service.get_active_boss()
            if not self.plugin_instance.world_boss:
                logger.error("存入数据库后未能成功获取BOSS信息，请检查 get_active_boss 方法！")
                return {"success": False, "message": "BOSS数据同步失败。"}


            # 4. 向所有活跃群组广播BOSS出现的消息
            if hasattr(self.plugin_instance, 'groups') and self.plugin_instance.groups:
                # 使用内存中（刚从数据库同步的）BOSS信息来构建消息
                current_boss_for_broadcast = self.plugin_instance.world_boss
                msg_broadcast = f"警报！{current_boss_for_broadcast['jj']}境界的【{current_boss_for_broadcast['name']}】已降临仙界，请各位道友速去讨伐！\n(HP: {current_boss_for_broadcast['hp']}, ATK: {current_boss_for_broadcast['atk']})"

                await self._broadcast_to_groups(msg_broadcast, "世界BOSS降临") # 调用你已有的广播方法
                logger.info(f"已向 {len(self.plugin_instance.groups)} 个群组广播了BOSS降临消息。")
            else:
                logger.info("没有配置活跃群组，BOSS生成消息未广播。")

            return {"success": True, "message": f"世界BOSS【{self.plugin_instance.world_boss['name']}】已成功生成并广播！"}

        except Exception as e:
            logger.error(f"生成或广播世界BOSS任务执行失败: {e}", exc_info=True)
            # 发生错误时，确保清理可能已部分创建的BOSS，避免状态不一致
            if hasattr(self.plugin_instance, 'world_boss') and self.plugin_instance.world_boss and 'id' in self.plugin_instance.world_boss:
                self.service.delete_boss(self.plugin_instance.world_boss['id'])
            self.plugin_instance.world_boss = None
            return {"success": False, "message": f"生成世界BOSS时发生内部错误: {e}"}
