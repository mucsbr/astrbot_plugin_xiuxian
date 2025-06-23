import random
import threading
import time
import json
from typing import Dict, List, Optional, Tuple
from datetime import datetime, date, timedelta, timezone
from .db import FishingDB
from astrbot.api import logger
from .po import UserFishing, POND_CAPACITY_PRIMARY, POND_CAPACITY_MIDDLE, POND_CAPACITY_ADVANCED, POND_CAPACITY_TOP
from . import enhancement_config
from . import class_config
from . import pk_skill_handler
from . import pk_config
from . import pve_config
from ..service import XiuxianService as MainXiuxianService

def get_coins_name():
    """获取金币名称"""
    coins_names = ["星声", "原石", "社会信用点", "精粹", "黑油", "馒头", "马内", "🍓", "米线"]
    return random.choice(coins_names)

UTC4 = timezone(timedelta(hours=4))

def get_utc4_now():
    return datetime.now(UTC4)

def get_utc4_today():
    return get_utc4_now().date()

class _BattleSimulator:
    def __init__(self, service, attacker, defender, prize_pool):
        self.service = service # 允许访问DB等
        if prize_pool == 0:
            self.attacker = self._init_player_state_pve(attacker, 'attacker')
            self.defender = self._init_player_state_pve(defender, 'defender')
        else:
            self.attacker = self._init_player_state(attacker, 'attacker')
            self.defender = self._init_player_state(defender, 'defender')
        self.round = 0
        self.battle_ended = False
        self.duel_states = {}
        self.report = [f"⚔️ 深海角斗场 - 战报 ⚔️", f"挑战者: {self.attacker['name']} vs 被挑战者: {self.defender['name']}", f"奖池: {prize_pool} 金币", "---"]

    def _init_player_state_pve(self, p_info, role):
        p_class = p_info['player_class']
        energy = pk_config.PK_RULES['base_energy'] + pk_config.CLASS_PK_BONUS.get(p_class, {}).get('start_energy_bonus', 0)

        # <<< 核心修复：不再调用数据库，直接使用 p_info 中已有的 lineup >>>
        lineup = p_info['lineup']
        for fish in lineup:
            # 初始化鱼的战斗状态
            fish['current_stats'] = {'rarity': fish['rarity'], 'weight': fish['weight'], 'value': fish['base_value']}
            fish['states'] = {'aura_disabled': False, 'ultimate_disabled': False, 'permanent_debuffs': [], 'turn_buffs': [], 'turn_debuffs': []}

        return {
            'id': p_info['id'],
            'name': p_info['nickname'],
            'class': p_class,
            'score': 0,
            'energy': energy,
            'lineup': lineup,
            'simulator': self,
            'role': role,
            'states': {'aura_buff_chance': 0.0}
        }

    def _init_player_state(self, p_info, role):
        p_class = p_info['player_class']
        energy = pk_config.PK_RULES['base_energy'] + pk_config.CLASS_PK_BONUS.get(p_class, {}).get('start_energy_bonus', 0)

        has_bonus = pk_config.CLASS_PK_BONUS.get(p_class, {}).get('lineup_quality_bonus', False)
        lineup = self.service.db.get_duel_lineup(p_info['id'], pk_config.PK_RULES['lineup_size'], has_bonus)

        for fish in lineup:
            fish['states'] = {'aura_disabled': False, 'ultimate_disabled': False, 'permanent_debuffs': [], 'turn_buffs': [], 'turn_debuffs': []}

        return {'id': p_info['id'], 'name': p_info['nickname'], 'class': p_class, 'score': 0, 'energy': energy, 'lineup': lineup, 'simulator': self, 'role': role, 'states': {'aura_buff_chance': 0.0}}

    def log(self, message, indent=0):
        self.report.append("  " * indent + message)

    def run(self):
        if len(self.attacker['lineup']) < pk_config.PK_RULES['lineup_size'] or len(self.defender['lineup']) < pk_config.PK_RULES['lineup_size']:
            return {'error': f"一方或双方的鱼塘鱼不足{pk_config.PK_RULES['lineup_size']}条"}

        self._execute_pre_battle_skills()

        for i in range(pk_config.PK_RULES['lineup_size']):
            if self.battle_ended: break
            self.round = i + 1
            self.log(f"【第{self.round}回合】")
            self._execute_round()
            self.log("---")

        return self._get_final_result()

    def _execute_round(self):
        # 1. 准备阶段
        p1, p2 = self.attacker, self.defender
        p1_fish, p2_fish = p1['lineup'][self.round - 1], p2['lineup'][self.round - 1]

        self.log(f"🔵 {p1['name']} 派出 {p1_fish['name']} (R{p1_fish['rarity']})")
        self.log(f"🔴 {p2['name']} 派出 {p2_fish['name']} (R{p2_fish['rarity']})")

        self._generate_energy(p1_fish, p2_fish)
        self._reset_and_apply_permanent_states(p1_fish, p2_fish)

        # <<< 核心修复：提前初始化所有回合状态变量 >>>
        self.forced_rule = None
        self.round_winner = None
        self.force_draw = False
        self.reroll_this_round = False
        self.special_win_condition_triggered = None
        # <<< 修复结束 >>>

        # 2. 光环阶段
        self._apply_auras(p1, p2, p1_fish, p2_fish)

        # 3. 必杀技阶段
        # 注意：现在forced_rule已存在，可以在必杀技中被修改
        self._decide_and_use_ultimates(p1, p2, p1_fish, p2_fish)

        # 4. 裁定阶段
        if self.special_win_condition_triggered:
            self._execute_special_win_condition(self.special_win_condition_triggered)
            return

        if self.reroll_this_round:
            self.log("🌪️ 命运的齿轮开始倒转，本回合重赛！")
            self._execute_round()
            return

        rule = self.forced_rule if self.forced_rule else random.choice(['rarity', 'weight', 'value'])
        self.log(f"(比拼规则: **{rule.upper()}**)")

        if self.force_draw:
            winner_player = None
        elif self.round_winner:
            winner_player = self.round_winner
        else:
            p1_val = p1_fish['current_stats'].get(rule, 0) # 使用.get增加健壮性
            p2_val = p2_fish['current_stats'].get(rule, 0)
            winner_player = p1 if p1_val > p2_val else p2 if p2_val > p1_val else None

        # 5. 结算阶段
        loser_player = None
        if winner_player:
            winner_player['score'] += 1
            loser_player = p2 if winner_player['id'] == p1['id'] else p1
            self.log(f"⭐ {winner_player['name']} 获胜！ (比分 {self.attacker['score']}-{self.defender['score']})")
        else:
            self.log("⭐ 本回合平局！")

        self._execute_end_of_round_skills(p1, p2, p1_fish, p2_fish, winner_player, loser_player)

    def _generate_energy(self, p1_fish, p2_fish):
        p1_energy = pk_config.ENERGY_GENERATION.get(p1_fish['rarity'], 0)
        p2_energy = pk_config.ENERGY_GENERATION.get(p2_fish['rarity'], 0)
        self.attacker['energy'] += p1_energy
        self.defender['energy'] += p2_energy
        if p1_energy > 0 or p2_energy > 0:
            self.log(f"能量变化: {self.attacker['name']} {self.attacker['energy']}(+{p1_energy}) | {self.defender['name']} {self.defender['energy']}(+{p2_energy})", 1)

    def _reset_and_apply_permanent_states(self, p1_fish, p2_fish):
        fishes = [p1_fish, p2_fish]
        for fish in fishes:
            fish['current_stats'] = {'rarity': fish['rarity'], 'weight': fish['weight'], 'value': fish['base_value']}
            # 应用永久性debuff
            for debuff in fish['states'].get('permanent_debuffs', []):
                if debuff['type'] == 'all_stats':
                    for stat in fish['current_stats']:
                        fish['current_stats'][stat] *= (1 - debuff['value'])
            # 应用回合性debuff
            for debuff in fish['states'].get('turn_debuffs', []):
                if debuff['type'] == 'weight_debuff_rate':
                    fish['current_stats']['weight'] *= (1-debuff['value'])

    def _apply_auras(self, p1, p2, p1_fish, p2_fish):
        # 双方光环依次触发
        self._apply_single_fish_aura(p1, p2, p1_fish, p2_fish)
        self._apply_single_fish_aura(p2, p1, p2_fish, p1_fish)

    def _apply_single_fish_aura(self, player, opponent, p_fish, o_fish):
        skill = pk_config.get_skill_by_fish_name(p_fish['name'])
        if not skill or p_fish['states']['aura_disabled']: return

        if opponent['lineup'][self.round-1]['states'].get('dodge_aura', False) and pk_skill_handler.check_trigger_chance({'chance': 0.3}, player['states']):
            self.log(f"💨 {p_fish['name']} 的光环被对手 {o_fish['name']} 的`[墨汁斗篷]`闪避了！")
            return

        effect_params = skill.get('effect', {})
        aura_effect = effect_params.get('aura_effect', {})

        for effect_name, effect_value in aura_effect.items():
            handler = pk_skill_handler.AURA_EFFECT_MAP.get(effect_name)
            if handler:
                # 复杂的触发条件判断
                trigger_params = effect_params.get('aura_trigger', {})
                if self._check_triggers(trigger_params, player, opponent, p_fish, o_fish):
                    self.log(f"✨ {p_fish['name']} 的光环 `{skill['aura']}` 触发！", 1)
                    handler(player, opponent, p_fish, o_fish, {effect_name: effect_value})

    def _decide_and_use_ultimates(self, p1, p2, p1_fish, p2_fish):
        # 智能AI决策（简化版：能用且有意义就用）
        self._ai_use_ultimate(p1, p2, p1_fish, p2_fish)
        self._ai_use_ultimate(p2, p1, p2_fish, p1_fish)

    def _ai_use_ultimate(self, player, opponent, p_fish, o_fish):
        skill = pk_config.get_skill_by_fish_name(p_fish['name'])
        if not skill or p_fish['states']['ultimate_disabled']: return

        effect_params = skill.get('effect', {})
        cost = effect_params.get('ultimate_cost')
        if not cost: return

        energy_cost = 0
        if cost == "all":
            energy_cost = player['energy']
            if energy_cost < 1: return
        elif cost == "all_min_2":
            energy_cost = player['energy']
            if energy_cost < 2: return
        elif isinstance(cost, int):
            energy_cost = cost
            if player['energy'] < energy_cost: return

        # 简单的决策：只要能量够就用（更复杂的AI可以模拟使用后结果）
        player['energy'] -= energy_cost
        player['energy_spent_on_ultimate'] = energy_cost
        self.log(f"💥 {p_fish['name']} 消耗{energy_cost}能量发动必杀 `{skill['ultimate']}`！", 1)

        ultimate_effect = effect_params.get('ultimate_effect', {})
        for effect_name, effect_value in ultimate_effect.items():
            handler = pk_skill_handler.ULTIMATE_EFFECT_MAP.get(effect_name)
            if handler:
                 handler(player, opponent, p_fish, o_fish, {effect_name: effect_value})

    def _check_triggers(self, triggers, player, opponent, p_fish, o_fish) -> bool:
        # 这是一个巨大的触发器检查函数，返回是否满足所有触发条件
        if not triggers: return True # 没有触发条件，默认触发

        for key, val in triggers.items():
            if key == 'opponent_rarity_lte' and o_fish['rarity'] > val: return False
            if key == 'rule_is' and self.forced_rule != val and (not self.forced_rule and random.choice(['rarity', 'weight', 'value']) != val): return False # 简化预判
            if key == 'chance' and not pk_skill_handler.check_trigger_chance(triggers, player['states']): return False
            if key == 'is_first_fish' and self.round != 1: return False
            if key == 'is_last_rounds' and self.round <= pk_config.PK_RULES['lineup_size'] - val: return False
            # ... 此处需要添加所有触发条件的检查逻辑 ...
        return True
    # service.py -> _BattleSimulator 类的内部

    def _execute_special_win_condition(self, player):
        """处理海神三叉戟的特殊胜利条件"""
        opponent = self.defender if player['id'] == self.attacker['id'] else self.attacker

        # 1. 随机选择一个比拼属性
        rule = random.choice(['rarity', 'weight', 'value'])
        self.log(f"🔱 神之裁决发动！开始清算双方阵容的总【{rule.upper()}】！", 1)

        # 2. 计算双方阵容的总属性值
        player_total = sum(fish['current_stats'][rule] for fish in player['lineup'])
        opponent_total = sum(fish['current_stats'][rule] for fish in opponent['lineup'])

        self.log(f"{player['name']}的总值为: {player_total}", 2)
        self.log(f"{opponent['name']}的总值为: {opponent_total}", 2)

        # 3. 判断胜负并给予分数
        if player_total > opponent_total:
            player['score'] += 2
            self.log(f"⭐ {player['name']} 的阵容更胜一筹，直接获得 2 分！", 1)
        elif opponent_total > player_total:
            opponent['score'] += 2
            self.log(f"⭐ {opponent['name']} 的阵容更胜一筹，直接获得 2 分！", 1)
        else:
            self.log("双方阵容势均力敌，判定为平局！", 1)

        # 4. 这个技能可能会直接决定胜负，所以检查是否需要提前结束战斗
        if player['score'] >= 3 or opponent['score'] >= 3:
            self.battle_ended = True
            self.log("裁决的结果直接决定了最终的胜负！", 1)

    def _execute_pre_battle_skills(self):
        # 处理海豚、光颌鱼等战前技能
        for p, o in [(self.attacker, self.defender), (self.defender, self.attacker)]:
            for fish in p['lineup']:
                skill = pk_config.get_skill_by_fish_name(fish['name'])
                if not skill: continue
                effect = skill.get('effect', {})
                if effect.get('pre_battle_spy_chance') and random.random() < effect['pre_battle_spy_chance']:
                    spy_target = random.choice(o['lineup'])
                    self.log(f"**战前情报**: {p['name']} 的 {fish['name']} 窥探到对手阵容中有 **{spy_target['name']}**！")

    def _execute_end_of_round_skills(self, p1, p2, p1_fish, p2_fish, winner, loser):
        # 核心修复：遍历出战的鱼，而不是玩家
        for player, fish in [(p1, p1_fish), (p2, p2_fish)]:
            # 从鱼的states字典中获取效果
            for effect in fish['states'].get('end_of_round_effects', []):
                if effect['type'] == 'add_energy':
                    player['energy'] += effect['value']
                    self.log(f"✨ 回合结束效果发动，{player['name']} 的 {fish['name']} 为其回复了 {effect['value']} 点能量！", 1)

        # 清空本回合效果，防止带到下一回合
        p1_fish['states']['end_of_round_effects'] = []
        p2_fish['states']['end_of_round_effects'] = []

    def _get_final_result(self):
        if hasattr(self, 'battle_winner'):
            winner = self.battle_winner
            loser = self.defender if winner['id'] == self.attacker['id'] else self.attacker
        elif self.attacker['score'] > self.defender['score']:
            winner, loser = self.attacker, self.defender
        elif self.defender['score'] > self.attacker['score']:
            winner, loser = self.defender, self.attacker
        else:
            return {'winner': None, 'loser': None, 'report': self.report}
        return {'winner': winner, 'loser': loser, 'report': self.report}

