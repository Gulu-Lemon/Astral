"""Save blueprint — 5 endpoints: save, load, slots, new_game, select_scene."""
from flask import Blueprint, request, jsonify
import session as _sess
import scenarios
from .meta import _npc_info

save_bp = Blueprint('save', __name__)

@save_bp.route("/api/save/<slot>", methods=["POST"])
def api_save(slot):
    if slot == "auto": pass
    else:
        try: slot = int(slot); assert 1 <= slot <= 6
        except: return jsonify({"ok":False,"error":"槽位 1-6 或 auto"})
    _sess.session.save_mgr.save(slot=slot, world=_sess.session.world, agent_states=_sess.session.agent_states, player_name=_sess.session.player_name, player_location=_sess.session.player_location, round_count=_sess.session.round_count, narrative_log=_sess.session.narrative_log, prologue_context=list(_sess.session._prologue_context), prologue_turn=_sess.session._prologue_turn, post_admin_explored=_sess.session._post_admin_explored, player_action_log=list(_sess.session._player_action_log))
    return jsonify({"ok":True,"slots":_sess.session.save_mgr.list_slots()})

@save_bp.route("/api/load/<slot>", methods=["POST"])
def api_load(slot):
    if slot != "auto":
        try: slot = int(slot)
        except: return jsonify({"ok":False,"error":"无效槽位"})
    data = _sess.session.save_mgr.load(slot)
    if not data: return jsonify({"ok":False,"error":"槽位无存档"})
    _sess.session.player_name, _sess.session.player_location, _sess.session.round_count, action_log = _sess.session.save_mgr.apply_loaded_state(data, _sess.session.world, _sess.session.agents, _sess.session.agent_states)
    _sess.session._prologue_context = list(data.get("prologue_context", []))
    _sess.session._prologue_turn = data.get("prologue_turn", 0)
    _sess.session._post_admin_explored = data.get("post_admin_explored", False)
    _sess.session._player_action_log = action_log
    _sess.session.player_created = True; _sess.session.agent_states["player"].name = _sess.session.player_name
    if not _sess.session.world.room_item_state or all(not v for v in _sess.session.world.room_item_state.values()): _sess.session._init_room_items()
    return jsonify({"ok":True,"player_name":_sess.session.player_name,"day":_sess.session.world.current_day,"time":_sess.session.world.current_time,"location":_sess.session.player_location,"round":_sess.session.round_count,"npcs":_npc_info(),"narrative_log":data.get("narrative_log",[])})

@save_bp.route("/api/slots")
def api_slots(): return jsonify({"slots":_sess.session.save_mgr.list_slots()})

@save_bp.route("/api/new_game", methods=["POST"])
def api_new_game():
    sid = request.get_json().get("scene_id","tianji_maze")
    with _sess._session_lock:
        _sess.session = _sess.GameSession(scene_id=sid)
    return jsonify({"ok":True,"scene_id":sid,"scene_name":_sess.session.scenario.get("name",sid) if _sess.session.scenario else sid})

@save_bp.route("/api/select_scene", methods=["POST"])
def api_select_scene():
    sid = request.get_json().get("scene_id","tianji_maze")
    if sid not in {s["id"] for s in scenarios.list_scenarios()}: scenarios.load(sid)
    with _sess._session_lock:
        _sess.session = _sess.GameSession(scene_id=sid)
    return jsonify({"ok":True,"scene_id":sid,"scene_name":_sess.session.scenario.get("name","")})
