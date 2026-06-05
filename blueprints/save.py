"""Save blueprint — 5 endpoints: auto-save, manual-save, load, list, delete."""
from flask import Blueprint, request, jsonify
import session as _sess
import scenarios
from .meta import _npc_info

save_bp = Blueprint('save', __name__)

@save_bp.route("/api/save", methods=["POST"])
def api_save():
    """手动存档：生成带时间戳的新文件。"""
    s = _sess.session
    fname = s.save_mgr.save(
        slot="manual",
        world=s.world, agent_states=s.agent_states,
        player_name=s.player_name, player_location=s.player_location,
        round_count=s.round_count, scene_id=s.scene_id,
        narrative_log=s.narrative_log,
        prologue_context=list(s.prologue._prologue_context),
        prologue_turn=s.prologue._prologue_turn,
        prologue_phase=s.prologue._prologue_phase,
        post_admin_explored=s.prologue._post_admin_explored,
        player_action_log=list(s.prologue._player_action_log),
        prologue_options=list(s.prologue._last_options),
        last_options=list(s.last_options) if getattr(s,'last_options',None) else [],
    )
    return jsonify({"ok": True, "filename": fname, "slots": s.save_mgr.list_slots()})

@save_bp.route("/api/save/auto", methods=["POST"])
def api_save_auto():
    """自动存档到 autosave.json。"""
    s = _sess.session
    s.save_mgr.save(
        slot="auto",
        world=s.world, agent_states=s.agent_states,
        player_name=s.player_name, player_location=s.player_location,
        round_count=s.round_count, scene_id=s.scene_id,
        narrative_log=s.narrative_log,
        prologue_context=list(s.prologue._prologue_context),
        prologue_turn=s.prologue._prologue_turn,
        prologue_phase=s.prologue._prologue_phase,
        post_admin_explored=s.prologue._post_admin_explored,
        player_action_log=list(s.prologue._player_action_log),
        prologue_options=list(s.prologue._last_options),
        last_options=list(s.last_options) if getattr(s,'last_options',None) else [],
    )
    return jsonify({"ok": True, "slots": s.save_mgr.list_slots()})

@save_bp.route("/api/load/<path:filename>", methods=["POST"])
def api_load(filename: str):
    data = _sess.session.save_mgr.load(filename)
    if not data:
        return jsonify({"ok": False, "error": "存档文件不存在"})

    # 如果存档场景与当前会话不同，先重建会话
    saved_scene = data.get("scene_id", "")
    if saved_scene and saved_scene != _sess.session.scene_id:
        if saved_scene not in {s["id"] for s in scenarios.list_scenarios()}:
            scenarios.load(saved_scene)
        with _sess._session_lock:
            _sess.session = _sess.GameSession(scene_id=saved_scene)

    s = _sess.session
    s.player_name, s.player_location, s.round_count, loaded_scene, act_log, s.last_options = s.save_mgr.apply_loaded_state(
        data, s.world, s.agents, s.agent_states)
    s.prologue._prologue_context = list(data.get("prologue_context", []))
    s.prologue._prologue_turn = data.get("prologue_turn", 0)
    s.prologue._prologue_phase = data.get("prologue_phase", "free")
    s.prologue._post_admin_explored = data.get("post_admin_explored", False)
    s.prologue._player_action_log = act_log
    s.prologue._last_options = list(data.get("prologue_options", []))
    s.player_created = True
    if "player" in s.agent_states:
        s.agent_states["player"].name = s.player_name
    if not s.world.room_item_state or all(not v for v in s.world.room_item_state.values()):
        s._init_room_items()
    return jsonify({
        "ok": True,
        "player_name": s.player_name,
        "scene_id": s.scene_id,
        "scene_name": s.scenario.get("name", s.scene_id) if s.scenario else s.scene_id,
        "day": s.world.current_day,
        "time": s.world.current_time,
        "location": s.player_location,
        "round": s.round_count,
        "prologue_step": s.world.prologue_step,
        "prologue_phase": s.prologue._prologue_phase,
        "prologue_options": s.prologue._last_options,
        "npcs": _npc_info(),
        "narrative_log": data.get("narrative_log", []),
        "options": s.last_options if getattr(s,'last_options',None) else [],
    })

@save_bp.route("/api/slots")
def api_slots():
    return jsonify({"slots": _sess.session.save_mgr.list_slots()})

@save_bp.route("/api/save/<filename>", methods=["DELETE"])
def api_delete_save(filename: str):
    return jsonify({"ok": _sess.session.save_mgr.delete(filename), "slots": _sess.session.save_mgr.list_slots()})

@save_bp.route("/api/new_game", methods=["POST"])
def api_new_game():
    sid = request.get_json().get("scene_id", "tianji_maze")
    with _sess._session_lock:
        _sess.session = _sess.GameSession(scene_id=sid)
    return jsonify({"ok": True, "scene_id": sid, "scene_name": _sess.session.scenario.get("name", sid) if _sess.session.scenario else sid})

@save_bp.route("/api/select_scene", methods=["POST"])
def api_select_scene():
    sid = request.get_json().get("scene_id", "tianji_maze")
    if sid not in {s["id"] for s in scenarios.list_scenarios()}:
        scenarios.load(sid)
    with _sess._session_lock:
        _sess.session = _sess.GameSession(scene_id=sid)
    return jsonify({"ok": True, "scene_id": sid, "scene_name": _sess.session.scenario.get("name", "")})
