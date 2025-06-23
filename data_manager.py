from pathlib import Path
import json
from astrbot.api import logger

# 定义数据文件所在的根目录
DATABASE = Path() / "data" / "xiuxian"

class DataManager:
    """
    处理JSON数据，加载游戏核心规则
    """

    def __init__(self):
        """定义所有数据文件的路径"""
        self.root_jsonpath = DATABASE / "灵根.json"
        self.level_rate_jsonpath = DATABASE / "突破概率.json"
        self.level_jsonpath = DATABASE / "境界.json"
        self.sect_json_path = DATABASE / "宗门玩法配置.json"
        self.physique_jsonpath = DATABASE / "炼体境界.json"

    def _read_json_file(self, file_path):
        """通用JSON文件读取方法"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            # 在实际使用中，如果文件丢失，这将是一个严重问题。
            # 此处打印错误并返回空字典，以防程序完全崩溃。
            print(f"错误: 未找到数据文件 {file_path}")
            return {}

    def level_data(self):
        """获取境界数据"""
        return self._read_json_file(self.level_jsonpath)

    def sect_config_data(self):
        """获取宗门玩法配置"""
        return self._read_json_file(self.sect_json_path)

    def root_data(self):
        """获取灵根数据"""
        return self._read_json_file(self.root_jsonpath)

    def level_rate_data(self):
        """获取境界突破概率"""
        return self._read_json_file(self.level_rate_jsonpath)
        
    def physique_data(self):
        """获取炼体境界数据"""
        return self._read_json_file(self.physique_jsonpath)
    # ==================================
# === 在 data_manager.py 的 DataManager 类中追加 ===
# ==================================

    def get_shop_data(self) -> dict:
        """获取坊市商品数据"""
        shop_path = DATABASE / "goods.json"
        return self._read_json_file(shop_path)
    # ==================================
# === 在 data_manager.py 的 DataManager 类中追加 ===
# ==================================

    def get_bounty_data(self) -> dict:
        """获取悬赏令数据"""
        bounty_path = DATABASE / "悬赏令.json"
        return self._read_json_file(bounty_path)

    def get_rift_data(self) -> dict:
        """获取秘境数据"""
        rift_path = DATABASE / "rift.json"
        return self._read_json_file(rift_path)

    def get_goods_data(self) -> dict:
        """获取坊市基础商品数据"""
        goods_path = DATABASE / "goods.json"
        return self._read_json_file(goods_path)


# 创建一个全局实例，方便其他文件直接导入使用
jsondata = DataManager()
