import json
import os
from pathlib import Path
from typing import List
from astrbot.api import logger

# 定义数据文件所在的根目录
DATABASE = Path() / "data" / "xiuxian"
SKILL_PATH = DATABASE / "功法"
WEAPON_PATH = DATABASE / "装备"
ELIXIR_PATH = DATABASE / "丹药"
XIULIAN_ITEM_PATH = DATABASE / "修炼物品"

class Items:
    """
    一个用于加载和管理所有游戏物品、功法、装备等数据的单例类。
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Items, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
            
        self.items = {}
        self._load_all_items()
        self.prepared_faqi_pool = []
        self.total_weight_faqi = 700
        self.prepared_gongfa_pool = []
        self.total_weight_gongfa = 700
        self.prepared_fangju_pool = []
        self.total_weight_fangju = 700
        self.prepared_shengtongs_pool_by_type = {"attack": [], "support_debuff": [], "dot_control": []}
        self.total_weight_shengtong_by_type = {"attack": 100, "support_debuff": 100, "dot_control": 100}

        self._prepare_gacha_pools_data()  # 再进行抽奖数据的预处理
        self._initialized = True


    def _get_gongfa_origin_level_weight(self, origin_level_value: int) -> int:
        """
        根据主修功法的 origin_level 值（即 item_manager 交换前的 level 值，越小越稀有）
        返回其在抽奖池中的权重。
        主修功法 origin_level from 主功法.json: 50 (人阶下品) down to 18 (仙阶下品).
        """
        # 权重分配策略：origin_level 值越小（越稀有），权重越低。
        # 这个权重可以参考法器的，或者根据功法的重要性进行调整。
        if origin_level_value >= 48: return 150  # 人阶下品 (origin_level 50, 49, 48)
        if origin_level_value >= 43: return 90  # 人阶上品 (origin_level 45, 44, 43)
        if origin_level_value >= 37: return 50  # 黄阶下品 (origin_level 42, 41, 40, 39, 38, 37)
        if origin_level_value >= 31: return 20  # 黄阶上品 (origin_level 36, 35, 34, 33, 32, 31)
        if origin_level_value >= 28: return 10  # 玄阶下品 (origin_level 30, 29, 28)
        if origin_level_value >= 25: return 6  # 玄阶上品 (origin_level 27, 26, 25)
        if origin_level_value >= 20: return 2  # 地阶 (origin_level 24, 23, 22, 21, 20)
        if origin_level_value >= 18: return 1  # 天阶/仙阶 (origin_level 18)
        return 1

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
        return 1 # 对于超出预期范围的level，给予最低权重

    def _get_faqi_rank_weight(self, rank_value: int) -> int:
        """
        根据法器的 rank 值（越小越稀有）返回其在抽奖池中的权重。
        法器 ranks from 法器.json: 50 (common) down to 18 (rare).
        权重分配策略：rank 值越小（越稀有），权重越低。
        """
        # 示例权重，您可以根据实际稀有度分布调整
        if rank_value >= 48: return 150  # 例如：rank 50, 49, 48 (对应 "下品符器" 等级)
        if rank_value >= 43: return 90  # 例如：rank 47-43 (对应 "上品符器" 等级)
        if rank_value >= 37: return 40  # 例如：rank 42-37 (对应 "下品法器" 等级)
        if rank_value >= 31: return 20  # 例如：rank 36-31 (对应 "上品法器" 等级)
        if rank_value >= 28: return 8  # 例如：rank 30-28 (对应 "下品纯阳法器" 等级)
        if rank_value >= 25: return 5  # 例如：rank 27-25 (对应 "上品纯阳法器"/"下品通天法器" 等级)
        if rank_value >= 20: return 2  # 例如：rank 24-20 (对应 "上品通天法器"/"下品仙器" 等级)
        if rank_value >= 18: return 1  # 例如：rank 18 (对应 "上品仙器" 等级)
        return 1  # 对于超出预期范围的rank，给予最低权重

    def _get_fangju_rank_weight(self, rank_value: int) -> int:
        """
        根据防具的 rank 值（越小越稀有）返回其在抽奖池中的权重。
        防具 ranks from 防具.json: 50 (common) down to 18 (rare).
        权重分配策略：rank 值越小（越稀有），权重越低。
        """
        # 权重可以参考法器的，或根据实际稀有度分布调整
        if rank_value >= 48: return 160  # 例如：rank 50, 49, 48
        if rank_value >= 43: return 100  # 例如：rank 47-43
        if rank_value >= 37: return 60  # 例如：rank 42-37
        if rank_value >= 31: return 30  # 例如：rank 36-31
        if rank_value >= 28: return 15  # 例如：rank 30-28
        if rank_value >= 25: return 9  # 例如：rank 27-25
        if rank_value >= 20: return 2  # 例如：rank 24-20
        if rank_value >= 18: return 1  # 例如：rank 18
        return 1

    def _create_weighted_item_entry(self, item_id_str: str, item_data: dict, weight_func, rank_field_name: str,
                                    default_name_prefix: str):
        rank_val = item_data.get(rank_field_name)
        if rank_val is None:
            logger.warning(
                f"{default_name_prefix} {item_data.get('name', item_id_str)} 缺少 '{rank_field_name}' 字段，跳过。")
            return None
        try:
            rank_int = int(rank_val)
        except (ValueError, TypeError):
            logger.warning(
                f"{default_name_prefix} {item_data.get('name', item_id_str)} 的 '{rank_field_name}' 值 '{rank_val}' 不是有效整数，跳过。")
            return None
        weight = weight_func(rank_int)
        return {
            "id": item_id_str,
            "name": item_data.get('name', f"{default_name_prefix}{item_id_str}"),
            rank_field_name: rank_int,  # 存储用于判断稀有度的字段
            "weight": weight,
            "data": item_data
        }

    def _prepare_gacha_pools_data(self):
        """预处理所有用于抽奖的物品池数据"""
        # 法器
        faqi_raw = self.get_data_by_item_type(['法器'])
        for item_id, data in faqi_raw.items():
            entry = self._create_weighted_item_entry(item_id, data, self._get_faqi_rank_weight, 'rank', "未知法器")
            if entry: self.prepared_faqi_pool.append(entry)
        if self.prepared_faqi_pool:
            self.total_weight_faqi = sum(item['weight'] for item in self.prepared_faqi_pool)

        # 功法
        gongfa_raw = self.get_data_by_item_type(['功法', '辅修功法'])
        for item_id, data in gongfa_raw.items():
            entry = self._create_weighted_item_entry(item_id, data, self._get_gongfa_origin_level_weight, 'origin_level', "未知功法")
            if entry: self.prepared_gongfa_pool.append(entry)
        if self.prepared_gongfa_pool:
            self.total_weight_gongfa = sum(item['weight'] for item in self.prepared_gongfa_pool)

        # 防具
        fangju_raw = self.get_data_by_item_type(['防具'])
        for item_id, data in fangju_raw.items():
            entry = self._create_weighted_item_entry(item_id, data, self._get_fangju_rank_weight, 'rank', "未知防具")
            if entry: self.prepared_fangju_pool.append(entry)
        if self.prepared_fangju_pool:
            self.total_weight_fangju = sum(item['weight'] for item in self.prepared_fangju_pool)

        # 神通
        shengtong_raw = self.get_data_by_item_type(['神通'])
        for item_id, data in shengtong_raw.items():
            entry = self._create_weighted_item_entry(item_id, data, self._get_shengtong_level_weight, 'origin_level', "未知神通")
            if entry:
                skill_type = data.get('skill_type')
                if skill_type == 1:
                    self.prepared_shengtongs_pool_by_type["attack"].append(entry)
                elif skill_type == 3:
                    self.prepared_shengtongs_pool_by_type["support_debuff"].append(entry)
                elif skill_type == 2 or skill_type == 4:
                    self.prepared_shengtongs_pool_by_type["dot_control"].append(entry)

        for st_type in self.prepared_shengtongs_pool_by_type:
            if self.prepared_shengtongs_pool_by_type[st_type]:
                self.total_weight_shengtong_by_type[st_type] = sum(item['weight'] for item in self.prepared_shengtongs_pool_by_type[st_type])

        logger.info("抽奖物品池数据预处理完成。")
        logger.info(f"法器总权重: {self.total_weight_faqi}, 功法总权重: {self.total_weight_gongfa}, 防具总权重: {self.total_weight_fangju}")
        logger.info(f"神通各类型总权重: {self.total_weight_shengtong_by_type}")




    def _load_all_items(self):
        """加载所有数据文件并整合"""
        # 定义所有需要加载的数据源及其类型
        data_sources = {
            "防具": WEAPON_PATH / "防具.json",
            "法器": WEAPON_PATH / "法器.json",
            "功法": SKILL_PATH / "主功法.json",
            "辅修功法": SKILL_PATH / "辅修功法.json",
            "神通": SKILL_PATH / "神通.json",
            "丹药": ELIXIR_PATH / "丹药.json",
            "商店丹药": ELIXIR_PATH / "商店丹药.json",
            "药材": ELIXIR_PATH / "药材.json",
            "合成丹药": ELIXIR_PATH / "炼丹丹药.json",
            "炼丹炉": ELIXIR_PATH / "炼丹炉.json",
            "聚灵旗": XIULIAN_ITEM_PATH / "聚灵旗.json",
        }

        for item_type, path in data_sources.items():
            try:
                data = self._read_json_file(path)
                self._process_and_set_item_data(data, item_type)
            except FileNotFoundError:
                # 在这里可以添加日志记录，但在教学场景中我们假设文件都已存在
                print(f"警告: 未找到数据文件 {path}")
                continue
            except Exception as e:
                print(f"加载文件 {path} 时出错: {e}") # 在实际插件中用 logger
    
    def _read_json_file(self, file_path: Path):
        """读取指定的JSON文件"""
        with open(file_path, "r", encoding="UTF-8") as f:
            return json.load(f)

    def _process_and_set_item_data(self, data_dict: dict, item_type: str):
        """处理原始数据并存入 self.items"""
        for k, v in data_dict.items():
            # 兼容原版功法/神通JSON中的 'level' 和 'rank' 字段混淆
            if item_type in ['功法', '神通', '辅修功法']:
                # 在这里交换 'rank' 和 'level' 的值
                v['origin_level'] = v.get('level', 1)
                v['rank'], v['level'] = v.get('level', "未知"), v.get('rank', "未知品阶")
                v['type'] = '技能'
            
            self.items[k] = v
            self.items[k]['item_type'] = item_type

    def get_data_by_item_id(self, item_id: int):
        """通过物品ID获取其详细信息"""
        return self.items.get(str(item_id))

    def get_data_by_item_type(self, item_types: List[str]) -> dict:
        """根据一个或多个物品类型获取所有匹配的物品"""
        temp_dict = {}
        for k, v in self.items.items():
            if v.get('item_type') in item_types:
                temp_dict[k] = v
        return temp_dict
    
    def get_all_items(self) -> dict:
        """获取所有物品的数据"""
        return self.items

        # --- 新增一个专门获取商店丹药的方法 (可选，但更清晰) ---
    def get_shop_dan_yao_items(self) -> list:
        """获取所有标记为 '商店丹药' 类型的物品，并进行格式化和排序"""
        shop_items_raw = self.get_data_by_item_type(["商店丹药"])
        shop_items_list = []
        if shop_items_raw:
            for item_id, item_info in shop_items_raw.items():
                if item_info.get("status", 0) == 1: # 只处理 status 为 1 的
                    shop_items_list.append({
                        "id": item_id,
                        "name": item_info.get("name", "未知丹药"),
                        "price": item_info.get("price", 999999),
                        "desc": item_info.get("desc", "效果未知"),
                        "require_level": item_info.get("境界", "无要求"),
                        "item_type_from_data": item_info.get("type", "丹药"), # 从JSON中读取的type
                        "item_type_internal": item_info.get("item_type"), # Manager赋予的类型，应该是"商店丹药"
                        "raw_info": item_info
                    })
            # 按照境界要求（品阶数字小的在前）和价格排序
            # 需要 USERRANK 字典，这里暂时不导入，实际应从config获取或传入
            # from .config import USERRANK # 假设可以这样导入
            # shop_items_list.sort(key=lambda x: (USERRANK.get(x["require_level"], 99), x["price"]))
            # 简化排序：
            shop_items_list.sort(key=lambda x: x["price"])
        return shop_items_list
