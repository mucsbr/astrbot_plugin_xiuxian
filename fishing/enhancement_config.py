# enhancement_config.py

"""
集中管理用户锻造强化系统的所有配置。
- 成本和概率参考了DNF手游的设定。
- 收益数值经过平滑处理，以适应本游戏的生态。
"""

# 锻造等级配置表
# cost: 金币花费
# probability: 成功率 (0-100)
# quality_bonus: 品质加成 (百分比, %)
# rare_bonus: 稀有度加成 (百分比, %)
# fishing_cd_reduction: 钓鱼CD减少 (秒)
# steal_cd_reduction: 偷鱼CD减少 (分钟)
FORGE_CONFIG = [
    # 等级 0 -> 1
    {'level': 1, 'cost': 1000, 'probability': 100, 'quality_bonus': 0.5, 'rare_bonus': 0.10, 'fishing_cd_reduction': 1, 'steal_cd_reduction': 1},
    # 等级 1 -> 2
    {'level': 2, 'cost': 2000, 'probability': 100, 'quality_bonus': 1.0, 'rare_bonus': 0.20, 'fishing_cd_reduction': 2, 'steal_cd_reduction': 2},
    # 等级 2 -> 3
    {'level': 3, 'cost': 3000, 'probability': 100, 'quality_bonus': 1.5, 'rare_bonus': 0.30, 'fishing_cd_reduction': 3, 'steal_cd_reduction': 3},
    # 等级 3 -> 4
    {'level': 4, 'cost': 5000, 'probability': 95, 'quality_bonus': 2.0, 'rare_bonus': 0.40, 'fishing_cd_reduction': 4, 'steal_cd_reduction': 4},
    # 等级 4 -> 5
    {'level': 5, 'cost': 8000, 'probability': 90, 'quality_bonus': 3.0, 'rare_bonus': 0.50, 'fishing_cd_reduction': 5, 'steal_cd_reduction': 5},
    # 等级 5 -> 6
    {'level': 6, 'cost': 12000, 'probability': 85, 'quality_bonus': 4.0, 'rare_bonus': 0.65, 'fishing_cd_reduction': 7, 'steal_cd_reduction': 7},
    # 等级 6 -> 7
    {'level': 7, 'cost': 18000, 'probability': 80, 'quality_bonus': 5.0, 'rare_bonus': 0.80, 'fishing_cd_reduction': 9, 'steal_cd_reduction': 9},
    # 等级 7 -> 8
    {'level': 8, 'cost': 25000, 'probability': 70, 'quality_bonus': 6.0, 'rare_bonus': 1.00, 'fishing_cd_reduction': 11, 'steal_cd_reduction': 11},
    # 等级 8 -> 9
    {'level': 9, 'cost': 35000, 'probability': 60, 'quality_bonus': 7.0, 'rare_bonus': 1.25, 'fishing_cd_reduction': 13, 'steal_cd_reduction': 13},
    # 等级 9 -> 10
    {'level': 10, 'cost': 50000, 'probability': 50, 'quality_bonus': 9.0, 'rare_bonus': 1.50, 'fishing_cd_reduction': 15, 'steal_cd_reduction': 15},
    # 等级 10 -> 11
    {'level': 11, 'cost': 70000, 'probability': 45, 'quality_bonus': 10.5, 'rare_bonus': 1.80, 'fishing_cd_reduction': 18, 'steal_cd_reduction': 18},
    # 等级 11 -> 12
    {'level': 12, 'cost': 100000, 'probability': 40, 'quality_bonus': 12.0, 'rare_bonus': 2.10, 'fishing_cd_reduction': 21, 'steal_cd_reduction': 21},
    # 等级 12 -> 13
    {'level': 13, 'cost': 150000, 'probability': 35, 'quality_bonus': 13.5, 'rare_bonus': 2.40, 'fishing_cd_reduction': 24, 'steal_cd_reduction': 24},
    # 等级 13 -> 14
    {'level': 14, 'cost': 220000, 'probability': 30, 'quality_bonus': 15.0, 'rare_bonus': 2.70, 'fishing_cd_reduction': 27, 'steal_cd_reduction': 27},
    # 等级 14 -> 15
    {'level': 15, 'cost': 300000, 'probability': 25, 'quality_bonus': 18.0, 'rare_bonus': 3.00, 'fishing_cd_reduction': 30, 'steal_cd_reduction': 30},
    # 等级 15 -> 16
    {'level': 16, 'cost': 500000, 'probability': 20, 'quality_bonus': 20.0, 'rare_bonus': 3.40, 'fishing_cd_reduction': 34, 'steal_cd_reduction': 35},
    # 等级 16 -> 17
    {'level': 17, 'cost': 800000, 'probability': 18, 'quality_bonus': 22.0, 'rare_bonus': 3.80, 'fishing_cd_reduction': 38, 'steal_cd_reduction': 40},
    # 等级 17 -> 18
    {'level': 18, 'cost': 1200000, 'probability': 15, 'quality_bonus': 24.0, 'rare_bonus': 4.20, 'fishing_cd_reduction': 42, 'steal_cd_reduction': 45},
    # 等级 18 -> 19
    {'level': 19, 'cost': 2000000, 'probability': 10, 'quality_bonus': 26.0, 'rare_bonus': 4.60, 'fishing_cd_reduction': 46, 'steal_cd_reduction': 50},
    # 等级 19 -> 20
    {'level': 20, 'cost': 5000000, 'probability': 5, 'quality_bonus': 30.0, 'rare_bonus': 5.00, 'fishing_cd_reduction': 50, 'steal_cd_reduction': 60},
]

# 最大等级
MAX_FORGE_LEVEL = 20

def get_config_for_next_level(current_level: int) -> dict:
    """获取强化到下一级所需的配置"""
    if current_level >= MAX_FORGE_LEVEL:
        return None
    # 列表索引从0开始，而等级从1开始
    return FORGE_CONFIG[current_level]

def get_bonuses_for_level(level: int) -> dict:
    """获取指定等级提供的总加成"""
    if level <= 0:
        return {
            'quality_bonus': 0, 'rare_bonus': 0, 
            'fishing_cd_reduction': 0, 'steal_cd_reduction': 0
        }
    # 列表索引从0开始
    return FORGE_CONFIG[level - 1]