# --- PVE处理器 (最终完整版) ---
class PVEHandler:
    def __init__(self, service):
        self.service = service
        self.db = service.db
        self.legendary_deck_map = {id: name for id, name in pve_config.LEGENDARY_DECK.items()}
        self.name_to_id_map = {name: id for id, name in self.legendary_deck_map.items()}

    def get_deck_list_message(self):
        all_fish = self.db.get_legendary_fish_data()
        r4_list, r5_list = [], []
        for fish in all_fish:
            id_str = self.name_to_id_map.get(fish['name'], "N/A")
            line = f"`{id_str}`: [R{fish['rarity']}] **{fish['name']}** - {fish['description'] or '神秘的鱼'}"
            if fish['rarity'] == 4: r4_list.append(line)
            else: r5_list.append(line)

        return "📜 **镜像回廊 - 传说牌库** 📜\n\n**【四星战术核心】**\n" + "\n".join(r4_list) + \
               "\n\n**【五星神话之力】**\n" + "\n".join(r5_list)

    def start_challenge(self, user_id, lineup_ids):
        """发起一场回廊挑战（包含完整前置检查）"""
         # --- 1. 完整的每日次数和成本前置检查 ---
        now = get_utc4_now()
        today_str = now.date().isoformat()
        rules = pve_config.CORRIDOR_RULES

        # a. 获取并解析玩家的挑战信息
        # 我们将复用 duel_cooldown_hours 的数据库字段，但key不同
        info_str = self.db.get_user_by_id(user_id).get('last_corridor_info', '{}')
        logger.info(info_str)
        try:
            last_info = json.loads(info_str)
        except json.JSONDecodeError:
            last_info = {}

        last_challenge_date = last_info.get('date', '')
        daily_attempts = last_info.get('attempts', 0)

        # b. 如果不是同一天，自动重置挑战次数
        logger.info(last_challenge_date)
        logger.info(today_str)
        if last_challenge_date != today_str:
            daily_attempts = 0

        pay_cnt = ""
        # c. 检查免费次数是否用尽，如果用尽，则检查并扣除金币成本
        if daily_attempts >= rules['daily_free_challenges']:
            cost = rules['cost_after_free']
            user_coins = self.db.get_user_coins(user_id)
            if user_coins < cost:
                return {"success": False, "message": f"今天的 {rules['daily_free_challenges']} 次免费挑战已用完，再次挑战需要 {cost} 金币，但你的金币不足。"}

            # 扣费
            if not self.db.update_user_coins(user_id, -cost):
                 return {"success": False, "message": "金币扣除失败，请重试。"}
            self.service.LOG.info(f"用户 {user_id} 支付 {cost} 金币挑战回廊。")
            pay_cnt = "支付15w获得了一次挑战机会！"

        # 2. 验证与准备阵容
        if len(lineup_ids) != 5: return {"success": False, "message": "阵容必须包含5条鱼。"}
        fish_names = [self.legendary_deck_map.get(id) for id in lineup_ids]
        if None in fish_names: return {"success": False, "message": "阵容中包含无效的ID。"}

        # --- 更新玩家挑战记录 ---
        new_info = {
            'date': today_str,
            'attempts': daily_attempts + 1
        }
        self.db.update_user_corridor_info(user_id, json.dumps(new_info)) # 复用duel的DB方法来更新

        player_lineup_data = self.db.get_fish_by_names(fish_names)
        player_info = self.db.get_user_for_duel(user_id) # 复用duel的方法获取基础信息
        player_full_info = {'id': user_id, "lineup": player_lineup_data, 'nickname': self.db.get_user_by_id(user_id)['nickname'], **player_info}

        # 3. 计算难度并生成守卫
        difficulty, guard_type = pve_config.get_difficulty_and_guard(player_lineup_data)
        guard_lineup = self._generate_guard_lineup(guard_type)

        # 4. 运行战斗模拟器 (完全复用PVP的模拟器)
        guard_info = {'id': '镜像守卫', 'nickname': f'{difficulty}难度守卫', 'player_class': 'BOSS', 'lineup': guard_lineup}

        # 注意：这里的 prize_pool 为0，因为是PVE
        simulator = _BattleSimulator(self.service, player_full_info, guard_info, 0)
        result = simulator.run()

        if result.get('error'):
            return {"success": False, "message": pay_cnt + result['error']}

        # 5. 处理结果
        battle_report = result['report']
        if result['winner'] and result['winner']['id'] == user_id: # 玩家胜利
            rewards = self._calculate_rewards(difficulty)
            self._grant_rewards(user_id, rewards)

            reward_report = ["---", f"**挑战成功! (难度: {difficulty})**", "你获得了:"]
            for item, qty in rewards.items():
                reward_report.append(f"- {item}: {qty}")
            battle_report.extend(reward_report)
            return {"success": True, "message": pay_cnt + "\n".join(battle_report)}
        else: # 玩家失败或平局
            battle_report.append("---")
            battle_report.append("**挑战失败!**")
            battle_report.append("镜像中的倒影击败了你，调整阵容再战吧！")
            return {"success": True, "message": pay_cnt + "\n".join(battle_report)}

    def _generate_guard_lineup(self, guard_type):
        all_r4_names = [name for id, name in pve_config.LEGENDARY_DECK.items() if id.startswith('1')]
        all_r5_names = [name for id, name in pve_config.LEGENDARY_DECK.items() if id.startswith('2')]

        guard_fish_names = []
        if guard_type == 'guard_normal':
            guard_fish_names = random.sample(all_r4_names, 5)
        elif guard_type == 'guard_hard':
            guard_fish_names.extend(random.sample(all_r4_names, 3))
            guard_fish_names.extend(random.sample(all_r5_names, 2))
        elif guard_type == 'guard_heroic':
            guard_fish_names.extend(random.sample(all_r4_names, 1))
            guard_fish_names.extend(random.sample(all_r5_names, 4))
        elif guard_type == 'guard_legendary':
            guard_fish_names = random.sample(all_r5_names, 5)

        return self.db.get_fish_by_names(guard_fish_names)

    def _calculate_rewards(self, difficulty):
        pool = pve_config.REWARD_POOLS[difficulty]
        rewards = {'金币': pool['gold'], '镜像碎片': pool['shards']}

        chests = int(pool['chests'])
        if random.random() < (pool['chests'] - chests): chests += 1
        if chests > 0: rewards['沉没的宝箱'] = chests

        if random.random() < pool['rare_chance']:
            item_type = pool['rare_item_type']
            item_data = self.db.get_random_r5_item(item_type)
            if item_data:
                rewards[f"稀有掉落: {item_data['name']}"] = 1
        return rewards

    def _grant_rewards(self, user_id, rewards):
        for item, qty in rewards.items():
            if item == '金币': self.db.update_user_coins(user_id, qty)
            elif item == '镜像碎片': self.db.add_special_item(user_id, 'mirror_shards', qty)
            elif item == '沉没的宝箱':
                chest_id = self.db.get_fish_id_by_name("沉没的宝箱")
                if chest_id: self.db.add_fish_to_inventory(user_id, chest_id, qty)
            elif item.startswith('稀有掉落'):
                item_name = item.split(': ')[1]
                item_info = self.db.get_item_by_name(item_name)
                if item_info: self.db.batch_add_item_to_users([user_id], item_info, qty)

