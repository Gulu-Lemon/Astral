"""Prologue blueprint — 6 endpoints."""
from flask import Blueprint, request, jsonify
import session as _sess

prologue_bp = Blueprint('prologue', __name__, url_prefix='/api/prologue')

@prologue_bp.route("/mirror", methods=["POST"])
def api_mirror():
    d = request.get_json()
    return jsonify({"ok":True,"step":1,"text":_sess.session.prologue_step_1_mirror(d.get("name","无名"), d.get("age","16"), d.get("appearance","普通少女"))})

@prologue_bp.route("/magic", methods=["POST"])
def api_magic():
    return jsonify({"ok":True,"step":2,"text":_sess.session.prologue_step_2_magic(request.get_json().get("magic","尚未觉醒"))})

@prologue_bp.route("/difficulty", methods=["POST"])
def api_difficulty():
    return jsonify({"ok":True,"step":3,"text":_sess.session.prologue_step_3_difficulty(request.get_json().get("mode","B"))})

@prologue_bp.route("/camp", methods=["GET"])
def api_camp():
    result = _sess.session.prologue_step_4_camp()
    return jsonify({"ok":True,"step":4,"text":result["text"] if isinstance(result,dict) else result,"options":result.get("options",[]) if isinstance(result,dict) else []})

@prologue_bp.route("/continue", methods=["POST"])
def api_prologue_continue():
    result = _sess.session.prologue_continue(request.get_json().get("choice","").strip())
    if result is None:
        return jsonify({"ok":False,"error":"序章推进失败：内部状态异常，请尝试重新开始游戏。"})
    return jsonify({"ok":True,"text":result["text"],"options":result["options"],"step":result["step"],"finished":result.get("finished",False),"rule":result.get("rule","")})

@prologue_bp.route("/finish", methods=["POST"])
def api_finish():
    _sess.session.prologue_finish()
    return jsonify({"ok":True,"step":7,"text":"序章结束。"})
