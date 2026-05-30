"""Settings blueprint — 6 endpoints (profiles, test_connection, shutdown)."""
from flask import Blueprint, request, jsonify
import time
import session as _sess
from config_profiles import (list_profiles as _lcp, save_profile as _scp, activate as _acp,
                             delete_profile as _dcp, get_active as _gac,
                             apply_to_all_llms as _aal)

settings_bp = Blueprint('settings', __name__)

@settings_bp.route("/api/profiles")
def api_profiles(): return jsonify({"profiles":_lcp(),"active":_gac().get("name","")})

@settings_bp.route("/api/profiles", methods=["POST"])
def api_save_profile():
    d = request.get_json(); name = d.get("name","").strip()
    if not name: return jsonify({"ok":False,"error":"配置名不能为空"})
    _scp(name, d.get("base_url",""), d.get("api_key",""), d.get("model",""),
         d.get("temperature", 1.0), d.get("top_p", 0.95),
         d.get("agent_model",""), d.get("arbiter_model",""), d.get("gm_model",""))
    return jsonify({"ok":True,"profiles":_lcp()})

@settings_bp.route("/api/profiles/activate", methods=["POST"])
def api_activate_profile():
    name = request.get_json().get("name","").strip()
    if not name or not _acp(name): return jsonify({"ok":False,"error":"配置不存在"})
    _aal(_sess.session.llm, _sess.session.agent_llm, _sess.session.gm_llm)
    _sess.session._sync_arbiter_llm()
    return jsonify({"ok":True,"active":name})

@settings_bp.route("/api/profiles/delete", methods=["POST"])
def api_delete_profile():
    _dcp(request.get_json().get("name","").strip())
    if _gac():
        _aal(_sess.session.llm, _sess.session.agent_llm, _sess.session.gm_llm)
        _sess.session._sync_arbiter_llm()
    return jsonify({"ok":True,"profiles":_lcp()})

@settings_bp.route("/api/test_connection")
def api_test_connection():
    bu = _sess.session.llm.base_url.strip()
    if not bu: return jsonify({"ok":False,"error":"接口地址为空。","base_url":""})
    if not _sess.session.llm.api_key or not _sess.session.llm.api_key.strip(): return jsonify({"ok":False,"error":"API Key 为空。","base_url":bu})
    try:
        start = time.time()
        resp = _sess.session.llm.chat(messages=[{"role":"user","content":"回复一个词：连通"}], temperature=0.1, max_tokens=16)
        return jsonify({"ok":True,"model":_sess.session.llm.model,"latency_ms":round((time.time()-start)*1000),"response":resp[:50]})
    except Exception as e: return jsonify({"ok":False,"error":str(e)[:300],"base_url":bu})

@settings_bp.route("/api/shutdown")
def api_shutdown():
    import os as _os; _os._exit(0)
