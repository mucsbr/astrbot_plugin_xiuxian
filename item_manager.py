import json
import os
from pathlib import Path
from typing import List

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
        self._initialized = True

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
