"""Trial blueprint — 4 endpoints."""
from flask import Blueprint, request, jsonify
import session as _sess

trial_bp = Blueprint('trial', __name__, url_prefix='/api/trial')

@trial_bp.route("/investigate", methods=["POST"])
def api_trial_investigate():
    return jsonify({"ok":True,"description":_sess.session.trial_investigate(request.get_json().get("action","查看现场"))})

@trial_bp.route("/proceed", methods=["POST"])
def api_trial_proceed(): return jsonify(_sess.session.trial_proceed())

@trial_bp.route("/argue", methods=["POST"])
def api_trial_argue():
    trial = _sess.session.world.active_trial
    if trial: trial.statements.append({"role":"player","content":request.get_json().get("argument",""),"type":"closing"}); trial.player_has_argued = True
    return jsonify({"ok":True})

@trial_bp.route("/state")
def api_trial_state():
    trial = _sess.session.world.active_trial
    if not trial: return jsonify({"active":False})
    return jsonify({"active":trial.active,"phase":trial.phase,"victim_id":trial.victim_id,"victim_name":_sess.session.agent_states[trial.victim_id].name if trial.victim_id in _sess.session.agent_states else "未知","turn_count":trial.turn_count})
