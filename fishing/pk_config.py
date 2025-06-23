# pk_config.py
"""
集中管理“深海角斗场”(PK系统)的所有配置。
这是一个完整的版本，包含了所有R4和R5鱼的技能定义。
"""
import random

# PK系统基本规则
PK_RULES = {
    'cost_rate': 0.10,
    'min_gold_to_challenge': 10000,
    'daily_duel_limit': 3,
    'duel_cooldown_hours': 24,
    'base_energy': 3,
    'win_steal_base_count': 1,
    'win_extra_steal_chance': 0.2,
    'lineup_size': 5
}

# 稀有度 -> 能量产出
ENERGY_GENERATION = {1: 0, 2: 0, 3: 1, 4: 2, 5: 3}

# 职业对PK的影响
CLASS_PK_BONUS = {
    'hunter': {'lineup_quality_bonus': True},
    'plunderer': {'spy_chance': 0.1},
    'seeker': {'win_steal_chance_bonus': 0.1},
    'child': {'start_energy_bonus': 1},
    'BOSS': {'start_energy_bonus': 1},
}

# 定义垃圾鱼的名称列表
JUNK_FISH_NAMES = ["破旧的靴子", "生锈的铁罐", "缠绕的水草", "普通石头"]

# 鱼类技能定义
FISH_SKILLS = {
    # --- Rarity 4 ---
    "金龙鱼": {"aura": "[帝王之气]: 对手是R3及以下时，其全属性降低15%。", "ultimate": "[黄金鳞](2能量): 若本回合比拼价值，则自身价值翻倍。", "effect": {"aura_trigger": {"opponent_rarity_lte": 3}, "aura_effect": {"debuff_all_stats": 0.15}, "ultimate_cost": 2, "ultimate_trigger": {"rule_is": "value"}, "ultimate_effect": {"buff_self_value": 2.0}}},
    "清道夫": {"aura": "[环境清理]: 若对手是“垃圾鱼”，直接获胜。", "ultimate": "[坚硬外壳](2能量): 本回合受到的所有负面属性影响效果减半。", "effect": {"aura_trigger": {"opponent_is_junk": True}, "aura_effect": {"win_round": True}, "ultimate_cost": 2, "ultimate_effect": {"debuff_resistance": 0.5}}},
    "娃娃鱼": {"aura": "[再生]: 若本回合输了，有30%几率判定为平局。", "ultimate": "[婴儿啼哭](2能量): 跳过本回合比拼，直接判定为平局，并使对手下一条鱼的“重量”降低50%。", "effect": {"aura_trigger": {"on_lose": True, "chance": 0.3}, "aura_effect": {"force_draw": True}, "ultimate_cost": 2, "ultimate_effect": {"force_draw_round": True, "debuff_next_opponent_weight": 0.5}}},
    "蓝鳍金枪鱼": {"aura": "[高速突进]: 若本回合比拼重量，自身重量提升20%。", "ultimate": "[深海闪击](2能量): 强制本回合比拼规则变为“重量”。", "effect": {"aura_trigger": {"rule_is": "weight"}, "aura_effect": {"buff_self_weight": 1.2}, "ultimate_cost": 2, "ultimate_effect": {"force_rule": "weight"}}},
    "剑鱼": {"aura": "[利刃]: 若本回合比拼稀有度，自身稀有度临时+1。", "ultimate": "[致命一刺](*能量): 消耗所有剩余能量（最少1），每点能量使自身全属性临时提升25%。", "effect": {"aura_trigger": {"rule_is": "rarity"}, "aura_effect": {"buff_self_rarity": 1}, "ultimate_cost": "all", "ultimate_effect": {"buff_all_stats_per_energy": 0.25}}},
    "海豚": {"aura": "[声波定位]: 战斗开始时，有25%几率窥探到对手阵容中的一条鱼。", "ultimate": "[治愈之跃](2能量): 若你当前分数落后，本回合平局时为你回复1点能量。", "effect": {"pre_battle_spy_chance": 0.25, "ultimate_cost": 2, "ultimate_trigger": {"on_draw": True, "score_is_behind": True}, "ultimate_effect": {"add_energy": 1}}},
    "鲸鱼": {"aura": "[庞然大物]: 基础“重量”属性是所有鱼中最高的之一。", "ultimate": "[鲸落](2能量): 若这是你的最后一条鱼且你输掉了本回合，对手下一条鱼的“价值”将被清零。", "effect": {"ultimate_cost": 2, "ultimate_trigger": {"on_lose": True, "is_last_fish": True}, "ultimate_effect": {"debuff_next_opponent_value": 0}}},
    "电鳗": {"aura": "[麻痹电流]: 若本回合比拼重量，直接获胜。", "ultimate": "[十万伏特](2能量): 使对手下一条鱼的所有“光环”技能失效。", "effect": {"aura_trigger": {"rule_is": "weight"}, "aura_effect": {"win_round": True}, "ultimate_cost": 2, "ultimate_effect": {"disable_next_opponent_aura": True}}},
    "海龟": {"aura": "[长寿之盾]: 若这是你出战的第一条鱼，为你额外增加1点起始能量。", "ultimate": "[智慧守护](2能量): 强制本回合比拼规则变为“价值”。", "effect": {"aura_trigger": {"is_first_fish": True}, "aura_effect": {"add_energy": 1}, "ultimate_cost": 2, "ultimate_effect": {"force_rule": "value"}}},
    "深海鮟鱇": {"aura": "[诱捕之光]: 若对手是R3及以下的鱼，有30%几率强制本回合比拼规则变为“稀有度”。", "ultimate": "[深渊吞噬](2能量): 若本回合获胜，从对手身上吸取1点能量。", "effect": {"aura_trigger": {"opponent_rarity_lte": 3, "chance": 0.3}, "aura_effect": {"force_rule": "rarity"}, "ultimate_cost": 2, "ultimate_trigger": {"on_win": True}, "ultimate_effect": {"steal_energy": 1}}},
    "沉没的宝箱": {"aura": "[财富诅咒]: 对手在本回合无法使用任何“必杀技”。", "ultimate": "[开箱](1能量): 放弃本回合胜利，但为你回复2点能量。", "effect": {"aura_effect": {"disable_opponent_ultimate": True}, "ultimate_cost": 1, "ultimate_effect": {"lose_round_for_energy": 2}}},
    "腔棘鱼": {"aura": "[活化石]: 不受任何降低“稀有度”效果的影响。", "ultimate": "[远古血脉](2能量): 若对手的稀有度低于你，本回合你的“重量”和“价值”提升30%。", "effect": {"aura_effect": {"resist_rarity_debuff": True}, "ultimate_cost": 2, "ultimate_trigger": {"opponent_rarity_lt_self": True}, "ultimate_effect": {"buff_self_weight_value": 1.3}}},
    "桔连鳍鲑": {"aura": "[深海住民]: 若对手不是深海鱼，本回合你的“重量”提升40%。", "ultimate": "[缓慢爆发](2能量): 若这是最后两个回合，你的所有属性提升50%。", "effect": {"aura_trigger": {"opponent_is_not_deep_sea": True}, "aura_effect": {"buff_self_weight": 1.4}, "ultimate_cost": 2, "ultimate_trigger": {"is_last_rounds": 2}, "ultimate_effect": {"buff_self_all": 1.5}}},
    "皇带鱼": {"aura": "[海龙卷]: 出战时，20%几率与对方下一条未出战的鱼强制交换位置。", "ultimate": "[末日预兆](3能量): 若分数落后且是最后两回合，本回合全属性翻倍。", "effect": {"aura_trigger": {"on_deploy": True, "chance": 0.2}, "aura_effect": {"swap_next_opponent": True}, "ultimate_cost": 3, "ultimate_trigger": {"score_is_behind": True, "is_last_rounds": 2}, "ultimate_effect": {"buff_self_all": 2.0}}},
    "尖牙鱼": {"aura": "[穿刺之牙]: 若本回合比拼价值，无视对手25%的“价值”数值。", "ultimate": "[恶狠狠](2能量): 使对手下一条鱼的“稀有度”临时-1。", "effect": {"aura_trigger": {"rule_is": "value"}, "aura_effect": {"ignore_opponent_value": 0.25}, "ultimate_cost": 2, "ultimate_effect": {"debuff_next_opponent_rarity": -1}}},
    "水滴鱼": {"aura": "[深海压力]: 若本回合比拼重量，且你的重量低于对手，有50%几率判定为平局。", "ultimate": "[形态伪装](2能量): 复制对手本回合的“重量”和“价值”数值进行比拼。", "effect": {"aura_trigger": {"rule_is": "weight", "self_weight_lt_opponent": True, "chance": 0.5}, "aura_effect": {"force_draw": True}, "ultimate_cost": 2, "ultimate_effect": {"copy_opponent_stats": ["weight", "value"]}}},
    "光颌鱼": {"aura": "[红外视觉]: 战斗开始时，窥探到对手阵容中“价值”最高的一条鱼。", "ultimate": "[精准锁定](2能量): 强制本回合比拼规则变为“价值”。", "effect": {"pre_battle_spy_highest_value": True, "ultimate_cost": 2, "ultimate_effect": {"force_rule": "value"}}},
    "角鮟鱇": {"aura": "[寄生之力]: 若你的阵容中有其他“鮟鱇”类鱼，本回合你的所有属性提升20%。", "ultimate": "[深海诱惑](2能量): 使对手下一条鱼出战时，有50%几率无法发动“必杀技”。", "effect": {"aura_trigger": {"team_has_angler_fish": True}, "aura_effect": {"buff_self_all": 1.2}, "ultimate_cost": 2, "ultimate_effect": {"disable_next_opponent_ultimate_chance": 0.5}}},
    "黑魔鬼鱼": {"aura": "[黑暗笼罩]: 使对手的“光环”技能触发率降低10%。", "ultimate": "[能量虹吸](2能量): 若本回合获胜，且对手能量多于你，从对手处偷取1点能量。", "effect": {"aura_effect": {"debuff_opponent_aura_chance": 0.1}, "ultimate_cost": 2, "ultimate_trigger": {"on_win": True, "opponent_energy_gt_self": True}, "ultimate_effect": {"steal_energy": 1}}},
    "鳕鲈": {"aura": "[稳固]: 不受任何强制交换位置效果的影响。", "ultimate": "[均衡之力](2能量): 若本回合比拼的三项属性中，你有两项高于对手，则直接获胜。", "effect": {"aura_effect": {"resist_swap": True}, "ultimate_cost": 2, "ultimate_trigger": {"has_2_of_3_stats_higher": True}, "ultimate_effect": {"win_round": True}}},
    "大比目鱼": {"aura": "[伪装]: 出战时，有15%的几率让对手误判比拼规则。", "ultimate": "[双眼凝视](2能量): 若本回合比拼稀有度，且对手稀有度高于你，则强制重赛本回合。", "effect": {"aura_trigger": {"on_deploy": True, "chance": 0.15}, "aura_effect": {"confuse_opponent_rule": True}, "ultimate_cost": 2, "ultimate_trigger": {"rule_is": "rarity", "opponent_rarity_gt_self": True}, "ultimate_effect": {"reroll_round": True}}},
    "旗鱼": {"aura": "[破浪]: 若这是第一回合，你的所有属性提升30%。", "ultimate": "[急速冲锋](2能量): 强制本回合比拼规则变为“重量”，且自身重量临时提升30%。", "effect": {"aura_trigger": {"is_first_round": True}, "aura_effect": {"buff_self_all": 1.3}, "ultimate_cost": 2, "ultimate_effect": {"force_rule": "weight", "buff_self_weight": 1.3}}},
    
    # --- Rarity 5 ---
    "锦鲤": {"aura": "[祥瑞]: 本回合双方都无法使用必杀技。回合结束后，为你回复1点能量。", "ultimate": "[逆天改命](2能量): 若本回合输了，强制重赛。每场限一次。", "effect": {"aura_effect": {"disable_all_ultimate": True, "add_energy_on_end": 1}, "ultimate_cost": 2, "ultimate_trigger": {"on_lose": True}, "ultimate_effect": {"reroll_round": True}, "limit_per_duel": 1}},
    "龙王": {"aura": "[四海臣服]: 对手是R4或以下时，其“光环”技能失效。", "ultimate": "[龙王之怒](3能量): 强制本回合比拼规则变为“稀有度”，且自身稀有度临时+2。", "effect": {"aura_trigger": {"opponent_rarity_lte": 4}, "aura_effect": {"disable_opponent_aura": True}, "ultimate_cost": 3, "ultimate_effect": {"force_rule": "rarity", "buff_self_rarity": 2}}},
    "美人鱼": {"aura": "[魅惑之歌]: 若对手是R4或以下的鱼，有20%几率直接获胜。", "ultimate": "[海洋摇篮曲](3能量): 使对手下一条鱼的“必杀技”消耗的能量+2。", "effect": {"aura_trigger": {"opponent_rarity_lte": 4, "chance": 0.2}, "aura_effect": {"win_round": True}, "ultimate_cost": 3, "ultimate_effect": {"increase_next_opponent_ultimate_cost": 2}}},
    "深海巨妖": {"aura": "[深渊恐惧]: 对手的鱼所有属性永久降低10%。", "ultimate": "[致命缠绕](3能量): 若本回合比拼重量，直接获胜，并使对手下一条鱼无法发动“光环”。", "effect": {"aura_effect": {"debuff_opponent_all_permanent": 0.1}, "ultimate_cost": 3, "ultimate_trigger": {"rule_is": "weight"}, "ultimate_effect": {"win_round": True, "disable_next_opponent_aura": True}}},
    "海神三叉戟": {"aura": "[神器共鸣]: 你后续出战的鱼，“光环”触发率提升10%。", "ultimate": "[神之裁决](3能量): 立即结束本回合，比较双方阵容总属性（随机一项），胜者得2分。每场限一次。", "effect": {"aura_effect": {"buff_team_aura_chance": 0.1}, "ultimate_cost": 3, "ultimate_effect": {"special_win_condition": True}, "limit_per_duel": 1}},
    "时间沙漏": {"aura": "[时光倒流]: 当你输掉一回合后，有10%几率获得1点能量。", "ultimate": "[停滞领域](3能量): 使对手在本回合及下一回合都无法使用“必杀技”。", "effect": {"aura_trigger": {"on_lose": True, "chance": 0.1}, "aura_effect": {"add_energy": 1}, "ultimate_cost": 3, "ultimate_effect": {"disable_opponent_ultimate_for_rounds": 2}}},
    "克拉肯之触": {"aura": "[无尽延伸]: 若本回合比拼重量，你的重量有20%几率翻倍。", "ultimate": "[深渊之握](3能量): 强制本回合比拼规则变为“重量”，且对手重量降低30%。", "effect": {"aura_trigger": {"rule_is": "weight", "chance": 0.2}, "aura_effect": {"buff_self_weight": 2.0}, "ultimate_cost": 3, "ultimate_effect": {"force_rule": "weight", "debuff_opponent_weight": 0.3}}},
    "许德拉之鳞": {"aura": "[九头蛇之血]: 当你输掉一回合后，下一条鱼的所有属性提升15%。", "ultimate": "[多重吐息](*能量): 消耗所有剩余能量（最少1），每点能量随机降低对手一条未出战鱼的某项属性20%。", "effect": {"aura_trigger": {"on_lose": True}, "aura_effect": {"buff_next_self_all": 1.15}, "ultimate_cost": "all", "ultimate_effect": {"debuff_random_opponent_fish_stat_per_energy": 0.2}}},
    "尘世巨蟒之环": {"aura": "[世界之力]: 你的所有鱼（包括未出战的），其“重量”属性提升5%。", "ultimate": "[衔尾蛇](3能量): 若这是最后一回合，且比分持平，则直接判定你获胜。", "effect": {"aura_effect": {"buff_team_weight": 1.05}, "ultimate_cost": 3, "ultimate_trigger": {"is_last_round": True, "score_is_draw": True}, "ultimate_effect": {"win_duel": True}}},
    "神马": {"aura": "[踏浪]: 若你的阵容中有鱼类数量多于非鱼类物品，你的所有鱼属性提升10%。", "ultimate": "[海神冲锋](3能量): 若本回合比拼价值，你的价值临时提升50%，且对手无法使用必杀技。", "effect": {"aura_trigger": {"team_has_more_fish_than_items": True}, "aura_effect": {"buff_team_all": 1.1}, "ultimate_cost": 3, "ultimate_trigger": {"rule_is": "value"}, "ultimate_effect": {"buff_self_value": 1.5, "disable_opponent_ultimate": True}}},
    "狮子鱼": {"aura": "[剧毒之棘]: 若本回合你输了，对手下一条鱼的所有属性永久降低15%。", "ultimate": "[华丽威慑](3能量): 若本回合比拼稀有度，直接获胜。", "effect": {"aura_trigger": {"on_lose": True}, "aura_effect": {"debuff_next_opponent_all_permanent": 0.15}, "ultimate_cost": 3, "ultimate_trigger": {"rule_is": "rarity"}, "ultimate_effect": {"win_round": True}}},
    "幽灵鲨": {"aura": "[深海幽影]: 对手无法窥探到你的任何阵容信息。", "ultimate": "[缝合再生](3能量): 若你已损失的鱼中有R4或R5的鱼，本回合你的全属性提升50%。", "effect": {"aura_effect": {"resist_spy": True}, "ultimate_cost": 3, "ultimate_trigger": {"defeated_has_high_rarity": True}, "ultimate_effect": {"buff_self_all": 1.5}}},
    "吸血鬼乌贼": {"aura": "[墨汁斗篷]: 闪避对手的“光环”效果，触发率30%。", "ultimate": "[能量吸取](3能量): 若本回合获胜，吸取对手1点能量。若对手没有能量，则使其下一条鱼全属性降低20%。", "effect": {"aura_trigger": {"chance": 0.3}, "aura_effect": {"dodge_aura": True}, "ultimate_cost": 3, "ultimate_trigger": {"on_win": True}, "ultimate_effect": {"steal_or_debuff": True}}},
    "阿斯皮多凯隆幼龟": {"aura": "[岛龟之壳]: 免疫所有直接获胜或直接判负的技能效果。", "ultimate": "[世界背负者](*能量): 消耗所有能量（最少2），使你在接下来的所有回合中，每次比拼重量时，自身重量额外增加（能量数 * 10000g）。", "effect": {"aura_effect": {"resist_instant_win_lose": True}, "ultimate_cost": "all_min_2", "ultimate_effect": {"buff_future_weight_per_energy": 10000}}},
    "最深之鱼": {"aura": "[虚空适应]: 不受任何降低属性效果的影响。", "ultimate": "[混沌一瞥](3能量): 随机选择一项属性，将你和对手该项属性互换，然后进行比拼。", "effect": {"aura_effect": {"resist_debuff": True}, "ultimate_cost": 3, "ultimate_effect": {"swap_random_stat_and_compare": True}}},
}

def get_skill_by_fish_name(name):
    """根据鱼名安全地获取技能信息"""
    return FISH_SKILLS.get(name)
