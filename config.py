import yaml
from pathlib import Path

# 定义数据文件所在的根目录
DATABASE = Path() / "data" / "xiuxian"

class XiuConfig:
    """
    集中管理插件的所有静态配置
    """
    def __init__(self):
        # 从 YAML 文件加载配置
        config_yaml_path = DATABASE / "config.yaml"
        try:
            with open(config_yaml_path, 'r', encoding='utf-8') as f:
                config_data = yaml.safe_load(f)
        except FileNotFoundError:
            # 如果配置文件不存在，使用默认值
            config_data = {
                'level': ["江湖好手", "练气境初期", "练气境中期", "练气境圆满", "筑基境初期", "筑基境中期", "筑基境圆满", "结丹境初期", "结丹境中期", "结丹境圆满", "元婴境初期", "元婴境中期", "元婴境圆满", "化神境初期", "化神境中期", "化神境圆满", "炼虚境初期", "炼虚境中期", "炼虚境圆满", "合体境初期", "合体境中期", "合体境圆满", "大乘境初期", "大乘境中期", "大乘境圆满", "渡劫境初期", "渡劫境中期", "渡劫境圆满", "半步真仙", "真仙境初期", "真仙境中期", "真仙境圆满", "金仙境初期", "金仙境中期", "金仙境圆满", "太乙境初期", "太乙境中期", "太乙境圆满", "化圣境一层", "化圣境二层", "化圣境三层", "化圣境四层", "化圣境五层", "化圣境六层", "化圣境七层", "化圣境八层", "化圣境九层"],
                'level_up_cd': 60,
                'closing_exp': 10,
                'closing_exp_upper_limit': 1.5,
                'level_punishment_floor': 1,
                'level_punishment_limit': 5,
                'level_up_probability': 0.1,
                'sign_in_lingshi_lower_limit': 5000,
                'sign_in_lingshi_upper_limit': 15000,
                'sign_in_xiuwei_lower_limit': 5000,
                'sign_in_xiuwei_upper_limit': 15000,
                'tou': 500,
                'tou_lower_limit': 300,
                'tou_upper_limit': 5000,
                'remake': 1000,
                'sect_min_level': "化神境圆满",
                'sect_create_cost': 50000,
                'user_info_cd': 30,
                'battle_boss_cd': 60,
            }

        # 基础配置
        self.level = config_data.get('level', [])
        self.level_up_cd = config_data.get("level_up_cd", 60)  # 境界突破CD 单位分钟
        self.closing_exp = config_data.get('closing_exp', 10)  # 闭关每分钟增加的修为
        self.closing_exp_upper_limit = config_data.get('closing_exp_upper_limit', 1.5)
        self.level_punishment_floor = config_data.get('level_punishment_floor', 1)
        self.level_punishment_limit = config_data.get('level_punishment_limit', 5)
        self.level_up_probability = config_data.get('level_up_probability', 0.1)
        self.sign_in_lingshi_lower_limit = config_data.get('sign_in_lingshi_lower_limit', 5000)
        self.sign_in_lingshi_upper_limit = config_data.get('sign_in_lingshi_upper_limit', 15000)
        self.sign_in_xiuwei_lower_limit = config_data.get('sign_in_xiuwei_lower_limit', 5000)
        self.sign_in_xiuwei_upper_limit = config_data.get('sign_in_xiuwei_upper_limit', 15000)
        self.remake = config_data.get('remake', 1000)  # 重入仙途的消费

        self.atk_practice_buff_per_level = config_data.get('atk_practice_buff_per_level', 0.04) # 每级攻击修炼提升4%攻击
        self.blessed_spot_exp_rate_per_level = config_data.get('blessed_spot_exp_rate_per_level', 0.1) # 洞天福地每级修炼速度加成

        # 突破死劫配置
        self.death_calamity_config = {
            "probability": 0.001, # 每次突破有 1% 的基础概率触发死劫
            "reincarnation_buff": {
                "name": "天道馈赠",
                "type": "reincarnation",
                "修炼速度加成": 0.2, # 转世后修炼速度永久提升 20%
                "持续时间": "永久"
            }
        }
        # 秘境配置
        self.rift_cost = 30000 # 探索一次秘境消耗的灵石
         # 秘境配置
        self.rift_config = {
            # key 是进入该秘境所需的最低 USERRANK 值 (数字越小境界越高)
            "50": { # 江湖好手及以上
                "name_pool": ["试炼之森", "新手村矿洞"],
                "floors": 5,
                "reward_multiplier": 1.0 # 奖励倍率
            },
            "44": { # 筑基境圆满及以上
                "name_pool": ["血色禁地", "无边沼泽"],
                "floors": 8,
                "reward_multiplier": 1.5
            },
            "38": { # 元婴境圆满及以上
                "name_pool": ["乱魔海", "鬼雾山脉"],
                "floors": 10,
                "reward_multiplier": 2.0
            },
            "32": { # 炼虚境圆满及以上
                "name_pool": ["堕神海域", "九幽深渊"],
                "floors": 12,
                "reward_multiplier": 2.5
            },
            "26": { # 大乘境圆满及以上
                "name_pool": ["昆仑墟", "太古神境"],
                "floors": 15,
                "reward_multiplier": 3.0
            }
        }
       # 炼丹配置 (虽然 alchemy_manager 中已实现，此处备用)
        self.alchemy_furnace_buff = {
            "初级炼丹炉": 0.05,
            "中级炼丹炉": 0.10,
            "高级炼丹炉": 0.20,
        }
                # v-- 在 __init__ 方法的末尾追加以下炼丹和功法配置 --v
        # 炼丹升级配置
        self.alchemy_config = {
            "收取等级": { # 每日从灵田收取的药材数量
                "1": {"level_up_cost": 1500},
                "2": {"level_up_cost": 3000},
                "3": {"level_up_cost": 6000}
            },
            "丹药控火": { # 炼丹时额外产出的丹药数量
                "1": {"level_up_cost": 10000},
                "2": {"level_up_cost": 15500}
            }
        }
        default_alchemy_level_up_config = {
            "收取等级": { # 每日从灵田收取的药材数量等级，每级提升采集数量
                "1": {"level_up_cost": 1500, "description": "提升至1级收取"}, # 假设从0级升到1级
                "2": {"level_up_cost": 3000, "description": "提升至2级收取"},
                "3": {"level_up_cost": 6000, "description": "提升至3级收取"}
                # 您可以根据需要添加更多等级
            },
            "丹药控火": { # 炼丹时额外产出的丹药数量等级，每级提升额外产出几率或数量
                "1": {"level_up_cost": 10000, "description": "提升至1级控火"},
                "2": {"level_up_cost": 15500, "description": "提升至2级控火"}
                # 您可以根据需要添加更多等级
            }
        }
        self.alchemy_level_up_config = config_data.get('alchemy_level_up_config', default_alchemy_level_up_config)

        # 洞天福地与灵田配置
        self.blessed_spot_cost = 500000  # 购买洞天福地所需灵石
        self.herb_gathering_config = {
            "time_cost": 1,  # 收取一次药材所需的基础时间（小时）
            "speed_up_rate": 0.05,  # 聚灵旗每级提升的收取速度
        }

        # 宗门功法和神通参数（原版中炼丹也可能产出，这里一并添加）
        self.sect_main_buff_config = {
            "获取消耗的资材": 600000,
            "获取消耗的灵石": 30000,
            "获取到功法的概率": 100,
            "建设度": 10000000,
            "学习资材消耗": 600000,
        }
        self.sect_sec_buff_config = {
            "获取消耗的资材": 600000,
            "获取消耗的灵石": 30000,
            "获取到神通的概率": 100,
            "建设度": 10000000,
            "学习资材消耗": 600000,
        }

       # 坊市系统自动上架配置
        self.market_auto_add_config = {
            "is_enabled": False, # 是否开启自动上架
            "cron_hours": "*/3", # 每3小时执行一次
            "item_pool": [ # 自动上架的物品池
                {"id": 1106, "price": 3000},  # 生骨丹
                {"id": 1105, "price": 3000},  # 生骨丹
                {"id": 1113, "price": 3000}  # 生骨丹
            ]
        }

        # 拍卖行配置
        self.auction_config = {
            "is_enabled": True, # 是否开启定时拍卖
            "cron_hour": 18, # 每天晚上18点开启
            "cron_minute": 0,
            "duration_seconds": 600, # 基础拍卖时长 10分钟
            "extension_seconds": 60, # 最后时刻出价的延长时间 1分钟
            "item_pool": [ # 拍卖物品池
                {"id": 1999, "start_price": 100000}, # 渡厄丹
                {"id": 9910, "start_price": 2500000}, # 元磁神光
                {"id": 9911, "start_price": 2500000}, # 天罗真功
                {"id": 8911, "start_price": 2500000}, # 大罗仙印
                {"id": 4001, "start_price": 10000},   # 寒铁铸心炉
            ]
        }

        # 宗门配置
        self.sect_min_level = config_data.get('sect_min_level', "化神境圆满")
        self.sect_create_cost = config_data.get('sect_create_cost', 50000)
        
        # 秘境探索CD配置
        self.rift_cd_minutes = 60
        # CD 配置
        self.user_info_cd = config_data.get('user_info_cd', 30)
        self.battle_boss_cd = config_data.get('battle_boss_cd', 1800)

        self.boss_config = {
            "Boss生成时间参数": {
                "hours": 0,
                "minutes": 50, # BOSS每50分钟刷新一次
            },
            "Boss个数上限": 15, # 这个在您的单BOSS模式下可以忽略
            "Boss名字": [
                "墨蛟", "婴鲤兽", "千目妖", "鸡冠蛟", "妖冠蛇", "铁火蚁", "天晶蚁", "银光鼠", "紫云鹰", "狗青",
                "吞海鱼", "银翼鸟", "琉璃兽", "鹰鸢兽", "盘黎蚓", "卧虎鲨", "火鳞兽", "狡狰兽", "罗睺", "碧蟾兽",
                "玄岩龟", "吸魔蚁", "铁牙兽", "雪吼兽", "雷兽", "雷龟", "冥雷兽", "九头鸟", "多眼魔", "镇海猿",
                "青夜蟒", "飞虹鱼", "血蛊虫", "碧木妖", "鹿面妖", "三目苍鼠"
            ],
            "Boss倍率": {
                # Boss属性：基于境界的修为值进行倍率计算
                "气血": 20,
                "真元": 5,
                "攻击": 0.2
            },
            "Boss灵石": {
                # 不同境界BOSS的基础灵石奖励
                '江湖好手': 2000, '练气境初期': 5000, '练气境中期': 5000, '练气境圆满': 5000,
                '筑基境初期': 10000, '筑基境中期': 10000, '筑基境圆满': 10000, '结丹境初期': 20000,
                '结丹境中期': 20000, '结丹境圆满': 20000, '元婴境初期': 30000, '元婴境中期': 30000,
                '元婴境圆满': 30000, '化神境初期': 60000, '化神境中期': 60000, '化神境圆满': 60000,
                '炼虚境初期': 120000, '炼虚境中期': 120000, '炼虚境圆满': 120000, '合体境初期': 240000,
                '合体境中期': 240000, '合体境圆满': 240000, '大乘境初期': 800000, '大乘境中期': 800000,
                '大乘境圆满': 800000, '渡劫境初期': 1800000, '渡劫境中期': 1800000, '渡劫境圆满': 1800000,
                '半步真仙': 4000000, '真仙境初期': 4000000, '真仙境中期': 4000000, '真仙境圆满': 4000000,
                '金仙境初期': 10000000, '金仙境中期': 10000000, '金仙境圆满': 10000000, '太乙境初期': 25000000,
                '太乙境中期': 25000000, '太乙境圆满': 25000000
            }
        }
        # 世界BOSS掉落物配置
        self.boss_drop_config = {
            "default_drop_pool": [ # 默认掉落池
                {"id": 4003, "rate": 30},  # 陨铁炉, 30%概率
                {"id": 4002, "rate": 10},  # 雕花紫铜炉, 10%概率
                {"id": 4001, "rate": 2},   # 寒铁铸心炉, 2%概率
                {"id": 2500, "rate": 20},  # 一级聚灵旗, 20%概率
                {"id": 2501, "rate": 5},   # 二级聚灵旗, 5%概率
            ],
            "final_hit_bonus": { # 对BOSS造成最后一击的额外奖励
                "exp_rate": 0.1,    # 额外获得BOSS总经验10%的修为
                "stone_rate": 0.1,  # 额外获得BOSS总灵石10%的灵石
            }
        }
        self.closing_hp_heal_rate = 2000
        # 新增：万法宝鉴抽卡池配置
        self.gacha_pools_config = {
            "wanfa_baojian": {
                "name": "万法宝鉴",
                "single_cost": 10000, # 单抽消耗灵石
                "multi_cost": 90000,  # 十连抽消耗灵石
                "item_categories_rate": { # 单抽时各大类物品的概率 (总和为1.0)
                    "shengtong": 0.05,  # 抽中神通的概率
                    "lingshi": 0.95,   # 抽中灵石的概率
                },
                "shengtong_type_rate": { # 在抽中神通的前提下，不同类型神通的概率 (总和为1.0)
                    "attack": 0.10,      # skill_type: 1 (直接伤害)
                    "support_debuff": 0.50, # skill_type: 3 (Buff/Debuff)
                    "dot_control": 0.40  # skill_type: 2 (持续伤害), skill_type: 4 (控制)
                },
                "lingshi_rewards": [ # 灵石奖励池和对应的权重
                    {"amount_range": [500, 1000], "weight": 60},
                    {"amount_range": [1001, 2500], "weight": 30},
                    {"amount_range": [2501, 5000], "weight": 10}
                ],
                "ten_pull_guarantee": {
                    "enabled": True,
                    "guaranteed_item_type": "shengtong", # 保底类型为神通
                    "replacement_priority": ["lingshi"] # 如果十连无神通，优先替换灵石类奖励
                }
            }
        }
        
        # 功能开关
        self.img = True # 是否全部转为简单图片发送
        self.cmd_img = False # 是否全部转为简单图片发送

                # 新增PVP相关配置
        self.spar_cd_minutes = config_data.get('spar_cd_minutes', 5) # 切磋CD，默认5分钟
        self.rob_cd_minutes = config_data.get('rob_cd_minutes', 10)   # 抢劫CD，默认10分钟
        self.robbed_protection_cd_minutes = config_data.get('robbed_protection_cd_minutes', 5) # 被抢劫后的保护CD，默认5分

        # 世界BOSS按境界划分的掉落表
        self.boss_drops_by_level_range = {
            # --- 初期阶段 ---
            "江湖好手": { # 假设有对应此境界的BOSS，实际可能从练气开始
                "final_hit_bonus": {"exp_rate": 0.08, "stone_rate": 0.08,
                                    "extra_items": [
                                        {"id": 1101, "rate": 30, "type": "丹药", "quantity": [1, 2]} # 生骨丹
                                    ]},
                "participant_drop_pool": [
                    {"id": 0, "rate": 100, "type": "灵石", "amount": [500, 1500]}, # 参与保底灵石
                    {"id": 3001, "rate": 60, "type": "药材", "quantity": [2, 4]},   # 恒心草
                    {"id": 7001, "rate": 15, "type": "法器"},                         # 精铁符剑
                    {"id": 6001, "rate": 15, "type": "防具"},                         # 修士道袍
                    {"id": 9001, "rate": 10, "type": "功法"},                         # 吐纳功法
                ]
            },
            "练气境": { # 包含练气初期、中期、圆满的BOSS
                "final_hit_bonus": {"exp_rate": 0.1, "stone_rate": 0.1,
                                    "extra_items": [
                                        {"id": 1101, "rate": 50, "type": "丹药", "quantity": [1, 3]} # 生骨丹
                                    ]},
                "participant_drop_pool": [
                    {"id": 0, "rate": 100, "type": "灵石", "amount": [1000, 3000]},
                    {"id": 3001, "rate": 70, "type": "药材", "quantity": [3, 5]},   # 恒心草
                    {"id": 3002, "rate": 50, "type": "药材", "quantity": [2, 4]},   # 红绫草
                    {"id": 7002, "rate": 20, "type": "法器"},                         # 桃木符剑
                    {"id": 6001, "rate": 20, "type": "防具"},                         # 修士道袍
                    {"id": 9002, "rate": 15, "type": "功法"},                         # 冰心诀
                    {"id": 8001, "rate": 5, "type": "神通"},                          # 灵光印 (秘籍)
                ]
            },
            "筑基境": {
                "final_hit_bonus": {"exp_rate": 0.12, "stone_rate": 0.12,
                                    "extra_items": [
                                        {"id": 1102, "rate": 40, "type": "丹药", "quantity": [1, 2]}, # 化瘀丹
                                        {"id": 1400, "rate": 10, "type": "合成丹药"} # 筑基丹 (稀有)
                                    ]},
                "participant_drop_pool": [
                    {"id": 0, "rate": 100, "type": "灵石", "amount": [3000, 7000]},
                    {"id": 3005, "rate": 60, "type": "药材", "quantity": [2, 4]},   # 五柳根
                    {"id": 3009, "rate": 40, "type": "药材", "quantity": [1, 3]},   # 紫猴花
                    {"id": 7011, "rate": 25, "type": "法器"},                         # 火铜符剑
                    {"id": 6011, "rate": 25, "type": "防具"},                         # 化尘道袍
                    {"id": 9011, "rate": 18, "type": "功法"},                         # 禾山经 (人阶上品)
                    {"id": 8101, "rate": 8, "type": "神通"},                          # 化尘剑法 (人阶上品)
                    {"id": 10001, "rate": 5, "type": "辅修功法"}                      # 饮血术 (人阶下品)
                ]
            },
            # --- 中期阶段 ---
            "结丹境": {
                "final_hit_bonus": {"exp_rate": 0.13, "stone_rate": 0.13,
                                    "extra_items": [
                                        {"id": 1103, "rate": 35, "type": "丹药", "quantity": [1, 2]}, # 固元丹
                                        {"id": 1401, "rate": 8, "type": "合成丹药"}  # 聚顶丹
                                    ]},
                "participant_drop_pool": [
                    {"id": 0, "rate": 100, "type": "灵石", "amount": [7000, 15000]},
                    {"id": 3013, "rate": 50, "type": "药材", "quantity": [2, 4]},   # 血莲精 (四品)
                    {"id": 3037, "rate": 40, "type": "药材", "quantity": [2, 3]},   # 宁心草 (一品，但可能用于高级丹药)
                    {"id": 7021, "rate": 20, "type": "法器"},                         # 辟邪惊雷尺 (下品法器)
                    {"id": 6021, "rate": 20, "type": "防具"},                         # 阴磷甲 (下品玄器)
                    {"id": 9101, "rate": 15, "type": "功法"},                         # 长生诀 (黄阶下品)
                    {"id": 8201, "rate": 7, "type": "神通"},                          # 竹山剑法 (黄阶下品)
                    {"id": 10101, "rate": 6, "type": "辅修功法"}                      # 长生诀(辅修) (黄阶下品)
                ]
            },
            "元婴境": {
                "final_hit_bonus": {"exp_rate": 0.14, "stone_rate": 0.14,
                                    "extra_items": [
                                        {"id": 1104, "rate": 30, "type": "丹药", "quantity": [1, 1]}, # 培元丹
                                        {"id": 2000, "rate": 10, "type": "合成丹药"} # 洗髓丹
                                    ]},
                "participant_drop_pool": [
                    {"id": 0, "rate": 100, "type": "灵石", "amount": [15000, 30000]},
                    {"id": 3017, "rate": 50, "type": "药材", "quantity": [1, 3]},   # 地心火芝 (五品)
                    {"id": 3041, "rate": 40, "type": "药材", "quantity": [1, 3]},   # 流莹草 (二品)
                    {"id": 7031, "rate": 18, "type": "法器"},                         # 金光镜 (上品法器)
                    {"id": 6031, "rate": 18, "type": "防具"},                         # 御灵盾 (上品玄器)
                    {"id": 9201, "rate": 12, "type": "功法"},                         # 万木诀 (黄阶上品)
                    {"id": 8301, "rate": 6, "type": "神通"},                          # 五毒摄魂阵 (黄阶上品)
                    {"id": 10102, "rate": 5, "type": "辅修功法"}                      # 养刀术 (黄阶下品)
                ]
            },
            "化神境": {
                "final_hit_bonus": {"exp_rate": 1.5, "stone_rate": 0.15,
                                    "extra_items": [
                                        {"id": 1105, "rate": 25, "type": "丹药"}, # 黄龙丹
                                        {"id": 2009, "rate": 5, "type": "合成丹药"}  # 摄魂鬼丸 (加攻击)
                                    ]},
                "participant_drop_pool": [
                    {"id": 0, "rate": 100, "type": "灵石", "amount": [130000, 160000]},
                    {"id": 3021, "rate": 45, "type": "药材", "quantity": [1, 2]},   # 三叶青芝 (六品)
                    {"id": 3045, "rate": 35, "type": "药材", "quantity": [1, 2]},   # 轻灵草 (三品)
                    {"id": 7041, "rate": 15, "type": "法器"},                         # 离地焰光旗 (下品纯阳)
                    {"id": 6041, "rate": 15, "type": "防具"},                         # 凤血魔袍 (下品纯阳)
                    {"id": 9301, "rate": 10, "type": "功法"},                         # 水灵妙法 (玄阶下品)
                    {"id": 8401, "rate": 5, "type": "神通"},                          # 降魔锁骨阵 (玄阶下品)
                    {"id": 10201, "rate": 4, "type": "辅修功法"}                      # 方圆 (玄阶下品)
                ]
            },
            # --- 后期阶段 ---
            "炼虚境": {
                "final_hit_bonus": {"exp_rate": 1.6, "stone_rate": 0.16,
                                    "extra_items": [
                                        {"id": 1500, "rate": 15, "type": "丹药"}, # 冰心丹 (加突破概率)
                                        {"id": 4003, "rate": 5, "type": "炼丹炉"}  # 陨铁炉
                                    ]},
                "participant_drop_pool": [
                    {"id": 0, "rate": 100, "type": "灵石", "amount": [160000, 220000]},
                    {"id": 3025, "rate": 40, "type": "药材", "quantity": [1, 2]},   # 地心淬灵乳 (七品)
                    {"id": 7051, "rate": 12, "type": "法器"},                         # 五火七禽扇 (上品纯阳)
                    {"id": 6051, "rate": 12, "type": "防具"},                         # 避水法袍 (上品纯阳)
                    {"id": 9401, "rate": 8, "type": "功法"},                          # 混元引气诀 (玄阶上品)
                    {"id": 8501, "rate": 4, "type": "神通"},                          # 苍云荫月 (玄阶上品)
                    {"id": 10202, "rate": 3, "type": "辅修功法"}                      # 敛息术 (玄阶下品)
                ]
            },
            "合体境": {
                "final_hit_bonus": {"exp_rate": 1.7, "stone_rate": 0.17,
                                    "extra_items": [
                                        {"id": 1501, "rate": 12, "type": "丹药"}, # 明心丹
                                        {"id": 2500, "rate": 8, "type": "聚灵旗"} # 一级聚灵旗
                                    ]},
                "participant_drop_pool": [
                    {"id": 0, "rate": 100, "type": "灵石", "amount": [220000, 340000]},
                    {"id": 3029, "rate": 35, "type": "药材", "quantity": [1, 2]},   # 木灵三针花 (八品)
                    {"id": 7061, "rate": 10, "type": "法器"},                         # 绝仙剑 (下品通天)
                    {"id": 6061, "rate": 10, "type": "防具"},                         # 青溪法袍 (下品通天)
                    {"id": 9501, "rate": 7, "type": "功法"},                          # 紫阳混元劲 (地阶下品)
                    {"id": 8601, "rate": 3, "type": "神通"},                          # 开山诀 (地阶下品)
                    {"id": 10311, "rate": 2, "type": "辅修功法"}                      # 静气诀 (地阶上品)
                ]
            },
            "大乘境": {
                "final_hit_bonus": {"exp_rate": 1.8, "stone_rate": 0.18,
                                    "extra_items": [
                                        {"id": 1502, "rate": 10, "type": "丹药"}, # 幻心玄丹
                                        {"id": 4002, "rate": 4, "type": "炼丹炉"}  # 雕花紫铜炉
                                    ]},
                "participant_drop_pool": [
                    {"id": 0, "rate": 100, "type": "灵石", "amount": [340000, 800000]},
                    {"id": 3033, "rate": 30, "type": "药材", "quantity": [1, 1]},   # 离火梧桐芝 (九品)
                    {"id": 7071, "rate": 8, "type": "法器"},                          # 乾坤尺 (上品通天)
                    {"id": 6071, "rate": 8, "type": "防具"},                          # 驱厄灵袍 (上品通天)
                    {"id": 9601, "rate": 6, "type": "功法"},                          # 大罗千幻诀 (地阶上品)
                    {"id": 8701, "rate": 2, "type": "神通"},                          # 怒水天殇 (地阶上品)
                    {"id": 2501, "rate": 6, "type": "聚灵旗"}  # 二级聚灵旗
                ]
            },
             # --- 毕业前夕 ---
            "渡劫境": {
                "final_hit_bonus": {"exp_rate": 1.9, "stone_rate": 0.19,
                                    "extra_items": [
                                        {"id": 1999, "rate": 8, "type": "丹药"}, # 渡厄丹 (重要)
                                        {"id": 4001, "rate": 3, "type": "炼丹炉"} # 寒铁铸心炉
                                    ]},
                "participant_drop_pool": [
                    {"id": 0, "rate": 100, "type": "灵石", "amount": [1800000, 2800000]},
                    {"id": 3033, "rate": 25, "type": "药材", "quantity": [1, 2]}, # 九品药材依然有需求
                    {"id": 7081, "rate": 7, "type": "法器"},                         # 陨仙 (下品仙器)
                    {"id": 6081, "rate": 7, "type": "防具"},                         # 三阳道袍 (下品仙器)
                    {"id": 9701, "rate": 5, "type": "功法"},                         # 朝元御金诀 (天阶下品)
                    {"id": 8801, "rate": 1, "type": "神通"},                         # 天星若雨 (天阶下品)
                    {"id": 10401, "rate": 1, "type": "辅修功法"},                    # 玄门引气真诀 (天阶下品)
                    {"id": 2502, "rate": 5, "type": "聚灵旗"} # 三级聚灵旗
                ]
            },
            "半步真仙": { # 与渡劫境掉落类似，但概率和数量稍好
                "final_hit_bonus": {"exp_rate": 2.0, "stone_rate": 0.2,
                                    "extra_items": [
                                        {"id": 1999, "rate": 10, "type": "丹药", "quantity": [1,2]}, # 渡厄丹
                                        {"id": 1504, "rate": 8, "type": "丹药"} # 少阴清灵丹
                                    ]},
                "participant_drop_pool": [
                    {"id": 0, "rate": 100, "type": "灵石", "amount": [2000000, 3500000]},
                    {"id": 3034, "rate": 28, "type": "药材", "quantity": [1, 2]},   # 尘磊岩麟果
                    {"id": 7083, "rate": 8, "type": "法器"},                          # 承影 (下品仙器)
                    {"id": 6081, "rate": 8, "type": "防具"},                          # 三阳道袍 (下品仙器)
                    {"id": 9702, "rate": 6, "type": "功法"},                          # 太上化龙诀 (天阶下品)
                    {"id": 2503, "rate": 4, "type": "聚灵旗"}  # 四级聚灵旗
                ]
            },
            "真仙境": {
                "final_hit_bonus": {"exp_rate": 2.2, "stone_rate": 0.22,
                                    "extra_items": [
                                        {"id": 1415, "rate": 7, "type": "合成丹药"}, # 太上玄门丹
                                        {"id": 9801, "rate": 3, "type": "功法"}    # 玄武吐纳术 (天阶上品)
                                    ]},
                "participant_drop_pool": [
                    {"id": 0, "rate": 100, "type": "灵石", "amount": [4000000, 5000000]},
                    {"id": 3035, "rate": 25, "type": "药材", "quantity": [1, 1]},   # 剑魄竹笋
                    {"id": 7091, "rate": 6, "type": "法器"},                          # 无影剑 (上品仙器)
                    {"id": 6091, "rate": 6, "type": "防具"},                          # 皇鳞甲 (上品仙器)
                    {"id": 9802, "rate": 4, "type": "功法"},                          # 太上化龙真诀 (天阶上品)
                    {"id": 8907, "rate": 1, "type": "神通"},                          # 雷霆十闪 (天阶上品)
                    {"id": 10411, "rate": 1, "type": "辅修功法"},                     # 真龙九变 (天阶上品)
                    {"id": 2504, "rate": 3, "type": "聚灵旗"}  # 仙级聚灵旗
                ]
            },
            "金仙境": {
                "final_hit_bonus": {"exp_rate": 2.5, "stone_rate": 0.25,
                                    "extra_items": [
                                        {"id": 1416, "rate": 6, "type": "合成丹药"}, # 金仙破厄丹
                                        {"id": 9910, "rate": 2, "type": "功法"}    # 元磁神光 (仙阶)
                                    ]},
                "participant_drop_pool": [
                    {"id": 0, "rate": 100, "type": "灵石", "amount": [4000000, 10000000]},
                    {"id": 3036, "rate": 20, "type": "药材", "quantity": [1, 1]},   # 明心问道果
                    {"id": 7092, "rate": 5, "type": "法器"},                          # 风云幡 (上品仙器)
                    {"id": 6091, "rate": 5, "type": "防具"},                          # 皇鳞甲 (上品仙器) - 防具更新慢些
                    {"id": 9911, "rate": 3, "type": "功法"},                          # 天罗真功 (仙阶)
                    {"id": 8911, "rate": 1, "type": "神通"},                          # 大罗仙印 (仙阶)
                ]
            },
            "太乙境": {
                "final_hit_bonus": {"exp_rate": 3.0, "stone_rate": 0.3,
                                    "extra_items": [
                                        {"id": 1417, "rate": 5, "type": "合成丹药"}, # 太乙炼髓丹
                                        {"id": 9912, "rate": 1, "type": "功法"}    # 托天魔功 (仙阶)
                                    ]},
                "participant_drop_pool": [
                    {"id": 0, "rate": 100, "type": "灵石", "amount": [10000000, 25000000]},
                    {"id": 3036, "rate": 15, "type": "药材", "quantity": [1, 1]},   # 明心问道果
                    # 后期BOSS掉落成品装备概率降低，更多是材料或图纸（如果以后加入）
                    # 这里暂时还是掉落仙器，但概率更低
                    {"id": 7093, "rate": 3, "type": "法器"},                          # 青竹蜂云剑 (上品仙器)
                    {"id": 6091, "rate": 3, "type": "防具"},                          # 皇鳞甲 (上品仙器)
                    # 仙阶功法/神通掉落率极低
                    {"id": 9910, "rate": 1, "type": "功法"},
                    {"id": 8911, "rate": 0.5, "type": "神通"}, # 概率可以小于1，代码处理时用 random.random() < rate/100
                ]
            },
            # 化圣境的BOSS掉落可以与太乙境类似，但灵石和经验奖励更高，或者加入极其稀有的特殊物品
             "化圣境": { # 代表化圣境所有层次
                "final_hit_bonus": {"exp_rate": 3.5, "stone_rate": 0.35,
                                    "extra_items": [
                                        # 化圣境可能需要特殊材料而不是丹药
                                        {"id": 1417, "rate": 3, "type": "合成丹药", "quantity": [1,2]},
                                    ]},
                "participant_drop_pool": [
                    {"id": 0, "rate": 100, "type": "灵石", "amount": [20000000, 50000000]},
                    # 可以设计一些化圣境专属的材料，用于合成更高级的物品或特殊用途
                    # {"id": 9999, "rate": 10, "type": "特殊材料", "name": "圣域残片", "quantity": [1,1]},
                    {"id": 7093, "rate": 2, "type": "法器"},
                    {"id": 6091, "rate": 2, "type": "防具"},
                    {"id": 9912, "rate": 0.5, "type": "功法"},
                ]
            }
        }
