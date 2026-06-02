"""Trial blueprint — trial + evidence endpoints."""
import json
from flask import Blueprint, request, jsonify, Response, stream_with_context
import session as _sess

trial_bp = Blueprint('trial', __name__, url_prefix='/api/trial')

@trial_bp.route("/investigate", methods=["POST"])
def api_trial_investigate():
    return jsonify({"ok":True,"description":_sess.session.trial_investigate(request.get_json().get("action","查看现场"))})

@trial_bp.route("/proceed", methods=["POST"])
def api_trial_proceed():
    trial = _sess.session.world.active_trial
    if not trial or not trial.active:
        return jsonify({"ok":False,"error":"没有审判","phase":""})
    trial.turn_count += 1
    if trial.phase == "investigation":
        trial.phase = "court_statement"
        # 生成陈述
        result = _sess.session.generate_statement()
        return jsonify(result)
    elif trial.phase == "court_statement":
        trial.phase = "court_debate"
        trial.timer_elapsed = 0
        return jsonify({"ok":True,"phase":"court_debate",
                        "text":"辩论阶段开始。各抒己见，找出真相。",
                        "stream_url":"/api/trial/debate_stream"})
    elif trial.phase == "court_debate":
        # 强制进入投票（辩论结束）
        votes = _sess.session._trial_vote()
        trial.votes = votes
        from collections import Counter
        counts = Counter(votes.values())
        if counts:
            max_votes_ = max(counts.values())
            tied = [pid for pid,c in counts.items() if c == max_votes_]
            import random
            trial.defendant_id = random.choice(tied) if len(tied) > 1 else tied[0]
        trial.phase = "execution"
        return jsonify({"ok":True,"phase":"execution",
                        "text":_sess.session._trial_execution(),
                        "votes":trial.votes,"defendant":trial.defendant_id})
    return jsonify({"ok":False,"error":"未知阶段","phase":trial.phase})

@trial_bp.route("/debate_stream")
def api_debate_stream():
    def generate():
        for event in _sess.session.stream_debate():
            yield event
        yield "event: _done_\ndata: {}\n\n"
    return Response(stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})

@trial_bp.route("/debate_option", methods=["POST"])
def api_debate_option():
    choice = request.get_json() or {}
    result = _sess.session.process_debate_option(choice)
    return jsonify(result)

@trial_bp.route("/argue", methods=["POST"])
def api_trial_argue():
    trial = _sess.session.world.active_trial
    if trial: trial.statements.append({"role":"player","content":request.get_json().get("argument",""),"type":"closing"})
    return jsonify({"ok":True})

@trial_bp.route("/state")
def api_trial_state():
    trial = _sess.session.world.active_trial
    if not trial: return jsonify({"active":False,"phase":"","timer_remaining":0})
    remaining = 0
    if trial.phase == "investigation":
        remaining = max(0, 60 - trial.timer_elapsed)
    elif trial.phase == "court_debate":
        remaining = max(0, 60 - trial.timer_elapsed)
    return jsonify({
        "active":trial.active,"phase":trial.phase,
        "victim_id":trial.victim_id,
        "victim_name":_sess.session.agent_states[trial.victim_id].name if trial.victim_id in _sess.session.agent_states else "未知",
        "turn_count":trial.turn_count,
        "timer_remaining":remaining,
        "evidence_count":len(trial.case_evidence_items),
    })

# Evidence (证物) endpoints
@trial_bp.route("/evidence")
def api_evidence_list():
    trial = _sess.session.world.active_trial
    if not trial: return jsonify({"evidence": []})
    items = [e.to_dict() for e in trial.case_evidence_items]
    return jsonify({"evidence": items, "count": len(items)})

@trial_bp.route("/evidence/add", methods=["POST"])
def api_evidence_add():
    d = request.get_json() or {}
    item_desc = d.get("item", d.get("name", "")).strip()
    if not item_desc:
        return jsonify({"ok": False, "error": "请描述要添加的证物。"})
    result = _sess.session.add_evidence(item_desc)
    return jsonify(result)
