# pk_skill_handler.py
"""
PK技能效果处理器 (完整实现版)
使用策略模式，将每个技能效果的实现封装成独立的函数。
"""
import random
from . import pk_config

# --- 辅助函数 ---
def log_and_apply(player, message, indent=1):
    player['simulator'].log(message, indent)

def check_trigger_chance(effect_params, player_states):
    """检查几率触发的技能"""
    chance = effect_params.get('chance', 1.0)
    aura_buff = player_states.get('aura_buff_chance', 0.0)
    final_chance = chance + aura_buff
    return random.random() < final_chance

# --- 光环(Aura)技能效果处理器 ---
class AuraHandlers:
    # --- 属性变更类 ---
    @staticmethod
    def debuff_all_stats(player, opponent, p_fish, o_fish, effect):
        debuff = effect['debuff_all_stats']
        for stat in o_fish['current_stats']:
            o_fish['current_stats'][stat] = int(o_fish['current_stats'][stat] * (1 - debuff))
        log_and_apply(player, f"对手 {o_fish['name']} 全属性降低{debuff:.0%}")

    @staticmethod
    def buff_self_weight(player, opponent, p_fish, o_fish, effect):
        buff = effect['buff_self_weight']
        p_fish['current_stats']['weight'] = int(p_fish['current_stats']['weight'] * buff)
        log_and_apply(player, f"自身重量提升至 {p_fish['current_stats']['weight']}")

    @staticmethod
    def buff_self_rarity(player, opponent, p_fish, o_fish, effect):
        p_fish['current_stats']['rarity'] += effect['buff_self_rarity']
        log_and_apply(player, f"自身稀有度临时 +{effect['buff_self_rarity']}")

    @staticmethod
    def ignore_opponent_value(player, opponent, p_fish, o_fish, effect):
        ignore_rate = effect['ignore_opponent_value']
        o_fish['current_stats']['value'] = int(o_fish['current_stats']['value'] * (1 - ignore_rate))
        log_and_apply(player, f"无视了对手 {o_fish['name']} {ignore_rate:.0%}的价值")

    @staticmethod
    def buff_team_weight(player, opponent, p_fish, o_fish, effect):
        buff = effect['buff_team_weight']
        for fish in player['lineup']:
            fish['base_value'] = int(fish['base_value'] * buff) # 注意: 永久提升本场基础值
        log_and_apply(player, f"我方所有鱼的重量基础值提升了{buff-1:.0%}")

    @staticmethod
    def buff_next_self_all(player, opponent, p_fish, o_fish, effect):
        sim = player['simulator']
        if sim.round < pk_config.PK_RULES['lineup_size']:
            next_fish = player['lineup'][sim.round]
            if 'turn_buffs' not in next_fish['states']: next_fish['states']['turn_buffs'] = []
            next_fish['states']['turn_buffs'].append({'type': 'all_stats', 'value': effect['buff_next_self_all']})
            log_and_apply(player, f"我方下一条鱼 {next_fish['name']} 将获得属性提升！")

    # --- 规则与状态变更类 ---
    @staticmethod
    def win_round(player, opponent, p_fish, o_fish, effect):
        player['simulator'].round_winner = player
        log_and_apply(player, "直接赢得了本回合！")

    @staticmethod
    def force_draw(player, opponent, p_fish, o_fish, effect):
        player['simulator'].force_draw = True
        log_and_apply(player, "本回合被强制判定为平局")

    @staticmethod
    def force_rule(player, opponent, p_fish, o_fish, effect):
        player['simulator'].forced_rule = effect['force_rule']
        log_and_apply(player, f"比拼规则被强制变为 **{effect['force_rule'].upper()}**！")

    @staticmethod
    def swap_next_opponent(player, opponent, p_fish, o_fish, effect):
        sim = player['simulator']
        if sim.round < pk_config.PK_RULES['lineup_size']:
            opponent['lineup'][sim.round], opponent['lineup'][sim.round-1] = opponent['lineup'][sim.round-1], opponent['lineup'][sim.round]
            log_and_apply(player, f"与对手下一条鱼交换了出战顺序！")

    @staticmethod
    def disable_opponent_ultimate(player, opponent, p_fish, o_fish, effect):
        o_fish['states']['ultimate_disabled'] = True
        log_and_apply(player, f"对手 {o_fish['name']} 本回合无法使用必杀技")

    @staticmethod
    def disable_all_ultimate(player, opponent, p_fish, o_fish, effect):
        p_fish['states']['ultimate_disabled'] = True
        o_fish['states']['ultimate_disabled'] = True
        log_and_apply(player, "本回合双方都无法使用必杀技")

    @staticmethod
    def add_energy_on_end(player, opponent, p_fish, o_fish, effect):
        # 核心修复：将效果附加到鱼的states，而不是player的states
        if 'end_of_round_effects' not in p_fish['states']:
            p_fish['states']['end_of_round_effects'] = []
        p_fish['states']['end_of_round_effects'].append({'type': 'add_energy', 'value': effect['add_energy_on_end']})
        # 日志记录可以保持不变，因为它只是文本
        log_and_apply(player, "将在回合结束时产生额外效果")

    @staticmethod
    def disable_opponent_aura(player, opponent, p_fish, o_fish, effect):
        o_fish['states']['aura_disabled'] = True
        log_and_apply(player, f"对手 {o_fish['name']} 的光环技能失效")

    @staticmethod
    def debuff_opponent_all_permanent(player, opponent, p_fish, o_fish, effect):
        debuff = effect['debuff_opponent_all_permanent']
        for fish in opponent['lineup']:
            if 'permanent_debuffs' not in fish['states']: fish['states']['permanent_debuffs'] = []
            fish['states']['permanent_debuffs'].append({'type': 'all_stats', 'value': debuff})
        log_and_apply(player, f"对手所有鱼的属性被永久降低了{debuff:.0%}")
        
    @staticmethod
    def add_energy(player, opponent, p_fish, o_fish, effect):
        player['energy'] += effect['add_energy']
        log_and_apply(player, f"回复了 {effect['add_energy']} 点能量！")

    # --- 抗性类 ---
    @staticmethod
    def resist_swap(player, opponent, p_fish, o_fish, effect):
        p_fish['states']['resist_swap'] = True
    
    @staticmethod
    def resist_debuff(player, opponent, p_fish, o_fish, effect):
        p_fish['states']['resist_debuff'] = True

    @staticmethod
    def resist_instant_win_lose(player, opponent, p_fish, o_fish, effect):
        p_fish['states']['resist_instant_win_lose'] = True
        
    @staticmethod
    def resist_spy(player, opponent, p_fish, o_fish, effect):
        player['states']['resist_spy'] = True

    @staticmethod
    def buff_team_all(player, opponent, p_fish, o_fish, effect):
        buff = effect['buff_team_all']
        for fish in player['lineup']:
            if 'permanent_buffs' not in fish['states']: fish['states']['permanent_buffs'] = []
            fish['states']['permanent_buffs'].append({'type': 'all_stats', 'value': buff})
        log_and_apply(player, f"我方所有鱼的属性获得了{buff-1:.0%}的永久加成！")

    @staticmethod
    def debuff_next_opponent_all_permanent(player, opponent, p_fish, o_fish, effect):
        debuff = effect['debuff_next_opponent_all_permanent']
        sim = player['simulator']
        if sim.round < pk_config.PK_RULES['lineup_size']:
            next_o_fish = opponent['lineup'][sim.round]
            if 'permanent_debuffs' not in next_o_fish['states']: next_o_fish['states']['permanent_debuffs'] = []
            next_o_fish['states']['permanent_debuffs'].append({'type': 'all_stats', 'value': debuff})
            log_and_apply(player, f"对手下一条鱼 {next_o_fish['name']} 将被永久降低{debuff:.0%}的属性")

    @staticmethod
    def dodge_aura(player, opponent, p_fish, o_fish, effect):
        p_fish['states']['dodge_aura'] = True
        log_and_apply(player, f"获得了闪避对手光环的能力！")