SKILL_RANK_VALUE = {
    "人阶下品": 50,
    "人阶上品": 45, # 假设人阶上品比下品高5个rank点
    "黄阶下品": 42,
    "黄阶上品": 39,
    "玄阶下品": 36,
    "玄阶上品": 33,
    "地阶下品": 30,
    "地阶上品": 27,
    "天阶下品": 24,
    "天阶上品": 21,
    "仙阶下品": 18, # 假设有仙阶神通
    "仙阶上品": 15,
    # ... 可以根据您的游戏设计继续添加 ...
    "未知品阶": 99 # 对于无法识别的品阶，给予一个很低的值
}

# MP_COST_REDUCTION_BY_LEVEL_DIFFERENCE
# key: 玩家境界rank值 与 技能rank值 的最小差值 (玩家rank - 技能rank >= key)
# value: MP消耗乘数 (例如 0.8 表示消耗变为原来的80%)
# 键需要从大到小排列，以确保优先匹配最大的境界差
MP_COST_REDUCTION_MAP = {
    25: 0.20,  # 玩家境界比技能高出25个rank点以上，MP消耗为原20% (如 化圣 打 人阶)
    20: 0.30,  # 高出20-24个rank点，消耗30%
    15: 0.40,  # 高出15-19个rank点，消耗40%
    10: 0.55,  # 高出10-14个rank点，消耗55%
    5:  0.75,  # 高出5-9个rank点，消耗75%
    0:  1.00,   # 境界持平或玩家更低，无削减 (或技能rank高于玩家rank)
    # 也可以设置为小于0的情况，比如玩家境界低于技能，MP消耗增加（可选）
    -5: 1.2 # 玩家境界比技能低5个rank点以内，MP消耗变为120%
}

