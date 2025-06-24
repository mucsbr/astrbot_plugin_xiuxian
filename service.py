from datetime import datetime, timedelta
import json
import random
import sqlite3
from collections import namedtuple
import time

from astrbot.api import logger

from .config import XiuConfig, USERRANK
from .data_manager import jsondata
from .item_manager import Items

# 定义数据模型
UserDate = namedtuple(
    "UserDate",
    ["id", "user_id", "stone", "root", "root_type", "level", "power", "create_time", "is_sign", "exp",
     "user_name", "level_up_cd", "level_up_rate", "sect_id", "sect_position", "hp", "mp", "atk", "atkpractice",
     "sect_task", "sect_contribution", "sect_elixir_get", "blessed_spot_flag", "blessed_spot_name", "wanted_status",
     "reincarnation_buff"]
)
MarketGoods = namedtuple(
    "MarketGoods",
    ["id", "user_id", "goods_id", "goods_name", "goods_type", "price", "group_id", "user_name"]
)
UserAlchemyInfo = namedtuple(
    "UserAlchemyInfo",
    ["user_id", "collection_level", "fire_level", "pill_resistance_level", "alchemy_exp", "alchemy_record", "last_collection_time"]
)
# ^-- 追加结束 --^
UserCd = namedtuple("UserCd", ["user_id", "type", "create_time", "scheduled_time"])
SectInfo = namedtuple(
    "SectInfo",
    ["sect_id", "sect_name", "sect_owner", "sect_scale", "sect_used_stone", "sect_fairyland",
     "sect_materials", "mainbuff", "secbuff", "elixir_room_level"]
)
BuffInfo = namedtuple(
    "BuffInfo",
    ["id", "user_id", "main_buff", "sec_buff", "faqi_buff", "fabao_weapon", "armor_buff", "atk_buff", "blessed_spot", "sub_buff"]
)
BackpackItem = namedtuple(
    "BackpackItem",
    ["user_id", "goods_id", "goods_name", "goods_type", "goods_num", "create_time", "update_time",
     "remake", "day_num", "all_num", "action_time", "state", "bind_num"]
)

class XiuxianService:
    """
    负责所有数据库交互的服务类
    """

    def __init__(self, db_path):
        self.db_path = db_path
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        logger.info("修仙数据库已连接！")
        self._check_and_create_tables()
        self.items = Items()
        self.xiu_config = XiuConfig()
        self.jsondata = jsondata
        self.user_temp_buffs = {}

    def get_goods_data(self) -> dict:
        return self.jsondata.get_goods_data()

    def close(self):
        self.conn.close()
        logger.info("修仙数据库已关闭！")

    def _check_and_create_tables(self):
        """检查并创建所有需要的数据库表和字段"""
        c = self.conn.cursor()
        tables = {
            "user_xiuxian": """
                CREATE TABLE "user_xiuxian" (
                    "id" INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT, "user_id" TEXT NOT NULL,
                    "stone" INTEGER DEFAULT 0, "root" TEXT, "root_type" TEXT, "level" TEXT,
                    "power" INTEGER DEFAULT 0, "create_time" TEXT, "is_sign" INTEGER DEFAULT 0,
                    "exp" INTEGER DEFAULT 0, "user_name" TEXT, "level_up_cd" TEXT,
                    "level_up_rate" INTEGER DEFAULT 0, "sect_id" INTEGER, "sect_position" INTEGER,
                    "hp" INTEGER, "mp" INTEGER, "atk" INTEGER, "atkpractice" INTEGER DEFAULT 0,
                    "sect_task" INTEGER DEFAULT 0, "sect_contribution" INTEGER DEFAULT 0,
                    "sect_elixir_get" INTEGER DEFAULT 0, "blessed_spot_flag" INTEGER DEFAULT 0,
                    "blessed_spot_name" TEXT
                );
            """,
            "user_cd": """
                CREATE TABLE "user_cd" (
                    "user_id" TEXT NOT NULL,
                    "type" INTEGER NOT NULL,
                    "create_time" TEXT,
                    "scheduled_time" TEXT,
                    PRIMARY KEY ("user_id", "type")
                );
            """,
            "sects": """
                CREATE TABLE "sects" (
                    "sect_id" INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT, "sect_name" TEXT NOT NULL,
                    "sect_owner" TEXT, "sect_scale" INTEGER NOT NULL DEFAULT 0,
                    "sect_used_stone" INTEGER DEFAULT 0, "sect_fairyland" TEXT,
                    "sect_materials" INTEGER DEFAULT 0, "mainbuff" TEXT, "secbuff" TEXT,
                    "elixir_room_level" INTEGER DEFAULT 0
                );
            """,
            "back": """
                CREATE TABLE "back" (
                    "user_id" TEXT NOT NULL, "goods_id" INTEGER NOT NULL, "goods_name" TEXT,
                    "goods_type" TEXT, "goods_num" INTEGER, "create_time" TEXT, "update_time" TEXT,
                    "remake" TEXT, "day_num" INTEGER DEFAULT 0, "all_num" INTEGER DEFAULT 0,
                    "action_time" TEXT, "state" INTEGER DEFAULT 0, "bind_num" INTEGER DEFAULT 0
                );
            """,
            "user_bounty": """
                CREATE TABLE "user_bounty" (
                    "user_id" TEXT NOT NULL PRIMARY KEY, "bounty_id" INTEGER NOT NULL,
                    "bounty_name" TEXT NOT NULL, "bounty_type" TEXT NOT NULL,
                    "monster_name" TEXT, "monster_hp" INTEGER, "monster_atk" INTEGER, "item_name" TEXT,
                    "item_id" INTEGER, "item_count" INTEGER, "is_completed" INTEGER DEFAULT 0
                );
            """,
            "user_rift": """
                CREATE TABLE "user_rift" (
                    "user_id" TEXT NOT NULL PRIMARY KEY, "rift_name" TEXT NOT NULL,
                    "rift_map" TEXT NOT NULL, "current_floor" INTEGER DEFAULT 1
                );
            """,
            "world_boss": """
                CREATE TABLE "world_boss" (
                    "id" INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT, "boss_name" TEXT NOT NULL,
                    "boss_level" TEXT NOT NULL, "current_hp" INTEGER NOT NULL,
                    "total_hp" INTEGER NOT NULL, "exp_reward" INTEGER NOT NULL,
                    "stone_reward" INTEGER NOT NULL, "atk" INTEGER NOT NULL,
                    "defense_rate" REAL DEFAULT 0.05,
                    "crit_rate" REAL DEFAULT 0.03,
                    "crit_damage" REAL DEFAULT 0.1 
                );
            """,
            "active_groups": """
                CREATE TABLE "active_groups" (
                    "group_id" TEXT NOT NULL PRIMARY KEY
                );
            """,
            "user_alchemy_info": """
                CREATE TABLE "user_alchemy_info" (
                    "user_id" TEXT NOT NULL PRIMARY KEY,
                    "collection_level" INTEGER DEFAULT 0,
                    "fire_level" INTEGER DEFAULT 0,
                    "pill_resistance_level" INTEGER DEFAULT 0,
                    "alchemy_exp" INTEGER DEFAULT 0,
                    "alchemy_record" TEXT,
                    "last_collection_time" TEXT
                );
            """,
            "market": """
                CREATE TABLE "market" (
                    "id" INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                    "user_id" TEXT NOT NULL,
                    "goods_id" INTEGER NOT NULL,
                    "goods_name" TEXT NOT NULL,
                    "goods_type" TEXT NOT NULL,
                    "price" INTEGER NOT NULL,
                    "group_id" TEXT NOT NULL,
                    "user_name" TEXT
                );
            """,
           "user_mortgage": """
            CREATE TABLE "user_mortgage" (
                "mortgage_id" INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                "user_id" TEXT NOT NULL,
                "item_id_original" INTEGER NOT NULL,
                "item_name" TEXT NOT NULL,
                "item_type" TEXT NOT NULL,
                "item_data_json" TEXT NOT NULL,
                "loan_amount" INTEGER NOT NULL,
                "mortgage_time" TEXT NOT NULL,
                "due_time" TEXT NOT NULL,
                "status" TEXT NOT NULL DEFAULT 'active'
            );
            """,
            "BuffInfo": """
                CREATE TABLE "BuffInfo" (
                    "id" INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT, "user_id" TEXT,
                    "main_buff" INTEGER DEFAULT 0, "sec_buff" INTEGER DEFAULT 0,
                    "faqi_buff" INTEGER DEFAULT 0, "fabao_weapon" INTEGER DEFAULT 0,
                    "armor_buff" INTEGER DEFAULT 0, "atk_buff" INTEGER DEFAULT 0,
                    "blessed_spot" INTEGER DEFAULT 0, "sub_buff" INTEGER DEFAULT 0
                );
            """
        }
        for table_name, creation_sql in tables.items():
            try:
                c.execute(f"SELECT count(*) FROM {table_name}")
            except sqlite3.OperationalError:
                c.execute(creation_sql)

            # 确保 world_boss 表有新字段 (对于可能已存在的旧表)
        boss_columns_to_add = {
            "defense_rate": "REAL DEFAULT 0.05",
            "crit_rate": "REAL DEFAULT 0.03",
            "crit_damage": "REAL DEFAULT 0.1"
        }
        c.execute("PRAGMA table_info(world_boss);")
        existing_boss_columns = [column[1] for column in c.fetchall()]
        for col, col_type in boss_columns_to_add.items():
            if col not in existing_boss_columns:
                try:
                    c.execute(f"ALTER TABLE world_boss ADD COLUMN {col} {col_type};")
                    logger.info(f"成功为 world_boss 表添加字段 {col}。")
                except sqlite3.OperationalError as e:
                    logger.error(f"为 world_boss 表添加字段 {col} 失败 (可能已存在但PRAGMA未及时刷新): {e}")

        # 检查并添加 wanted_status 字段（非破坏性更新）
        try:
            c.execute("SELECT wanted_status FROM user_xiuxian LIMIT 1")
        except sqlite3.OperationalError:
            try:
                c.execute("ALTER TABLE user_xiuxian ADD COLUMN wanted_status INTEGER DEFAULT 0;")
                logger.info("成功为 user_xiuxian 表添加 wanted_status 字段。")
            except sqlite3.OperationalError as e:
                logger.error(f"为 user_xiuxian 表添加字段失败: {e}")

               # v-- 3. 添加一个非破坏性的字段添加逻辑，确保老用户也能更新 --v
        try:
            c.execute("SELECT last_collection_time FROM user_alchemy_info LIMIT 1")
        except sqlite3.OperationalError:
            try:
                c.execute("ALTER TABLE user_alchemy_info ADD COLUMN last_collection_time TEXT;")
                logger.info("成功为 user_alchemy_info 表添加 last_collection_time 字段。")
            except sqlite3.OperationalError as e:
                logger.error(f"为 user_alchemy_info 表添加字段失败: {e}")

        try:
            c.execute("SELECT reincarnation_buff FROM user_xiuxian LIMIT 1")
        except sqlite3.OperationalError:
            try:
                # 存储修炼速度的百分比加成，例如 0.2 代表 20%
                c.execute("ALTER TABLE user_xiuxian ADD COLUMN reincarnation_buff REAL DEFAULT 0.0;")
                logger.info("成功为 user_xiuxian 表添加 reincarnation_buff 字段。")
            except sqlite3.OperationalError as e:
                logger.error(f"为 user_xiuxian 表添加字段失败: {e}")

        try:
            c.execute("SELECT monster_atk FROM user_bounty LIMIT 1")
        except sqlite3.OperationalError:
            c.execute("ALTER TABLE user_bounty ADD COLUMN monster_atk INTEGER;")
            logger.info("成功为 user_bounty 表添加 monster_atk 字段。")

        self.conn.commit()
    # v-- 新增的类方法 --v
    def cal_max_hp(self, user_msg, hp_buff_rate: float) -> int:
        if user_msg.level.startswith("化圣境"):
            level_info = jsondata.level_data().get(user_msg.level, {})
            exp = level_info.get("exp", user_msg.exp) * self.xiu_config.closing_exp_upper_limit
        else:
            exp = user_msg.exp
        max_hp = int(exp / 2 * (1 + hp_buff_rate))
        return max_hp

    def cal_max_mp(self, user_msg, mp_buff_rate: float) -> int:
        if user_msg.level.startswith("化圣境"):
            level_info = jsondata.level_data().get(user_msg.level, {})
            exp = level_info.get("exp", user_msg.exp) * self.xiu_config.closing_exp_upper_limit
        else:
            exp = user_msg.exp
        max_mp = int(exp * (1 + mp_buff_rate))
        return max_mp
    # ^-- 新增的类方法 --^
    
    def get_user_message(self, user_id: str) -> UserDate | None:
        """根据USER_ID获取原始用户信息"""
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM user_xiuxian WHERE user_id=?", (user_id,))
        result = cur.fetchone()
        return UserDate(*result) if result else None

    def register_user(self, user_id: str, user_name: str) -> dict:
        """注册新用户，返回一个包含结果的字典"""
        if self.get_user_message(user_id):
            return {"success": False, "message": "您已迈入修仙世界，输入【我的修仙信息】获取数据吧！"}

        linggen_data = jsondata.root_data()
        rate_dict = {i: v["type_rate"] for i, v in linggen_data.items()}
        root_type = self._calculated(rate_dict)
        
        if linggen_data[root_type]["type_flag"]:
            flag = random.choice(linggen_data[root_type]["type_flag"])
            root_list = random.sample(linggen_data[root_type]["type_list"], flag)
            root = "、".join(root_list) + '属性灵根'
        else:
            root = random.choice(linggen_data[root_type]["type_list"])
        
        rate = jsondata.root_data()[root_type]['type_speeds']
        power = 100 * float(rate)
        create_time = str(datetime.now())

        try:
            c = self.conn.cursor()
            c.execute(
                "INSERT INTO user_xiuxian (user_id, stone, root, root_type, level, power, create_time, user_name, exp, hp, mp, atk) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (user_id, 0, root, root_type, '江湖好手', int(power), create_time, user_name, 100, 50, 100, 10)
            )
            # 初始化 CD 表和 Buff 表
            c.execute("INSERT INTO user_cd (user_id) VALUES (?)", (user_id,))
            c.execute("INSERT INTO BuffInfo (user_id) VALUES (?)", (user_id,))
            self.conn.commit()
            return {"success": True, "message": f"欢迎进入修仙世界，你的灵根为：{root}，类型是：{root_type}，你的战力为：{int(power)}，当前境界：江湖好手"}
        except Exception as e:
            logger.error(f"创建用户失败: {e}")
            return {"success": False, "message": "系统错误，创建角色失败！"}

    def get_sign(self, user_id: str) -> dict:
        """处理用户签到，返回结果字典"""
        user = self.get_user_message(user_id)
        if not user:
            return {'success': False, 'message': '修仙界没有你的足迹，输入【我要修仙】加入修仙世界吧！'}
        
        if user.is_sign == 1:
            return {'success': False, 'message': '贪心的人是不会有好运的！'}
            
        ls = random.randint(self.xiu_config.sign_in_lingshi_lower_limit, self.xiu_config.sign_in_lingshi_upper_limit)
        exp = random.randint(self.xiu_config.sign_in_xiuwei_lower_limit, self.xiu_config.sign_in_xiuwei_upper_limit)
        
        try:
            c = self.conn.cursor()
            c.execute("UPDATE user_xiuxian SET is_sign=1, stone=stone+?, exp=exp+? WHERE user_id=?", (ls, exp, user_id))
            self.conn.commit()
            self.update_power2(user_id)
            return {'success': True, 'message': f'签到成功，获取{ls}块灵石, 修为增加{exp}！'}
        except Exception as e:
            logger.error(f"签到失败: {e}")
            return {'success': False, 'message': '签到失败，请联系管理员。'}

    def update_ls(self, user_id: str, amount: int, mode: int):
        """更新灵石, 1为增加, 2为减少"""
        c = self.conn.cursor()
        if mode == 1:
            c.execute("UPDATE user_xiuxian SET stone=stone+? WHERE user_id=?", (amount, user_id))
        elif mode == 2:
            c.execute("UPDATE user_xiuxian SET stone=stone-? WHERE user_id=?", (amount, user_id))
        self.conn.commit()
        
    def update_exp(self, user_id: str, amount: int):
        """增加修为"""
        c = self.conn.cursor()
        c.execute("UPDATE user_xiuxian SET exp=exp+? WHERE user_id=?", (amount, user_id))
        self.conn.commit()

    def update_j_exp(self, user_id: str, amount: int):
        """减少修为"""
        c = self.conn.cursor()
        c.execute("UPDATE user_xiuxian SET exp=exp-? WHERE user_id=?", (amount, user_id))
        self.conn.commit()

    def update_user_calculated_power(self, user_id: str):
        """【修正版】获取真实属性并用其计算的战力更新数据库"""
        real_user_info = self.get_user_real_info(user_id)
        if real_user_info and 'power' in real_user_info:
            self._update_user_power_in_db(user_id, real_user_info['power'])
        else:
            logger.error(f"update_user_calculated_power: 无法为用户 {user_id} 更新战力，因无法获取其真实信息。")

    def update_power2(self, user_id: str):
        """【修正版】获取真实属性并用其计算的战力更新数据库"""
        real_user_info = self.get_user_real_info(user_id)
        if real_user_info and 'power' in real_user_info:
            self._update_user_power_in_db(user_id, real_user_info['power'])
        else:
            logger.error(f"update_user_calculated_power: 无法为用户 {user_id} 更新战力，因无法获取其真实信息。")

    def singh_remake(self):
        """重置所有用户签到"""
        c = self.conn.cursor()
        c.execute("UPDATE user_xiuxian SET is_sign=0")
        self.conn.commit()

    def _calculated(self, rate: dict) -> str:
        """根据概率计算，轮盘型"""
        total_rate = sum(rate.values())
        rand_num = random.randint(1, total_rate)
        
        current_sum = 0
        for name, value in rate.items():
            current_sum += value
            if rand_num <= current_sum:
                return name
        return list(rate.keys())[-1]

    # ==================================
