"""
存档管理 — 自动存档 + 不限量手动槽位（文件名含时间戳）
"""
from __future__ import annotations
import json
import os
import time
from datetime import datetime
from typing import Optional, Union

from state import WorldState, AgentState, Event, GamePhase, DifficultyMode, TrialState, BodyRecord

SAVES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "saves")


def _safe_scene_label(scene_id: str) -> str:
    m = {"tianji_maze": "maze", "cloud_holiday": "hotel", "snow_train": "train"}
    return m.get(scene_id, scene_id[:8])


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
        scene_id: str = "",
        description: str = "",
        narrative_log: list = None,
        prologue_context: list = None,
        prologue_turn: int = 0,
        post_admin_explored: bool = False,
        player_action_log: list = None,
        last_options: list = None,
    ) -> str:
        """保存存档。slot="auto" → autosave.json；否则用 _next_filename() 生成新文件名。返回文件名。"""
        data = {
            "version": 2,
            "scene_id": scene_id,
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
            "last_options": last_options or [],
        }
        if slot == "auto":
            fname = "autosave.json"
        else:
            fname = self._next_filename(data)
        path = os.path.join(SAVES_DIR, fname)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return fname

    def _next_filename(self, data: dict) -> str:
        ts = datetime.now().strftime("%y%m%d_%H%M")
        sc = _safe_scene_label(data.get("scene_id", ""))
        day = data.get("world", {}).get("current_day", 1)
        base = f"{ts}_{sc}_{day}d"
        fname = f"{base}.json"
        counter = 1
        while os.path.exists(os.path.join(SAVES_DIR, fname)):
            fname = f"{base}_{counter}.json"
            counter += 1
        return fname

    def load(self, filename: str) -> Optional[dict]:
        """按文件名加载存档，返回解析后的 JSON dict。兼容 v1 和 v2 格式。"""
        path = os.path.join(SAVES_DIR, filename)
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def delete(self, filename: str) -> bool:
        path = os.path.join(SAVES_DIR, filename)
        if "autosave" in filename:
            return False  # 不删除自动存档
        if not os.path.exists(path):
            return False
        os.remove(path)
        return True

    def list_slots(self) -> list[dict]:
        """列出所有存档文件及其元数据。"""
        slots = []
        for fname in sorted(os.listdir(SAVES_DIR)):
            if not fname.endswith(".json"):
                continue
            path = os.path.join(SAVES_DIR, fname)
            try:
                mtime = os.path.getmtime(path)
                fsize = os.path.getsize(path)
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                is_auto = (fname == "autosave.json")
                slots.append({
                    "filename": fname,
                    "auto": is_auto,
                    "scene_id": data.get("scene_id", ""),
                    "player_name": data.get("player_name", ""),
                    "description": data.get("description", ""),
                    "timestamp": data.get("timestamp", ""),
                    "round_count": data.get("round_count", 0),
                    "alive_count": len(data.get("world", {}).get("alive_npcs", data.get("world", {}).get("alive_npcs", []))),
                    "total_npc": len(data.get("agent_states", {})),
                    "mtime": mtime,
                    "fsize": fsize,
                })
            except Exception:
                pass
        # auto 排第一，其余按 mtime 倒序
        slots.sort(key=lambda s: (not s["auto"], -s.get("mtime", 0)))
        return slots

    def apply_loaded_state(
        self, data: dict, world: WorldState,
        agents: dict, agent_states: dict[str, AgentState],
    ) -> tuple[str, str, int, str, list, list]:
        """将 JSON data 恢复到运行时对象。返回 (player_name, player_location, round_count, scene_id, player_action_log, last_options)。"""
        wd = data["world"]
        world.current_day = wd.get("current_day", 1)
        world.current_time = wd.get("current_time", "上午7点")
        world.time_minutes = wd.get("time_minutes", 420)
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
        world.undiscovered_bodies = [BodyRecord.from_dict(b) if isinstance(b, dict) else b for b in wd.get("undiscovered_bodies", [])]
        world.cursed_npc = wd.get("cursed_npc", "")
        world.atmosphere = wd.get("atmosphere", "")
        world.last_narrative_summary = wd.get("last_narrative_summary", "")
        world.ending_triggered = wd.get("ending_triggered", False)
        world.ending_chosen = wd.get("ending_chosen", "")
        world.ending_resolved = wd.get("ending_resolved", False)
        world.player_is_murderer = wd.get("player_is_murderer", False)
        trial_data = wd.get("active_trial")
        if trial_data:
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
        scene_id = data.get("scene_id", "")
        player_action_log = list(data.get("player_action_log", []))
        last_options = list(data.get("last_options", []))
        return player_name, player_location, round_count, scene_id, player_action_log, last_options