# 境界 -> Rank 映射
USERRANK = {
    '江湖好手': 50, '练气境初期': 49, '练气境中期': 48, '练气境圆满': 47,
    '筑基境初期': 46, '筑基境中期': 45, '筑基境圆满': 44, '结丹境初期': 43,
    '结丹境中期': 42, '结丹境圆满': 41, '元婴境初期': 40, '元婴境中期': 39,
    '元婴境圆满': 38, '化神境初期': 37, '化神境中期': 36, '化神境圆满': 35,
    '炼虚境初期': 34, '炼虚境中期': 33, '炼虚境圆满': 32, '合体境初期': 31,
    '合体境中期': 30, '合体境圆满': 29, '大乘境初期': 28, '大乘境中期': 27,
    '大乘境圆满': 26, '渡劫境初期': 25, '渡劫境中期': 24, '渡劫境圆满': 23,
    '半步真仙': 22, '真仙境初期': 21, '真仙境中期': 20, '真仙境圆满': 19,
    '金仙境初期': 18, '金仙境中期': 17, '金仙境圆满': 16, '太乙境初期': 15,
    '太乙境中期': 14, '太乙境圆满': 13, '化圣境一层': 12, '化圣境二层': 11,
    '化圣境三层': 10, '化圣境四层': 9, '化圣境五层': 8, '化圣境六层': 7,
    '化圣境七层': 6, '化圣境八层': 5, '化圣境九层': 4,
}
