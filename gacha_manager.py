# astrbot_plugin_xiuxian/gacha_manager.py

import random
from astrbot.api import logger
from .item_manager import Items # 用于获取神通的详细信息
from .config import XiuConfig # 用于获取卡池配置
from .service import XiuxianService # 用于扣除灵石、添加物品等

class GachaManager:
    def __init__(self, service: XiuxianService, items_manager: Items, xiu_config: XiuConfig):
        self.service = service
        self.items_manager = items_manager # Items 实例
        self.xiu_config = xiu_config       # XiuConfig 实例
        self.all_shengtongs = self.items_manager.get_data_by_item_type(['神通'])
        
        # 预处理神通数据，按类型和稀有度（level）分层，并计算权重
        self.prepared_shengtongs = self._prepare_shengtong_pool()

    def _get_shengtong_level_weight(self, level_value: int) -> int:
        """
        根据神通的 origin_level 值（越小越稀有）返回其在抽奖池中的权重。
        """
        if 1 <= level_value <= 10: return 1
        if 11 <= level_value <= 20: return 3
        if 21 <= level_value <= 23: return 3
        if 24 <= level_value <= 26: return 9
        if 27 <= level_value <= 32: return 15
        if 33 <= level_value <= 39: return 30
        if 40 <= level_value <= 50: return 50
        logger.warning(f"神通的 origin_level 值 {level_value} 超出预期范围 (1-50)，使用默认最低权重1。")
        return 1 # 对于超出预期范围的level，给予最低权重

    def _prepare_shengtong_pool(self) -> dict:
        """
        加载并预处理神通数据，按skill_type分类，并为每个神通计算抽奖权重。
        现在使用 st_data.get('origin_level') 来获取原始等级数值。
        """
        prepared = {
            "attack": [],
            "support_debuff": [],
            "dot_control": []
        }
        if not self.all_shengtongs:
            logger.warning("神通数据为空，万法宝鉴可能无法正确抽取神通。")
            return prepared

        for st_id, st_data in self.all_shengtongs.items():
            skill_type = st_data.get('skill_type')
            
            # --- 修改点：使用 origin_level ---
            origin_level_val = st_data.get('origin_level') # 这个应该是您添加的，保证是数字
            # --- 结束修改点 ---

            if origin_level_val is None: # 理论上不会发生，因为您设置了默认值1
                logger.warning(f"神通 {st_data.get('name', st_id)} 缺少 'origin_level' 字段，将使用默认最高level值处理。")
                origin_level_val = 50 # 假设50是最高（最不稀有）的level
            
            # 确保 origin_level_val 是整数
            try:
                level_val_for_weight = int(origin_level_val)
            except (ValueError, TypeError):
                logger.warning(f"神通 {st_data.get('name', st_id)} 的 'origin_level' 值 '{origin_level_val}' 不是有效整数，将使用默认最高level值处理。")
                level_val_for_weight = 50

            weight = self._get_shengtong_level_weight(level_val_for_weight)
            
            item_entry = {
                "id": st_id,
                "name": st_data.get('name', f"未知神通{st_id}"),
                "level": level_val_for_weight, # 这里可以存处理过的整数level，或原始的origin_level，取决于后续是否需要
                "weight": weight,
                "data": st_data # 存储完整的神通数据，包含 'origin_level' 和转换后的 'level'/'rank'
            }

            if skill_type == 1:
                prepared["attack"].append(item_entry)
            elif skill_type == 3:
                prepared["support_debuff"].append(item_entry)
            elif skill_type == 2 or skill_type == 4:
                prepared["dot_control"].append(item_entry)
            else:
                logger.warning(f"未知技能类型 {skill_type} for 神通 {st_id}")
        
        for category in prepared:
            prepared[category].sort(key=lambda x: x['weight'])

        return prepared


    def _weighted_random_choice(self, items_with_weights: list) -> dict | None:
        """
        根据权重随机选择一个物品。
        :param items_with_weights: 列表，每个元素是字典，必须包含 "weight" 键和物品信息。
                                   例如: [{"id": "1", "name": "A", "weight": 10}, {"id": "2", "name": "B", "weight": 1}]
        :return: 选中的物品字典，或 None (如果列表为空或总权重为0)
        """
        if not items_with_weights:
            return None

        total_weight = sum(item['weight'] for item in items_with_weights)
        if total_weight <= 0:
            # 如果所有物品权重都是0，则均等概率选择一个
            if all(item['weight'] == 0 for item in items_with_weights):
                return random.choice(items_with_weights)
            return None # 或者抛出错误

        rand_val = random.uniform(0, total_weight)
        cumulative_weight = 0
        for item in items_with_weights:
            cumulative_weight += item['weight']
            if rand_val <= cumulative_weight:
                return item
        return items_with_weights[-1] # 理论上不会执行到这里，除非浮点数精度问题

    def _draw_single_item(self, pool_config: dict) -> dict:
        """
        执行一次单抽逻辑。
        :param pool_config: 特定卡池的配置字典。
        :return: 抽到的物品信息字典，包含 "category", "id", "name", "data" (原始物品数据)
        """
        # 1. 决定抽中的大类 (神通或灵石)
        category_rates = pool_config['item_categories_rate']
        rand_category = random.random()
        cumulative_rate = 0
        chosen_category = None
        for category, rate in category_rates.items():
            cumulative_rate += rate
            if rand_category <= cumulative_rate:
                chosen_category = category
                break

        if chosen_category == "shengtong":
            # 2a. 如果抽中神通，再决定神通类型
            shengtong_type_rates = pool_config['shengtong_type_rate']
            rand_st_type = random.random()
            cumulative_st_rate = 0
            chosen_st_type_key = None
            for st_type_key, rate in shengtong_type_rates.items():
                cumulative_st_rate += rate
                if rand_st_type <= cumulative_st_rate:
                    chosen_st_type_key = st_type_key
                    break

            # 2b. 从对应类型和稀有度的神通池中抽取
            if chosen_st_type_key and self.prepared_shengtongs.get(chosen_st_type_key):
                shengtong_pool_for_type = self.prepared_shengtongs[chosen_st_type_key]
                if shengtong_pool_for_type:
                    chosen_shengtong = self._weighted_random_choice(shengtong_pool_for_type)
                    if chosen_shengtong:
                        return {
                            "category": "shengtong",
                            "id": chosen_shengtong['id'],
                            "name": chosen_shengtong['name'],
                            "data": chosen_shengtong['data'] # 返回完整的神通数据
                        }
            # 如果上面步骤失败（如池子为空），则降级为灵石
            logger.warning(f"无法从神通池 {chosen_st_type_key} 中抽取神通，降级为灵石。")
            chosen_category = "lingshi" # 确保降级

        if chosen_category == "lingshi":
            # 3. 如果抽中灵石，从灵石奖励池中抽取
            lingshi_reward_pool = pool_config['lingshi_rewards']
            chosen_lingshi_tier = self._weighted_random_choice(lingshi_reward_pool)
            if chosen_lingshi_tier:
                amount = random.randint(chosen_lingshi_tier['amount_range'][0], chosen_lingshi_tier['amount_range'][1])
                return {
                    "category": "lingshi",
                    "id": "lingshi_reward", # 特殊ID
                    "name": f"{amount}灵石",
                    "data": {"amount": amount} # 存储具体数量
                }

        # 默认或降级情况：返回最低档灵石
        logger.error("万法宝鉴抽奖逻辑出现意外，返回默认灵石奖励。")
        min_lingshi_amount = pool_config['lingshi_rewards'][0]['amount_range'][0]
        return {
            "category": "lingshi", "id": "lingshi_reward", "name": f"{min_lingshi_amount}灵石", "data": {"amount": min_lingshi_amount}
        }

    def perform_gacha(self, user_id: str, pool_id: str, is_ten_pull: bool = False) -> dict:
        """
        执行抽奖 (单抽或十连)。
        :param user_id: 玩家ID
        :param pool_id: 卡池ID (例如 "wanfa_baojian")
        :param is_ten_pull: 是否是十连抽
        :return: 结果字典 {"success": bool, "message": str, "rewards": list | None}
        """
        pool_config = self.xiu_config.gacha_pools_config.get(pool_id)
        if not pool_config:
            return {"success": False, "message": "无效的卡池ID。"}

        cost = pool_config['multi_cost'] if is_ten_pull else pool_config['single_cost']

        # 1. 检查灵石是否足够
        user_info = self.service.get_user_message(user_id)
        if not user_info or user_info.stone < cost:
            return {"success": False, "message": f"灵石不足！本次抽取需要 {cost} 灵石。"}

        # 2. 扣除灵石 (事务性操作，如果后续发放失败应回滚，但这里简化)
        self.service.update_ls(user_id, cost, 2) # 2代表减少

        # 3. 执行抽奖
        num_pulls = 10 if is_ten_pull else 1
        rewards_list = []
        shengtong_obtained_in_ten_pull = False

        for _ in range(num_pulls):
            item = self._draw_single_item(pool_config)
            rewards_list.append(item)
            if item['category'] == "shengtong":
                shengtong_obtained_in_ten_pull = True

        # 4. 处理十连保底 (平滑替换版)
        if is_ten_pull and pool_config['ten_pull_guarantee']['enabled'] and not shengtong_obtained_in_ten_pull:
            logger.info(f"用户 {user_id} 十连抽未获得神通，触发保底机制。")
            # 找到一个可以被替换的奖励（优先替换灵石）
            replacement_candidate_index = -1
            min_value_for_replacement = float('inf') # 用于找到价值最低的

            for i, reward_item in enumerate(rewards_list):
                if reward_item['category'] in pool_config['ten_pull_guarantee']['replacement_priority']:
                    # 对于灵石，其"价值"就是其数量
                    current_value = reward_item['data'].get('amount', float('inf')) if reward_item['category'] == 'lingshi' else float('inf')
                    if current_value < min_value_for_replacement:
                        min_value_for_replacement = current_value
                        replacement_candidate_index = i

            if replacement_candidate_index != -1:
                # 从所有神通中（不限类型）按稀有度权重随机抽取一个作为保底
                # 为了简单，我们这里直接从所有品阶的神通中抽取，但可以限定为较低品阶
                all_st_for_guarantee = []
                for st_type_list in self.prepared_shengtongs.values():
                    all_st_for_guarantee.extend(st_type_list)

                if all_st_for_guarantee:
                    guaranteed_shengtong_info = self._weighted_random_choice(all_st_for_guarantee)
                    if guaranteed_shengtong_info:
                        guaranteed_item = {
                            "category": "shengtong",
                            "id": guaranteed_shengtong_info['id'],
                            "name": guaranteed_shengtong_info['name'],
                            "data": guaranteed_shengtong_info['data']
                        }
                        logger.info(f"保底替换：将第 {replacement_candidate_index+1} 个奖励替换为神通【{guaranteed_item['name']}】")
                        rewards_list[replacement_candidate_index] = guaranteed_item
                    else:
                        logger.error("保底触发，但无法从神通池中抽取保底神通！")
                else:
                     logger.error("保底触发，但神通池为空！")
            else:
                logger.warning("十连保底触发，但找不到合适的非神通奖励进行替换（例如全是神通了）。")


        # 5. 发放奖励到玩家背包/账户
        final_rewards_summary = []
        for reward_item in rewards_list:
            final_rewards_summary.append(reward_item['name'])
            if reward_item['category'] == "shengtong":
                # 神通是物品，需要添加到背包
                # 假设神通在items.json中定义，并且类型是"神通"
                # item_manager.get_data_by_item_id(reward_item['id']) 会返回其详细信息
                shengtong_data = reward_item['data'] # 已经包含了完整数据
                self.service.add_item(user_id, int(reward_item['id']), shengtong_data.get('item_type', '神通'), 1)
            elif reward_item['category'] == "lingshi":
                # 灵石是直接增加到玩家账户 (注意：这里是增加抽到的灵石，不是消耗)
                self.service.update_ls(user_id, reward_item['data']['amount'], 1) # 1代表增加

        pull_type_msg = "十连召唤" if is_ten_pull else "召唤"
        message = f"恭喜道友进行{pull_type_msg}，从【万法宝鉴】中获得：\n" + "\n".join([f"- {name}" for name in final_rewards_summary])
        if is_ten_pull and pool_config['ten_pull_guarantee']['enabled'] and not shengtong_obtained_in_ten_pull and replacement_candidate_index != -1:
             message += "\n(十连保底已触发)"


        return {"success": True, "message": message, "rewards": rewards_list}
