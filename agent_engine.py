"""
NPC Agent 引擎 — 每个 NPC 的决策与行为生成
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from state import AgentState, WorldState, Event, Intent, IntentType, GamePhase, AffectionEntry
from characters import CharacterProfile


class NPCAgent:
    """每个 NPC 的独立 agent"""

    def __init__(self, agent_id: str, llm, characters: Optional[dict] = None, player_name: str = ""):
        self.agent_id: str = agent_id
        self._all_chars = characters or {}
        self._player_name = player_name
        self.profile: CharacterProfile = self._all_chars[agent_id]
        self.state: AgentState = AgentState(
            agent_id=agent_id,
            name=self.profile.name,
            affection_map={},  # 后台逐轮更新
            emotional_state="困惑"
        )
        self._llm = llm
        self._chat_history: list[dict[str, str]] = []  # agent 内部的对话记忆
        self._last_action: str = ""  # 上轮行动的摘要

    def perceive(self, world: WorldState) -> "Perception":
        """构建本轮 agent 的感知信息"""
        loc = world.npc_locations.get(self.agent_id, "")

        visible_events = []
        visible_dialogues = []
        for evt in world.public_events:
            if self.agent_id in evt.witnesses or evt.location == loc:
                visible_events.append(evt.full_description or evt.public_description)
                if evt.dialogue_snapshot:
                    actor_name = self._all_chars.get(evt.actor_id, type('',(),{'name':evt.actor_id})()).name
                    visible_dialogues.append(f"{actor_name}：「{evt.dialogue_snapshot}」")

        nearby_npcs = [
            aid for aid, aloc in world.npc_locations.items()
            if aloc == loc and aid != self.agent_id
        ]

        recent_dialogue = self._chat_history[-3:] if self._chat_history else []

        return Perception(
            agent_id=self.agent_id,
            current_location=loc,
            current_time=world.current_time,
            current_day=world.current_day,
            game_phase=world.phase,
            nearby_npcs=nearby_npcs,
            visible_events=visible_events[-5:],
            visible_dialogues=visible_dialogues[-8:],
            emotional_state=self.state.emotional_state,
            threat_level=self.state.threat_level,
            affection_snapshot=self.state.affection_map,
            previous_action=self._last_action,
            recent_dialogue=recent_dialogue,
        )

    def decide(self, world: WorldState) -> list[Intent]:
        """基于当前感知决定本轮行动"""
        perception = self.perceive(world)

        prompt = self._build_decision_prompt(perception, world)

        try:
            result = self._llm.chat_json(
                messages=[{"role": "user", "content": prompt}],
                system=self.profile.system_prompt,
                temperature=1.0,
                max_tokens=1024,
            )
        except Exception as e:
            import logging
            logging.getLogger("astral.agents").warning(f"Agent {self.agent_id} LLM 错误，默认待机: {e}")
            return [Intent(
                agent_id=self.agent_id,
                intent_type=IntentType.REST,
                reasoning="暂时不采取行动。",
            )]

        actions = result.get("actions")
        if actions is None:
            actions = [result]
        intent_list = []
        for act in actions:
            if act is None or not isinstance(act, dict):
                continue
            its = str(act.get("t", act.get("intent_type", "rest"))).lower()
            it = _parse_intent_type(its)
            tid = act.get("tid") or act.get("target_id") or None
            tloc = act.get("loc") or act.get("target_location") or None
            reason = act.get("r", act.get("reasoning", ""))
            risk = act.get("risk", "") or ""
            scene_hint = act.get("sh", act.get("scene_hint", "")) or ""
            dialogue = act.get("dialogue", "") or ""
            prose = act.get("prose", "") or ""
            internal = act.get("internal", "") or ""
            intent_list.append(Intent(
                agent_id=self.agent_id,
                intent_type=it,
                target_id=tid,
                target_location=tloc,
                reasoning=reason,
                risk=risk,
                scene_hint=scene_hint,
                dialogue=dialogue,
                prose=prose,
                internal=internal,
            ))
        new_emotion = result.get("e") or result.get("emotional_state") or ""
        if new_emotion.strip():
            self.state.emotional_state = new_emotion
        if intent_list:
            self._last_action = intent_list[0].reasoning
        if not intent_list:
            intent_list = [Intent(agent_id=self.agent_id, intent_type=IntentType.REST, reasoning="")]
        return intent_list

    def _build_decision_prompt(self, p: "Perception", world: WorldState) -> str:
        nearby_names = []
        for aid in p.nearby_npcs:
            cp = self._all_chars.get(aid)
            if cp:
                nearby_names.append(f"{cp.name}({aid})")

        aff_parts = []
        for k, v in p.affection_snapshot.items():
            cp = self._all_chars.get(k)
            name = cp.name if cp else k
            hint = _aff_hint(v)
            if v >= 65: action_hint = "信任亲近，倾向主动接近、分享信息"
            elif v >= 50: action_hint = "友善，愿意交谈互动"
            elif v >= 35: action_hint = "一般，保持基本社交"
            elif v >= 20: action_hint = "冷淡警惕，倾向回避或暗中观察"
            else: action_hint = "敌意不信任，可能对峙或密谋报复"
            aff_parts.append(f"{name}({k}):{v}({hint}，{action_hint})")
        aff_str = "；".join(aff_parts) if aff_parts else "无"

        allowed_intents = self._allowed_intents(world.phase)

        room_items = world.room_item_state.get(p.current_location, {})
        item_desc = "、".join(k for k, v in room_items.items() if v == "存在") or "无"

        curse_line = f"⚠️ 你今天受到了魔女诅咒！你的魔法【{self.profile.magic}】暂时失效。情绪被放大，愤怒/悲伤/恐惧加剧，可能失控产生杀人冲动。身体力量反而增强。" if world.cursed_npc == self.agent_id else ""

        prev_line = f"你上轮做了：{p.previous_action}" if p.previous_action else ""
        dia_parts = []
        for d in (p.recent_dialogue or []):
            if isinstance(d, dict):
                dia_parts.append(f"{d.get('role','')}:{d.get('content','')}")
            elif isinstance(d, str):
                dia_parts.append(d)
        dia_line = "最近的对话：" + "; ".join(dia_parts) if dia_parts else ""

        return f"""【世界观】你来自现代日本/当代世界。你拥有的"魔法"是个人层面的超常能力——没有咒语、没有魔法阵，它是一种与生俱来或后天觉醒的个人力量。你的思维是现代人的思维。

