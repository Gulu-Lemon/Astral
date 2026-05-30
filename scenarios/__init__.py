"""
场景注册与加载器
"""
from __future__ import annotations
from typing import Optional

_registry: dict[str, dict] = {}


def add_module(module, scene_id: str = ""):
    """注册一个场景模块"""
    sid = scene_id or getattr(module, "SCENE_ID", "")
    if not sid:
        sid = getattr(module, "SCENE_NAME", "unknown")
    _registry[sid] = {
        "id": sid,
        "name": getattr(module, "SCENE_NAME", sid),
        "gm_name": getattr(module, "GM_NAME", "GM"),
        "gm_prompt": getattr(module, "GM_SYSTEM_PROMPT", ""),
        "characters": getattr(module, "CHARACTERS", {}),
        "room_features": getattr(module, "ROOM_FEATURES", {}),
        "floor_rooms": getattr(module, "FLOOR_ROOMS", {}),
        "floor_transitions": getattr(module, "FLOOR_TRANSITIONS", {}),
        "prologue_mirror": getattr(module, "PROLOGUE_MIRROR", ""),
        "prologue_magic": getattr(module, "PROLOGUE_MAGIC", ""),
        "prologue_difficulty": getattr(module, "PROLOGUE_DIFFICULTY", ""),
        "prologue_camp": getattr(module, "PROLOGUE_CAMP", ""),
        "prologue_explore": getattr(module, "PROLOGUE_EXPLORE", ""),
        "prologue_admin": getattr(module, "PROLOGUE_ADMIN", ""),
        "rule_text": getattr(module, "RULE_TEXT", ""),
        "trial_rules": getattr(module, "TRIAL_RULES", ""),
        "event_times": getattr(module, "EVENT_TIMES", []),
        "start_room": getattr(module, "START_ROOM", ""),
        "npc_ids": getattr(module, "NPC_IDS", [f"No.{i:02d}" for i in range(1, 13)]),
        "scene_desc": getattr(module, "SCENE_DESC", ""),
        "scene_tone": getattr(module, "SCENE_TONE", ""),
        "prologue_start_1": getattr(module, "PROLOGUE_START_1", ""),
    }
    return _registry[sid]


def list_scenarios() -> list[dict]:
    return [
        {"id": sid, "name": info["name"], "desc": info.get("scene_desc", "")}
        for sid, info in _registry.items()
    ]


def get(scene_id: str = "") -> Optional[dict]:
    if scene_id not in _registry:
        # 尝试动态加载
        try:
            import importlib
            mod = importlib.import_module(f"scenarios.{scene_id}")
            if hasattr(mod, "SCENE_NAME"):
                add_module(mod, scene_id)
        except ImportError:
            pass
    return _registry.get(scene_id)


def load(sid: str = ""):
    """显式加载一个场景（供启动时调用）"""
    return get(sid)
