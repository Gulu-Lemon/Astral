"""
存档管理 — 自动存档 + 6个手動槽位
"""
from __future__ import annotations
import json
import os
from datetime import datetime
from typing import Optional, Union

from state import WorldState, AgentState

SAVES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "saves")


class SaveManager:
    def __init__(self):
        os.makedirs(SAVES_DIR, exist_ok=True)

    def save(
        self,
        slot: Union[int, str],
        world: WorldState,
        agent_states: dict[str, AgentState],
        player_name: str,
        player_location: str,
        round_count: int,
        description: str = "",
        narrative_log: list = None,
        prologue_context: list = None,
        prologue_turn: int = 0,
        post_admin_explored: bool = False,
        player_action_log: list = None,
    ):
        data = {
            "version": 1,
            "timestamp": datetime.now().isoformat(),
            "player_name": player_name,
            "player_location": player_location,
            "round_count": round_count,
            "description": description or f"第{world.current_day}天 {world.current_time} - {player_location}",
            "world": world.to_dict(),
            "agent_states": {aid: st.to_dict() for aid, st in agent_states.items()},
            "narrative_log": narrative_log or [],
            "prologue_context": prologue_context or [],
            "prologue_turn": prologue_turn,
            "post_admin_explored": post_admin_explored,
            "player_action_log": player_action_log or [],
        }
        path = self._slot_path(slot)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load(self, slot: Union[int, str]) -> Optional[dict]:
        path = self._slot_path(slot)
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def list_slots(self) -> list[dict]:
        slots = []
        # auto
        auto = self._read_meta("auto")
        if auto:
            auto["slot"] = "auto"
            auto["label"] = "自动存档"
            slots.append(auto)
        # 1-6
        for slot in range(1, 7):
            meta = self._read_meta(slot)
            if meta:
                meta["slot"] = slot
                meta["label"] = f"槽位 {slot}"
                slots.append(meta)
        return slots

    def _read_meta(self, slot: Union[int, str]) -> Optional[dict]:
        path = self._slot_path(slot)
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {
                "description": data.get("description", ""),
                "timestamp": data.get("timestamp", ""),
                "round_count": data.get("round_count", 0),
            }
        except Exception:
            return None

    def apply_loaded_state(
        self, data: dict, world: WorldState,
        agents: dict, agent_states: dict[str, AgentState],
    ) -> tuple[str, str, int, list]:
        wd = data["world"]
        world.current_day = wd.get("current_day", 1)
        world.current_time = wd.get("current_time", "上午7点")
        world.current_floor = wd.get("current_floor", 1)
        world.explored_rooms = set(wd.get("explored_rooms", []))
        world.npc_locations = dict(wd.get("npc_locations", {}))
        world.public_events = [Event.from_dict(e) for e in wd.get("public_events", [])]
        world.phase = GamePhase(wd.get("phase", "blackout"))
        world.difficulty = DifficultyMode(wd.get("difficulty", "normal"))
        world.player_met_npcs = set(wd.get("player_met_npcs", []))
        world.global_tick = wd.get("global_tick", 0)
        world.discovered_bodies = list(wd.get("discovered_bodies", []))
        world.player_inventory = list(wd.get("player_inventory", []))
        world.room_item_state = dict(wd.get("room_item_state", {}))
        world.knowledge_flags = set(wd.get("knowledge_flags", []))
        world.rounds_since_last_murder = wd.get("rounds_since_last_murder", 99)
        world.first_murder_delayed = wd.get("first_murder_delayed", True)
        world.prologue_step = wd.get("prologue_step", 7)
        world.floor_2_unlocked = wd.get("floor_2_unlocked", False)
        world.floor_3_unlocked = wd.get("floor_3_unlocked", False)
        world.world_revelation_phase = wd.get("world_revelation_phase", 1)
        world.player_magic = wd.get("player_magic", "")
        world.alive_npcs = set(wd.get("alive_npcs", []))
        world.undiscovered_bodies = list(wd.get("undiscovered_bodies", []))
        world.cursed_npc = wd.get("cursed_npc", "")
        world.atmosphere = wd.get("atmosphere", "")
        world.last_narrative_summary = wd.get("last_narrative_summary", "")
        # 恢复审判状态
        trial_data = wd.get("active_trial")
        if trial_data:
            from state import TrialState
            world.active_trial = TrialState.from_dict(trial_data)
        else:
            world.active_trial = None

        for aid, ad in data.get("agent_states", {}).items():
            st = AgentState.from_dict(ad)
            agent_states[aid] = st
            if aid in agents:
                agents[aid].state = st

        player_name = data.get("player_name", "")
        player_location = data.get("player_location", "")
        round_count = data.get("round_count", 0)
        player_action_log = list(data.get("player_action_log", data.get("prologue_story_beats", [])))
        return player_name, player_location, round_count, player_action_log

    @staticmethod
    def _slot_path(slot: Union[int, str]) -> str:
        if slot == "auto":
            return os.path.join(SAVES_DIR, "autosave.json")
        return os.path.join(SAVES_DIR, f"slot_{slot}.json")
