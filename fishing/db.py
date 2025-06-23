import threading
import sqlite3
from datetime import datetime, date, timedelta, timezone
from typing import Dict, List, Optional, Any, Tuple
import time
import os
import random # Needed for gacha simulation if done here
from astrbot.api import logger
from .po import UserFishing
from . import enhancement_config
from . import class_config

# --- Constants ---
DEFAULT_COINS = 200

UTC4 = timezone(timedelta(hours=4))

def get_utc4_now():
    return datetime.now(UTC4)

def get_utc4_today():
    return get_utc4_now().date()

class FishingDB:
    def __init__(self, db_path: str, xiuxian_service_instance):
        """
        接收一个已存在的修仙服务实例和独立的钓鱼数据库路径。
        """
        self.db_path = db_path
        self._local = threading.local()
        self.xiuxian_service = xiuxian_service_instance # 持有修仙服务的实例

        db_dir = os.path.dirname(db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir)

        self.init_db()
        self.initialize_core_data()

    def _get_connection(self) -> sqlite3.Connection:
        """为钓鱼数据库获取独立的连接（线程安全）。"""
        conn = getattr(self._local, 'connection', None)
        if conn is None:
            conn = sqlite3.connect(self.db_path, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)
            conn.row_factory = sqlite3.Row
            self._local.connection = conn
        return conn

    def close_connection(self) -> None:
        """关闭当前线程的数据库连接。"""
        conn = getattr(self._local, 'connection', None)
        if conn is not None:
            conn.close()
            self._local.connection = None

    def init_db(self) -> None:
        """
        Initializes all tables based on the new schema if they don't exist.
        Also creates necessary indices.
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                logger.info("Initializing database schema...")

                # Configuration Tables
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS fish (
                        fish_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL UNIQUE,
                        description TEXT,
                        rarity INTEGER NOT NULL CHECK (rarity >= 1 AND rarity <= 5),
                        base_value INTEGER NOT NULL CHECK (base_value > 0),
                        min_weight INTEGER NOT NULL CHECK (min_weight >= 0),
                        max_weight INTEGER NOT NULL CHECK (max_weight > min_weight),
                        icon_url TEXT
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS baits (
                        bait_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL UNIQUE,
                        description TEXT,
                        rarity INTEGER NOT NULL DEFAULT 1 CHECK (rarity >= 1),
                        effect_description TEXT,
                        duration_minutes INTEGER DEFAULT 0,
                        cost INTEGER DEFAULT 0,
                        required_rod_rarity INTEGER DEFAULT 0
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS rods (
                        rod_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL UNIQUE,
                        description TEXT,
                        rarity INTEGER NOT NULL DEFAULT 1 CHECK (rarity >= 1),
                        source TEXT NOT NULL CHECK (source IN ('shop', 'gacha', 'event')),
                        purchase_cost INTEGER DEFAULT NULL,
                        bonus_fish_quality_modifier REAL DEFAULT 1.0,
                        bonus_fish_quantity_modifier REAL DEFAULT 1.0,
                        bonus_rare_fish_chance REAL DEFAULT 0.0,
                        durability INTEGER DEFAULT NULL,
                        icon_url TEXT
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS accessories (
                        accessory_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL UNIQUE,
                        description TEXT,
                        rarity INTEGER NOT NULL DEFAULT 1 CHECK (rarity >= 1),
                        slot_type TEXT DEFAULT 'general' NOT NULL,
                        bonus_fish_quality_modifier REAL DEFAULT 1.0,
                        bonus_fish_quantity_modifier REAL DEFAULT 1.0,
                        bonus_rare_fish_chance REAL DEFAULT 0.0,
                        bonus_coin_modifier REAL DEFAULT 1.0,
                        other_bonus_description TEXT,
                        icon_url TEXT
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS titles (
                        title_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL UNIQUE,
                        description TEXT NOT NULL,
                        display_format TEXT DEFAULT '{name}'
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS achievements (
                        achievement_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL UNIQUE,
                        description TEXT NOT NULL,
                        target_type TEXT NOT NULL CHECK (target_type IN ('total_fish_count', 'specific_fish_count', 'total_coins_earned', 'total_weight_caught', 'rare_fish_rarity_sum', 'wipe_bomb_profit', 'rod_collection', 'accessory_collection', 'login_days')),
                        target_value INTEGER NOT NULL,
                        target_fish_id INTEGER DEFAULT NULL,
                        reward_type TEXT DEFAULT 'none' CHECK (reward_type IN ('none', 'coins', 'title', 'bait', 'rod', 'accessory', 'premium_currency')),
                        reward_value INTEGER DEFAULT NULL,
                        reward_quantity INTEGER DEFAULT 1,
                        is_repeatable INTEGER DEFAULT 0 CHECK (is_repeatable IN (0, 1)),
                        icon_url TEXT
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS gacha_pools (
                        gacha_pool_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL UNIQUE,
                        description TEXT,
                        cost_coins INTEGER DEFAULT 0,
                        cost_premium_currency INTEGER DEFAULT 0
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS gacha_pool_items (
                        gacha_pool_item_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        gacha_pool_id INTEGER NOT NULL,
                        item_type TEXT NOT NULL CHECK (item_type IN ('rod', 'accessory', 'bait', 'fish', 'coins', 'premium_currency')),
                        item_id INTEGER NOT NULL,
                        quantity INTEGER DEFAULT 1,
                        weight INTEGER NOT NULL CHECK (weight > 0),
                        FOREIGN KEY (gacha_pool_id) REFERENCES gacha_pools(gacha_pool_id) ON DELETE CASCADE
                    )
                ''')

                # 添加抽卡记录表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS gacha_records (
                        record_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT NOT NULL,
                        gacha_pool_id INTEGER NOT NULL,
                        item_type TEXT NOT NULL CHECK (item_type IN ('rod', 'accessory', 'bait', 'fish', 'coins', 'titles','premium_currency')),
                        item_id INTEGER NOT NULL,
                        item_name TEXT NOT NULL,
                        quantity INTEGER DEFAULT 1,
                        rarity INTEGER DEFAULT 1,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                        FOREIGN KEY (gacha_pool_id) REFERENCES gacha_pools(gacha_pool_id) ON DELETE CASCADE
                    )
                ''')

                # User Data Tables
                cursor.execute(f'''
                                CREATE TABLE IF NOT EXISTS users (
                                    user_id TEXT PRIMARY KEY,
                                    nickname TEXT,
                                    coins INTEGER DEFAULT 0,
                                    premium_currency INTEGER DEFAULT 0 CHECK (premium_currency >= 0),
                                    total_fishing_count INTEGER DEFAULT 0,
                                    total_weight_caught INTEGER DEFAULT 0,
                                    total_coins_earned INTEGER DEFAULT 0,
                                    equipped_rod_instance_id INTEGER DEFAULT NULL,
                                    equipped_accessory_instance_id INTEGER DEFAULT NULL,
                                    current_bait_id INTEGER DEFAULT NULL,
                                    bait_start_time DATETIME DEFAULT NULL,
                                    current_title_id INTEGER DEFAULT NULL,
                                    auto_fishing_enabled INTEGER DEFAULT 0 CHECK (auto_fishing_enabled IN (0, 1)),
                                    last_fishing_time DATETIME DEFAULT NULL,
                                    last_wipe_bomb_time DATETIME DEFAULT NULL,
                                    last_steal_time DATETIME DEFAULT NULL,
                                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                                    last_login_time DATETIME DEFAULT NULL,
                                    consecutive_login_days INTEGER DEFAULT 0,
                                    FOREIGN KEY (equipped_rod_instance_id) REFERENCES user_rods(rod_instance_id) ON DELETE SET NULL,
                                    FOREIGN KEY (equipped_accessory_instance_id) REFERENCES user_accessories(accessory_instance_id) ON DELETE SET NULL,
                                    FOREIGN KEY (current_title_id) REFERENCES titles(title_id) ON DELETE SET NULL,
                                    FOREIGN KEY (current_bait_id) REFERENCES baits(bait_id) ON DELETE SET NULL
                                )
                            ''')

                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS user_fish_inventory (
                        user_id TEXT NOT NULL,
                        fish_id INTEGER NOT NULL,
                        quantity INTEGER DEFAULT 0 CHECK (quantity >= 0),
                        no_sell_until DATETIME DEFAULT NULL,
                        PRIMARY KEY (user_id, fish_id),
                        FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                        FOREIGN KEY (fish_id) REFERENCES fish(fish_id) ON DELETE CASCADE
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS user_bait_inventory (
                        user_id TEXT NOT NULL,
                        bait_id INTEGER NOT NULL,
                        quantity INTEGER DEFAULT 0 CHECK (quantity >= 0),
                        PRIMARY KEY (user_id, bait_id),
                        FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                        FOREIGN KEY (bait_id) REFERENCES baits(bait_id) ON DELETE CASCADE
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS user_rods (
                        rod_instance_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT NOT NULL,
                        rod_id INTEGER NOT NULL,
                        obtained_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        current_durability INTEGER DEFAULT NULL,
                        is_equipped INTEGER DEFAULT 0 CHECK (is_equipped IN (0, 1)),
                        FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                        FOREIGN KEY (rod_id) REFERENCES rods(rod_id) ON DELETE CASCADE
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS user_accessories (
                        accessory_instance_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT NOT NULL,
                        accessory_id INTEGER NOT NULL,
                        obtained_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        is_equipped INTEGER DEFAULT 0 CHECK (is_equipped IN (0, 1)),
                        FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                        FOREIGN KEY (accessory_id) REFERENCES accessories(accessory_id) ON DELETE CASCADE
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS user_titles (
                        user_id TEXT NOT NULL,
                        title_id INTEGER NOT NULL,
                        unlocked_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (user_id, title_id),
                        FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                        FOREIGN KEY (title_id) REFERENCES titles(title_id) ON DELETE CASCADE
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS user_achievement_progress (
                        user_id TEXT NOT NULL,
                        achievement_id INTEGER NOT NULL,
                        current_progress INTEGER DEFAULT 0,
                        completed_at DATETIME DEFAULT NULL,
                        claimed_at DATETIME DEFAULT NULL,
                        PRIMARY KEY (user_id, achievement_id),
                        FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                        FOREIGN KEY (achievement_id) REFERENCES achievements(achievement_id) ON DELETE CASCADE
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS wipe_bomb_log (
                        log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT NOT NULL,
                        contribution_amount INTEGER NOT NULL CHECK (contribution_amount > 0),
                        reward_multiplier REAL NOT NULL CHECK (reward_multiplier >= 0 AND reward_multiplier <= 10),
                        reward_amount INTEGER NOT NULL CHECK (reward_amount >= 0),
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS fishing_records (
                        record_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT NOT NULL,
                        fish_id INTEGER NOT NULL,
                        weight INTEGER NOT NULL,
                        value INTEGER NOT NULL,
                        rod_instance_id INTEGER,
                        accessory_instance_id INTEGER,
                        bait_id INTEGER,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                        location_id INTEGER DEFAULT NULL,
                        is_king_size INTEGER DEFAULT 0 CHECK (is_king_size IN (0,1)),
                        FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                        FOREIGN KEY (fish_id) REFERENCES fish(fish_id) ON DELETE RESTRICT,
                        FOREIGN KEY (rod_instance_id) REFERENCES user_rods(rod_instance_id) ON DELETE SET NULL,
                        FOREIGN KEY (accessory_instance_id) REFERENCES user_accessories(accessory_instance_id) ON DELETE SET NULL,
                        FOREIGN KEY (bait_id) REFERENCES baits(bait_id) ON DELETE SET NULL
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS check_ins (
                        user_id TEXT NOT NULL,
                        check_in_date DATE NOT NULL, -- Use DATE type
                        PRIMARY KEY (user_id, check_in_date),
                        FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS subsidies (
                        user_id TEXT NOT NULL,
                        subsidy_date DATE NOT NULL, -- Use DATE type
                        PRIMARY KEY (user_id, subsidy_date),
                        FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                    )
                ''')
                # 创建市场表
                cursor.execute(f'''
                    CREATE TABLE IF NOT EXISTS market (
                        market_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT NOT NULL,
                        item_type TEXT NOT NULL CHECK (item_type IN ('fish', 'bait', 'rod', 'accessory')),
                        item_id INTEGER NOT NULL,
                        quantity INTEGER NOT NULL CHECK (quantity > 0),
                        price INTEGER NOT NULL CHECK (price > 0),
                        listed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        expires_at DATETIME DEFAULT NULL,
                        FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS taxes (
                        tax_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT NOT NULL,
                        tax_amount INTEGER NOT NULL,
                        tax_rate REAL NOT NULL,
                        original_amount INTEGER NOT NULL,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                        tax_type TEXT NOT NULL DEFAULT 'daily',
                        balance_after INTEGER NOT NULL,
                        FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                    )
                ''')

                # Indices
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_coins ON users(coins)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_last_login ON users(last_login_time)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_fish_inventory_user ON user_fish_inventory(user_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_bait_inventory_user ON user_bait_inventory(user_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_rods_user ON user_rods(user_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_accessories_user ON user_accessories(user_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_titles_user ON user_titles(user_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_achievement_progress_user ON user_achievement_progress(user_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_wipe_bomb_log_user_time ON wipe_bomb_log(user_id, timestamp)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_fishing_records_user_time ON fishing_records(user_id, timestamp)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_fishing_records_fish_id ON fishing_records(fish_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_gacha_pool_items_pool_type ON gacha_pool_items(gacha_pool_id, item_type)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_gacha_records_user_time ON gacha_records(user_id, timestamp)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_market_user ON market(user_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_market_item ON market(item_type, item_id)")

                conn.commit()
                logger.info("Database schema initialization complete.")
        except sqlite3.Error as e:
            logger.error(f"Database initialization failed: {e}", exc_info=True)
            raise # Stop execution if DB init fails

    def initialize_core_data(self) -> None:
        """
        Initializes core configuration data like fish types, baits, etc.
        This should be idempotent.
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                # --- Initialize Fish (Example subset) ---
                fish_data = [
                    # --- Fish Data (Formatted for Auto-Increment ID) ---
                    # Format: (name, description, rarity, base_value, min_weight, max_weight, icon_url)
                    # Rarity 1
                    ('小鲫鱼', '一条非常常见的小鱼。', 1, 10, 100, 500, None),
                    ('泥鳅', '滑溜溜的小家伙。', 1, 15, 50, 200, None),
                    ('小虾', '常见的水底生物。', 1, 20, 30, 100, None),
                    ('沙丁鱼', '成群结队的小型海鱼。', 1, 12, 100, 300, None),
                    ('小黄鱼', '体色金黄，常见食用鱼。', 1, 18, 150, 400, None),
                    ('海虾', '比淡水虾稍大。', 1, 25, 50, 150, None),
                    ('破旧的靴子', '谁把靴子扔水里了？还能穿吗？', 1, 1, 200, 800, None),  # Junk
                    ('生锈的铁罐', '被水泡得不成样子了。', 1, 2, 100, 400, None),  # Junk
                    ('缠绕的水草', '一团湿漉漉的水生植物。', 1, 1, 50, 300, None),  # Junk
                    ('普通石头', '就是一块普通的石头，沉甸甸的。', 1, 0, 500, 2000, None),  # Junk (Value 0)
                    ('罗非鱼', '繁殖能力很强，适应性好。', 1, 13, 120, 600, None),
                    ('鲦鱼', '溪流中常见的小型杂食鱼。', 1, 8, 20, 80, None),
                    ('鮈鱼', '生活在水底的小型鲤科鱼。', 1, 9, 30, 100, None),
                    ('银鲈', '沿海常见的小型银色鱼类。', 1, 16, 130, 450, None),
                    ('大西洋黄花鱼', '能发出类似蛙鸣的鼓噪声。', 1, 17, 160, 550, None),
                    ('斑点鱼', '尾鳍基部有个明显的黑斑。', 1, 14, 110, 350, None),
                    ('食蚊鱼', '以蚊子幼虫为食，体型微小。', 1, 5, 10, 30, None),
                    ('凤尾鱼', '常被用来制作鱼干或罐头。', 1, 7, 15, 60, None),
                    ('胡瓜鱼', '体型细长，有一种特殊的黄瓜味。', 1, 11, 80, 250, None),

                    # Rarity 2
                    ('草鱼', '喜欢吃草的淡水鱼。', 2, 50, 500, 2000, None),
                    ('鲤鱼', '据说能带来好运。', 2, 60, 600, 2500, None),
                    ('鲢鱼', '头部较大，滤食性鱼类。', 2, 55, 500, 2000, None),
                    ('鳊鱼', '体型侧扁，味道不错。', 2, 65, 600, 2500, None),
                    ('鲅鱼', '体型较长，常做熏鱼。', 2, 70, 700, 3000, None),
                    ('带鱼', '身体扁长如带。', 2, 75, 800, 3500, None),
                    ('黄花鱼', '分为大黄鱼和小黄鱼。', 2, 80, 900, 4000, None),
                    ('鲳鱼', '肉厚刺少。', 2, 85, 1000, 4500, None),
                    ('河豚', '生气时会鼓成一个球，可能有毒！', 2, 40, 300, 1500, None),
                    ('小丑鱼', '和海葵共生，颜色鲜艳。', 2, 45, 80, 250, None),
                    ('螃蟹', '横行霸道的甲壳生物。', 2, 35, 200, 1000, None),  # Crustacean
                    ('河鲈', '广泛分布的淡水掠食性鱼类。', 2, 48, 400, 1800, None),
                    ('蓝鳃太阳鱼', '北美常见的太阳鱼，色彩鲜艳。', 2, 42, 350, 1500, None),
                    ('莓鲈', '北美常见的两种太阳鱼，分黑莓鲈和白莓鲈。', 2, 44, 380, 1600, None),
                    ('玻璃梭鲈', '眼睛在光下会反光，夜行性。', 2, 68, 650, 2800, None),
                    ('牛头鱼', '头大嘴宽，常见的小型鲶鱼。', 2, 38, 300, 1400, None),
                    ('羊头鱼', '牙齿像羊齿，能咬碎贝壳。', 2, 72, 750, 3200, None),
                    ('比目鱼', '眼睛长在同一侧，身体扁平。', 2, 62, 600, 2600, None),
                    ('黑线鳕', '背部有明显的黑色侧线。', 2, 58, 550, 2400, None),
                    ('青鳕', '常见的食用鱼，肉质白色。', 2, 52, 500, 2200, None),
                    ('无须鳕', '深水鱼类，常用于鱼排。', 2, 54, 520, 2300, None),
                    ('鲭鱼', '体型纺锤，游泳速度快。', 2, 67, 700, 3100, None),
                    ('斧头鱼', '身体侧扁像斧头，深海发光鱼。', 2, 88, 100, 400, None),
                    ('鳞鲀', '有一个可以锁定的背鳍棘刺。', 2, 78, 800, 3400, None),

                    # Rarity 3
                    ('鲈鱼', '肉质鲜美，适合清蒸。', 3, 100, 800, 3000, None),
                    ('黑鱼', '生性凶猛的掠食者。', 3, 150, 1000, 4000, None),
                    ('鳜鱼', '又称桂鱼，名贵食用鱼。', 3, 120, 1000, 5000, None),
                    ('胭脂鱼', '色彩艳丽，国家保护动物(游戏中)。', 3, 180, 1200, 6000, None),
                    ('鲨鱼', '海洋中的顶级掠食者之一。', 3, 200, 5000, 20000, None),
                    ('金枪鱼', '高速游泳的大型鱼类。', 3, 250, 6000, 25000, None),  # Generic Tuna
                    ('石斑鱼', '名贵的海产鱼类。', 3, 300, 7000, 30000, None),  # Generic Grouper
                    ('鲷鱼', '体色鲜艳，寓意吉祥。', 3, 350, 8000, 35000, None),  # Generic Snapper/Bream
                    ('食人鱼', '牙齿锋利，成群时很危险。', 3, 110, 500, 2000, None),
                    ('章鱼', '非常聪明，有很多触手。', 3, 140, 1000, 5000, None),  # Cephalopod
                    ('狗鱼', '体型细长，嘴巴像鸭嘴。', 3, 130, 1100, 5500, None),
                    ('大口黑鲈', '北美最受欢迎的游钓鱼之一。', 3, 145, 1200, 6000, None),
                    ('鳟鱼', '生活在清澈冷水中，种类繁多。', 3, 165, 1400, 7000, None),  # Generic Trout
                    ('鲑鱼', '会洄游产卵的著名鱼类。', 3, 175, 1500, 8000, None),  # Generic Salmon
                    ('鲟鱼', '古老的鱼类，产鱼子酱。', 3, 280, 4000, 18000, None),
                    ('匙吻鲟', '吻部像船桨，滤食性。', 3, 260, 3500, 16000, None),
                    ('鲶鱼', '有胡须，种类繁多，从大到小。', 3, 115, 1000, 9000, None),  # Generic Catfish
                    ('鲯鳅', '体色鲜艳，游泳速度快。', 3, 290, 5000, 22000, None),
                    ('军曹鱼', '体型像鲨鱼，常跟随大型海洋生物。', 3, 240, 4500, 20000, None),
                    ('梭鱼', '体型细长，牙齿锋利的海中猎手。', 3, 210, 3000, 15000, None),
                    ('鮟鱇鱼', '长相奇特，用诱饵捕食。', 3, 190, 2000, 12000, None),
                    ('灯笼鱼', '深海中最常见的发光鱼类。', 3, 95, 50, 200, None),
                    ('蝰鱼', '牙齿极长，无法完全闭合嘴巴。', 3, 230, 400, 1800, None),  # Deep Sea

                    # Rarity 4
                    ('金龙鱼', '价值不菲的观赏鱼。', 4, 500, 2000, 8000, None),
                    ('清道夫', '常被误认为能清洁水质。', 4, 450, 2000, 10000, None),  # Adjusted value
                    ('娃娃鱼', '学名大鲵，叫声似婴儿啼哭。', 4, 800, 3000, 15000, None),
                    ('蓝鳍金枪鱼', '金枪鱼中的极品，价格昂贵。', 4, 1000, 10000, 50000, None),
                    ('剑鱼', '上颌延长呈剑状。', 4, 1200, 12000, 60000, None),
                    ('海豚', '聪明友善的海洋哺乳动物。', 4, 900, 15000, 70000, None),  # Lowered value slightly
                    ('鲸鱼', '巨大的海洋哺乳动物。', 4, 1500, 20000, 100000, None),  # Lowered value slightly
                    ('电鳗', '能释放强大的电流。', 4, 600, 1500, 6000, None),  # Upgraded rarity
                    ('海龟', '长寿的海洋爬行动物。', 4, 750, 10000, 50000, None),  # Upgraded rarity
                    ('深海鮟鱇', '用头顶的"灯笼"诱捕猎物。', 4, 700, 2500, 12000, None),  # More specific name
                    ('沉没的宝箱', '里面似乎装着什么东西？（打开可能获得金币或其他物品）', 4, 100, 5000, 15000, None),
                    # Item
                    ('腔棘鱼', '被称为活化石的古老鱼类。', 4, 1100, 8000, 40000, None),
                    ('桔连鳍鲑', '寿命极长，生长缓慢的深海鱼。', 4, 850, 1500, 7000, None),
                    ('皇带鱼', '世界上最长的硬骨鱼，传说中的"海蛇"。', 4, 1300, 50000, 300000, None),
                    ('尖牙鱼', '牙齿相对于体型来说非常巨大。', 4, 680, 300, 1200, None),  # Deep Sea
                    ('水滴鱼', '离开深海高压环境后变成一滩凝胶状。', 4, 400, 1000, 5000, None),  # Famous 'ugly' fish
                    ('光颌鱼', '能发出和感知红光的深海鱼。', 4, 950, 200, 800, None),  # Deep Sea
                    ('角鮟鱇', '雌雄体型差异巨大的深海鮟鱇。', 4, 820, 1800, 9000, None),  # Deep Sea
                    ('黑魔鬼鱼', '另一种深海鮟鱇，通体黑色。', 4, 880, 1600, 8500, None),  # Deep Sea
                    ('鳕鲈', '生活在海底峡谷边缘的鱼类。', 4, 720, 3000, 14000, None),
                    ('大比目鱼', '大型的比目鱼，价值较高。', 4, 980, 15000, 80000, None),
                    ('旗鱼', '背鳍高大如旗，速度极快。', 4, 1400, 30000, 150000, None),

                    # Rarity 5
                    ('锦鲤', '极其珍贵，象征吉祥。', 5, 1000, 5000, 15000, None),  # Adjusted value
                    ('龙王', '传说中的四海之主(的投影?)。', 5, 5000, 50000, 200000, None),
                    ('美人鱼', '传说中的海洋生物。', 5, 8000, 80000, 300000, None),
                    ('深海巨妖', '盘踞在深渊中的恐怖存在。', 5, 10000, 100000, 500000, None),
                    ('海神三叉戟', '遗落在某处的神器(的一部分)。', 5, 15000, 500, 1500, None),
                    # Adjusted weights/value for item
                    ('时间沙漏', '据说能短暂地影响时间流逝的神器部件。', 5, 20000, 300, 1000, None),  # Item
                    ('克拉肯之触', '传说巨妖的一小部分，依然充满力量。', 5, 11000, 80000, 250000, None),  # Mythical Part
                    ('许德拉之鳞', '九头蛇的鳞片，闪耀着再生的光泽。', 5, 13000, 100, 500, None),  # Mythical Item
                    ('尘世巨蟒之环', '环绕世界之蛇蜕下的一节，蕴含世界之力。', 5, 22000, 200, 800, None),  # Mythical Item
                    ('神马', '神话中波塞冬的坐骑，半马半鱼。', 5, 7000, 4000, 12000, None),
                    # Mythical Creature (Simplified name from Hippocampus)
                    ('狮子鱼', '外表华丽但棘刺剧毒，属于入侵物种（游戏中设为稀有）。', 5, 800, 500, 2000, None),
                    # Real, but made rare for game
                    ('幽灵鲨', '深海软骨鱼，样子奇特，像缝合怪。', 5, 6500, 6000, 18000, None),  # Deep Sea Cartilaginous
                    ('吸血鬼乌贼', '既不是乌贼也不是章鱼，能像斗篷一样包裹自己。', 5, 7500, 800, 2500, None),
                    # Deep Sea Cephalopod relative
                    ('阿斯皮多凯隆幼龟', '传说中的岛龟的幼崽，背上已有微缩景观。', 5, 16000, 100000, 400000, None),
                    # Mythical Creature
                    ('最深之鱼', '来自马里亚纳海沟深处的神秘生物，几乎无法承受低压。', 5, 30000, 50, 150, None),
                ]

                cursor.executemany('''
                    INSERT OR IGNORE INTO fish (name, description, rarity, base_value, min_weight, max_weight, icon_url)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', fish_data)

                # --- Initialize Baits ---
                bait_data = [
                    # Format: (name, description, rarity, effect_description, duration_minutes, cost, required_rod_rarity)
                    # --- Rarity 1 (基础) ---
                    ('普通蚯蚓', '最基础的鱼饵，随处可见。', 1, '无特殊效果', 0, 5, 0),
                    ('面包团', '用面包捏成的简单鱼饵。', 1, '容易吸引小型杂食鱼类', 0, 3, 0),
                    ('玉米粒', '甜甜的玉米粒，有些鱼喜欢。', 1, '略微提高鲤科鱼上钩率', 0, 4, 0),

                    # --- Rarity 2 (进阶) ---
                    ('红虫', '营养丰富的鱼饵，很多鱼都爱吃。', 2, '提高中小型淡水鱼上钩率', 0, 20, 0),
                    ('亮片拟饵', '旋转时能反光的基础金属拟饵。', 2, '略微提高掠食性鱼类上钩率，无消耗', 0, 50, 1),  # 拟饵
                    ('腥味颗粒饵', '商业生产的鱼饵，气味浓烈。', 2, '提高多种淡水鱼上钩率', 0, 30, 1),

                    # --- Rarity 3 (高级) ---
                    ('万能饵', '精心调配，对大多数鱼类都有效果。', 3, '提高所有鱼种上钩率', 0, 100, 0),
                    ('活虾', '活蹦乱跳的虾，是许多鱼类的美味。', 3, '显著提高中大型海鱼上钩率', 0, 80, 1),
                    ('驱散垃圾饵', '散发着垃圾鱼讨厌的气味。', 3, '降低钓上 Rarity 1 垃圾的概率', 30, 250, 1),  # 持续时间

                    # --- Rarity 4 (稀有) ---
                    ('秘制香饵', '用特殊配方制成，对稀有鱼类极具诱惑力。', 4, '显著提高 Rarity 3及以上鱼的上钩率', 0, 500,
                     2),
                    ('价值连城饵', '散发着财富的气息。', 4, '钓上的鱼基础价值+10%', 0, 700, 3),
                    ('大师拟饵', '由钓鱼大师制作的完美拟饵。', 4, '大幅提高掠食性鱼类上钩率，无消耗', 0, 1000, 3),  # 拟饵

                    # --- Rarity 5 (传说) ---
                    # ('龙涎香饵', '沾染了龙王气息的神秘饵料。', 5, '极大提高 Rarity 5 鱼的上钩率', 0, 0, 3),  # 特殊获取
                    ('巨物诱饵', '蕴含着远古力量，能吸引庞然大物。', 5, '钓上的鱼最大重量潜力+20%', 0, 2500, 4),
                    # ('丰饶号角粉末', '从丰收号角上刮下来的一点粉末。', 5, '下一次钓鱼必定获得双倍数量的鱼', 0, 0, 5),
                    ('奇迹水滴', '一滴蕴含着丰饶魔力的水珠，能让渔获凭空倍增。', 5, '下一次钓鱼必定获得双倍数量', 0, 5000, 0),
                    # 特殊获取
                ]

                cursor.executemany('''
                    INSERT OR IGNORE INTO baits (name, description, rarity, effect_description, duration_minutes, cost, required_rod_rarity)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', bait_data)

                # --- Initialize Rods ---
                rod_data = [
                    ('新手木竿', '刚入门时的可靠伙伴', 1, 'shop', 50, 1.0, 1.0, 0.0, None, None),
                    ('竹制鱼竿', '轻巧耐用', 2, 'shop', 500, 1.0, 1.0, 0.01, None, None),
                    ('碳素纤维竿', '现代工艺的结晶', 3, 'shop', 5000, 1.05, 1.0, 0.03, 1000, None), # Has durability
                    ('星辰钓者', '蕴含星光力量的神秘鱼竿', 4, 'gacha', None, 1.1, 1.0, 0.08, None, None),
                    ('海神之赐', '传说中海神波塞冬使用过的鱼竿', 5, 'gacha', None, 1.2, 1.1, 0.15, None, None),
                ]
                cursor.executemany('''
                    INSERT OR IGNORE INTO rods (name, description, rarity, source, purchase_cost, bonus_fish_quality_modifier, bonus_fish_quantity_modifier, bonus_rare_fish_chance, durability, icon_url)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', rod_data)

                # --- Initialize Accessories ---
                accessory_data = [
                    ('幸运四叶草', '带来好运的小饰品', 2, 'charm', 1.05, 1.0, 0.01, 1.02, None, None),
                    ('渔夫的戒指', '刻有古老符文的戒指', 3, 'ring', 1.0, 1.0, 0.0, 1.10, None, None),
                    ('丰收号角', '象征丰收的魔法号角', 4, 'trinket', 1.10, 1.05, 0.03, 1.15, None, None),
                    ('海洋之心', '传说中的宝石，能与海洋生物沟通', 5, 'amulet', 1.20, 1.10, 0.05, 1.25, '大幅减少钓鱼等待时间', None),
                ]
                cursor.executemany('''
                    INSERT OR IGNORE INTO accessories (name, description, rarity, slot_type, bonus_fish_quality_modifier, bonus_fish_quantity_modifier, bonus_rare_fish_chance, bonus_coin_modifier, other_bonus_description, icon_url)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', accessory_data)

                # --- Initialize Titles ---
                title_data = [
                    (1, '钓鱼新手', '完成第一次钓鱼', '{name}'),
                    (2, '熟练渔夫', '累计钓上100条鱼', '{name}'),
                    (3, '钓鱼大师', '累计钓上1000条鱼', '钓鱼大师 {username}'),
                    (4, '图鉴收藏家', '钓到10种不同的鱼', '{username}收藏家'),
                    (5, '百万富翁', '累计赚取1,000,000金币', '富有的 {username}'),
                    (6, '擦弹之王', '在擦弹中获得10倍奖励', '{username}, 擦弹之王!'),
                    (7, '幸运星', '钓到锦鲤', '幸运的 {username}'),
                    (8, '海神眷属', '钓到海神三叉戟', '海神眷属 {username}'),
                    (9, '回收大师', '累计钓上50个垃圾物品', '回收大师 {username}'),
                    (10, '物种观察员', '收集25种不同的鱼', '{username}观察员'),
                    (11, '鱼类学者', '收集50种不同的鱼', '鱼类学者 {username}'),
                    (12, '深渊垂钓者', '收集15种不同的深海鱼类', '深渊垂钓者 {username}'),
                    (13, '活化石发现者', '钓到腔棘鱼', '{username}, 活化石发现者'),
                    (14, '巨兽捕手', '钓到皇带鱼', '{username}, 巨兽捕手'),
                    (15, '重量级选手', '累计钓鱼总重量达到10,000公斤', '{username}, 重量级!'),
                    (16, '吨位钓手', '累计钓鱼总重量达到100,000公斤', '{username}, 力能扛鼎!'),
                    (17, '神器收藏家', '钓到任意传说级物品（非生物）', '{username}, 神器猎人'),  # 如三叉戟, 沙漏, 鳞片, 指环
                    (18, '神话猎人', '钓到任意传说级生物', '{username}, 神话猎人'),  # 如龙王, 美人鱼, 巨妖, 神马, 幼龟
                    (19, '虚空渔夫', '钓到最深之鱼', '{username}, 虚空渔夫'),
                ]
                cursor.executemany('''
                    INSERT OR IGNORE INTO titles (title_id, name, description, display_format)
                    VALUES (?, ?, ?, ?)
                ''', title_data)

                # --- Initialize Achievements ---
                achievement_data = [
                    # (name, description, target_type, target_value, target_fish_id, reward_type, reward_value, reward_quantity, is_repeatable, icon_url)

                    # 基础与计数
                    ('初试身手', '成功钓到第一条鱼', 'total_fish_count', 1, None, 'coins', 50, 1, 0, None),
                    ('小有所成', '累计钓到100条鱼', 'total_fish_count', 100, None, 'coins', 500, 1, 0, None),
                    ('百竿不空', '累计钓到1000条鱼', 'total_fish_count', 1000, None, 'title', 3, 1, 0, None),
                    # 奖励 "钓鱼大师"
                    (
                    '渔获颇丰', '累计钓到5000条鱼', 'total_fish_count', 5000, None, 'premium_currency', 50, 1, 0, None),

                    # 图鉴收集
                    ('图鉴收集者I', '收集10种不同的鱼', 'specific_fish_count', 10, None, 'bait', 3, 5, 0, None),
                    # 奖励5个万能饵 (bait_id=3) - target_type可能需要调整为记录不同种类数量
                    ('图鉴收集者II', '收集25种不同的鱼', 'specific_fish_count', 25, None, 'title', 10, 1, 0, None),
                    # 奖励 "物种观察员" - target_type同上
                    ('图鉴收集者III', '收集50种不同的鱼', 'specific_fish_count', 50, None, 'title', 11, 1, 0, None),
                    # 奖励 "鱼类学者" - target_type同上
                    ('物种大师', '收集所有种类的鱼', 'specific_fish_count', 112, None, 'premium_currency', 500, 1, 0, None), # 假设总共112种 - target_type同上

                    # 金币与经济
                    ('金币猎手', '累计赚取10,000金币', 'total_coins_earned', 10000, None, 'coins', 1000, 1, 0, None),
                    (
                    '家财万贯', '累计赚取100,000金币', 'total_coins_earned', 100000, None, 'premium_currency', 20, 1, 0,
                    None),
                    ('富可敌国', '累计赚取1,000,000金币', 'total_coins_earned', 1000000, None, 'title', 5, 1, 0, None),
                    # 奖励 "百万富翁"

                    # 擦弹相关
                    ('试试手气', '进行第一次擦弹', 'wipe_bomb_profit', 1, None, 'coins', 100, 1, 0, None),  # 随便盈利1块钱就算
                    ('一夜暴富?', '在擦弹中单次盈利超过5000金币', 'wipe_bomb_profit', 5000, None, 'coins', 2000, 1, 0,
                     None),
                    ('十倍奉还！', '在擦弹中获得10倍奖励', 'wipe_bomb_profit', 10, None, 'title', 6, 1, 0, None),
                    # 奖励 "擦弹之王" (target_value=10 代表10倍)

                    # 装备相关
                    ('鸟枪换炮', '获得一个稀有度为3的鱼竿', 'rod_collection', 3, None, 'bait', 8, 3, 0, None),
                    # 奖励3个活虾 (假设bait_id=8)
                    (
                    '神竿!', '获得一个稀有度为5的鱼竿', 'rod_collection', 5, None, 'premium_currency', 100, 1, 0, None),
                    ('珠光宝气', '获得一个稀有度为3的饰品', 'accessory_collection', 3, None, 'coins', 1500, 1, 0, None),
                    ('海神之佑', '获得一个稀有度为5的饰品', 'accessory_collection', 5, None, 'premium_currency', 100, 1,
                     0, None),

                    # 特定鱼/物品捕捉
                    ('锦鲤附体', '钓到一条锦鲤', 'specific_fish_count', 7, 7, 'title', 7, 1, 0, None),
                    # 奖励 "幸运星", target_fish_id=7 (锦鲤)
                    ('神器发现者', '钓到海神三叉戟', 'specific_fish_count', 34, 34, 'title', 8, 1, 0, None),
                    # 奖励 "海神眷属", target_fish_id=34
                    ('远古的回响', '钓到腔棘鱼', 'specific_fish_count', 93, 93, 'title', 14, 1, 0, None),
                    # 奖励 "活化石发现者", target_fish_id=93
                    ('海蛇传说', '钓到皇带鱼', 'specific_fish_count', 95, 95, 'title', 15, 1, 0, None),
                    # 奖励 "巨兽捕手", target_fish_id=95
                    ('危险水域', '钓到食人鱼', 'specific_fish_count', 45, 45, 'coins', 200, 1, 0, None),
                    # target_fish_id=45
                    ('意外之财', '钓到沉没的宝箱', 'specific_fish_count', 54, 54, 'coins', 500, 1, 0, None),
                    # target_fish_id=54
                    ('失落的遗物', '钓到任意传说级物品', 'specific_fish_count', -1, -1, 'title', 18, 1, 0, None),
                    # target_fish_id=-1 代表类型匹配 (需要代码逻辑支持)
                    ('传说的回响', '钓到任意传说级生物', 'specific_fish_count', -2, -2, 'title', 19, 1, 0, None),
                    # target_fish_id=-2 代表类型匹配 (需要代码逻辑支持)
                    ('触及虚空', '钓到最深之鱼', 'specific_fish_count', 112, 112, 'title', 20, 1, 0, None),
                    # 奖励 "虚空渔夫", target_fish_id=112

                    # 垃圾清理
                    ('清理河道I', '累计钓上10个垃圾物品', 'specific_fish_count', -3, -3, 'coins', 100, 1, 0, None),
                    # target_fish_id=-3 代表垃圾类型 (需要代码逻辑支持)
                    ('回收站常客', '累计钓上50个垃圾物品', 'specific_fish_count', -3, -3, 'title', 9, 1, 0, None),
                    # 奖励 "回收大师" - target_fish_id同上

                    # 深海探索 (需要定义深海鱼列表/标签)
                    ('深渊窥探者', '收集5种不同的深海鱼类', 'specific_fish_count', -4, -4, 'title', 12, 1, 0, None),
                    # 奖励 "深潜者", target_fish_id=-4 代表深海类型
                    ('深海主宰', '收集15种不同的深海鱼类', 'specific_fish_count', -4, -4, 'title', 13, 1, 0, None),
                    # 奖励 "深渊垂钓者", target_fish_id同上

                    # 重量相关
                    ('初露锋芒', '累计钓鱼总重量达到10,000公斤', 'total_weight_caught', 10000000, None, 'title', 16, 1,
                     0, None),  # 10,000kg = 10,000,000g
                    (
                    '力拔山兮', '累计钓鱼总重量达到100,000公斤', 'total_weight_caught', 100000000, None, 'title', 17, 1,
                    0, None),  # 100,000kg = 100,000,000g
                    ('庞然大物', '单次钓上重量超过100公斤的鱼', 'specific_fish_count', -5, -5, 'bait', 14, 1, 0, None),
                    # 奖励 巨物诱饵(假设id=14), target_fish_id=-5 代表重量>100kg
                ]

                # 在 initialize_core_data 中插入:
                # cursor.executemany('''
                #     INSERT OR IGNORE INTO achievements (name, description, target_type, target_value, target_fish_id, reward_type, reward_value, reward_quantity, is_repeatable, icon_url)
                #     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                # ''', achievement_data)

                cursor.executemany('''
                    INSERT OR IGNORE INTO achievements (name, description, target_type, target_value, target_fish_id, reward_type, reward_value, reward_quantity, is_repeatable, icon_url)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', achievement_data)

                # --- Initialize Gacha Pools ---
                cursor.execute('''
                    INSERT OR IGNORE INTO gacha_pools (gacha_pool_id, name, description, cost_coins, cost_premium_currency)
                    VALUES (1, '鱼竿抽奖池', '含有高级鱼竿', 5000, 0)
                ''')
                cursor.execute('''
                    INSERT OR IGNORE INTO gacha_pools (gacha_pool_id, name, description, cost_coins, cost_premium_currency)
                    VALUES (2, '饰品抽奖池', '含有各类钓鱼饰品', 10000, 0)
                ''')
                
                # 初始化时调整奖池权重，避免出现重复物品
                self.adjust_gacha_pool_weights()

                
                conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Failed to initialize core data: {e}", exc_info=True)

    # --- 用户相关操作 ---
    def register_user(self, user_id: str, nickname: str) -> bool:
        """注册新用户"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("INSERT OR IGNORE INTO users (user_id, nickname) VALUES (?, ?)", 
                             (user_id, nickname))
                conn.commit()
                return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"注册用户失败: {e}")
            return False

    def check_user_registered(self, user_id: str) -> bool:
        """检查用户是否已注册"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,))
            return cursor.fetchone() is not None

    def set_user_last_fishing_time(self, user_id: str) -> bool:
        """设置用户最后钓鱼时间"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                # 使用Python的datetime.now()获取当前时间，东八区
                current_time = get_utc4_now().strftime('%Y-%m-%d %H:%M:%S')
                cursor.execute("UPDATE users SET last_fishing_time = ? WHERE user_id = ?", (current_time, user_id))
                conn.commit()
                return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"设置用户最后钓鱼时间失败: {e}")
            return False

    def get_user_equipment(self, user_id: str) -> Dict:
        """获取用户装备的鱼竿和饰品信息"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    COALESCE(r.bonus_fish_quality_modifier, 1.0) as rod_quality_modifier,
                    COALESCE(r.bonus_fish_quantity_modifier, 1.0) as rod_quantity_modifier,
                    COALESCE(r.bonus_rare_fish_chance, 0.0) as rod_rare_chance,
                    COALESCE(a.bonus_fish_quality_modifier, 1.0) as acc_quality_modifier,
                    COALESCE(a.bonus_fish_quantity_modifier, 1.0) as acc_quantity_modifier,
                    COALESCE(a.bonus_rare_fish_chance, 0.0) as acc_rare_chance
                FROM users u
                LEFT JOIN user_rods ur ON u.equipped_rod_instance_id = ur.rod_instance_id
                LEFT JOIN rods r ON ur.rod_id = r.rod_id
                LEFT JOIN user_accessories ua ON u.equipped_accessory_instance_id = ua.accessory_instance_id
                LEFT JOIN accessories a ON ua.accessory_id = a.accessory_id
                WHERE u.user_id = ?
            """, (user_id,))
            result = cursor.fetchone()
            if result:
                return dict(result)
            else:
                # 如果查询没有结果，返回默认值
                return {
                    "rod_quality_modifier": 1.0,
                    "rod_quantity_modifier": 1.0,
                    "rod_rare_chance": 0.0,
                    "acc_quality_modifier": 1.0,
                    "acc_quantity_modifier": 1.0,
                    "acc_rare_chance": 0.0
                }

    def get_random_fish(self) -> Dict:
        """随机获取一条鱼"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT fish_id, name, rarity, base_value, min_weight, max_weight
                FROM fish
                ORDER BY RANDOM()
                LIMIT 1
            """)
            fish = cursor.fetchone()
            return dict(fish) if fish else None

    def add_fish_to_inventory(self, user_id: str, fish_id: int, quantity: int = 1) -> bool:
        """将鱼添加到用户库存"""
        if quantity <= 0:
            return False

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                # 先检查用户的鱼塘容量是否足够
                cursor.execute("SELECT fish_pond_capacity FROM users WHERE user_id = ?", (user_id,))
                result = cursor.fetchone()
                # 先获取用户鱼塘中所有鱼的数量
                cursor.execute("SELECT SUM(quantity) FROM user_fish_inventory WHERE user_id = ?", (user_id,))
                current_quantity = cursor.fetchone()[0] or 0

                # 如果鱼塘容量不足，鱼塘内随机删除一条鱼
                if result and current_quantity >= result[0]:
                    logger.warning(f"用户 {user_id} 鱼塘容量不足，无法添加 {quantity} 条鱼。")
                    # 在这里可以选择不添加，或者只添加部分，为简单起见我们直接拒绝
                    # 如果需要更复杂的逻辑，比如只添加满为止，可以在这里修改
                    return False # 返回False，让上层知道操作未完全成功
                   # cursor.execute("""
                   #     DELETE FROM user_fish_inventory 
                   #     WHERE user_id = ? 
                   #     ORDER BY RANDOM() 
                   #     LIMIT 1
                   # """, (user_id,))

                cursor.execute("""
                    INSERT INTO user_fish_inventory (user_id, fish_id, quantity)
                    VALUES (?, ?, ?)
                    ON CONFLICT(user_id, fish_id) DO UPDATE SET quantity = quantity + 1
                """, (user_id, fish_id, quantity))
                conn.commit()
                return True
        except sqlite3.Error as e:
            logger.error(f"添加鱼到库存失败: {e}")
            return False

    def update_user_fishing_stats(self, user_id: str, weight: int, value: int) -> bool:
        """更新用户钓鱼统计数据"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                # 使用Python的datetime.now()获取当前时间，东八区
                current_time = get_utc4_now().strftime('%Y-%m-%d %H:%M:%S')
                cursor.execute("""
                    UPDATE users 
                    SET total_fishing_count = total_fishing_count + 1,
                        total_weight_caught = total_weight_caught + ?,
                        total_coins_earned = total_coins_earned + ?,
                        last_fishing_time = ?
                    WHERE user_id = ?
                """, (weight, value, current_time, user_id))
                conn.commit()
                return True
        except sqlite3.Error as e:
            logger.error(f"更新用户钓鱼统计失败: {e}")
            return False

    def toggle_user_auto_fishing(self, user_id: str) -> bool:
        """开启/关闭用户自动钓鱼"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE users 
                    SET auto_fishing_enabled = NOT auto_fishing_enabled
                    WHERE user_id = ?
                """, (user_id,))
                conn.commit()
                return True
        except sqlite3.Error as e:
            logger.error(f"切换自动钓鱼状态失败: {e}")
            return False

    def get_user_auto_fishing_status(self, user_id: str) -> bool:
        """获取用户自动钓鱼状态"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT auto_fishing_enabled FROM users WHERE user_id = ?", (user_id,))
            result = cursor.fetchone()
            return bool(result[0]) if result else False

    # --- 鱼库存相关操作 ---
    def get_user_fish_inventory_value(self, user_id: str) -> int:
        """获取用户鱼库存总价值"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT SUM(f.base_value * ufi.quantity)
                FROM user_fish_inventory ufi
                JOIN fish f ON ufi.fish_id = f.fish_id
                WHERE ufi.user_id = ?
            """, (user_id,))
            result = cursor.fetchone()
            return result[0] or 0

    def get_user_fish_inventory_value_by_rarity(self, user_id: str, rarity: int) -> int:
        """获取用户指定稀有度鱼的总价值"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT SUM(f.base_value * ufi.quantity)
                FROM user_fish_inventory ufi
                JOIN fish f ON ufi.fish_id = f.fish_id
                WHERE ufi.user_id = ? AND f.rarity = ?
            """, (user_id, rarity))
            result = cursor.fetchone()
            return result[0] or 0

    def clear_user_fish_inventory(self, user_id: str) -> bool:
        """清空用户鱼库存"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM user_fish_inventory WHERE user_id = ?", (user_id,))
                conn.commit()
                return True
        except sqlite3.Error as e:
            logger.error(f"清空鱼库存失败: {e}")
            return False

    def clear_user_fish_by_rarity(self, user_id: str, rarity: int) -> bool:
        """清空用户指定稀有度的鱼"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    DELETE FROM user_fish_inventory 
                    WHERE user_id = ? AND fish_id IN (
                        SELECT fish_id FROM fish WHERE rarity = ?
                    )
                """, (user_id, rarity))
                conn.commit()
                return True
        except sqlite3.Error as e:
            logger.error(f"清空指定稀有度鱼失败: {e}")
            return False

    def update_user_coins(self, user_id: str, amount: int) -> bool:
        """【新】更新修仙数据库的灵石数量"""
        mode = 1 if amount >= 0 else 2
        try:
            self.xiuxian_service.update_ls(user_id, abs(amount), mode)
            return True
        except Exception as e:
            logger.error(f"跨系统更新灵石失败: {e}")
            return False

    def get_all_titles(self) -> List[Dict]:
        """获取所有称号"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT title_id, name, description FROM titles")
            return [dict(row) for row in cursor.fetchall()]

    def get_all_achievements(self) -> List[Dict]:
        """获取所有成就"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM achievements")
            return [dict(row) for row in cursor.fetchall()]

    def get_user_titles(self, user_id: str) -> List[Dict]:
        """获取用户已获得的称号"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT t.title_id, t.name, t.description
                FROM user_titles ut
                JOIN titles t ON ut.title_id = t.title_id
                WHERE ut.user_id = ?
            """, (user_id,))
            return [dict(row) for row in cursor.fetchall()]

    def get_user_achievements(self, user_id: str) -> List[Dict]:
        """获取用户已获得的成就"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT a.achievement_id, a.name, a.description
                FROM user_achievements ua
                JOIN achievements a ON ua.achievement_id = a.achievement_id
                WHERE ua.user_id = ?
            """, (user_id,))
            return [dict(row) for row in cursor.fetchall()]

    # --- 鱼饵相关操作 ---
    def get_all_baits(self) -> List[Dict]:
        """获取所有鱼饵"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT bait_id, name, description, cost FROM baits")
            return [dict(row) for row in cursor.fetchall()]

    def get_user_baits(self, user_id: str) -> List[Dict]:
        """获取用户已有的鱼饵"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT b.bait_id, b.name, b.description, ubi.quantity
                FROM user_bait_inventory ubi
                JOIN baits b ON ubi.bait_id = b.bait_id
                WHERE ubi.user_id = ?
            """, (user_id,))
            return [dict(row) for row in cursor.fetchall()]

    def get_bait_info(self, bait_id: int) -> Dict:
        """获取鱼饵信息"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM baits WHERE bait_id = ?", (bait_id,))
            bait = cursor.fetchone()
            return dict(bait) if bait else None

    def get_user_coins(self, user_id: str) -> int:
        """【新】从修仙数据库获取灵石数量"""
        user_info = self.xiuxian_service.get_user_message(user_id)
        return user_info.stone if user_info else 0

    def add_bait_to_inventory(self, user_id: str, bait_id: int, quantity: int = 1) -> bool:
        """将鱼饵添加到用户库存"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO user_bait_inventory (user_id, bait_id, quantity)
                    VALUES (?, ?, ?)
                    ON CONFLICT(user_id, bait_id) DO UPDATE SET quantity = quantity + ?
                """, (user_id, bait_id, quantity, quantity))
                conn.commit()
                return True
        except sqlite3.Error as e:
            logger.error(f"添加鱼饵到库存失败: {e}")
            return False

    # --- 鱼竿相关操作 ---
    def get_all_rods(self) -> List[Dict]:
        """获取所有鱼竿"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM rods")
            return [dict(row) for row in cursor.fetchall()]

    def get_user_rods(self, user_id: str) -> List[Dict]:
        """获取用户已有的鱼竿"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT ur.rod_instance_id, r.rod_id, r.name, r.description, r.rarity, 
                       r.bonus_fish_quality_modifier, r.bonus_fish_quantity_modifier, 
                       r.bonus_rare_fish_chance, ur.current_durability, ur.is_equipped,
                       r.source, r.purchase_cost, r.durability, r.icon_url
                FROM user_rods ur
                JOIN rods r ON ur.rod_id = r.rod_id
                WHERE ur.user_id = ?
            """, (user_id,))
            return [dict(row) for row in cursor.fetchall()]

    def get_rod_info(self, rod_id: int) -> Dict:
        """获取鱼竿信息"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM rods WHERE rod_id = ?", (rod_id,))
            rod = cursor.fetchone()
            return dict(rod) if rod else None

    def add_rod_to_inventory(self, user_id: str, rod_id: int, durability: Optional[int] = None) -> bool:
        """将鱼竿添加到用户库存，并自动装备（如果用户没有装备其他鱼竿）"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # 添加鱼竿到库存
                cursor.execute("""
                    INSERT INTO user_rods (user_id, rod_id, current_durability)
                    VALUES (?, ?, ?)
                """, (user_id, rod_id, durability))
                
                # 获取新插入的鱼竿实例ID
                new_rod_instance_id = cursor.lastrowid
                
                # 检查用户是否已有装备的鱼竿
                cursor.execute("""
                    SELECT equipped_rod_instance_id 
                    FROM users 
                    WHERE user_id = ?
                """, (user_id,))
                result = cursor.fetchone()
                
                # 如果用户没有装备鱼竿，则装备新鱼竿
                if not result or not result[0]:
                    cursor.execute("""
                        UPDATE users
                        SET equipped_rod_instance_id = ?
                        WHERE user_id = ?
                    """, (new_rod_instance_id, user_id))
                    
                    # 同时更新鱼竿实例的装备状态
                    cursor.execute("""
                        UPDATE user_rods
                        SET is_equipped = 1
                        WHERE rod_instance_id = ?
                    """, (new_rod_instance_id,))
                
                conn.commit()
                return True
        except sqlite3.Error as e:
            logger.error(f"添加鱼竿到库存失败: {e}")
            return False

    # --- 饰品相关操作 ---
    def get_all_accessories(self) -> List[Dict]:
        """获取所有饰品"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT accessory_id, name, description FROM accessories")
            return [dict(row) for row in cursor.fetchall()]

    def get_user_accessories(self, user_id: str) -> List[Dict]:
        """获取用户已有的饰品"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT ua.accessory_instance_id, a.accessory_id, a.name, a.description, a.rarity,
                       a.bonus_fish_quality_modifier, a.bonus_fish_quantity_modifier,
                       a.bonus_rare_fish_chance, a.other_bonus_description, ua.is_equipped
                FROM user_accessories ua
                JOIN accessories a ON ua.accessory_id = a.accessory_id
                WHERE ua.user_id = ?
            """, (user_id,))
            return [dict(row) for row in cursor.fetchall()]

    def add_accessory_to_inventory(self, user_id: str, accessory_id: int) -> bool:
        """将饰品添加到用户库存"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO user_accessories (user_id, accessory_id)
                    VALUES (?, ?)
                """, (user_id, accessory_id))
                conn.commit()
                return True
        except sqlite3.Error as e:
            logger.error(f"添加饰品到库存失败: {e}")
            return False

    # --- 抽奖相关操作 ---
    def get_gacha_pool_info(self, pool_id: int) -> Dict:
        """获取抽奖池信息"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT cost_coins, cost_premium_currency 
                FROM gacha_pools 
                WHERE gacha_pool_id = ?
            """, (pool_id,))
            pool = cursor.fetchone()
            return dict(pool) if pool else None

    def get_user_currency(self, user_id: str) -> Dict:
        """获取用户的货币信息"""
        coins = self.get_user_coins(user_id)
        
        return {
            "success": True,
            "coins": coins,
            "premium_currency": 0
        }

    def get_gacha_pool_items(self, pool_id: int) -> List[Dict]:
        """获取抽奖池物品列表"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT item_type, item_id, quantity, weight
                FROM gacha_pool_items
                WHERE gacha_pool_id = ?
            """, (pool_id,))
            return [dict(row) for row in cursor.fetchall()]

    def update_user_currency(self, user_id: str, coins_delta: int, premium_delta: int) -> bool:
        """更新用户货币"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE users 
                    SET coins = coins + ?,
                        premium_currency = premium_currency + ?
                    WHERE user_id = ?
                """, (coins_delta, premium_delta, user_id))
                conn.commit()
                return True
        except sqlite3.Error as e:
            logger.error(f"更新用户货币失败: {e}")
            return False

    # --- 鱼饵使用相关操作 ---
    def set_user_current_bait(self, user_id: str, bait_id: int) -> bool:
        """设置用户当前使用的鱼饵，如果用户没有该鱼饵，返回False"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                # 首先检查用户是否有该鱼饵
                cursor.execute("""
                    SELECT quantity 
                    FROM user_bait_inventory
                    WHERE user_id = ? AND bait_id = ?
                """, (user_id, bait_id))
                
                result = cursor.fetchone()
                if not result or result[0] <= 0:
                    return False
                    
                # 设置用户当前鱼饵并消耗一个鱼饵
                # 使用Python的datetime.now()获取当前时间，东八区
                current_time = get_utc4_now().strftime('%Y-%m-%d %H:%M:%S')
                
                # 获取鱼饵持续时间（如果有）
                cursor.execute("SELECT duration_minutes FROM baits WHERE bait_id = ?", (bait_id,))
                bait_info = cursor.fetchone()
               
                # 如果是一次性鱼饵，消耗一个
                if bait_info or bait_info['duration_minutes'] > 0:
                    cursor.execute("""
                        UPDATE user_bait_inventory
                        SET quantity = quantity - 1
                        WHERE user_id = ? AND bait_id = ?
                    """, (user_id, bait_id))
                
                # 设置用户当前鱼饵
                cursor.execute("""
                    UPDATE users
                    SET current_bait_id = ?,
                        bait_start_time = ?
                    WHERE user_id = ?
                """, (bait_id, current_time, user_id))
                
                conn.commit()
                return True
        except sqlite3.Error as e:
            logger.error(f"设置用户当前鱼饵失败: {e}")
            return False
    
    def get_user_current_bait(self, user_id: str) -> Dict:
        """获取用户当前使用的鱼饵信息"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT b.*, u.bait_start_time
                FROM users u
                LEFT JOIN baits b ON u.current_bait_id = b.bait_id
                WHERE u.user_id = ? AND u.current_bait_id IS NOT NULL
            """, (user_id,))
            result = cursor.fetchone()
            if result:
                bait_info = dict(result)
                # 计算剩余时间（如果有持续时间的话）
                if bait_info.get('duration_minutes', 0) > 0 and bait_info.get('bait_start_time'):
                    start_time = datetime.strptime(bait_info['bait_start_time'], '%Y-%m-%d %H:%M:%S')
                    start_time = start_time.replace(tzinfo=UTC4)
                    elapsed_minutes = (get_utc4_now() - start_time).total_seconds() / 60
                    bait_info['remaining_minutes'] = max(0, bait_info['duration_minutes'] - elapsed_minutes)
                    # 如果已经过期，清除当前鱼饵
                    if bait_info['remaining_minutes'] <= 0:
                        self.clear_user_current_bait(user_id)
                        return None
                return bait_info
            return None
    
    def clear_user_current_bait(self, user_id: str) -> bool:
        """清除用户当前使用的鱼饵"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE users
                    SET current_bait_id = NULL,
                        bait_start_time = NULL
                    WHERE user_id = ?
                """, (user_id,))
                conn.commit()
                return True
        except sqlite3.Error as e:
            logger.error(f"清除用户当前使用鱼饵失败: {e}")
            return False

    # --- 自动钓鱼相关操作 ---
    def get_auto_fishing_users(self) -> List[str]:
        """获取所有开启自动钓鱼的用户ID列表"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT user_id 
                FROM users 
                WHERE auto_fishing_enabled = 1
            """)
            return [row[0] for row in cursor.fetchall()]
    
    def get_last_fishing_time(self, user_id: str) -> float:
        """获取用户上次钓鱼时间(时间戳)"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT last_fishing_time 
                FROM users 
                WHERE user_id = ?
            """, (user_id,))
            result = cursor.fetchone()
            if result and result[0]:
                try:
                    # 如果数据库中已经是datetime对象，直接获取时间戳
                    if isinstance(result[0], datetime):
                        return result[0].timestamp()
                    # 如果是字符串，则需要转换
                    elif isinstance(result[0], str):
                        dt = datetime.strptime(result[0], '%Y-%m-%d %H:%M:%S')
                        return dt.timestamp()
                    # 如果已经是时间戳，则直接返回
                    elif isinstance(result[0], (int, float)):
                        return float(result[0])
                    else:
                        return 0
                except (ValueError, TypeError):
                    return 0
            return 0
    
    def set_auto_fishing_status(self, user_id: str, status: bool) -> bool:
        """设置用户自动钓鱼状态"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE users 
                    SET auto_fishing_enabled = ? 
                    WHERE user_id = ?
                """, (1 if status else 0, user_id))
                conn.commit()
                return True
        except sqlite3.Error as e:
            logger.error(f"设置自动钓鱼状态失败: {e}")
            return False

    # --- 鱼塘（鱼类库存）相关操作 ---
    def get_user_fish_inventory(self, user_id: str) -> List[Dict]:
        """获取用户钓到的所有鱼的详细信息"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT f.fish_id, f.name, f.description, f.rarity, f.base_value, 
                       ufi.quantity
                FROM user_fish_inventory ufi
                JOIN fish f ON ufi.fish_id = f.fish_id
                WHERE ufi.user_id = ? AND ufi.quantity > 0
                ORDER BY f.rarity DESC, f.base_value DESC
            """, (user_id,))
            return [dict(row) for row in cursor.fetchall()]
            
    def get_user_fish_stats(self, user_id: str) -> Dict:
        """获取用户鱼塘统计信息（总数量、总价值、稀有度分布）"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # 获取总数量和总价值
            cursor.execute("""
                SELECT SUM(ufi.quantity) as total_count,
                       SUM(f.base_value * ufi.quantity) as total_value
                FROM user_fish_inventory ufi
                JOIN fish f ON ufi.fish_id = f.fish_id
                WHERE ufi.user_id = ?
            """, (user_id,))
            stats = dict(cursor.fetchone() or {})
            
            if not stats.get('total_count'):
                return {"total_count": 0, "total_value": 0, "rarity_distribution": {}}
            
            # 获取稀有度分布
            cursor.execute("""
                SELECT f.rarity, SUM(ufi.quantity) as count
                FROM user_fish_inventory ufi
                JOIN fish f ON ufi.fish_id = f.fish_id
                WHERE ufi.user_id = ?
                GROUP BY f.rarity
                ORDER BY f.rarity
            """, (user_id,))
            
            rarity_distribution = {}
            for row in cursor.fetchall():
                rarity_distribution[row['rarity']] = row['count']
                
            stats['rarity_distribution'] = rarity_distribution
            return stats

    # --- 签到相关操作 ---
    def check_daily_sign_in(self, user_id: str) -> bool:
        """检查用户今天是否已经签到"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            today = get_utc4_today().isoformat()
            cursor.execute("""
                SELECT 1 FROM check_ins
                WHERE user_id = ? AND check_in_date = ?
            """, (user_id, today))
            return cursor.fetchone() is not None

    def record_daily_sign_in(self, user_id: str, coins_reward: int) -> bool:
        """记录用户签到并发放奖励"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                today = get_utc4_today().isoformat()
                
                # 记录签到
                cursor.execute("""
                    INSERT INTO check_ins (user_id, check_in_date)
                    VALUES (?, ?)
                """, (user_id, today))
                
                # 增加用户金币
                cursor.execute("""
                    UPDATE users
                    SET coins = coins + ?,
                        consecutive_login_days = consecutive_login_days + 1
                    WHERE user_id = ?
                """, (coins_reward, user_id))
                
                conn.commit()
                return True
        except sqlite3.Error as e:
            logger.error(f"记录签到失败: {e}")
            return False

    def reset_login_streak(self, user_id: str) -> bool:
        """重置用户的连续登录天数（如果昨天没有登录）"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                yesterday = (get_utc4_today() - timedelta(days=1)).isoformat()
                
                # 检查昨天是否签到
                cursor.execute("""
                    SELECT 1 FROM check_ins
                    WHERE user_id = ? AND check_in_date = ?
                """, (user_id, yesterday))
                
                # 如果昨天没有签到，重置连续登录天数
                if not cursor.fetchone():
                    cursor.execute("""
                        UPDATE users
                        SET consecutive_login_days = 0
                        WHERE user_id = ?
                    """, (user_id,))
                    conn.commit()
                    return True
                return False
        except sqlite3.Error as e:
            logger.error(f"重置登录连续天数失败: {e}")
            return False

    def get_consecutive_login_days(self, user_id: str) -> int:
        """获取用户连续登录的天数"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT consecutive_login_days
                FROM users
                WHERE user_id = ?
            """, (user_id,))
            result = cursor.fetchone()
            return result[0] if result else 0

    def get_accessory_info(self, accessory_id: int) -> Dict:
        """获取饰品详细信息"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM accessories WHERE accessory_id = ?", (accessory_id,))
            accessory = cursor.fetchone()
            return dict(accessory) if accessory else None
            
    def equip_accessory(self, user_id: str, accessory_instance_id: int) -> bool:
        """装备指定的饰品"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # 先检查该饰品是否属于用户
                cursor.execute("""
                    SELECT accessory_id 
                    FROM user_accessories 
                    WHERE user_id = ? AND accessory_instance_id = ?
                """, (user_id, accessory_instance_id))
                result = cursor.fetchone()
                
                if not result:
                    return False
                
                # 取消所有饰品的装备状态
                cursor.execute("""
                    UPDATE user_accessories
                    SET is_equipped = 0
                    WHERE user_id = ?
                """, (user_id,))
                
                # 装备新饰品
                cursor.execute("""
                    UPDATE user_accessories
                    SET is_equipped = 1
                    WHERE accessory_instance_id = ?
                """, (accessory_instance_id,))
                
                # 更新用户表中的装备饰品ID
                cursor.execute("""
                    UPDATE users
                    SET equipped_accessory_instance_id = ?
                    WHERE user_id = ?
                """, (accessory_instance_id, user_id))
                
                conn.commit()
                return True
        except sqlite3.Error as e:
            logger.error(f"装备饰品失败: {e}")
            return False
            
    def unequip_accessory(self, user_id: str) -> bool:
        """取消装备当前饰品"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # 取消所有饰品的装备状态
                cursor.execute("""
                    UPDATE user_accessories
                    SET is_equipped = 0
                    WHERE user_id = ?
                """, (user_id,))
                
                # 更新用户表
                cursor.execute("""
                    UPDATE users
                    SET equipped_accessory_instance_id = NULL
                    WHERE user_id = ?
                """, (user_id,))
                
                conn.commit()
                return True
        except sqlite3.Error as e:
            logger.error(f"取消装备饰品失败: {e}")
            return False
            
    def get_user_equipped_accessory(self, user_id: str) -> Dict:
        """获取用户当前装备的饰品信息"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT a.*, ua.accessory_instance_id
                FROM users u
                JOIN user_accessories ua ON u.equipped_accessory_instance_id = ua.accessory_instance_id
                JOIN accessories a ON ua.accessory_id = a.accessory_id
                WHERE u.user_id = ?
            """, (user_id,))
            result = cursor.fetchone()
            return dict(result) if result else None

    def get_user_disposable_baits(self, user_id: str) -> List[Dict]:
        """获取用户拥有的一次性鱼饵（不含持续时间的鱼饵）"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT b.bait_id, b.name, b.description, b.effect_description, ubi.quantity
                FROM user_bait_inventory ubi
                JOIN baits b ON ubi.bait_id = b.bait_id
                WHERE ubi.user_id = ? AND ubi.quantity > 0 
                AND (b.duration_minutes = 0 OR b.duration_minutes IS NULL)
            """, (user_id,))
            return [dict(row) for row in cursor.fetchall()]
            
    def consume_bait(self, user_id: str, bait_id: int) -> bool:
        """消耗用户的一个鱼饵，但不设置为当前使用的鱼饵"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # 检查用户是否有该鱼饵
                cursor.execute("""
                    SELECT quantity FROM user_bait_inventory
                    WHERE user_id = ? AND bait_id = ?
                """, (user_id, bait_id))
                result = cursor.fetchone()
                
                if not result or result[0] <= 0:
                    return False
                
                # 减少鱼饵数量
                cursor.execute("""
                    UPDATE user_bait_inventory
                    SET quantity = quantity - 1
                    WHERE user_id = ? AND bait_id = ?
                """, (user_id, bait_id))
                
                conn.commit()
                return True
        except sqlite3.Error as e:
            logger.error(f"消耗鱼饵失败: {e}")
            return False

    def get_all_users(self) -> List[str]:
        """获取所有用户ID"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT user_id FROM users")
            return [row[0] for row in cursor.fetchall()]
            
    def get_user_achievement_progress(self, user_id: str) -> List[Dict]:
        """获取用户所有成就的进度"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT a.achievement_id, a.name, a.description, a.target_type, 
                       a.target_value, a.target_fish_id, a.reward_type, a.reward_value,
                       COALESCE(uap.current_progress, 0) as current_progress,
                       uap.completed_at, uap.claimed_at
                FROM achievements a
                LEFT JOIN user_achievement_progress uap 
                    ON a.achievement_id = uap.achievement_id AND uap.user_id = ?
            """, (user_id,))
            return [dict(row) for row in cursor.fetchall()]
            
    def get_user_fishing_stats(self, user_id: str) -> Dict:
        """获取用户钓鱼统计数据"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT total_fishing_count, total_weight_caught, total_coins_earned,
                       consecutive_login_days
                FROM users
                WHERE user_id = ?
            """, (user_id,))
            result = cursor.fetchone()
            return dict(result) if result else {}
            
    def get_user_distinct_fish_count(self, user_id: str) -> int:
        """获取用户钓到的不同种类鱼的数量"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(DISTINCT fish_id)
                FROM user_fish_inventory
                WHERE user_id = ? AND quantity > 0
            """, (user_id,))
            result = cursor.fetchone()
            return result[0] if result else 0
            
    def update_user_achievement_progress(self, user_id: str, achievement_id: int, progress: int, 
                                        completed: bool = False) -> bool:
        """更新用户成就进度"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                now = get_utc4_now().strftime('%Y-%m-%d %H:%M:%S')
                
                # 检查是否已有记录
                cursor.execute("""
                    SELECT current_progress, completed_at
                    FROM user_achievement_progress
                    WHERE user_id = ? AND achievement_id = ?
                """, (user_id, achievement_id))
                record = cursor.fetchone()
                
                if record:
                    # 已有记录，更新进度
                    completed_at = now if completed and not record['completed_at'] else record['completed_at']
                    cursor.execute("""
                        UPDATE user_achievement_progress
                        SET current_progress = ?,
                            completed_at = ?
                        WHERE user_id = ? AND achievement_id = ?
                    """, (progress, completed_at, user_id, achievement_id))
                else:
                    # 创建新记录
                    completed_at = now if completed else None
                    cursor.execute("""
                        INSERT INTO user_achievement_progress
                        (user_id, achievement_id, current_progress, completed_at)
                        VALUES (?, ?, ?, ?)
                    """, (user_id, achievement_id, progress, completed_at))
                
                conn.commit()
                return True
        except sqlite3.Error as e:
            logger.error(f"更新成就进度失败: {e}")
            return False
            
    def award_achievement_reward(self, user_id: str, achievement_id: int) -> Dict:
        """授予成就奖励"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # 获取成就信息和用户进度
                cursor.execute("""
                    SELECT a.reward_type, a.reward_value, a.reward_quantity,
                           uap.claimed_at
                    FROM achievements a
                    JOIN user_achievement_progress uap 
                        ON a.achievement_id = uap.achievement_id
                    WHERE uap.user_id = ? AND a.achievement_id = ?
                        AND uap.completed_at IS NOT NULL
                        AND uap.claimed_at IS NULL
                """, (user_id, achievement_id))
                reward_info = cursor.fetchone()
                
                if not reward_info:
                    return {"success": False, "message": "成就未完成或奖励已领取"}
                
                reward_type = reward_info['reward_type']
                reward_value = reward_info['reward_value']
                reward_quantity = reward_info['reward_quantity']
                
                # 根据奖励类型发放奖励
                if reward_type == 'coins':
                    # 增加金币
                    self.update_user_coins(user_id, reward_value * reward_quantity)
                    reward_desc = f"{reward_value * reward_quantity} 金币"
                    
                elif reward_type == 'title':
                    # 添加称号
                    cursor.execute("""
                        INSERT OR IGNORE INTO user_titles (user_id, title_id)
                        VALUES (?, ?)
                    """, (user_id, reward_value))
                    
                    # 获取称号名称
                    cursor.execute("SELECT name FROM titles WHERE title_id = ?", (reward_value,))
                    title = cursor.fetchone()
                    reward_desc = f"称号 【{title['name'] if title else reward_value}】"
                    
                elif reward_type == 'bait':
                    # 添加鱼饵
                    self.add_bait_to_inventory(user_id, reward_value, reward_quantity)
                    
                    # 获取鱼饵名称
                    cursor.execute("SELECT name FROM baits WHERE bait_id = ?", (reward_value,))
                    bait = cursor.fetchone()
                    reward_desc = f"{reward_quantity} 个 【{bait['name'] if bait else reward_value}】"
                    
                elif reward_type == 'rod':
                    # 添加鱼竿
                    for _ in range(reward_quantity):
                        self.add_rod_to_inventory(user_id, reward_value)
                    
                    # 获取鱼竿名称
                    cursor.execute("SELECT name FROM rods WHERE rod_id = ?", (reward_value,))
                    rod = cursor.fetchone()
                    reward_desc = f"鱼竿 【{rod['name'] if rod else reward_value}】"
                    
                elif reward_type == 'accessory':
                    # 添加饰品
                    for _ in range(reward_quantity):
                        self.add_accessory_to_inventory(user_id, reward_value)
                    
                    # 获取饰品名称
                    cursor.execute("SELECT name FROM accessories WHERE accessory_id = ?", (reward_value,))
                    accessory = cursor.fetchone()
                    reward_desc = f"饰品 【{accessory['name'] if accessory else reward_value}】"
                    
                elif reward_type == 'premium_currency':
                    # 增加高级货币
                    cursor.execute("""
                        UPDATE users
                        SET premium_currency = premium_currency + ?
                        WHERE user_id = ?
                    """, (reward_value * reward_quantity, user_id))
                    reward_desc = f"{reward_value * reward_quantity} 高级货币"
                    
                else:
                    reward_desc = "未知奖励"
                
                # 标记奖励已领取
                cursor.execute("""
                    UPDATE user_achievement_progress
                    SET claimed_at = CURRENT_TIMESTAMP
                    WHERE user_id = ? AND achievement_id = ?
                """, (user_id, achievement_id))
                
                conn.commit()
                return {
                    "success": True, 
                    "message": f"恭喜获得成就奖励: {reward_desc}"
                }
                
        except sqlite3.Error as e:
            logger.error(f"发放成就奖励失败: {e}")
            return {"success": False, "message": "发放奖励失败，请稍后再试"}
            
    def add_title_to_user(self, user_id: str, title_id: int) -> bool:
        """为用户添加称号"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR IGNORE INTO user_titles (user_id, title_id)
                    VALUES (?, ?)
                """, (user_id, title_id))
                conn.commit()
                return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"添加称号失败: {e}")
            return False

    def get_all_gacha_pools(self) -> List[Dict]:
        """获取所有奖池信息"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT gacha_pool_id, name, description, cost_coins, cost_premium_currency
                FROM gacha_pools
                ORDER BY gacha_pool_id
            """)
            return [dict(row) for row in cursor.fetchall()]
            
    def get_gacha_pool_details(self, pool_id: int) -> Dict:
        """获取奖池详细信息，包括物品列表和概率"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # 获取奖池基本信息
            cursor.execute("""
                SELECT gacha_pool_id, name, description, cost_coins, cost_premium_currency
                FROM gacha_pools
                WHERE gacha_pool_id = ?
            """, (pool_id,))
            pool_info = cursor.fetchone()
            
            if not pool_info:
                return None
                
            pool_details = dict(pool_info)
            
            # 获取奖池物品详情
            cursor.execute("""
                SELECT gpi.gacha_pool_item_id, gpi.item_type, gpi.item_id, 
                       gpi.quantity, gpi.weight,
                       CASE 
                           WHEN gpi.item_type = 'rod' THEN r.name
                           WHEN gpi.item_type = 'accessory' THEN a.name
                           WHEN gpi.item_type = 'bait' THEN b.name
                           WHEN gpi.item_type = 'fish' THEN f.name
                           WHEN gpi.item_type = 'coins' THEN '金币'
                           WHEN gpi.item_type = 'titles' THEN t.name
                           WHEN gpi.item_type = 'premium_currency' THEN '钻石'
                           ELSE '未知物品'
                       END as item_name,
                       CASE 
                           WHEN gpi.item_type = 'rod' THEN r.rarity
                           WHEN gpi.item_type = 'accessory' THEN a.rarity
                           WHEN gpi.item_type = 'bait' THEN b.rarity
                           WHEN gpi.item_type = 'fish' THEN f.rarity
                           WHEN gpi.item_type IN ('coins', 'premium_currency') THEN 1
                           ELSE 1
                       END as item_rarity,
                       CASE 
                           WHEN gpi.item_type = 'rod' THEN r.description
                           WHEN gpi.item_type = 'accessory' THEN a.description
                           WHEN gpi.item_type = 'bait' THEN b.description
                           WHEN gpi.item_type = 'fish' THEN f.description
                           WHEN gpi.item_type = 'titles' THEN t.description
                           WHEN gpi.item_type = 'coins' THEN '获得一定数量的金币'
                           WHEN gpi.item_type = 'premium_currency' THEN '获得一定数量的高级货币'
                           ELSE NULL
                       END as item_description,
                       CASE 
                           WHEN gpi.item_type = 'rod' THEN r.bonus_fish_quality_modifier
                           WHEN gpi.item_type = 'accessory' THEN a.bonus_fish_quality_modifier
                           ELSE NULL
                       END as quality_modifier,
                       CASE 
                           WHEN gpi.item_type = 'rod' THEN r.bonus_fish_quantity_modifier
                           WHEN gpi.item_type = 'accessory' THEN a.bonus_fish_quantity_modifier
                           ELSE NULL
                       END as quantity_modifier,
                       CASE 
                           WHEN gpi.item_type = 'rod' THEN r.bonus_rare_fish_chance
                           WHEN gpi.item_type = 'accessory' THEN a.bonus_rare_fish_chance
                           ELSE NULL
                       END as rare_chance,
                       CASE 
                           WHEN gpi.item_type = 'bait' THEN b.effect_description
                           WHEN gpi.item_type = 'accessory' THEN a.other_bonus_description
                           ELSE NULL
                       END as effect_description
                FROM gacha_pool_items gpi
                LEFT JOIN rods r ON gpi.item_type = 'rod' AND gpi.item_id = r.rod_id
                LEFT JOIN accessories a ON gpi.item_type = 'accessory' AND gpi.item_id = a.accessory_id
                LEFT JOIN baits b ON gpi.item_type = 'bait' AND gpi.item_id = b.bait_id
                LEFT JOIN fish f ON gpi.item_type = 'fish' AND gpi.item_id = f.fish_id
                LEFT JOIN titles t ON gpi.item_type = 'titles' AND gpi.item_id = t.title_id
                WHERE gpi.gacha_pool_id = ?
                ORDER BY item_rarity DESC, gpi.weight
            """, (pool_id,))
            
            pool_items = [dict(row) for row in cursor.fetchall()]
            
            # 计算总权重
            total_weight = sum(item['weight'] for item in pool_items)
            
            # 添加概率百分比，并将premium_currency显示为金币
            for item in pool_items:
                item['probability'] = (item['weight'] / total_weight) * 100
                # 如果是钻石类型，改为显示为金币
                if item['item_type'] == 'premium_currency':
                    item['item_type'] = 'coins'
                    item['item_name'] = f"{item['quantity']}金币"
                # 确保所有物品都有有效的名称
                if not item['item_name'] or item['item_name'] == 'None':
                    if item['item_type'] == 'coins':
                        item['item_name'] = f"{item['quantity']}金币"
                    else:
                        item['item_name'] = f"{item['item_type']}_{item['item_id']}"
                
            pool_details['items'] = pool_items
            pool_details['total_weight'] = total_weight
            
            return pool_details

    def adjust_gacha_pool_weights(self) -> bool:
        """调整奖池中稀有鱼竿和饰品的权重，使其更难抽出"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # 1. 清理原有奖池数据
                cursor.execute("DELETE FROM gacha_pool_items WHERE gacha_pool_id IN (1, 2)")
                
                # 2. 重新设置鱼竿池的物品（奖池1）
                rod_pool_items = [
                    # 稀有度5 - 传说
                    (1, 'rod', 5, 1, 3),     # 海神之赐 (3.3%)
                    
                    # 稀有度4 - 稀有
                    (1, 'rod', 4, 1, 11),    # 星辰钓者 (12.1%)
                    
                    # 稀有度3 - 高级
                    (1, 'rod', 3, 1, 22),    # 碳素纤维竿 (24.2%)
                    
                    # 稀有度2 - 优质
                    (1, 'bait', 4, 3, 18),   # 红虫×3 (19.8%)
                    
                    # 稀有度1 - 普通
                    (1, 'coins', 0, 1000, 37)  # 1000金币 (40.6%)
                ]
                
                for pool_id, item_type, item_id, quantity, weight in rod_pool_items:
                    cursor.execute("""
                        INSERT INTO gacha_pool_items
                        (gacha_pool_id, item_type, item_id, quantity, weight)
                        VALUES (?, ?, ?, ?, ?)
                    """, (pool_id, item_type, item_id, quantity, weight))
                
                # 3. 重新设置饰品池的物品（奖池2）- 调低稀有概率
                accessory_pool_items = [
                    # 稀有度5 - 传说
                    (2, 'accessory', 4, 1, 3),    # 海洋之心 (2.5%)
                    
                    # 稀有度4 - 稀有
                    (2, 'accessory', 3, 1, 8),    # 丰收号角 (6.7%)
                    
                    # 稀有度3 - 高级
                    (2, 'accessory', 2, 1, 15),   # 渔夫的戒指 (12.5%)
                    
                    # 稀有度2 - 优质
                    (2, 'bait', 5, 1, 4),         # 亮片拟饵 (3.3%)
                    
                    # 稀有度1 - 普通 - 提高金币额度
                    (2, 'coins', 0, 5000, 90)     # 5000金币 (75.0%)
                ]
                
                for pool_id, item_type, item_id, quantity, weight in accessory_pool_items:
                    cursor.execute("""
                        INSERT INTO gacha_pool_items
                        (gacha_pool_id, item_type, item_id, quantity, weight)
                        VALUES (?, ?, ?, ?, ?)
                    """, (pool_id, item_type, item_id, quantity, weight))
                
                # 4. 更新奖池的基本信息，确保不使用钻石
                cursor.execute("""
                    UPDATE gacha_pools 
                    SET cost_premium_currency = 0
                    WHERE gacha_pool_id IN (1, 2)
                """)
                
                conn.commit()
                # logger.info("奖池数据已重置，移除了钻石类物品并使用金币替代")
                return True
                
        except sqlite3.Error as e:
            logger.error(f"调整奖池权重失败: {e}")
            return False

    def get_user_equipped_accessories(self, user_id: str) -> Dict:
        """获取用户当前装备的饰品信息"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                # 只用user_accessories表和accessories表
                cursor.execute("""
                    SELECT a.*, ua.accessory_instance_id
                    FROM user_accessories ua
                    JOIN accessories a ON ua.accessory_id = a.accessory_id
                    WHERE ua.user_id = ? AND ua.is_equipped = 1
                """, (user_id,))
                result = cursor.fetchone()
                return dict(result) if result else None
        except sqlite3.Error as e:
            logger.error(f"获取用户装备饰品失败: {e}")
            return {}


    def get_leaderboard(self, limit: int = 10) -> List[Dict]:
        """获取用户排行榜数据

        Args:
            limit: 最多返回的用户数量

        Returns:
            包含用户昵称和相关统计信息的列表
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT 
                        user_id, 
                        nickname, 
                        coins, 
                        premium_currency,
                        total_fishing_count,
                        total_weight_caught,
                        total_coins_earned,
                        consecutive_login_days
                    FROM users
                    ORDER BY coins DESC
                    LIMIT ?
                """, (limit,))
                
                results = []
                for row in cursor.fetchall():
                    results.append(dict(row))
                    
                return results
        except sqlite3.Error as e:
            logger.error(f"Failed to get leaderboard: {e}")
            return []

    def get_leaderboard_with_details(self, limit: int = 10) -> List[Dict]:
        """获取用户排行榜数据，包含更详细的信息

        Args:
            limit: 最多返回的用户数量

        Returns:
            包含用户昵称、称号、金币数、鱼竿、饰品和钓鱼总数的排序列表
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT 
                        u.user_id,
                        u.nickname, 
                        u.coins,
                        u.total_fishing_count as fish_count,
                        t.name as title,
                        r.name as fishing_rod,
                        a.name as accessory
                    FROM users u
                    LEFT JOIN titles t ON u.current_title_id = t.title_id
                    LEFT JOIN user_rods ur ON u.equipped_rod_instance_id = ur.rod_instance_id
                    LEFT JOIN rods r ON ur.rod_id = r.rod_id
                    LEFT JOIN user_accessories ua ON ua.user_id = u.user_id AND ua.is_equipped = 1
                    LEFT JOIN accessories a ON ua.accessory_id = a.accessory_id
                    ORDER BY u.coins DESC
                    LIMIT ?
                """, (limit,))

                results = []
                for row in cursor.fetchall():
                    user_data = dict(row)
                    # 确保即使某些字段为空也有默认值
                    user_data['title'] = user_data.get('title', '无称号')
                    user_data['fishing_rod'] = user_data.get('fishing_rod', '无鱼竿')
                    user_data['accessory'] = user_data.get('accessory', '无饰品')
                    if user_data['title'] is None:
                        user_data['title'] = '无称号'
                    if user_data['fishing_rod'] is None:
                        user_data['fishing_rod'] = '无鱼竿'
                    if user_data['accessory'] is None:
                        user_data['accessory'] = '无饰品'
                    results.append(user_data)

                return results
        except sqlite3.Error as e:
            logger.error(f"获取排行榜详细数据失败: {e}")
            return []

    def equip_rod(self, user_id: str, rod_instance_id: int) -> bool:
        """装备指定的鱼竿"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # 先检查该鱼竿是否属于用户
                cursor.execute("""
                    SELECT rod_id 
                    FROM user_rods 
                    WHERE user_id = ? AND rod_instance_id = ?
                """, (user_id, rod_instance_id))
                result = cursor.fetchone()
                
                if not result:
                    return False
                
                # 取消所有鱼竿的装备状态
                cursor.execute("""
                    UPDATE user_rods
                    SET is_equipped = 0
                    WHERE user_id = ?
                """, (user_id,))
                
                # 装备新鱼竿
                cursor.execute("""
                    UPDATE user_rods
                    SET is_equipped = 1
                    WHERE rod_instance_id = ?
                """, (rod_instance_id,))
                
                # 更新用户表中的装备鱼竿ID
                cursor.execute("""
                    UPDATE users
                    SET equipped_rod_instance_id = ?
                    WHERE user_id = ?
                """, (rod_instance_id, user_id))
                
                conn.commit()
                return True
        except sqlite3.Error as e:
            logger.error(f"装备鱼竿失败: {e}")
            return False

    def add_fishing_record(self, user_id: str, fish_id: int, weight: int, value: int, 
                          rod_instance_id: Optional[int] = None, 
                          accessory_instance_id: Optional[int] = None,
                          bait_id: Optional[int] = None,
                          location_id: Optional[int] = None,
                          is_king_size: bool = False) -> bool:
        """添加钓鱼记录
        
        Args:
            user_id: 用户ID
            fish_id: 鱼的ID
            weight: 鱼的重量
            value: 鱼的价值
            rod_instance_id: 使用的鱼竿实例ID
            accessory_instance_id: 使用的饰品实例ID
            bait_id: 使用的鱼饵ID
            location_id: 钓鱼地点ID
            is_king_size: 是否为王者大小
            
        Returns:
            是否成功添加记录
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # 获取用户当前装备
                if rod_instance_id is None:
                    cursor.execute("""
                        SELECT equipped_rod_instance_id
                        FROM users
                        WHERE user_id = ?
                    """, (user_id,))
                    result = cursor.fetchone()
                    rod_instance_id = result['equipped_rod_instance_id'] if result else None
                
                if accessory_instance_id is None:
                    cursor.execute("""
                        SELECT accessory_instance_id
                        FROM user_accessories
                        WHERE user_id = ? AND is_equipped = 1
                    """, (user_id,))
                    result = cursor.fetchone()
                    accessory_instance_id = result['accessory_instance_id'] if result else None
                
                # 添加钓鱼记录
                cursor.execute("""
                    INSERT INTO fishing_records (
                        user_id, fish_id, weight, value, rod_instance_id,
                        accessory_instance_id, bait_id, timestamp, location_id, is_king_size
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?)
                """, (
                    user_id, fish_id, weight, value, rod_instance_id,
                    accessory_instance_id, bait_id, location_id, 1 if is_king_size else 0
                ))
                
                conn.commit()
                return True
        except sqlite3.Error as e:
            logger.error(f"添加钓鱼记录失败: {e}")
            return False
            
    def get_user_fishing_records(self, user_id: str, limit: int = 10) -> List[Dict]:
        """获取用户的钓鱼记录
        
        Args:
            user_id: 用户ID
            limit: 最多返回的记录数
            
        Returns:
            钓鱼记录列表
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT 
                        fr.record_id, fr.fish_id, f.name as fish_name, f.rarity,
                        fr.weight, fr.value, fr.timestamp, fr.is_king_size,
                        r.name as rod_name, b.name as bait_name, a.name as accessory_name
                    FROM fishing_records fr
                    JOIN fish f ON fr.fish_id = f.fish_id
                    LEFT JOIN user_rods ur ON fr.rod_instance_id = ur.rod_instance_id
                    LEFT JOIN rods r ON ur.rod_id = r.rod_id
                    LEFT JOIN baits b ON fr.bait_id = b.bait_id
                    LEFT JOIN user_accessories ua ON fr.accessory_instance_id = ua.accessory_instance_id
                    LEFT JOIN accessories a ON ua.accessory_id = a.accessory_id
                    WHERE fr.user_id = ?
                    ORDER BY fr.timestamp DESC
                    LIMIT ?
                """, (user_id, limit))
                
                return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"获取钓鱼记录失败: {e}")
            return []

    def get_user_deep_sea_fish_count(self, user_id: str) -> int:
        """获取用户钓到的深海鱼种类数量"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(DISTINCT f.fish_id)
                FROM user_fish_inventory ufi
                JOIN fish f ON ufi.fish_id = f.fish_id
                WHERE ufi.user_id = ? AND f.is_deep_sea = 1
            """, (user_id,))
            return cursor.fetchone()[0] or 0

    def get_user_garbage_count(self, user_id: str) -> int:
        """获取用户钓到的垃圾物品数量"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*)
                FROM user_fish_inventory ufi
                JOIN fish f ON ufi.fish_id = f.fish_id
                WHERE ufi.user_id = ? AND f.rarity = 1 AND f.base_value <= 2
            """, (user_id,))
            return cursor.fetchone()[0] or 0

    def get_user_unique_fish_count(self, user_id: str) -> int:
        """获取用户钓到的不同种类鱼的数量"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(DISTINCT fish_id)
                FROM user_fish_inventory
                WHERE user_id = ?
            """, (user_id,))
            return cursor.fetchone()[0] or 0

    def get_user_specific_fish_count(self, user_id: str, fish_id: int) -> int:
        """获取用户钓到的特定鱼的数量"""
        fish_id_mapping = {
            7:89,
            34:93,
            93:78,
            95:80,
            45:52,
            54:77
        }
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*)
                FROM user_fish_inventory
                WHERE user_id = ? AND fish_id = ?
            """, (user_id, fish_id_mapping.get(fish_id, fish_id)))
            return cursor.fetchone()[0] or 0

    def has_caught_heavy_fish(self, user_id: str, min_weight: int) -> bool:
        """检查用户是否钓到过重量超过指定值的鱼"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 1
                FROM fishing_records
                WHERE user_id = ? AND weight >= ?
                LIMIT 1
            """, (user_id, min_weight))
            return cursor.fetchone() is not None

    def has_performed_wipe_bomb(self, user_id: str) -> bool:
        """检查用户是否进行过擦弹"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 1
                FROM wipe_bomb_log
                WHERE user_id = ?
                LIMIT 1
            """, (user_id,))
            return cursor.fetchone() is not None

    def has_wipe_bomb_multiplier(self, user_id: str, multiplier: float) -> bool:
        """检查用户是否在擦弹中获得过指定倍数的奖励"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 1
                FROM wipe_bomb_log
                WHERE user_id = ? AND reward_multiplier >= ?
                LIMIT 1
            """, (user_id, multiplier))
            return cursor.fetchone() is not None

    def has_wipe_bomb_profit(self, user_id: str, min_profit: int) -> bool:
        """检查用户是否在擦弹中获得过指定金额的盈利"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 1
                FROM wipe_bomb_log
                WHERE user_id = ? AND (reward_amount - contribution_amount) >= ?
                LIMIT 1
            """, (user_id, min_profit))
            return cursor.fetchone() is not None

    def has_rod_of_rarity(self, user_id: str, rarity: int) -> bool:
        """检查用户是否拥有指定稀有度的鱼竿"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 1
                FROM user_rods ur
                JOIN rods r ON ur.rod_id = r.rod_id
                WHERE ur.user_id = ? AND r.rarity = ?
                LIMIT 1
            """, (user_id, rarity))
            return cursor.fetchone() is not None

    def has_accessory_of_rarity(self, user_id: str, rarity: int) -> bool:
        """检查用户是否拥有指定稀有度的饰品"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 1
                FROM user_accessories ua
                JOIN accessories a ON ua.accessory_id = a.accessory_id
                WHERE ua.user_id = ? AND a.rarity = ?
                LIMIT 1
            """, (user_id, rarity))
            return cursor.fetchone() is not None

    def get_user_uncompleted_achievements(self, user_id: str) -> List[Dict]:
        """获取用户未完成的成就列表"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT a.*
                FROM achievements a
                LEFT JOIN user_achievements ua ON a.achievement_id = ua.achievement_id AND ua.user_id = ?
                WHERE ua.achievement_id IS NULL
                ORDER BY a.achievement_id
            """, (user_id,))
            return [dict(row) for row in cursor.fetchall()]

    def record_achievement_completion(self, user_id: str, achievement_id: int) -> bool:
        """记录用户完成成就"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO user_achievements (user_id, achievement_id, completed_at)
                    VALUES (?, ?, datetime('now'))
                """, (user_id, achievement_id))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"记录成就完成失败: {e}")
            return False

    def grant_title_to_user(self, user_id: str, title_id: int) -> bool:
        """授予用户称号"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR IGNORE INTO user_titles (user_id, title_id, unlocked_at)
                    VALUES (?, ?, datetime('now'))
                """, (user_id, title_id))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"授予称号失败: {e}")
            return False

    def get_all_users(self) -> List[str]:
        """获取所有注册用户的ID列表"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT user_id FROM users")
            return [row[0] for row in cursor.fetchall()]

    def record_gacha_result(self, user_id: str, gacha_pool_id: int, item_type: str, 
                          item_id: int, item_name: str, quantity: int = 1, 
                          rarity: int = 1) -> bool:
        """
        记录用户的抽卡结果
        
        Args:
            user_id: 用户ID
            gacha_pool_id: 抽卡池ID
            item_type: 物品类型
            item_id: 物品ID
            item_name: 物品名称
            quantity: 物品数量
            rarity: 物品稀有度
            
        Returns:
            bool: 是否成功记录
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO gacha_records (
                        user_id, gacha_pool_id, item_type, item_id, 
                        item_name, quantity, rarity
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (user_id, gacha_pool_id, item_type, item_id, 
                     item_name, quantity, rarity))
                conn.commit()
                return True
        except sqlite3.Error as e:
            logger.error(f"记录抽卡结果失败: {e}")
            return False

    def get_user_gacha_records(self, user_id: str, limit: int = 10) -> List[Dict]:
        """
        获取用户的抽卡记录
        
        Args:
            user_id: 用户ID
            limit: 返回记录数量限制
            
        Returns:
            List[Dict]: 抽卡记录列表
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT * FROM gacha_records 
                    WHERE user_id = ? 
                    ORDER BY timestamp DESC 
                    LIMIT ?
                """, (user_id, limit))
                return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"获取抽卡记录失败: {e}")
            return []
    def get_title_info(self, title_id: int) -> Dict:
        """获取称号信息"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM titles WHERE title_id = ?", (title_id,))
            title = cursor.fetchone()
            return dict(title) if title else None
            
    def get_old_database_data(self, OLD_DATABASE):
        old_conn = sqlite3.connect(OLD_DATABASE)
        old_conn.row_factory = sqlite3.Row
        old_corsor = old_conn.cursor()
        try:
            # 获取所有用户的ID
            old_corsor.execute("SELECT * FROM user_fishing;")
            user_data = old_corsor.fetchall()
            return [dict(row) for row in user_data]
        except sqlite3.Error as e:
            logger.error(f"获取旧数据库数据失败: {e}")
            return []
        finally:
            old_conn.close()

    def insert_users(self, users):
        """批量插入用户数据"""
        conn = self._get_connection()
        cursor = conn.cursor()
        success_count = 0
        fail_count = 0

        try:
            for user in users:
                try:
                    # 检查用户是否已存在
                    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user.user_id,))
                    existing_user = cursor.fetchone()

                    if existing_user:
                        # 如果用户已存在，更新金币数量
                        cursor.execute(
                            "UPDATE users SET coins = coins + ? WHERE user_id = ?",
                            (user.coins, user.user_id)
                        )
                        logger.info(f"更新用户 {user.user_id} 的金币: +{user.coins}")
                    else:
                        # 如果用户不存在，则插入新用户
                        # 只使用必要的字段：user_id, nickname, coins
                        cursor.execute(
                            "INSERT INTO users (user_id, nickname, coins) VALUES (?, ?, ?)",
                            (user.user_id, user.nickname, user.coins)
                        )
                        logger.info(f"插入新用户 {user.user_id}, 昵称: {user.nickname}, 金币: {user.coins}")

                    success_count += 1
                except Exception as e:
                    logger.error(f"插入单个用户 {user.user_id} 失败: {e}")
                    fail_count += 1

            conn.commit()
            return {
                "success": True,
                "message": f"成功导入 {success_count} 名用户，失败 {fail_count} 名用户"
            }
        except Exception as e:
            conn.rollback()
            logger.error(f"批量插入用户数据失败: {e}")
            return {
                "success": False,
                "message": f"导入数据失败: {str(e)}"
            }

    def use_title(self, user_id, title_id):
        """使用指定的称号

        Args:
            user_id: 用户ID
            title_id: 称号ID

        Returns:
            bool: 是否成功使用称号
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # 检查用户是否拥有该称号
                cursor.execute("""
                    SELECT 1 FROM user_titles 
                    WHERE user_id = ? AND title_id = ?
                """, (user_id, title_id))
                if not cursor.fetchone():
                    return False

                # 更新用户的当前称号
                cursor.execute("""
                    UPDATE users 
                    SET current_title_id = ? 
                    WHERE user_id = ?
                """, (title_id, user_id))

                conn.commit()
                return True
        except sqlite3.Error as e:
            logger.error(f"使用称号失败: {e}")
            return False

    def get_user_current_title(self, user_id):
        """获取用户当前使用的称号"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT t.title_id, t.name, t.description
                    FROM users u
                    JOIN titles t ON u.current_title_id = t.title_id
                    WHERE u.user_id = ? 
                """, (user_id,))
                result = cursor.fetchone()
                return dict(result) if result else None
        except sqlite3.Error as e:
            logger.error(f"获取用户当前称号失败: {e}")
            return None

    def get_full_inventory_with_values(self, user_id: str) -> List[Dict]:
        """获取完整库存数据（包含基础价值）"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    f.fish_id,
                    f.name,
                    f.rarity,
                    f.base_value,
                    ufi.quantity as quantity
                FROM user_fish_inventory ufi
                JOIN fish f ON ufi.fish_id = f.fish_id
                WHERE ufi.user_id = ?
                GROUP BY f.fish_id
                HAVING COUNT(*) > 0
                ORDER BY f.rarity DESC, f.base_value DESC
            """, (user_id,))
            return [dict(row) for row in cursor.fetchall()]

    def get_user_fish_total_value(self, user_id: str) -> float:
        """精确计算当前总价值"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT SUM(f.base_value) as total
                FROM user_fish_inventory ufi
                JOIN fish f ON ufi.fish_id = f.fish_id
                WHERE ufi.user_id = ?
            """, (user_id,))
            row = cursor.fetchone()
            return float(row['total']) if row and row['total'] else 0.0

    def sell_rod(self, user_id, rod_instance_id):
        """出售指定的鱼竿

        Args:
            user_id: 用户ID
            rod_instance_id: 鱼竿实例ID

        Returns:
            bool: 是否成功出售
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # 检查鱼竿是否属于用户
                cursor.execute("""
                    SELECT rod_id, is_equipped 
                    FROM user_rods 
                    WHERE user_id = ? AND rod_instance_id = ?
                """, (user_id, rod_instance_id))
                result = cursor.fetchone()

                if not result:
                    return {
                        'success': False,
                        'message': "鱼竿不存在或不属于用户"
                    }  # 鱼竿不存在或不属于用户

                rod_id, is_equipped = result

                # 如果鱼竿正在装备中，先取消装备
                if is_equipped:
                    cursor.execute("""
                        UPDATE user_rods 
                        SET is_equipped = 0 
                        WHERE user_id = ? AND rod_instance_id = ?
                    """, (user_id, rod_instance_id))
                    # 同时更新用户表中的装备鱼竿ID
                    cursor.execute("""
                        UPDATE users 
                        SET equipped_rod_instance_id = NULL 
                        WHERE user_id = ?
                    """, (user_id,))
                # 删除鱼竿记录
                cursor.execute("""
                    DELETE FROM user_rods 
                    WHERE user_id = ? AND rod_instance_id = ?
                """, (user_id, rod_instance_id))
                # 获取鱼竿的基础价值
                cursor.execute("""
                    SELECT rarity 
                    FROM rods 
                    WHERE rod_id = ?
                """, (rod_id,))
                row = cursor.fetchone()
                if not row:
                    return {
                        'success': False,
                        'message': "鱼竿信息不存在"
                    }
                rarity = row['rarity']
                # 根据稀有度计算出售价格
                if rarity == 5:
                    sell_price = 5000
                elif rarity == 4:
                    sell_price = 3000
                elif rarity == 3:
                    sell_price = 500
                elif rarity == 2:
                    sell_price = 80
                else:
                    sell_price = 30
                # 更新用户金币
                cursor.execute("""
                    UPDATE users 
                    SET coins = coins + ? 
                    WHERE user_id = ?
                """, (sell_price, user_id))
                logger.info(f"用户 {user_id} 出售鱼竿 {rod_instance_id} 成功，获得金币: {sell_price}")
                conn.commit()
                return {
                    'success': True,
                    'message': f"出售鱼竿成功，获得金币: {sell_price}"
                }
        except sqlite3.Error as e:
            logger.error(f"出售鱼竿失败: {e}")
            return {
                'success': False,
                'message': f"出售鱼竿失败: {str(e)}"
            }

    def sell_accessory(self, user_id, accessory_instance_id):
        """出售指定的饰品

        Args:
            user_id: 用户ID
            accessory_instance_id: 饰品实例ID

        Returns:
            bool: 是否成功出售
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # 检查饰品是否属于用户
                cursor.execute("""
                    SELECT accessory_id, is_equipped 
                    FROM user_accessories 
                    WHERE user_id = ? AND accessory_instance_id = ?
                """, (user_id, accessory_instance_id))
                result = cursor.fetchone()

                if not result:
                    return {
                        'success': False,
                        'message': "饰品不存在或不属于用户"
                    }  # 饰品不存在或不属于用户

                accessory_id, is_equipped = result

                # 如果饰品正在装备中，先取消装备
                if is_equipped:
                    cursor.execute("""
                        UPDATE user_accessories 
                        SET is_equipped = 0 
                        WHERE user_id = ? AND accessory_instance_id = ?
                    """, (user_id, accessory_instance_id))

                # 删除饰品记录
                cursor.execute("""
                    DELETE FROM user_accessories 
                    WHERE user_id = ? AND accessory_instance_id = ?
                """, (user_id, accessory_instance_id))

                # 获取饰品的基础价值
                cursor.execute("""
                    SELECT rarity 
                    FROM accessories 
                    WHERE accessory_id = ?
                """, (accessory_id,))
                row = cursor.fetchone()
                if not row:
                    return {
                        'success': False,
                        'message': "饰品信息不存在"
                    }

                rarity = row['rarity']

                # 根据稀有度计算出售价格
                if rarity == 5:
                    sell_price = 50000
                elif rarity == 4:
                    sell_price = 15000
                elif rarity == 3:
                    sell_price = 3000
                elif rarity == 2:
                    sell_price = 500

                # 更新用户金币
                cursor.execute("""
                    UPDATE users 
                    SET coins = coins + ? 
                    WHERE user_id = ?
                """, (sell_price, user_id))

                logger.info(f"用户 {user_id} 出售饰品 {accessory_instance_id} 成功，获得金币: {sell_price}")

                conn.commit()
                return {
                    'success': True,
                    'message': f"出售饰品成功，获得金币: {sell_price}"
                }
        except sqlite3.Error as e:
            logger.error(f"出售饰品失败: {e}")
            return {
                'success': False,
                'message': f"出售饰品失败: {str(e)}"
            }

    def put_rod_on_sale(self, user_id, rod_instance_id, price):
        """将鱼竿上架出售

        Args:
            user_id: 用户ID
            rod_instance_id: 鱼竿实例ID
            price: 出售价格

        Returns:
            bool: 是否成功上架
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # 检查鱼竿是否属于用户
                cursor.execute("""
                    SELECT rod_id 
                    FROM user_rods 
                    WHERE user_id = ? AND rod_instance_id = ?
                """, (user_id, rod_instance_id))
                result = cursor.fetchone()

                if not result:
                    return {
                        'success': False,
                        'message': "鱼竿不存在或不属于用户"
                    }  # 鱼竿不存在或不属于用户

                rod_id = result['rod_id']

                # 插入market表中
                #market_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        # user_id TEXT NOT NULL,
                        # item_type TEXT NOT NULL CHECK (item_type IN ('fish', 'bait', 'rod', 'accessory')),
                        # item_id INTEGER NOT NULL,
                        # quantity INTEGER NOT NULL CHECK (quantity > 0),
                        # price INTEGER NOT NULL CHECK (price > 0),
                        # listed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        # expires_at DATETIME DEFAULT NULL,
                cursor.execute("""
                    INSERT INTO market (user_id, item_type, item_id, quantity, price)
                    VALUES (?, 'rod', ?, 1, ?)
                """, (user_id, rod_id, price))

                # 上架后删除鱼竿并且扣除出售鱼竿金币20%的税
                cursor.execute("""
                    DELETE FROM user_rods 
                    WHERE user_id = ? AND rod_instance_id = ?
                """, (user_id, rod_instance_id))
                cursor.execute("""
                    UPDATE users 
                    SET coins = coins - ? 
                    WHERE user_id = ?
                """, (int(price * 0.2), user_id))

                conn.commit()
                return {
                    'success': True,
                    'message': f"鱼竿 {rod_instance_id} 已上架出售，价格: {price}金币"
                }
        except sqlite3.Error as e:
            logger.error(f"上架鱼竿失败: {e}")
            return {
                'success': False,
                'message': f"上架鱼竿失败: {str(e)}"
            }

    def put_accessory_on_sale(self, user_id, accessory_instance_id, price):
        """将饰品上架出售

        Args:
            user_id: 用户ID
            accessory_instance_id: 饰品实例ID
            price: 出售价格

        Returns:
            bool: 是否成功上架
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # 检查饰品是否属于用户
                cursor.execute("""
                    SELECT accessory_id 
                    FROM user_accessories 
                    WHERE user_id = ? AND accessory_instance_id = ?
                """, (user_id, accessory_instance_id))
                result = cursor.fetchone()

                if not result:
                    return {
                        'success': False,
                        'message': "饰品不存在或不属于用户"
                    }  # 饰品不存在或不属于用户

                accessory_id = result['accessory_id']

                # 插入market表中
                cursor.execute("""
                    INSERT INTO market (user_id, item_type, item_id, quantity, price)
                    VALUES (?, 'accessory', ?, 1, ?)
                """, (user_id, accessory_id, price))

                # 上架后删除饰品并且扣除出售饰品金币20%的税
                cursor.execute("""
                    DELETE FROM user_accessories 
                    WHERE user_id = ? AND accessory_instance_id = ?
                """, (user_id, accessory_instance_id))
                cursor.execute("""
                    UPDATE users 
                    SET coins = coins - ? 
                    WHERE user_id = ?
                """, (int(price * 0.2), user_id))

                conn.commit()
                return {
                    'success': True,
                    'message': f"饰品 {accessory_instance_id} 已上架出售，价格: {price}金币"
                }
        except sqlite3.Error as e:
            logger.error(f"上架饰品失败: {e}")
            return {
                'success': False,
                'message': f"上架饰品失败: {str(e)}"
            }

    def get_market_rods(self):
        """获取市场上架的鱼竿列表

        Returns:
            List[Dict]: 市场上架的鱼竿信息列表
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                # 返回市场上架的鱼竿信息，包括市场ID、用户昵称、鱼竿ID、鱼竿名称、数量、价格和上架时间
                cursor.execute("""
                    SELECT 
                        m.market_id, m.user_id, u.nickname, m.item_id, r.name AS rod_name, 
                        m.quantity, m.price, m.listed_at
                    FROM market m
                    JOIN users u ON m.user_id = u.user_id
                    JOIN rods r ON m.item_id = r.rod_id
                    WHERE m.item_type = 'rod'
                """)
                return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"获取市场鱼竿失败: {e}")
            return []

    def get_market_accessories(self):
        """获取市场上架的饰品列表

        Returns:
            List[Dict]: 市场上架的饰品信息列表
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                # 返回市场上架的饰品信息，包括市场ID、用户昵称、饰品ID、饰品名称、数量、价格和上架时间
                cursor.execute("""
                    SELECT 
                        m.market_id, m.user_id, u.nickname, m.item_id, a.name AS accessory_name, 
                        m.quantity, m.price, m.listed_at
                    FROM market m
                    JOIN users u ON m.user_id = u.user_id
                    JOIN accessories a ON m.item_id = a.accessory_id
                    WHERE m.item_type = 'accessory'
                """)
                return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"获取市场饰品失败: {e}")
            return []

    def buy_item(self, buyer_id: str, market_id: int) -> dict:
        """
        【新版】处理市场购买的核心数据库事务。
        注意：此方法不处理货币操作，货币操作由上层Service负责。
        :return: 包含商品信息的字典，或包含错误信息的字典。
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # 1. 获取商品信息，并锁定该行防止并发问题
                # (SQLite的默认隔离级别可以简单处理并发，这里不做复杂锁定)
                cursor.execute(
                    "SELECT * FROM market WHERE market_id = ?",
                    (market_id,)
                )
                item_on_market = cursor.fetchone()

                if not item_on_market:
                    return {'success': False, 'message': "来晚一步，这件商品已经被别人买走或下架了。"}

                item_info = dict(item_on_market)

                # 2. 检查买家是否是卖家
                if item_info['user_id'] == buyer_id:
                    return {'success': False, 'message': "道友为何要购买自己上架的物品？"}

                # --- 开始事务 ---
                conn.execute("BEGIN")

                try:
                    # 3. 从市场删除该商品
                    cursor.execute("DELETE FROM market WHERE market_id = ?", (market_id,))
                    if cursor.rowcount == 0:
                        # 在我们检查后，商品被删除了，说明有并发操作
                        conn.rollback()
                        return {'success': False, 'message': "手慢了，这件商品刚刚被别人买走了！"}

                    # 4. 将物品添加到买家库存
                    item_type = item_info['item_type']
                    item_id = item_info['item_id']

                    if item_type == 'rod':
                        # 鱼竿是独立的，需要插入新行
                        self.add_rod_to_inventory(buyer_id, item_id)
                    elif item_type == 'accessory':
                        self.add_accessory_to_inventory(buyer_id, item_id)
                    else: # 其他可堆叠物品
                        # 这里可以添加对鱼饵、鱼等的支持
                        # self.add_item_to_inventory(buyer_id, item_id, item_type, 1)
                        pass

                    conn.commit()
                    # --- 事务成功 ---

                    # 5. 返回成功信息和需要处理的交易数据给上层服务
                    return {
                        'success': True,
                        'message': "物品交割成功！",
                        'trade_details': {
                            'buyer_id': buyer_id,
                            'seller_id': item_info['user_id'],
                            'price': item_info['price'],
                        }
                    }

                except Exception as e:
                    # 如果事务中任何一步出错，回滚所有操作
                    conn.rollback()
                    logger.error(f"购买物品事务失败: {e}")
                    return {'success': False, 'message': "交易过程中发生未知错误，交易已取消。"}

        except sqlite3.Error as e:
            logger.error(f"购买物品时数据库连接失败: {e}")
            return {'success': False, 'message': f"购买物品失败: {str(e)}"}


    def apply_daily_tax_to_high_value_users(self):
        """对高价值用户应用每日税收
           对于不同资产值的用户，应用不同的税率
        Returns:
            dict: 应用结果，包括成功与否和消息
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # 获取所有高价值用户
                cursor.execute("""
                    SELECT user_id, coins 
                    FROM users 
                    WHERE coins >= ?
                """, (10000,))
                high_value_users = cursor.fetchall()

                if not high_value_users:
                    return {
                        'success': True,
                        'message': "没有高价值用户需要缴税"
                    }

                for user in high_value_users:
                    user_id, coins = user
                    if coins <= 100000:
                        param = 0.05
                    elif coins <= 1000000:
                        param = 0.1
                    elif coins <= 10000000:
                        param = 0.2
                    else:
                        param = 0.35
                    tax_amount = int(coins * param)
                    # 扣除税收
                    cursor.execute("""
                        UPDATE users 
                        SET coins = coins - ? 
                        WHERE user_id = ?
                    """, (tax_amount, user_id))
                    # 记录税收日志
                    # CREATE TABLE IF NOT EXISTS taxes (
                    #     tax_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    #     user_id TEXT NOT NULL,
                    #     tax_amount INTEGER NOT NULL,
                    #     tax_rate REAL NOT NULL,
                    #     original_amount INTEGER NOT NULL,
                    #     timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    #     tax_type TEXT NOT NULL DEFAULT 'daily',
                    #     balance_after INTEGER NOT NULL,
                    #     FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                    # )
                    cursor.execute("""
                        INSERT INTO taxes (user_id, tax_amount, tax_rate, original_amount, balance_after)
                        VALUES (?, ?, ?, ?, ?)
                    """, (user_id, tax_amount, param, coins, coins - tax_amount))
                conn.commit()
                return {
                    'success': True,
                    'message': f"已对 {len(high_value_users)} 名高价值用户应用每日税收"
                }
        except sqlite3.Error as e:
            logger.error(f"应用每日税收失败: {e}")
            return {
                'success': False,
                'message': f"应用每日税收失败: {str(e)}"
            }
    def get_tax_records(self, user_id: str, limit: int = 10) -> List[Dict]:
        """获取用户的税收记录"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT tax_id, tax_amount, tax_rate, original_amount, balance_after, timestamp, tax_type AS reason
                    FROM taxes
                    WHERE user_id = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (user_id, limit))

                return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"获取税收记录失败: {e}")
            return []

    def _migrate_database(self):
        """执行数据库修改操作"""
        # 查看用户表是否有鱼塘容量列
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(users)")
            columns = [col[1] for col in cursor.fetchall()]

            # 如果没有 fish_pond_capacity 列，则添加
            if 'fish_pond_capacity' not in columns:
                cursor.execute("ALTER TABLE users ADD COLUMN fish_pond_capacity INTEGER DEFAULT 480")
                logger.info("已添加 fish_pond_capacity 列到 users 表")
            # 如果没有被偷鱼时间列，则添加
            if 'last_stolen_at' not in columns:
                cursor.execute("ALTER TABLE users ADD COLUMN last_stolen_at DATETIME DEFAULT NULL")
                logger.info("已添加 last_stolen_at 列到 users 表")
            if 'forging_level' not in columns:
                cursor.execute("ALTER TABLE users ADD COLUMN forging_level INTEGER DEFAULT 0")
                logger.info("已添加 forging_level 列到 users 表")
            if 'player_class' not in columns:
                cursor.execute("ALTER TABLE users ADD COLUMN player_class TEXT DEFAULT '无'")
                logger.info("已添加 player_class 列到 users 表")
            # 检查鱼饵表中是否有龙涎香饵和丰饶号角粉末，删除它们
            cursor.execute("SELECT bait_id FROM baits WHERE name = '龙涎香饵'")
            if cursor.fetchone():
                cursor.execute("DELETE FROM baits WHERE name = '龙涎香饵'")
                logger.debug("已删除龙涎香饵")
            if 'last_active_skill_time' not in columns:
                cursor.execute("ALTER TABLE users ADD COLUMN last_active_skill_time TEXT DEFAULT NULL")
                logger.info("已添加 last_active_skill_time 列到 users 表")
            if 'active_buff_type' not in columns:
                cursor.execute("ALTER TABLE users ADD COLUMN active_buff_type TEXT DEFAULT NULL")
                logger.info("已添加 active_buff_type 列到 users 表")
            if 'buff_expires_at' not in columns:
                cursor.execute("ALTER TABLE users ADD COLUMN buff_expires_at TEXT DEFAULT NULL")
                logger.info("已添加 buff_expires_at 列到 users 表")

            if 'pk_points' not in columns:
                cursor.execute("ALTER TABLE users ADD COLUMN pk_points INTEGER DEFAULT 0")
            if 'last_duel_info' not in columns: # 记录对同一人的CD
                cursor.execute("ALTER TABLE users ADD COLUMN last_duel_info TEXT DEFAULT '{}'")

            # PVE 相关
            if 'mirror_shards' not in columns:
                cursor.execute("ALTER TABLE users ADD COLUMN mirror_shards INTEGER DEFAULT 0")
            if 'shop_purchase_history' not in columns:
                cursor.execute("ALTER TABLE users ADD COLUMN shop_purchase_history TEXT DEFAULT '{}'")
            if 'last_corridor_info' not in columns:
                cursor.execute("ALTER TABLE users ADD COLUMN last_corridor_info TEXT DEFAULT '{}'")

            # 贷款系统相关字段
            if 'loan_total' not in columns:
                cursor.execute("ALTER TABLE users ADD COLUMN loan_total INTEGER DEFAULT 0")
            if 'loan_repaid' not in columns:
                cursor.execute("ALTER TABLE users ADD COLUMN loan_repaid INTEGER DEFAULT 0")

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_special_items (
                    user_id TEXT NOT NULL,
                    item_key TEXT NOT NULL, -- 'luck_charm', 'rod_chest', etc.
                    quantity INTEGER NOT NULL,
                    PRIMARY KEY (user_id, item_key),
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                );
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS duel_logs (
                    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    attacker_id TEXT NOT NULL,
                    defender_id TEXT NOT NULL,
                    winner_id TEXT,
                    details TEXT,
                    timestamp TEXT NOT NULL
                );
            """)

            cursor.execute("SELECT bait_id FROM baits WHERE name = '丰饶号角粉末'")
            if cursor.fetchone():
                cursor.execute("DELETE FROM baits WHERE name = '丰饶号角粉末'")
                logger.debug("已删除丰饶号角粉末")



    def get_user_fish_inventory_capacity(self, user_id):
        """获取用户鱼塘容量"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT fish_pond_capacity 
                FROM users 
                WHERE user_id = ?
            """, (user_id,))
            row = cursor.fetchone()
            # 获取当前鱼塘的容量
            cursor.execute("SELECT SUM(quantity) FROM user_fish_inventory WHERE user_id = ?", (user_id,))
            current_capacity = cursor.fetchone()[0] or 0
            return {
                "capacity": row['fish_pond_capacity'],
                "current_count": current_capacity
            }

    def upgrade_user_fish_inventory(self, user_id, to_capacity):
        """升级用户鱼塘容量

        Args:
            user_id: 用户ID
            to_capacity: 升级后的容量

        Returns:
            bool: 是否成功升级
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                # 直接将用户鱼塘容量修改为 to_capacity
                cursor.execute("""
                    UPDATE users 
                    SET fish_pond_capacity = ? 
                    WHERE user_id = ?
                """, (to_capacity, user_id))
                conn.commit()
                return {
                    'success': True,
                    'message': f"鱼塘容量已升级到 {to_capacity} 只"
                }
        except sqlite3.Error as e:
            logger.error(f"升级鱼塘容量失败: {e}")
            return {
                'success': False,
                'message': f"升级鱼塘容量失败: {str(e)}"
            }

    def get_user_by_id(self, target_id):
        """根据用户ID获取用户信息

        Args:
            target_id: 用户ID

        Returns:
            Dict: 用户信息字典
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (target_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def steal_fish(self, user_id, target_id):
        """偷取目标用户的鱼 (已修复时区问题并支持职业系统)"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # --- 获取双方职业 ---
                cursor.execute("SELECT player_class, forging_level, last_stolen_at FROM users WHERE user_id = ?", (user_id,))
                attacker_info = cursor.fetchone()
                attacker_class = attacker_info['player_class'] if attacker_info else '无'

                cursor.execute("SELECT player_class FROM users WHERE user_id = ?", (target_id,))
                defender_info = cursor.fetchone()
                defender_class = defender_info['player_class'] if defender_info else '无'

                # --- 敏锐直觉 (影之掠夺者被动) ---
                if defender_class == 'plunderer' and random.random() < 0.25:
                    return {
                        'success': False,
                        'message': "你感觉到似乎有人在窥探对方的鱼塘，但被一股神秘的力量弹开了！"
                    }
                active_buff = self.get_user_buff(user_id)
                if active_buff and active_buff['type'] == 'plunderer_skill':
                    # 如果暗影帷幕Buff生效，直接跳过CD检查
                    pass
                else:
                    # --- CD检查逻辑 ---
                    last_stolen_at_str = attacker_info['last_stolen_at']
                    if last_stolen_at_str:
                       last_stolen_datetime = None
                       try:
                           # 步骤1: 优先尝试按新的ISO格式(带时区)解析
                           aware_dt = datetime.fromisoformat(last_stolen_at_str)
                           last_stolen_datetime = aware_dt.replace(tzinfo=timezone.utc) + timedelta(hours=4)
                       except ValueError:
                           # 步骤2: 如果失败，再尝试按旧的朴素格式解析
                           try:
                               naive_dt = datetime.strptime(last_stolen_at_str, '%Y-%m-%d %H:%M:%S')
                               # 重要的假设：所有旧数据都视为 UTC+4
                               last_stolen_datetime = naive_dt.replace(tzinfo=UTC4)
                           except (ValueError, TypeError) as e:
                               logger.error(f"无法解析用户 {user_id} 的偷鱼时间: {last_stolen_at_str}, 错误: {e}")
                               # 解析失败，跳过CD检查以防卡死
                       # <<< 关键的兼容性修改结束 >>>
                       if last_stolen_datetime:
                           #current_time = get_utc4_now()
                           current_time = get_utc4_now().replace(tzinfo=timezone.utc) + timedelta(hours=4)
                           forging_level = attacker_info['forging_level'] if attacker_info else 0
                           bonuses = enhancement_config.get_bonuses_for_level(forging_level)
                           cd_reduction_seconds = bonuses['steal_cd_reduction'] * 60
                           total_cd = 14400 - cd_reduction_seconds
                           elapsed_time = (current_time - last_stolen_datetime).total_seconds()

                           if elapsed_time < total_cd:
                               remaining_seconds = total_cd - elapsed_time
                               remaining_h = int(remaining_seconds / 3600)
                               remaining_m = int((remaining_seconds % 3600) / 60)
                               return {
                                   'success': False,
                                   'message': f"你需要等待 {remaining_h}小时{remaining_m}分钟 才能再次偷鱼"
                               }
                           # # 将字符串时间转换为datetime对象，并添加UTC4时区信息
                           # last_stolen_datetime = datetime.strptime(last_stolen_at_str, '%Y-%m-%d %H:%M:%S')
                           # last_stolen_datetime = last_stolen_datetime.replace(tzinfo=timezone.utc) + timedelta(hours=4)
                           # # 使用get_utc4_now()获取当前时间
                           # current_time = get_utc4_now()
                           ## current_time = get_utc4_now().replace(tzinfo=timezone.utc) + timedelta(hours=4)
                           # logger.info(f"当前时间: {current_time}, 上次偷鱼时间: {last_stolen_datetime}")
                           # # 获取锻造等级带来的CD减少
                           # cursor.execute("SELECT forging_level FROM users WHERE user_id = ?", (user_id,))
                           # forging_level_row = cursor.fetchone()
                           # forging_level = forging_level_row['forging_level'] if forging_level_row else 0
                           # bonuses = enhancement_config.get_bonuses_for_level(forging_level)
                           # cd_reduction_seconds = bonuses['steal_cd_reduction'] * 60
                           # logger.info(f"用户 {user_id} 偷鱼CD检查：当前时间: {current_time}, 上次偷鱼时间: {last_stolen_datetime}, CD减少: {cd_reduction_seconds}s")
                           # # 如果上次偷鱼时间在4小时内，则不能偷
                           # if (current_time - last_stolen_datetime).total_seconds() < (14400 - cd_reduction_seconds):
                           #     remaining_seconds = (14400 - cd_reduction_seconds) - (current_time - last_stolen_datetime).total_seconds()
                           #     remaining_h = int(remaining_seconds / 3600)
                           #     remaining_m = int((remaining_seconds % 3600) / 60)
                           #     return {
                           #         'success': False,
                           #         'message': f"你需要等待 {remaining_h}小时{remaining_m}分钟 才能再次偷鱼"
                           #     }

                # --- 偷鱼核心逻辑 ---
                # <<< 修改：根据攻击者职业决定偷鱼策略 >>>
                if attacker_class == 'plunderer':
                    # 【精准出手】: 偷最贵的鱼
                    query = """
                        SELECT ufi.fish_id, ufi.quantity
                        FROM user_fish_inventory ufi
                        JOIN fish f ON ufi.fish_id = f.fish_id
                        WHERE ufi.user_id = ?
                        ORDER BY f.base_value DESC
                        LIMIT 1
                    """
                else:
                    # 普通玩家：随机偷
                    query = "SELECT fish_id, quantity FROM user_fish_inventory WHERE user_id = ? ORDER BY RANDOM() LIMIT 1"

                cursor.execute(query, (target_id,))
                stolen_fish = cursor.fetchone()

                # ... (后续的偷鱼执行逻辑与之前相同) ...
                if not stolen_fish:
                    return {'success': False, 'message': "目标用户没有鱼可被偷"}
                fish_id, quantity = stolen_fish['fish_id'], stolen_fish['quantity']
                if quantity == 1:
                    cursor.execute("DELETE FROM user_fish_inventory WHERE user_id = ? AND fish_id = ?", (target_id, fish_id))
                else:
                    cursor.execute("UPDATE user_fish_inventory SET quantity = quantity - 1 WHERE user_id = ? AND fish_id = ?", (target_id, fish_id))
                cursor.execute("INSERT INTO user_fish_inventory (user_id, fish_id, quantity) VALUES (?, ?, 1) ON CONFLICT(user_id, fish_id) DO UPDATE SET quantity = quantity + 1", (user_id, fish_id))
                cursor.execute("UPDATE users SET last_stolen_at = ? WHERE user_id = ?", (get_utc4_now().isoformat(), user_id))
                cursor.execute("SELECT name FROM fish WHERE fish_id = ?", (fish_id,))
                fish_name = cursor.fetchone()['name']
                cursor.execute("SELECT nickname FROM users WHERE user_id = ?", (target_id,))
                target_nickname = cursor.fetchone()['nickname']
                conn.commit()
                return {
                    'success': True,
                    'message': f"成功偷取 {target_nickname} 的 {fish_name}，数量: 1"
                }
        except sqlite3.Error as e:
            logger.error(f"偷鱼失败: {e}")
            return {'success': False, 'message': f"偷鱼失败: {str(e)}"}
   # def steal_fish(self, user_id, target_id):
   #     """偷取目标用户的鱼

   #     Args:
   #         user_id: 偷鱼者的用户ID
   #         target_id: 被偷者的用户ID

   #     Returns:
   #         dict: 偷鱼结果，包括成功与否和消息
   #     """
   #     try:
   #         with self._get_connection() as conn:
   #             cursor = conn.cursor()

   #             # 先检查偷鱼者是否有足够的时间间隔
   #             cursor.execute("""
   #                 SELECT last_stolen_at 
   #                 FROM users 
   #                 WHERE user_id = ?
   #             """, (user_id,))
   #             last_stolen_at = cursor.fetchone()['last_stolen_at']
   #             if last_stolen_at:
   #                 # 将字符串时间转换为datetime对象，并添加UTC4时区信息
   #                 last_stolen_datetime = datetime.strptime(last_stolen_at, '%Y-%m-%d %H:%M:%S')
   #                 last_stolen_datetime = last_stolen_datetime.replace(tzinfo=timezone.utc) + timedelta(hours=4)
   #                 # 使用get_utc4_now()获取当前时间
   #                 #current_time = get_utc4_now()
   #                 current_time = get_utc4_now().replace(tzinfo=timezone.utc) + timedelta(hours=4)
   #                 logger.info(f"当前时间: {current_time}, 上次偷鱼时间: {last_stolen_datetime}")
   #                 # 获取锻造等级带来的CD减少
   #                 cursor.execute("SELECT forging_level FROM users WHERE user_id = ?", (user_id,))
   #                 forging_level_row = cursor.fetchone()
   #                 forging_level = forging_level_row['forging_level'] if forging_level_row else 0
   #                 bonuses = enhancement_config.get_bonuses_for_level(forging_level)
   #                 cd_reduction_seconds = bonuses['steal_cd_reduction'] * 60
   #                 logger.info(f"用户 {user_id} 偷鱼CD检查：当前时间: {current_time}, 上次偷鱼时间: {last_stolen_datetime}, CD减少: {cd_reduction_seconds}s")
   #                 # 如果上次偷鱼时间在4小时内，则不能偷
   #                 if (current_time - last_stolen_datetime).total_seconds() < (14400 - cd_reduction_seconds):
   #                     remaining_seconds = (14400 - cd_reduction_seconds) - (current_time - last_stolen_datetime).total_seconds()
   #                     remaining_h = int(remaining_seconds / 3600)
   #                     remaining_m = int((remaining_seconds % 3600) / 60)
   #                     return {
   #                         'success': False,
   #                         'message': f"你需要等待 {remaining_h}小时{remaining_m}分钟 才能再次偷鱼"
   #                     }
   #                     #return {
   #                     #    'success': False,
   #                     #    'message': "你需要等待4小时才能再次偷鱼"
   #                     #}

   #             # 检查目标用户是否有鱼可被偷
   #             cursor.execute("""
   #                 SELECT fish_id, quantity 
   #                 FROM user_fish_inventory 
   #                 WHERE user_id = ? 
   #                 ORDER BY RANDOM() 
   #                 LIMIT 1
   #             """, (target_id,))
   #             stolen_fish = cursor.fetchone()
   #             if not stolen_fish:
   #                 return {
   #                     'success': False,
   #                     'message': "目标用户没有鱼可被偷"
   #                 }

   #             fish_id, quantity = stolen_fish['fish_id'], stolen_fish['quantity']

   #             # 从目标用户库存中删除被偷的鱼
   #             if quantity == 1:
   #                 cursor.execute("""
   #                     DELETE FROM user_fish_inventory 
   #                     WHERE user_id = ? AND fish_id = ?
   #                 """, (target_id, fish_id))
   #             else:
   #                 cursor.execute("""
   #                     UPDATE user_fish_inventory 
   #                     SET quantity = quantity - 1 
   #                     WHERE user_id = ? AND fish_id = ?
   #                 """, (target_id, fish_id))

   #             # 将被偷的鱼添加到偷鱼者的库存中
   #             cursor.execute("""
   #                 INSERT INTO user_fish_inventory (user_id, fish_id, quantity)
   #                 VALUES (?, ?, 1)
   #                 ON CONFLICT(user_id, fish_id) DO UPDATE SET quantity = quantity + 1
   #             """, (user_id, fish_id))
   #             # 记录偷鱼时间
   #             cursor.execute("""
   #                 UPDATE users 
   #                 SET last_stolen_at = ?
   #                 WHERE user_id = ?
   #             """, (get_utc4_now().strftime('%Y-%m-%d %H:%M:%S'),user_id))
   #             # 获取鱼的名称
   #             cursor.execute("""
   #                 SELECT name 
   #                 FROM fish 
   #                 WHERE fish_id = ?
   #             """, (fish_id,))
   #             fish_name = cursor.fetchone()['name']
   #             # 获取被偷人的昵称
   #             cursor.execute("""
   #                 SELECT nickname 
   #                 FROM users 
   #                 WHERE user_id = ?
   #             """, (target_id,))
   #             target_nickname = cursor.fetchone()['nickname']
   #             # 提交事务
   #             conn.commit()
   #             return {
   #                 'success': True,
   #                 'message': f"成功偷取 {target_nickname} 的 {fish_name}，数量: 1"
   #             }
   #     except sqlite3.Error as e:
   #         logger.error(f"偷鱼失败: {e}")
   #         return {
   #             'success': False,
   #             'message': f"偷鱼失败: {str(e)}"
   #         }


    # webui 数据库操作
    # 在 db.py 的 FishingDB 类中添加

    def get_all_fish(self) -> List[Dict]:
        """获取所有鱼类信息，用于后台管理"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM fish ORDER BY rarity DESC, fish_id DESC")
            return [dict(row) for row in cursor.fetchall()]

    def add_fish(self, data: Dict) -> bool:
        """后台添加一条新鱼"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO fish (name, description, rarity, base_value, min_weight, max_weight, icon_url)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (data['name'], data['description'], data['rarity'], data['base_value'], data['min_weight'],
                      data['max_weight'], data.get('icon_url')))
                conn.commit()
                return True
        except sqlite3.Error as e:
            logger.error(f"后台添加鱼类失败: {e}")
            return False

    def update_fish(self, fish_id: int, data: Dict) -> bool:
        """后台更新一条鱼的信息"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE fish SET
                    name = ?, description = ?, rarity = ?, base_value = ?,
                    min_weight = ?, max_weight = ?, icon_url = ?
                    WHERE fish_id = ?
                """, (data['name'], data['description'], data['rarity'], data['base_value'], data['min_weight'],
                      data['max_weight'], data.get('icon_url'), fish_id))
                conn.commit()
                return True
        except sqlite3.Error as e:
            logger.error(f"后台更新鱼类 {fish_id} 失败: {e}")
            return False

    def delete_fish(self, fish_id: int) -> bool:
        """后台删除一条鱼"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM fish WHERE fish_id = ?", (fish_id,))
                conn.commit()
                return True
        except sqlite3.Error as e:
            logger.error(f"后台删除鱼类 {fish_id} 失败: {e}")
            return False

    # --- 后台管理方法：鱼竿 ---

    def get_all_rods_admin(self) -> list[dict]:
        """获取所有鱼竿信息，用于后台管理"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM rods ORDER BY rarity DESC, rod_id DESC")
            return [dict(row) for row in cursor.fetchall()]

    def add_rod_admin(self, data: dict) -> bool:
        """后台添加一个新鱼竿"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO rods (name, description, rarity, source, purchase_cost, 
                                      bonus_fish_quality_modifier, bonus_fish_quantity_modifier, 
                                      bonus_rare_fish_chance, durability, icon_url)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (data['name'], data.get('description'), data['rarity'], data['source'],
                      data.get('purchase_cost') or None,
                      data.get('bonus_fish_quality_modifier', 1.0), data.get('bonus_fish_quantity_modifier', 1.0),
                      data.get('bonus_rare_fish_chance', 0.0), data.get('durability') or None, data.get('icon_url')))
                conn.commit()
                return True
        except sqlite3.Error as e:
            logger.error(f"后台添加鱼竿失败: {e}")
            return False

    def update_rod_admin(self, rod_id: int, data: dict) -> bool:
        """后台更新一个鱼竿的信息"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE rods SET
                    name = ?, description = ?, rarity = ?, source = ?, purchase_cost = ?, 
                    bonus_fish_quality_modifier = ?, bonus_fish_quantity_modifier = ?, 
                    bonus_rare_fish_chance = ?, durability = ?, icon_url = ?
                    WHERE rod_id = ?
                """, (data['name'], data.get('description'), data['rarity'], data['source'],
                      data.get('purchase_cost') or None,
                      data.get('bonus_fish_quality_modifier', 1.0), data.get('bonus_fish_quantity_modifier', 1.0),
                      data.get('bonus_rare_fish_chance', 0.0), data.get('durability') or None, data.get('icon_url'),
                      rod_id))
                conn.commit()
                return True
        except sqlite3.Error as e:
            logger.error(f"后台更新鱼竿 {rod_id} 失败: {e}")
            return False

    def delete_rod_admin(self, rod_id: int) -> bool:
        """后台删除一个鱼竿"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM rods WHERE rod_id = ?", (rod_id,))
                conn.commit()
                return True
        except sqlite3.Error as e:
            logger.error(f"后台删除鱼竿 {rod_id} 失败: {e}")
            return False

    # --- 后台管理方法：鱼饵 ---

    def get_all_baits_admin(self) -> list[dict]:
        """获取所有鱼饵信息，用于后台管理"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM baits ORDER BY rarity DESC, bait_id DESC")
            return [dict(row) for row in cursor.fetchall()]

    def add_bait_admin(self, data: dict) -> bool:
        """后台添加一个新鱼饵"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO baits (name, description, rarity, effect_description, 
                                       duration_minutes, cost, required_rod_rarity)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (data['name'], data.get('description'), data['rarity'], data.get('effect_description'),
                      data.get('duration_minutes', 0), data.get('cost', 0), data.get('required_rod_rarity', 0)))
                conn.commit()
                return True
        except sqlite3.Error as e:
            logger.error(f"后台添加鱼饵失败: {e}")
            return False

    def update_bait_admin(self, bait_id: int, data: dict) -> bool:
        """后台更新一个鱼饵的信息"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE baits SET
                    name = ?, description = ?, rarity = ?, effect_description = ?, 
                    duration_minutes = ?, cost = ?, required_rod_rarity = ?
                    WHERE bait_id = ?
                """, (data['name'], data.get('description'), data['rarity'], data.get('effect_description'),
                      data.get('duration_minutes', 0), data.get('cost', 0), data.get('required_rod_rarity', 0),
                      bait_id))
                conn.commit()
                return True
        except sqlite3.Error as e:
            logger.error(f"后台更新鱼饵 {bait_id} 失败: {e}")
            return False

    def delete_bait_admin(self, bait_id: int) -> bool:
        """后台删除一个鱼饵"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM baits WHERE bait_id = ?", (bait_id,))
                conn.commit()
                return True
        except sqlite3.Error as e:
            logger.error(f"后台删除鱼饵 {bait_id} 失败: {e}")
            return False

    # --- 后台管理方法：饰品 ---

    def get_all_accessories_admin(self) -> list[dict]:
        """获取所有饰品信息，用于后台管理"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM accessories ORDER BY rarity DESC, accessory_id DESC")
            return [dict(row) for row in cursor.fetchall()]

    def add_accessory_admin(self, data: dict) -> bool:
        """后台添加一个新饰品"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO accessories (name, description, rarity, slot_type, bonus_fish_quality_modifier,
                                             bonus_fish_quantity_modifier, bonus_rare_fish_chance,
                                             bonus_coin_modifier, other_bonus_description, icon_url)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (data['name'], data.get('description'), data['rarity'], data.get('slot_type', 'general'),
                      data.get('bonus_fish_quality_modifier', 1.0), data.get('bonus_fish_quantity_modifier', 1.0),
                      data.get('bonus_rare_fish_chance', 0.0), data.get('bonus_coin_modifier', 1.0),
                      data.get('other_bonus_description'), data.get('icon_url')))
                conn.commit()
                return True
        except sqlite3.Error as e:
            logger.error(f"后台添加饰品失败: {e}")
            return False

    def update_accessory_admin(self, accessory_id: int, data: dict) -> bool:
        """后台更新一个饰品的信息"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE accessories SET
                    name = ?, description = ?, rarity = ?, slot_type = ?, bonus_fish_quality_modifier = ?,
                    bonus_fish_quantity_modifier = ?, bonus_rare_fish_chance = ?,
                    bonus_coin_modifier = ?, other_bonus_description = ?, icon_url = ?
                    WHERE accessory_id = ?
                """, (data['name'], data.get('description'), data['rarity'], data.get('slot_type', 'general'),
                      data.get('bonus_fish_quality_modifier', 1.0), data.get('bonus_fish_quantity_modifier', 1.0),
                      data.get('bonus_rare_fish_chance', 0.0), data.get('bonus_coin_modifier', 1.0),
                      data.get('other_bonus_description'), data.get('icon_url'), accessory_id))
                conn.commit()
                return True
        except sqlite3.Error as e:
            logger.error(f"后台更新饰品 {accessory_id} 失败: {e}")
            return False

    def delete_accessory_admin(self, accessory_id: int) -> bool:
        """后台删除一个饰品"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM accessories WHERE accessory_id = ?", (accessory_id,))
                conn.commit()
                return True
        except sqlite3.Error as e:
            logger.error(f"后台删除饰品 {accessory_id} 失败: {e}")
            return False

    # --- 后台管理方法：抽卡池 ---

    def get_gacha_pool_admin(self, pool_id: int) -> dict:
        """获取单个抽卡池信息"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM gacha_pools WHERE gacha_pool_id = ?", (pool_id,))
            return dict(cursor.fetchone())

    def add_gacha_pool_admin(self, data: dict) -> bool:
        """后台添加一个新抽卡池"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO gacha_pools (name, description, cost_coins, cost_premium_currency)
                    VALUES (?, ?, ?, ?)
                """, (
                data['name'], data.get('description'), data.get('cost_coins', 0), data.get('cost_premium_currency', 0)))
                conn.commit()
                return True
        except sqlite3.Error as e:
            logger.error(f"后台添加抽卡池失败: {e}")
            return False

    def update_gacha_pool_admin(self, pool_id: int, data: dict) -> bool:
        """后台更新一个抽卡池的信息"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE gacha_pools SET
                    name = ?, description = ?, cost_coins = ?, cost_premium_currency = ?
                    WHERE gacha_pool_id = ?
                """, (
                data['name'], data.get('description'), data.get('cost_coins', 0), data.get('cost_premium_currency', 0),
                pool_id))
                conn.commit()
                return True
        except sqlite3.Error as e:
            logger.error(f"后台更新抽卡池 {pool_id} 失败: {e}")
            return False

    def delete_gacha_pool_admin(self, pool_id: int) -> bool:
        """后台删除一个抽卡池（其下的物品也会被级联删除）"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM gacha_pools WHERE gacha_pool_id = ?", (pool_id,))
                conn.commit()
                return True
        except sqlite3.Error as e:
            logger.error(f"后台删除抽卡池 {pool_id} 失败: {e}")
            return False

    # --- 后台管理方法：抽卡池 & 抽卡池物品 ---

    def get_gacha_pool_admin(self, pool_id: int) -> dict:
        """获取单个抽卡池信息"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM gacha_pools WHERE gacha_pool_id = ?", (pool_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def add_gacha_pool_admin(self, data: dict) -> bool:
        """后台添加一个新抽卡池"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO gacha_pools (name, description, cost_coins)
                    VALUES (?, ?, ?)
                """, (data['name'], data.get('description'), data.get('cost_coins', 0)))
                conn.commit()
                return True
        except sqlite3.Error as e:
            logger.error(f"后台添加抽卡池失败: {e}")
            return False

    def update_gacha_pool_admin(self, pool_id: int, data: dict) -> bool:
        """后台更新一个抽卡池的信息"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE gacha_pools SET
                    name = ?, description = ?, cost_coins = ?
                    WHERE gacha_pool_id = ?
                """, (data['name'], data.get('description'), data.get('cost_coins', 0), pool_id))
                conn.commit()
                return True
        except sqlite3.Error as e:
            logger.error(f"后台更新抽卡池 {pool_id} 失败: {e}")
            return False

    def delete_gacha_pool_admin(self, pool_id: int) -> bool:
        """后台删除一个抽卡池（其下的物品也会被级联删除）"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM gacha_pools WHERE gacha_pool_id = ?", (pool_id,))
                conn.commit()
                return True
        except sqlite3.Error as e:
            logger.error(f"后台删除抽卡池 {pool_id} 失败: {e}")
            return False

    def get_items_in_pool_admin(self, pool_id: int) -> list[dict]:
        """获取指定抽卡池内的所有物品详情"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    gpi.*,
                    CASE
                        WHEN gpi.item_type = 'rod' THEN r.name
                        WHEN gpi.item_type = 'bait' THEN b.name
                        WHEN gpi.item_type = 'accessory' THEN a.name
                        WHEN gpi.item_type = 'fish' THEN f.name
                        WHEN gpi.item_type = 'titles' THEN t.name
                        WHEN gpi.item_type = 'coins' THEN '金币'
                        ELSE '未知'
                    END as item_name
                FROM gacha_pool_items gpi
                LEFT JOIN rods r ON gpi.item_type = 'rod' AND gpi.item_id = r.rod_id
                LEFT JOIN baits b ON gpi.item_type = 'bait' AND gpi.item_id = b.bait_id
                LEFT JOIN accessories a ON gpi.item_type = 'accessory' AND gpi.item_id = a.accessory_id
                LEFT JOIN fish f ON gpi.item_type = 'fish' AND gpi.item_id = f.fish_id
                LEFT JOIN titles t ON gpi.item_type = 'titles' AND gpi.item_id = t.title_id
                WHERE gpi.gacha_pool_id = ?
                ORDER BY gpi.gacha_pool_item_id DESC
            """, (pool_id,))
            return [dict(row) for row in cursor.fetchall()]

    def add_item_to_pool_admin(self, pool_id: int, data: dict) -> bool:
        """后台向抽卡池添加一个物品"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                item_full_id = data.get('item_full_id', '').split('-')
                if len(item_full_id) != 2: return False
                item_type, item_id = item_full_id

                cursor.execute("""
                    INSERT INTO gacha_pool_items (gacha_pool_id, item_type, item_id, quantity, weight)
                    VALUES (?, ?, ?, ?, ?)
                """, (pool_id, item_type, item_id, data.get('quantity', 1), data.get('weight', 10)))
                conn.commit()
                return True
        except sqlite3.Error as e:
            logger.error(f"后台添加物品到奖池 {pool_id} 失败: {e}")
            return False

    def update_pool_item_admin(self, item_pool_id: int, data: dict) -> bool:
        """后台更新一个抽卡池物品的信息"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                item_full_id = data.get('item_full_id', '').split('-')
                if len(item_full_id) != 2: return False
                item_type, item_id = item_full_id

                cursor.execute("""
                    UPDATE gacha_pool_items SET
                    item_type = ?, item_id = ?, quantity = ?, weight = ?
                    WHERE gacha_pool_item_id = ?
                """, (item_type, item_id, data.get('quantity', 1), data.get('weight', 10), item_pool_id))
                conn.commit()
                return True
        except sqlite3.Error as e:
            logger.error(f"后台更新奖池物品 {item_pool_id} 失败: {e}")
            return False

    def delete_pool_item_admin(self, item_pool_id: int) -> bool:
        """后台删除一个抽卡池物品"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM gacha_pool_items WHERE gacha_pool_item_id = ?", (item_pool_id,))
                conn.commit()
                return True
        except sqlite3.Error as e:
            logger.error(f"后台删除奖池物品 {item_pool_id} 失败: {e}")
            return False
        # db.py (文件末尾)

    def get_user_forging_level(self, user_id: str) -> int:
        """获取用户的锻造等级"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT forging_level FROM users WHERE user_id = ?", (user_id,))
            result = cursor.fetchone()
            return result['forging_level'] if result else 0

    def update_user_forging_level(self, user_id: str, level: int) -> bool:
        """更新用户的锻造等级"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE users SET forging_level = ? WHERE user_id = ?", (level, user_id))
                conn.commit()
                return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"更新用户锻造等级失败: {e}")
            return False

    def get_player_class(self, user_id: str) -> str:
        """获取用户的职业"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT player_class FROM users WHERE user_id = ?", (user_id,))
            result = cursor.fetchone()
            return result['player_class'] if result else '无'

    def set_player_class(self, user_id: str, class_name: str) -> bool:
        """设置用户的职业"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE users SET player_class = ? WHERE user_id = ?", (class_name, user_id))
                conn.commit()
                return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"设置用户职业失败: {e}")
            return False

    def get_last_active_skill_time(self, user_id: str) -> str:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT last_active_skill_time FROM users WHERE user_id = ?", (user_id,))
            result = cursor.fetchone()
            return result['last_active_skill_time'] if result else None

    def record_active_skill_use(self, user_id: str) -> bool:
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE users SET last_active_skill_time = ? WHERE user_id = ?", (get_utc4_now().isoformat(), user_id))
                conn.commit()
                return True
        except sqlite3.Error as e:
            logger.error(f"记录主动技能使用时间失败: {e}")
            return False

    def reset_daily_limits(self, user_id: str) -> bool:
        """重置签到和擦弹次数 (用于海洋之子技能)"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                today_str = get_utc4_today().isoformat()
                # 删除今天的签到记录
                cursor.execute("DELETE FROM check_ins WHERE user_id = ? AND check_in_date = ?", (user_id, today_str))
                # 删除今天的擦弹记录
                cursor.execute("DELETE FROM wipe_bomb_log WHERE user_id = ? AND DATE(timestamp) = ?", (user_id, today_str))
                conn.commit()
                return True
        except sqlite3.Error as e:
            logger.error(f"重置每日限制失败: {e}")
            return False

    def set_user_buff(self, user_id: str, buff_type: str, duration_hours: int) -> bool:
        """为用户设置一个Buff"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                expire_time = get_utc4_now() + timedelta(hours=duration_hours)
                cursor.execute(
                    "UPDATE users SET active_buff_type = ?, buff_expires_at = ? WHERE user_id = ?",
                    (buff_type, expire_time.isoformat(), user_id)
                )
                conn.commit()
                return True
        except sqlite3.Error as e:
            logger.error(f"设置用户Buff失败: {e}")
            return False

    def get_user_buff(self, user_id: str) -> Dict:
        """获取用户当前的Buff，如果已过期则返回None"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT active_buff_type, buff_expires_at FROM users WHERE user_id = ?",
                (user_id,)
            )
            result = cursor.fetchone()
            if not result or not result['active_buff_type'] or not result['buff_expires_at']:
                return None

            expire_time = datetime.fromisoformat(result['buff_expires_at'])
            if get_utc4_now() > expire_time:
                # Buff已过期，可以顺便清理一下
                self.clear_user_buff(user_id)
                return None

            return {'type': result['active_buff_type'], 'expires_at': expire_time}

    def clear_user_buff(self, user_id: str):
        """清除用户的Buff"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE users SET active_buff_type = NULL, buff_expires_at = NULL WHERE user_id = ?",
                    (user_id,)
                )
                conn.commit()
        except sqlite3.Error as e:
            logger.error(f"清除用户Buff失败: {e}")

    def get_fish_id_by_name(self, fish_name: str) -> Optional[int]:
        """根据鱼的名称获取其ID"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT fish_id FROM fish WHERE name = ?", (fish_name,))
            result = cursor.fetchone()
            return result['fish_id'] if result else None

    def consume_item_from_inventory(self, user_id: str, fish_id: int, quantity: int = 1) -> bool:
        """从用户鱼塘中消耗一个指定物品（如宝箱）"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                # 检查用户是否有足够的物品
                cursor.execute(
                    "SELECT quantity FROM user_fish_inventory WHERE user_id = ? AND fish_id = ?",
                    (user_id, fish_id)
                )
                result = cursor.fetchone()
                if not result or result['quantity'] < quantity:
                    return False # 物品不存在或数量不足

                # 消耗物品
                cursor.execute(
                    "UPDATE user_fish_inventory SET quantity = quantity - ? WHERE user_id = ? AND fish_id = ?",
                    (quantity, user_id, fish_id)
                )
                conn.commit()
                return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(f"消耗物品 {fish_id} 失败: {e}")
            return False

    def clear_last_active_skill_time(self, user_id: str) -> bool:
        """清除用户的主动技能最后使用时间，即重置CD"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE users SET last_active_skill_time = NULL WHERE user_id = ?",
                    (user_id,)
                )
                conn.commit()
                return True
        except sqlite3.Error as e:
            logger.error(f"清除用户技能CD失败: {e}")
            return False
    def get_duel_lineup(self, user_id: str, size: int, has_quality_bonus: bool) -> List[Dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            order_by_clause = "ORDER BY f.rarity DESC, RANDOM()" if has_quality_bonus else "ORDER BY RANDOM()"
            cursor.execute(f"""
                SELECT f.fish_id, f.name, f.rarity, f.base_value, f.min_weight, f.max_weight
                FROM user_fish_inventory ufi JOIN fish f ON ufi.fish_id = f.fish_id
                WHERE ufi.user_id = ? AND ufi.quantity > 0 {order_by_clause} LIMIT ?
            """, (user_id, size))
            lineup = [dict(row) for row in cursor.fetchall()]
            for fish in lineup:
                fish['weight'] = random.randint(fish['min_weight'], fish['max_weight'])
                fish['current_stats'] = {'rarity': fish['rarity'], 'weight': fish['weight'], 'value': fish['base_value']}
                fish['states'] = {'aura_disabled': False, 'ultimate_disabled': False}
            return lineup

    def execute_duel_results(self, winner_id, loser_id, prize_pool, stolen_fish_ids: List[int]):
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                conn.execute("BEGIN")
                cursor.execute("UPDATE users SET coins = coins + ?, pk_points = pk_points + 10 WHERE user_id = ?", (prize_pool, winner_id))
                cursor.execute("UPDATE users SET pk_points = pk_points - 5 WHERE user_id = ? AND pk_points >= 5", (loser_id,))
                for fish_id in stolen_fish_ids:
                    cursor.execute("UPDATE user_fish_inventory SET quantity = quantity - 1 WHERE user_id = ? AND fish_id = ? AND quantity > 0", (loser_id, fish_id))
                    cursor.execute("INSERT INTO user_fish_inventory (user_id, fish_id, quantity) VALUES (?, ?, 1) ON CONFLICT(user_id, fish_id) DO UPDATE SET quantity = quantity + 1", (winner_id, fish_id))
                conn.commit()
                return True
        except sqlite3.Error as e:
            conn.rollback()
            logger.error(f"执行决斗结果失败: {e}")
            return False

    def record_duel_log(self, attacker_id, defender_id, winner_id, details):
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("INSERT INTO duel_logs (attacker_id, defender_id, winner_id, details, timestamp) VALUES (?, ?, ?, ?, ?)", (attacker_id, defender_id, winner_id, details, get_utc4_now().isoformat()))
                conn.commit()
        except sqlite3.Error as e:
            logger.error(f"记录决斗日志失败: {e}")

    def get_user_for_duel(self, user_id: str) -> Dict:
        """获取用户决斗所需的信息"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT coins, player_class, last_duel_info, pk_points FROM users WHERE user_id = ?", (user_id,))
            result = cursor.fetchone()
            return dict(result) if result else None

    def update_user_last_duel_info(self, user_id: str, new_info: str):
        """更新用户的上次决斗信息"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET last_duel_info = ? WHERE user_id = ?", (new_info, user_id))
            conn.commit()

    def get_user_ids_by_class(self, class_name: str) -> List[str]:
        """根据职业名称获取所有符合条件的玩家ID"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT user_id FROM users WHERE player_class = ?", (class_name,))
            return [row['user_id'] for row in cursor.fetchall()]

    def get_item_by_name(self, item_name: str) -> Optional[Dict]:
        """根据名称，在所有物品表中查找物品"""
        # 优先查找非鱼类物品，因为鱼类重名可能性低
        item_tables = {
            'bait': 'baits',
            'rod': 'rods',
            'accessory': 'accessories',
            'fish': 'fish'
        }
        with self._get_connection() as conn:
            cursor = conn.cursor()
            for item_type, table_name in item_tables.items():
                # 为了简化，我们假设每个表都有一个唯一的 name 字段
                id_column = f"{item_type}_id"
                if table_name == 'baits': id_column = 'bait_id' # 修正bait表的id

                cursor.execute(f"SELECT {id_column} AS item_id FROM {table_name} WHERE name = ?", (item_name,))
                result = cursor.fetchone()
                if result:
                    return {'type': item_type, 'id': result['item_id'], 'name': item_name}
        return None

    def batch_add_item_to_users(self, user_ids: List[str], item_info: Dict, quantity: int) -> int:
        """为一批用户批量添加物品"""
        if not user_ids: return 0

        item_type = item_info['type']
        item_id = item_info['id']
        success_count = 0

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                conn.execute("BEGIN")
                for user_id in user_ids:
                    try:
                        if item_type == 'fish':
                            cursor.execute("INSERT INTO user_fish_inventory (user_id, fish_id, quantity) VALUES (?, ?, ?) ON CONFLICT(user_id, fish_id) DO UPDATE SET quantity = quantity + ?", (user_id, item_id, quantity, quantity))
                        elif item_type == 'bait':
                            cursor.execute("INSERT INTO user_bait_inventory (user_id, bait_id, quantity) VALUES (?, ?, ?) ON CONFLICT(user_id, bait_id) DO UPDATE SET quantity = quantity + ?", (user_id, item_id, quantity, quantity))
                        elif item_type == 'rod':
                            # 鱼竿是独立的，需要循环添加
                            for _ in range(quantity):
                                self.add_rod_to_inventory(user_id, item_id)
                        elif item_type == 'accessory':
                            for _ in range(quantity):
                                self.add_accessory_to_inventory(user_id, item_id)
                        success_count += 1
                    except sqlite3.Error:
                        logger.error(f"为用户 {user_id} 添加物品 {item_info['name']} 失败，跳过。")
                conn.commit()
                return success_count
        except sqlite3.Error as e:
            conn.rollback()
            logger.error(f"批量添加物品失败: {e}")
            return 0

    def batch_add_coins_to_users(self, user_ids: List[str], amount: int) -> int:
        """为一批用户批量增加金币"""
        if not user_ids or amount <= 0: return 0
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                # 使用 executemany 提高效率
                params = [(amount, user_id) for user_id in user_ids]
                cursor.executemany("UPDATE users SET coins = coins + ? WHERE user_id = ?", params)
                conn.commit()
                return cursor.rowcount
        except sqlite3.Error as e:
            logger.error(f"批量增加金币失败: {e}")
            return 0

    def get_legendary_fish_data(self) -> List[Dict]:
        """获取所有R4和R5鱼的数据"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name, rarity, description FROM fish WHERE rarity >= 4 ORDER BY rarity, fish_id")
            return [dict(row) for row in cursor.fetchall()]

    def get_fish_by_names(self, names: List[str]) -> List[Dict]:
        """根据一批名称获取鱼的完整数据"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            placeholders = ','.join('?' for name in names)
            cursor.execute(f"SELECT * FROM fish WHERE name IN ({placeholders})", names)
            #return [dict(row) for row in cursor.fetchall()]
            lineup = [dict(row) for row in cursor.fetchall()]
            for fish in lineup:
                fish['weight'] = random.randint(fish['min_weight'], fish['max_weight'])
                fish['current_stats'] = {'rarity': fish['rarity'], 'weight': fish['weight'], 'value': fish['base_value']}
                fish['states'] = {'aura_disabled': False, 'ultimate_disabled': False}
            return lineup

    def get_random_r5_item(self, item_type: str) -> Optional[Dict]:
        """随机获取一个R5的鱼竿或饰品"""
        table = 'rods' if item_type == 'rod' else 'accessories'
        id_col = 'rod_id' if item_type == 'rod' else 'accessory_id'
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"SELECT {id_col} AS item_id, name FROM {table} WHERE rarity = 5 ORDER BY RANDOM() LIMIT 1")
            result = cursor.fetchone()
            return dict(result) if result else None

    def add_special_item(self, user_id, item_key, quantity=1):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO user_special_items (user_id, item_key, quantity) VALUES (?, ?, ?) "
                "ON CONFLICT(user_id, item_key) DO UPDATE SET quantity = quantity + excluded.quantity",
                (user_id, item_key, quantity)
            )
            conn.commit()

    def update_user_shop_history(self, user_id: str, history_json: str):
        """更新用户的商店购买历史"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET shop_purchase_history = ? WHERE user_id = ?", (history_json, user_id))
            conn.commit()

    # db.py (文件末尾)
    def get_special_item_count(self, user_id: str, item_key: str) -> int:
        """获取用户拥有的特殊物品数量"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT quantity FROM user_special_items WHERE user_id = ? AND item_key = ?", (user_id, item_key))
            result = cursor.fetchone()
            return result['quantity'] if result else 0

    def consume_special_item(self, user_id: str, item_key: str, quantity: int = 1) -> bool:
        """消耗用户的特殊物品"""
        current_quantity = self.get_special_item_count(user_id, item_key)
        if current_quantity < quantity:
            return False

        with self._get_connection() as conn:
            cursor = conn.cursor()
            new_quantity = current_quantity - quantity
            if new_quantity > 0:
                cursor.execute("UPDATE user_special_items SET quantity = ? WHERE user_id = ? AND item_key = ?", (new_quantity, user_id, item_key))
            else:
                cursor.execute("DELETE FROM user_special_items WHERE user_id = ? AND item_key = ?", (user_id, item_key))
            conn.commit()
            return True

    def get_all_user_special_items(self, user_id: str) -> List[Dict]:
        """获取一个用户拥有的所有特殊物品及其数量"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT item_key, quantity FROM user_special_items WHERE user_id = ? AND quantity > 0",
                (user_id,)
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_user_fish_count(self, user_id: str, fish_id: int) -> int:
        """获取用户拥有的指定单种鱼的数量"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT quantity FROM user_fish_inventory WHERE user_id = ? AND fish_id = ?",
                (user_id, fish_id)
            )
            result = cursor.fetchone()
            return result['quantity'] if result else 0

    def update_user_corridor_info(self, user_id: str, info_json: str):
        """更新用户的回廊挑战信息"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET last_corridor_info = ? WHERE user_id = ?", (info_json, user_id))
            conn.commit()

    # db.py (文件末尾)

    def grant_loan(self, user_id: str, total_amount: int):
        """为用户发放一笔新贷款"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # 增加金币
            cursor.execute("UPDATE users SET coins = coins + ? WHERE user_id = ?", (total_amount, user_id))
            # 设置贷款状态
            cursor.execute("UPDATE users SET loan_total = ?, loan_repaid = 0 WHERE user_id = ?", (total_amount, user_id))
            conn.commit()

    def get_loan_status(self, user_id: str) -> Optional[Dict]:
        """获取用户的贷款状态"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT loan_total, loan_repaid FROM users WHERE user_id = ?", (user_id,))
            result = cursor.fetchone()
            return dict(result) if result else None

    def make_repayment(self, user_id: str, repayment_amount: int) -> int:
        """记录一笔还款，并返回还款后的总已还款额"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET loan_repaid = loan_repaid + ? WHERE user_id = ?", (repayment_amount, user_id))
            conn.commit()

            cursor.execute("SELECT loan_repaid FROM users WHERE user_id = ?", (user_id,))
            return cursor.fetchone()['loan_repaid']

    def clear_loan(self, user_id: str):
        """结清用户的贷款"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET loan_total = 0, loan_repaid = 0 WHERE user_id = ?", (user_id,))
            conn.commit()

    def batch_initialize_loans(self, loan_data: List[Tuple[int, int, str]]):
        """
        批量为用户初始化贷款状态。
        loan_data 的格式为: [(loan_total, loan_repaid, user_id), ...]
        """
        if not loan_data:
            return 0

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                # 使用 executemany 来高效地执行批量更新
                cursor.executemany(
                    "UPDATE users SET loan_total = ?, loan_repaid = ? WHERE user_id = ?",
                    loan_data
                )
                conn.commit()
                return cursor.rowcount # 返回成功更新的行数
        except sqlite3.Error as e:
            logger.error(f"批量初始化贷款失败: {e}")
            return -1 # 返回-1表示出错
