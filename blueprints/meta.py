"""Meta blueprint — 7 endpoints: scenes, cards, start_with_card, meta, free_narrative, state, index."""
from flask import Blueprint, request, jsonify, Response, send_from_directory, stream_with_context
import json, time, threading
import session as _sess
from card_manager import list_cards, save_card, delete_card, get_card, get_cards_mtime
import scenarios

meta_bp = Blueprint('meta', __name__)

def _map_data():
    fr = _sess.session.scenario.get("floor_rooms", {}) if _sess.session.scenario else {}
    ft = _sess.session.scenario.get("floor_transitions", {}) if _sess.session.scenario else {}
    expl = _sess.session.world.explored_rooms
    cars = []
    for floor_num in sorted(fr.keys()):
        rooms = fr[floor_num]
        explored = [r for r in rooms if r in expl]
        has_player = _sess.session.world.current_floor == floor_num
        locked = False
        if floor_num == 2 and not _sess.session.world.floor_2_unlocked:
            locked = True
        elif floor_num == 3 and not _sess.session.world.floor_3_unlocked:
            locked = True
        cars.append({
            "floor": floor_num,
            "rooms": rooms,
            "explored": explored,
            "has_player": has_player,
            "locked": locked,
        })
    transitions = []
    for room, t in ft.items():
        transitions.append({
            "from_floor": t.get("from_floor", 0),
            "to_floor": t.get("to_floor", 0),
            "via_room": room,
        })
    return {
        "cars": cars,
        "transitions": transitions,
        "player_room": _sess.session.player_location,
    }

def _npc_info():
    npcs = []; pl = _sess.session.player_location
    for aid in sorted(_sess.session.agents.keys()):
        a = _sess.session.agents[aid]; st = a.state
        if not st.alive: continue
        nl = _sess.session.world.npc_locations.get(aid,""); nearby = nl == pl; met = aid in _sess.session.world.player_met_npcs
        npcs.append({"agent_id":aid,"name":a.profile.name if met else "？","age":a.profile.age if met else 0,"affection":st.affection_map.get("player",50),"threat":50 if nearby else 0,"location":nl if nearby else "（不在视野内）","nearby":nearby})
    return npcs

@meta_bp.route("/")
def index(): return send_from_directory("static","index.html")

@meta_bp.route("/api/state")
def get_state():
    s = _sess.session.scenario if _sess.session.scenario else {}
    return jsonify({"player_name":_sess.session.player_name,"player_created":_sess.session.player_created,"scene_id":_sess.session.scene_id,"scene_name":s.get("name",""),"prologue_step":_sess.session.world.prologue_step,"day":_sess.session.world.current_day,"time":_sess.session.world.current_time,"floor":_sess.session.world.current_floor,"phase":_sess.session.world.phase.value,"difficulty":_sess.session.world.difficulty.value,"location":_sess.session.player_location,"round":_sess.session.round_count,"npcs":_npc_info(),"alive_count":len(_sess.session.world.alive_npcs),"in_trial":bool(_sess.session.world.active_trial and _sess.session.world.active_trial.active),"trial_phase":_sess.session.world.active_trial.phase if _sess.session.world.active_trial else "","trial_victim":_sess.session.world.active_trial.victim_id if _sess.session.world.active_trial else "","slots":_sess.session.save_mgr.list_slots(),"inventory":list(_sess.session.world.player_inventory),"room_items":_sess.session.world.room_item_state.get(_sess.session.player_location,{}),"knowledge_flags":sorted(_sess.session.world.knowledge_flags),"cards":list_cards(),"rule_text":s.get("rule_text",""),"trial_rules":s.get("trial_rules",""),"event_times":s.get("event_times",[]) if s else [],"map_data":_map_data()})

@meta_bp.route("/api/scenes")
def api_scenes(): return jsonify({"scenes":scenarios.list_scenarios()})

@meta_bp.route("/api/cards")
def api_cards(): return jsonify({"cards":list_cards()})

@meta_bp.route("/api/cards", methods=["POST"])
def api_save_card():
    d = request.get_json(); name = d.get("name","").strip()
    if not name: return jsonify({"ok":False,"error":"角色名不能为空"})
    fname = save_card(name, d.get("age","16"), d.get("appearance",""), d.get("magic",""),
                      d.get("personality",""), d.get("raw_text",""))
    return jsonify({"ok":True,"filename":fname,"cards":list_cards()})

@meta_bp.route("/api/cards/<name>", methods=["DELETE"])
def api_delete_card(name: str): return jsonify({"ok":delete_card(name),"cards":list_cards()})

@meta_bp.route("/api/cards/watch")
def api_cards_watch():
    """SSE 端点：每 2 秒检查 cards/ 目录变化，推送更新后的卡片列表。"""
    def generate():
        last_mtime = get_cards_mtime()
        yield f"event: cards_updated\ndata: {json.dumps({'type':'cards_updated','cards':list_cards()}, ensure_ascii=False)}\n\n"
        while True:
            time.sleep(2)
            try:
                current = get_cards_mtime()
                if current != last_mtime:
                    last_mtime = current
                    cards = list_cards()
                    yield f"event: cards_updated\ndata: {json.dumps({'type':'cards_updated','cards':cards}, ensure_ascii=False)}\n\n"
            except GeneratorExit:
                break
            except Exception:
                pass
    return Response(stream_with_context(generate()), mimetype="text/event-stream",
                    headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})