{world.atmosphere or ''}
{world.last_narrative_summary and f'【上轮叙事回忆】\n{world.last_narrative_summary}\n' or ''}

【行动类型】{', '.join(allowed_intents)}
【输出格式】决定你本轮 1-2 个行动。大致上 90% 按性格行事，但偶尔 (~10%) 可以做出让人意外的举动。好感度直接影响你的行为：对高好感度(≥65)的角色倾向社交合作保护，对低好感度(≤25)的角色倾向回避对峙暗中调查。
输出 JSON：
{{
  "actions": [
    {{
      "t":"类型",
      "tid":"目标ID或null",
      "loc":"地点或null",
      "r":"理由（1句话）",
      "dialogue":"你说出的话+说话时的动作。含引号。如「'你还好吗？'她试探地开口，声音轻得像怕惊动什么。」。rest/explore时不填。",
      "prose":"该行动旁观者视角的描写（1-2句第三人称）。如'她走向窗边，指尖在结霜的玻璃上画了一个圆圈，呼出的白雾迅速消散在晨曦里。'——rest/explore/isolate也需写。",
      "internal":"你此刻内心真实的感受（1句话）。绝不会被其他角色知晓。如'其实她知道对方在撒谎，但她选择不说穿。'"
    }},
    {{"t":"类型或null","tid":"目标或null","loc":"地点或null","r":"理由","dialogue":"或null","prose":"或null","internal":"或null"}}
  ],
  "e":"本轮情绪"
}}
trap 额外加 "risk" 字段（无风险/低风险/中风险/高风险/极高风险）。
attack 需要周围无目击者，否则会被放弃。
如果你 socialize，dialogue 字段写你对目标说的第一句话 + 说话动作。

---
【当前回合】第{p.current_day}天 {p.current_time} · {p.current_location}
{prev_line}
{dia_line}
情绪：{p.emotional_state} | 威胁感：{p.threat_level:.1f}
好感：{aff_str}
附近角色：{', '.join(nearby_names) if nearby_names else '无人'}
房间物品：{item_desc}
{curse_line}