# --- 必杀技(Ultimate)技能效果处理器 ---
class UltimateHandlers:
    @staticmethod
    def force_rule(player, opponent, p_fish, o_fish, effect):
        new_rule = effect['force_rule']
        player['simulator'].forced_rule = new_rule
        log_and_apply(player, f"比拼规则被强制变为 **{new_rule.upper()}**！", 2)

    @staticmethod
    def buff_self_value(player, opponent, p_fish, o_fish, effect):
        buff = effect['buff_self_value']
        p_fish['current_stats']['value'] = int(p_fish['current_stats']['value'] * buff)
        log_and_apply(player, f"自身价值提升至 {p_fish['current_stats']['value']}", 2)

    @staticmethod
    def buff_self_rarity(player, opponent, p_fish, o_fish, effect):
        buff = effect['buff_self_rarity']
        p_fish['current_stats']['rarity'] += buff
        log_and_apply(player, f"自身稀有度临时提升 {buff}点", 2)
        
    @staticmethod
    def debuff_resistance(player, opponent, p_fish, o_fish, effect):
        if 'turn_buffs' not in p_fish['states']: p_fish['states']['turn_buffs'] = []
        p_fish['states']['turn_buffs'].append({'type': 'debuff_resistance', 'value': effect['debuff_resistance']})
        log_and_apply(player, "获得了50%的负面效果抗性", 2)

    @staticmethod
    def force_draw_round(player, opponent, p_fish, o_fish, effect):
        player['simulator'].force_draw = True
        log_and_apply(player, "本回合被强制判定为平局", 2)
        if 'debuff_next_opponent_weight' in effect:
            sim = player['simulator']
            if sim.round < pk_config.PK_RULES['lineup_size']:
                next_o_fish = opponent['lineup'][sim.round]
                if 'turn_debuffs' not in next_o_fish['states']: next_o_fish['states']['turn_debuffs'] = []
                next_o_fish['states']['turn_debuffs'].append({'type': 'weight_debuff_rate', 'value': effect['debuff_next_opponent_weight']})
                log_and_apply(player, f"对手下一条鱼 {next_o_fish['name']} 的重量将降低50%", 2)

    @staticmethod
    def buff_all_stats_per_energy(player, opponent, p_fish, o_fish, effect):
        energy_spent = player['energy_spent_on_ultimate']
        buff_rate = effect['buff_all_stats_per_energy'] * energy_spent
        for stat in p_fish['current_stats']:
            p_fish['current_stats'][stat] = int(p_fish['current_stats'][stat] * (1 + buff_rate))
        log_and_apply(player, f"全属性提升了{buff_rate:.0%}", 2)

    @staticmethod
    def lose_round_for_energy(player, opponent, p_fish, o_fish, effect):
        player['energy'] += effect['lose_round_for_energy']
        player['simulator'].round_winner = opponent
        log_and_apply(player, f"放弃了本回合，回复了 {effect['lose_round_for_energy']} 点能量", 2)
        
    @staticmethod
    def add_energy(player, opponent, p_fish, o_fish, effect):
        player['energy'] += effect['add_energy']
        log_and_apply(player, f"回复了 {effect['add_energy']}点能量", 2)
        
    @staticmethod
    def reroll_round(player, opponent, p_fish, o_fish, effect):
        duel_id = player['id'] + p_fish['name']
        if player['simulator'].duel_states.get(f'reroll_used_{duel_id}', False):
            log_and_apply(player, "但逆天改命已经使用过了...", 2)
            return
        player['simulator'].reroll_this_round = True
        player['simulator'].duel_states[f'reroll_used_{duel_id}'] = True
        log_and_apply(player, "时光倒流，本回合将重赛！", 2)

    @staticmethod
    def disable_next_opponent_aura(player, opponent, p_fish, o_fish, effect):
        sim = player['simulator']
        if sim.round < pk_config.PK_RULES['lineup_size']:
            next_o_fish = opponent['lineup'][sim.round]
            next_o_fish['states']['aura_disabled'] = True
            log_and_apply(player, f"对手下一条鱼 {next_o_fish['name']} 的光环将被无效化", 2)

    @staticmethod
    def win_round(player, opponent, p_fish, o_fish, effect):
        player['simulator'].round_winner = player
        log_and_apply(player, "直接赢得了本回合！", 2)

    @staticmethod
    def debuff_next_opponent_weight(player, opponent, p_fish, o_fish, effect):
        debuff = effect['debuff_next_opponent_weight']
        sim = player['simulator']
        if sim.round < pk_config.PK_RULES['lineup_size']:
            next_o_fish = opponent['lineup'][sim.round]
            if 'turn_debuffs' not in next_o_fish['states']: next_o_fish['states']['turn_debuffs'] = []
            next_o_fish['states']['turn_debuffs'].append({'type': 'weight_debuff_rate', 'value': debuff})
            log_and_apply(player, f"对手下一条鱼 {next_o_fish['name']} 的重量将降低{debuff:.0%}", 2)

    @staticmethod
    def debuff_next_opponent_rarity(player, opponent, p_fish, o_fish, effect):
        debuff = effect['debuff_next_opponent_rarity']
        sim = player['simulator']
        if sim.round < pk_config.PK_RULES['lineup_size']:
            next_o_fish = opponent['lineup'][sim.round]
            if 'turn_debuffs' not in next_o_fish['states']: next_o_fish['states']['turn_debuffs'] = []
            next_o_fish['states']['turn_debuffs'].append({'type': 'rarity_debuff_flat', 'value': debuff})
            log_and_apply(player, f"对手下一条鱼 {next_o_fish['name']} 的稀有度将降低{-debuff}", 2)

    @staticmethod
    def copy_opponent_stats(player, opponent, p_fish, o_fish, effect):
        stats_to_copy = effect['copy_opponent_stats']
        for stat in stats_to_copy:
            p_fish['current_stats'][stat] = o_fish['current_stats'][stat]
        log_and_apply(player, f"复制了对手的{', '.join(stats_to_copy)}属性！", 2)

    @staticmethod
    def disable_next_opponent_ultimate_chance(player, opponent, p_fish, o_fish, effect):
        chance = effect['disable_next_opponent_ultimate_chance']
        sim = player['simulator']
        if sim.round < pk_config.PK_RULES['lineup_size']:
            next_o_fish = opponent['lineup'][sim.round]
            if 'turn_debuffs' not in next_o_fish['states']: next_o_fish['states']['turn_debuffs'] = []
            next_o_fish['states']['turn_debuffs'].append({'type': 'disable_ultimate_chance', 'value': chance})
            log_and_apply(player, f"对手下一条鱼 {next_o_fish['name']} 将有{chance:.0%}几率无法使用必杀技", 2)

    @staticmethod
    def steal_energy(player, opponent, p_fish, o_fish, effect):
        if opponent['energy'] > 0:
            opponent['energy'] -= 1
            player['energy'] += 1
            log_and_apply(player, "从对手处偷取了1点能量", 2)

    @staticmethod
    def increase_next_opponent_ultimate_cost(player, opponent, p_fish, o_fish, effect):
        cost_increase = effect['increase_next_opponent_ultimate_cost']
        sim = player['simulator']
        if sim.round < pk_config.PK_RULES['lineup_size']:
            next_o_fish = opponent['lineup'][sim.round]
            if 'turn_debuffs' not in next_o_fish['states']: next_o_fish['states']['turn_debuffs'] = []
            next_o_fish['states']['turn_debuffs'].append({'type': 'increase_ultimate_cost', 'value': cost_increase})
            log_and_apply(player, f"对手下一条鱼 {next_o_fish['name']} 的必杀技消耗将增加{cost_increase}点", 2)

    @staticmethod
    def disable_opponent_ultimate_for_rounds(player, opponent, p_fish, o_fish, effect):
        duration = effect['disable_opponent_ultimate_for_rounds']
        for i in range(player['simulator'].round - 1, min(player['simulator'].round - 1 + duration, pk_config.PK_RULES['lineup_size'])):
            opponent['lineup'][i]['states']['ultimate_disabled'] = True
        log_and_apply(player, f"对手在接下来的{duration}回合内无法使用必杀技", 2)

    @staticmethod
    def debuff_random_opponent_fish_stat_per_energy(player, opponent, p_fish, o_fish, effect):
        energy_spent = player['energy_spent_on_ultimate']
        debuff_rate = effect['debuff_random_opponent_fish_stat_per_energy']
        for _ in range(energy_spent):
            if opponent['lineup']:
                target_fish = random.choice(opponent['lineup'])
                target_stat = random.choice(['weight', 'value'])
                if 'permanent_debuffs' not in target_fish['states']: target_fish['states']['permanent_debuffs'] = []
                target_fish['states']['permanent_debuffs'].append({'type': f'{target_stat}_debuff_rate', 'value': debuff_rate})
                log_and_apply(player, f"对手的 {target_fish['name']} 的{target_stat}被永久降低了{debuff_rate:.0%}", 2)

    @staticmethod
    def win_duel(player, opponent, p_fish, o_fish, effect):
        player['simulator'].battle_winner = player
        log_and_apply(player, "直接赢得了整场决斗的胜利！", 2)

    @staticmethod
    def buff_future_weight_per_energy(player, opponent, p_fish, o_fish, effect):
        energy_spent = player['energy_spent_on_ultimate']
        buff_amount = effect['buff_future_weight_per_energy'] * energy_spent
        if 'permanent_buffs' not in player['states']: player['states']['permanent_buffs'] = []
        player['states']['permanent_buffs'].append({'type': 'weight_buff_flat', 'value': buff_amount})
        log_and_apply(player, f"我方所有鱼在比拼重量时将获得 {buff_amount}g 的加成", 2)

    @staticmethod
    def swap_random_stat_and_compare(player, opponent, p_fish, o_fish, effect):
        stat_to_swap = random.choice(['rarity', 'weight', 'value'])
        p_val = p_fish['current_stats'][stat_to_swap]
        o_val = o_fish['current_stats'][stat_to_swap]
        p_fish['current_stats'][stat_to_swap] = o_val
        o_fish['current_stats'][stat_to_swap] = p_val
        log_and_apply(player, f"与对手交换了 **{stat_to_swap.upper()}** 属性！", 2)

    @staticmethod
    def steal_or_debuff(player, opponent, p_fish, o_fish, effect):
        if opponent['energy'] > 0:
            opponent['energy'] -= 1
            player['energy'] += 1
            log_and_apply(player, "从对手处偷取了1点能量", 2)
        else:
            sim = player['simulator']
            if sim.round < pk_config.PK_RULES['lineup_size']:
                next_o_fish = opponent['lineup'][sim.round]
                if 'turn_debuffs' not in next_o_fish['states']: next_o_fish['states']['turn_debuffs'] = []
                next_o_fish['states']['turn_debuffs'].append({'type': 'all_stats', 'value': 0.2})
                log_and_apply(player, f"对手没有能量，使其下一条鱼 {next_o_fish['name']} 属性降低20%", 2)

    @staticmethod
    def special_win_condition(player, opponent, p_fish, o_fish, effect):
        duel_id = player['id'] + p_fish['name']
        if player['simulator'].duel_states.get(f'special_win_used_{duel_id}', False):
            log_and_apply(player, "但神之裁决已经使用过了...", 2)
            return
        player['simulator'].special_win_condition_triggered = player
        player['simulator'].duel_states[f'special_win_used_{duel_id}'] = True
        log_and_apply(player, "高举三叉戟，发动了神之裁决！", 2)


