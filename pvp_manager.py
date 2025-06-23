import random
from astrbot.api import logger

#from .service import XiuxianService
from .item_manager import Items
from .config import USERRANK, SKILL_RANK_VALUE, MP_COST_REDUCTION_MAP

class PvPManager:
    """处理玩家之间战斗的核心逻辑"""

    @staticmethod
    def _calculate_damage(attacker_atk: int, defender_defense_rate: float,
                          attacker_crit_rate: float, attacker_crit_damage: float) -> tuple[int, bool]:
        """
        计算单次攻击的最终伤害。
        :return: (伤害值, 是否暴击)
        """
        base_damage = attacker_atk
        is_crit = False

        # 攻击浮动 (例如 +/- 10%)
        damage_float_rate = random.uniform(0.9, 1.1)
        base_damage = int(base_damage * damage_float_rate)

        # 计算暴击
        if random.random() < attacker_crit_rate:
            is_crit = True
            # 暴击伤害 = 基础伤害 * (1 + 暴击伤害加成)
            # 例如，基础暴击伤害是150%，则 attacker_crit_damage 是 0.5
            base_damage = int(base_damage * (1 + attacker_crit_damage + 0.5))

        # 计算减伤
        # 最终伤害 = 基础伤害 * (1 - 减伤率)
        final_damage = int(base_damage * (1 - defender_defense_rate))

        return max(1, final_damage), is_crit # 至少造成1点伤害

    @staticmethod
    def simulate_player_vs_player_fight(p1_info_dict: dict, p2_info_dict: dict, max_rounds: int = 30) -> dict:
        items_manager = Items()

        p1_state = PlayerBattleInternalState(p1_info_dict, items_manager)
        p2_state = PlayerBattleInternalState(p2_info_dict, items_manager)

        battle_log = [
            f"⚔️ 一场惊心动魄的对决在【{p1_state.user_name}】与【{p2_state.user_name}】之间展开！",
            f"【{p1_state.user_name}】:\n ❤️{p1_state.hp}/{p1_state.base_hp}\n 💙{p1_state.mp}/{p1_state.base_mp}\n ⚔️{p1_state.base_atk}", # 显示基础攻击
            f"【{p2_state.user_name}】:\n ❤️{p2_state.hp}/{p2_state.base_hp}\n 💙{p2_state.mp}/{p2_state.base_mp}\n ⚔️{p2_state.base_atk}",
            "----------------------------------"
        ]
        battle_round_details_log = []

        turn_p1 = p1_state.power >= p2_state.power # 假设 power 是一个初始战斗力用于决定先手

        for round_num in range(1, max_rounds + 1):
            battle_round_details_log.append(f"ዙ 回合 {round_num} ዙ")

            p1_state.tick_cooldowns_and_effects()
            p2_state.tick_cooldowns_and_effects()

            # 应用DoT伤害 (双方)
            for player_s_dot in [p1_state, p2_state]:
                dot_damage_this_round = 0
                active_dots_after_tick = []
                for dot_effect in player_s_dot.active_dot_effects:
                    dot_damage_this_round += dot_effect['damage_per_turn']
                    # 效果在 tick_cooldowns_and_effects 中减少回合，这里只结算伤害
                if dot_damage_this_round > 0:
                    player_s_dot.hp -= dot_damage_this_round
                    battle_round_details_log.append(f"🩸【{player_s_dot.user_name}】受到持续伤害效果，损失了 {dot_damage_this_round} 点气血。剩余HP: {max(0, player_s_dot.hp)}")
                    if player_s_dot.hp <= 0: break
                if player_s_dot.hp <= 0: break 
            if p1_state.hp <= 0 or p2_state.hp <= 0: break # 一方因DoT死亡

            # --- 轮流行动 ---
            if turn_p1:
                attacker, defender = p1_state, p2_state
            else:
                attacker, defender = p2_state, p1_state
            
            battle_round_details_log.append(f"轮到【{attacker.user_name}】行动...")
            
            if attacker.is_sealed > 0:
                battle_round_details_log.append(f"【{attacker.user_name}】被封印了，本回合无法行动！(剩余 {attacker.is_sealed} 回合)")
            else:
                # === 玩家行动决策：使用神通还是普攻 ===
                used_skill_this_turn = False
                if attacker.can_use_skill():
                    skill_cast_rate = attacker.active_skill_data.get('rate', 100) / 100.0
                    if random.random() <= skill_cast_rate:
                        used_skill_this_turn = True
                        skill_data = attacker.active_skill_data
                        battle_round_details_log.append(f"✨【{attacker.user_name}】准备施展神通【{skill_data['name']}】！")

                        hp_cost = attacker.apply_hp_cost_for_skill()
                        mp_cost = attacker.apply_mp_cost_for_skill()
                        cost_log_parts = []
                        if hp_cost > 0: cost_log_parts.append(f"消耗气血 {hp_cost}")
                        if mp_cost > 0: cost_log_parts.append(f"消耗真元 {mp_cost}")
                        if cost_log_parts: battle_round_details_log.append(f"({', '.join(cost_log_parts)})")
                        
                        # 按照您的要求，turncost 既是持续也是冷却
                        attacker.skill_cooldown = skill_data.get('turncost', 0)  + 1
                        
                        skill_type = skill_data.get('skill_type')

                        if skill_type == 1: #直接伤害/多段伤害
                            total_skill_damage = 0
                            for hit_multiplier in skill_data.get('atkvalue', [1.0]):
                                damage_this_hit, was_crit_skill = PvPManager._calculate_damage(
                                    int(attacker.get_current_atk() * hit_multiplier), # 使用当前计算的攻击力
                                    defender.get_current_defense_rate(),
                                    attacker.get_current_crit_rate(),
                                    attacker.get_current_crit_damage()
                                )
                                crit_text_skill = "✨暴击！" if was_crit_skill else ""
                                battle_round_details_log.append(f"  💥 神通造成 {damage_this_hit} 点伤害！{crit_text_skill}")
                                defender.hp -= damage_this_hit
                                total_skill_damage += damage_this_hit
                            battle_round_details_log.append(f"  总计对【{defender.user_name}】造成 {total_skill_damage} 点神通伤害！")

                        elif skill_type == 2: # 持续性伤害 (DoT)
                            dot_damage_multiplier = skill_data.get('atkvalue', 0.0)
                            dot_duration = skill_data.get('turncost', 0)
                            damage_per_turn = int(attacker.get_current_atk() * dot_damage_multiplier)
                            if damage_per_turn > 0 and dot_duration > 0:
                                defender.add_dot_effect(skill_data['name'], damage_per_turn, dot_duration, attacker.user_id)
                                battle_round_details_log.append(f"  【{defender.user_name}】受到了【{skill_data['name']}】效果，将在接下来 {dot_duration} 回合持续受到伤害！")
                                used_skill_this_turn = False
                        
                        elif skill_type == 3: # Buff/Debuff
                            target_is_opponent = skill_data.get('target_opponent', False) # 新增字段判断目标
                            target_player_state = defender if target_is_opponent else attacker
                            
                            buff_type_from_skill_json = skill_data.get('bufftype') # 原版是字符串 "1", "2"
                            buff_value = skill_data.get('buffvalue', 0.0) # 这个值本身就是小数倍率
                            buff_duration = skill_data.get('turncost', 0)
                            
                            buff_applied_type_internal = None # 用于 active_buff_effects 的type
                            buff_desc_for_log = ""
                            is_debuff_flag = target_is_opponent # 简单认为给对方上的就是debuff

                            if buff_type_from_skill_json == 1 or buff_type_from_skill_json == "1": # 攻击力
                                buff_applied_type_internal = "atk_rate"
                                buff_desc_for_log = f"攻击力变化 {buff_value*100:+.0f}%" # +号显示正负
                            elif buff_type_from_skill_json == 2 or buff_type_from_skill_json == "2": # 减伤率 (对应防御率)
                                buff_applied_type_internal = "def_rate"
                                buff_desc_for_log = f"减伤率变化 {buff_value*100:+.0f}%"
                            # --- 补充其他 bufftype ---
                            elif buff_type_from_skill_json == "crit_rate_add": # 假设神通数据中这样定义
                                buff_applied_type_internal = "crit_rate_add"
                                buff_desc_for_log = f"暴击率变化 {buff_value*100:+.1f}%"
                            elif buff_type_from_skill_json == "crit_dmg_add":
                                buff_applied_type_internal = "crit_dmg_add"
                                buff_desc_for_log = f"暴击伤害变化 {buff_value*100:+.1f}%"
                            # ...可以继续添加其他类型的buff...
                            else:
                                battle_round_details_log.append(f"  【{skill_data['name']}】具有未知的bufftype: {buff_type_from_skill_json}")

                            if buff_applied_type_internal and buff_duration > 0:
                                target_player_state.add_buff_effect(
                                    skill_data['name'], buff_applied_type_internal,
                                    buff_value, buff_duration, attacker.user_id, is_debuff_flag
                                )
                                battle_round_details_log.append(f"  【{target_player_state.user_name}】受【{skill_data['name']}】影响，{buff_desc_for_log}，持续 {buff_duration} 回合！")
                            used_skill_this_turn = False

                        elif skill_type == 4: # 封印
                            seal_success_rate = skill_data.get('success', 100) / 100.0
                            seal_duration = skill_data.get('turncost', 0)
                            if random.random() <= seal_success_rate:
                                defender.is_sealed = max(defender.is_sealed, seal_duration)
                                battle_round_details_log.append(f"  【{defender.user_name}】被【{skill_data['name']}】封印了神通，持续 {seal_duration} 回合！")
                            else:
                                battle_round_details_log.append(f"  【{skill_data['name']}】对【{defender.user_name}】的封印失败了！")
                        
                    else: # 神通发动失败 (概率)
                        battle_round_details_log.append(f"【{attacker.user_name}】施展神通【{attacker.active_skill_data['name']}】失败了！")
                        used_skill_this_turn = False 
                
                # === 如果没有使用技能，或者技能判定失败，则进行普通攻击 ===
                if not used_skill_this_turn:
                    battle_round_details_log.append(f"【{attacker.user_name}】选择了普通攻击...")
                    damage_dealt, was_crit = PvPManager._calculate_damage(
                        attacker.get_current_atk(), # 使用动态计算的攻击力
                        defender.get_current_defense_rate(), # 使用动态计算的防御率
                        attacker.get_current_crit_rate(),
                        attacker.get_current_crit_damage()
                    )
                    crit_text = "✨暴击！" if was_crit else ""
                    battle_round_details_log.append(
                        f"💥【{attacker.user_name}】的普通攻击，{crit_text}对【{defender.user_name}】造成了 {damage_dealt} 点伤害！"
                    )
                    defender.hp -= damage_dealt
            
            battle_round_details_log.append(f"🩸【{defender.user_name}】剩余气血: {max(0, defender.hp)}")

            # --- 攻击后辅修功法效果 (如吸血) ---
            attacker_buff_info_obj = attacker.buff_info
            if attacker_buff_info_obj and getattr(attacker_buff_info_obj, 'sub_buff', 0) != 0:
                sub_buff_data_attacker = items_manager.get_data_by_item_id(attacker_buff_info_obj.sub_buff)
                if sub_buff_data_attacker and sub_buff_data_attacker.get("buff_type") == "6": # 吸血
                    leech_percent = float(sub_buff_data_attacker.get("buff", "0")) / 100.0
                    # 吸血量基于实际造成的伤害 (需要确定是神通伤害还是普攻伤害，或两者都有)
                    # 简单起见，我们假设它作用于本回合造成的所有直接伤害
                    # 如果 used_skill_this_turn 且 skill_type == 1, 伤害是 total_skill_damage
                    # 否则是 damage_dealt (如果是普攻)
                    damage_source_for_leech = 0
                    if used_skill_this_turn and skill_type == 1:
                         damage_source_for_leech = total_skill_damage # total_skill_damage 在上面 skill_type 1 处定义
                    elif not used_skill_this_turn:
                         damage_source_for_leech = damage_dealt # damage_dealt 在上面普攻处定义
                    
                    leech_amount = int(damage_source_for_leech * leech_percent)
                    if leech_amount > 0:
                        original_attacker_hp = attacker.hp
                        attacker.hp = min(attacker.base_hp, attacker.hp + leech_amount) # 注意这里用 base_hp 作为上限
                        healed_by_leech = attacker.hp - original_attacker_hp
                        if healed_by_leech > 0:
                           battle_round_details_log.append(f"🩸【{sub_buff_data_attacker['name']}】效果发动，{attacker.user_name} 吸取了 {healed_by_leech} 点气血！")

            # 检查防御方是否阵亡
            if defender.hp <= 0:
                battle_log.append(f"战斗共计【{round_num}】回合👑【{attacker.user_name}】击败了【{defender.user_name}】，获得了胜利！")
                battle_log.append(f"回合结束状态：【{p1_state.user_name}】HP:{max(0, p1_state.hp)} MP:{max(0, p1_state.mp)} | 【{p2_state.user_name}】HP:{max(0, p2_state.hp)} MP:{max(0, p2_state.mp)}")
                # 更新最终状态，以便返回
                p1_state.hp = max(0, p1_state.hp)
                p2_state.hp = max(0, p2_state.hp)
                return {
                    "winner": attacker.user_id, "loser": defender.user_id,
                    "log": battle_log,
                    "p1_hp_final": p1_state.hp, "p2_hp_final": p2_state.hp,
                    "p1_mp_final": p1_state.mp, "p2_mp_final": p2_state.mp,
                    "battle_round_details_log": battle_round_details_log
                }
            
            # 如果是p1行动完，轮到p2；如果是p2行动完，则回合结束，下一轮还是p1先手判断
            if turn_p1 and p2_state.hp > 0 : # 如果是P1攻击完了，且P2没死，则轮到P2
                turn_p1 = False # 下次该 P2 行动 (在这个大回合内)
                # 为了代码结构简单，我们不在一个循环里做两次完整的行动逻辑，
                # 而是依赖外层 for round_num 循环和 turn_p1 的交替
            elif not turn_p1 and p1_state.hp > 0 : # 如果是P2攻击完了，且P1没死
                turn_p1 = True # 下一轮该 P1 先手判断
            # 如果一方死亡，则上面已经 return

            # --- 大回合结束，结算双方的辅修功法（如回血回蓝） ---
            # 注意：这里应该在双方都行动完毕后，或者至少在回合数增加前
            # 当前逻辑是每个玩家行动后，会有一个turn_p1切换，所以下一个循环开始时attacker/defender会变
            # 我们需要确保双方的回合结束效果都被触发
            
            if not turn_p1: # 刚刚是P1攻击，现在轮到P2，所以是P1的回合结束
                effects_log_attacker = PvPManager._apply_end_of_round_sub_buff_effects(attacker, items_manager) # attacker此时是p1_state
                if effects_log_attacker: battle_round_details_log.extend(effects_log_attacker)
            else: # 刚刚是P2攻击，现在轮到P1，所以是P2的回合结束
                effects_log_defender = PvPManager._apply_end_of_round_sub_buff_effects(attacker, items_manager) # attacker此时是p2_state
                if effects_log_defender: battle_round_details_log.extend(effects_log_defender)
            # (上面的逻辑有些绕，改为在回合末尾统一结算双方)

        # === 循环结束后 ===
        
        # 大回合真正结束，结算双方的辅修功法被动回复效果
        #effects_log_p1 = PvPManager._apply_end_of_round_sub_buff_effects(p1_state, items_manager)
        #if effects_log_p1: battle_log.extend(effects_log_p1)
        #
        #effects_log_p2 = PvPManager._apply_end_of_round_sub_buff_effects(p2_state, items_manager)
        #if effects_log_p2: battle_log.extend(effects_log_p2)

        battle_log.append(f"战斗共计【{round_num}】回合, 回合结束状态：【{p1_state.user_name}】HP:{max(0, p1_state.hp)} MP:{max(0, p1_state.mp)} | 【{p2_state.user_name}】HP:{max(0, p2_state.hp)} MP:{max(0, p2_state.mp)}")
        
        # 如果循环是因为一方死亡而break，这里不会执行
        if p1_state.hp <= 0 and p2_state.hp <= 0 : # 同时死亡或DoT致死
            battle_log.append("----------------------------------")
            battle_log.append("⚔️ 双方激战力竭，同归于尽！")
            winner_id, loser_id = None, None
        elif p1_state.hp <= 0:
             battle_log.append("----------------------------------")
             battle_log.append(f"👑【{p2_state.user_name}】击败了【{p1_state.user_name}】，获得了胜利！")
             winner_id, loser_id = p2_state.user_id, p1_state.user_id
        elif p2_state.hp <= 0:
             battle_log.append("----------------------------------")
             battle_log.append(f"👑【{p1_state.user_name}】击败了【{p2_state.user_name}】，获得了胜利！")
             winner_id, loser_id = p1_state.user_id, p2_state.user_id
        else: # 达到最大回合数
            battle_log.append("----------------------------------")
            battle_log.append("⌛ 对决已达最大回合数，按剩余气血判定胜负！")
            if p1_state.hp > p2_state.hp:
                winner_id, loser_id = p1_state.user_id, p2_state.user_id
                battle_log.append(f"👑【{p1_state.user_name}】凭借微弱优势获胜！")
            elif p2_state.hp > p1_state.hp:
                winner_id, loser_id = p2_state.user_id, p1_state.user_id
                battle_log.append(f"👑【{p2_state.user_name}】凭借微弱优势获胜！")
            else:
                winner_id, loser_id = None, None
                battle_log.append("平分秋色！")


        return {
            "winner": winner_id, "loser": loser_id, "log": battle_log,
            "p1_hp_final": max(0,p1_state.hp), "p2_hp_final": max(0,p2_state.hp),
            "p1_mp_final": p1_state.mp, "p2_mp_final": p2_state.mp,
            "battle_round_details_log": battle_round_details_log
        }


    #@staticmethod
    #def simulate_full_bounty_fight(player_info: dict, monster_info: dict) -> dict:
    #    """
    #    模拟玩家与悬赏怪物的完整战斗过程
    #    :param player_info: 玩家的完整信息字典
    #    :param monster_info: 怪物的信息字典
    #    :return: 包含战斗结果和日志的字典
    #    """
    #    battle_log = [f"你遭遇了【{monster_info['name']}】，战斗一触即发！"]

    #    player_hp = player_info['hp']
    #    monster_hp = monster_info['hp']
    #    if not monster_hp:
    #        monster_hp = 100

    #    # 战斗循环，最多进行50个回合，防止无限战斗
    #    for i in range(50):
    #        # 玩家先手
    #        player_damage = player_info['atk'] + random.randint(-int(player_info['atk'] * 0.1), int(player_info['atk'] * 0.1))
    #        monster_hp -= player_damage
    #        battle_log.append(f"第{i+1}回合：你对【{monster_info['name']}】造成了 {player_damage} 点伤害！")
    #        if monster_hp <= 0:
    #            break

    #        # 怪物反击
    #        monster_damage = monster_info['atk'] + random.randint(-int(monster_info['atk'] * 0.1), int(monster_info['atk'] * 0.1))
    #        player_hp -= monster_damage
    #        battle_log.append(f"          【{monster_info['name']}】对你造成了 {monster_damage} 点伤害！")
    #        if player_hp <= 0:
    #            break

    #    result = {}
    #    if player_hp > 0:
    #        battle_log.append(f"\n恭喜道友，成功击败了【{monster_info['name']}】！")
    #        result = {"success": True, "log": battle_log, "player_hp": player_hp, "monster_hp": monster_hp}
    #    else:
    #        battle_log.append(f"\n很遗憾，你被【{monster_info['name']}】击败了...")
    #        result = {"success": False, "log": battle_log, "player_hp": player_hp, "monster_hp": monster_hp}

    #    return result

    @staticmethod
    def execute_robbery_fight(attacker_info: dict, defender_info: dict) -> dict:
        """
        【修正版】执行抢劫战斗模拟, 调用核心PVP战斗逻辑
        """
        battle_result = PvPManager.simulate_player_vs_player_fight(attacker_info, defender_info)

        final_result = {
            "winner": battle_result["winner"],
            "loser": battle_result["loser"],
            "log": battle_result["log"],
            "stolen_amount": 0, # 默认为0
            "attacker_hp_final": battle_result["p1_hp_final"], # 假设 attacker_info 是 p1
            "defender_hp_final": battle_result["p2_hp_final"],
            "attacker_mp_final": battle_result["p1_mp_final"], # 假设 attacker_info 是 p1
            "defender_mp_final": battle_result["p2_mp_final"],
            "battle_round_details_log": battle_result["battle_round_details_log"]
        }

        if battle_result["winner"] == attacker_info['user_id']: # 攻击方胜利
            # 假设抢劫成功率和金额计算规则
            # 原版是10%的对方灵石
            # 你可以根据 XiuConfig 调整
            # from ..config import XiuConfig # 假设可以这样导入
            # rob_percent = XiuConfig().rob_stone_percent_of_target_total # 比如 0.05 (5%)
            # rob_max_amount = XiuConfig().rob_stone_max_amount # 比如 10000
            rob_percent = 0.05 # 示例：抢夺对方当前灵石的5%
            rob_max_amount = 10000 # 示例：单次最多抢10000

            stolen_amount = int(defender_info['stone'] * rob_percent)
            stolen_amount = min(stolen_amount, rob_max_amount) # 不超过上限
            stolen_amount = max(0, stolen_amount) # 不会是负数

            final_result["stolen_amount"] = stolen_amount
            final_result["log"].append(f"💰【{attacker_info['user_name']}】乘胜追击，从【{defender_info['user_name']}】处搜刮了 {stolen_amount} 块灵石！")

        elif battle_result["winner"] == defender_info['user_id']: # 防守方胜利 (攻击方失败)
            # 攻击方失败惩罚
            # penalty_amount = XiuConfig().rob_fail_penalty # 比如 500
            penalty_amount = 500 # 示例：失败罚款500
            final_result["stolen_amount"] = -penalty_amount # 用负数表示攻击方损失
            final_result["log"].append(f"💸【{attacker_info['user_name']}】抢劫失败，反被【{defender_info['user_name']}】教训了一顿，损失了 {penalty_amount} 块灵石作为赔偿！")
        else: # 平局
            final_result["log"].append(f"🤝 双方势均力敌，未能分出胜负，也未有灵石易手。")

        return final_result

    @staticmethod
    def simulate_full_bounty_fight(player_info: dict, monster_info: dict) -> dict:
        # ... (这个方法保持你现有的，或者如果怪物属性复杂了，也让它调用 _calculate_damage)
        # 简单的说，就是把 monster_info 也包装成类似 player_info 的结构，包含 crit_rate, crit_damage, defense_rate
        # 这样就可以复用 _calculate_damage
        battle_log = [f"你遭遇了【{monster_info['name']}】，战斗一触即发！"]
        player_hp = player_info['hp']
        monster_hp = monster_info.get('hp', 100) # 确保有默认值
        monster_atk = monster_info.get('atk', 10)

        for i in range(50): # 最多50回合
            # 玩家攻击
            player_raw_damage = player_info['atk']
            player_damage, p_crit = PvPManager._calculate_damage(
                player_raw_damage,
                0.0, # 假设怪物无减伤
                player_info['crit_rate'],
                player_info['crit_damage']
            )
            monster_hp -= player_damage
            crit_log = "✨暴击！" if p_crit else ""
            battle_log.append(f"第{i+1}回合：你{crit_log}对【{monster_info['name']}】造成了 {player_damage} 点伤害！")
            if monster_hp <= 0:
                break

            # 怪物反击
            monster_true_damage, m_crit = PvPManager._calculate_damage(
                monster_atk,
                player_info['defense_rate'], # 玩家有减伤
                0.05, # 假设怪物有5%基础暴击率
                0.2  # 假设怪物有20%基础暴击伤害加成
            )
            player_hp -= monster_true_damage
            crit_log_m = "✨暴击！" if m_crit else ""
            battle_log.append(f"          【{monster_info['name']}】{crit_log_m}对你造成了 {monster_true_damage} 点伤害！")
            if player_hp <= 0:
                break

        result = {}
        final_player_hp = max(0, player_hp)
        if final_player_hp > 0 and monster_hp <=0 :
            battle_log.append(f"\n恭喜道友，成功击败了【{monster_info['name']}】！")
            result = {"success": True, "log": battle_log, "player_hp": final_player_hp, "monster_hp": max(0, monster_hp)}
        else:
            battle_log.append(f"\n很遗憾，你被【{monster_info['name']}】击败了...")
            result = {"success": False, "log": battle_log, "player_hp": final_player_hp, "monster_hp": max(0, monster_hp)}
        return result

    @staticmethod
    def _apply_end_of_round_sub_buff_effects(player_state, service_items_instance) -> list[str]:
        """
        在回合结束时应用玩家装备的辅修功法的被动效果。
        :param player_state: 当前玩家的 PlayerBattleInternalState 实例
        :param service_items_instance: Items 类的实例，用于获取物品信息
        :return: 包含效果描述的日志列表
        """
        effect_log = []
        if not player_state: # 检查 player_state 对象本身是否为 None
            return effect_log

        buff_info_obj = player_state.buff_info # <<< 修正：直接访问属性
        if not buff_info_obj: # 检查 buff_info 对象是否为 None
            return effect_log

        sub_buff_id = getattr(buff_info_obj, 'sub_buff', 0) # 安全获取 sub_buff

        if sub_buff_id == 0:  # 没有装备辅修功法
            return effect_log

        sub_buff_data = service_items_instance.get_data_by_item_id(sub_buff_id)
        if not sub_buff_data:
            logger.warning(f"未能找到ID为 {sub_buff_id} 的辅修功法数据。")
            return effect_log

        buff_type = sub_buff_data.get("buff_type")
        buff_value_percent = float(sub_buff_data.get("buff", "0")) / 100.0

        original_hp = player_state.hp # <<< 修正
        original_mp = player_state.mp # <<< 修正

        if buff_type == "4":  # 每回合气血回复
            # 注意：max_hp 在 PlayerBattleInternalState 中应该叫 base_hp (战斗开始时的最大血量)
            # 或者如果 PlayerBattleInternalState 也有一个动态的 max_hp (受buff影响的当前最大血量)，则用那个
            # 假设我们用 base_hp 作为回复上限和计算基准
            hp_to_restore = int(player_state.base_hp * buff_value_percent) # <<< 修正
            if hp_to_restore > 0:
                player_state.hp = min(player_state.base_hp, player_state.hp + hp_to_restore) # <<< 修正
                healed_amount = player_state.hp - original_hp
                if healed_amount > 0:
                    effect_log.append(f"✨【{sub_buff_data['name']}】效果发动，{player_state.user_name} 回复了 {healed_amount} 点气血！")

        elif buff_type == "5":  # 每回合真元回复
            mp_to_restore = int(player_state.base_mp * buff_value_percent) # <<< 修正
            if mp_to_restore > 0:
                player_state.mp = min(player_state.base_mp, player_state.mp + mp_to_restore) # <<< 修正
                restored_mp_amount = player_state.mp - original_mp
                if restored_mp_amount > 0:
                    effect_log.append(f"✨【{sub_buff_data['name']}】效果发动，{player_state.user_name} 回复了 {restored_mp_amount} 点真元！")

        return effect_log


