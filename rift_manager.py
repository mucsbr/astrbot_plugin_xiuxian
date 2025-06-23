import random
from .data_manager import jsondata
from .service import USERRANK

class RiftManager:
    """秘境管理器，负责生成秘境"""
    def __init__(self):
        self.rift_event_data = jsondata.get_rift_data().get("type", {})
        from .config import XiuConfig
        self.config = XiuConfig()

    # v-- 将这个方法完整替换你原来的 generate_rift --v
    def generate_rift(self, user_level: str) -> dict | None:
        """
        【新版】根据玩家境界动态生成不同等级和类型的秘境。
        """
        if not self.rift_event_data:
            return None

        user_rank = USERRANK.get(user_level, 99)
        chosen_rift_template = None

        # 1. 从配置中筛选出玩家有资格进入的所有秘境等级
        #available_rifts = []
        rift_config_pool = self.config.rift_config
        for rank_threshold, rift_info in rift_config_pool.items():
            if user_rank <= int(rank_threshold):
                # available_rifts.append(rift_info)
                chosen_rift_template = rift_info

        if not chosen_rift_template:
            # 如果没有任何匹配的秘境（理论上不会发生），给一个默认的
            chosen_rift_template = list(rift_config_pool.values())[0]
        #else:
        #    # 从所有符合条件的秘境中随机选择一个
        #    chosen_rift_template = random.choice(available_rifts)

        # 2. 获取秘境的基础设定
        rift_name = random.choice(chosen_rift_template['name_pool'])
        total_floors = chosen_rift_template['floors']
        reward_multiplier = chosen_rift_template['reward_multiplier']

        # 3. 获取玩家境界的基础属性作为怪物生成蓝本
        player_level_info = jsondata.level_data().get(user_level, {})
        base_hp = player_level_info.get('HP', 100)
        base_atk = player_level_info.get('atk', 10)

        # 4. 生成秘境地图
        event_pool = list(self.rift_event_data.values())
        rift_map = []
        for i in range(total_floors):
            event_template = random.choice(event_pool)

            floor_event = {
                "floor": i + 1,
                "event_type": event_template["type"],
                "event_name": event_template["name"],
                "desc": event_template["desc"],
                "is_finished": False,
            }

            # 动态生成奖励和怪物属性
            if event_template["type"] == "reward":
                base_exp_reward = random.randint(*event_template['reward']['exp'])
                base_stone_reward = random.randint(*event_template['reward']['stone'])
                floor_event['reward'] = {
                    "exp": int(base_exp_reward * reward_multiplier),
                    "stone": int(base_stone_reward * reward_multiplier)
                }

            elif event_template["type"] == "combat":
                floor_multiplier = 1 + (i * 0.1) # 层数加成
                monster_hp = int(base_hp * 1.2 * floor_multiplier)
                monster_atk = int(base_atk * 0.9 * floor_multiplier)

                floor_event["monster"] = {
                    "name": f"第{i+1}层守卫", "hp": monster_hp, "atk": monster_atk
                }
                # 战斗胜利的奖励也应该被加成
                base_exp_reward = random.randint(*event_template['reward']['exp'])
                base_stone_reward = random.randint(*event_template['reward']['stone'])
                floor_event['reward'] = {
                    "exp": int(base_exp_reward * reward_multiplier),
                    "stone": int(base_stone_reward * reward_multiplier)
                }

            rift_map.append(floor_event)

        return {
            "name": rift_name,
            "total_floors": total_floors,
            "map": rift_map
        }