# 效果名称 -> 处理函数 的映射字典 (完整版)
AURA_EFFECT_MAP = {
    'debuff_all_stats': AuraHandlers.debuff_all_stats,
    'win_round': AuraHandlers.win_round,
    'force_draw': AuraHandlers.force_draw,
    'buff_self_weight': AuraHandlers.buff_self_weight,
    'buff_self_rarity': AuraHandlers.buff_self_rarity,
    'ignore_opponent_value': AuraHandlers.ignore_opponent_value,
    'buff_team_weight': AuraHandlers.buff_team_weight,
    'buff_next_self_all': AuraHandlers.buff_next_self_all,
    'swap_next_opponent': AuraHandlers.swap_next_opponent,
    'disable_opponent_ultimate': AuraHandlers.disable_opponent_ultimate,
    'disable_all_ultimate': AuraHandlers.disable_all_ultimate,
    'add_energy_on_end': AuraHandlers.add_energy_on_end,
    'disable_opponent_aura': AuraHandlers.disable_opponent_aura,
    'debuff_opponent_all_permanent': AuraHandlers.debuff_opponent_all_permanent,
    'add_energy': AuraHandlers.add_energy,
    'resist_swap': AuraHandlers.resist_swap,
    'resist_debuff': AuraHandlers.resist_debuff,
    'resist_instant_win_lose': AuraHandlers.resist_instant_win_lose,
    'resist_spy': AuraHandlers.resist_spy,
    'buff_team_all': AuraHandlers.buff_team_all,
    'debuff_next_opponent_all_permanent': AuraHandlers.debuff_next_opponent_all_permanent,
    'dodge_aura': AuraHandlers.dodge_aura,
}


