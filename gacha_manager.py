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
        # self.all_shengtongs = self.items_manager.get_data_by_item_type(['神通'])
        # self.all_faqi = self.items_manager.get_data_by_item_type(['法器'])
        # self.all_fangju = self.items_manager.get_data_by_item_type(['防具'])
        # self.all_gongfa = self.items_manager.get_data_by_item_type(['功法'])
        # #
        # # # 预处理神通数据，按类型和稀有度（level）分层，并计算权重
        # self.prepared_shengtongs = self._prepare_shengtong_pool()
        # self.prepared_faqi = self._prepare_faqi_pool()
        # self.prepared_gongfa = self._prepare_gongfa_pool()
        # self.prepared_fangju = self._prepare_fangju_pool()

        # # 计算并存储各主要物品类型的总权重
        # self.total_weight_faqi = sum(item['weight'] for item in self.prepared_faqi) if self.prepared_faqi else 700
        # self.total_weight_gongfa = sum(
        #     item['weight'] for item in self.prepared_gongfa) if self.prepared_gongfa else 700
        # self.total_weight_fangju = sum(
        #     item['weight'] for item in self.prepared_fangju) if self.prepared_fangju else 700
        #
        # self.total_weight_shengtong_by_type = {
        #     'attack': sum(item['weight'] for item in self.prepared_shengtongs.get('attack', [])),
        #     'support_debuff': sum(
        #         item['weight'] for item in self.prepared_shengtongs.get('support_debuff', [])),
        #     'dot_control': sum(item['weight'] for item in self.prepared_shengtongs.get('dot_control', []))
        # }

    # def _prepare_shengtong_pool(self) -> dict:
    #     """
    #     加载并预处理神通数据，按skill_type分类，并为每个神通计算抽奖权重。
    #     现在使用 st_data.get('origin_level') 来获取原始等级数值。
    #     """
    #     prepared = {
    #         "attack": [],
    #         "support_debuff": [],
    #         "dot_control": []
    #     }
    #     if not self.all_shengtongs:
    #         logger.warning("神通数据为空，万法宝鉴可能无法正确抽取神通。")
    #         return prepared
    #
    #     for st_id, st_data in self.all_shengtongs.items():
    #         skill_type = st_data.get('skill_type')
    #
    #         # --- 修改点：使用 origin_level ---
    #         origin_level_val = st_data.get('origin_level') # 这个应该是您添加的，保证是数字
    #         # --- 结束修改点 ---
    #
    #         if origin_level_val is None: # 理论上不会发生，因为您设置了默认值1
    #             logger.warning(f"神通 {st_data.get('name', st_id)} 缺少 'origin_level' 字段，将使用默认最高level值处理。")
    #             origin_level_val = 50 # 假设50是最高（最不稀有）的level
    #
    #         # 确保 origin_level_val 是整数
    #         try:
    #             level_val_for_weight = int(origin_level_val)
    #         except (ValueError, TypeError):
    #             logger.warning(f"神通 {st_data.get('name', st_id)} 的 'origin_level' 值 '{origin_level_val}' 不是有效整数，将使用默认最高level值处理。")
    #             level_val_for_weight = 50
    #
    #         weight = self.items_manager._get_shengtong_level_weight(level_val_for_weight)
    #
    #         item_entry = {
    #             "id": st_id,
    #             "name": st_data.get('name', f"未知神通{st_id}"),
    #             "level": level_val_for_weight, # 这里可以存处理过的整数level，或原始的origin_level，取决于后续是否需要
    #             "weight": weight,
    #             "data": st_data # 存储完整的神通数据，包含 'origin_level' 和转换后的 'level'/'rank'
    #         }
    #
    #         if skill_type == 1:
    #             prepared["attack"].append(item_entry)
    #         elif skill_type == 3:
    #             prepared["support_debuff"].append(item_entry)
    #         elif skill_type == 2 or skill_type == 4:
    #             prepared["dot_control"].append(item_entry)
    #         else:
    #             logger.warning(f"未知技能类型 {skill_type} for 神通 {st_id}")
    #
    #     for category in prepared:
    #         prepared[category].sort(key=lambda x: x['weight'])
    #
    #     return prepared


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


    # def _prepare_faqi_pool(self) -> list:
    #     """
    #     加载并预处理法器数据，为每个法器计算抽奖权重。
    #     法器的 'rank' 字段是整数，'level' 字段是品阶字符串。
    #     """
    #     prepared_faqi_list = []
    #     if not self.all_faqi:
    #         logger.warning("法器数据为空，神兵宝库可能无法正确抽取法器。")
    #         return prepared_faqi_list
    #
    #     for faqi_id, faqi_data in self.all_faqi.items():
    #         rank_val = faqi_data.get('rank')  # 这是整数 rank
    #         if rank_val is None:
    #             logger.warning(f"法器 {faqi_data.get('name', faqi_id)} 缺少 'rank' 字段，跳过。")
    #             continue
    #
    #         try:
    #             rank_int = int(rank_val)
    #         except (ValueError, TypeError):
    #             logger.warning(f"法器 {faqi_data.get('name', faqi_id)} 的 'rank' 值 '{rank_val}' 不是有效整数，跳过。")
    #             continue
    #
    #         weight = self.items_manager._get_faqi_rank_weight(rank_int)
    #         item_entry = {
    #             "id": faqi_id,
    #             "name": faqi_data.get('name', f"未知法器{faqi_id}"),
    #             "rank": rank_int,  # 存储整数 rank，用于保底判断
    #             "weight": weight,
    #             "data": faqi_data  # 存储完整的法器数据
    #         }
    #         prepared_faqi_list.append(item_entry)
    #
    #     # 按权重排序是可选的，但有助于调试或特定抽奖策略
    #     prepared_faqi_list.sort(key=lambda x: x['weight'])
    #     return prepared_faqi_list

    def _draw_single_item(self, pool_config: dict, pool_id: str) -> dict:  # 添加 pool_id 参数
        """
        执行一次单抽逻辑。
        :param pool_config: 特定卡池的配置字典。
        :param pool_id: 当前卡池的ID (e.g., "wanfa_baojian", "shenbing_baoku")
        :return: 抽到的物品信息字典，包含 "category", "id", "name", "data" (原始物品数据)
        """
        category_rates = pool_config['item_categories_rate']
        rand_category = random.random()
        cumulative_rate = 0
        chosen_category = None
        for category, rate in category_rates.items():
            cumulative_rate += rate
            if rand_category <= cumulative_rate:
                chosen_category = category
                break

        main_item_type_for_pool = pool_config['ten_pull_guarantee']['guaranteed_item_type']
        item_to_return = None

        if chosen_category == main_item_type_for_pool:
            if pool_id == "wanfa_baojian" and main_item_type_for_pool == "shengtong":
                shengtong_type_rates = pool_config['shengtong_type_rate']
                rand_st_type = random.random()
                cumulative_st_rate = 0
                chosen_st_type_key = None
                for st_type_key, rate in shengtong_type_rates.items():
                    cumulative_st_rate += rate
                    if rand_st_type <= cumulative_st_rate:
                        chosen_st_type_key = st_type_key
                        break
                if chosen_st_type_key and self.items_manager.prepared_shengtongs_pool_by_type.get(chosen_st_type_key):
                    shengtong_pool_for_type = self.items_manager.prepared_shengtongs_pool_by_type[chosen_st_type_key]
                    if shengtong_pool_for_type:
                        chosen_shengtong = self._weighted_random_choice(shengtong_pool_for_type)
                        if chosen_shengtong:
                            item_to_return = {
                                "category": "shengtong",  # 确保 category 与 main_item_type_for_pool 一致
                                "id": chosen_shengtong['id'],
                                "name": chosen_shengtong['name'],
                                "data": chosen_shengtong['data']
                            }
                if not item_to_return:  # 如果神通抽取失败
                    logger.warning(f"无法从神通池 {chosen_st_type_key} 中抽取神通，降级为灵石。")
                    chosen_category = "lingshi"  # 强制降级

            elif pool_id == "shenbing_baoku" and main_item_type_for_pool == "faqi":  # 新增法器池逻辑
                if self.items_manager.prepared_faqi_pool:
                    chosen_faqi = self._weighted_random_choice(self.items_manager.prepared_faqi_pool)
                    if chosen_faqi:
                        item_to_return = {
                            "category": "faqi",  # 确保 category 与 main_item_type_for_pool 一致
                            "id": chosen_faqi['id'],
                            "name": chosen_faqi['name'],
                            "data": chosen_faqi['data']
                        }
                if not item_to_return:  # 如果法器抽取失败
                    logger.warning(f"无法从法器池中抽取法器，降级为灵石。")
                    chosen_category = "lingshi"  # 强制降级
            elif pool_id == "wanggu_gongfa_ge" and main_item_type_for_pool == "gongfa": # 新增功法池逻辑
                if self.items_manager.prepared_gongfa_pool:
                    chosen_gongfa = self._weighted_random_choice(self.items_manager.prepared_gongfa_pool)
                    if chosen_gongfa:
                        item_to_return = {
                            "category": "gongfa", # 确保 category 与 main_item_type_for_pool 一致
                            "id": chosen_gongfa['id'],
                            "name": chosen_gongfa['name'],
                            "data": chosen_gongfa['data']
                        }
                if not item_to_return: # 如果功法抽取失败
                    logger.warning(f"无法从功法池中抽取功法，降级为灵石。")
                    chosen_category = "lingshi" # 强制降级
            elif pool_id == "xuanjia_baodian" and main_item_type_for_pool == "fangju":  # 新增防具池逻辑
                if self.items_manager.prepared_fangju_pool:
                    chosen_fangju = self._weighted_random_choice(self.items_manager.prepared_fangju_pool)
                    if chosen_fangju:
                        item_to_return = {
                            "category": "fangju",  # 确保 category 与 main_item_type_for_pool 一致
                            "id": chosen_fangju['id'],
                            "name": chosen_fangju['name'],
                            "data": chosen_fangju['data']
                        }
                if not item_to_return:  # 如果防具抽取失败
                    logger.warning(f"无法从防具池中抽取防具，降级为灵石。")
                    chosen_category = "lingshi"  # 强制降级

            # --- 在这里为后续的功法池、防具池添加 elif ---

            if item_to_return:
                return item_to_return

        # 如果抽中的是灵石，或者主要物品抽取失败后降级为灵石
        if chosen_category == "lingshi":
            lingshi_reward_pool = pool_config['lingshi_rewards']
            chosen_lingshi_tier = self._weighted_random_choice(lingshi_reward_pool)
            if chosen_lingshi_tier:
                amount = random.randint(chosen_lingshi_tier['amount_range'][0], chosen_lingshi_tier['amount_range'][1])
                return {
                    "category": "lingshi",
                    "id": "lingshi_reward",
                    "name": f"{amount}灵石",
                    "data": {"amount": amount}
                }

        # 最终的降级/默认情况
        logger.error(f"卡池 {pool_id} 抽奖逻辑出现意外或多次降级，返回默认最低灵石奖励。")
        min_lingshi_amount = pool_config['lingshi_rewards'][0]['amount_range'][0]  # 取配置中最低档灵石的最小值
        return {
            "category": "lingshi", "id": "lingshi_reward", "name": f"{min_lingshi_amount}灵石",
            "data": {"amount": min_lingshi_amount}
        }

    def perform_gacha(self, user_id: str, pool_id: str, is_ten_pull: bool = False) -> dict:
        pool_config = self.xiu_config.gacha_pools_config.get(pool_id)
        if not pool_config:
            return {"success": False, "message": "无效的卡池ID。"}

        cost = pool_config['multi_cost'] if is_ten_pull else pool_config['single_cost']
        user_info = self.service.get_user_message(user_id)
        if not user_info or user_info.stone < cost:
            return {"success": False, "message": f"灵石不足！本次抽取需要 {cost} 灵石。"}

        self.service.update_ls(user_id, cost, 2)

        num_pulls = 10 if is_ten_pull else 1
        rewards_list = []
        # 修改：shengtong_obtained_in_ten_pull -> obtained_guaranteed_type_in_ten_pull
        obtained_guaranteed_type_in_ten_pull = False
        guaranteed_item_type_for_this_pool = pool_config['ten_pull_guarantee']['guaranteed_item_type']

        for _ in range(num_pulls):
            item = self._draw_single_item(pool_config, pool_id)  # 传递 pool_id
            rewards_list.append(item)
            if item['category'] == guaranteed_item_type_for_this_pool:  # 检查是否抽到了该池的保底类型
                obtained_guaranteed_type_in_ten_pull = True

        # 处理十连保底
        if is_ten_pull and pool_config['ten_pull_guarantee']['enabled'] and not obtained_guaranteed_type_in_ten_pull:
            logger.info(
                f"用户 {user_id} 在卡池 {pool_id} 十连抽未获得类型为 {guaranteed_item_type_for_this_pool} 的物品，触发保底。")

            replacement_candidate_index = -1
            min_value_for_replacement = float('inf')
            for i, reward_item in enumerate(rewards_list):
                if reward_item['category'] in pool_config['ten_pull_guarantee']['replacement_priority']:
                    current_value = reward_item['data'].get('amount', float('inf')) if reward_item[
                                                                                           'category'] == 'lingshi' else float(
                        'inf')
                    if current_value < min_value_for_replacement:
                        min_value_for_replacement = current_value
                        replacement_candidate_index = i

            if replacement_candidate_index != -1:
                guaranteed_item_pool_for_selection = []
                min_rank_or_level_for_guarantee = pool_config['ten_pull_guarantee'].get('guaranteed_min_rank_value',
                                                                                        99)  # 默认一个很高的值

                if pool_id == "wanfa_baojian" and guaranteed_item_type_for_this_pool == "shengtong":
                    # 神通的保底是任意神通，不按稀有度筛选（或按需调整）
                    for st_type_list in self.items_manager.prepared_shengtongs_pool_by_type.values():
                        guaranteed_item_pool_for_selection.extend(st_type_list)
                elif pool_id == "shenbing_baoku" and guaranteed_item_type_for_this_pool == "faqi":
                    # 法器保底，筛选 rank <= guaranteed_min_rank_value
                    guaranteed_item_pool_for_selection = [
                        item for item in self.items_manager.prepared_faqi_pool if item['rank'] <= min_rank_or_level_for_guarantee
                    ]
                elif pool_id == "wanggu_gongfa_ge" and guaranteed_item_type_for_this_pool == "gongfa":  # 新增功法保底
                    # 功法保底，筛选 origin_level <= guaranteed_min_rank_value
                    guaranteed_item_pool_for_selection = [
                        item for item in self.items_manager.prepared_gongfa_pool if
                        item['origin_level'] <= min_rank_or_level_for_guarantee
                    ]
                elif pool_id == "xuanjia_baodian" and guaranteed_item_type_for_this_pool == "fangju": # 新增防具保底
                    # 防具保底，筛选 rank <= guaranteed_min_rank_value
                    guaranteed_item_pool_for_selection = [
                        item for item in self.items_manager.prepared_fangju_pool if
                        item['rank'] <= min_rank_or_level_for_guarantee
                    ]
                # --- 在这里为后续的功法池、防具池添加 elif ---

                if guaranteed_item_pool_for_selection:
                    chosen_guaranteed_item_info = self._weighted_random_choice(guaranteed_item_pool_for_selection)
                    if chosen_guaranteed_item_info:
                        guaranteed_item_to_add = {
                            "category": guaranteed_item_type_for_this_pool,
                            "id": chosen_guaranteed_item_info['id'],
                            "name": chosen_guaranteed_item_info['name'],
                            "data": chosen_guaranteed_item_info['data']
                        }
                        logger.info(
                            f"保底替换：将第 {replacement_candidate_index + 1} 个奖励替换为 {guaranteed_item_type_for_this_pool}【{guaranteed_item_to_add['name']}】")
                        rewards_list[replacement_candidate_index] = guaranteed_item_to_add
                    else:
                        logger.error(f"保底触发，但无法从 {guaranteed_item_type_for_this_pool} 池中抽取保底物品！")
                else:
                    logger.error(f"保底触发，但 {guaranteed_item_type_for_this_pool} 池为空或不满足保底稀有度！")
            else:
                logger.warning(f"十连保底触发，但找不到合适的非 {guaranteed_item_type_for_this_pool} 奖励进行替换。")

        # 发放奖励
        final_rewards_summary = []
        for reward_item in rewards_list:
            final_rewards_summary.append(reward_item['name'])
            if reward_item['category'] in ["shengtong", "faqi", "gongfa", "fangju"]:  # 扩展到法器
                item_data = reward_item['data']
                actual_item_type = item_data.get('item_type', '未知')  # "神通" 或 "法器"
                self.service.add_item(user_id, int(reward_item['id']), actual_item_type, 1)
            elif reward_item['category'] == "lingshi":
                self.service.update_ls(user_id, reward_item['data']['amount'], 1)

        pull_type_msg = "十连铸造" if is_ten_pull and pool_id == "xuanjia_baodian" else "十连参悟" if is_ten_pull and pool_id == "wanggu_gongfa_ge" else "十连寻访" if is_ten_pull else "铸造" if pool_id == "xuanjia_baodian" else "参悟" if pool_id == "wanggu_gongfa_ge" else "寻访"
        message = f"恭喜道友进行{pull_type_msg}，从【{pool_config.get('name', '神秘宝库')}】中获得：\n" + "\n".join(
            [f"- {name}" for name in final_rewards_summary])

        # 调整保底提示的触发条件
        if is_ten_pull and pool_config['ten_pull_guarantee'][
            'enabled'] and not obtained_guaranteed_type_in_ten_pull and replacement_candidate_index != -1:
            message += f"\n(十连保底已触发，获得{guaranteed_item_type_for_this_pool}!)"

        return {"success": True, "message": message, "rewards": rewards_list}

    # def _prepare_gongfa_pool(self) -> list:
    #     """
    #     加载并预处理主修功法数据，为每个功法计算抽奖权重。
    #     主修功法的 'origin_level' 字段是原始等级整数。
    #     """
    #     prepared_gongfa_list = []
    #     if not self.all_gongfa:
    #         logger.warning("主修功法数据为空，万古功法阁可能无法正确抽取功法。")
    #         return prepared_gongfa_list
    #
    #     for gongfa_id, gongfa_data in self.all_gongfa.items():
    #         origin_level_val = gongfa_data.get('origin_level')  # 这是原始的等级数值
    #         if origin_level_val is None:
    #             logger.warning(f"主修功法 {gongfa_data.get('name', gongfa_id)} 缺少 'origin_level' 字段，跳过。")
    #             continue
    #
    #         try:
    #             level_int = int(origin_level_val)
    #         except (ValueError, TypeError):
    #             logger.warning(
    #                 f"主修功法 {gongfa_data.get('name', gongfa_id)} 的 'origin_level' 值 '{origin_level_val}' 不是有效整数，跳过。")
    #             continue
    #
    #         weight = self.items_manager._get_gongfa_origin_level_weight(level_int)
    #         item_entry = {
    #             "id": gongfa_id,
    #             "name": gongfa_data.get('name', f"未知功法{gongfa_id}"),
    #             "origin_level": level_int,  # 存储原始等级用于保底判断
    #             "weight": weight,
    #             "data": gongfa_data  # 存储完整的功法数据
    #         }
    #         prepared_gongfa_list.append(item_entry)
    #
    #     prepared_gongfa_list.sort(key=lambda x: x['weight'])
    #     return prepared_gongfa_list

    # def _prepare_fangju_pool(self) -> list:
    #     """
    #     加载并预处理防具数据，为每个防具计算抽奖权重。
    #     防具的 'rank' 字段是整数。
    #     """
    #     prepared_fangju_list = []
    #     if not self.all_fangju:
    #         logger.warning("防具数据为空，玄甲宝殿可能无法正确抽取防具。")
    #         return prepared_fangju_list
    #
    #     for fangju_id, fangju_data in self.all_fangju.items():
    #         rank_val = fangju_data.get('rank')  # 这是整数 rank
    #         if rank_val is None:
    #             logger.warning(f"防具 {fangju_data.get('name', fangju_id)} 缺少 'rank' 字段，跳过。")
    #             continue
    #
    #         try:
    #             rank_int = int(rank_val)
    #         except (ValueError, TypeError):
    #             logger.warning(
    #                 f"防具 {fangju_data.get('name', fangju_id)} 的 'rank' 值 '{rank_val}' 不是有效整数，跳过。")
    #             continue
    #
    #         weight = self.items_manager._get_fangju_rank_weight(rank_int)
    #         item_entry = {
    #             "id": fangju_id,
    #             "name": fangju_data.get('name', f"未知防具{fangju_id}"),
    #             "rank": rank_int,  # 存储整数 rank，用于保底判断
    #             "weight": weight,
    #             "data": fangju_data  # 存储完整的防具数据
    #         }
    #         prepared_fangju_list.append(item_entry)
    #
    #     prepared_fangju_list.sort(key=lambda x: x['weight'])
    #     return prepared_fangju_list