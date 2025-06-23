# astrbot_plugin_xiuxian/alchemy_manager.py

import random
from .item_manager import Items
from .config import XiuConfig, USERRANK
from astrbot.api import logger
import json

class AlchemyManager:
    """炼丹管理器，负责处理炼丹的核心逻辑"""

    def __init__(self, service):
        self.items_manager = Items()
        self.config = XiuConfig()
        self.service = service
        self.all_recipes_with_key = self.items_manager.get_data_by_item_type(['合成丹药'])
        self.all_recipes = list(self.all_recipes_with_key.values())


    def get_all_recipes(self) -> list:
        """获取所有丹方"""
        return self.all_recipes

    def find_possible_recipes(self, user_backpack: dict) -> dict:
        """
        根据用户背包里的药材，找出所有可能炼制的丹药配方
        """
        if not user_backpack: # 如果背包为空，直接返回
            return {}

        # 1. 从完整背包中提取药材的初始物理数量
        initial_backpack_quantities = self._get_user_backpack_herb_quantities(user_backpack)
        if not initial_backpack_quantities: # 如果没有药材，也直接返回
            return {}
            
        # 2. 将背包药材按药力类型分类 (这个方法内部会处理药材ID到药力类型的转换)
        user_herbs_by_type = self._get_user_herbs_by_type(user_backpack)

        possible_recipes = {}
        for pill_id, recipe in self.all_recipes_with_key.items():
            required_materials_config = recipe.get("elixir_config", {})
            if not required_materials_config: # 如果丹方不需要材料，跳过
                continue

            # 3. 使用与 craft_pill 相同的逻辑来判断是否能凑齐材料
            # 注意：这里传递的是 initial_backpack_quantities，因为每次检查丹方都是独立的
            can_craft_this_pill, consumed_materials_for_this_pill = self._find_materials_for_recipe(
                required_materials_config,
                user_herbs_by_type,
                initial_backpack_quantities # 每次都用完整的背包初始量去判断
            )

            if can_craft_this_pill:
                # 找到了一个可以炼制的丹药
                # 构建所需材料的显示字符串
                materials_display_list = []
                for consumed_herb_id, consumed_num in consumed_materials_for_this_pill.items():
                    herb_info = self.items_manager.get_data_by_item_id(consumed_herb_id)
                    materials_display_list.append(f"{herb_info['name']}x{consumed_num}")

                possible_recipes[pill_id] = {
                    "name": recipe['name'],
                    "desc": recipe['desc'],
                    "materials_str": "、".join(materials_display_list) if materials_display_list else "无需特定药材",
                    "effect_desc": recipe.get('desc', '效果未知') # 单独提取效果描述，方便后续格式化
                }
        
        return possible_recipes
    
    def craft_pill(self, user_info, user_backpack: list, user_alchemy_info, recipe_name: str) -> dict:
        """
        【最终正确版】执行炼丹的核心逻辑（完全基于药材类型和药力）。
        """
        target_recipe = None
        target_pill_id = None
        for pill_id, recipe in self.all_recipes_with_key.items():
            if recipe['name'] == recipe_name:
                target_recipe = recipe
                target_pill_id = pill_id
                break

        if not target_recipe:
            return {"success": False, "message": f"未找到名为【{recipe_name}】的丹方。"}

        # 1. 检查炼丹炉
        furnace = next((self.items_manager.get_data_by_item_id(item.goods_id) 
                        for item in user_backpack if item.goods_type == '炼丹炉'), None)
        if not furnace:
            return {"success": False, "message": "炼丹需要先在背包中拥有一个炼丹炉！"}

        # 2. 检查修为消耗
        exp_cost = target_recipe.get("mix_exp", 0)
        if user_info.exp < exp_cost:
            return {"success": False, "message": f"炼丹需要消耗 {exp_cost} 修为，道友的修为不足！"}
            
        # 3. 检查药材和药力 (新逻辑)
        required_formula = {str(k): v for k, v in target_recipe.get("elixir_config", {}).items()}
        user_herbs_by_type = self._get_user_herbs_by_type(user_backpack)

        # Get initial quantities of all herbs in backpack
        initial_backpack_quantities = self._get_user_backpack_herb_quantities(user_backpack)

        # 调用智能匹配方法
        can_craft, materials_to_consume = self._find_materials_for_recipe(
            required_formula, user_herbs_by_type, initial_backpack_quantities
        )

        if not can_craft:
            # 给出更详细的缺失提示
            missing_info = []
            YAOCAI_TYPE_MAP = {"2": "生息", "3": "养气", "4": "炼气", "5": "聚元", "6": "凝神"}
            for r_type, r_power in required_formula.items():
                type_name = YAOCAI_TYPE_MAP.get(r_type, f"类型{r_type}")
                
                # 计算玩家拥有的该类型总药力
                available_power = 0
                if r_type in user_herbs_by_type:
                    for herb in user_herbs_by_type[r_type]:
                        available_power += herb['power'] * herb['num']
                
                if available_power < r_power:
                    missing_info.append(f"【{type_name}】药力不足 (需要 {r_power}, 拥有 {available_power})")

            if missing_info:
                return {"success": False, "message": f"炼制【{recipe_name}】失败！\n原因: {', '.join(missing_info)}"}
            else: # 理论上不会走到这里，但作为保险
                return {"success": False, "message": f"药力或药材不满足炼制【{recipe_name}】的要求！"}

        # 4. 计算产出和经验 (这部分逻辑不变)
        product_num = 1 + furnace.get("buff", 0) + user_alchemy_info.fire_level
        alchemy_record = json.loads(user_alchemy_info.alchemy_record)
        current_craft_count = alchemy_record.get(target_pill_id, {}).get('num', 0)
        max_exp_craft_count = target_recipe.get("mix_all", 100)
        
        exp_gain = 0
        if current_craft_count < max_exp_craft_count:
            exp_eligible_num = min(product_num, max_exp_craft_count - current_craft_count)
            exp_gain = target_recipe.get("mix_exp", 10) * exp_eligible_num
        
        # 5. 构建返回结果
        consume = {
            "exp": exp_cost,
            "materials": materials_to_consume # 这是 {药材ID: 数量} 的字典
        }
        produce = {
            "item_id": int(target_pill_id),
            "num": product_num
        }
        
        materials_str_list = [f"【{self.items_manager.get_data_by_item_id(mat_id)['name']}】x{num}" for mat_id, num in materials_to_consume.items()]
            
        message = f"你消耗了{', '.join(materials_str_list)}和{exp_cost}点修为...\n"
        message += f"经过一番努力，丹炉中霞光一闪，成功炼制出【{recipe_name}】x{product_num}！"
        if exp_gain > 0:
            message += f"\n获得炼丹经验 {exp_gain} 点。"
        else:
            message += f"\n此丹药已炼制多次，无法再获得经验。"
            
        return {
            "success": True, 
            "message": message,
            "consume": consume,
            "produce": produce,
            "exp_gain": exp_gain
        }

    def _bulk_use_check(self, goods_info: dict, use_num: int, user_daily_used: int, user_total_used: int) -> int:
        """检查批量使用时，最终能成功使用的丹药数量"""
        daily_limit = goods_info.get('day_num', 999) # 每日使用上限
        total_limit = goods_info.get('all_num', 999) # 终生使用上限 (耐药性)

        day_can_use = max(0, daily_limit - user_daily_used)
        all_can_use = max(0, total_limit - user_total_used)

        # 最终可使用的数量是 计划使用数、每日剩余、终生剩余 这三者中的最小值
        return min(use_num, day_can_use, all_can_use)

    def use_pill(self, user_info, user_backpack_item, pill_info: dict, use_num: int = 1) -> dict:
        """
        处理使用丹药的核心逻辑
        :param user_info: 用户的完整信息
        :param user_backpack_item: 用户背包中对应的该丹药的条目
        :param pill_info: 丹药的物品信息
        :param use_num: 计划使用的数量
        :return: 一个包含结果的字典
        """
        user_rank = USERRANK.get(user_info.level, 99)
        #pill_rank = pill_info.get('rank', 0)
        pill_name = pill_info['name']

        required_level_name = pill_info.get("境界", "江湖好手")
        required_rank = USERRANK.get(required_level_name, 99)

        user_id = user_info.user_id

        # 1. 检查使用条件
        if user_rank > required_rank:
            return {"success": False, "message": f"【{pill_name}】需要达到【{required_level_name}】境界才能使用！"}

        # 2. 检查使用数量和限制
        # 从背包物品信息中获取已使用次数
        user_daily_used = user_backpack_item.day_num
        user_total_used = user_backpack_item.all_num

        final_use_num = self._bulk_use_check(pill_info, use_num, user_daily_used, user_total_used)

        if final_use_num <= 0:
            msg = f"【{pill_name}】已达到使用上限（每日或终生），无法再使用。"
            # 可以在这里补充更详细的提示，比如具体是哪个上限
            if user_daily_used >= pill_info.get('day_num', 999):
                msg += " (今日已达上限)"
            elif user_total_used >= pill_info.get('all_num', 999):
                msg += " (已产生耐药性)"
            return {"success": False, "message": msg}

        # 3. 根据丹药类型执行效果
        buff_type = pill_info.get('buff_type')
        buff_value = pill_info.get('buff', 0)

        result_data = {
            "success": True,
            "message": "",
            "consume_num": final_use_num,
            "update_data": {}
        }

        if buff_type == "level_up_rate": # 增加固定突破概率
            result_data['update_data']['level_up_rate_add'] = buff_value * final_use_num
            result_data['message'] = f"道友使用了 {final_use_num} 颗【{pill_name}】，下次突破成功率增加了 {buff_value * final_use_num}%！"

        elif buff_type == "level_up_big": # 增加大境界突破概率
            # 检查大境界是否匹配
            if user_info.level != required_level_name:
                 return {"success": False, "message": f"【{pill_name}】只能在【{required_level_name}】时使用，道友当前境界不符！"}
            result_data['update_data']['level_up_rate_add'] = buff_value * final_use_num
            result_data['message'] = f"道友使用了 {final_use_num} 颗【{pill_name}】，下次突破成功率增加了 {buff_value * final_use_num}%！"

        elif buff_type == "hp": # 按百分比回血
            # 使用 self.service 来访问 XiuxianService 的实例方法
            user_real_info = self.service.get_user_real_info(user_id)
            if not user_real_info:
                return {"success": False, "message": "错误：无法获取用户的详细状态信息！"}

            # 如果当前血量已满，则不使用
            if user_real_info['hp'] >= user_real_info['max_hp']:
                 return {"success": False, "message": "道友气血充盈，无需使用丹药。"}

            hp_to_heal = int(user_real_info['max_hp'] * buff_value * final_use_num)

            result_data['update_data']['hp_add'] = hp_to_heal
            result_data['message'] = f"道友使用了 {final_use_num} 颗【{pill_name}】，生命回复了 {hp_to_heal} 点！"
        elif buff_type == "mp": # 按百分比回血
            user_real_info = self.service.get_user_real_info(user_id)
            if not user_real_info:
                return {"success": False, "message": "错误：无法获取用户的详细状态信息！"}

            # 如果当前血量已满，则不使用
            if user_real_info['mp'] >= user_real_info['max_mp']:
                 return {"success": False, "message": "道友真元充盈，无需使用丹药。"}

            mp_to_heal = int(user_real_info['max_mp'] * buff_value * final_use_num)

            result_data['update_data']['mp_add'] = mp_to_heal
            result_data['message'] = f"道友使用了 {final_use_num} 颗【{pill_name}】，真元回复了 {mp_to_heal} 点！"
        elif buff_type == "exp_up": # 增加固定修为
            exp_to_add = buff_value * final_use_num
            result_data['update_data']['exp_add'] = exp_to_add
            result_data['message'] = f"道友使用了 {final_use_num} 颗【{pill_name}】，修爲增加了 {exp_to_add} 点！"
        elif buff_type == "atk_buff": # 永久增加攻击力
            atk_to_add = buff_value * final_use_num
            result_data['update_data']['atk_add'] = atk_to_add
            result_data['message'] = f"道友使用了 {final_use_num} 颗【{pill_name}】，根骨得到强化，永久增加了 {atk_to_add} 点攻击力！"
        elif buff_type == "all":
            user_real_info = self.service.get_user_real_info(user_id)
            if not user_real_info:
                return {"success": False, "message": "错误：无法获取用户的详细状态信息！"}

            # 如果当前血量已满，则不使用
            if user_real_info['hp'] >= user_real_info['max_hp']:
                return {"success": False, "message": "道友气血充盈，无需使用丹药。"}
            # HP 回满

            result_data['update_data']['hp_add'] = user_real_info['max_hp'] - user_real_info['hp'] # 计算需要补满的量
            # MP 回满 (假设您有MP系统)
            result_data['update_data']['mp_add'] = user_real_info['max_mp'] - user_real_info['mp']
            result_data['message'] = f"道友使用了 {final_use_num} 颗【{pill_name}】，所有状态焕然一新！"
        elif buff_type == "level_up": # 渡厄丹
            result_data['update_data']['set_temp_buff'] = {
                "key": "reduce_breakthrough_penalty", # 定义一个清晰的key
                "value": True,                         # Buff的值，这里用True表示生效
                "duration": None                       # 对于渡厄丹这种下次突破生效的，可以不设持续时间，靠主动消耗
            }
            result_data['message'] = f"道友使用了 {final_use_num} 颗【{pill_name}】，周身被一股神秘力量包裹(请马上突破,效果说没就没了)，下次突破将无后顾之忧！"
        else:
            return {"success": False, "message": f"【{pill_name}】的效果暂未实现，请联系管理员。"}

        return result_data

    def _get_user_herbs_by_type(self, user_backpack: list) -> dict:
        """
        将用户背包的药材按类型和药力进行分类
        :return: { "2": [{"id": 3001, "name": "恒心草", "power": 2, "num": 5}, ...], "3": [...] }
        """
        herbs_by_type = {}
        if not user_backpack:
            return herbs_by_type

        for item in user_backpack:
            if item.goods_type == "药材":
                herb_info = self.items_manager.get_data_by_item_id(item.goods_id)
                if not herb_info: continue

                # 一个药材可能同时可以作为多种类型的辅药或主药，这里我们只考虑它作为“主药”和“辅药”时的类型
                # 原版逻辑中，药引的类型与主药相同，所以我们不单独处理

                # 作为主药时的类型
                if main_herb_info := herb_info.get("主药"):
                    herb_type = str(main_herb_info['type'])
                    if herb_type not in herbs_by_type:
                        herbs_by_type[herb_type] = []

                    herbs_by_type[herb_type].append({
                        "id": item.goods_id,
                        "name": item.goods_name,
                        "power": main_herb_info['power'],
                        "num": item.goods_num
                    })

                # 作为辅药时的类型
                if sub_herb_info := herb_info.get("辅药"):
                    herb_type = str(sub_herb_info['type'])
                    if herb_type not in herbs_by_type:
                        herbs_by_type[herb_type] = []

                    # 避免重复添加同一个药材
                    is_added = False
                    for existing_herb in herbs_by_type[herb_type]:
                        if existing_herb['id'] == item.goods_id:
                            is_added = True
                            break
                    if not is_added:
                         herbs_by_type[herb_type].append({
                            "id": item.goods_id,
                            "name": item.goods_name,
                            "power": sub_herb_info['power'],
                            "num": item.goods_num
                        })

        # 按power从大到小排序，方便后续优先使用药力高的药材
        for herb_type in herbs_by_type:
            herbs_by_type[herb_type].sort(key=lambda x: x['power'], reverse=True)

        return herbs_by_type

    def _find_materials_for_recipe(self, required_formula: dict, user_herbs_by_type: dict, initial_backpack_quantities: dict) -> tuple[bool, dict]:
        """
        Smartly finds and combines herbs to meet recipe's medicinal power requirements.
        :param required_formula: Recipe requirements, e.g., {"2": 10, "3": 5}
        :param user_herbs_by_type: User's herbs categorized by medicinal type.
        :param initial_backpack_quantities: A dict of {herb_id: quantity} for all herbs in backpack.
        :return: (bool: can_craft, dict: {herb_id_to_consume: quantity_to_consume})
        """
        materials_to_consume_for_this_recipe = {}
        # Create a mutable copy of available quantities for this crafting attempt
        available_quantities = initial_backpack_quantities.copy()

        for required_type, required_power_needed in required_formula.items():
            if required_type not in user_herbs_by_type:
                return False, {} # 用户完全没有这种类型的药材，直接失败

            power_gathered_for_this_type = 0
            # 获取用户拥有的该类型所有药材，它们已经按药力从高到低排好序
            herbs_of_this_type = user_herbs_by_type[required_type]

            # 优先使用药力高的药材来凑数
            for herb_spec_for_this_type in herbs_of_this_type:
                herb_id = herb_spec_for_this_type['id']
                herb_power_per_item = herb_spec_for_this_type['power']

                physically_available_count = available_quantities.get(herb_id, 0)

                if physically_available_count == 0:
                    continue

                num_of_this_herb_to_use_for_this_type = 0
                # 如果当前凑齐的药力还不够，并且这种药材还有剩余
                while (power_gathered_for_this_type < required_power_needed and
                       num_of_this_herb_to_use_for_this_type < physically_available_count):
                    power_gathered_for_this_type += herb_power_per_item
                    num_of_this_herb_to_use_for_this_type += 1
                    if power_gathered_for_this_type >= required_power_needed:
                        break

                # 如果使用了这种药材，记录下要消耗的数量
                if num_of_this_herb_to_use_for_this_type > 0:
                    materials_to_consume_for_this_recipe[herb_id] = materials_to_consume_for_this_recipe.get(herb_id, 0) + num_of_this_herb_to_use_for_this_type
                    available_quantities[herb_id] -= num_of_this_herb_to_use_for_this_type

                # 如果当前类型的药力已经凑齐，就跳出循环，去凑下一种类型
                if power_gathered_for_this_type >= required_power_needed:
                    break

            # 如果遍历完所有该类型的药材后，药力依然不够，则说明无法炼制
            if power_gathered_for_this_type < required_power_needed:
                return False, {}

        # 如果所有类型的药力都成功凑齐了
        return True, materials_to_consume_for_this_recipe

    def _get_user_backpack_herb_quantities(self, user_backpack: list) -> dict:
        """
        Helper to get a simple dict of herb_id to quantity from backpack.
        :return: {herb_id_int: quantity_int}
        """
        quantities = {}
        if not user_backpack:
            return quantities
        for item in user_backpack:
            if item.goods_type == "药材":
                quantities[item.goods_id] = item.goods_num
        return quantities