# ===== 在 service.py 末尾追加以下代码 =====
# ==================================

    def get_user_buff_info(self, user_id: str) -> BuffInfo | None:
        """获取用户的Buff信息"""
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM BuffInfo WHERE user_id=?", (user_id,))
        result = cur.fetchone()
        if not result:
            return BuffInfo(id=-1, user_id=user_id, main_buff=0, sec_buff=0, 
                            faqi_buff=0, fabao_weapon=0, armor_buff=0, 
                            atk_buff=0, blessed_spot=0, sub_buff=0)

        return BuffInfo(*result) if result and len(result) == len(BuffInfo._fields) else None

    def get_sect_config(self) -> dict:
        """获取宗门配置"""
        return jsondata.sect_config_data()

    def get_boss_config(self) -> dict:
        """获取世界Boss配置"""
        # 在我们的结构中，这部分配置在 XiuConfig 类中管理
        # 我们从 config.py 中读取，而不是直接读json
        return self.xiu_config.boss_config if hasattr(self.xiu_config, 'boss_config') else {}

    def get_all_sects_id_scale(self):
        """获取所有宗门ID和规模"""
        cur = self.conn.cursor()
        cur.execute("SELECT sect_id, sect_scale, sect_owner FROM sects")
        return cur.fetchall()

    def update_sect_materials(self, sect_id, sect_materials, key=1):
        """更新宗门资材"""
        cur = self.conn.cursor()
        if key == 1:
            cur.execute("UPDATE sects SET sect_materials = sect_materials + ? WHERE sect_id = ?", (sect_materials, sect_id))
        else:
            cur.execute("UPDATE sects SET sect_materials = sect_materials - ? WHERE sect_id = ?", (sect_materials, sect_id))
        self.conn.commit()

    #def create_boss(self) -> dict:
    #    """
    #    创建世界boss, 返回boss信息字典
    #    移植自 makeboss.py
    #    """
    #    all_boss_data = jsondata.level_data()
    #    logger.info(all_boss_data)

    #    # 随机选择一个境界作为boss
    #    boss_level = random.choice(list(all_boss_data.keys()))
    #    logger.info(boss_level)
    #    boss_info = all_boss_data[boss_level]
    #    logger.info(boss_info)

    #    hp = int(boss_info['HP']) * random.randint(10, 20)
    #    atk = int(boss_info['ATK']) * random.randint(5, 15)

    #    return {
    #        "name": f"{boss_level}妖兽",
    #        "jj": boss_level, # 境界
    #        "hp": hp,
    #        "atk": atk,
    #        "stone": int(hp / 2),
    #        "exp": int(hp / 5),
    #        "s_bool": False # 是否被击杀
    #    }

    def day_num_reset(self):
        """重置丹药每日使用次数"""
        cur = self.conn.cursor()
        cur.execute("UPDATE back SET day_num = 0 WHERE goods_type = '丹药'")
        self.conn.commit()

    def sect_task_reset(self):
        """重置宗门任务次数"""
        cur = self.conn.cursor()
        cur.execute("UPDATE user_xiuxian SET sect_task = 0")
        self.conn.commit()

    def sect_elixir_get_num_reset(self):
        """重置宗门丹药每日领取次数"""
        cur = self.conn.cursor()
        cur.execute("UPDATE user_xiuxian SET sect_elixir_get = 0")
        self.conn.commit()
    # ==================================
# === 在 service.py 末尾追加修炼功能相关方法 ===
# ==================================

    def get_user_cd(self, user_id: str) -> list[UserCd]:
        """获取一个用户所有的CD信息记录，返回一个列表"""
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM user_cd WHERE user_id = ?", (user_id,))
        results = cur.fetchall()
        return [UserCd(*row) for row in results]

    def start_closing(self, user_id: str, close_time: str) -> None:
        """开始闭关 (type=1)"""
        # 使用一个超长的CD代表状态，并记录开始时间
        self._set_user_cd(user_id, 1, 999999)
        cur = self.conn.cursor()
        cur.execute("UPDATE user_cd SET create_time = ? WHERE user_id = ? and type = 1", (close_time, user_id))
        self.conn.commit()

    def end_closing(self, user_id: str) -> None:
        """结束闭关，通过删除记录实现"""
        self._delete_user_cd_by_type(user_id, 1)

    def get_closing_info(self, user_id: str) -> UserCd | None:
        """
        【新增】精确获取闭关状态信息 (type=1)
        """
        return self._get_user_cd_by_type(user_id, 1)

    def update_level(self, user_id: str, level: str) -> None:
        """更新用户境界"""
        cur = self.conn.cursor()
        cur.execute("UPDATE user_xiuxian SET level = ? WHERE user_id = ?", (level, user_id))
        self.conn.commit()

    def update_level_up_cd(self, user_id: str, time: str) -> None:
        """更新突破CD"""
        cur = self.conn.cursor()
        cur.execute("UPDATE user_xiuxian SET level_up_cd = ? WHERE user_id = ?", (time, user_id))
        self.conn.commit()

    # ==================================
