# pve_config.py
"""
PVE系统（镜像回廊）的配置文件
"""

# --- 镜像回廊规则 ---
CORRIDOR_RULES = {
    'daily_free_challenges': 3,
    'cost_after_free': 150000,
}

# --- 传说牌库 (固定ID) ---
# key为固定ID，value为数据库中的fish_id (或一个唯一标识，如鱼的name)
# 为简单起见，我们直接用鱼的name作为唯一标识
LEGENDARY_DECK = {
    # R4
    "101": "金龙鱼", "102": "清道夫", "103": "娃娃鱼", "104": "蓝鳍金枪鱼", "105": "剑鱼",
    "106": "海豚", "107": "鲸鱼", "108": "电鳗", "109": "海龟", "110": "深海鮟鱇",
    "111": "沉没的宝箱", "112": "腔棘鱼", "113": "桔连鳍鲑", "114": "皇带鱼", "115": "尖牙鱼",
    "116": "水滴鱼", "117": "光颌鱼", "118": "角鮟鱇", "119": "黑魔鬼鱼", "120": "鳕鲈",
    "121": "大比目鱼", "122": "旗鱼",
    # R5
    "201": "锦鲤", "202": "龙王", "203": "美人鱼", "204": "深海巨妖", "205": "海神三叉戟",
    "206": "时间沙漏", "207": "克拉肯之触", "208": "许德拉之鳞", "209": "尘世巨蟒之环", "210": "神马",
    "211": "狮子鱼", "212": "幽灵鲨", "213": "吸血鬼乌贼", "214": "阿斯皮多凯隆幼龟", "215": "最深之鱼",
}

# --- 阵容强度与难度匹配 ---
def get_difficulty_and_guard(player_lineup_fish_data):
    strength_score = sum([3 if fish['rarity'] == 5 else 1 for fish in player_lineup_fish_data])
    
    if strength_score <= 5:
        return '普通', 'guard_normal'
    elif strength_score <= 10:
        return '困难', 'guard_hard'
    elif strength_score <= 14:
        return '英雄', 'guard_heroic'
    else: # 15
        return '传说', 'guard_legendary'

# --- 动态奖励池 ---
REWARD_POOLS = {
    '普通': {'gold': 10000, 'shards': 1, 'chests': 1, 'rare_chance': 0},
    '困难': {'gold': 25000, 'shards': 2, 'chests': 1.5, 'rare_chance': 0.001, 'rare_item_type': 'accessory'},
    '英雄': {'gold': 50000, 'shards': 3, 'chests': 2.3, 'rare_chance': 0.003, 'rare_item_type': 'accessory'},
    '传说': {'gold': 20000, 'shards': 1, 'chests': 1, 'rare_chance': 0.005, 'rare_item_type': 'rod'},
}

# --- 回廊商店 ---
SHOP_ITEMS = {
    "1": {'name': "[万能饵] x10", 'cost': 15, 'limit_type': 'daily', 'item_type': 'bait', 'item_name': '万能饵', 'quantity': 10},
    "2": {'name': "[秘制香饵] x5", 'cost': 25, 'limit_type': 'daily', 'item_type': 'bait', 'item_name': '秘制香饵', 'quantity': 5},
    "3": {'name': "[巨物诱饵] x1", 'cost': 50, 'limit_type': 'weekly', 'item_type': 'bait', 'item_name': '巨物诱饵', 'quantity': 1},
    "4": {'name': "[强化幸运符]", 'cost': 120, 'limit_type': 'weekly', 'limit_count': 3, 'item_type': 'special', 'item_key': 'luck_charm', 'quantity': 1},
    "5": {'name': "[随机鱼竿宝箱]", 'cost': 300, 'limit_type': 'weekly', 'limit_count': 1, 'item_type': 'special', 'item_key': 'rod_chest', 'quantity': 1},
    "6": {'name': "[随机饰品宝箱]", 'cost': 300, 'limit_type': 'weekly', 'limit_count': 1, 'item_type': 'special', 'item_key': 'accessory_chest', 'quantity': 1},
    "7": {'name': "[奇迹水滴]", 'cost': 800, 'limit_type': 'weekly', 'limit_count': 1, 'item_type': 'bait', 'item_name': '奇迹水滴', 'quantity': 1},
}