class FishingService:
    def __init__(self, db_path: str, xiuxian_service: MainXiuxianService):
        """初始化钓鱼服务"""
        self.db = FishingDB(db_path, xiuxian_service)
        self.main_service = xiuxian_service
        self.auto_fishing_thread = None
        self.auto_fishing_running = False
        self.achievement_check_thread = None
        self.achievement_check_running = False
        self.today = get_utc4_today()
        self.chest_id = None # 用于缓存宝箱的ID
        self.pve_handler = PVEHandler(self)
        
        # 设置日志记录器
        self.LOG = logger
        
        # 确保必要的基础数据存在
        self._ensure_shop_items_exist()

        # 数据库修改操作
        self.db._migrate_database()
        
        # 启动自动钓鱼
        self.start_auto_fishing_task()
        
        # 启动成就检查
        self.start_achievement_check_task()
        
    def _ensure_shop_items_exist(self):
        """确保商店中有基本物品数据"""
        # 检查是否有鱼竿数据
        rods = self.db.get_all_rods()
        if not rods:
            self.LOG.info("正在初始化基础鱼竿数据...")
            with self.db._get_connection() as conn:
                cursor = conn.cursor()
                # 添加几种基本鱼竿
                cursor.executemany("""
                    INSERT OR IGNORE INTO rods (
                        name, description, rarity, source, purchase_cost, 
                        bonus_fish_quality_modifier, bonus_fish_quantity_modifier, 
                        bonus_rare_fish_chance, durability
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, [
                    ("简易木竿", "最基础的钓鱼竿，适合入门", 1, "shop", 100, 1.0, 1.0, 0.0, 100),
                    ("优质钓竿", "中级钓鱼竿，提高鱼的质量", 2, "shop", 500, 1.2, 1.0, 0.01, 200),
                    ("专业碳素竿", "高级钓鱼竿，提高钓到稀有鱼的几率", 3, "shop", 1500, 1.3, 1.1, 0.03, 300),
                    ("抗压合金钓竿", "稀有钓鱼竿，综合属性较好", 4, "shop", 5000, 1.4, 1.2, 0.05, 500)
                ])
                conn.commit()
                self.LOG.info("基础鱼竿数据初始化完成。")
        
        # 这里还可以检查其他必要的物品数据，如鱼饵等

    def register(self, user_id: str, nickname: str) -> Dict:
        """注册用户"""
        if self.db.check_user_registered(user_id):
            return {"success": False, "message": "用户已注册"}
        
        success = self.db.register_user(user_id, nickname)
        if success:
            return {"success": True, "message": f"用户 {nickname} 注册成功"}
        else:
            return {"success": False, "message": "注册失败，请稍后再试"}

    def is_registered(self, user_id: str) -> bool:
        """检查用户是否已注册"""
        return self.db.check_user_registered(user_id)
    
    def _check_registered_or_return(self, user_id: str) -> Optional[Dict]:
        """检查用户是否已注册，未注册返回错误信息"""
        if not self.is_registered(user_id):
            return {"success": False, "message": "请先注册才能使用此功能"}
        return None

    def fish(self, user_id: str, is_auto: bool = False) -> Dict:
        """进行一次钓鱼，考虑鱼饵的影响"""
        error = self._check_registered_or_return(user_id)
        if error:
            return error
            
        # 如果是自动钓鱼，先扣除钓鱼成本
        if is_auto:
            fishing_cost = self.get_fishing_cost()
            if not self.db.update_user_coins(user_id, -fishing_cost):
                return {"success": False, "message": "金币不足，无法进行自动钓鱼"}

        # 获取装备信息计算成功率和加成
        equipment = self.db.get_user_equipment(user_id)

        player_class = self.db.get_player_class(user_id)
        
        # 获取用户当前使用的鱼饵信息
        current_bait = self.db.get_user_current_bait(user_id)
        
        # 如果用户没有主动使用鱼饵，尝试随机消耗一个一次性鱼饵
        consumed_bait = None
        if not current_bait:
            # 获取用户所有可用的一次性鱼饵
            disposable_baits = self.db.get_user_disposable_baits(user_id)
            if disposable_baits:
                if player_class == 'child' and random.random() < 0.10:
                    bait_effect = "【海洋祝福】本次钓鱼未消耗鱼饵！"
                else:
                    # 随机选择一个鱼饵消耗
                    random_bait = random.choice(disposable_baits)
                    bait_id = random_bait['bait_id']
                    if self.db.consume_bait(user_id, bait_id):
                        consumed_bait = random_bait
        
        # 计算钓鱼成功率和加成
        base_success_rate = 0.7
        if player_class == 'hunter': # 巨物猎手被动
            base_success_rate += 0.01
        quality_modifier = 1.0
        quantity_modifier = 1.0 
        rare_chance = 0.0
        garbage_reduction = 0.0
        bait_effect_message = ""
        consumed_bait_id = None
        
        # 应用装备加成（现在equipment总是有值，且各属性也都有默认值）
        rod_quality = equipment.get('rod_quality_modifier', 1.0)
        rod_quantity = equipment.get('rod_quantity_modifier', 1.0)
        rod_rare = equipment.get('rod_rare_chance', 0.0)
        acc_quality = equipment.get('acc_quality_modifier', 1.0)
        acc_quantity = equipment.get('acc_quantity_modifier', 1.0)
        acc_rare = equipment.get('acc_rare_chance', 0.0)
        
        # 应用装备影响
        quality_modifier = rod_quality * acc_quality
        quantity_modifier = rod_quantity * acc_quantity
        rare_chance = rod_rare + acc_rare

        if player_class == 'hunter': # 巨物猎手被动
            quality_modifier *= 1.15
            rare_chance *= 1.15

         # 获取并应用锻造等级加成
        forging_level = self.db.get_user_forging_level(user_id)
        if forging_level > 0:
            forging_bonuses = enhancement_config.get_bonuses_for_level(forging_level)
            # 品质加成是乘算，稀有度加成是加算
            quality_modifier *= (1 + forging_bonuses['quality_bonus'] / 100.0)
            rare_chance += forging_bonuses['rare_bonus'] / 100.0
        
        # 考虑饰品的特殊效果
        equipped_accessory = self.db.get_user_equipped_accessory(user_id)
        if equipped_accessory:
            # 使用饰品的实际属性值进行加成
            acc_quality_bonus = equipped_accessory.get('bonus_fish_quality_modifier', 1.0)
            acc_quantity_bonus = equipped_accessory.get('bonus_fish_quantity_modifier', 1.0)
            acc_rare_bonus = equipped_accessory.get('bonus_rare_fish_chance', 0.0)
            acc_coin_bonus = equipped_accessory.get('bonus_coin_modifier', 1.0)
            
            # 应用饰品属性到钓鱼相关的修饰符
            quality_modifier *= acc_quality_bonus
            quantity_modifier *= acc_quantity_bonus  
            rare_chance += acc_rare_bonus
            
            # 如果有饰品特殊效果描述，可考虑额外加成
            other_bonus = equipped_accessory.get('other_bonus_description', '')
            # 确保other_bonus是字符串
            other_bonus = str(other_bonus) if other_bonus is not None else ""
            if '减少垃圾' in other_bonus or '减少钓鱼等待时间' in other_bonus:
                garbage_reduction += 0.2
        
        # 应用鱼饵效果（这里简化处理，实际可根据鱼饵类型设置不同效果）
        bait_effect = ""
        
        # 处理主动使用的鱼饵
        if current_bait:
            # 解析鱼饵效果（示例）
            effect_desc = current_bait.get('effect_description', '').lower()
            
            # 简单规则匹配不同效果
            if '提高所有鱼种上钩率' in effect_desc:
                base_success_rate += 0.1
                bait_effect = "提高钓鱼成功率"
            elif '显著提高中大型海鱼上钩率' in effect_desc:
                base_success_rate += 0.05
                rare_chance += 0.03
                bait_effect = "提高稀有鱼几率"
            elif '降低钓上' in effect_desc and '垃圾' in effect_desc:
                garbage_reduction = 0.5
                bait_effect = "降低垃圾概率"
            elif '提高 rarity 3及以上鱼的上钩率' in effect_desc:
                rare_chance += 0.05
                bait_effect = "提高稀有鱼几率"
            elif '钓上的鱼基础价值+10%' in effect_desc:
                quality_modifier *= 1.1
                bait_effect = "提高鱼价值10%"
            elif '下一次钓鱼必定获得双倍数量' in effect_desc:
                quantity_modifier *= 2
                bait_effect = "双倍鱼获取"
                # 这种一次性效果使用后应清除
                #self.db.clear_user_current_bait(user_id)
            
            # 拟饵类型不消耗
            if not ('无消耗' in effect_desc):
                # 如果是持续时间类型的鱼饵，则不在这里清除，由get_user_current_bait自动判断
                if current_bait.get('duration_minutes', 0) == 0:
                    # 一般鱼饵用一次就消耗完
                    self.db.consume_bait(user_id, current_bait['bait_id'])
                    self.db.clear_user_current_bait(user_id)

        
        # 处理自动消耗的一次性鱼饵
        elif consumed_bait:
            effect_desc = consumed_bait.get('effect_description', '').lower()
            
            # 应用与主动使用相同的效果逻辑
            if '提高所有鱼种上钩率' in effect_desc:
                base_success_rate += 0.1
                bait_effect = f"自动使用【{consumed_bait['name']}】，提高钓鱼成功率"
            elif '显著提高中大型海鱼上钩率' in effect_desc:
                base_success_rate += 0.05
                rare_chance += 0.03
                bait_effect = f"自动使用【{consumed_bait['name']}】，提高稀有鱼几率"
            elif '降低钓上' in effect_desc and '垃圾' in effect_desc:
                garbage_reduction = 0.5
                bait_effect = f"自动使用【{consumed_bait['name']}】，降低垃圾概率"
            elif '提高 rarity 3及以上鱼的上钩率' in effect_desc:
                rare_chance += 0.05
                bait_effect = f"自动使用【{consumed_bait['name']}】，提高稀有鱼几率"
            elif '钓上的鱼基础价值+10%' in effect_desc:
                quality_modifier *= 1.1
                bait_effect = f"自动使用【{consumed_bait['name']}】，提高鱼价值10%"
            elif '下一次钓鱼必定获得双倍数量' in effect_desc:
                quantity_modifier *= 2
                bait_effect = f"自动使用【{consumed_bait['name']}】，双倍鱼获取"
            else:
                bait_effect = f"自动使用【{consumed_bait['name']}】"
        
        # 应用成功率上限
        base_success_rate = min(0.98, base_success_rate)
        
        # 判断是否钓到鱼
        if random.random() < base_success_rate:
            # 确定鱼的稀有度，使用固定的概率分布
            rarity_probs = {
                1: 0.40,  # 普通 40%
                2: 0.305,  # 稀有 30.5%
                3: 0.205,  # 史诗 20.5%
                4: 0.08,  # 传说 8%
                5: 0.01   # 神话 1%
            }
            
            # 应用稀有度加成，提高更高稀有度的概率
            if rare_chance > 0:
                # 检查并应用“追踪巨物”Buff
                active_buff = self.db.get_user_buff(user_id)
                if active_buff and active_buff['type'] == 'hunter_skill':
                    # 将R4和R5的概率翻倍，从R1,R2,R3中扣除
                    doubled_prob = rarity_probs[4] + rarity_probs[5]
                    rarity_probs[4] *= 2
                    rarity_probs[5] *= 2
                    # 从低稀有度中平均扣除增加的概率
                    deduction = doubled_prob / 3
                    rarity_probs[1] -= deduction
                    rarity_probs[2] -= deduction
                    rarity_probs[3] -= deduction
                # 将一部分概率从低稀有度转移到高稀有度
                transfer_prob = rare_chance * 0.5  # 最多转移50%的概率
                
                rarity_probs[1] -= transfer_prob * 0.4  # 减少40%的转移概率
                rarity_probs[2] -= transfer_prob * 0.3  # 减少30%的转移概率
                rarity_probs[3] -= transfer_prob * 0.2  # 减少20%的转移概率
                
                # 增加更高稀有度的概率
                rarity_probs[4] += transfer_prob * 0.7  # 增加70%的转移概率
                rarity_probs[5] += transfer_prob * 0.3  # 增加30%的转移概率
                
                # 确保概率都是正数
                for r in rarity_probs:
                    rarity_probs[r] = max(0.001, rarity_probs[r])
            
            # 基于概率分布选择稀有度
            rarity_roll = random.random()
            cumulative_prob = 0
            selected_rarity = 1  # 默认为1
            
            for rarity, prob in sorted(rarity_probs.items()):
                cumulative_prob += prob
                if rarity_roll <= cumulative_prob:
                    selected_rarity = rarity
                    break

            # <<< 核心修改：黄金罗盘的“转化”逻辑 >>>
            force_get_chest = False
            if player_class == 'seeker' and selected_rarity >= 4:
                conversion_chance = 0.0
                if selected_rarity == 4:
                    conversion_chance = 0.50 # 判定出R4时，50%转为宝箱
                elif selected_rarity == 5:
                    conversion_chance = 0.25 # 判定出R5时，25%转为宝箱

                if random.random() < conversion_chance:
                    force_get_chest = True
                    logger.info(f"宝藏探寻者 {user_id} 触发【黄金罗盘】，将 R{selected_rarity} 结果转化为宝箱！")
            
            # 根据稀有度获取一条鱼
            with self.db._get_connection() as conn:
                cursor = conn.cursor()
                
                if force_get_chest:
                    if not hasattr(self, 'chest_id') or not self.chest_id:
                        self.chest_id = self.db.get_fish_id_by_name("沉没的宝箱")
                    cursor.execute("SELECT * FROM fish WHERE fish_id = ?", (self.chest_id,))
                    fish = dict(cursor.fetchone())
                else:
                    # 获取指定稀有度的所有鱼
                    cursor.execute("""
                        SELECT fish_id, name, rarity, base_value, min_weight, max_weight
                        FROM fish
                        WHERE rarity = ?
                    """, (selected_rarity,))
                    
                    fishes = cursor.fetchall()
                    if not fishes:
                        # 如果没有对应稀有度的鱼，回退到随机选择
                        cursor.execute("""
                            SELECT fish_id, name, rarity, base_value, min_weight, max_weight
                            FROM fish
                            ORDER BY RANDOM()
                            LIMIT 1
                        """)
                        fish = dict(cursor.fetchone())
                    else:
                        # 在同稀有度内，基于价值反比来选择鱼（价值越高，概率越低）
                        # 计算所有鱼的总价值倒数
                        total_inverse_value = sum(1.0 / (f['base_value'] or 1) for f in fishes)
                        
                        # 为每条鱼分配概率
                        fish_probs = []
                        for f in fishes:
                            # 避免除以零
                            inv_value = 1.0 / (f['base_value'] or 1)
                            prob = inv_value / total_inverse_value
                            fish_probs.append((dict(f), prob))
                        
                        # 基于概率选择鱼
                        fish_roll = random.random()
                        cum_prob = 0
                        fish = fish_probs[0][0]  # 默认选第一条
                        
                        for f, prob in fish_probs:
                            cum_prob += prob
                            if fish_roll <= cum_prob:
                                fish = f
                                break
            
            # 考虑减少垃圾鱼的概率（如果选中了垃圾鱼且有垃圾减免）
            is_garbage = fish['rarity'] == 1 and fish['base_value'] <= 2  # 简单判断是否为垃圾
            if is_garbage and garbage_reduction > 0 and random.random() < garbage_reduction:
                # 重新随机一条非垃圾鱼
                with self.db._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT fish_id, name, rarity, base_value, min_weight, max_weight
                        FROM fish
                        WHERE NOT (rarity = 1 AND base_value <= 2)
                        ORDER BY RANDOM()
                        LIMIT 1
                    """)
                    non_garbage = cursor.fetchone()
                    if non_garbage:
                        fish = dict(non_garbage)
            
            # <<< 核心修复：让 quantity_modifier 生效！>>>
            # a. 计算最终数量
            final_quantity = int(quantity_modifier)
            # b. 处理小数部分，增加随机性
            if random.random() < (quantity_modifier - final_quantity):
                final_quantity += 1

            # 计算鱼的重量和价值
            weight = random.randint(fish['min_weight'], fish['max_weight']) * final_quantity
            if player_class == 'hunter' and random.random() < 0.05: # 巨物猎手被动
                extra_weight_multiplier = random.uniform(1.1, 1.3)
                weight = int(weight * extra_weight_multiplier)
            
            # 应用价值修饰符（包括饰品的金币加成）
            value = int(fish['base_value'] * quality_modifier) *  final_quantity
            
            # 应用金币加成（如果有装备饰品）
            if equipped_accessory:
                acc_coin_bonus = equipped_accessory.get('bonus_coin_modifier', 1.0)
                value = int(value * acc_coin_bonus)
            
            # 更新用户库存和统计
            self.db.add_fish_to_inventory(user_id, fish['fish_id'])
            self.db.update_user_fishing_stats(user_id, weight, value)
            
            # 添加钓鱼记录
            self.db.add_fishing_record(
                user_id=user_id,
                fish_id=fish['fish_id'],
                weight=weight,
                value=value,
                bait_id=current_bait.get('bait_id') if current_bait else (consumed_bait.get('bait_id') if consumed_bait else None)
            )
            
            # 构建结果，包含鱼饵效果信息
            result = {
                "success": True,
                "fish": {
                    "name": fish['name'],
                    "rarity": fish['rarity'],
                    "weight": weight,
                    "value": value
                }
            }
            
            if bait_effect:
                result["bait_effect"] = bait_effect
                
            # 添加装备效果信息
            equipment_effects = []
            if quality_modifier > 1.0:
                equipment_effects.append(f"鱼价值增加{int((quality_modifier-1)*100)}%")
            if quantity_modifier > 1.0:
                equipment_effects.append(f"渔获数量增加{int((quantity_modifier-1)*100)}%")
            if rare_chance > 0.0:
                equipment_effects.append(f"稀有度提升{int(rare_chance*100)}%")
            if garbage_reduction > 0.0:
                equipment_effects.append(f"垃圾减少{int(garbage_reduction*100)}%")
                
            if equipment_effects:
                result["equipment_effects"] = equipment_effects
            self.db.set_user_last_fishing_time(user_id)
            return result
        else:
            # 钓鱼失败时，单独更新最后钓鱼时间
            self.db.set_user_last_fishing_time(user_id)
            failure_msg = "💨 什么都没钓到..."
            if bait_effect:
                failure_msg += f"（鱼饵效果：{bait_effect}）"
            return {"success": False, "message": failure_msg}

    def toggle_auto_fishing(self, user_id: str) -> Dict:
        """开启/关闭自动钓鱼"""
        error = self._check_registered_or_return(user_id)
        if error:
            return error
            
        success = self.db.toggle_user_auto_fishing(user_id)
        if success:
            current_status = self.db.get_user_auto_fishing_status(user_id)
            status_text = "开启" if current_status else "关闭"
            return {"success": True, "message": f"自动钓鱼已{status_text}", "status": current_status}
        else:
            return {"success": False, "message": "操作失败，请稍后再试"}

    def sell_all_fish(self, user_id: str) -> Dict:
        """卖出所有鱼"""
        error = self._check_registered_or_return(user_id)
        if error:
            return error
            
        # 获取总价值
        total_value = self.db.get_user_fish_inventory_value(user_id)
        if total_value <= 0:
            return {"success": False, "message": "你没有可以卖出的鱼"}
            
        repayment_result = self.process_income_repayment(user_id, total_value)
        final_income = repayment_result['final_income']

        # 清空库存并更新金币
        self.db.clear_user_fish_inventory(user_id)
        self.db.update_user_coins(user_id, final_income)
        
        return {"message": f"已卖出所有鱼，获得 {final_income} {get_coins_name()}。{repayment_result['repayment_message']}"}

    def sell_fish_by_rarity(self, user_id: str, rarity: int) -> Dict:
        """卖出指定稀有度的鱼"""
        error = self._check_registered_or_return(user_id)
        if error:
            return error
            
        # 验证稀有度参数
        if not (1 <= rarity <= 5):
            return {"success": False, "message": "无效的稀有度，应为1-5之间的整数"}
            
        # 获取指定稀有度鱼的总价值
        total_value = self.db.get_user_fish_inventory_value_by_rarity(user_id, rarity)
        if total_value <= 0:
            return {"success": False, "message": f"你没有稀有度为 {rarity} 的鱼可以卖出"}
            
        # 清空指定稀有度的鱼并更新金币
        self.db.clear_user_fish_by_rarity(user_id, rarity)
        self.db.update_user_coins(user_id, total_value)
        
        return {"success": True, "message": f"已卖出稀有度为 {rarity} 的鱼，获得 {total_value} 金币"}

    def get_all_titles(self) -> Dict:
        """查看所有称号"""
        titles = self.db.get_all_titles()
        return {"success": True, "titles": titles}

    def get_all_achievements(self) -> Dict:
        """查看所有成就"""
        achievements = self.db.get_all_achievements()
        return {"success": True, "achievements": achievements}

    def get_user_titles(self, user_id: str) -> Dict:
        """查看用户已有称号"""
        error = self._check_registered_or_return(user_id)
        if error:
            return error
            
        titles = self.db.get_user_titles(user_id)
        return {"success": True, "titles": titles}

    def get_user_achievements(self, user_id: str) -> Dict:
        """查看用户已有成就"""
        error = self._check_registered_or_return(user_id)
        if error:
            return error
            
        # 获取所有成就
        all_achievements = self.db.get_all_achievements()
        
        # 获取用户成就进度
        progress_records = self.db.get_user_achievement_progress(user_id)
        progress_map = {record['achievement_id']: record for record in progress_records}
        
        # 获取用户统计数据
        stats = self.db.get_user_fishing_stats(user_id)
        
        # 处理每个成就
        achievements = []
        for achievement in all_achievements:
            achievement_id = achievement['achievement_id']
            progress_record = progress_map.get(achievement_id, {
                'current_progress': 0,
                'completed_at': None,
                'claimed_at': None
            })
            
            # 计算当前进度
            current_progress = progress_record['current_progress']
            if current_progress == 0:  # 如果进度为0，重新计算
                if achievement['target_type'] == 'total_fish_count':
                    current_progress = stats.get('total_count', 0)
                elif achievement['target_type'] == 'total_coins_earned':
                    current_progress = stats.get('total_value', 0)
                elif achievement['target_type'] == 'total_weight_caught':
                    current_progress = stats.get('total_weight', 0)
                elif achievement['target_type'] == 'specific_fish_count':
                    if achievement['target_fish_id'] is None:
                        current_progress = self.db.get_user_unique_fish_count(user_id)
                    else:
                        current_progress = self.db.get_user_specific_fish_count(user_id, achievement['target_fish_id'])
                
                # 更新进度
                self.db.update_user_achievement_progress(
                    user_id, 
                    achievement_id, 
                    current_progress,
                    current_progress >= achievement['target_value']
                )
            
            achievements.append({
                **achievement,
                'is_completed': progress_record['completed_at'] is not None,
                'is_claimed': progress_record['claimed_at'] is not None,
                'progress': current_progress,
                'target_value': achievement['target_value']
            })
        
        return {"success": True, "achievements": achievements}

    def get_all_baits(self) -> Dict:
        """查看所有鱼饵"""
        baits = self.db.get_all_baits()
        return {"success": True, "baits": baits}

    def get_user_baits(self, user_id: str) -> Dict:
        """查看用户已有鱼饵"""
        error = self._check_registered_or_return(user_id)
        if error:
            return error
            
        baits = self.db.get_user_baits(user_id)
        return {"success": True, "baits": baits}

    def buy_bait(self, user_id: str, bait_id: int, quantity: int = 1) -> Dict:
        """购买鱼饵"""
        error = self._check_registered_or_return(user_id)
        if error:
            return error
            
        # 获取鱼饵信息
        bait = self.db.get_bait_info(bait_id)
        if not bait:
            return {"success": False, "message": "鱼饵不存在"}
            
        cost_per_unit = bait['cost']
        message_prefix = ""

        player_class = self.db.get_player_class(user_id)
        if player_class == 'tycoon':
            cost_per_unit = int(cost_per_unit * 0.9)
            message_prefix = "(大亨九折) "

        total_cost = cost_per_unit * quantity
        # 检查用户金币是否足够
        user_coins = self.db.get_user_coins(user_id)
        #total_cost = bait['cost'] * quantity
        if user_coins < total_cost:
            return {"success": False, "message": f"金币不足，需要 {total_cost} 金币"}
            
        # 扣除金币并添加鱼饵
        self.db.update_user_coins(user_id, -total_cost)
        self.db.add_bait_to_inventory(user_id, bait_id, quantity)
        
        #return {"success": True, "message": f"成功购买 {bait['name']} x{quantity}"}
        return {"success": True, "message": f"{message_prefix}成功以 {total_cost} 金币购买 {bait['name']} x{quantity}"}

    def get_all_rods(self) -> Dict:
        """查看所有鱼竿"""
        rods = self.db.get_all_rods()
        return {"success": True, "rods": rods}

    def get_user_rods(self, user_id: str) -> Dict:
        """查看用户已有鱼竿"""
        error = self._check_registered_or_return(user_id)
        if error:
            return error
            
        rods = self.db.get_user_rods(user_id)
        return {"success": True, "rods": rods}

    def buy_rod(self, user_id: str, rod_id: int) -> Dict:
        """购买鱼竿"""
        error = self._check_registered_or_return(user_id)
        if error:
            return error
            
        # 获取鱼竿信息
        rod = self.db.get_rod_info(rod_id)
        if not rod:
            return {"success": False, "message": "鱼竿不存在"}
            
        # 检查鱼竿是否可购买
        if rod['source'] != 'shop' or rod['purchase_cost'] is None:
            return {"success": False, "message": "此鱼竿无法直接购买"}

        cost = rod['purchase_cost']
        message_prefix = ""

        # 应用鱼市大亨折扣
        player_class = self.db.get_player_class(user_id)
        if player_class == 'tycoon':
            cost = int(cost * 0.9)
            message_prefix = "(大亨九折) "
            
        # 检查用户金币是否足够
        user_coins = self.db.get_user_coins(user_id)
        if user_coins < rod['purchase_cost']:
            return {"success": False, "message": f"金币不足，需要 {rod['purchase_cost']} 金币"}
            
        # 扣除金币并添加鱼竿
        self.db.update_user_coins(user_id, -cost)
        self.db.add_rod_to_inventory(user_id, rod_id, rod['durability'])
        
        #return {"success": True, "message": f"成功购买 {rod['name']}"}
        return {"success": True, "message": f"{message_prefix}成功以 {cost} 金币购买 {rod['name']}"}

    def get_all_accessories(self) -> Dict:
        """查看所有饰品"""
        accessories = self.db.get_all_accessories()
        return {"success": True, "accessories": accessories}

    def get_user_accessories(self, user_id: str) -> Dict:
        """查看用户已有饰品"""
        error = self._check_registered_or_return(user_id)
        if error:
            return error
            
        accessories = self.db.get_user_accessories(user_id)
        return {"success": True, "accessories": accessories}

    def use_bait(self, user_id: str, bait_id: int) -> Dict:
        """使用鱼饵"""
        error = self._check_registered_or_return(user_id)
        if error:
            return error

        # 获取鱼饵信息
        bait_info = self.db.get_bait_info(bait_id)
        if not bait_info:
            return {"success": False, "message": "鱼饵不存在"}
        
        # 设置用户当前鱼饵
        success = self.db.set_user_current_bait(user_id, bait_id)
        if not success:
            return {"success": False, "message": f"你没有【{bait_info['name']}】，请先购买"}

        # 构建响应消息
        duration_text = ""
        if bait_info.get('duration_minutes', 0) > 0:
            duration_text = f"，持续时间：{bait_info['duration_minutes']}分钟"
            
        return {
            "success": True, 
            "message": f"成功使用【{bait_info['name']}】{duration_text}，效果：{bait_info['effect_description']}",
            "bait": bait_info
        }

    def get_current_bait(self, user_id: str) -> Dict:
        """获取用户当前使用的鱼饵"""
        error = self._check_registered_or_return(user_id)
        if error:
            return error
            
        bait_info = self.db.get_user_current_bait(user_id)
        if not bait_info:
            return {"success": False, "message": "你当前没有使用任何鱼饵"}
            
        remaining_text = ""
        if bait_info.get('duration_minutes', 0) > 0:
            remaining_text = f"，剩余时间：{int(bait_info.get('remaining_minutes', 0))}分钟"
            
        return {
            "success": True,
            "message": f"当前使用的鱼饵：【{bait_info['name']}】{remaining_text}，效果：{bait_info['effect_description']}",
            "bait": bait_info
        }

    def get_all_gacha_pools(self) -> Dict:
        """获取所有抽奖奖池信息"""
        pools = self.db.get_all_gacha_pools()
        return {
            "success": True,
            "pools": pools
        }
        
    def get_gacha_pool_details(self, pool_id: int) -> Dict:
        """获取特定奖池的详细信息"""
        pool_details = self.db.get_gacha_pool_details(pool_id)
        if not pool_details:
            return {"success": False, "message": "奖池不存在"}
            
        return {
            "success": True,
            "pool_details": pool_details
        }
        
    def multi_gacha(self, user_id: str, pool_id: int, count: int = 10) -> Dict:
        """执行十连抽卡"""
        # 获取抽卡池信息
        pool_info = self.db.get_gacha_pool_info(pool_id)
        if not pool_info:
            return {"success": False, "message": "抽卡池不存在"}

        # 检查用户金币是否足够
        cost = pool_info.get('cost_coins', 0) * count
        user_coins = self.db.get_user_coins(user_id)
        if user_coins < cost:
            return {"success": False, "message": f"金币不足，需要 {cost} 金币"}

        # 执行多次抽卡
        results = []
        rewards_by_rarity = {}

        for _ in range(count):
            result = self._perform_single_gacha(user_id, pool_id)
            if not result.get("success"):
                # 如果抽卡失败，退还金币
                self.db.update_user_coins(user_id, cost)
                return result

            item = result.get("item", {})
            results.append(item)

            # 按稀有度分组
            rarity = item.get("rarity", 1)
            if rarity not in rewards_by_rarity:
                rewards_by_rarity[rarity] = []
            rewards_by_rarity[rarity].append(item)

        return {
            "success": True,
            "results": results,
            "rewards_by_rarity": rewards_by_rarity
        }
    
    def _perform_single_gacha(self, user_id: str, pool_id: int) -> Dict:
        """执行单次抽卡"""
        # 获取抽卡池信息
        pool_info = self.db.get_gacha_pool_info(pool_id)
        if not pool_info:
            return {"success": False, "message": "抽卡池不存在"}

        # 检查用户金币是否足够
        cost = pool_info.get('cost_coins', 0)
        user_coins = self.db.get_user_coins(user_id)
        if user_coins < cost:
            return {"success": False, "message": f"金币不足，需要 {cost} 金币"}

        # 获取抽卡池物品列表
        items = self.db.get_gacha_pool_items(pool_id)
        if not items:
            return {"success": False, "message": "抽卡池为空"}

        # 计算总权重
        total_weight = sum(item['weight'] for item in items)
        if total_weight <= 0:
            return {"success": False, "message": "抽卡池配置错误"}

        # 随机抽取物品
        rand = random.uniform(0, total_weight)
        current_weight = 0
        selected_item = None

        # 将物品随机打乱
        items = random.sample(items, len(items))

        for item in items:
            current_weight += item['weight']
            if rand <= current_weight:
                selected_item = item
                break

        if not selected_item:
            return {"success": False, "message": "抽卡失败"}
        # 扣除金币
        if not self.db.update_user_coins(user_id, -cost):
            return {"success": False, "message": "扣除金币失败"}

        # 根据物品类型处理奖励
        item_type = selected_item['item_type']
        item_id = selected_item['item_id']
        quantity = selected_item.get('quantity', 1)

        # 获取物品详细信息
        item_info = None
        if item_type == 'rod':
            item_info = self.db.get_rod_info(item_id)
        elif item_type == 'accessory':
            item_info = self.db.get_accessory_info(item_id)
        elif item_type == 'bait':
            item_info = self.db.get_bait_info(item_id)
        elif item_type == 'coins':
            item_info = {'name': '金币', 'rarity': 1}


        if not item_info:
            return {"success": False, "message": "获取物品信息失败"}

        # 发放奖励
        success = False
        if item_type == 'rod':
            success = self.db.add_rod_to_inventory(user_id, item_id)
        elif item_type == 'accessory':
            success = self.db.add_accessory_to_inventory(user_id, item_id)
        elif item_type == 'bait':
            success = self.db.add_bait_to_inventory(user_id, item_id, quantity)
        elif item_type == 'coins':
            success = self.db.update_user_coins(user_id, quantity)
        elif item_type == 'titles':
            success = self.db.add_title_to_user(user_id, item_id)
        elif item_type == 'premium_currency':
            success = self.db.update_user_currency(user_id, 0, item_id * quantity)

        if not success:
            # 如果发放失败，退还金币
            self.db.update_user_coins(user_id, cost)
            return {"success": False, "message": "发放奖励失败"}

        # 记录抽卡结果
        self.db.record_gacha_result(
            user_id=user_id,
            gacha_pool_id=pool_id,
            item_type=item_type,
            item_id=item_id,
            item_name=item_info.get('name', '未知物品'),
            quantity=quantity,
            rarity=item_info.get('rarity', 1)
        )

        return {
            "success": True,
            "item": {
                "type": item_type,
                "id": item_id,
                "name": item_info.get('name', '未知物品'),
                "quantity": quantity,
                "rarity": item_info.get('rarity', 1)
            }
        }
    
    def gacha(self, user_id: str, pool_id: int) -> Dict:
        """进行一次抽奖"""
        error = self._check_registered_or_return(user_id)
        if error:
            return error
            
        # 获取抽奖池信息
        pool = self.db.get_gacha_pool_info(pool_id)
        if not pool:
            return {"success": False, "message": "抽奖池不存在"}
        logger.info(pool)
            
        # 检查用户货币是否足够
        user_currency = self.get_user_currency(user_id)
        logger.info(user_currency)
        if user_currency['coins'] < pool['cost_coins']:
            return {"success": False, "message": "货币不足，无法抽奖"}
        
        # 执行抽奖
        result = self._perform_single_gacha(user_id, pool_id)
        self.LOG.info(f"======= 抽奖结果: {result} =======")
        if not result.get('success'):
            return {"success": False, "message": result.get("message")}
            
        # 将物品信息添加到rewards_by_rarity中，便于前端显示
        rewards_by_rarity = {}
        item = result.get('item', {})
        rarity = item.get('rarity', 1)
        rewards_by_rarity[rarity] = [item]
            
        return {
            "success": True,
            "message": f"恭喜获得: {item.get('name', '未知物品')}",
            "item": item,
            "rewards_by_rarity": rewards_by_rarity
        }

    # --- 自动钓鱼相关方法 ---
    def get_fishing_cost(self) -> int:
        """获取钓鱼成本"""
        # 实际项目中可能会根据不同因素计算钓鱼成本，这里简化为固定值
        return 10

    def start_auto_fishing_task(self):
        """启动自动钓鱼任务"""
        if self.auto_fishing_thread and self.auto_fishing_thread.is_alive():
            self.LOG.info("自动钓鱼线程已在运行中")
            return
            
        self.auto_fishing_running = True
        self.auto_fishing_thread = threading.Thread(target=self._auto_fishing_loop, daemon=True)
        self.auto_fishing_thread.start()
        self.LOG.info("自动钓鱼线程已启动")
        
    def stop_auto_fishing_task(self):
        """停止自动钓鱼任务"""
        self.auto_fishing_running = False
        if self.auto_fishing_thread:
            self.auto_fishing_thread.join(timeout=1.0)
            self.LOG.info("自动钓鱼线程已停止")

    def _auto_fishing_loop(self):
        """自动钓鱼循环任务"""
        while self.auto_fishing_running:
            try:
                # 获取所有开启自动钓鱼的用户
                auto_fishing_users = self.db.get_auto_fishing_users()
                now_today = get_utc4_today()
                # 新的一天，对资产大于1000000的用户扣除2%的税
                if now_today != self.today:
                    self.today = now_today
                    self.db.apply_daily_tax_to_high_value_users()
                if auto_fishing_users:
                    self.LOG.info(f"执行自动钓鱼任务，{len(auto_fishing_users)}个用户")
                    
                    for user_id in auto_fishing_users:
                        try:
                            # 检查CD时间
                            utc_time = datetime.utcnow()
                            utc_plus_4 = utc_time + timedelta(hours=4)
                            current_time = utc_plus_4.timestamp()
                            last_time = self.db.get_last_fishing_time(user_id)

                            # 检查用户是否装备了海洋之心
                            equipped_accessory = self.db.get_user_equipped_accessory(user_id)
                            if equipped_accessory and equipped_accessory.get('name') == "海洋之心":
                                # 海洋之心效果：减少CD时间
                                last_time -= 40  # 减少2分钟CD

                            base_cd = 120
                            forging_level = self.db.get_user_forging_level(user_id)
                            bonuses = enhancement_config.get_bonuses_for_level(forging_level)
                            cd_reduction = bonuses['fishing_cd_reduction']

                            final_cd = base_cd - cd_reduction

                            if current_time - last_time < final_cd:
                            #if current_time - last_time < 60:  # 3分钟CD
                                self.LOG.debug(f"用户 {user_id} 钓鱼CD中，跳过")
                                continue
                                
                            # 检查金币是否足够
                            user_coins = self.db.get_user_coins(user_id)
                            if user_coins < self.get_fishing_cost():
                                # 金币不足，关闭自动钓鱼
                                self.db.set_auto_fishing_status(user_id, False)
                                self.LOG.info(f"用户 {user_id} 金币不足，已关闭自动钓鱼")
                                continue
                            
                            # 执行钓鱼
                            result = self.fish(user_id, is_auto=True)
                            
                            # 记录日志
                            if result["success"]:
                                fish = result["fish"]
                                log_message = f"用户 {user_id} 自动钓鱼成功: {fish['name']}，稀有度: {fish['rarity']}，价值: {fish['value']}"
                            else:
                                log_message = f"用户 {user_id} 自动钓鱼失败: {result['message']}"
                                
                            self.LOG.info(log_message)
                            
                        except Exception as e:
                            self.LOG.error(f"用户 {user_id} 自动钓鱼出错: {e}")
                
                # 每40s检查一次
                time.sleep(100)
                
            except Exception as e:
                self.LOG.error(f"自动钓鱼任务出错: {e}", exc_info=True)
                time.sleep(60)  # 出错后等待1分钟再重试
                
    def set_user_auto_fishing(self, user_id: str, status: bool) -> Dict:
        """设置用户自动钓鱼状态"""
        error = self._check_registered_or_return(user_id)
        if error:
            return error
            
        # 如果启用自动钓鱼，检查用户钱是否够钓鱼成本
        if status:
            user_coins = self.db.get_user_coins(user_id)
            if user_coins < self.get_fishing_cost():
                return {"success": False, "message": "金币不足，无法开启自动钓鱼"}
        
        success = self.db.set_auto_fishing_status(user_id, status)
        if success:
            status_text = "开启" if status else "关闭"
            return {"success": True, "message": f"已{status_text}自动钓鱼"}
        else:
            return {"success": False, "message": "设置自动钓鱼状态失败，请稍后再试"}

    def is_auto_fishing_enabled(self, user_id: str) -> bool:
        """检查用户是否开启了自动钓鱼"""
        error = self._check_registered_or_return(user_id)
        if error:
            return False
            
        # 直接使用之前实现的获取自动钓鱼状态方法
        return self.db.get_user_auto_fishing_status(user_id)

    def get_fish_pond(self, user_id: str) -> Dict:
        """查看用户的鱼塘（所有钓到的鱼）"""
        error = self._check_registered_or_return(user_id)
        if error:
            return error
            
        # 获取用户的鱼类库存
        fish_inventory = self.db.get_user_fish_inventory(user_id)
        
        # 获取鱼塘统计信息
        stats = self.db.get_user_fish_stats(user_id)
        
        if not fish_inventory:
            return {
                "success": True, 
                "message": "你的鱼塘里还没有鱼，快去钓鱼吧！",
                "stats": stats,
                "fishes": []
            }
        
        # 按稀有度分组整理鱼类
        fish_by_rarity = {}
        for fish in fish_inventory:
            rarity = fish['rarity']
            if rarity not in fish_by_rarity:
                fish_by_rarity[rarity] = []
            fish_by_rarity[rarity].append(fish)
        
        return {
            "success": True,
            "message": f"你的鱼塘里有 {stats.get('total_count', 0)} 条鱼，总价值: {stats.get('total_value', 0)} 金币",
            "stats": stats,
            "fish_by_rarity": fish_by_rarity,
            "fishes": fish_inventory
        }

    def daily_sign_in(self, user_id: str) -> Dict:
        """用户每日签到，随机获得100-300金币"""
        error = self._check_registered_or_return(user_id)
        if error:
            return error
            
        # 检查用户今天是否已经签到
        if self.db.check_daily_sign_in(user_id):
            return {"success": False, "message": "你今天已经签到过了，明天再来吧！"}
        
        # 检查是否需要重置连续登录天数（昨天没有签到）
        self.db.reset_login_streak(user_id)
        
        # 随机生成今天的签到奖励金币（100-300之间）
        coins_reward = random.randint(100, 300)
        player_class = self.db.get_player_class(user_id)
        if player_class == 'child':
            bonus = int(coins_reward * 0.5)
            coins_reward += bonus
        
        # 记录签到并发放奖励
        if self.db.record_daily_sign_in(user_id, coins_reward):
            # 获取当前连续签到天数
            consecutive_days = self.db.get_consecutive_login_days(user_id)
            
            # 构建返回消息
            result = {
                "success": True,
                "message": f"签到成功！获得 {coins_reward} 金币",
                "coins_reward": coins_reward,
                "consecutive_days": consecutive_days
            }
            
            # 如果连续签到达到特定天数，给予额外奖励
            if consecutive_days in [7, 14, 30, 60, 90, 180, 365]:
                bonus_coins = consecutive_days * 10  # 简单计算额外奖励
                self.db.update_user_coins(user_id, bonus_coins)
                result["bonus_coins"] = bonus_coins
                result["message"] += f"，连续签到 {consecutive_days} 天，额外奖励 {bonus_coins} 金币！"
                
            if player_class == 'child': # 在返回消息中体现
                result["message"] += f" (海洋之子加成 +{bonus}!)"

            return result
        else:
            return {"success": False, "message": "签到失败，请稍后再试"}

    def equip_accessory(self, user_id: str, accessory_instance_id: int) -> Dict:
        """装备指定的饰品"""
        error = self._check_registered_or_return(user_id)
        if error:
            return error
            
        # 检查饰品是否存在并属于用户
        if self.db.equip_accessory(user_id, accessory_instance_id):
            # 获取饰品信息
            accessory = self.db.get_user_equipped_accessory(user_id)
            if accessory:
                return {
                    "success": True,
                    "message": f"成功装备【{accessory['name']}】！",
                    "accessory": accessory
                }
            else:
                return {
                    "success": True,
                    "message": "饰品已装备，但无法获取详细信息"
                }
        else:
            return {
                "success": False,
                "message": "装备饰品失败，请确认该饰品属于你"
            }
            
    def unequip_accessory(self, user_id: str) -> Dict:
        """取消装备当前饰品"""
        error = self._check_registered_or_return(user_id)
        if error:
            return error
            
        if self.db.unequip_accessory(user_id):
            return {
                "success": True,
                "message": "已取消装备当前饰品"
            }
        else:
            return {
                "success": False,
                "message": "取消装备饰品失败"
            }
            
    def get_user_equipped_accessory(self, user_id: str) -> Dict:
        """获取用户当前装备的饰品"""
        error = self._check_registered_or_return(user_id)
        if error:
            return error
            
        accessory = self.db.get_user_equipped_accessory(user_id)
        if not accessory:
            return {"success": True, "accessory": None}
            
        return {"success": True, "accessory": accessory}

    def get_user_currency(self, user_id: str) -> Dict:
        """获取用户的货币信息"""
        error = self._check_registered_or_return(user_id)
        if error:
            return error
            
        # 获取用户的金币和钻石数量
        coins = self.db.get_user_coins(user_id)
        # premium_currency = self.db.get_user_premium_currency(user_id)
        
        return {
            "success": True,
            "coins": coins,
            "premium_currency": 0
        }

    def adjust_gacha_pool_weights(self) -> Dict:
        """调整奖池物品权重，使稀有物品更难抽出"""
        success = self.db.adjust_gacha_pool_weights()
        if success:
            return {
                "success": True,
                "message": "奖池权重调整成功，稀有物品现在更难抽出"
            }
        else:
            return {
                "success": False,
                "message": "奖池权重调整失败，请检查日志"
            }

    def check_wipe_bomb_available(self, user_id: str) -> bool:
        """检查用户今天是否已经进行了3次擦弹"""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            today = get_utc4_today().isoformat()
            cursor.execute("""
                SELECT COUNT(*) as count FROM wipe_bomb_log
                WHERE user_id = ? AND DATE(timestamp) = ?
            """, (user_id, today))
            result = cursor.fetchone()
            return result['count'] < 3  # 如果次数小于3，表示今天还可以进行擦弹

    def perform_wipe_bomb(self, user_id: str, contribution_amount: int) -> Dict:
        """执行擦弹操作，向公共奖池投入金币并获得随机倍数的奖励"""
        error = self._check_registered_or_return(user_id)
        if error:
            return error
            
        # 检查是否已经进行过擦弹
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            today = get_utc4_today().isoformat()
            cursor.execute("""
                SELECT COUNT(*) as count FROM wipe_bomb_log
                WHERE user_id = ? AND DATE(timestamp) = ?
            """, (user_id, today))
            result = cursor.fetchone()
            count = result['count']
            if count >= 3:
                return {"success": False, "message": "你今天已经使用了3次擦弹，明天再来吧！"}

        # 验证投入金额
        if contribution_amount <= 0:
            return {"success": False, "message": "投入金额必须大于0"}
            
        # 检查用户金币是否足够
        user_coins = self.db.get_user_coins(user_id)
        if user_coins < contribution_amount:
            return {"success": False, "message": f"金币不足，当前拥有 {user_coins} 金币"}
            
        # 扣除用户金币
        self.db.update_user_coins(user_id, -contribution_amount)
        
        # 使用加权随机算法生成奖励倍数（0-10倍，保留1位小数）
        # 定义倍数区间和对应的权重
        ranges = [
            (0.0, 0.5, 35),    # 0.0-0.5倍，权重35
            (0.5, 1.0, 25),    # 0.5-1.0倍，权重25
            (1.0, 2.0, 20),    # 1.0-2.0倍，权重20
            (2.0, 3.0, 10),    # 2.0-3.0倍，权重10
            (3.0, 5.0, 7),     # 3.0-5.0倍，权重7
            (5.0, 8.0, 2),     # 5.0-8.0倍，权重2
            (8.0, 10.0, 1),    # 8.0-10.0倍，权重1
        ]
        
        # 计算总权重
        total_weight = sum(weight for _, _, weight in ranges)
        
        # 随机选择一个区间
        random_value = random.random() * total_weight
        current_weight = 0
        selected_range = ranges[0]  # 默认第一个区间
        
        for range_min, range_max, weight in ranges:
            current_weight += weight
            if random_value <= current_weight:
                selected_range = (range_min, range_max, weight)
                break
                
        # 在选中的区间内随机生成倍数值
        range_min, range_max, _ = selected_range
        reward_multiplier = round(random.uniform(range_min, range_max), 1)
        # <<< 新增代码开始 (幸运之手) >>>
        # 检查职业是否为宝藏探寻者，并应用【幸运之手】被动
        player_class = self.db.get_player_class(user_id)
        skill_message = ""
        if player_class == 'seeker':
            # 将下限提高0.2
            modified_multiplier = reward_multiplier + 0.2
            # 确保最终结果不低于0.5
            final_multiplier = max(0.5, modified_multiplier)

            if final_multiplier > reward_multiplier:
                skill_message = f" (幸运之手发动，倍率提升!)"
            reward_multiplier = final_multiplier
        # <<< 新增代码结束 >>>
        #reward_multiplier = 10.0
        # 检查并应用“命运硬币”Buff
        active_buff = self.db.get_user_buff(user_id)
        if active_buff and active_buff['type'] == 'seeker_skill':
            if reward_multiplier < 1.0:
                reward_multiplier = 1.0  # 保本
            elif random.random() < 0.5:
                reward_multiplier += 0.5 # 50%几率+0.5
            # 使用后立即清除Buff
            self.db.clear_user_buff(user_id)
        
        # 计算实际奖励金额
        reward_amount = int(contribution_amount * reward_multiplier)
        
        # 将奖励金额添加到用户账户
        self.db.update_user_coins(user_id, reward_amount)
        
        # 记录擦弹操作
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO wipe_bomb_log 
                (user_id, contribution_amount, reward_multiplier, reward_amount, timestamp)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, contribution_amount, reward_multiplier, reward_amount,get_utc4_now().isoformat()))
            conn.commit()
        
        # 构建返回消息
        profit = reward_amount - contribution_amount
        profit_text = f"盈利 {profit}" if profit > 0 else f"亏损 {-profit}"
        remaining = 2 - count  # 计算剩余次数
        
        return {
            "success": True,
            "message": f"擦弹结果：投入 {contribution_amount} 金币，获得 {reward_multiplier}倍 奖励{skill_message}，共 {reward_amount} 金币，{profit_text}！今天还可以擦弹 {remaining} 次。",
            "contribution": contribution_amount,
            "multiplier": reward_multiplier,
            "reward": reward_amount,
            "profit": profit,
            "remaining_today": remaining
        }

    def get_wipe_bomb_history(self, user_id: str, limit: int = 10) -> Dict:
        """获取用户的擦弹历史记录"""
        error = self._check_registered_or_return(user_id)
        if error:
            return error
            
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            # 获取历史记录
            cursor.execute("""
                SELECT contribution_amount, reward_multiplier, reward_amount, timestamp
                FROM wipe_bomb_log
                WHERE user_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (user_id, limit))
            
            records = []
            for row in cursor.fetchall():
                record = dict(row)
                # 计算盈利
                record['profit'] = record['reward_amount'] - record['contribution_amount']
                records.append(record)
            
            # 获取今天的擦弹次数
            today = get_utc4_today().isoformat()
            cursor.execute("""
                SELECT COUNT(*) as count FROM wipe_bomb_log
                WHERE user_id = ? AND DATE(timestamp) = ?
            """, (user_id, today))
            result = cursor.fetchone()
            count = result['count']
            remaining = 3 - count
                
            return {
                "success": True,
                "records": records,
                "count_today": count,
                "remaining_today": remaining,
                "available_today": remaining > 0
            }

    def get_user_equipment(self, user_id: str) -> Dict:
        """获取用户当前装备的鱼竿和饰品信息，包括各种加成属性"""
        error = self._check_registered_or_return(user_id)
        if error:
            return {"success": False, "message": error["message"], "equipment": {}}
            
        equipment = self.db.get_user_equipment(user_id)
        
        # 获取鱼竿详细信息
        user_rods = self.db.get_user_rods(user_id)
        equipped_rod = next((rod for rod in user_rods if rod.get('is_equipped')), None)
        
        # 获取饰品详细信息
        equipped_accessory = self.db.get_user_equipped_accessory(user_id)
        
        return {
            "success": True,
            "equipment": equipment,
            "rod": equipped_rod,
            "accessory": equipped_accessory
        }

    def equip_rod(self, user_id: str, rod_instance_id: int) -> Dict:
        """装备指定的鱼竿"""
        error = self._check_registered_or_return(user_id)
        if error:
            return error
        
        if self.db.equip_rod(user_id, rod_instance_id):
            return {"success": True, "message": "鱼竿装备成功"}
        else:
            return {"success": False, "message": "鱼竿装备失败，请确认鱼竿ID是否正确"}
            
    def get_user_fishing_records(self, user_id: str, limit: int = 10) -> Dict:
        """获取用户的钓鱼记录
        
        Args:
            user_id: 用户ID
            limit: 最多返回的记录数
            
        Returns:
            包含钓鱼记录的字典
        """
        error = self._check_registered_or_return(user_id)
        if error:
            return error
            
        records = self.db.get_user_fishing_records(user_id, limit)
        return {
            "success": True,
            "records": records,
            "count": len(records)
        }

    def start_achievement_check_task(self):
        """启动成就检查任务"""
        if self.achievement_check_thread and self.achievement_check_thread.is_alive():
            self.LOG.info("成就检查线程已在运行中")
            return
            
        self.achievement_check_running = True
        self.achievement_check_thread = threading.Thread(target=self._achievement_check_loop, daemon=True)
        self.achievement_check_thread.start()
        self.LOG.info("成就检查线程已启动")
        
    def stop_achievement_check_task(self):
        """停止成就检查任务"""
        self.achievement_check_running = False
        if self.achievement_check_thread:
            self.achievement_check_thread.join(timeout=1.0)
            self.LOG.info("成就检查线程已停止")

    def _achievement_check_loop(self):
        """成就检查循环任务"""
        while self.achievement_check_running:
            try:
                # 获取所有注册用户
                users = self.db.get_all_users()
                
                if users:
                    self.LOG.info(f"执行成就检查任务，{len(users)}个用户")
                    
                    for user_id in users:
                        try:
                            self._check_user_achievements(user_id)
                        except Exception as e:
                            self.LOG.error(f"用户 {user_id} 成就检查出错: {e}")
                
                # 每10分钟检查一次
                time.sleep(600)
                
            except Exception as e:
                self.LOG.error(f"成就检查任务出错: {e}", exc_info=True)
                time.sleep(60)  # 出错后等待1分钟再重试

    def _check_user_achievements(self, user_id: str):
        """检查单个用户的成就完成情况"""
        # 获取所有成就
        achievements = self.db.get_all_achievements()
        
        for achievement in achievements:
            try:
                # 检查成就是否完成
                is_completed = self._check_achievement_completion(user_id, achievement)
                
                if is_completed:
                    # 发放奖励
                    self._grant_achievement_reward(user_id, achievement)
                    
                    # 记录成就完成
                    self.db.update_user_achievement_progress(
                        user_id,
                        achievement['achievement_id'],
                        achievement['target_value'],
                        True
                    )
                    
                    # 记录日志
                    self.LOG.info(f"用户 {user_id} 完成成就: {achievement['name']}")
                    
            except Exception as e:
                self.LOG.error(f"检查成就 {achievement['name']} 时出错: {e}")

    def _check_achievement_completion(self, user_id: str, achievement: Dict) -> bool:
        """检查特定成就是否完成"""
        target_type = achievement['target_type']
        target_value = achievement['target_value']
        target_fish_id = achievement['target_fish_id']
        
        # 获取用户统计数据
        stats = self.db.get_user_fishing_stats(user_id)
        
        # 获取当前进度
        progress_records = self.db.get_user_achievement_progress(user_id)
        progress_record = next(
            (record for record in progress_records if record['achievement_id'] == achievement['achievement_id']),
            {'current_progress': 0}
        )
        current_progress = progress_record['current_progress']
        
        # 如果已经完成，直接返回
        if progress_record.get('completed_at') is not None:
            return False
        
        # 根据不同的目标类型检查完成情况
        if target_type == 'total_fish_count':
            return stats.get('total_count', 0) >= target_value
            
        elif target_type == 'specific_fish_count':
            if target_fish_id is None:
                # 检查不同种类鱼的数量
                unique_fish_count = self.db.get_user_unique_fish_count(user_id)
                return unique_fish_count >= target_value
            elif target_fish_id == -3:
                # 检查垃圾物品数量
                garbage_count = self.db.get_user_garbage_count(user_id)
                return garbage_count >= target_value
            elif target_fish_id == -4:
                # 检查深海鱼种类数量（重量大于3000的鱼）
                with self.db._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT COUNT(DISTINCT f.fish_id) as deep_sea_count
                        FROM fishing_records fr
                        JOIN fish f ON fr.fish_id = f.fish_id
                        WHERE fr.user_id = ? AND f.max_weight > 3000
                    """, (user_id,))
                    result = cursor.fetchone()
                    deep_sea_count = result['deep_sea_count'] if result else 0
                    return deep_sea_count >= target_value
            elif target_fish_id == -5:
                # 检查是否钓到过重量超过100kg的鱼
                return self.db.has_caught_heavy_fish(user_id, 100000)  # 100kg = 100000g
            else:
                # 检查特定鱼的捕获数量
                if target_fish_id in [-1, -2]:
                    return False
                specific_fish_count = self.db.get_user_specific_fish_count(user_id, target_fish_id)
                return specific_fish_count >= 1
                
        elif target_type == 'total_coins_earned':
            return stats.get('total_value', 0) >= target_value
            
        elif target_type == 'total_weight_caught':
            return stats.get('total_weight', 0) >= target_value
            
        elif target_type == 'wipe_bomb_profit':
            if target_value == 1:  # 第一次擦弹
                return self.db.has_performed_wipe_bomb(user_id)
            elif target_value == 10:  # 10倍奖励
                return self.db.has_wipe_bomb_multiplier(user_id, 10)
            else:  # 特定盈利金额
                return self.db.has_wipe_bomb_profit(user_id, target_value)
                
        elif target_type == 'rod_collection':
            # 检查是否有特定稀有度的鱼竿
            return self.db.has_rod_of_rarity(user_id, target_value)
            
        elif target_type == 'accessory_collection':
            # 检查是否有特定稀有度的饰品
            return self.db.has_accessory_of_rarity(user_id, target_value)
            
        return False

    def _grant_achievement_reward(self, user_id: str, achievement: Dict):
        """发放成就奖励"""
        reward_type = achievement['reward_type']
        reward_value = achievement['reward_value']
        reward_quantity = achievement['reward_quantity']
        
        if reward_type == 'coins':
            self.db.update_user_coins(user_id, reward_value * reward_quantity)
            
        elif reward_type == 'premium_currency':
            self.db.update_user_currency(user_id, 0, reward_value * reward_quantity)
            
        elif reward_type == 'title':
            self.db.grant_title_to_user(user_id, reward_value)
            
        elif reward_type == 'bait':
            self.db.add_bait_to_inventory(user_id, reward_value, reward_quantity)

    def get_user_deep_sea_fish_count(self, user_id: str) -> int:
        """获取用户钓到的深海鱼种类数量（重量大于3000的鱼）"""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(DISTINCT f.fish_id) as deep_sea_count
                FROM fishing_records fr
                JOIN fish f ON fr.fish_id = f.fish_id
                WHERE fr.user_id = ? AND f.max_weight > 3000
            """, (user_id,))
            result = cursor.fetchone()
            return result['deep_sea_count'] if result else 0

    def get_old_database_data(self, OLD_DATABASE: str):
        """获取旧数据库数据"""
        return self.db.get_old_database_data(OLD_DATABASE)

    def insert_users(self, users):
        """插入用户数据"""
        return self.db.insert_users(users)

    def use_title(self, user_id, title_id):
        """使用指定的称号"""
        error = self._check_registered_or_return(user_id)
        if error:
            return error

        # 检查称号是否存在并属于用户
        if self.db.use_title(user_id, title_id):
            # 获取当前使用的称号
            current_title = self.db.get_user_current_title(user_id)
            return {
                "success": True,
                "message": f"🎉 成功使用称号【{current_title['name']}】！",
                "title": current_title
            }
        else:
            return {
                "success": False,
                "message": "使用称号失败，请确认该称号属于你"
            }

    def sell_all_fish_keep_one_batch(self, user_id: str) -> Dict:
        """卖出用户所有鱼，但每种保留1条。"""

        try:
            inventory = self.db.get_full_inventory_with_values(user_id)
            if not inventory:
                return {"success": False, "message": "你的鱼塘是空的"}

            total_value = 0.0
            sell_details = []

            with self.db._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("BEGIN TRANSACTION")

                try:
                    for fish in inventory:
                        current_qty = fish['quantity']
                        if current_qty > 1:
                            sell_qty = current_qty - 1
                            sell_value = sell_qty * fish['base_value']

                            # 更新数量字段，只保留1条
                            cursor.execute("""
                                UPDATE user_fish_inventory
                                SET quantity = 1
                                WHERE user_id = ? AND fish_id = ?
                            """, (user_id, fish['fish_id']))

                            total_value += sell_value
                            sell_details.append({
                                "name": fish['name'],
                                "sell_count": sell_qty,
                                "value_per": fish['base_value'],
                                "total_value": sell_value,
                            })

                    if not sell_details:
                        conn.rollback()
                        return {"success": False, "message": "没有可卖出的鱼（每种至少保留一条）"}

                    # 更新用户水晶
                    cursor.execute("""
                        UPDATE users
                        SET coins = coins + ?
                        WHERE user_id = ?
                    """, (total_value, user_id))

                    conn.commit()

                    report = "🐟 卖出明细：\n" + "\n".join(
                        f"- {item['name']}×{item['sell_count']} ({item['value_per']}水晶/个)"
                        for item in sorted(sell_details, key=lambda x: -x['value_per'])
                    )

                    return {
                        "success": True,
                        "message": f"✅ 成功卖出！获得 {total_value} 水晶\n{report}",
                        "total_value": total_value,
                        "details": sell_details
                    }

                except Exception as e:
                    conn.rollback()
                    return {"success": False, "message": f"交易失败: {str(e)}"}

        except Exception as e:
            return {"success": False, "message": f"系统错误: {str(e)}"}

    def sell_rod(self, user_id, rod_instance_id):
        """卖出指定的鱼竿"""
        error = self._check_registered_or_return(user_id)
        if error:
            return error
        # 检查鱼竿是否存在并属于用户
        return self.db.sell_rod(user_id, rod_instance_id)

    def sell_accessory(self, user_id, accessory_instance_id):
        """卖出指定的饰品"""
        error = self._check_registered_or_return(user_id)
        if error:
            return error

        # 检查饰品是否存在并属于用户
        return self.db.sell_accessory(user_id, accessory_instance_id)

    def put_rod_on_sale(self, user_id, rod_instance_id, price):
        """将鱼竿放到市场上出售"""
        error = self._check_registered_or_return(user_id)
        if error:
            return error

        return self.db.put_rod_on_sale(user_id, rod_instance_id, price)

    def put_accessory_on_sale(self, user_id, accessory_instance_id, price):
        """将饰品放到市场上出售"""
        error = self._check_registered_or_return(user_id)
        if error:
            return error

        return self.db.put_accessory_on_sale(user_id, accessory_instance_id, price)

    def get_market_items(self):
        """获取市场上所有的鱼竿和饰品"""
        rods = self.db.get_market_rods()
        accessories = self.db.get_market_accessories()

        return {
            "success": True,
            "rods": rods,
            "accessories": accessories
        }

    def buy_item(self, user_id, market_id):
        """购买市场上的鱼竿或饰品"""
        error = self._check_registered_or_return(user_id)
        if error:
            return error

        return self.db.buy_item(user_id, market_id)

    def get_user_fish_inventory_capacity(self, user_id):
        """获取用户鱼塘的容量"""
        error = self._check_registered_or_return(user_id)
        if error:
            return error

        # 获取用户当前鱼塘容量
        result = self.db.get_user_fish_inventory_capacity(user_id)
        if result is None:
            return {"success": False, "message": "无法获取用户鱼塘容量"}
        return {
            "success": True,
            "capacity": result['capacity'],
            "current_count": result['current_count']
        }

    def upgrade_fish_inventory(self, user_id):
        """升级用户鱼塘容量"""
        error = self._check_registered_or_return(user_id)
        if error:
            return error

        # 先获取当前用户的鱼塘容量
        user_capacity = self.db.get_user_fish_inventory_capacity(user_id)['capacity']
        cost_coins = 0
        to_capacity = None
        if user_capacity == POND_CAPACITY_PRIMARY:
            to_capacity = POND_CAPACITY_MIDDLE
            cost_coins = 50000
        elif user_capacity == POND_CAPACITY_MIDDLE:
            to_capacity = POND_CAPACITY_ADVANCED
            cost_coins = 500000
        elif user_capacity == POND_CAPACITY_ADVANCED:
            to_capacity = POND_CAPACITY_TOP
            cost_coins = 50000000
        else:
            return {
                "success": False,
                "message": "鱼塘容量已达到最大，无法再升级"
            }

        # 检查用户是否有足够的金币
        user_coins = self.db.get_user_coins(user_id)
        if user_coins < cost_coins:
            return {"success": False, "message": f"金币不足，无法升级鱼塘容量，需要 {cost_coins} 金币"}
        # 扣除金币
        self.db.update_user_coins(user_id, -cost_coins)
        # 升级鱼塘容量
        result = self.db.upgrade_user_fish_inventory(user_id, to_capacity)
        if result:
            return {
                "success": True,
                "new_capacity": to_capacity,
                "cost": cost_coins,
            }
        else:
            return {"success": False, "message": "鱼塘升级失败，请稍后再试"}

    def steal_fish(self, user_id, target_id):
        """尝试偷取其他用户的鱼"""
        error = self._check_registered_or_return(user_id)
        if error:
            return error

        # 检查目标用户是否存在
        target_user = self.db.get_user_by_id(target_id)
        if not target_user:
            return {"success": False, "message": "目标用户不存在"}

        # # 检查用户是否有足够的金币进行偷窃
        # user_coins = self.db.get_user_coins(user_id)
        # steal_cost = 1000

        # 执行偷鱼
        return self.db.steal_fish(user_id, target_id)

    def perform_enhancement(self, user_id: str, use_luck_charm: bool = False) -> Dict:
        """执行一次强化操作"""
        error = self._check_registered_or_return(user_id)
        if error:
            return error

        current_level = self.db.get_user_forging_level(user_id)
        if current_level >= enhancement_config.MAX_FORGE_LEVEL:
            return {"success": False, "message": "已达到最高强化等级！"}

        next_level_config = enhancement_config.get_config_for_next_level(current_level)
        cost = next_level_config['cost']
        probability = next_level_config['probability']

        # --- 核心修改：幸运符逻辑 ---
        charm_message = ""
        if use_luck_charm:
            # 1. 检查是否有幸运符
            if self.db.get_special_item_count(user_id, 'luck_charm') < 1:
                return {"success": False, "message": "你没有强化幸运符。"}

            # 2. 检查是否满足使用条件 (+10及以上)
            if current_level < 9: # +9 -> +10 是第9级，所以是小于9
                 return {"success": False, "message": "强化+10及以上才能使用幸运符。"}

            # 3. 消耗幸运符并应用概率加成
            self.db.consume_special_item(user_id, 'luck_charm')
            # 概率提升20% (乘以1.2)
            original_prob = probability
            probability = min(100, probability * 1.2) # 最高不超过100%
            charm_message = f"（幸运符生效！概率从{original_prob:.1f}%提升至{probability:.1f}%）"

        # 应用海洋之子职业加成
        player_class = self.db.get_player_class(user_id)
        if player_class == 'child':
            probability += 5

        probability = min(100, probability) # 最高不超过100%

        # 检查金币
        user_coins = self.db.get_user_coins(user_id)
        if user_coins < cost:
            return {"success": False, "message": f"金币不足，强化需要 {cost} 金币。"}

        # 扣除金币
        self.db.update_user_coins(user_id, -cost)

        # 进行强化判定
        if random.uniform(0, 100) < probability:
            # 强化成功
            new_level = current_level + 1
            self.db.update_user_forging_level(user_id, new_level)
            return {
                "success": True,
                "message": f"恭喜！锻造等级提升至 +{new_level}！{charm_message}",
                "old_level": current_level,
                "new_level": new_level
            }
        else:
            # 强化失败
            return {
                "success": False,
                "message": "很遗憾，强化失败了...{charm_message}",
                "old_level": current_level,
                "new_level": current_level
            }

    def choose_player_class(self, user_id: str, class_display_name: str) -> Dict:
        """选择一个职业"""
        error = self._check_registered_or_return(user_id)
        if error:
            return error
            
        current_class = self.db.get_player_class(user_id)
        if current_class != '无':
            return {"success": False, "message": f"你已经是【{class_config.CLASSES.get(current_class, {}).get('name', '未知职业')}】了，无法重复选择。"}
        
        if class_display_name not in class_config.CLASS_MAP:
            return {"success": False, "message": "无效的职业名称。"}
            
        class_internal_name = class_config.CLASS_MAP[class_display_name]
        
        # 这里可以加入选择职业的条件判断，例如锻造等级
        forging_level = self.db.get_user_forging_level(user_id)
        if forging_level < 5:
             return {"success": False, "message": "你的锻造等级还不足+5，无法选择传承职业！"}

        if self.db.set_player_class(user_id, class_internal_name):
            return {"success": True, "message": f"恭喜你就职成为【{class_display_name}】！"}
        else:
            return {"success": False, "message": "职业选择失败，请稍后再试。"}

    def use_active_skill(self, user_id: str) -> Dict:
        """统一的主动技能发动入口 (完整实现版)"""
        error = self._check_registered_or_return(user_id)
        if error: return error

        player_class = self.db.get_player_class(user_id)
        if player_class == '无':
            return {"success": False, "message": "你没有职业，无法发动技能。"}

        # 检查CD
        last_use_str = self.db.get_last_active_skill_time(user_id)
        if last_use_str:
            last_use_time = datetime.fromisoformat(last_use_str)
            elapsed_hours = (get_utc4_now() - last_use_time).total_seconds() / 3600
            cooldowns = {'hunter': 24, 'child': 72, 'tycoon': 24, 'seeker': 24, 'plunderer': 72}
            required_cd = cooldowns.get(player_class, 9999)
            if elapsed_hours < required_cd:
                remaining_cd = required_cd - elapsed_hours
                return {"success": False, "message": f"技能冷却中，还需等待 {remaining_cd:.1f} 小时。"}

        # 检查是否已有其他Buff
        if self.db.get_user_buff(user_id):
            return {"success": False, "message": "你身上已有其他技能效果，请等待其结束后再发动新技能。"}

        # 发动技能 & 记录使用时间
        self.db.record_active_skill_use(user_id)
        
        if player_class == 'hunter':
            self.db.set_user_buff(user_id, 'hunter_skill', 1) # 1小时持续时间
            return {"success": True, "message": "【追踪巨物】已发动！接下来1小时，你将更容易遇到稀有巨物！"}
        
        elif player_class == 'child':
            if self.db.reset_daily_limits(user_id):
                return {"success": True, "message": "【丰饶之潮】已发动！你的签到和擦弹次数已刷新，今天可以再次进行了！"}
            else:
                return {"success": False, "message": "技能发动失败，请联系管理员。"}

        elif player_class == 'tycoon':
            market_items = self.get_market_items()
            rods = sorted(market_items.get('rods', []), key=lambda x: x['price'])[:5]
            accessories = sorted(market_items.get('accessories', []), key=lambda x: x['price'])[:5]
            message = "【市场洞察】\n\n最低价鱼竿:\n"
            if rods:
                for rod in rods: message += f"- {rod['rod_name']}: {rod['price']}金币 (卖家: {rod['nickname']})\n"
            else: message += "- 暂无\n"
            message += "\n最低价饰品:\n"
            if accessories:
                for acc in accessories: message += f"- {acc['accessory_name']}: {acc['price']}金币 (卖家: {acc['nickname']})\n"
            else: message += "- 暂无\n"
            return {"success": True, "message": message}

        elif player_class == 'seeker':
            self.db.set_user_buff(user_id, 'seeker_skill', 24) # 持续24小时，直到下一次擦弹
            return {"success": True, "message": "【命运硬币】已发动！你的下一次“擦弹”将受到命运的眷顾！"}

        elif player_class == 'plunderer':
            self.db.set_user_buff(user_id, 'plunderer_skill', 1) # 1小时持续时间
            return {"success": True, "message": "【暗影帷幕】已发动！接下来1小时，你的偷鱼将无视冷却！"}

        return {"success": False, "message": "你的职业没有可发动的技能。"}

    def open_treasure_chest(self, user_id: str, quantity: int = 1) -> Dict:
        """打开指定数量的“沉没的宝箱”"""
        error = self._check_registered_or_return(user_id)
        if error: return error

        if quantity < 1:
            return {"success": False, "message": "开启数量必须大于0。"}

        # 1. 检查宝箱数量是否足够
        chest_id = self.db.get_fish_id_by_name("沉没的宝箱")
        if not chest_id:
            return {"success": False, "message": "错误：找不到“沉没的宝箱”的配置。"}
        
        logger.info(user_id + str(chest_id))
        chest_count = self.db.get_user_fish_count(user_id, chest_id)
        if chest_count < quantity:
            return {"success": False, "message": f"你的“沉没的宝箱”数量不足，需要{quantity}个，但你只有{chest_count}个。"}

        # 2. 消耗指定数量的宝箱
        self.db.consume_item_from_inventory(user_id, chest_id, quantity)

        # 3. 循环计算总奖励
        total_gold_reward = 0
        extra_rewards = {}
        player_class = self.db.get_player_class(user_id)

        for _ in range(quantity):
            # ... (这部分计算奖励的逻辑与之前完全相同) ...
            gold_reward = random.randint(500, 5000)
            if player_class == 'seeker':
                gold_reward += int(gold_reward * 0.2)
            total_gold_reward += gold_reward
            if random.random() < 0.3:
                extra_rewards["万能饵"] = extra_rewards.get("万能饵", 0) + random.randint(1, 3)

        repayment_result = self.process_income_repayment(user_id, total_gold_reward)
        final_income = repayment_result['final_income']
        # 4. 一次性发放所有奖励
        self.db.update_user_coins(user_id, final_income)
        if "万能饵" in extra_rewards:
            bait_id = self.db.get_fish_id_by_name("万能饵")
            if bait_id: self.db.add_bait_to_inventory(user_id, bait_id, extra_rewards["万能饵"])
            
        # 5. 构建汇总报告
        message = [f"你打开了 {quantity} 个【沉没的宝箱】！"]
        message.append(f"💰 你总共获得了 {final_income} 金币！{repayment_result['repayment_message']}")
        #message.append(f"💰 你总共获得了 {total_gold_reward} 金币！")
        if extra_rewards:
            for item_name, qty in extra_rewards.items():
                message.append(f"✨ 额外发现了 {qty} 个【{item_name}】！")
        
        return {"success": True, "message": "\n".join(message)}


    def open_equipment_chest(self, user_id: str, chest_type: str, quantity: int = 1) -> Dict:
        """打开指定数量的装备宝箱"""
        if quantity < 1:
            return {"success": False, "message": "开启数量必须大于0。"}

        item_key = f"{chest_type}_chest"
        chest_name = "随机鱼竿宝箱" if chest_type == 'rod' else "随机饰品宝箱"

        # 1. 检查宝箱数量是否足够
        chest_count = self.db.get_special_item_count(user_id, item_key)
        if chest_count < quantity:
            return {"success": False, "message": f"你的【{chest_name}】数量不足，需要{quantity}个，但你只有{chest_count}个。"}

        # 2. 消耗指定数量的宝箱
        self.db.consume_special_item(user_id, item_key, quantity)

        # 3. 循环开箱，记录结果
        loot_summary = {}
        rarity_map = {1:'R1', 2:'R2', 3:'R3', 4:'R4', 5:'R5'}

        for _ in range(quantity):
            # ... (这部分开箱逻辑与之前完全相同) ...
            rand = random.random()
            if rand < 0.01: rarity = 5
            elif rand < 0.15: rarity = 4
            else: rarity = random.randint(1, 3)
            
            item_info = self.db.get_random_item_by_rarity(chest_type, rarity)
            if item_info:
                loot_key = f"[{rarity_map.get(rarity, 'R?')}] {item_info['name']}"
                loot_summary[loot_key] = loot_summary.get(loot_key, 0) + 1
                item_add_method = self.db.add_rod_to_inventory if chest_type == 'rod' else self.db.add_accessory_to_inventory
                item_add_method(user_id, item_info['item_id'])
        
        # 4. 构建汇总报告
        message = [f"你打开了 {quantity} 个【{chest_name}】！获得了以下物品："]
        if not loot_summary:
            message.append("...一阵风吹过，什么都没有发生。")
        else:
            sorted_loot = sorted(loot_summary.items(), key=lambda x: x[0], reverse=True)
            for item_str, qty in sorted_loot:
                message.append(f"- {item_str} x {qty}")
        
        return {"success": True, "message": "\n".join(message)}
   # def open_treasure_chest(self, user_id: str) -> Dict:
   #     """打开一个沉没的宝箱"""
   #     error = self._check_registered_or_return(user_id)
   #     if error: return error

   #     # 第一次调用时，获取并缓存宝箱的ID
   #     if self.chest_id is None:
   #         self.chest_id = self.db.get_fish_id_by_name("沉没的宝箱")
   #         if not self.chest_id:
   #             return {"success": False, "message": "错误：找不到“沉没的宝箱”的配置。"}

   #     # 消耗一个宝箱
   #     if not self.db.consume_item_from_inventory(user_id, self.chest_id):
   #         return {"success": False, "message": "你没有“沉没的宝箱”可以打开。"}

   #     # --- 开箱奖励逻辑 ---
   #     # 基础奖励：随机金币
   #     gold_reward = random.randint(500, 5000)

   #     # 检查职业技能：宝藏探寻者 - 开箱大师
   #     player_class = self.db.get_player_class(user_id)
   #     skill_message = ""
   #     if player_class == 'seeker':
   #         bonus_gold = int(gold_reward * 0.2)
   #         gold_reward += bonus_gold
   #         skill_message = f"（开箱大师加成 +{bonus_gold}金币！）"

   #     # 发放奖励
   #     self.db.update_user_coins(user_id, gold_reward)

   #     # 更多奖励的可能性 (可以继续扩展)
   #     # 例如: 随机获得1-3个稀有鱼饵
   #     extra_reward_message = ""
   #     if random.random() < 0.3: # 30%的几率获得额外奖励
   #         rare_bait_id = self.db.get_fish_id_by_name("万能饵") # 假设万能饵存在
   #         if rare_bait_id:
   #             bait_quantity = random.randint(1, 3)
   #             self.db.add_bait_to_inventory(user_id, rare_bait_id, bait_quantity)
   #             extra_reward_message = f"\n你还发现了 {bait_quantity} 个【万能饵】！"

   #     # 构造最终消息
   #     final_message = (
   #         f"你费力地打开了沉没的宝箱，发现里面装满了闪闪发光的金币！\n"
   #         f"💰 你获得了 {gold_reward} 金币！{skill_message}"
   #         f"{extra_reward_message}"
   #     )

   #     return {"success": True, "message": final_message}

    def change_player_class(self, user_id: str) -> Dict:
        """处理转职逻辑（完整版），扣除金币并清理所有职业状态"""
        error = self._check_registered_or_return(user_id)
        if error: return error

        current_class_key = self.db.get_player_class(user_id)
        if current_class_key == '无':
            return {"success": False, "message": "你当前没有职业，无需转职。"}

        COST_TO_CHANGE_CLASS = 500000
        user_coins = self.db.get_user_coins(user_id)
        if user_coins < COST_TO_CHANGE_CLASS:
            return {"success": False, "message": f"金币不足，转职需要 {COST_TO_CHANGE_CLASS} 金币。"}

        # --- 执行转职事务 ---
        # 1. 扣除金币
        if not self.db.update_user_coins(user_id, -COST_TO_CHANGE_CLASS):
            return {"success": False, "message": "金币扣除失败，请稍后再试。"}

        # 2. 清理所有与旧职业相关的状态
        # a. 清理持续性Buff
        self.db.clear_user_buff(user_id)
        # b. 清理主动技能的冷却时间
        self.db.clear_last_active_skill_time(user_id)

        # 3. 重置职业为'无'
        if self.db.set_player_class(user_id, '无'):
            old_class_name = class_config.CLASSES.get(current_class_key, {}).get('name', '旧的')
            return {
                "success": True,
                "message": (
                    f"转职成功！你已花费 {COST_TO_CHANGE_CLASS} 金币忘却了【{old_class_name}】的传承，所有相关技能效果和冷却均已重置。\n"
                    "你现在可以重新选择你的道路了！使用「/选择职业 <职业名>」来开启新的篇章。"
                )
            }
        else:
            # 如果最后一步失败，这是一个严重问题，需要回滚金币
            self.db.update_user_coins(user_id, COST_TO_CHANGE_CLASS)
            return {"success": False, "message": "转职失败，发生未知错误。金币已退还。"}

    def initiate_duel(self, attacker_id: str, defender_id: str) -> Dict:
        """发起并处理一场完整的决斗 (包含所有检查逻辑的最终版)"""
        # --- 1. 前置检查 ---
        if attacker_id == defender_id:
            return {"success": False, "message": "你不能和自己决斗！"}

        rules = pk_config.PK_RULES
        attacker_info = self.db.get_user_for_duel(attacker_id)
        defender_info = self.db.get_user_for_duel(defender_id)

        if not defender_info:
            return {"success": False, "message": "找不到被挑战的玩家。"}
        if defender_info['coins'] < rules['min_gold_to_challenge']:
            return {"success": False, "message": "对方的财富未达到挑战门槛，放过他吧……"}

        challenge_cost = int(defender_info['coins'] * rules['cost_rate'])
        if not attacker_info or attacker_info['coins'] < challenge_cost:
            return {"success": False, "message": f"挑战失败，你需要支付 {challenge_cost} 金币作为挑战费，但你的金币不足。"}

        # --- 完整的CD和次数检查 ---
        now = get_utc4_now()
        last_duel_info_str = attacker_info.get('last_duel_info', '{}')
        try:
            last_duel_info = json.loads(last_duel_info_str)
        except json.JSONDecodeError:
            last_duel_info = {}

        # a. 每日主动决斗次数检查
        daily_duels = last_duel_info.get('daily_duels', [])
        # 过滤掉不是今天的记录
        today_str = now.date().isoformat()
        todays_duels = [d for d in daily_duels if d.startswith(today_str)]

        if len(todays_duels) >= rules['daily_duel_limit']:
            return {"success": False, "message": f"你今天已经发起了 {rules['daily_duel_limit']} 次决斗，请明天再来。"}

        # b. 对同一人的决斗冷却检查
        cooldowns = last_duel_info.get('cooldowns', {})
        if defender_id in cooldowns:
           last_duel_time = datetime.fromisoformat(cooldowns[defender_id])
           elapsed_hours = (now - last_duel_time).total_seconds() / 3600
           if elapsed_hours < rules['duel_cooldown_hours']:
               remaining_hours = rules['duel_cooldown_hours'] - elapsed_hours
               return {"success": False, "message": f"你刚挑战过这位玩家，请在 {remaining_hours:.1f} 小时后再次尝试。"}

        # --- 2. 更新限制信息并扣费 ---
        # a. 记录本次决斗时间戳
        todays_duels.append(now.isoformat())
        last_duel_info['daily_duels'] = todays_duels
        # b. 更新对该玩家的冷却时间
        cooldowns[defender_id] = now.isoformat()
        last_duel_info['cooldowns'] = cooldowns
        # c. 将更新后的信息写回数据库
        self.db.update_user_last_duel_info(attacker_id, json.dumps(last_duel_info))

        # d. 扣除挑战费
        self.db.update_user_coins(attacker_id, -challenge_cost)

        # --- 3. 初始化战斗 ---
        attacker_full_info = {'id': attacker_id, 'nickname': self.db.get_user_by_id(attacker_id)['nickname'], **attacker_info}
        defender_full_info = {'id': defender_id, 'nickname': self.db.get_user_by_id(defender_id)['nickname'], **defender_info}

        # 传入service自身，让模拟器可以访问db
        simulator = _BattleSimulator(self, attacker_full_info, defender_full_info, challenge_cost)
        result = simulator.run()

        if result.get('error'):
            self.db.update_user_coins(attacker_id, challenge_cost) # 退款
            return {"success": False, "message": result['error']}

        battle_report = result['report']

        # --- 4. 处理战斗结果 ---
        if not result['winner']:
            battle_report.append("最终结果: 双方平局！")
            self.db.update_user_coins(attacker_id, challenge_cost)
            battle_report.append(f"🤝 挑战费 {challenge_cost} 金币已退还给挑战者。")
            self.db.record_duel_log(attacker_id, defender_id, 'draw', "\n".join(battle_report))
            return {"success": True, "message": "\n".join(battle_report)}

        winner, loser = result['winner'], result['loser']
        battle_report.append(f"最终结果: {winner['name']} 以 {winner['score']}-{loser['score']} 的比分获胜！")
        battle_report.append(f"🏆 {winner['name']} 赢得了 {challenge_cost} 金币奖池！")

        # 偷鱼逻辑
        num_to_steal = rules['win_steal_base_count']
        if winner['class'] == 'seeker' and random.random() < pk_config.CLASS_PK_BONUS['seeker']['win_steal_chance_bonus']:
            num_to_steal += 1
        elif random.random() < rules['win_extra_steal_chance']:
            num_to_steal += 1

        loser_lineup = [fish for fish in loser['lineup'] if self.db.get_user_specific_fish_count(loser['id'], fish['fish_id']) > 0]
        stolen_fish_list = random.sample(loser_lineup, min(num_to_steal, len(loser_lineup)))

        for fish in stolen_fish_list:
            battle_report.append(f"🎣 {winner['name']} 夺走了 {loser['name']} 的 **{fish['name']}**！")

        stolen_ids = [f['fish_id'] for f in stolen_fish_list]
        self.db.execute_duel_results(winner['id'], loser['id'], challenge_cost, stolen_ids)
        self.db.record_duel_log(attacker_id, defender_id, winner['id'], "\n".join(battle_report))

        return {"success": True, "message": "\n".join(battle_report)}

    def global_send_item(self, target_str: str, item_name: str, quantity: int) -> Dict:
        """
        统一的后台发放物品服务
        target_str: 'all', 'class:<职业名>', 'wxid:<wxid1>,<wxid2>'
        item_name: 物品名称 或 '金币'
        quantity: 数量
        """
        # 1. 解析目标用户
        user_ids = []
        target_type, target_value = target_str.split(':', 1) if ':' in target_str else (target_str, None)
        
        if target_type == 'all':
            user_ids = self.db.get_all_users()
            target_desc = "全服玩家"
        elif target_type == 'class':
            if not target_value or target_value not in class_config.CLASS_MAP:
                return {"success": False, "message": f"无效的职业名称: {target_value}"}
            class_key = class_config.CLASS_MAP[target_value]
            user_ids = self.db.get_user_ids_by_class(class_key)
            target_desc = f"职业为【{target_value}】的玩家"
        elif target_type == 'wxid':
            if not target_value:
                return {"success": False, "message": "未指定wxid。"}
            user_ids = [uid.strip() for uid in target_value.split(',') if uid.strip()]
            target_desc = f"{len(user_ids)}名指定玩家"
        else:
            return {"success": False, "message": f"无效的目标类型: {target_type}"}

        if not user_ids:
            return {"success": False, "message": "找不到任何符合条件的目标玩家。"}
            
        # 2. 处理发放逻辑
        if item_name == '金币':
            success_count = 0
            for uid in user_ids:
                repayment_result = self.process_income_repayment(uid, quantity)
                final_income = repayment_result['final_income']
                if self.db.update_user_coins(uid, final_income):
                    success_count += 1
            message = f"成功向 {target_desc} ({success_count}/{len(user_ids)}) 发放了 {quantity} {get_coins_name()}！（已自动处理还款）"
            # 发放金币
            # success_count = self.db.batch_add_coins_to_users(user_ids, quantity)
            # message = f"成功向 {target_desc} ({success_count}/{len(user_ids)}) 发放了 {quantity} {get_coins_name()}！"
        else:
            # 发放物品
            item_info = self.db.get_item_by_name(item_name)
            if not item_info:
                return {"success": False, "message": f"找不到名为【{item_name}】的物品。"}
            
            success_count = self.db.batch_add_item_to_users(user_ids, item_info, quantity)
            message = f"成功向 {target_desc} ({success_count}/{len(user_ids)}) 发放了【{item_name}】x {quantity}！"
            
        return {"success": True, "message": message}

    # service.py -> FishingService 类的内部

    def get_shop_info_message(self, user_id: str) -> str:
        """获取并格式化回廊商店的商品列表"""
        # --- 核心修复：从正确的数据源获取信息 ---
        # 1. 从 user_special_items 表获取用户拥有的镜像碎片数量
        shards = self.db.get_special_item_count(user_id, 'mirror_shards')

        # 2. 从 users 表获取用户的购买历史
        user_info = self.db.get_user_by_id(user_id)
        purchase_history_str = user_info.get('shop_purchase_history', '{}') if user_info else '{}'
        try:
            purchase_history = json.loads(purchase_history_str)
        except json.JSONDecodeError:
            purchase_history = {}
        # --- 修复结束 ---

        # 2. 构建消息字符串
        message = [f"📜 **回廊商店** (你的碎片: {shards}) 📜\n"]

        for item_id, item_info in pve_config.SHOP_ITEMS.items():
            limit_type = item_info.get('limit_type')
            limit_count = item_info.get('limit_count', 1)

            # a. 检查购买限制
            is_sold_out = False
            if limit_type:
                # 假设 limit_type 是 'daily' 或 'weekly'
                # (一个完整的实现需要根据日期判断周/日是否重置)
                times_bought = purchase_history.get(item_id, 0)
                if times_bought >= limit_count:
                    is_sold_out = True

            # b. 格式化商品行
            price_str = f"{item_info['cost']}碎片"
            limit_str = f" ({limit_type}限购: {limit_count})" if limit_type else ""

            line = f"`{item_id}`: **{item_info['name']}** - {price_str}{limit_str}"
            if is_sold_out:
                line += " [已售罄]"

            message.append(line)

        message.append("\n使用「/回廊购买 <编号> [数量]」来兑换。")
        return "\n".join(message)

    def purchase_from_shop(self, user_id: str, item_id_str: str, quantity: int = 1) -> Dict:
        """从回廊商店购买一件物品"""
        # 1. 验证商品ID
        item_info = pve_config.SHOP_ITEMS.get(item_id_str)
        if not item_info:
            return {"success": False, "message": "无效的商品编号。"}
        if quantity < 1:
            return {"success": False, "message": "购买数量必须大于0。"}

        # 2. 检查购买限制
        user_info = self.db.get_user_by_id(user_id)
        purchase_history_str = user_info.get('shop_purchase_history', '{}')
        try:
            purchase_history = json.loads(purchase_history_str)
        except json.JSONDecodeError:
            purchase_history = {}

        limit_type = item_info.get('limit_type')
        limit_count = item_info.get('limit_count', 1)
        if limit_type:
            times_bought = purchase_history.get(item_id_str, 0)
            if times_bought + quantity > limit_count:
                return {"success": False, "message": f"超出购买限制！该商品每{limit_type}只能购买{limit_count}次。"}

        # 3. 检查并扣除碎片
        total_cost = item_info['cost'] * quantity
        user_shards = user_info.get('mirror_shards', 0)
        if user_shards < total_cost:
            return {"success": False, "message": f"镜像碎片不足，需要{total_cost}，你只有{user_shards}。"}

        self.db.add_special_item(user_id, 'mirror_shards', -total_cost) # 扣除碎片

        # 4. 发放物品
        item_type = item_info['item_type']
        if item_type == 'bait':
            self.db.add_bait_to_inventory(user_id, self.db.get_fish_id_by_name(item_info['item_name']), item_info['quantity'] * quantity)
        elif item_type == 'special':
            self.db.add_special_item(user_id, item_info['item_key'], item_info['quantity'] * quantity)

        # 5. 更新购买历史
        purchase_history[item_id_str] = purchase_history.get(item_id_str, 0) + quantity
        self.db.update_user_shop_history(user_id, json.dumps(purchase_history)) # 需要在db.py中添加此方法

        return {"success": True, "message": f"成功兑换【{item_info['name']}】x {quantity}！"}

    # service.py -> FishingService 类的内部

    def get_my_items_message(self, user_id: str) -> str:
        """获取并格式化玩家的道具背包信息"""

        # 1. 从数据库获取所有特殊物品
        special_items = self.db.get_all_user_special_items(user_id)

        # 2. 为了方便，我们再单独获取一下镜像碎片数量，即使它也在上面列表里
        shards = self.db.get_special_item_count(user_id, 'mirror_shards')

        # 3. 定义一个映射，将 item_key 转换为玩家能看懂的中文名
        item_name_map = {
            'mirror_shards': '镜像碎片',
            'luck_charm': '强化幸运符',
            'rod_chest': '随机鱼竿宝箱',
            'accessory_chest': '随机饰品宝箱'
        }

        # 4. 构建消息字符串
        message = [f"🎒 **我的道具背包** 🎒\n"]

        # a. 单独显示核心货币
        message.append(f"碎片: {shards}\n")

        # b. 遍历并显示其他所有道具
        has_other_items = False
        for item in special_items:
            item_key = item['item_key']
            # 我们已经单独显示了碎片，所以这里跳过
            if item_key == 'mirror_shards':
                continue

            item_name = item_name_map.get(item_key, item_key) # 如果找不到中文名，就显示原始key
            quantity = item['quantity']
            message.append(f"- **{item_name}** x {quantity}")
            has_other_items = True

        if not has_other_items:
            message.append("你还没有其他特殊道具。")

        message.append("\n💡 使用「/打开宝箱 鱼竿/饰品」来开启装备宝箱。")
        message.append("💡 使用「/强化 使用幸运符」来消耗幸运符。")

        return "\n".join(message)

    # service.py -> FishingService 类的内部

    def process_income_repayment(self, user_id: str, income_amount: int) -> Dict:
        """
        核心还款处理器：在任何金币收益前调用此函数。
        返回: {'final_income': 最终应得金币, 'repayment_message': 还款消息}
        """
        loan_status = self.db.get_loan_status(user_id)
        if not loan_status or loan_status['loan_total'] == 0:
            return {'final_income': income_amount, 'repayment_message': ""}

        remaining_loan = loan_status['loan_total'] - loan_status['loan_repaid']
        if remaining_loan <= 0:
            return {'final_income': income_amount, 'repayment_message': ""}

        # 计算90%用于还款
        repayment = int(income_amount * 0.9)
        # 确保还款额不会超过剩余欠款
        repayment = min(repayment, remaining_loan)

        final_income = income_amount - repayment

        # 执行还款
        new_repaid_amount = self.db.make_repayment(user_id, repayment)
        repayment_message = f"（自动还款 -{repayment}{get_coins_name()}）"

        # 检查是否已还清
        if new_repaid_amount >= loan_status['loan_total']:
            self.db.clear_loan(user_id)
            repayment_message += "\n🎉 恭喜你，所有贷款已还清！"

        return {'final_income': final_income, 'repayment_message': repayment_message}

    def grant_loan_to_user(self, user_id: str, loanable_amount: int) -> Dict:
        """为指定用户发放贷款"""
        error = self._check_registered_or_return(user_id)
        if error: return error

        # 检查是否已有贷款
        loan_status = self.db.get_loan_status(user_id)
        if loan_status and loan_status['loan_total'] > 0:
            return {"success": False, "message": "该用户身上已有未还清的贷款。"}

        if loanable_amount <= 0:
            return {"success": False, "message": f"该用户的镜像碎片不足10个（当前{shards}个），不满足贷款资格。"}

        # 发放贷款
        self.db.grant_loan(user_id, loanable_amount)

        user_name = self.db.get_user_by_id(user_id)['nickname']
        return {"success": True, "message": f"成功向【{user_name}】发放贷款 {loanable_amount}{get_coins_name()}！"}

    def get_loan_status_message(self, user_id: str) -> str:
        """获取并格式化用户的贷款状态信息"""
        loan_status = self.db.get_loan_status(user_id)
        if not loan_status:
            message = "你当前没有任何贷款记录。"
            return message

        total = loan_status['loan_total']
        repaid = loan_status['loan_repaid']
        remaining = total - repaid
        progress = repaid / total if total > 0 else 1

        # 制作进度条
        progress_bar_length = 10
        filled_length = int(progress_bar_length * progress)
        bar = '▓' * filled_length + '░' * (progress_bar_length - filled_length)

        message = [
            f"🏦 **我的贷款详情** 🏦",
            f"贷款总额: {total}",
            f"已还款: {repaid}",
            f"剩余未还: {remaining}",
            f"还款进度: [{bar}] {progress:.1%}"
        ]
        return "\n".join(message)

    def initialize_all_user_loans(self) -> Dict:
        """
        [管理员操作] 遍历所有用户，根据其现有碎片，初始化其贷款状态。
        这是一个一次性操作。
        """
        self.LOG.info("开始执行存量用户贷款数据初始化任务...")

        # 1. 获取所有用户
        all_users = self.db.get_all_users()
        if not all_users:
            return {"success": True, "message": "没有找到任何用户，无需初始化。"}
        
        # 2. 准备批量更新的数据
        loan_update_list = []
        processed_users = 0
        
        for user_id in all_users:
            # a. 检查该用户是否已有贷款，如果有，则跳过，不覆盖
            #loan_status = self.db.get_loan_status(user_id)
            #if loan_status and loan_status.get('loan_total', 0) > 0:
            #    continue

            # b. 获取碎片数量并计算初始贷款额度
            shards = self.db.get_special_item_count(user_id, 'mirror_shards')
            credit_shards = shards - 9
            
            initial_loan_total = 0
            if credit_shards > 0:
                initial_loan_total = credit_shards * 50000 / 3
                
            # c. 将需要更新的用户数据加入列表
            # 我们只初始化贷款总额，已还款默认为0
            loan_update_list.append((initial_loan_total, 0, user_id))
            processed_users += 1

        if not loan_update_list:
            return {"success": True, "message": "所有用户都已有贷款记录或不满足条件，无需初始化。"}

        # 3. 调用数据库进行批量更新
        updated_count = self.db.batch_initialize_loans(loan_update_list)

        if updated_count >= 0:
            message = f"贷款数据初始化成功！\n共扫描 {len(all_users)} 名用户。\n处理了 {processed_users} 名无贷款记录的用户。\n成功为 {updated_count} 名用户更新了初始贷款额度。"
            return {"success": True, "message": message}
        else:
            return {"success": False, "message": "在执行数据库批量更新时发生错误，请查看后台日志。"}

    def buy_item_from_market(self, buyer_id: str, market_id: int) -> Dict:
        """
        【新版】完整的坊市购买业务逻辑。
        """
        # 1. 检查买家灵石是否足够（预检查）
        market_item_info = self.get_market_goods_by_id(market_id) # 假设db.py有这个方法
        if not market_item_info:
            return {'success': False, 'message': "坊市中没有这个编号的商品！"}

        price = market_item_info["price"]
        if self._get_user_stone(buyer_id) < price:
            return {'success': False, 'message': f"灵石不足！购买此物品需要 {price} 灵石。"}

        # 2. 调用DB层执行物品转移事务
        db_result = self.db.buy_item(buyer_id, market_id)

        if not db_result['success']:
            return db_result # 直接返回DB层的错误信息

        # 3. 如果物品转移成功，再执行货币操作
        trade = db_result['trade_details']
        seller_id = trade['seller_id']
        price = trade['price']

        # a. 扣除买家灵石
        self._update_user_stone(buyer_id, -price)

        # b. 计算并给卖家灵石 (有手续费)
        tax = int(price * 0.05)
        income = price - tax
        if seller_id != "0": # 0 代表系统，不给系统加钱
            self._update_user_stone(seller_id, income)

        message = (
            f"交易成功！你花费了 {price} 灵石。\n"
            f"卖家获得 {income} 灵石（手续费: {tax}）。"
        )
        return {"success": True, "message": message}

    def get_market_goods_by_id(self, market_id: int) -> Optional[Dict]:
        """辅助方法：通过市场ID获取商品信息"""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM market WHERE market_id = ?", (market_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def _get_user_stone(self, user_id: str) -> int:
        """【新】从修仙主服务获取灵石数量"""
        user_info = self.main_service.get_user_message(user_id)
        return user_info.stone if user_info else 0

    def _update_user_stone(self, user_id: str, amount: int):
        """【新】通过修仙主服务更新灵石数量"""
        mode = 1 if amount >= 0 else 2
        try:
            self.main_service.update_ls(user_id, abs(amount), mode)
            return True
        except Exception as e:
            logger.error(f"跨系统更新灵石失败 for {user_id}: {e}")
            return False