@meta_bp.route("/api/start_with_card", methods=["POST"])
def api_start_with_card():
    card = get_card(request.get_json().get("card_name","").strip())
    if not card: return jsonify({"ok":False,"error":"角色卡不存在"})
    text = _sess.session.prologue_step_1_mirror(card["name"], card["age"], card["appearance"])
    _sess.session.world.player_magic = card["magic"]
    if card.get("personality"): _sess.session.world.player_magic += f" （性格: {card['personality']}）"
    return jsonify({"ok":True,"name":card["name"],"age":card["age"],"appearance":card["appearance"],"magic":card["magic"],"intro_text":text})

@meta_bp.route("/api/meta", methods=["POST"])
def api_meta():
    d = request.get_json(); cmd = d.get("command","").strip()
    if not cmd: return jsonify({"ok":False,"error":"空指令"})
    result = ""
    if "检查" in cmd and ("角色" in cmd or "所有" in cmd or "全员" in cmd):
        lines = []
        for aid in sorted(_sess.session.agents.keys()):
            a = _sess.session.agents[aid]; st = a.state
            if not st.alive: lines.append(f"[死亡] {a.profile.name}[{aid}]")
            else:
                loc = _sess.session.world.npc_locations.get(aid,"?")
                met = "已认识" if aid in _sess.session.world.player_met_npcs else "未认识"
                aff = st.affection_map.get("player","?")
                lines.append(f"{a.profile.name}[{aid}] {loc} {st.emotional_state} 好感{aff} {met}")
        result = "\n".join(lines)
    elif "位置" in cmd or "地点" in cmd:
        lines = []
        for loc in sorted(set(_sess.session.world.npc_locations.values())):
            npcs_here = [aid for aid, aloc in _sess.session.world.npc_locations.items() if aloc == loc]
            names = []
            for aid in npcs_here:
                if aid in _sess.session.agents:
                    names.append(_sess.session.agents[aid].profile.name)
            lines.append(f"【{loc}】: {', '.join(names) if names else '(无)'}")
        result = "\n".join(lines)
    elif "时间" in cmd:
        result = f"第{_sess.session.world.current_day}天 {_sess.session.world.current_time} · 阶段:{_sess.session.world.phase.value} · 第{_sess.session.round_count}轮"
    else:
        result = f"未知指令：{cmd}。可用指令：检查所有角色、检查各地点、查看当前时间。"
    return jsonify({"ok":True,"result":result, "command":cmd})

@meta_bp.route("/api/free_narrative", methods=["POST"])
def api_free_narrative():
    d = request.get_json(); action = d.get("action","").strip()
    if not action: return jsonify({"ok":False,"error":"空行动"})
    gm_name = _sess.session.scenario.get("gm_name","") if _sess.session.scenario else ""
    scene_name = _sess.session.scenario.get("name","") if _sess.session.scenario else ""
    loc_npcs = [aid for aid, aloc in _sess.session.world.npc_locations.items() if aloc == _sess.session.player_location and aid != "player"]
    nearby_names = [_sess.session.agents[aid].profile.name if aid in _sess.session.agents else aid for aid in loc_npcs]
    known = [_sess.session.agents[aid].profile.name for aid in _sess.session.world.player_met_npcs if aid in _sess.session.agents]
    try:
        result = _sess.session.llm.chat_json(messages=[{"role":"user","content":f"""场景：{scene_name}。玩家在{_sess.session.player_location}。
附近角色：{', '.join(nearby_names) if nearby_names else '无人'}。
玩家已认识：{', '.join(known) if known else '无'}。
玩家行动：{action}

以第二人称叙述，长度自适。直接描写玩家行动的结果，写出感官细节和 NPC 反应。
然后生成 2-4 个相关选项，第4个始终是"（自定义行动）"。

输出 JSON：
{{"narrative":"...", "options":[{{"label":"...","type":"dialogue|investigate|explore|custom","target":"No.01或null","room":"房间名或null"}}]}}
注意：不推进时间，不触发 NPC 决策。只描写玩家行动和周围人的即时反应。"""}], system=f"你是故事旁白。场景：{scene_name}。", temperature=1.0, max_tokens=1024)
        narrative = result.get("narrative","")
        raw_options = result.get("options",[])
        opts = []
        for item in raw_options:
            if not isinstance(item,dict): continue
            label = item.get("label","")
            if not label.strip(): continue
            t = (item.get("type","") or "investigate").strip()
            if t not in ("dialogue","investigate","explore","custom"): t = "investigate"
            target = item.get("target") or None
            room = item.get("room") or None
            opts.append({"label":label.strip(),"type":t,"target":target,"room":room})
        if not opts: opts = [{"label":"（自定义行动）","type":"custom","target":None,"room":None}]
        _sess.session._log("system", f"你: {action}")
        _sess.session._log("gm", narrative)
        return jsonify({"ok":True,"narrative":narrative,"options":opts})
    except Exception as e:
        return jsonify({"ok":False,"error":str(e)[:200]})