# === 在 service.py 末尾追加背包功能相关方法 ===
# ==================================

    def get_user_back_msg(self, user_id: str) -> list[BackpackItem]:
        """获取用户背包内的所有物品"""
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM back WHERE user_id=? AND goods_num > 0", (user_id,))
        items = cur.fetchall()
        return [BackpackItem(*item) for item in items]

    def get_item_by_name(self, user_id: str, item_name: str) -> BackpackItem | None:
        """根据物品名称获取用户背包内的特定物品"""
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM back WHERE user_id=? AND goods_name=?", (user_id, item_name))
        item = cur.fetchone()
        if item:
            return BackpackItem(*item)
        return None

    def add_item(self, user_id: str, item_id: int, item_type: str, item_num: int = 1):
        """为用户添加物品"""
        logger.info(user_id + " " + str(item_id) + " " + item_type)
        item_info = self.items.get_data_by_item_id(item_id)
        if not item_info:
            logger.error(f"尝试添加不存在的物品ID: {item_id}")
            return

        item_name = item_info.get('name')

        # 检查背包中是否已有该物品
        user_item = self.get_item_by_name(user_id, item_name)

        cur = self.conn.cursor()
        if user_item:
            # 已有，更新数量
            cur.execute("UPDATE back SET goods_num = goods_num + ? WHERE user_id = ? AND goods_name = ?", (item_num, user_id, item_name))
        else:
            # 没有，插入新纪录
            cur.execute(
                "INSERT INTO back (user_id, goods_id, goods_name, goods_type, goods_num, create_time, update_time) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (user_id, item_id, item_name, item_type, item_num, str(datetime.now()), str(datetime.now()))
            )
        self.conn.commit()

    def remove_item(self, user_id: str, item_name: str, item_num: int = 1) -> bool:
        """从用户背包移除物品"""
        user_item = self.get_item_by_name(user_id, item_name)
        if not user_item or user_item.goods_num < item_num:
            return False # 物品不存在或数量不足

        cur = self.conn.cursor()
        cur.execute("UPDATE back SET goods_num = goods_num - ? WHERE user_id = ? AND goods_name = ?", (item_num, user_id, item_name))
        self.conn.commit()
        return True

    def get_user_real_info(self, user_id: str) -> dict | None:
        """
        【新版】根据ID获取用户增益后的最终真实信息，返回一个字典。
        核心属性现在由“境界基准”+“装备/功法增益”决定。
        """
        user_info = self.get_user_message(user_id)
        if not user_info:
            return None

        buff_info = self.get_user_buff_info(user_id)
        if not buff_info:
            # 如果没有buff信息，创建一个临时的空buff对象
            from .service import BuffInfo
            buff_info = BuffInfo(id=0, user_id=user_id, main_buff=0, sec_buff=0, faqi_buff=0, fabao_weapon=0, armor_buff=0, atk_buff=0, blessed_spot=0, sub_buff=0)

        # 0. 初始化返回的字典结构，确保所有键都存在
        real_info = {
            "user_id": user_info.user_id,
            "user_name": user_info.user_name,
            "level": user_info.level,
            "root": user_info.root,
            "root_type": user_info.root_type,
            "exp": user_info.exp,
            "stone": user_info.stone,
            "hp": user_info.hp, # 当前HP，后续会被最大HP限制
            "mp": user_info.mp, # 当前MP，后续会被最大MP限制
            "max_hp": 0,
            "max_mp": 0,
            "atk": 0,
            "crit_rate": 0.0,       # 暴击率 (百分比，例如 0.05 代表 5%)
            "crit_damage": 0.0,   # 暴击伤害加成 (百分比，例如 0.5 代表额外50%伤害)
            "defense_rate": 0.0,  # 减伤率 (百分比，例如 0.1 代表减伤10%)
            "power": user_info.power, # 战力后续会重新计算
            "final_exp_rate": 1.0, # 修炼效率
            "buff_info": buff_info, # 原始buff信息，供其他地方使用
            "atk_practice_level": getattr(user_info, 'atkpractice', 0) # 攻击修炼等级
        }

        # 1. 获取境界基准属性
        level_config = self.jsondata.level_data().get(user_info.level, {})
        logger.info(level_config)
        #base_hp = level_config.get("HP", 50)
        #base_mp = level_config.get("MP", 100)
        #base_atk = level_config.get("ATK", 10)
        base_hp = level_config.get("HP", user_info.exp / 2 if user_info.exp > 0 else 50) # 以修为一半为基础或默认50
        base_mp = level_config.get("MP", user_info.exp if user_info.exp > 0 else 100)     # 以修为为基础或默认100
        base_atk = level_config.get("ATK", user_info.exp / 10 if user_info.exp > 0 else 10)   # 以修为十分之一为基础或默认10

        # 2. 初始化百分比增益率和固定增益值
        hp_buff_rate_total = 0.0
        mp_buff_rate_total = 0.0
        atk_buff_rate_total = 0.0
        crit_rate_buff_total = 0.0      # 初始暴击率
        crit_damage_buff_total = 0.0  # 初始暴击伤害加成 (例如基础暴击是150%伤害，这里存0.5)
        defense_rate_total = 0.0      # 初始减伤率

        fixed_atk_buff_total = buff_info.atk_buff if buff_info else 0 # 来自丹药等的永久攻击力

        # 2. 获取功法和装备的增益
        items_manager = self.items

        # 主修功法
        main_buff_info = items_manager.get_data_by_item_id(buff_info.main_buff) if buff_info else None
        if main_buff_info:
            hp_buff_rate_total += main_buff_info.get("hpbuff", 0)
            mp_buff_rate_total += main_buff_info.get("mpbuff", 0)
            atk_buff_rate_total += main_buff_info.get("atkbuff", 0)

        # 辅修功法
        sub_buff_info = items_manager.get_data_by_item_id(buff_info.sub_buff) if buff_info else None
        if sub_buff_info:
            sub_buff_type = sub_buff_info.get("buff_type")
            sub_buff_value = float(sub_buff_info.get("buff", 0)) / 100 # 原版是存的百分比整数
            if sub_buff_type == '1': # 攻击力百分比
                atk_buff_rate_total += sub_buff_value
            elif sub_buff_type == '2': # 暴击率百分比
                crit_rate_buff_total += sub_buff_value
            elif sub_buff_type == '3': # 暴击伤害百分比
                crit_damage_buff_total += sub_buff_value

         # 武器 (法器)
        weapon_info = items_manager.get_data_by_item_id(buff_info.fabao_weapon) if buff_info else None # fabao_weapon 对应原版的法器
        if weapon_info:
            atk_buff_rate_total += weapon_info.get("atk_buff", 0)
            crit_rate_buff_total += weapon_info.get("crit_buff", 0)

        # 防具
        armor_info = items_manager.get_data_by_item_id(buff_info.armor_buff) if buff_info else None
        if armor_info:
            defense_rate_total += armor_info.get("def_buff", 0)

        # 攻击修炼
        # 原版是每级4%攻击力，你的 XiuConfig 中是否有类似配置？
        # 假设每级 atkpractice 提升 XiuConfig().atk_practice_buff_per_level (例如 0.04)
        atk_practice_buff_rate = getattr(user_info, 'atkpractice', 0) * self.xiu_config.atk_practice_buff_per_level
        atk_buff_rate_total += atk_practice_buff_rate

        # 4. 计算最终属性
        # 最大生命值
        real_info['max_hp'] = int(base_hp * (1 + hp_buff_rate_total))
        # 最大真元
        real_info['max_mp'] = int(base_mp * (1 + mp_buff_rate_total))
        # 攻击力
        real_info['atk'] = int(base_atk * (1 + atk_buff_rate_total)) + fixed_atk_buff_total

        # 确保当前血量不超过最大血量
        real_info['hp'] = min(user_info.hp if user_info.hp is not None else real_info['max_hp'], real_info['max_hp'])
        if real_info['hp'] <= 0 and real_info['max_hp'] > 0 : # 如果血量为0但最大血量大于0，则置为1（防止战斗问题）
            real_info['hp'] = 1

        # 确保当前蓝量不超过最大蓝量
        real_info['mp'] = min(user_info.mp if user_info.mp is not None else real_info['max_mp'], real_info['max_mp'])

        # 其他属性
        real_info['crit_rate'] = round(crit_rate_buff_total, 4)
        real_info['crit_damage'] = round(crit_damage_buff_total, 4) # 例如，0.5 表示暴击时造成 100% + 50% = 150% 伤害
        real_info['defense_rate'] = round(defense_rate_total, 4)

        # 计算修炼效率
        main_rate_buff = main_buff_info.get("ratebuff", 0) if main_buff_info else 0
        realm_rate = level_config.get("spend", 1.0)
        root_rate = self.jsondata.root_data().get(user_info.root_type, {}).get("type_speeds", 1.0)

        reincarnation_buff_rate = user_info.reincarnation_buff if hasattr(user_info, 'reincarnation_buff') else 0.0
        blessed_spot_rate = getattr(buff_info, 'blessed_spot', 0) # 这个是等级，需要转换成倍率
        # 假设 blessed_spot 等级1对应 0.1 (10%) 的倍率加成
        blessed_spot_multiplier = blessed_spot_rate * self.xiu_config.blessed_spot_exp_rate_per_level

        logger.info(str(realm_rate) + " " + str(root_rate) + " " + str(main_rate_buff) + " " + str(reincarnation_buff_rate) + " " + str(blessed_spot_multiplier))
        real_info['final_exp_rate'] = realm_rate * root_rate * (1 + main_rate_buff + reincarnation_buff_rate + blessed_spot_multiplier)
        # 6. 更新战力 (复用你的 update_power2 逻辑，但传入的是已计算好的属性)
        # 战力计算应该在所有属性都确定后再进行，确保它基于的是最终的面板属性
        # 暂时注释掉，因为你的 update_power2 内部会再次调用 get_user_real_info，可能导致循环或不一致
        # self.update_power2(user_id) # 或者在这里直接计算并更新 real_info['power']

        # 重新计算战力，基于最终面板
        # 这些权重可以根据你的游戏平衡性进行调整
        hp_weight = 0.5  # 每点最大生命值提供 0.5 点战力
        mp_weight = 0.2  # 每点最大真元提供 0.2 点战力
        atk_weight = 10    # 每点攻击力提供 10 点战力
        # 也可以考虑将暴击、爆伤、减伤等属性也纳入战力计算

        calculated_power = int(
            (real_info['max_hp'] * hp_weight) +
            (real_info['max_mp'] * mp_weight) +
            (real_info['atk'] * atk_weight)
        )
        real_info['power'] = calculated_power

        return real_info

    # 你可能需要一个单独的方法来更新数据库中的战力，如果战力是持久化的
    def _update_user_power_in_db(self, user_id: str, power: int):
        """内部方法：仅更新数据库中的用户战力字段"""
        try:
            c = self.conn.cursor()
            c.execute("UPDATE user_xiuxian SET power=? WHERE user_id=?", (power, user_id))
            self.conn.commit()
        except Exception as e:
            logger.error(f"_update_user_power_in_db: 更新用户 {user_id} 战力失败: {e}")


    def equip_item(self, user_id: str, item_id: int) -> dict:
        """为用户穿戴装备"""
        item_info = self.items.get_data_by_item_id(item_id)
        if not item_info:
            return {"success": False, "message": "不存在的物品！"}

        item_type = item_info.get("item_type")
        if item_type not in ["法器", "防具"]:
            return {"success": False, "message": "这个物品好像不能被穿戴哦！"}

        # 检查是否已穿戴同类型装备
        buff_info = self.get_user_buff_info(user_id)
        slot_occupied = False
        if item_type == "法器" and buff_info.fabao_weapon != 0:
            slot_occupied = True
        elif item_type == "防具" and buff_info.armor_buff != 0:
            slot_occupied = True

        if slot_occupied:
            return {"success": False, "message": f"道友已经穿戴着{item_type}了，请先卸下再穿！"}

        # 扣除背包物品并更新Buff表
        if not self.remove_item(user_id, item_info['name'], 1):
            return {"success": False, "message": f"背包中没有{item_info['name']}！"}

        cur = self.conn.cursor()
        if item_type == "法器":
            slot_to_update = "fabao_weapon"
        elif item_type == "防具":
            slot_to_update = "armor_buff"
        # 使用参数化查询防止SQL注入
        cur.execute(f"UPDATE BuffInfo SET {slot_to_update} = ? WHERE user_id = ?", (item_id, user_id))
        
        # 确保 BuffInfo 表中确实有该用户的记录，如果没有（极少情况），插入一条
        if cur.rowcount == 0: # 如果 UPDATE 没有影响任何行
            logger.warning(f"BuffInfo表中未找到用户 {user_id} 的记录，尝试插入新记录并装备。")
            # 插入一条全0的记录，然后只更新要装备的槽位
            cur.execute("""
                INSERT OR IGNORE INTO BuffInfo 
                (user_id, main_buff, sec_buff, faqi_buff, fabao_weapon, armor_buff, atk_buff, blessed_spot, sub_buff) 
                VALUES (?, 0, 0, 0, 0, 0, 0, 0, 0)
                """, (user_id,)) # faqi_buff 是旧字段名，可能你的表里已经没有了
            cur.execute(f"UPDATE BuffInfo SET {slot_to_update} = ? WHERE user_id = ?", (item_id, user_id))
        self.conn.commit()

        return {"success": True, "message": f"成功穿戴 {item_info['name']}！"}

    def unequip_item(self, user_id: str, item_type_str: str) -> dict:
        """为用户卸下装备"""
        if item_type_str not in ["法器", "防具", "武器", "神通", "功法", "辅修功法"]: # 兼容"武器"的叫法
             return {"success": False, "message": "只能卸下【法器】或【防具】！"}

        buff_info = self.get_user_buff_info(user_id)
        item_to_unequip_id = 0

        if item_type_str in ["法器", "武器"]:
            item_to_unequip_id = buff_info.fabao_weapon
            slot_name = "fabao_weapon"
            item_type_for_add = "法器"
        elif item_type_str == "神通":
            item_to_unequip_id = buff_info.sec_buff
            slot_name = "sec_buff"
            item_type_for_add = "神通"
        elif item_type_str == "功法":
            item_to_unequip_id = buff_info.main_buff
            slot_name = "main_buff"
            item_type_for_add = "功法"
        elif item_type_str == "辅修功法":
            item_to_unequip_id = buff_info.sub_buff
            slot_name = "sub_buff"
            item_type_for_add = "辅修功法"
        else: # 防具
            item_to_unequip_id = buff_info.armor_buff
            slot_name = "armor_buff"
            item_type_for_add = "防具"

        if item_to_unequip_id == 0:
            return {"success": False, "message": f"道友当前没有穿戴{item_type_str}！"}

        # 归还物品到背包并清空buff表
        self.add_item(user_id, item_to_unequip_id, item_type_for_add, 1)

        cur = self.conn.cursor()
        cur.execute(f"UPDATE BuffInfo SET {slot_name} = 0 WHERE user_id = ?", (user_id,))
        self.conn.commit()

        item_info = self.items.get_data_by_item_id(item_to_unequip_id)
        return {"success": True, "message": f"成功卸下 {item_info['name']}！"}

    def get_sect_info_by_id(self, sect_id: int) -> SectInfo | None:
        """根据宗门ID获取宗门信息"""
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM sects WHERE sect_id=?", (sect_id,))
        result = cur.fetchone()
        return SectInfo(*result) if result and len(result) == len(SectInfo._fields) else None

    def get_sect_info_by_name(self, sect_name: str) -> SectInfo | None:
        """根据宗门名称获取宗门信息"""
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM sects WHERE sect_name=?", (sect_name,))
        result = cur.fetchone()
        return SectInfo(*result) if result and len(result) == len(SectInfo._fields) else None

    def get_all_sects(self) -> list[SectInfo]:
        """获取所有宗门信息"""
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM sects")
        results = cur.fetchall()
        return [SectInfo(*row) for row in results]

    def get_sect_member_count(self, sect_id: int) -> int:
        """获取宗门当前成员人数"""
        cur = self.conn.cursor()
        cur.execute("SELECT count(*) FROM user_xiuxian WHERE sect_id=?", (sect_id,))
        return cur.fetchone()[0]

    def create_sect(self, user_id: str, sect_name: str) -> dict:
        """创建宗门"""
        user_info = self.get_user_message(user_id)
        config = self.xiu_config

        # 前置条件检查
        if user_info.sect_id != 0:
            return {"success": False, "message": "道友已经身在宗门，无法另立门户！"}
        if self.get_sect_info_by_name(sect_name):
            return {"success": False, "message": f"仙界已存在名为【{sect_name}】的宗门！"}
        if USERRANK[user_info.level] > USERRANK[config.sect_min_level]:
            return {"success": False, "message": f"创建宗门需要达到【{config.sect_min_level}】境界！"}
        if user_info.stone < config.sect_create_cost:
            return {"success": False, "message": f"创建宗门需要花费 {config.sect_create_cost} 灵石，道友的灵石不足！"}

        # 执行创建
        try:
            cur = self.conn.cursor()
            # 扣除灵石
            self.update_ls(user_id, config.sect_create_cost, 2)
            # 创建宗门
            cur.execute("INSERT INTO sects (sect_name, sect_owner, sect_scale, sect_used_stone) VALUES (?, ?, ?, ?)",
                        (sect_name, user_id, 1, config.sect_create_cost))
            new_sect_id = cur.lastrowid
            # 更新用户宗门信息
            cur.execute("UPDATE user_xiuxian SET sect_id = ?, sect_position = ? WHERE user_id = ?",
                        (new_sect_id, 4, user_id)) # 4代表宗主
            self.conn.commit()
            return {"success": True, "message": f"恭喜道友成功创建宗门【{sect_name}】，广纳门徒，开创万世基业！"}
        except Exception as e:
            logger.error(f"创建宗门失败: {e}")
            return {"success": False, "message": "系统错误，创建宗门失败！"}

    def join_sect(self, user_id: str, sect_id: int) -> dict:
        """加入宗门"""
        user_info = self.get_user_message(user_id)
        if user_info.sect_id != 0:
            return {"success": False, "message": "道友已经身在宗门，请先退出宗门！"}

        sect_info = self.get_sect_info_by_id(sect_id)
        if not sect_info:
            return {"success": False, "message": "该宗门不存在！"}

        member_count = self.get_sect_member_count(sect_id)
        if member_count >= sect_info.sect_scale * 10: # 宗门规模*10为人数上限
            return {"success": False, "message": "宗门人数已达上限，无法加入！"}

        try:
            cur = self.conn.cursor()
            cur.execute("UPDATE user_xiuxian SET sect_id = ?, sect_position = ? WHERE user_id = ?",
                        (sect_id, 0, user_id)) # 0代表弟子
            self.conn.commit()
            return {"success": True, "message": f"道友成功加入【{sect_info.sect_name}】！"}
        except Exception as e:
            logger.error(f"加入宗门失败: {e}")
            return {"success": False, "message": "系统错误，加入宗门失败！"}

    def leave_sect(self, user_id: str) -> dict:
        """退出宗门"""
        user_info = self.get_user_message(user_id)
        if user_info.sect_id == 0:
            return {"success": False, "message": "道友尚未加入任何宗门！"}
        if user_info.sect_position == 4: # 宗主
            return {"success": False, "message": "宗主无法退出宗门，请先寻找继承人或解散宗门（暂未开放）！"}

        try:
            cur = self.conn.cursor()
            cur.execute("UPDATE user_xiuxian SET sect_id = 0, sect_position = 0, sect_contribution = 0 WHERE user_id = ?",
                        (user_id,))
            self.conn.commit()
            return {"success": True, "message": "道友已成功退出宗门，从此逍遥于天地之间。"}
        except Exception as e:
            logger.error(f"退出宗门失败: {e}")
            return {"success": False, "message": "系统错误，退出宗门失败！"}


    def set_user_cd(self, user_id: str, cd_time_minutes: int, cd_type: int = 2) -> None:
        """
        设置用户CD
        :param user_id: 用户ID
        :param cd_time_minutes: CD时长（分钟）
        :param cd_type: 2代表世界BOSS攻击CD
        """
        cur = self.conn.cursor()
        create_time = datetime.now()
        # scheduled_time 在这里可以理解为CD的结束时间
        scheduled_time = create_time + timedelta(minutes=cd_time_minutes)

        # 检查user_cd表中是否已有该用户的记录
        cur.execute("SELECT user_id FROM user_cd WHERE user_id = ?", (user_id,))
        if cur.fetchone():
            cur.execute(
                "UPDATE user_cd SET type = ?, create_time = ?, scheduled_time = ? WHERE user_id = ?",
                (cd_type, str(create_time), str(scheduled_time), user_id)
            )
        else:
            cur.execute(
                "INSERT INTO user_cd (user_id, type, create_time, scheduled_time) VALUES (?, ?, ?, ?)",
                (user_id, cd_type, str(create_time), str(scheduled_time))
            )
        self.conn.commit()

    def check_user_cd(self, user_id: str) -> int:
        """检查用户BOSS战CD (type=2)，返回剩余秒数"""
        cd_info = self._get_user_cd_by_type(user_id, 2)
        if cd_info and cd_info.scheduled_time:
            end_time = datetime.fromisoformat(cd_info.scheduled_time)
            if datetime.now() < end_time:
                return int((end_time - datetime.now()).total_seconds())
        return 0

    def get_user_bounty(self, user_id: str) -> dict | None:
        """获取用户当前接取的悬赏任务"""
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM user_bounty WHERE user_id=?", (user_id,))
        result = cur.fetchone()
        if not result:
            return None

        # 将元组转换为字典
        columns = [desc[0] for desc in cur.description]
        return dict(zip(columns, result))

    def accept_bounty(self, user_id: str, bounty: dict) -> None:
        """接取悬赏任务"""
        cur = self.conn.cursor()
        # v-- 完整替换这里的SQL和参数 --v
        cur.execute(
            "INSERT INTO user_bounty (user_id, bounty_id, bounty_name, bounty_type, monster_name, monster_hp, monster_atk, item_name, item_id, item_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, bounty['id'], bounty['name'], bounty['type'],
             bounty.get('monster_name'),
             bounty.get('monster_hp'),
             bounty.get('monster_atk'), # <-- 新增
             bounty.get('item_name'),
             bounty.get('item_id'),
             bounty.get('item_count'))
        )
        # ^-- 替换结束 --^
        self.conn.commit()

    def abandon_bounty(self, user_id: str) -> None:
        """放弃/完成悬赏任务"""
        cur = self.conn.cursor()
        cur.execute("DELETE FROM user_bounty WHERE user_id = ?", (user_id,))
        self.conn.commit()

    def update_bounty_monster_hp(self, user_id: str, damage: int) -> int:
        """
        更新悬赏任务中怪物的HP，并返回剩余HP
        """
        cur = self.conn.cursor()

        # v-- 这是本次修正的核心：使用 COALESCE 函数防止 NULL 值问题 --v
        # COALESCE(monster_hp, 0) 的意思是：如果 monster_hp 不是 NULL，就用它的值；如果是 NULL，就用 0 代替。
        cur.execute(
            "UPDATE user_bounty SET monster_hp = COALESCE(monster_hp, 0) - ? WHERE user_id = ?",
            (damage, user_id)
        )
        # ^-- 这是本次修正的核心 --^

        self.conn.commit()

        cur.execute("SELECT monster_hp FROM user_bounty WHERE user_id=?", (user_id,))
        result = cur.fetchone()

        # 添加一个额外的安全检查
        remaining_hp = result[0] if result and result[0] is not None else 0
        return remaining_hp

    def get_bounty_reward(self, bounty: dict) -> dict:
        """
        根据悬赏令信息，随机生成奖励
        移植自 reward_data_source.py
        """
        reward_type = bounty.get("reward_type")
        if not reward_type:
            return {"exp": 100, "stone": 100} # 默认奖励

        exp = random.randint(reward_type['exp_min'], reward_type['exp_max'])
        stone = random.randint(reward_type['stone_min'], reward_type['stone_max'])

        return {"exp": exp, "stone": stone}

    # ==================================