class PlayerBattleInternalState:
    def __init__(self, p_info: dict, items_manager):
        self.user_id = p_info['user_id']
        self.user_name = p_info['user_name']
        
        # 基础属性 (在战斗开始时固定，除非有永久改变属性的技能)
        self.base_hp = p_info['max_hp'] # 使用max_hp作为基准
        self.base_mp = p_info.get('max_mp', p_info.get('mp', 999999))
        self.base_atk = p_info['atk']
        self.base_defense_rate = p_info['defense_rate']
        self.base_crit_rate = p_info.get('crit_rate', 0.05) # 默认5%暴击
        self.base_crit_damage = p_info.get('crit_damage', 0.5) # 默认暴击造成额外50%伤害

        # 动态属性 (战斗中会变化)
        self.hp = p_info['hp']
        self.mp = p_info.get('mp', self.base_mp)
        self.exp = p_info.get('exp', 1000) # 用于计算神通消耗

        # 静态信息
        self.power = p_info['power']
        self.level = p_info['level']
        self.buff_info = p_info.get('buff_info')
        self.items_manager = items_manager

        self.user_level_rank = USERRANK.get(self.level, 99)

        # 神通相关状态
        self.active_skill_id = getattr(self.buff_info, 'sec_buff', 0) if self.buff_info else 0
        self.active_skill_data = self.items_manager.get_data_by_item_id(self.active_skill_id) if self.active_skill_id != 0 else None
        logger.info("self.active_skill_data :" + str(self.active_skill_data))
        
        self.skill_cooldown = 0 # 当前神通的剩余冷却回合
        self.is_sealed = 0 # 被封印的剩余回合
        
        # 战斗中的临时效果
        self.active_dot_effects = [] 
        # [{'name': str, 'damage_per_turn': int, 'remaining_turns': int, 'caster_id': str}]
        
        self.active_buff_effects = [] 
        # [{'name': str, 'type': str(如'atk_rate', 'def_rate', 'crit_rate_add', 'crit_dmg_add'), 
        #   'value': float, 'remaining_turns': int, 'caster_id': str, 'is_debuff': bool}]

    def tick_cooldowns_and_effects(self):
        """每回合开始时调用，减少冷却和持续效果的回合数"""
        if self.skill_cooldown > 0:
            self.skill_cooldown -= 1
        
        if self.is_sealed > 0:
            self.is_sealed -= 1

        next_dots = []
        for dot in self.active_dot_effects:
            dot['remaining_turns'] -= 1
            if dot['remaining_turns'] >= 0:
                next_dots.append(dot)
        self.active_dot_effects = next_dots
        
        next_buffs = []
        for buff in self.active_buff_effects:
            buff['remaining_turns'] -= 1
            if buff['remaining_turns'] >= 0:
                next_buffs.append(buff)
        self.active_buff_effects = next_buffs

    def get_current_atk(self) -> int:
        """计算应用了Buff后的当前攻击力"""
        atk_rate_bonus = sum(b['value'] for b in self.active_buff_effects if b['type'] == 'atk_rate' and not b.get('is_debuff'))
        atk_rate_penalty = sum(b['value'] for b in self.active_buff_effects if b['type'] == 'atk_rate' and b.get('is_debuff'))
        # 可以考虑固定值加成，但原版神通似乎没有
        return int(self.base_atk * (1 + atk_rate_bonus - atk_rate_penalty))

    def get_current_defense_rate(self) -> float:
        """计算应用了Buff后的当前减伤率"""
        def_rate_bonus = sum(b['value'] for b in self.active_buff_effects if b['type'] == 'def_rate' and not b.get('is_debuff'))
        def_rate_penalty = sum(b['value'] for b in self.active_buff_effects if b['type'] == 'def_rate' and b.get('is_debuff'))
        current_def = self.base_defense_rate + def_rate_bonus - def_rate_penalty
        return min(0.9, max(0, current_def)) # 减伤率限制在 0% 到 90%

    def get_current_crit_rate(self) -> float:
        """计算应用了Buff后的当前暴击率"""
        crit_rate_add = sum(b['value'] for b in self.active_buff_effects if b['type'] == 'crit_rate_add')
        # 假设暴击率是直接加算，且不超过100%
        return min(1.0, self.base_crit_rate + crit_rate_add)

    def get_current_crit_damage(self) -> float:
        """计算应用了Buff后的当前暴击伤害加成"""
        crit_dmg_add = sum(b['value'] for b in self.active_buff_effects if b['type'] == 'crit_dmg_add')
        # 暴击伤害加成也是直接加算
        return self.base_crit_damage + crit_dmg_add

    def _calculate_actual_mp_cost(self) -> int:
        """计算神通实际MP消耗，考虑境界折减"""
        if not self.active_skill_data:
            return 0

        # mpcost 现在直接代表最大MP的消耗百分比
        base_mp_cost_percent = self.active_skill_data.get('mpcost', 0.0)
        if base_mp_cost_percent <= 0:
            return 0

        base_required_mp = int(self.base_mp * base_mp_cost_percent)

        # 获取技能品阶文本，例如 "人阶下品"
        skill_rank_text = self.active_skill_data.get('rank', "未知品阶")
        # 使用 SKILL_RANK_VALUE 将文本品阶转换为数字品阶
        skill_rank_numeric = SKILL_RANK_VALUE.get(skill_rank_text, 99) # <<< 核心修正点

        # 玩家境界rank (self.user_level_rank) 是在 __init__ 中用 USERRANK 计算的
        level_diff = self.user_level_rank - skill_rank_numeric # 玩家境界rank - 技能品阶rank
                                                              # 同样，正数代表玩家境界远高于技能品阶

        reduction_factor = 1.0 # 默认无折减
        # 从 MP_COST_REDUCTION_MAP 中查找合适的折减系数
        # 遍历映射表，找到第一个满足条件的境界差（因为表是按差值从大到小或特定顺序定义的）
        # 假设 MP_COST_REDUCTION_MAP 的键是从大（高境界差）到小（低境界差）排列
        # 或者，更通用的方法是找到最接近且不超过 level_diff 的那个键

        # 精确查找或向下取最接近的键
        applicable_reduction_key = 0 # 默认无差（对应1.0的因子）
        for diff_threshold in sorted(MP_COST_REDUCTION_MAP.keys(), reverse=True): # 从大到小遍历阈值
            if level_diff >= diff_threshold:
                applicable_reduction_key = diff_threshold
                break
        reduction_factor = MP_COST_REDUCTION_MAP.get(applicable_reduction_key, 1.0)

        actual_mp_cost = int(base_required_mp * reduction_factor)

        min_cost_for_any_skill = max(1, int(self.base_mp * 0.01)) # 例如，最低消耗1点MP或最大MP的1%，取较大者
        actual_mp_cost = max(min_cost_for_any_skill, actual_mp_cost)

        # logger.debug(f"MP消耗计算: 技能 {self.active_skill_data['name']}, 基础消耗百分比 {base_mp_cost_percent*100}%, "
        #              f"基础MP消耗 {base_required_mp}, 玩家品阶 {self.user_level_rank} ({self.level}), "
        #              f"技能品阶 {skill_rank_value} ({skill_rank_text}), 境界差 {level_diff}, "
        #              f"折减系数 {reduction_factor:.2f}, 最终消耗 {actual_mp_cost}")

        return actual_mp_cost

    # can_use_skill, apply_mp_cost_for_skill 方法将自动使用新的 _calculate_actual_mp_cost 逻辑，
    # 无需显式修改这两个方法内部的MP消耗计算部分，因为它们已经调用了 _calculate_actual_mp_cost。
    # 只需要确保 can_use_skill 中的MP检查是 >= _calculate_actual_mp_cost() 的结果。
    # HP消耗判断逻辑保持不变。
    def can_use_skill(self) -> bool:
        if self.is_sealed > 0: return False
        if not self.active_skill_data: return False
        if self.skill_cooldown > 0: return False

        required_mp = self._calculate_actual_mp_cost()
        if self.mp < required_mp: return False

        #hp_cost_percent = self.active_skill_data.get('hpcost', 0.0)
        #if hp_cost_percent > 0:
        #    hp_that_would_be_consumed = int(self.hp * hp_cost_percent)
        #    if hp_that_would_be_consumed >= self.hp and self.hp > 0: # 如果消耗大于等于当前HP，则不能用
        #         return False
        return True

    def apply_mp_cost_for_skill(self): # 这个方法本身不需要改，因为它调用了已修改的_calculate_actual_mp_cost
        if self.active_skill_data:
            actual_mp_cost = self._calculate_actual_mp_cost()
            self.mp -= actual_mp_cost
            return actual_mp_cost
        return 0

        
        mp_cost_percent = self.active_skill_data.get('mpcost', 0.0)
        required_mp = int(self.exp * mp_cost_percent) # MP消耗基于修为
        return self.mp >= required_mp

    def apply_hp_cost_for_skill(self):
        if self.active_skill_data:
            hp_cost_percent = self.active_skill_data.get('hpcost', 0.0)
            hp_cost_actual = int(self.hp * hp_cost_percent) # HP消耗基于当前HP
            self.hp -= hp_cost_actual
            self.hp = max(0, self.hp) # 确保HP不为负
            return hp_cost_actual
        return 0


    def add_buff_effect(self, name: str, buff_type_str: str, value: float, duration: int, caster_id: str, is_debuff: bool = False):
        """添加一个Buff/Debuff效果"""
        # 可选：实现Buff叠加/覆盖逻辑，例如同名高级覆盖低级，或同类型取最高等
        self.active_buff_effects.append({
            'name': name, 'type': buff_type_str, 'value': value,
            'remaining_turns': duration, 'caster_id': caster_id, 'is_debuff': is_debuff
        })
        
    def add_dot_effect(self, name: str, damage_per_turn: int, duration: int, caster_id: str):
        """添加一个持续伤害效果"""
        self.active_dot_effects.append({
            'name': name, 'damage_per_turn': damage_per_turn,
            'remaining_turns': duration, 'caster_id': caster_id
        })
