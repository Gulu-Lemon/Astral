"""
核心数据结构 —— 涵盖难度模式、序章流程、审判系统、楼层控制
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from collections import namedtuple
import uuid
import random

# ====== 共享工具 ======

RISK_THRESHOLDS = {
    "不可能": [],
    "极高风险": [0],
    "高风险": [0, 1],
    "中风险": [0, 1, 2],
    "较低风险": [0, 1, 2, 3],
    "低风险": [0, 1, 2, 3, 4],
    "无风险": [0, 1, 2, 3, 4, 5],
}

def roll_risk(risk: str, rng=None) -> bool:
    """d6 随机掷骰。返回 True 表示成功。"""
    roll = (rng or random).randint(0, 5)
    return roll in RISK_THRESHOLDS.get(risk, [0, 1, 2])

DeadSentinel = namedtuple('DeadSentinel', ['alive'])
DEAD_NPC = DeadSentinel(alive=False)


class GamePhase(Enum):
    BLACKOUT = "blackout"
    UNDERCURRENT = "undercurrent"
    HUNTING = "hunting"


class DifficultyMode(Enum):
    STORY = "story"
    NORMAL = "normal"
    WITCH = "witch"


class IntentType(Enum):
    SOCIALIZE = "socialize"
    EXPLORE = "explore"
    REST = "rest"
    CONFRONT = "confront"
    ISOLATE = "isolate"
    STALK = "stalk"
    SABOTAGE = "sabotage"
    ATTACK = "attack"       # 直接攻击（需要无人目击或伪装）
    TRAP = "trap"           # 陷阱攻击（不要求无人目击）
    DEFEND = "defend"


# ====== 子数据结构 ======

@dataclass
class Evidence:
    evidence_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    location: str = ""
    description: str = ""
    points_to: list[str] = field(default_factory=list)
    reliability: str = "中等"
    discovered: bool = False

    def to_dict(self) -> dict:
        return {
            "evidence_id": self.evidence_id,
            "location": self.location,
            "description": self.description,
            "points_to": list(self.points_to),
            "reliability": self.reliability,
            "discovered": self.discovered,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Evidence":
        return cls(
            evidence_id=d.get("evidence_id", uuid.uuid4().hex[:8]),
            location=d.get("location", ""),
            description=d.get("description", ""),
            points_to=list(d.get("points_to", [])),
            reliability=d.get("reliability", "中等"),
            discovered=d.get("discovered", False),
        )


@dataclass
class Event:
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    tick: int = 0
    event_type: str = ""
    actor_id: str = ""
    target_id: str = ""
    victim_id: str = ""
    location: str = ""
    public_description: str = ""
    full_description: str = ""       # 含 dialogue+prose+reasoning 的完整描述
    dialogue_snapshot: str = ""      # Agent 台词原文
    full_reasoning: str = ""         # 完整动机推理（未截断）
    private_details: dict[str, str] = field(default_factory=dict)
    evidence_ids: list[str] = field(default_factory=list)
    witnesses: set[str] = field(default_factory=set)
    is_murder: bool = False

    @property
    def type(self) -> str:
        return self.event_type

    @type.setter
    def type(self, value: str):
        self.event_type = value

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "tick": self.tick,
            "type": self.event_type,
            "actor_id": self.actor_id,
            "target_id": self.target_id,
            "victim_id": self.victim_id,
            "location": self.location,
            "public_description": self.public_description,
            "full_description": self.full_description,
            "dialogue_snapshot": self.dialogue_snapshot,
            "full_reasoning": self.full_reasoning,
            "private_details": dict(self.private_details),
            "evidence_ids": list(self.evidence_ids),
            "witnesses": sorted(self.witnesses),
            "is_murder": self.is_murder,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Event":
        return cls(
            event_id=d.get("event_id", uuid.uuid4().hex[:12]),
            tick=d.get("tick", 0),
            event_type=d.get("type", ""),
            actor_id=d.get("actor_id", ""),
            target_id=d.get("target_id", ""),
            victim_id=d.get("victim_id", ""),
            location=d.get("location", ""),
            public_description=d.get("public_description", ""),
            full_description=d.get("full_description", ""),
            dialogue_snapshot=d.get("dialogue_snapshot", ""),
            full_reasoning=d.get("full_reasoning", ""),
            private_details=dict(d.get("private_details", {})),
            evidence_ids=list(d.get("evidence_ids", [])),
            witnesses=set(d.get("witnesses", [])),
            is_murder=d.get("is_murder", False),
        )


@dataclass
class Intent:
    agent_id: str
    intent_type: IntentType
    target_id: Optional[str] = None
    target_location: Optional[str] = None
    reasoning: str = ""
    risk: str = ""  # LLM 自评的陷阱风险（仅 TRAP 意图使用）
    scene_hint: str = ""  # NPC 叙事视角的 1 句话描写（微表情/小动作/神态）
    dialogue: str = ""  # 实际说出的话 + 说话动作（带引号）
    prose: str = ""  # 该行动的旁观者视角描写（1-2句，第三人称）
    internal: str = ""  # 内心真实感受（1句话，私密，存入 AgentState.private_motives）

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "intent_type": self.intent_type.value,
            "target_id": self.target_id,
            "target_location": self.target_location,
            "reasoning": self.reasoning,
            "risk": self.risk,
            "scene_hint": self.scene_hint,
            "dialogue": self.dialogue,
            "prose": self.prose,
            "internal": self.internal,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Intent":
        return cls(
            agent_id=d.get("agent_id", ""),
            intent_type=IntentType(d.get("intent_type", "rest")),
            target_id=d.get("target_id"),
            target_location=d.get("target_location"),
            reasoning=d.get("reasoning", ""),
            risk=d.get("risk", ""),
            scene_hint=d.get("scene_hint", ""),
            dialogue=d.get("dialogue", ""),
            prose=d.get("prose", ""),
            internal=d.get("internal", ""),
        )


@dataclass
class Ruling:
    intent: Intent
    approved: bool
    downgraded_to: Optional[IntentType] = None
    success: bool = True
    event_id: Optional[str] = None
    description: str = ""
    evidence_generated: list[Evidence] = field(default_factory=list)
    affected_agents: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "intent": self.intent.to_dict(),
            "approved": self.approved,
            "downgraded_to": self.downgraded_to.value if self.downgraded_to else None,
            "success": self.success,
            "event_id": self.event_id,
            "description": self.description,
            "evidence_generated": [e.to_dict() for e in self.evidence_generated],
            "affected_agents": list(self.affected_agents),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Ruling":
        return cls(
            intent=Intent.from_dict(d.get("intent", {})),
            approved=d.get("approved", True),
            downgraded_to=IntentType(d["downgraded_to"]) if d.get("downgraded_to") else None,
            success=d.get("success", True),
            event_id=d.get("event_id"),
            description=d.get("description", ""),
            evidence_generated=[Evidence.from_dict(e) for e in d.get("evidence_generated", [])],
            affected_agents=list(d.get("affected_agents", [])),
        )


@dataclass
class TrialState:
    active: bool = False
    phase: str = ""           # "investigation" | "court_statement" | "court_debate" | "closing" | "voting" | "execution"
    victim_id: str = ""
    case_evidence: list[Evidence] = field(default_factory=list)
    statements: list[dict] = field(default_factory=list)
    votes: dict[str, str] = field(default_factory=dict)
    defendant_id: Optional[str] = None
    executed_id: Optional[str] = None
    turn_count: int = 0
    player_has_argued: bool = False

    def to_dict(self) -> dict:
        return {
            "active": self.active,
            "phase": self.phase,
            "victim_id": self.victim_id,
            "case_evidence": [e.to_dict() for e in self.case_evidence],
            "statements": list(self.statements),
            "votes": dict(self.votes),
            "defendant_id": self.defendant_id,
            "executed_id": self.executed_id,
            "turn_count": self.turn_count,
            "player_has_argued": self.player_has_argued,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TrialState":
        return cls(
            active=d.get("active", False),
            phase=d.get("phase", ""),
            victim_id=d.get("victim_id", ""),
            case_evidence=[Evidence.from_dict(e) for e in d.get("case_evidence", [])],
            statements=list(d.get("statements", [])),
            votes=dict(d.get("votes", {})),
            defendant_id=d.get("defendant_id"),
            executed_id=d.get("executed_id"),
            turn_count=d.get("turn_count", 0),
            player_has_argued=d.get("player_has_argued", False),
        )


# ====== 尸体记录 ======

@dataclass
class BodyRecord:
    victim_id: str = ""
    actor_id: str = ""
    location: str = ""
    hiding_spot: str = ""
    tick: int = 0
    first_discoverer: Optional[str] = None
    discovered_by: list[str] = field(default_factory=list)
    broadcast: bool = False

    def to_dict(self) -> dict:
        return {"victim_id":self.victim_id,"actor_id":self.actor_id,"location":self.location,
                "hiding_spot":self.hiding_spot,"tick":self.tick,"first_discoverer":self.first_discoverer,
                "discovered_by":list(self.discovered_by),"broadcast":self.broadcast}

    @classmethod
    def from_dict(cls, d: dict) -> "BodyRecord":
        return cls(victim_id=d.get("victim_id",""),actor_id=d.get("actor_id",""),
                   location=d.get("location",""),hiding_spot=d.get("hiding_spot",""),
                   tick=d.get("tick",0),first_discoverer=d.get("first_discoverer"),
                   discovered_by=list(d.get("discovered_by",[])),broadcast=d.get("broadcast",False))


# ====== 主要状态 ======

@dataclass
class WorldState:
    current_day: int = 1
    current_time: str = "上午7点"
    current_floor: int = 1
    explored_rooms: set[str] = field(default_factory=set)
    npc_locations: dict[str, str] = field(default_factory=dict)
    public_events: list[Event] = field(default_factory=list)
    phase: GamePhase = GamePhase.BLACKOUT
    difficulty: DifficultyMode = DifficultyMode.NORMAL
    player_met_npcs: set[str] = field(default_factory=set)
    global_tick: int = 0
    discovered_bodies: list[str] = field(default_factory=list)
    active_trial: Optional[TrialState] = None
    prologue_step: int = 0
    floor_2_unlocked: bool = False
    floor_3_unlocked: bool = False
    world_revelation_phase: int = 1
    player_magic: str = "尚未觉醒"
    alive_npcs: set[str] = field(default_factory=lambda: {
        "No.01", "No.02", "No.03", "No.04", "No.05", "No.06",
        "No.07", "No.08", "No.09", "No.10", "No.11", "No.12"
    })
    # ====== 物品 & 世界状态持久化 ======
    player_inventory: list[str] = field(default_factory=list)
    room_item_state: dict[str, dict[str, str]] = field(default_factory=dict)
    knowledge_flags: set[str] = field(default_factory=set)
    # ====== 案件节奏控制 ======
    rounds_since_last_murder: int = 99
    first_murder_delayed: bool = True
    undiscovered_bodies: list[BodyRecord] = field(default_factory=list)
    cursed_npc: str = ""
    atmosphere: str = ""  # 本轮氛围上下文（由 GameSession 填充）
    last_narrative_summary: str = ""  # 上轮 GM 叙事摘要（注入 Agent 感知）

    def all_npcs_met(self) -> bool:
        return self.player_met_npcs >= {
            "No.01", "No.02", "No.03", "No.04", "No.05", "No.06",
            "No.07", "No.08", "No.09", "No.10", "No.11", "No.12"
        }

    def living_npcs(self) -> list[str]:
        return sorted(self.alive_npcs)

    def to_dict(self) -> dict:
        return {
            "current_day": self.current_day,
            "current_time": self.current_time,
            "current_floor": self.current_floor,
            "explored_rooms": sorted(self.explored_rooms),
            "npc_locations": dict(self.npc_locations),
            "public_events": [e.to_dict() for e in self.public_events],
            "phase": self.phase.value,
            "difficulty": self.difficulty.value,
            "player_met_npcs": sorted(self.player_met_npcs),
            "global_tick": self.global_tick,
            "discovered_bodies": list(self.discovered_bodies),
            "active_trial": self.active_trial.to_dict() if self.active_trial else None,
            "prologue_step": self.prologue_step,
            "floor_2_unlocked": self.floor_2_unlocked,
            "floor_3_unlocked": self.floor_3_unlocked,
            "world_revelation_phase": self.world_revelation_phase,
            "player_magic": self.player_magic,
            "alive_npcs": sorted(self.alive_npcs),
            "player_inventory": list(self.player_inventory),
            "room_item_state": dict(self.room_item_state),
            "knowledge_flags": sorted(self.knowledge_flags),
            "rounds_since_last_murder": self.rounds_since_last_murder,
            "first_murder_delayed": self.first_murder_delayed,
            "undiscovered_bodies": [b.to_dict() for b in self.undiscovered_bodies],
            "cursed_npc": self.cursed_npc,
            "atmosphere": self.atmosphere,
            "last_narrative_summary": self.last_narrative_summary,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "WorldState":
        return cls(
            current_day=d.get("current_day", 1),
            current_time=d.get("current_time", "上午7点"),
            current_floor=d.get("current_floor", 1),
            explored_rooms=set(d.get("explored_rooms", [])),
            npc_locations=dict(d.get("npc_locations", {})),
            public_events=[Event.from_dict(e) for e in d.get("public_events", [])],
            phase=GamePhase(d.get("phase", "blackout")),
            difficulty=DifficultyMode(d.get("difficulty", "normal")),
            player_met_npcs=set(d.get("player_met_npcs", [])),
            global_tick=d.get("global_tick", 0),
            discovered_bodies=list(d.get("discovered_bodies", [])),
            active_trial=TrialState.from_dict(d["active_trial"]) if d.get("active_trial") else None,
            prologue_step=d.get("prologue_step", 0),
            floor_2_unlocked=d.get("floor_2_unlocked", False),
            floor_3_unlocked=d.get("floor_3_unlocked", False),
            world_revelation_phase=d.get("world_revelation_phase", 1),
            player_magic=d.get("player_magic", "尚未觉醒"),
            alive_npcs=set(d.get("alive_npcs", [
                "No.01", "No.02", "No.03", "No.04", "No.05", "No.06",
                "No.07", "No.08", "No.09", "No.10", "No.11", "No.12"
            ])),
            player_inventory=list(d.get("player_inventory", [])),
            room_item_state=dict(d.get("room_item_state", {})),
            knowledge_flags=set(d.get("knowledge_flags", [])),
            rounds_since_last_murder=d.get("rounds_since_last_murder", 99),
            first_murder_delayed=d.get("first_murder_delayed", True),
            undiscovered_bodies=[BodyRecord.from_dict(b) if isinstance(b, dict) else b for b in d.get("undiscovered_bodies", [])],
            cursed_npc=d.get("cursed_npc", ""),
            atmosphere=d.get("atmosphere", ""),
            last_narrative_summary=d.get("last_narrative_summary", ""),
        )


@dataclass
class AffectionEntry:
    target_id: str
    delta: int
    reason: str
    tick: int = 0

    def to_dict(self) -> dict:
        return {"target_id": self.target_id, "delta": self.delta, "reason": self.reason, "tick": self.tick}

    @classmethod
    def from_dict(cls, d: dict) -> "AffectionEntry":
        return cls(target_id=d.get("target_id", ""), delta=d.get("delta", 0), reason=d.get("reason", ""), tick=d.get("tick", 0))


@dataclass
class AgentState:
    agent_id: str
    name: str
    affection_map: dict[str, int] = field(default_factory=dict)
    affection_log: list[AffectionEntry] = field(default_factory=list)
    threat_level: float = 0.0
    known_secrets: set[str] = field(default_factory=set)
    witnessed_events: list[str] = field(default_factory=list)
    emotional_state: str = "平静"
    private_motives: list[str] = field(default_factory=list)
    action_log: list[dict] = field(default_factory=list)
    suspicion_map: dict[str, float] = field(default_factory=dict)
    alive: bool = True

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "affection_map": dict(self.affection_map),
            "affection_log": [e.to_dict() for e in self.affection_log],
            "threat_level": self.threat_level,
            "known_secrets": sorted(self.known_secrets),
            "witnessed_events": list(self.witnessed_events),
            "emotional_state": self.emotional_state,
            "private_motives": list(self.private_motives),
            "action_log": list(self.action_log),
            "suspicion_map": dict(self.suspicion_map),
            "alive": self.alive,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "AgentState":
        return cls(
            agent_id=d.get("agent_id", ""),
            name=d.get("name", ""),
            affection_map=dict(d.get("affection_map", {})),
            affection_log=[AffectionEntry.from_dict(e) for e in d.get("affection_log", [])],
            threat_level=d.get("threat_level", 0.0),
            known_secrets=set(d.get("known_secrets", [])),
            witnessed_events=list(d.get("witnessed_events", [])),
            emotional_state=d.get("emotional_state", "平静"),
            private_motives=list(d.get("private_motives", [])),
            action_log=list(d.get("action_log", [])),
            suspicion_map=dict(d.get("suspicion_map", {})),
            alive=d.get("alive", True),
        )