# === 在 service.py 末尾追加秘境相关方法 ===
# ==================================

    def get_user_rift(self, user_id: str) -> dict | None:
        """获取用户的秘境信息"""
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM user_rift WHERE user_id=?", (user_id,))
        result = cur.fetchone()
        if not result:
            return None

        columns = [desc[0] for desc in cur.description]
        rift_data = dict(zip(columns, result))
        rift_data['rift_map'] = json.loads(rift_data['rift_map']) # 将json字符串转回list
        return rift_data

    def create_user_rift(self, user_id: str, rift_data: dict) -> None:
        """为用户创建秘境存档"""
        cur = self.conn.cursor()
        rift_map_str = json.dumps(rift_data['map']) # 将list转为json字符串存储
        cur.execute(
            "INSERT INTO user_rift (user_id, rift_name, rift_map) VALUES (?, ?, ?)",
            (user_id, rift_data['name'], rift_map_str)
        )
        self.conn.commit()

    def delete_user_rift(self, user_id: str) -> None:
        """删除用户的秘境存档"""
        cur = self.conn.cursor()
        cur.execute("DELETE FROM user_rift WHERE user_id=?", (user_id,))
        self.conn.commit()
    # ==================================
# === 在 service.py 末尾追加秘境进度更新方法 ===
# ==================================

    def update_user_rift(self, user_id: str, new_floor: int, new_map_str: str):
        """更新用户的秘境存档"""
        cur = self.conn.cursor()
        cur.execute(
            "UPDATE user_rift SET current_floor = ?, rift_map = ? WHERE user_id = ?",
            (new_floor, new_map_str, user_id)
        )
        self.conn.commit()

    # ==================================
# === 在 service.py 末尾追加功法系统相关方法 ===
# ==================================

    def set_user_buff(self, user_id: str, buff_type: str, item_id: int) -> bool:
        """
        通用方法：为用户装备或卸下功法/神通
        :param user_id: 用户ID
        :param buff_type: 'main_buff' 或 'sec_buff' 或 'sub_buff'
        :param item_id: 物品ID, 传 0 代表卸下
        """
        valid_buff_types = ['main_buff', 'sec_buff', 'sub_buff']
        if buff_type not in valid_buff_types:
            logger.error(f"无效的Buff类型: {buff_type}")
            return False

        try:
            cur = self.conn.cursor()
            # 使用 f-string 来动态构建列名，确保 buff_type 来自受信任的来源（我们自己的代码）
            cur.execute(f"UPDATE BuffInfo SET {buff_type} = ? WHERE user_id = ?", (item_id, user_id))
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"更新Buff失败: {e}")
            return False

    def remake_user_root(self, user_id: str) -> dict:
        """
        为用户重置灵根
        """
        user_info = self.get_user_message(user_id)
        if not user_info:
            return {"success": False, "message": "未找到用户信息。"}

        cost = self.xiu_config.remake
        if user_info.stone < cost:
            return {"success": False, "message": f"重入仙途需要花费 {cost} 灵石，道友的灵石不足！"}

        # 扣除灵石
        self.update_ls(user_id, cost, 2)

        # 重新生成灵根
        linggen_data = jsondata.root_data()
        rate_dict = {i: v["type_rate"] for i, v in linggen_data.items()}
        root_type = self._calculated(rate_dict)

        if linggen_data[root_type]["type_flag"]:
            flag = random.choice(linggen_data[root_type]["type_flag"])
            root_list = random.sample(linggen_data[root_type]["type_list"], flag)
            root = "、".join(root_list) + '属性灵根'
        else:
            root = random.choice(linggen_data[root_type]["type_list"])

        # 更新数据库
        cur = self.conn.cursor()
        cur.execute("UPDATE user_xiuxian SET root = ?, root_type = ? WHERE user_id = ?", (root, root_type, user_id))
        self.conn.commit()

        # 更新战力
        self.update_power2(user_id)

        new_user_info = self.get_user_message(user_id)
        return {
            "success": True,
            "message": f"道友重入仙途成功！新的灵根为【{root}】，当前战力已更新为 {int(new_user_info.power)}！"
        }

    def update_user_name(self, user_id: str, new_name: str) -> None:
        """更新用户名"""
        cur = self.conn.cursor()
        cur.execute("UPDATE user_xiuxian SET user_name = ? WHERE user_id = ?", (new_name, user_id))
        self.conn.commit()

    # ==================================
# === 在 service.py 末尾追加PVP与灵庄相关方法 ===
# ==================================

    def get_bank_info(self, user_id: str) -> dict | None:
        """获取用户灵庄存款"""
        # 我们复用 user_cd 表来存储存款，这是一种简化设计
        # type 为 3 代表灵庄存款
        cur = self.conn.cursor()
        cur.execute("SELECT scheduled_time FROM user_cd WHERE user_id=? AND type=3", (user_id,))
        result = cur.fetchone()
        if result:
            return {"savings": int(result[0])}
        return {"savings": 0}

    def update_bank_savings(self, user_id: str, amount: int) -> None:
        """更新用户灵庄存款"""
        cur = self.conn.cursor()
        # 检查记录是否存在
        cur.execute("SELECT user_id FROM user_cd WHERE user_id=? AND type=3", (user_id,))
        if cur.fetchone():
            cur.execute("UPDATE user_cd SET scheduled_time = ? WHERE user_id = ? AND type=3", (str(amount), user_id))
        else:
            cur.execute("INSERT INTO user_cd (user_id, type, scheduled_time) VALUES (?, 3, ?)", (user_id, str(amount)))
        self.conn.commit()

    def get_user_hp(self, user_id: str) -> int:
        """快速获取用户当前HP"""
        cur = self.conn.cursor()
        cur.execute("SELECT hp FROM user_xiuxian WHERE user_id=?", (user_id,))
        result = cur.fetchone()
        return result[0] if result else 0

    # ==================================
# === 在 service.py 末尾追加排行榜相关方法 ===
# ==================================

    def get_exp_ranking(self, limit: int = 10) -> list:
        """获取修为排行榜"""
        cur = self.conn.cursor()
        cur.execute(
            "SELECT user_name, level, exp FROM user_xiuxian ORDER BY exp DESC LIMIT ?",
            (limit,)
        )
        return cur.fetchall()

    def get_stone_ranking(self, limit: int = 10) -> list:
        """获取灵石排行榜"""
        cur = self.conn.cursor()
        cur.execute(
            "SELECT user_name, level, stone FROM user_xiuxian ORDER BY stone DESC LIMIT ?",
            (limit,)
        )
        return cur.fetchall()

    def get_power_ranking(self, limit: int = 10) -> list:
        """获取战力排行榜"""
        cur = self.conn.cursor()
        cur.execute(
            "SELECT user_name, level, power FROM user_xiuxian ORDER BY power DESC LIMIT ?",
            (limit,)
        )
        return cur.fetchall()
    # ==================================
# === 在 service.py 末尾追加抢劫相关方法 ===
# ==================================

    def update_wanted_status(self, user_id: str, amount: int):
        """更新通缉状态"""
        cur = self.conn.cursor()
        cur.execute("UPDATE user_xiuxian SET wanted_status = wanted_status + ? WHERE user_id = ?", (amount, user_id))
        self.conn.commit()

    # ==================================