ULTIMATE_EFFECT_MAP = {
    'force_rule': UltimateHandlers.force_rule,
    'buff_self_value': UltimateHandlers.buff_self_value,
    'buff_self_rarity': UltimateHandlers.buff_self_rarity,
    'debuff_resistance': UltimateHandlers.debuff_resistance,
    'force_draw_round': UltimateHandlers.force_draw_round,
    'buff_all_stats_per_energy': UltimateHandlers.buff_all_stats_per_energy,
    'lose_round_for_energy': UltimateHandlers.lose_round_for_energy,
    'add_energy': UltimateHandlers.add_energy,
    'reroll_round': UltimateHandlers.reroll_round,
    'disable_next_opponent_aura': UltimateHandlers.disable_next_opponent_aura,
    'win_round': UltimateHandlers.win_round,
    'debuff_next_opponent_weight': UltimateHandlers.debuff_next_opponent_weight,
    'debuff_next_opponent_rarity': UltimateHandlers.debuff_next_opponent_rarity,
    'copy_opponent_stats': UltimateHandlers.copy_opponent_stats,
    'disable_next_opponent_ultimate_chance': UltimateHandlers.disable_next_opponent_ultimate_chance,
    'steal_energy': UltimateHandlers.steal_energy,
    'increase_next_opponent_ultimate_cost': UltimateHandlers.increase_next_opponent_ultimate_cost,
    'disable_opponent_ultimate_for_rounds': UltimateHandlers.disable_opponent_ultimate_for_rounds,
    'debuff_random_opponent_fish_stat_per_energy': UltimateHandlers.debuff_random_opponent_fish_stat_per_energy,
    'win_duel': UltimateHandlers.win_duel,
    'buff_future_weight_per_energy': UltimateHandlers.buff_future_weight_per_energy,
    'swap_random_stat_and_compare': UltimateHandlers.swap_random_stat_and_compare,
    'steal_or_debuff': UltimateHandlers.steal_or_debuff,
    'special_win_condition': UltimateHandlers.special_win_condition,
}