【你看到的】
{chr(10).join(p.visible_events) if p.visible_events else '没什么特别的事。'}
【你听到的对话】
{chr(10).join(p.visible_dialogues) if p.visible_dialogues else '没有听到对话'}"""

    def _allowed_intents(self, phase: GamePhase) -> list[str]:
        base = ["socialize", "explore", "rest", "confront", "isolate"]
        if phase in (GamePhase.UNDERCURRENT, GamePhase.HUNTING):
            base += ["stalk", "sabotage"]
        if phase == GamePhase.HUNTING:
            base += ["attack", "trap", "defend"]
        return base

    def dialogue(self, context: str, speaker_name: str, content: str, speaker_id: Optional[str] = None) -> str:
        """生成对话回应 — 用于 NPC 间对话或 NPC 对玩家的回应"""
        aff_context = ""
        if speaker_id:
            aff_val = self.state.affection_map.get(speaker_id, 50)
            aff_hint = _aff_hint(aff_val)
            aff_context = f"\n你对【{speaker_name}】的好感度为 {aff_val}（{aff_hint}）。"
            recent_entries = [e for e in self.state.affection_log if e.target_id == speaker_id]
            if recent_entries:
                reasons = "；".join(e.reason for e in recent_entries[-3:])
                aff_context += f"近期关系变化：{reasons}"
        prompt = f"""[当前场景]
{context}
{aff_context}

【{speaker_name} 对你说】
"{content}"

        你作为 {self.profile.name}，请用你的性格、情绪和说话方式直接回应。好感度影响语气态度——高好感温暖亲近，低好感冷淡疏远或暗含敌意。只用对话和行动描写，不要内心独白。50-100字。"""

        try:
            text = self._llm.chat(
                messages=[{"role": "user", "content": prompt}],
                system=self.profile.system_prompt,
                temperature=0.95,
                max_tokens=1024,
            )
        except Exception:
            text = ""

        # 剥离残留的内心独白标记
        import re
        text = re.sub(r'[「【]*（[^）]*）[」】]*', '', text).strip()
        text = re.sub(r'[「【][^」】]*[」】]', '', text).strip()

        if not text or len(text.strip()) < 5:
            text = "嗯...有什么事吗？"

        return text.strip()

    def update_affection(self, target_id: str, delta: int, reason: str = "", tick: int = 0):
        current = self.state.affection_map.get(target_id, 50)
        self.state.affection_map[target_id] = max(0, min(100, current + delta))
        if reason:
            entry = AffectionEntry(target_id=target_id, delta=delta, reason=reason, tick=tick)
            self.state.affection_log.append(entry)
            if len(self.state.affection_log) > 5:
                self.state.affection_log = self.state.affection_log[-5:]

    def update_threat(self, delta: float):
        self.state.threat_level = max(0.0, min(1.0, self.state.threat_level + delta))


@dataclass
class Perception:
    """Agent 的感知快照"""
    agent_id: str
    current_location: str
    current_time: str
    current_day: int
    game_phase: GamePhase
    nearby_npcs: list[str]
    visible_events: list[str]
    visible_dialogues: list[str] = field(default_factory=list)  # 听到的 NPC 间对话
    emotional_state: str = ""
    threat_level: float = 0.0
    affection_snapshot: dict[str, int] = field(default_factory=dict)
    previous_action: str = ""
    recent_dialogue: list = field(default_factory=list)


def _parse_intent_type(raw: str) -> IntentType:
    mapping = {
        "socialize": IntentType.SOCIALIZE, "social": IntentType.SOCIALIZE,
        "explore": IntentType.EXPLORE, "rest": IntentType.REST,
        "confront": IntentType.CONFRONT, "isolate": IntentType.ISOLATE,
        "stalk": IntentType.STALK, "sabotage": IntentType.SABOTAGE,
        "attack": IntentType.ATTACK, "trap": IntentType.TRAP, "defend": IntentType.DEFEND,
    }
    return mapping.get(raw, IntentType.REST)


def _aff_hint(v: int) -> str:
    if v >= 70: return "很亲近"
    if v >= 50: return "友善"
    if v >= 35: return "比较陌生"
    if v >= 20: return "冷淡"
    return "有敌意"