# === 在 service.py 末尾追加数据清理方法 ===
# ==================================

    def reset_user_sect_info(self, user_id: str):
        """
        重置用户的宗门信息，用于处理数据不一致的情况
        """
        cur = self.conn.cursor()
        cur.execute(
            "UPDATE user_xiuxian SET sect_id = 0, sect_position = 0, sect_contribution = 0 WHERE user_id = ?",
            (user_id,)
        )
        self.conn.commit()
    def set_remake_cd(self, user_id: str):
        """
        设置用户重入仙途CD，30分钟
        现在调用通用的 _set_user_cd 方法。
        """
        # type=4 代表重入仙途的CD
        self._set_user_cd(user_id, 4, 30)

    def check_remake_cd(self, user_id: str) -> int:
        """
        检查用户重入仙途CD
        :return: 剩余秒数
        """
        # 精确查询 type=4 的CD记录
        cd_info = self._get_user_cd_by_type(user_id, 4)
        if cd_info and cd_info.scheduled_time:
            try:
                end_time = datetime.fromisoformat(cd_info.scheduled_time)
                if datetime.now() < end_time:
                    return int((end_time - datetime.now()).total_seconds())
            except (ValueError, TypeError):
                return 0 # 时间格式错误，视为无CD
        return 0

    def update_hp(self, user_id: str, amount: int, mode: int = 1):
        """
        更新用户HP，并防止超出上限
        :param user_id: 用户ID
        :param amount: 数值
        :param mode: 1为增加, 2为减少
        """
        user_real_info = self.get_user_real_info(user_id)
        if not user_real_info:
            return

        cur = self.conn.cursor()
        current_hp = user_real_info['hp']

        if mode == 1: # 增加生命值
            max_hp = user_real_info['max_hp']
            new_hp = min(current_hp + amount, max_hp) # 确保不会超过最大生命值
            cur.execute("UPDATE user_xiuxian SET hp = ? WHERE user_id = ?", (new_hp, user_id))
        else: # 减少生命值
            cur.execute("UPDATE user_xiuxian SET hp = hp - ? WHERE user_id = ?", (amount, user_id))

        self.conn.commit()

    def update_mp(self, user_id: str, amount: int, mode: int = 1):
        """
        更新用户MP，并防止超出上限
        :param user_id: 用户ID
        :param amount: 数值
        :param mode: 1为增加, 2为减少
        """
        user_real_info = self.get_user_real_info(user_id)
        if not user_real_info:
            return

        cur = self.conn.cursor()
        current_mp = user_real_info['mp']

        if mode == 1: # 增加生命值
            max_mp = user_real_info['max_mp']
            new_mp = min(current_mp + amount, max_mp) # 确保不会超过最大生命值
            cur.execute("UPDATE user_xiuxian SET mp = ? WHERE user_id = ?", (new_mp, user_id))
        else: # 减少生命值
            cur.execute("UPDATE user_xiuxian SET mp = mp - ? WHERE user_id = ?", (amount, user_id))

        self.conn.commit()

    def spawn_new_boss(self, boss_info: dict) -> int | None:
        """
        【最终修正版】在数据库中生成一个全局BOSS，会先清空旧的BOSS。
        :param boss_info: 包含所有BOSS属性的字典，与 create_boss 返回的结构一致。
        :return: 新BOSS在数据库中的主键ID，如果失败则返回None。
        """
        if not all(k in boss_info for k in ['name', 'jj', 'hp', 'max_hp', 'exp', 'stone', 'atk']):
            logger.error(f"spawn_new_boss: 传入的 boss_info 字典缺少必要的键: {boss_info}")
            return None

        try:
            cur = self.conn.cursor()
            # 先清空可能存在的旧BOSS
            cur.execute("DELETE FROM world_boss")

            # 插入新的BOSS数据
            cur.execute(
                """
                INSERT INTO world_boss
                (boss_name, boss_level, current_hp, total_hp, exp_reward, stone_reward, atk,
                 defense_rate, crit_rate, crit_damage)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    boss_info['name'],
                    boss_info['jj'],        # boss_level 对应 jj (境界)
                    boss_info['hp'],        # current_hp
                    boss_info['max_hp'],    # total_hp (boss_info中应有max_hp)
                    boss_info['exp'],       # exp_reward (boss_info中是总经验池)
                    boss_info['stone'],     # stone_reward (boss_info中是总灵石池)
                    boss_info['atk'],
                    boss_info.get('defense_rate', 0.05), # 从boss_info获取，若无则用默认值
                    boss_info.get('crit_rate', 0.03),
                    boss_info.get('crit_damage', 0.1)
                )
            )
            self.conn.commit()
            new_boss_id = cur.lastrowid
            logger.info(f"新世界BOSS【{boss_info['name']}】已成功存入数据库，ID: {new_boss_id}")
            return new_boss_id
        except sqlite3.Error as e: # 更具体的异常捕获
            logger.error(f"spawn_new_boss: 存入BOSS数据到数据库失败: {e}", exc_info=True)
            # self.conn.rollback() # 如果使用 self.conn，则需要手动回滚
            return None
        except KeyError as e: # 处理字典键不存在错误
            logger.error(f"spawn_new_boss: boss_info 字典缺少键: {e}, boss_info内容: {boss_info}", exc_info=True)
            return None

    def get_all_active_bosses(self) -> list:
        """获取所有活跃的世界BOSS信息"""
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM world_boss")
        return cur.fetchall()

    def get_active_boss(self) -> dict | None:
        """
        【元组下标访问版】获取当前活跃的唯一世界BOSS信息。
        假设 cur.fetchone() 返回一个元组，我们按固定顺序的下标访问。
        """
        # 确保这个查询语句的列顺序与下面的下标访问一一对应！
        # id, boss_name, boss_level, current_hp, total_hp,
        # exp_reward, stone_reward, atk,
        # defense_rate, crit_rate, crit_damage
        sql_query = """
            SELECT id, boss_name, boss_level, current_hp, total_hp,
                   exp_reward, stone_reward, atk,
                   defense_rate, crit_rate, crit_damage
            FROM world_boss LIMIT 1
        """
        try:
            # 假设 self.conn 是在 __init__ 中初始化的 sqlite3.Connection 对象
            cur = self.conn.cursor()
            cur.execute(sql_query)
            boss_row_tuple = cur.fetchone() # boss_row_tuple 是一个元组或 None
        except sqlite3.Error as e:
            logger.error(f"get_active_boss: 查询BOSS数据失败: {e}", exc_info=True)
            return None

        if not boss_row_tuple:
            return None

        # 按照 SELECT 语句的列顺序，通过下标访问元组元素
        # 如果列的顺序或数量与此不符，将会出错或取到错误的数据
        try:
            db_id = boss_row_tuple[0]
            boss_name = boss_row_tuple[1]
            boss_level = boss_row_tuple[2]
            current_hp = boss_row_tuple[3]
            total_hp = boss_row_tuple[4]
            exp_reward = boss_row_tuple[5]
            stone_reward = boss_row_tuple[6]
            atk_val = boss_row_tuple[7]
            # 对于后面添加的字段，需要检查元组长度，或者在SELECT时确保它们存在
            defense_rate_val = boss_row_tuple[8] if len(boss_row_tuple) > 8 and boss_row_tuple[8] is not None else 0.05
            crit_rate_val = boss_row_tuple[9] if len(boss_row_tuple) > 9 and boss_row_tuple[9] is not None else 0.03
            crit_damage_val = boss_row_tuple[10] if len(boss_row_tuple) > 10 and boss_row_tuple[10] is not None else 0.1

        except IndexError as e:
            logger.error(f"get_active_boss: 解析BOSS数据元组时下标越界: {e}. 元组内容: {boss_row_tuple}", exc_info=True)
            logger.error(f"请确保 world_boss 表的结构与查询语句和下标访问一致。")
            return None
        except TypeError as e: # 例如 boss_row_tuple 中某个期望是数字的字段是 None
            logger.error(f"get_active_boss: 解析BOSS数据元组时类型错误: {e}. 元组内容: {boss_row_tuple}", exc_info=True)
            return None


        # 构建战斗系统期望的BOSS信息字典
        boss_combat_info = {
            "id": db_id,                                  # 数据库主键
            "user_id": f"BOSS_INSTANCE_{db_id}",          # 战斗系统内部使用的唯一标识符
            "user_name": boss_name,                       # 用于显示和日志的BOSS名字
            "name": boss_name,                            # BOSS名字
            "level": boss_level,                          # 境界
            "jj": boss_level,                             # 境界 (兼容)
            "hp": current_hp,                             # 当前HP
            "max_hp": total_hp,                           # 最大HP
            "mp": 99999999,                               # 虚拟MP
            "max_mp": 99999999,                           # 虚拟最大MP
            "atk": atk_val,                               # 攻击力
            "defense_rate": defense_rate_val,             # 减伤率
            "crit_rate": crit_rate_val,                   # 暴击率
            "crit_damage": crit_damage_val,               # 爆伤加成
            "exp": exp_reward,                            # 总经验奖励池
            "stone": stone_reward,                        # 总灵石奖励池
            "power": int(total_hp * 0.5 + atk_val * 10),  # 简单估算战力
            "root": "妖兽之王",                           # 虚拟灵根
            "root_type": "太古凶兽",                        # 虚拟灵根类型
            "buff_info": None,                            # BOSS不使用玩家的Buff系统
            "attackers": set()                            # 初始化攻击者集合
        }

        return boss_combat_info

    def update_boss_hp(self, boss_db_id: int, new_hp: int):
        cur = self.conn.cursor()
        cur.execute("UPDATE world_boss SET current_hp = ? WHERE id = ?", (new_hp, boss_db_id))
        self.conn.commit()

    def delete_boss(self, boss_db_id: int):
        """从数据库中删除世界BOSS"""
        cur = self.conn.cursor()
        cur.execute("DELETE FROM world_boss WHERE id = ?", (boss_db_id,))
        self.conn.commit()
        # ==================================
# === 在 service.py 末尾追加群组持久化方法 ===
# ==================================

    def add_active_group(self, group_id: str):
        """添加一个活跃的群组到数据库，如果已存在则忽略"""
        cur = self.conn.cursor()
        # 使用 INSERT OR IGNORE 来避免因主键重复而报错
        cur.execute("INSERT OR IGNORE INTO active_groups (group_id) VALUES (?)", (group_id,))
        self.conn.commit()

    def get_all_active_groups(self) -> set:
        """从数据库获取所有活跃的群组ID"""
        cur = self.conn.cursor()
        cur.execute("SELECT group_id FROM active_groups")
        results = cur.fetchall()
        # 将返回的元组列表转换为集合
        return {row[0] for row in results}

    def get_user_alchemy_info(self, user_id: str) -> UserAlchemyInfo:
        """获取用户的炼丹信息，如果不存在则创建并返回默认值"""
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM user_alchemy_info WHERE user_id = ?", (user_id,))
        result = cur.fetchone()

        if not result:
            # v-- 4. 在创建默认记录时，设置一个非常早的时间，确保新用户第一次就能收取 --v
            # 创建一个2天前的时间作为默认值
            initial_time = str(datetime.now() - timedelta(days=2))
            default_record = (user_id, 0, 0, 0, 0, json.dumps({}), initial_time)
            # ^-- 更新结束 --^

            cur.execute("INSERT INTO user_alchemy_info VALUES (?, ?, ?, ?, ?, ?, ?)", default_record)
            self.conn.commit()
            return UserAlchemyInfo(*default_record)
        else:
            return UserAlchemyInfo(*result)

    def update_user_alchemy_info(self, user_id: str, alchemy_info: UserAlchemyInfo):
        """更新用户的炼丹信息"""
        cur = self.conn.cursor()
        record_str = alchemy_info.alchemy_record if isinstance(alchemy_info.alchemy_record, str) else json.dumps(alchemy_info.alchemy_record, ensure_ascii=False)

        # v-- 5. 在更新方法中加入对 last_collection_time 的更新 --v
        cur.execute(
            """
            UPDATE user_alchemy_info SET
                collection_level = ?, fire_level = ?, pill_resistance_level = ?,
                alchemy_exp = ?, alchemy_record = ?, last_collection_time = ?
            WHERE user_id = ?
            """,
            (
                alchemy_info.collection_level,
                alchemy_info.fire_level,
                alchemy_info.pill_resistance_level,
                alchemy_info.alchemy_exp,
                record_str,
                str(alchemy_info.last_collection_time), # 确保是字符串
                user_id
            )
        )
        # ^-- 更新结束 --^
        self.conn.commit()

    def purchase_blessed_spot(self, user_id: str) -> bool:
        """为用户购买洞天福地"""
        try:
            cur = self.conn.cursor()
            cur.execute("UPDATE user_xiuxian SET blessed_spot_flag = 1 WHERE user_id = ?", (user_id,))
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"购买洞天福地失败: {e}")
            return False

    def update_blessed_spot_name(self, user_id: str, new_name: str):
        """更新洞天福地名称"""
        cur = self.conn.cursor()
        cur.execute("UPDATE user_xiuxian SET blessed_spot_name = ? WHERE user_id = ?", (new_name, user_id))
        self.conn.commit()

    def get_boss_drop(self, boss_info: dict) -> tuple[dict, list]:
        """
        【修正版】根据BOSS信息和配置计算掉落物。
        :param boss_info: 被击败的BOSS的信息字典，必须包含 'jj' (境界), 'exp' (总经验), 'stone' (总灵石)
        :return: (最后一击的额外奖励字典, 所有参与者的掉落物品列表)
        """
        # 使用实例化的 XiuConfig
        drop_config_all = self.xiu_config.boss_drops_by_level_range

        # 1. 根据BOSS境界确定当前使用的掉落池
        boss_level_key = self._get_boss_level_range_key(boss_info['jj'])
        current_drop_config = drop_config_all.get(boss_level_key)

        if not current_drop_config:
            logger.error(f"未找到BOSS境界 {boss_info['jj']} (key: {boss_level_key}) 对应的掉落配置，将使用默认空掉落。")
            return {"exp": 0, "stone": 0, "items": []}, []

        # 2. 计算最后一击的额外奖励
        fh_bonus_config = current_drop_config.get("final_hit_bonus", {})
        final_hit_rewards = {
            "exp": int(boss_info['exp'] * fh_bonus_config.get('exp_rate', 0.0)),
            "stone": int(boss_info['stone'] * fh_bonus_config.get('stone_rate', 0.0)),
            "items": [] # 存储最后一击获得的物品
        }

        for item_spec in fh_bonus_config.get("extra_items", []):
            if random.randint(1, 100) <= item_spec['rate']:
                quantity = 1
                if "quantity" in item_spec:
                    quantity = random.randint(item_spec['quantity'][0], item_spec['quantity'][1])

                item_data = self.items.get_data_by_item_id(item_spec['id'])
                if item_data:
                    final_hit_rewards["items"].append({
                        "id": item_spec['id'],
                        "name": item_data.get('name', '未知物品'),
                        "type": item_spec.get('type', item_data.get('item_type', '未知类型')), # 优先使用配置中的type
                        "quantity": quantity
                    })
                else:
                    logger.warning(f"最后一击奖励中配置的物品ID {item_spec['id']} 未在物品库中找到。")


        # 3. 计算所有参与者的公共掉落
        participant_drop_pool = current_drop_config.get("participant_drop_pool", [])
        participant_drops_list = [] # 每个参与者独立roll一次这个list

        for item_spec in participant_drop_pool:
            if random.randint(1, 100) <= item_spec['rate']:
                item_id = item_spec['id']
                item_type_from_config = item_spec.get('type') # 从配置中获取的类型

                if item_id == 0 and item_type_from_config == "灵石": # 特殊处理基础灵石奖励
                    amount = random.randint(item_spec['amount'][0], item_spec['amount'][1])
                    participant_drops_list.append({
                        "id": 0, # 特殊ID代表灵石
                        "name": "灵石",
                        "type": "灵石",
                        "quantity": amount
                    })
                else:
                    item_data = self.items.get_data_by_item_id(item_id)
                    if item_data:
                        quantity = 1
                        if "quantity" in item_spec: # 可堆叠物品
                            quantity = random.randint(item_spec['quantity'][0], item_spec['quantity'][1])

                        participant_drops_list.append({
                            "id": item_id,
                            "name": item_data.get('name', '未知物品'),
                            # 优先使用掉落配置中指定的type，如果未指定，则用物品库中的item_type
                            "type": item_type_from_config or item_data.get('item_type', '未知类型'),
                            "quantity": quantity
                        })
                    else:
                        logger.warning(f"参与者掉落池中配置的物品ID {item_id} 未在物品库中找到。")

        return final_hit_rewards, participant_drops_list


    def get_top1_user(self) -> UserDate | None:
        """获取服务器内修为最高的用户信息"""
        cur = self.conn.cursor()
        # ORDER BY exp DESC LIMIT 1 可以直接找到修为最高的用户
        cur.execute("SELECT * FROM user_xiuxian ORDER BY exp DESC LIMIT 1")
        result = cur.fetchone()
        return UserDate(*result) if result and len(result) == len(UserDate._fields) else None

    def create_boss(self) -> dict | None:
        """
        【新版】创建世界boss, 采用基于境界基准值的动态生成。
        """
        top_user_info = self.get_top1_user()
        top_user_level = top_user_info.level if top_user_info else "江湖好手"
        if top_user_level.startswith("化圣境"):
            top_user_level = "太乙境圆满"

        all_levels = self.xiu_config.level
        try:
            now_jinjie_index = all_levels.index(top_user_level)
        except ValueError:
            now_jinjie_index = 0

        #min_jinjie_range = 30
        #start_index = max(0, now_jinjie_index - min_jinjie_range)
        #end_index = now_jinjie_index + 1
        #boss_level = random.choice(all_levels[start_index:end_index])

        boss_level_index = min(len(all_levels) -1, now_jinjie_index + random.randint(0,1)) # 略高于顶级玩家
        boss_level = all_levels[boss_level_index]

        # 1. 获取该境界的玩家基础属性作为蓝本
        #level_config = self.jsondata.level_data().get(boss_level, {})
        #base_hp = level_config.get("HP", 500)
        #base_atk = level_config.get("ATK", 100)
        level_config_data = self.jsondata.level_data()
        # BOSS的基础属性应该基于其对应境界的玩家属性，再进行大幅强化
        # 假设 level_data 中有 'HP', 'MP', 'ATK' 作为该境界玩家的基础参考值
        player_base_stats_for_boss_level = level_config_data.get(boss_level, {})

        # 如果该境界没有配置具体基础值，则基于修为估算（但最好是有配置）
        player_base_exp = player_base_stats_for_boss_level.get("power", 10000) # 用境界的power作为经验基准
        player_base_hp = player_base_stats_for_boss_level.get("HP", player_base_exp / 2)
        player_base_atk = player_base_stats_for_boss_level.get("ATK", player_base_exp / 10)
        boss_config_multipliers = self.xiu_config.boss_config.get("Boss倍率", {"气血": 45, "攻击": 0.2})

        boss_hp = int(player_base_hp * boss_config_multipliers['气血'])
        boss_atk = int(player_base_atk * boss_config_multipliers['攻击'])
        # 为BOSS设置其他战斗属性
        boss_defense_rate = round(random.uniform(0.05, 0.20), 2) # BOSS有5%-20%的减伤
        boss_crit_rate = round(random.uniform(0.05, 0.15), 2)    # BOSS有5%-15%的暴击率
        boss_crit_damage = round(random.uniform(0.2, 0.5), 2)   # BOSS暴击额外造成20%-50%伤害

        stone_reward = self.xiu_config.boss_config['Boss灵石'].get(boss_level, 1000)
        exp_reward = int(player_base_exp * 0.1) # 奖励为该境界玩家升级所需经验的10%

        boss_name = f"肆虐的{random.choice(self.xiu_config.boss_config['Boss名字'])}"

        return {
            "user_id": f"BOSS_{boss_name[:5]}_{int(time.time())}", # 特殊ID
            "user_name": boss_name, # 和name字段一致
            "name": boss_name,
            "jj": boss_level, # 境界
            "level": boss_level, # 也用level字段存储境界，方便PVP函数
            "hp": boss_hp,
            "max_hp": boss_hp, # BOSS初始血量即为最大血量
            "mp": 99999999, # BOSS通常蓝无限或极高
            "max_mp": 99999999,
            "atk": boss_atk,
            "defense_rate": boss_defense_rate,
            "crit_rate": boss_crit_rate,
            "crit_damage": boss_crit_damage,
            "stone": stone_reward, # 这是总掉落池的灵石
            "exp": exp_reward,     # 这是总掉落池的经验
            "power": boss_hp * 0.5 + boss_atk * 10, # 简单估算一个战力值
            "root": "妖兽",
            "root_type": "洪荒异种",
            "buff_info": None # BOSS通常不直接使用玩家的BuffInfo系统
        }

    def set_user_buff(self, user_id: str, buff_type: str, value: int, is_additive: bool = False):
        """
        通用方法：为用户设置或增加Buff值
        :param is_additive: True代表增加值，False代表直接设置值
        """
        valid_buff_types = ['main_buff', 'sec_buff', 'sub_buff', 'fabao_weapon', 'armor_buff', 'atk_buff']
        if buff_type not in valid_buff_types:
            logger.error(f"无效的Buff类型: {buff_type}")
            return False

        try:
            cur = self.conn.cursor()
            if is_additive:
                sql = f"UPDATE BuffInfo SET {buff_type} = {buff_type} + ? WHERE user_id = ?"
            else:
                sql = f"UPDATE BuffInfo SET {buff_type} = ? WHERE user_id = ?"
            cur.execute(sql, (value, user_id))
            if cur.rowcount == 0: # 如果 UPDATE 没有影响任何行
                logger.warning(f"BuffInfo表中未找到用户 {user_id} 的记录，尝试插入新记录并装备。")
                # 插入一条全0的记录，然后只更新要装备的槽位
                cur.execute("""
                    INSERT OR IGNORE INTO BuffInfo 
                    (user_id, main_buff, sec_buff, faqi_buff, fabao_weapon, armor_buff, atk_buff, blessed_spot, sub_buff) 
                    VALUES (?, 0, 0, 0, 0, 0, 0, 0, 0)
                    """, (user_id,)) # faqi_buff 是旧字段名，可能你的表里已经没有了

                cur.execute(sql, (value, user_id))
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"更新Buff失败: {e}")
            return False

    def update_user_level_up_rate(self, user_id: str, rate_add: int):
        """增加用户的突破成功率"""
        cur = self.conn.cursor()
        cur.execute("UPDATE user_xiuxian SET level_up_rate = level_up_rate + ? WHERE user_id = ?", (rate_add, user_id))
        self.conn.commit()

    def update_user_blessed_spot_level(self, user_id: str, new_level: int):
        """更新用户的洞天福地等级"""
        cur = self.conn.cursor()
        # 确保 BuffInfo 记录存在
        if not self.get_user_buff_info(user_id):
            cur.execute("INSERT INTO BuffInfo (user_id) VALUES (?)", (user_id,))

        cur.execute("UPDATE BuffInfo SET blessed_spot = ? WHERE user_id = ?", (new_level, user_id))
        self.conn.commit()

    def reset_user_level_up_rate(self, user_id: str):
        """将用户的额外突破成功率清零"""
        cur = self.conn.cursor()
        cur.execute("UPDATE user_xiuxian SET level_up_rate = 0 WHERE user_id = ?", (user_id,))
        self.conn.commit()

    #def update_user_hp_mp_atk(self, user_id: str):
    #    """根据当前修为，重置并更新用户的HP, MP, ATK基础值"""
    #    user_info = self.get_user_message(user_id)
    #    if not user_info:
    #        return

    #    new_hp = int(user_info.exp / 2)
    #    new_mp = int(user_info.exp)
    #    new_atk = int(user_info.exp / 10)

    #    cur = self.conn.cursor()
    #    cur.execute(
    #        "UPDATE user_xiuxian SET hp = ?, mp = ?, atk = ? WHERE user_id = ?",
    #        (new_hp, new_mp, new_atk, user_id)
    #    )
    #    self.conn.commit()
    
    #    # --- 坊市 Market 相关方法 ---
    def add_market_goods(self, user_id: str, goods_id: int, goods_type: str, price: int) -> bool:
        """上架一件商品到坊市"""
        item_info = self.items.get_data_by_item_id(goods_id)
        if not item_info:
            return False

        user_info = self.get_user_message(user_id)
        goods_name = item_info.get('name')
        user_name = user_info.user_name if user_info else "神秘人"

        try:
            cur = self.conn.cursor()
            cur.execute(
                "INSERT INTO market (user_id, goods_id, goods_name, goods_type, price, group_id, user_name) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (user_id, goods_id, goods_name, goods_type, price, "0", user_name)
            )
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"上架商品失败: {e}")
            return False

    def get_market_goods_by_group(self) -> list[MarketGoods]:
        """获取指定群聊坊市的所有商品"""
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM market ORDER BY id ASC")
        results = cur.fetchall()
        return [MarketGoods(*row) for row in results]

    def get_market_goods_by_id(self, market_id: int) -> MarketGoods | None:
        """通过坊市ID和群聊ID获取商品信息"""
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM market WHERE id = ?", (market_id, ))
        result = cur.fetchone()
        return MarketGoods(*result) if result else None

    def remove_market_goods_by_id(self, market_id: int) -> bool:
        """通过坊市ID下架商品"""
        try:
            cur = self.conn.cursor()
            cur.execute("DELETE FROM market WHERE id = ?", (market_id,))
            self.conn.commit()
            return cur.rowcount > 0 # 检查是否真的有行被删除了
        except Exception as e:
            logger.error(f"下架商品失败: {e}")
            return False

    def set_user_rift_cd(self, user_id: str):
        """设置用户秘境探索CD"""
        cd_minutes = self.xiu_config.rift_cd_minutes
        self._set_user_cd(user_id, 5, cd_minutes)

    def check_user_rift_cd(self, user_id: str) -> int:
        """检查用户秘境探索CD (type=5)，返回剩余秒数"""
        cd_info = self._get_user_cd_by_type(user_id, 5)
        if cd_info and cd_info.scheduled_time:
            end_time = datetime.fromisoformat(cd_info.scheduled_time)
            if datetime.now() < end_time:
                return int((end_time - datetime.now()).total_seconds())
        return 0

    def _get_user_cd_by_type(self, user_id: str, cd_type: int) -> UserCd | None:
        """内部方法：通过类型精确获取一个用户的特定CD记录"""
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM user_cd WHERE user_id = ? AND type = ?", (user_id, cd_type))
        result = cur.fetchone()
        return UserCd(*result) if result else None

    def _set_user_cd(self, user_id: str, cd_type: int, cd_duration_minutes: int):
        """内部方法：设置一个特定类型的CD"""
        create_time = datetime.now()
        end_time = create_time + timedelta(minutes=cd_duration_minutes)

        cur = self.conn.cursor()
        # 使用 INSERT OR REPLACE，如果存在则更新，不存在则插入
        cur.execute(
            "INSERT OR REPLACE INTO user_cd (user_id, type, create_time, scheduled_time) VALUES (?, ?, ?, ?)",
            (user_id, cd_type, str(create_time), str(end_time))
        )
        self.conn.commit()

    def set_user_cd(self, user_id: str, cd_time_minutes: int, cd_type: int):
        """通用CD设置接口，现直接调用内部方法"""
        self._set_user_cd(user_id, cd_type, cd_time_minutes)

    def rollback_high_exp_users(self, exp_threshold: int = 200000, avg_exp_per_rift: int = 2300, avg_stone_per_rift: int = 2500) -> list[str]:
        """
        批量修复修为异常高的用户数据。
        :param exp_threshold: 触发修复的修为阈值。
        :param avg_exp_per_rift: 估算的单次秘境修为收益。
        :param avg_stone_per_rift: 估算的单次秘境灵石收益。
        :return: 一个包含每位用户修复详情的字符串列表。
        """
        cur = self.conn.cursor()

        # 1. 找出所有修为超过阈值的用户
        cur.execute("SELECT user_id, user_name, exp, stone FROM user_xiuxian WHERE exp > ?", (exp_threshold,))
        high_exp_users = cur.fetchall()

        if not high_exp_users:
            return ["未找到修为超过20万的用户，无需修复。"]

        log_messages = ["--- 开始执行数据修复 ---"]

        for user_data in high_exp_users:
            user_id, user_name, current_exp, current_stone = user_data

            # 2. 计算超额修为和估算的秘境次数
            excess_exp = current_exp - exp_threshold
            estimated_rift_count = excess_exp // avg_exp_per_rift

            if estimated_rift_count <= 0:
                log_messages.append(f"用户【{user_name}】({user_id})修为虽高，但未达到一次秘境估算收益，跳过。")
                continue

            # 3. 计算需要扣除的总量
            exp_to_deduct = estimated_rift_count * avg_exp_per_rift
            stone_to_deduct = estimated_rift_count * avg_stone_per_rift

            # 4. 执行扣除（带安全检查，防止扣成负数）
            final_exp_to_deduct = min(exp_to_deduct, current_exp - 100) # 至少保留100修为
            final_stone_to_deduct = min(stone_to_deduct, current_stone)

            try:
                self.update_j_exp(user_id, final_exp_to_deduct)
                self.update_ls(user_id, final_stone_to_deduct, 2)

                # 设置一个惩罚性CD，比如24小时
                self.set_user_cd(user_id, 24 * 60, 5) # type=5是秘境CD

                log_messages.append(
                    f"用户【{user_name}】:\n"
                    f" - 估算超额探索次数: {estimated_rift_count} 次\n"
                    f" - 已扣除修为: {final_exp_to_deduct}\n"
                    f" - 已扣除灵石: {final_stone_to_deduct}\n"
                    f" - 已施加24小时秘境冷却。"
                )
            except Exception as e:
                logger.error(f"为用户 {user_id} 执行回滚时失败: {e}")
                log_messages.append(f"用户【{user_name}】({user_id}) 修复失败，发生数据库错误。")

        log_messages.append("--- 数据修复执行完毕 ---")
        return log_messages

    def fix_user_data(self, user_id: str) -> tuple[bool, str]:
        """
        【最终版】修复单个用户的数据，包括基础属性、战力和HP溢出。
        """
        user_info_before = self.get_user_message(user_id)
        if not user_info_before:
            return False, f"找不到用户 {user_id} 的数据。"

        try:
            # --- 执行修复 ---
            # 1. 根据境界，刷新基础属性 (HP, MP, ATK)
            self.refresh_user_base_attributes(user_id)
            
            # 2. 基于新的基础属性和装备功法，刷新战力
            self.update_power2(user_id)
            
            # 3. 再次获取信息，检查并修复HP溢出问题
            user_info_after = self.get_user_message(user_id)
            user_real_info_after = self.get_user_real_info(user_id)
            
            max_hp = user_real_info_after['max_hp']
            hp_log = f"HP正常 ({user_info_after.hp}/{max_hp})。"
            if user_info_after.hp > max_hp:
                self.conn.cursor().execute("UPDATE user_xiuxian SET hp = ? WHERE user_id = ?", (max_hp, user_id))
                self.conn.commit()
                hp_log = f"HP异常({user_info_after.hp}/{max_hp})，已修正为 {max_hp}。"
                # 再次获取最终信息
                user_info_after = self.get_user_message(user_id)

            # --- 生成日志 ---
            log = (
                f"用户【{user_info_before.user_name}】数据修复完成：\n"
                f" - 攻击力: {user_info_before.atk} → {user_info_after.atk}\n"
                f" - 战 力: {user_info_before.power} → {user_info_after.power}\n"
                f" - {hp_log}"
            )
            return True, log

        except Exception as e:
            logger.error(f"修复用户 {user_id} 数据时失败: {e}")
            return False, f"用户【{user_info_before.user_name}】修复失败，发生错误。"

    def fix_all_users_data(self) -> list[str]:
        """
        【最终正确版】批量修复所有用户的数据，并返回每个用户的详细修复日志列表。
        """
        cur = self.conn.cursor()
        cur.execute("SELECT user_id FROM user_xiuxian")
        all_user_ids = cur.fetchall()

        if not all_user_ids:
            return ["数据库中没有任何用户数据。"]

        # 1. 初始化报告列表，并添加一个总览头
        report_messages = [f"--- 开始执行全服数据修复，总计 {len(all_user_ids)} 名用户 ---"]
        success_count = 0
        fail_count = 0

        # 2. 循环为每个用户执行单点修复，并收集详细日志
        for user_id_tuple in all_user_ids:
            user_id = user_id_tuple[0]
            # fix_user_data 会返回 (bool, str)
            success, log_msg = self.fix_user_data(user_id)

            if success:
                success_count += 1
            else:
                fail_count += 1

            # 将每个用户的详细修复日志添加到报告列表中
            report_messages.append(log_msg)

        # 3. 在报告的末尾添加一个总结
        summary = f"--- 修复完成 ---\n成功修复 {success_count} 名用户，失败 {fail_count} 名。"
        report_messages.append(summary)

        return report_messages

    def refresh_user_base_attributes(self, user_id: str):
        """
        根据用户当前境界，刷新其基础属性（HP, MP, ATK）。
        这个方法现在不再直接依赖修为，而是依赖境界配置。
        """
        user_info = self.get_user_message(user_id)
        if not user_info:
            return

        level_config = self.jsondata.level_data().get(user_info.level, {})

        # 从境界配置中获取基础属性值
        base_hp = level_config.get("HP", 50)
        base_mp = level_config.get("MP", 100)
        base_atk = level_config.get("ATK", 10)

        cur = self.conn.cursor()

        # 更新时，确保当前HP和MP不超过新的最大值
        final_hp = min(user_info.hp, base_hp) if user_info.hp > 0 else base_hp
        final_mp = min(user_info.mp, base_mp) if user_info.mp > 0 else base_mp

        cur.execute(
            "UPDATE user_xiuxian SET hp = ?, mp = ?, atk = ? WHERE user_id = ?",
            (int(final_hp), int(final_mp), int(base_atk), user_id)
        )
        self.conn.commit()

    def get_next_level_info(self, current_level: str) -> dict | None:
        """获取下一境界的完整配置信息"""
        all_levels = self.xiu_config.level
        if current_level not in all_levels or current_level == all_levels[-1]:
            return None # 已是最高级或当前等级不存在

        current_index = all_levels.index(current_level)
        next_level_name = all_levels[current_index + 1]

        return self.jsondata.level_data().get(next_level_name)

    def _delete_user_cd_by_type(self, user_id: str, cd_type: int):
        """
        【新增】内部方法：删除特定类型的CD记录
        """
        cur = self.conn.cursor()
        cur.execute("DELETE FROM user_cd WHERE user_id = ? AND type = ?", (user_id, cd_type))
        self.conn.commit()

    async def _create_world_boss_task(self):
        """定时生成世界BOSS并写入数据库"""
        logger.info("调用生成boss的task")

        # 这个检查确保了不会在已有BOSS时重复生成
        if self.plugin_instance.world_boss:
            logger.info("已有世界BOSS存在，本次生成任务跳过。")
            return

        try:
            boss_info_template = self.service.create_boss()
            if not boss_info_template:
                logger.error("生成BOSS模板失败，任务中止。")
                return

            boss_db_id = self.service.spawn_new_boss(boss_info_template)
            logger.info(f"已生成新的世界BOSS，并存入数据库，ID: {boss_db_id}")
        except Exception as e:
            logger.error(f"生成BOSS并存入数据库失败：{e}")
            return # 发生错误时中止

        # 从数据库重新获取，确保信息一致
        self.plugin_instance.world_boss = self.service.get_active_boss()

        # 确保获取成功再广播
        if not self.plugin_instance.world_boss:
            logger.error("存入数据库后未能成功获取BOSS信息，广播取消。")
            return

        if hasattr(self.plugin_instance, 'groups') and self.plugin_instance.groups:
            msg = f"警报！{self.plugin_instance.world_boss['jj']}境界的【{self.plugin_instance.world_boss['name']}】已降临仙界，请各位道友速去讨伐！"
            await self._broadcast_to_groups(msg, "世界BOSS降临")

    def clear_all_bosses(self) -> int:
        """
        清理数据库中所有的世界BOSS记录。
        :return: 被删除的BOSS数量。
        """
        try:
            cur = self.conn.cursor()
            cur.execute("DELETE FROM world_boss")
            deleted_rows = cur.rowcount
            self.conn.commit()
            return deleted_rows
        except Exception as e:
            logger.error(f"清理世界BOSS失败: {e}")
            return 0

    def get_all_user_ids(self) -> list[str]:
        """获取所有用户的ID列表"""
        cur = self.conn.cursor()
        cur.execute("SELECT user_id FROM user_xiuxian")
        return [row[0] for row in cur.fetchall()]

    def reset_user_for_reincarnation(self, user_id: str, user_name: str, buff_value: float) -> dict:
        """
        处理用户身死道消和转世的逻辑。
        :param buff_value: 转世Buff的具体数值 (例如 0.2)
        :return: 包含新灵根信息的字典
        """
        death_config = self.xiu_config.death_calamity_config
        reincarnation_config = death_config['reincarnation_buff']
        buff_to_set = reincarnation_config['修炼速度加成'] # 本次要设置的固定值，例如 0.2

        # a. 重新生成灵根
        linggen_data = self.jsondata.root_data()
        rate_dict = {i: v["type_rate"] for i, v in linggen_data.items()}
        root_type = self._calculated(rate_dict)

        if linggen_data[root_type]["type_flag"]:
            flag = random.choice(linggen_data[root_type]["type_flag"])
            root = "、".join(random.sample(linggen_data[root_type]["type_list"], flag)) + '属性灵根'
        else:
            root = random.choice(linggen_data[root_type]["type_list"])

        # b. 重置用户信息，但保留并累加转世Buff
        try:
            cur = self.conn.cursor()
            # 我们将所有要更新的字段都作为参数传入，避免SQL注入和格式问题
            update_sql = """
                UPDATE user_xiuxian SET
                    stone = ?, root = ?, root_type = ?, level = ?, power = ?,
                    is_sign = ?, exp = ?, level_up_cd = ?, level_up_rate = ?,
                    sect_id = ?, sect_position = ?, hp = ?, mp = ?, atk = ?,
                    atkpractice = ?, sect_task = ?, sect_contribution = ?,
                    sect_elixir_get = ?, reincarnation_buff = ?
                WHERE user_id = ?
            """
            
            # 准备一个包含所有新值的元组，顺序与SQL语句中的'?'一一对应
            params = (
                0, root, root_type, '江湖好手', 100,             # stone, root, root_type, level, power
                0, 100, None, 0,                              # is_sign, exp, level_up_cd, level_up_rate
                0, 0, 50, 20, 10,                             # sect_id, sect_position, hp, mp, atk
                0, 0, 0, 0,                                   # atkpractice, sect_task, sect_contribution, sect_elixir_get
                buff_to_set,                                  # reincarnation_buff
                user_id                                       # for WHERE clause
            )
            cur.execute(update_sql, params)

            # c. 清理其他关联表的数据
            cur.execute("DELETE FROM back WHERE user_id = ?", (user_id,))
            cur.execute("DELETE FROM user_cd WHERE user_id = ?", (user_id,))
            cur.execute("DELETE FROM BuffInfo WHERE user_id = ?", (user_id,))
            cur.execute("DELETE FROM user_alchemy_info WHERE user_id = ?", (user_id,))
            cur.execute("DELETE FROM user_bounty WHERE user_id = ?", (user_id,))
            cur.execute("DELETE FROM user_rift WHERE user_id = ?", (user_id,))

            self.conn.commit()
            return {"success": True, "root": root, "root_type": root_type}
        except Exception as e:
            logger.error(f"重置用户 {user_id} 数据失败: {e}")
            return {"success": False}

    def get_market_goods_count(self) -> int:
        """获取全局坊市的商品总数"""
        with self.conn as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM market")
            result = cursor.fetchone()
            return result[0] if result else 75

    def check_user_cd_specific_type(self, user_id: str, cd_type: int) -> int:
        """
        检查用户特定类型的CD。
        :param user_id: 用户ID
        :param cd_type: CD类型 (1-闭关, 2-抢劫/BOSS, 4-重入仙途, 5-秘境, 6-切磋, 7-被打劫保护)
        :return: 剩余秒数, 0表示无CD或已结束
        """
        cd_info = self._get_user_cd_by_type(user_id, cd_type) # _get_user_cd_by_type 已在之前实现
        if cd_info and cd_info.scheduled_time:
            try:
                end_time = datetime.fromisoformat(cd_info.scheduled_time)
                if datetime.now() < end_time:
                    return int((end_time - datetime.now()).total_seconds())
            except (ValueError, TypeError):
                logger.warning(f"用户 {user_id} 的CD类型 {cd_type} 时间格式无效: {cd_info.scheduled_time}")
                return 0 # 无效时间视为无CD
        return 0
    
    def update_hp_to_value(self, user_id: str, new_hp_value: int):
        """
        直接将用户的HP设置为一个特定的值，会进行上下限校验。
        :param user_id: 用户ID
        :param new_hp_value: 新的HP值
        """
        user_real_info = self.get_user_real_info(user_id)
        if not user_real_info:
            logger.error(f"update_hp_to_value: 无法获取用户 {user_id} 的真实信息。")
            return

        max_hp = user_real_info['max_hp']
        # 确保HP不低于1（除非最大HP就是0或负数，那就有问题了），也不高于最大HP
        final_hp = max(1 if max_hp > 0 else 0, min(new_hp_value, max_hp))

        try:
            c = self.conn.cursor()
            c.execute("UPDATE user_xiuxian SET hp = ? WHERE user_id = ?", (final_hp, user_id))
            self.conn.commit()
        except Exception as e:
            logger.error(f"update_hp_to_value: 更新用户 {user_id} HP失败: {e}")

    def update_mp_to_value(self, user_id: str, new_mp_value: int):
        """
        直接将用户的HP设置为一个特定的值，会进行上下限校验。
        :param user_id: 用户ID
        :param new_mp_value: 新的HP值
        """
        user_real_info = self.get_user_real_info(user_id)
        if not user_real_info:
            logger.error(f"update_hp_to_value: 无法获取用户 {user_id} 的真实信息。")
            return

        max_mp = user_real_info['max_mp']
        # 确保HP不低于1（除非最大HP就是0或负数，那就有问题了），也不高于最大HP
        final_mp = max(1 if max_mp > 0 else 0, min(new_mp_value, max_mp))

        try:
            c = self.conn.cursor()
            c.execute("UPDATE user_xiuxian SET mp = ? WHERE user_id = ?", (final_mp, user_id))
            self.conn.commit()
        except Exception as e:
            logger.error(f"update_mp_to_value: 更新用户 {user_id} MP失败: {e}")

    def _get_boss_level_range_key(self, boss_level_actual: str) -> str:
        """
        辅助函数：根据BOSS具体境界映射到掉落配置表的大境界键。
        """
        # 这个映射逻辑需要根据你的 XiuConfig.level 列表来精确化
        # 简化版本：
        if boss_level_actual.startswith("练气境"): return "练气境"
        if boss_level_actual.startswith("筑基境"): return "筑基境"
        if boss_level_actual.startswith("结丹境"): return "结丹境"
        if boss_level_actual.startswith("元婴境"): return "元婴境"
        if boss_level_actual.startswith("化神境"): return "化神境"
        if boss_level_actual.startswith("炼虚境"): return "炼虚境"
        if boss_level_actual.startswith("合体境"): return "合体境"
        if boss_level_actual.startswith("大乘境"): return "大乘境"
        if boss_level_actual.startswith("渡劫境"): return "渡劫境"
        if boss_level_actual.startswith("半步真仙"): return "半步真仙"
        if boss_level_actual.startswith("真仙境"): return "真仙境"
        if boss_level_actual.startswith("金仙境"): return "金仙境"
        if boss_level_actual.startswith("太乙境"): return "太乙境"
        if boss_level_actual.startswith("化圣境"): return "化圣境"
        return "江湖好手" # 默认或最低级

    def format_item_details(item_data: dict) -> str | None:
        """
        根据物品数据字典，格式化该物品的详细描述字符串。
        :param item_data: 从 Items().get_data_by_item_id() 获取到的物品信息字典。
        :return: 格式化后的字符串，如果item_data无效则返回None。
        """
        if not item_data or not isinstance(item_data, dict):
            return "未能找到该物品的详细信息。"

        name = item_data.get('name', '未知物品')
        item_true_type = item_data.get('item_type', '未知类别') # 这是加载时赋予的内部类型

        # 统一从item_data中获取品阶信息
        # 功法类交换过，所以 'level' 是品阶；其他类是 'rank'
        if item_true_type in ["功法", "辅修功法", "神通"]:
            rank_display = item_data.get('level', '未知品阶') # 对于技能类，'level'字段现在是品阶
        else:
            rank_display = item_data.get('rank', '未知品阶') # 其他物品，'rank'字段是品阶
            if isinstance(rank_display, int): # 如果rank是数字，可能需要映射为文本，或直接显示
                # 你可能有一个 USERRANK 的反向映射，或者直接显示数字等级对应的品阶名
                # 为了简化，我们先直接用rank值，如果它是文本就直接用
                pass


        desc_lines = [f"【{name}】"]
        desc_lines.append(f"类型: {item_true_type} | 品阶: {rank_display}")

        description_field = item_data.get('desc') # 物品本身的描述字段
        if description_field:
            desc_lines.append(f"描述: {description_field}")

        # 根据不同类型添加特定信息
        if item_true_type == "法器": # 武器
            atk_buff = item_data.get('atk_buff', 0.0) * 100
            crit_buff = item_data.get('crit_buff', 0.0) * 100
            effects = []
            if atk_buff > 0: effects.append(f"攻击力+{atk_buff:.0f}%")
            if crit_buff > 0: effects.append(f"暴击率+{crit_buff:.0f}%")
            if effects: desc_lines.append(f"效果: {', '.join(effects)}")

        elif item_true_type == "防具":
            def_buff = item_data.get('def_buff', 0.0) * 100
            if def_buff > 0: desc_lines.append(f"效果: 减伤率+{def_buff:.0f}%")

        elif item_true_type == "功法": # 主修功法
            effects = []
            if item_data.get('hpbuff', 0) != 0: effects.append(f"生命+{item_data['hpbuff']*100:.0f}%")
            if item_data.get('mpbuff', 0) != 0: effects.append(f"真元+{item_data['mpbuff']*100:.0f}%")
            if item_data.get('atkbuff', 0) != 0: effects.append(f"攻击+{item_data['atkbuff']*100:.0f}%")
            if item_data.get('ratebuff', 0) != 0: effects.append(f"修炼速度+{item_data['ratebuff']*100:.0f}%")
            if effects: desc_lines.append(f"效果: {', '.join(effects)}")

        elif item_true_type == "辅修功法":
            buff_type_str = item_data.get('buff_type')
            buff_val_str = item_data.get('buff', "0")
            effect_desc = "未知效果"
            if buff_type_str == '1': effect_desc = f"攻击力+{buff_val_str}%"
            elif buff_type_str == '2': effect_desc = f"暴击率+{buff_val_str}%"
            elif buff_type_str == '3': effect_desc = f"暴击伤害+{buff_val_str}%"
            elif buff_type_str == '4': effect_desc = f"每回合气血回复+{buff_val_str}%"
            elif buff_type_str == '5': effect_desc = f"每回合真元回复+{buff_val_str}%"
            elif buff_type_str == '6': effect_desc = f"气血吸取+{buff_val_str}%"
            elif buff_type_str == '7': effect_desc = f"真元吸取+{buff_val_str}%"
            elif buff_type_str == '8': effect_desc = f"对敌中毒效果+{buff_val_str}%"
            desc_lines.append(f"效果: {effect_desc}")

        elif item_true_type == "神通":
            # 神通的描述比较复杂，直接使用原版 get_sec_msg 的逻辑（如果适用）或简化
            # 这里我先用它自带的 desc 字段，并指出其消耗
            hpcost_p = item_data.get('hpcost', 0) * 100
            mpcost_p = item_data.get('mpcost', 0) * 100 # 假设原版mpcost是基于exp的百分比，这里简化
            skill_type = item_data.get('skill_type')

            cost_str_parts = []
            if hpcost_p > 0: cost_str_parts.append(f"消耗当前生命{hpcost_p:.0f}%")
            if mpcost_p > 0: cost_str_parts.append(f"消耗当前真元{mpcost_p:.0f}%") # 或者 "消耗最大真元xx%"

            effect_details = []
            if skill_type == 1: # 直接伤害类
                atk_values_str = ", ".join([f"{v}倍" for v in item_data.get('atkvalue', [])])
                effect_details.append(f"造成 {len(item_data.get('atkvalue', []))} 次伤害，分别为基础攻击的 {atk_values_str}")
                if item_data.get('turncost', 0) > 0 : effect_details.append(f"释放后休息 {item_data['turncost']} 回合")
            elif skill_type == 2: # 持续伤害
                 effect_details.append(f"造成 {item_data.get('atkvalue',0)} 倍攻击的持续伤害，持续 {item_data.get('turncost',0)} 回合")
            elif skill_type == 3: # Buff类
                buff_type_val = item_data.get('bufftype')
                buff_val = item_data.get('buffvalue',0)
                if buff_type_val == 1: effect_details.append(f"提升自身 {buff_val*100:.0f}% 攻击力")
                elif buff_type_val == 2: effect_details.append(f"提升自身 {buff_val*100:.0f}% 减伤率")
                effect_details.append(f"持续 {item_data.get('turncost',0)} 回合")
            elif skill_type == 4: # 封印类
                effect_details.append(f"尝试封印对手，成功率 {item_data.get('success', 100)}%，持续 {item_data.get('turncost',0)} 回合")

            if item_data.get('desc'): # 神通自带的描述通常是flavor text
                 desc_lines.append(f"lore: {item_data.get('desc')}")
            if effect_details:
                desc_lines.append(f"战斗效果: {'; '.join(effect_details)}")
            if cost_str_parts:
                desc_lines.append(f"使用条件: {', '.join(cost_str_parts)}")
            desc_lines.append(f"释放概率: {item_data.get('rate', 100)}%")


        elif item_true_type == "丹药" or item_true_type == "合成丹药":
            # 'desc' 字段通常已经包含了效果描述
            if 'buff_type' in item_data: # 更详细的说明
                bt = item_data['buff_type']
                bv = item_data.get('buff', 0)
                if bt == "hp": desc_lines.append(f"  具体: 回复最大生命 {bv*100:.0f}%")
                elif bt == "exp_up": desc_lines.append(f"  具体: 增加修为 {bv} 点")
                elif bt == "atk_buff": desc_lines.append(f"  具体: 永久增加攻击力 {bv} 点")
                elif bt == "level_up_rate": desc_lines.append(f"  具体: 下次突破成功率 +{bv}%")
                elif bt == "level_up_big": desc_lines.append(f"  具体: 冲击大境界时突破成功率 +{bv}%")
            if 'day_num' in item_data: desc_lines.append(f"  每日使用上限: {item_data.get('day_num', '无限制')}")
            if 'all_num' in item_data: desc_lines.append(f"  总使用上限: {item_data.get('all_num', '无限制')}")
            if '境界' in item_data: desc_lines.append(f"  使用境界: {item_data['境界']}")


        elif item_true_type == "药材":
            # 主药、药引、辅药的冷热、药性、效力
            # YAOCAIINFOMSG 需定义或从原版引入
            YAOCAIINFOMSG = { "-1": "性寒", "0": "性平", "1": "性热", "2": "生息", "3": "养气", "4": "炼气", "5": "聚元", "6": "凝神" }
            main_herb = item_data.get('主药')
            catalyst_herb = item_data.get('药引')
            aux_herb = item_data.get('辅药')
            if main_herb:
                desc_lines.append(f"  主药效用: {YAOCAIINFOMSG.get(str(main_herb.get('h_a_c',{}).get('type')),'')} {main_herb.get('h_a_c',{}).get('power','')} | {YAOCAIINFOMSG.get(str(main_herb.get('type')),'')} {main_herb.get('power','')}")
            if catalyst_herb:
                 desc_lines.append(f"  药引效用: {YAOCAIINFOMSG.get(str(catalyst_herb.get('h_a_c',{}).get('type')),'')} {catalyst_herb.get('h_a_c',{}).get('power','')}") #药引只有冷热
            if aux_herb:
                desc_lines.append(f"  辅药效用: {YAOCAIINFOMSG.get(str(aux_herb.get('type')),'')} {aux_herb.get('power','')}")

        elif item_true_type == "炼丹炉":
            buff = item_data.get('buff', 0)
            desc_lines.append(f"  效果: 炼丹时额外产出丹药 +{buff} 枚")

        elif item_true_type == "聚灵旗":
            speed_buff = item_data.get('修炼速度', 0)
            herb_speed_buff = item_data.get('药材速度', 0)
            effects = []
            if speed_buff > 0 : effects.append(f"洞天修炼速度提升等级 {speed_buff}") # 原版似乎是等级，不是百分比
            if herb_speed_buff > 0 : effects.append(f"灵田药材生长速度提升等级 {herb_speed_buff}")
            if effects: desc_lines.append(f"  效果: {', '.join(effects)}")

        return "\n".join(desc_lines)

    def set_user_temp_buff(self, user_id: str, buff_key: str, buff_value: any, duration_seconds: int = None):
        """
        为用户设置一个内存中的临时Buff。
        :param user_id: 用户ID
        :param buff_key: Buff的唯一标识符 (例如 "reduce_breakthrough_penalty")
        :param buff_value: Buff的值 (例如 True, 或一个包含更多信息的字典)
        :param duration_seconds: Buff的持续时间（秒）。如果为None，则Buff不会自动过期，需要手动消耗。
        """
        if user_id not in self.user_temp_buffs:
            self.user_temp_buffs[user_id] = {}

        expires_at = None
        if duration_seconds is not None:
            expires_at = time.time() + duration_seconds

        self.user_temp_buffs[user_id][buff_key] = {
            "value": buff_value,
            "expires_at": expires_at
        }
        logger.info(f"为用户 {user_id} 设置临时Buff: {buff_key}={buff_value}, 过期时间: {expires_at}")

    def get_user_temp_buff(self, user_id: str, buff_key: str):
        """
        获取用户当前的临时Buff值，如果Buff不存在或已过期则返回None。
        :param user_id: 用户ID
        :param buff_key: Buff的唯一标识符
        :return: Buff的值，或者None
        """
        if user_id in self.user_temp_buffs and buff_key in self.user_temp_buffs[user_id]:
            buff_data = self.user_temp_buffs[user_id][buff_key]
            if buff_data["expires_at"] is None or time.time() < buff_data["expires_at"]:
                return buff_data["value"]
            else:
                # Buff已过期，从字典中移除
                del self.user_temp_buffs[user_id][buff_key]
                if not self.user_temp_buffs[user_id]: # 如果该用户没有其他buff了，也移除用户条目
                    del self.user_temp_buffs[user_id]
                logger.info(f"用户 {user_id} 的临时Buff {buff_key} 已过期并移除。")
        return None

    def consume_user_temp_buff(self, user_id: str, buff_key: str):
        """
        消耗（移除）用户的一个临时Buff。
        :param user_id: 用户ID
        :param buff_key: Buff的唯一标识符
        """
        if user_id in self.user_temp_buffs and buff_key in self.user_temp_buffs[user_id]:
            del self.user_temp_buffs[user_id][buff_key]
            if not self.user_temp_buffs[user_id]:
                del self.user_temp_buffs[user_id]
            logger.info(f"用户 {user_id} 的临时Buff {buff_key} 已被消耗并移除。")

    def check_and_consume_temp_buff(self, user_id: str, buff_key: str):
        """
        检查用户是否有指定的临时Buff，如果存在且未过期，则返回其值并消耗（移除）该Buff。
        :param user_id: 用户ID
        :param buff_key: Buff的唯一标识符
        :return: Buff的值（如果存在且有效），否则返回None。
        """
        buff_value = self.get_user_temp_buff(user_id, buff_key)
        if buff_value is not None:
            self.consume_user_temp_buff(user_id, buff_key)
            return buff_value
        return None

    def update_item_usage_counts(self, user_id: str, goods_id: int, consumed_num: int):
        """
        更新用户背包中特定物品的每日已使用次数和总已使用次数。
        """
        cur = self.conn.cursor()
        try:
            # 增加每日使用次数和总使用次数
            # 确保 update_time 也被更新，如果您的每日重置逻辑依赖它
            cur.execute("""
                UPDATE back
                SET day_num = day_num + ?,
                    all_num = all_num + ?,
                    update_time = ?
                WHERE user_id = ? AND goods_id = ?
            """, (consumed_num, consumed_num, str(datetime.now()), user_id, goods_id))

            self.conn.commit()
            if cur.rowcount == 0: # 这是一个潜在问题，如果物品在消耗后记录就没了，这里可能更新不到
                logger.warning(f"更新物品使用次数警告：未找到用户 {user_id} 的物品ID {goods_id} 的记录来更新使用次数。可能物品已耗尽。")
        except Exception as e:
            logger.error(f"更新物品 {goods_id} 的使用次数失败 for user {user_id}: {e}")
            self.conn.rollback()

    def get_item_mortgage_loan_amount(self, item_id_original_str: str, item_data_dict: dict) -> int:
        """
        计算给定物品的抵押贷款额度。
        :param item_id_original_str: 物品在其原始JSON中的ID (字符串形式)。
        :param item_data_dict: 物品的完整数据字典 (从 Items().get_data_by_item_id() 获取)。
        :return: 可贷款的灵石数量，如果物品不可抵押或计算失败则返回0。
        """
        item_type = item_data_dict.get('item_type')
        loan_amount = 0

        items_manager = self.items

        main_item_rate_from_pool = 0.15 # 卡池主要物品的综合爆率 (例如15%)

        pool_id = None
        single_pull_cost = 0
        item_weight = 0
        total_category_weight = 1 # 默认为1防止除零

        if item_type == "法器":
            pool_id = "shenbing_baoku"
            rank_val = item_data_dict.get('rank')
            if rank_val is None: return 0
            item_weight = items_manager._get_faqi_rank_weight(int(rank_val))  # 调用 Items 类的方法
            total_category_weight = items_manager.total_weight_faqi / 4  # 从 Items 实例获取
        elif item_type == "功法" or item_type == "辅修功法": # 主修功法
            pool_id = "wanggu_gongfa_ge"
            origin_level_val = item_data_dict.get('origin_level')
            if origin_level_val is None: return 0
            item_weight = items_manager._get_gongfa_origin_level_weight(int(origin_level_val))  # 调用 Items 类的方法
            total_category_weight = items_manager.total_weight_gongfa / 20  # 从 Items 实例获取
        elif item_type == "防具":
            pool_id = "xuanjia_baodian"
            rank_val = item_data_dict.get('rank')
            if rank_val is None: return 0
            item_weight = items_manager._get_fangju_rank_weight(int(rank_val))  # 调用 Items 类的方法
            total_category_weight = items_manager.total_weight_fangju / 2 # 从 Items 实例获取
        elif item_type == "神通":
            pool_id = "wanfa_baojian"
            origin_level_val = item_data_dict.get('origin_level')
            skill_type_from_data = item_data_dict.get('skill_type') # 1, 2, 3, 4
            if origin_level_val is None or skill_type_from_data is None: return 0

            item_weight = items_manager._get_shengtong_level_weight(int(origin_level_val))  # 调用 Items 类的方法

            # 获取神通子类别及其在池子中的概率
            pool_config_for_shengtong = self.xiu_config.gacha_pools_config.get(pool_id, {})
            shengtong_type_rates = pool_config_for_shengtong.get('shengtong_type_rate', {})

            # 映射 skill_type 到配置中的 key
            st_type_key_in_config = None
            if skill_type_from_data == 1: st_type_key_in_config = "attack"
            elif skill_type_from_data == 3: st_type_key_in_config = "support_debuff"
            elif skill_type_from_data in [2, 4]: st_type_key_in_config = "dot_control"

            if not st_type_key_in_config: return 0

            prob_of_this_st_type = shengtong_type_rates.get(st_type_key_in_config, 0)
            if prob_of_this_st_type == 0: return 0

            total_category_weight = items_manager.total_weight_shengtong_by_type.get(st_type_key_in_config,
                                                                                     1)  # 从 Items 实例获取
            if total_category_weight == 0: return 0

            # 神通的 P(item_i_within_main_category) 需要额外乘以其子类别的选中概率
            # P(item_i_within_shengtong_pool) = P(type_X) * (Weight(item_i) / TotalWeight(type_X_items))
            main_item_rate_from_pool = main_item_rate_from_pool * prob_of_this_st_type * 10
        else:
            return 0 # 不可抵押的类型

        pool_config_for_cost = self.xiu_config.gacha_pools_config.get(pool_id)
        if not pool_config_for_cost: return 0
        single_pull_cost = pool_config_for_cost['single_cost']

        if total_category_weight == 0: # 避免除以零
            logger.warning(f"计算抵押价值时，物品类型 {item_type} 的总权重为0。")
            return 0

        prob_within_category = item_weight / total_category_weight
        overall_prob = main_item_rate_from_pool * prob_within_category

        if overall_prob == 0: # 避免除以零
            logger.warning(f"计算抵押价值时，物品 {item_data_dict.get('name')} 的综合概率为0。")
            return 0

        expected_cost = single_pull_cost / overall_prob
        loan_amount = int(expected_cost / 10) # 期望成本的一半

        # 可以设置一个最低贷款额，例如至少100灵石，避免过低的无意义贷款
        return max(100, loan_amount) if loan_amount > 0 else 0

    def get_user_active_mortgages(self, user_id: str) -> list[dict]:
        """获取用户所有状态为 'active' 的抵押记录"""
        cur = self.conn.cursor()
        cur.execute(
            "SELECT mortgage_id, item_name, item_type, loan_amount, due_time FROM user_mortgage WHERE user_id = ? AND status = 'active' ORDER BY due_time ASC",
            (user_id,)
        )
        rows = cur.fetchall()
        mortgages = []
        if rows:
            columns = [desc[0] for desc in cur.description]
            for row in rows:
                mortgages.append(dict(zip(columns, row)))
        return mortgages

    def create_mortgage(self, user_id: str, item_id_in_backpack_str: str, item_name_in_backpack: str,
                        due_days: int = 30) -> tuple[bool, str]:
        """
        创建一个新的抵押记录。
        :param item_id_in_backpack_str: 玩家背包中物品的ID (通常是其在 items.json 中的原始ID，字符串形式)
        :param item_name_in_backpack: 玩家背包中物品的名称 (用于从背包移除)
        :param due_days: 抵押期限（天）
        :return: (success: bool, message: str)
        """
        user_info = self.get_user_message(user_id)
        if not user_info:
            return False, "用户信息不存在。"

        # 1. 从背包中找到该物品并获取其完整信息
        # 注意：get_item_by_name 返回的是 BackpackItem 具名元组，我们需要原始物品数据
        # 我们需要通过 item_id_in_backpack_str 从 Items() 获取物品的权威数据
        item_data_dict = self.items.get_data_by_item_id(int(item_id_in_backpack_str))
        if not item_data_dict:
            return False, f"错误：无法在物品库中找到ID为 {item_id_in_backpack_str} 的物品定义。"

        # 2. 检查物品是否可抵押 (类型检查)
        allowed_mortgage_types = ["法器", "功法", "防具", "神通"]
        if item_data_dict.get('item_type') not in allowed_mortgage_types:
            return False, f"【{item_name_in_backpack}】的类型不可抵押。"

        # 3. 计算贷款额度
        loan_amount = self.get_item_mortgage_loan_amount(item_id_in_backpack_str, item_data_dict)
        if loan_amount <= 0:
            return False, f"【{item_name_in_backpack}】价值过低或无法评估，无法抵押。"

        # 4. 从玩家背包移除物品 (假设一次抵押一件)
        if not self.remove_item(user_id, item_name_in_backpack, 1):
            return False, f"抵押失败：从背包移除【{item_name_in_backpack}】时出错，可能数量不足。"

        # 5. 记录抵押信息
        mortgage_time = datetime.now()
        due_time = mortgage_time + timedelta(days=due_days)
        item_data_json_str = json.dumps(item_data_dict, ensure_ascii=False)

        try:
            cur = self.conn.cursor()
            cur.execute(
                """
                INSERT INTO user_mortgage 
                (user_id, item_id_original, item_name, item_type, item_data_json, loan_amount, mortgage_time, due_time, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active')
                """,
                (user_id, int(item_id_in_backpack_str), item_name_in_backpack, item_data_dict.get('item_type'),
                 item_data_json_str, loan_amount, str(mortgage_time), str(due_time))
            )
            # 6. 发放贷款给玩家
            self.update_ls(user_id, loan_amount, 1)  # 1 代表增加
            self.conn.commit()
            return True, f"成功将【{item_name_in_backpack}】抵押给银行，获得贷款 {loan_amount} 灵石！请在 {due_days} 天内（{due_time.strftime('%Y-%m-%d %H:%M')}前）赎回。"
        except Exception as e:
            logger.error(f"创建抵押记录失败 for user {user_id}, item {item_name_in_backpack}: {e}")
            # 尝试回滚背包操作（如果可能且必要）
            self.add_item(user_id, int(item_id_in_backpack_str), item_data_dict.get('item_type'), 1)
            return False, "抵押过程中发生数据库错误，操作已取消。"

    def redeem_mortgage(self, user_id: str, mortgage_id: int) -> tuple[bool, str]:
        """处理赎回操作"""
        user_info = self.get_user_message(user_id)
        if not user_info:
            return False, "用户信息不存在。"

        cur = self.conn.cursor()
        cur.execute(
            "SELECT item_id_original, item_name, item_type, item_data_json, loan_amount, status, due_time FROM user_mortgage WHERE mortgage_id = ? AND user_id = ?",
            (mortgage_id, user_id)
        )
        mortgage_record = cur.fetchone()

        if not mortgage_record:
            return False, "未找到该抵押记录，或此记录不属于你。"

        record_dict = dict(zip([desc[0] for desc in cur.description], mortgage_record))

        if record_dict['status'] != 'active':
            return False, f"此抵押品【{record_dict['item_name']}】的状态为 {record_dict['status']}，无法赎回。"

        # 检查是否逾期 (虽然我们有单独的处理函数，但赎回时也应检查)
        due_time_obj = datetime.fromisoformat(record_dict['due_time'])
        if datetime.now() > due_time_obj:
            # 自动处理为逾期并没收
            cur.execute("UPDATE user_mortgage SET status = 'expired' WHERE mortgage_id = ?", (mortgage_id,))
            self.conn.commit()
            return False, f"抵押品【{record_dict['item_name']}】已于 {due_time_obj.strftime('%Y-%m-%d %H:%M')} 到期，已被银行没收。"

        # 计算应还金额 (当前无利息，即为贷款金额)
        amount_to_repay = record_dict['loan_amount']

        if user_info.stone < amount_to_repay:
            return False, f"灵石不足！赎回【{record_dict['item_name']}】需要 {amount_to_repay} 灵石。"

        try:
            # 1. 扣除玩家灵石
            self.update_ls(user_id, amount_to_repay, 2)  # 2 代表减少
            # 2. 将物品添加回玩家背包
            # item_data_original = json.loads(record_dict['item_data_json']) # 理论上不需要，因为 item_type 和 item_id_original 足够
            self.add_item(user_id, record_dict['item_id_original'], record_dict['item_type'], 1)
            # 3. 更新抵押记录状态
            cur.execute("UPDATE user_mortgage SET status = 'redeemed' WHERE mortgage_id = ?", (mortgage_id,))
            self.conn.commit()
            return True, f"成功赎回【{record_dict['item_name']}】，花费 {amount_to_repay} 灵石。"
        except Exception as e:
            logger.error(f"赎回抵押品失败 for user {user_id}, mortgage_id {mortgage_id}: {e}")
            # 此处可能需要更复杂的事务回滚，但暂时简化
            return False, "赎回过程中发生数据库错误。"

    def check_and_handle_expired_mortgages(self, user_id_filter: str = None):
        """检查并处理所有（或特定用户的）逾期抵押，将其状态更新为 'expired' (没收)"""
        now_str = str(datetime.now())
        cur = self.conn.cursor()
        if user_id_filter:
            cur.execute(
                "UPDATE user_mortgage SET status = 'expired' WHERE user_id = ? AND status = 'active' AND due_time < ?",
                (user_id_filter, now_str)
            )
        else:
            cur.execute(
                "UPDATE user_mortgage SET status = 'expired' WHERE status = 'active' AND due_time < ?",
                (now_str,)
            )
        expired_count = cur.rowcount
        self.conn.commit()
        if expired_count > 0:
            logger.info(f"处理了 {expired_count} 条逾期抵押记录，已将其标记为 'expired' (没收)。")
        return expired_count
