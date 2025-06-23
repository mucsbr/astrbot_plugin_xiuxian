import random
from .data_manager import jsondata
from .service import USERRANK

class BountyManager:
    def __init__(self):
        self.raw_bounty_data = jsondata.get_bounty_data()
        self.level_data = jsondata.level_data()
        self.all_bounties_template = []
        # 将json数据扁平化处理，作为模板
        for bounty_type, bounties in self.raw_bounty_data.items():
            for bounty_name, bounty_info in bounties.items():
                b_data = bounty_info.copy()
                b_data['name'] = bounty_name
                b_data['type'] = bounty_type
                b_data['id'] = random.randint(1000, 9999) 
                self.all_bounties_template.append(b_data)

    def generate_bounties(self, user_level: str) -> list[dict]:
        """为用户生成一组悬赏令，怪物属性动态生成"""
        if not self.all_bounties_template:
            return []

        num_to_generate = min(len(self.all_bounties_template), 5)
        generated_list = random.sample(self.all_bounties_template, num_to_generate)

        user_rank = USERRANK.get(user_level, 99)
        player_level_info = self.level_data.get(user_level, {})
        base_hp = player_level_info.get('hp', 100)
        base_atk = player_level_info.get('atk', 10)

        for bounty in generated_list:
            # 调整奖励
            base_reward = bounty.get("succeed_thank", 100)
            reward_multiplier = 1 + (50 - user_rank) * 0.1
            bounty['succeed_thank'] = int(base_reward * reward_multiplier)

            # 如果是战斗类任务，动态生成怪物属性
            if bounty['type'] in ["捉妖", "暗杀"]:
                # 定义悬赏怪物的难度系数
                hp_multiplier = random.uniform(1.5, 3.0)  # 怪物血量是玩家的1.5到3倍
                atk_multiplier = random.uniform(0.8, 1.5) # 怪物攻击力是玩家的0.8到1.5倍

                monster_hp = int(base_hp * hp_multiplier)
                monster_atk = int(base_atk * atk_multiplier)

               # bounty['monster_name'] = f"{user_level}期的{bounty['name']}目标"
               # bounty['monster_hp'] = monster_hp
               # bounty['atk'] = monster_atk # 为了统一，我们将怪物攻击力也存到atk字段
                bounty['monster_name'] = f"{user_level}期的{bounty['name']}目标"
                bounty['monster_hp'] = monster_hp
                bounty['monster_atk'] = monster_atk

        return generated_list
