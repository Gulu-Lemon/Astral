"""
仲裁层 — 收集所有 agent 意图，消解冲突，判定结果，生成证据，更新世界状态
"""
from __future__ import annotations
from typing import Optional
import random
from state import (
    WorldState, AgentState, Event, Intent, IntentType,
    Ruling, Evidence, GamePhase, AffectionEntry,
    DEAD_NPC, roll_risk,
)
from characters import CHARACTERS


class Arbiter:
    def __init__(self, llm, random_seed: Optional[int] = None, characters: Optional[dict] = None):
        self._llm = llm
        self._rng = random.Random(random_seed)
        self._characters = characters or {}

    def process_round(
        self,
        intents: dict[str, list],       # agent_id → list[Intent]
        agent_states: dict[str, AgentState],
        world: WorldState,
    ) -> list[Ruling]:
        """处理一轮中的所有意图（支持多意图）"""
        rulings: list[Ruling] = []

        # 展平：每个 intent 独立处理
        flat_intents = []
        for aid, intent_list in sorted(intents.items()):
            for intent in intent_list:
                flat_intents.append((aid, intent))

        # 优先级排序
        priority_order = [
            IntentType.ATTACK, IntentType.TRAP, IntentType.SABOTAGE,
            IntentType.STALK, IntentType.DEFEND, IntentType.CONFRONT,
            IntentType.ISOLATE, IntentType.SOCIALIZE, IntentType.EXPLORE,
            IntentType.REST,
        ]
        flat_intents.sort(
            key=lambda kv: priority_order.index(kv[1].intent_type)
            if kv[1].intent_type in priority_order else 99
        )

        # Phase 2: 冲突检测
        intents_map = {aid: list(il) for aid, il in intents.items()}
        conflict_matrix = self._detect_conflicts(intents_map, world)

        for agent_id, intent in flat_intents:
            ruling = self._rule_on_intent(agent_id, intent, agent_states, world, conflict_matrix)
            rulings.append(ruling)

        self._apply_rulings(rulings, agent_states, world)
        return rulings

    def _detect_conflicts(
        self, intents: dict[str, list], world: WorldState
    ) -> dict[str, list[str]]:
        conflicts: dict[str, list[str]] = {}
        for aid, intent_list in intents.items():
            for intent in intent_list:
                if intent.target_id and intent.intent_type in (
                    IntentType.ATTACK, IntentType.TRAP, IntentType.CONFRONT, IntentType.STALK, IntentType.SABOTAGE
                ):
                    key = intent.target_id
                    conflicts.setdefault(key, []).append(aid)
        return conflicts

    def _rule_on_intent(
        self, agent_id: str, intent: Intent,
        agent_states: dict[str, AgentState],
        world: WorldState,
        conflicts: dict[str, list[str]],
    ) -> Ruling:
        """对单个意图做出裁决"""
        ruling = Ruling(intent=intent, approved=True, success=True)

        # --- 阶段审查 ---
        if intent.intent_type == IntentType.ATTACK:
            if world.phase != GamePhase.HUNTING:
                ruling.approved = False
                ruling.downgraded_to = IntentType.CONFRONT
                ruling.description = f"[黑箱/暗流期禁止致命攻击] {agent_id} 的攻击意图被压制成对峙。"
                return ruling
            if not intent.target_id:
                ruling.approved = False
                ruling.description = "攻击意图无目标，视为无效。"
                return ruling
            # 目击者检测：同位置有其他 NPC 时攻击自动失败
            actor_loc = world.npc_locations.get(agent_id, "")
            witnesses = [
                aid for aid, aloc in world.npc_locations.items()
                if aloc == actor_loc and aid != agent_id and aid != intent.target_id
                and agent_states.get(aid, DEAD_NPC).alive
            ]
            if witnesses:
                ruling.approved = False
                ruling.downgraded_to = IntentType.CONFRONT
                ruling.description = f"{agent_id} 准备攻击但周围有目击者（{', '.join(witnesses)}），改为对峙。"
                return ruling

        if intent.intent_type == IntentType.TRAP:
            if world.phase != GamePhase.HUNTING:
                ruling.approved = False
                ruling.downgraded_to = IntentType.ISOLATE
                ruling.description = f"[非猎杀期禁止陷阱] {agent_id} 的陷阱意图被压制。"
                return ruling
            # 陷阱不检查目击者

        if intent.intent_type == IntentType.SABOTAGE:
            if world.phase == GamePhase.BLACKOUT:
                ruling.approved = False
                ruling.downgraded_to = IntentType.ISOLATE
                ruling.description = f"[黑箱期禁止破坏行为] {agent_id} 的行为降级为冷处理。"
                return ruling
            # 禁止彻底毁尸灭迹（道德底线/行动总会留下痕迹）
            if world.undiscovered_bodies or world.discovered_bodies:
                actor_loc = world.npc_locations.get(agent_id, "")
                if actor_loc and any(
                    world.npc_locations.get(v, "") == actor_loc
                    for v in world.undiscovered_bodies + world.discovered_bodies
                ):
                    ruling.approved = False
                    ruling.downgraded_to = IntentType.CONFRONT
                    ruling.description = f"{agent_id} 试图毁尸灭迹但无法做到——道德底线或现场状况阻止了彻底销毁。留下的痕迹反而增加了嫌疑。"
                    return ruling

        if intent.intent_type == IntentType.DEFEND:
            if world.phase != GamePhase.HUNTING:
                ruling.approved = False
                ruling.downgraded_to = IntentType.REST
                ruling.description = f"[非猎杀期禁止防御行动] {agent_id} 的防御意图被压制为待机。"
                return ruling

        # --- 技能判定（基于游戏规则的 modulo-6 系统）---
        risk_rating = self._assess_risk(intent, agent_states, world)
        tick = world.global_tick
        success = roll_risk(risk_rating, self._rng)
        ruling.success = success

        # --- 证据生成（仅对恶意行为）---
        if intent.intent_type in (
            IntentType.ATTACK, IntentType.TRAP, IntentType.SABOTAGE, IntentType.STALK,
            IntentType.CONFRONT, IntentType.ISOLATE,
        ):
            ruling.evidence_generated = self._generate_evidence(
                agent_id, intent, ruling.success, agent_states, world
            )
            ruling.evidence_generated = ruling.evidence_generated or []

        # --- 生成描述 ---
        ruling.description = self._build_ruling_description(
            agent_id, intent, ruling.success,
            agent_states.get(agent_id),
            world
        )

        # --- 影响范围 ---
        agent_state = agent_states.get(agent_id)
        if agent_state:
            ruling.affected_agents = [agent_id]
            if intent.target_id:
                ruling.affected_agents.append(intent.target_id)

        return ruling

    def _assess_risk(
        self, intent: Intent, agent_states: dict[str, AgentState], world: WorldState
    ) -> str:
        """评估行动风险等级（方案A：Arbiter 可上调不可下调）"""
        it = intent.intent_type
        arbiter_risk = "中风险"  # 默认

        if it in (IntentType.REST, IntentType.EXPLORE):
            arbiter_risk = "无风险"
        elif it == IntentType.SOCIALIZE:
            arbiter_risk = "低风险"
        elif it == IntentType.ISOLATE:
            arbiter_risk = "较低风险"
        elif it == IntentType.CONFRONT:
            if intent.target_id and intent.target_id in agent_states:
                target_threat = agent_states[intent.target_id].threat_level
                if target_threat > 0.7:
                    arbiter_risk = "高风险"
                elif target_threat > 0.4:
                    arbiter_risk = "中风险"
                else:
                    arbiter_risk = "较低风险"
            else:
                arbiter_risk = "较低风险"
        elif it == IntentType.STALK:
            arbiter_risk = "中风险"
        elif it == IntentType.SABOTAGE:
            arbiter_risk = "高风险"
        elif it == IntentType.ATTACK:
            if intent.target_id and intent.target_id in agent_states:
                target = agent_states[intent.target_id]
                if target.threat_level > 0.8:
                    arbiter_risk = "极高风险"
                elif target.threat_level > 0.5:
                    arbiter_risk = "高风险"
                else:
                    arbiter_risk = "中风险"
            else:
                arbiter_risk = "中风险"
        elif it == IntentType.TRAP:
            actor_loc = world.npc_locations.get(intent.agent_id, "")
            nearby_count = 0
            if actor_loc:
                for nid, aloc in list(world.npc_locations.items()):
                    if aloc == actor_loc and nid != intent.agent_id and nid != intent.target_id:
                        ns = agent_states.get(nid)
                        if ns and ns.alive:
                            nearby_count += 1
            external_risk_boost = min(nearby_count, 3)
            level_order = {"无风险":0, "低风险":1, "中风险":2, "高风险":3, "极高风险":4}
            base = level_order.get(intent.risk, 2)
            final = min(base + external_risk_boost, 4)
            reverse_map = {0:"无风险",1:"低风险",2:"中风险",3:"高风险",4:"极高风险"}
            return reverse_map[final]  # TRAP 已叠加 external_boost，跳过通用 max 比较

        # 方案 A：尊重 LLM 自评，Arbiter 只上调不回调
        if intent.risk and intent.risk.strip():
            llm_risk = intent.risk.strip()
            risk_levels = {"无风险":0, "低风险":1, "较低风险":2, "中风险":3, "高风险":4, "极高风险":5, "不可能":6}
            arb_lvl = risk_levels.get(arbiter_risk, 3)
            llm_lvl = risk_levels.get(llm_risk, 3)
            if llm_lvl > arb_lvl:
                return llm_risk
        return arbiter_risk

    def _generate_evidence(
        self, actor_id: str, intent: Intent, success: bool,
        agent_states: dict[str, AgentState], world: WorldState,
    ) -> list[Evidence]:
        """生成证据 — 保证逻辑自洽但不保证唯一指向"""
        loc = world.npc_locations.get(actor_id, "未知")
        evidences: list[Evidence] = []

        actor_state = agent_states.get(actor_id)
        actor_name = CHARACTERS.get(actor_id, type('', (), {'name': actor_id})).name if actor_id in CHARACTERS else actor_id

        if intent.intent_type == IntentType.ATTACK:
            # 致命攻击 — 生成全套证据
            try:
                result = self._llm.chat_json(
                    messages=[{
                        "role": "user",
                        "content": f"角色 {actor_name} 在 {loc} 对角色 {self._get_name(intent.target_id)} 发起攻击。"
                                    f"行动成功？{'是' if success else '否'}。"
                                    f"请生成2-4条现场证据的描述（每条一句话），这些证据可能指向{actor_name}或其他人。"
                                    f"输出 JSON：{{\"items\": [{{\"description\": \"...\", \"points_to\": [\"No.XX\"]}}]}}"
                    }],
                    temperature=0.8, max_tokens=1024,
                )
                items = result if isinstance(result, list) else result.get("items", [])
                if not isinstance(items, list):
                    items = []
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    evidences.append(Evidence(
                        location=loc,
                        description=item.get("description", ""),
                        points_to=item.get("points_to", [actor_id]),
                        reliability="中等" if success else "模糊",
                    ))
            except Exception:
                pass

        elif intent.intent_type == IntentType.SABOTAGE:
            evidences.append(Evidence(
                location=loc,
                description=f"某些物品似乎被翻动过，可能有东西丢失。",
                points_to=[actor_id],
                reliability="模糊",
            ))

        return evidences

    def _build_ruling_description(
        self, agent_id: str, intent: Intent, success: bool,
        agent_state: Optional[AgentState], world: WorldState,
    ) -> str:
        actor_name = self._get_name(agent_id)
        loc = world.npc_locations.get(agent_id, "未知")
        it = intent.intent_type
        reasoning_hint = f"（动机：{intent.reasoning[:120]}）" if intent.reasoning else ""
        scene_hint = f" [{intent.scene_hint}]" if intent.scene_hint else ""

        if it == IntentType.REST:
            return f"{actor_name} 待在 {loc}，没有特别行动。{reasoning_hint}{scene_hint}".rstrip()
        if it == IntentType.EXPLORE:
            dest = intent.target_location or "附近的房间"
            return f"{actor_name} 前往探索 {dest}。{reasoning_hint}{scene_hint}".rstrip()
        if it == IntentType.SOCIALIZE:
            target = self._get_name(intent.target_id) if intent.target_id else "周围的人"
            return f"{actor_name} 在 {loc} 与 {target} 互动。{reasoning_hint}{scene_hint}".rstrip()
        if it == IntentType.CONFRONT:
            target = self._get_name(intent.target_id)
            status = "公开指责了" if success else "试图指责但被无视了"
            return f"{actor_name} 在 {loc} {status} {target}。{reasoning_hint}{scene_hint}".rstrip()
        if it == IntentType.ISOLATE:
            target = self._get_name(intent.target_id)
            return f"{actor_name} 在 {loc} 刻意冷落了 {target}。{reasoning_hint}{scene_hint}".rstrip()
        if it == IntentType.STALK:
            target = self._get_name(intent.target_id)
            status = "暗中观察了" if success else "试图跟踪但跟丢了"
            return f"{actor_name} {status} {target}。{reasoning_hint}{scene_hint}".rstrip()
        if it == IntentType.SABOTAGE:
            status = "成功破坏了" if success else "试图破坏但被发现了的"
            target = self._get_name(intent.target_id)
            return f"{actor_name} 在 {loc} {status} {target} 的物品。{reasoning_hint}{scene_hint}".rstrip()
        if it == IntentType.ATTACK:
            target = self._get_name(intent.target_id)
            if success:
                return f"‼️ 严重事件：{actor_name} 在 {loc} 对 {target} 发动了致命攻击。{reasoning_hint}{scene_hint}".rstrip()
            return f"{actor_name} 在 {loc} 试图攻击 {target} 但失败了。{reasoning_hint}{scene_hint}".rstrip()
        if it == IntentType.TRAP:
            target = self._get_name(intent.target_id)
            if success:
                return f"‼️ 陷阱：{actor_name} 设下的陷阱杀死了 {target}。{reasoning_hint}{scene_hint}".rstrip()
            return f"{actor_name} 设下的陷阱没有触发。{reasoning_hint}{scene_hint}".rstrip()
        return f"{actor_name} 在 {loc} 进行了行动。{reasoning_hint}{scene_hint}".rstrip()

    def _apply_rulings(
        self, rulings: list[Ruling], agent_states: dict[str, AgentState], world: WorldState
    ):
        """将裁决结果写入世界状态"""
        for ruling in rulings:
            evt = Event(
                tick=world.global_tick,
                event_type=ruling.intent.intent_type.value,
                actor_id=ruling.intent.agent_id,
                target_id=ruling.intent.target_id or "",
                location=world.npc_locations.get(ruling.intent.agent_id, "未知"),
                public_description=ruling.description,
                full_description=self._build_full_description(ruling.description, ruling.intent),
                dialogue_snapshot=ruling.intent.dialogue or "",
                full_reasoning=ruling.intent.reasoning or "",
                evidence_ids=[e.evidence_id for e in ruling.evidence_generated],
            )

            actor_loc = world.npc_locations.get(ruling.intent.agent_id, "")
            evt.witnesses = {
                aid for aid, aloc in world.npc_locations.items()
                if aloc == actor_loc
            }

            world.public_events.append(evt)

            actor_state = agent_states.get(ruling.intent.agent_id)
            if actor_state:
                if ruling.intent.intent_type == IntentType.CONFRONT:
                    if ruling.success:
                        actor_state.threat_level = max(0, actor_state.threat_level - 0.1)
                    else:
                        actor_state.threat_level = min(1.0, actor_state.threat_level + 0.1)
                # 存储 NPC 内心活动作为个人记忆
                if ruling.intent.internal:
                    actor_state.private_motives.append(ruling.intent.internal)

            # 填充目击者的 witnessed_events
            event_desc = evt.full_description or evt.public_description
            for witness_id in evt.witnesses:
                ws = agent_states.get(witness_id)
                if ws and ws.alive and event_desc.strip():
                    ws.witnessed_events.append(event_desc)

            if ruling.intent.intent_type == IntentType.EXPLORE and ruling.success:
                dest = ruling.intent.target_location
                if dest:
                    world.npc_locations[ruling.intent.agent_id] = dest
                    world.explored_rooms.add(dest)

        self._evaluate_affection(rulings, agent_states, world)

    def _evaluate_affection(
        self, rulings: list[Ruling], agent_states: dict[str, AgentState], world: WorldState
    ):
        interactions = []
        for r in rulings:
            if not r.intent.target_id or not r.success:
                continue
            it = r.intent.intent_type
            if it not in (IntentType.SOCIALIZE, IntentType.CONFRONT, IntentType.ATTACK,
                          IntentType.TRAP, IntentType.SABOTAGE):
                continue
            actor_id = r.intent.agent_id
            target_id = r.intent.target_id
            as_actor = agent_states.get(actor_id)
            as_target = agent_states.get(target_id)
            if not as_actor or not as_actor.alive or not as_target or not as_target.alive:
                continue
            cp_actor = self._characters.get(actor_id)
            cp_target = self._characters.get(target_id)
            if not cp_actor or not cp_target:
                continue
            interactions.append({
                "actor_id": actor_id,
                "actor_name": cp_actor.name,
                "actor_personality": getattr(cp_actor, "personality", "未知") or "未知",
                "target_id": target_id,
                "target_name": cp_target.name,
                "target_personality": getattr(cp_target, "personality", "未知") or "未知",
                "intent_type": it.value,
                "description": r.description,
                "actor_aff": as_actor.affection_map.get(target_id, 50),
                "target_aff": as_target.affection_map.get(actor_id, 50),
            })
        if not interactions:
            return

        items_text = []
        for i, inter in enumerate(interactions):
            items_text.append(
                f"交互{i+1}：{inter['actor_name']}({inter['actor_personality']}) "
                f"对 {inter['target_name']}({inter['target_personality']}) "
                f"进行了 {inter['intent_type']}：「{inter['description']}」"
                f"\n  当前好感：{inter['actor_name']}→{inter['target_name']}={inter['actor_aff']}，"
                f"{inter['target_name']}→{inter['actor_name']}={inter['target_aff']}"
            )
        prompt = f"""评估以下 NPC 间交互对好感度的影响。根据每个 NPC 的性格和交互的具体内容，判断好感度变化（-10 到 +10）。

{chr(10).join(items_text)}

规则：
- 双方好感独立评估（A→B可能与B→A不同）
- SOCIALIZE 通常正向(0~+8)，配合作者的恶意/冒犯话语可能负向
- CONFRONT 通常负向(-3~-8)，性格强势者可能欣赏对方勇气而持平
- ATTACK/TRAP 被攻击方→攻击方大幅负向(-8~-10)
- 变化幅度受当前好感影响：高好感上升空间小，低好感上升空间大；低好感下降空间小，高好感下降空间大
- delta=0 表示关系不变

输出 JSON：
{{"evaluations":[{{"actor_id":"No.01","target_id":"No.05","delta":3,"reason":"一句话原因"}}]}}
"""
        try:
            result = self._llm.chat_json(
                messages=[{"role": "user", "content": prompt}],
                system="你是游戏剧本的社交逻辑判断引擎。根据角色性格和交互内容，输出准确的好感度变化。",
                temperature=0.9, max_tokens=1024,
            )
        except Exception:
            self._fallback_affection(rulings, agent_states)
            return

        evals = result.get("evaluations", [])
        if not isinstance(evals, list):
            self._fallback_affection(rulings, agent_states)
            return

        tick = world.global_tick
        for ev in evals:
            if not isinstance(ev, dict):
                continue
            actor_id = str(ev.get("actor_id", ""))
            target_id = str(ev.get("target_id", ""))
            try:
                delta = max(-10, min(10, int(ev.get("delta", 0))))
            except (ValueError, TypeError):
                delta = 0
            reason = str(ev.get("reason", "")) or ""
            as_actor = agent_states.get(actor_id)
            if as_actor and as_actor.alive:
                current = as_actor.affection_map.get(target_id, 50)
                as_actor.affection_map[target_id] = max(0, min(100, current + delta))
                if reason:
                    entry = AffectionEntry(target_id=target_id, delta=delta, reason=reason, tick=tick)
                    as_actor.affection_log.append(entry)
                    if len(as_actor.affection_log) > 5:
                        as_actor.affection_log = as_actor.affection_log[-5:]

    def _fallback_affection(self, rulings, agent_states):
        for r in rulings:
            if not r.intent.target_id or not r.success:
                continue
            as_actor = agent_states.get(r.intent.agent_id)
            if not as_actor or not as_actor.alive:
                continue
            target = r.intent.target_id
            if r.intent.intent_type in (IntentType.ATTACK, IntentType.TRAP, IntentType.CONFRONT):
                as_actor.affection_map[target] = max(0, min(100, as_actor.affection_map.get(target, 50) - 10))
            elif r.intent.intent_type == IntentType.SOCIALIZE:
                as_actor.affection_map[target] = max(0, min(100, as_actor.affection_map.get(target, 50) + 5))

    def _build_narrative_materials(self, rulings: list[Ruling]) -> str:
        materials = []
        for r in rulings:
            it = r.intent
            if it.intent_type == IntentType.DEFEND:
                continue
            actor_name = self._get_name(it.agent_id)
            target_name = self._get_name(it.target_id) if it.target_id else None
            entry = f"[{actor_name}] {it.intent_type.value}"
            if it.intent_type in (IntentType.REST, IntentType.EXPLORE, IntentType.ISOLATE, IntentType.DEFEND):
                entry += " [可略写]"
            if target_name:
                entry += f" → {target_name}"
            if not r.success:
                entry += " (尝试但未成功)"
            if it.prose:
                entry += f"\n  动作: {it.prose}"
            if it.dialogue:
                entry += f"\n  对话: {it.dialogue}"
            if it.reasoning:
                entry += f"\n  动机: {it.reasoning}"
            materials.append(entry)
        return "\n\n".join(materials) if materials else "（本轮无显著互动）"

    @staticmethod
    def _build_full_description(description: str, intent: Intent) -> str:
        """拼接完整事件描述：public_description + dialogue + prose + reasoning"""
        parts = [description]
        if intent.dialogue:
            parts.append(f"她说：「{intent.dialogue}」")
        if intent.prose:
            parts.append(f"动作描写：{intent.prose}")
        if intent.reasoning:
            parts.append(f"深层动机：{intent.reasoning}")
        return "\n".join(parts)

    def check_body_discovery(self, person_name: str, action_desc: str, location: str, hiding_spot: str) -> bool:
        """LLM判定：该角色的行动是否可能发现藏在hiding_spot的尸体。"""
        prompt = f"""角色[{person_name}]正在：{action_desc}
位置：{location}
这间房里有一具尸体，位于：{hiding_spot}

基于该角色的行动描述，她/他是否有可能发现这具尸体？只回答 YES 或 NO。"""
        try:
            resp = self._llm.chat(messages=[{"role":"user","content":prompt}],
                                  system="你是一个情境推理器。根据角色的位置和行动，判断她是否可能发现尸体。只回答YES或NO。",
                                  temperature=0, max_tokens=5)
            return "YES" in resp.upper()
        except Exception:
            return False

    def _get_name(self, agent_id: Optional[str]) -> str:
        if not agent_id:
            return "未知"
        cp = self._characters.get(agent_id) if self._characters else None
        if not cp:
            from characters import CHARACTERS as _DEFAULT
            cp = _DEFAULT.get(agent_id)
        return cp.name if cp else agent_id
