"""Meta blueprint — 7 endpoints: scenes, cards, start_with_card, meta, free_narrative, state, index."""
from flask import Blueprint, request, jsonify, send_from_directory
from session import session
from card_manager import list_cards, save_card, delete_card, get_card
import scenarios

meta_bp = Blueprint('meta', __name__)

def _map_data():
    fr = session.scenario.get("floor_rooms", {}) if session.scenario else {}
    ft = session.scenario.get("floor_transitions", {}) if session.scenario else {}
    expl = session.world.explored_rooms
    cars = []
    for floor_num in sorted(fr.keys()):
        rooms = fr[floor_num]
        explored = [r for r in rooms if r in expl]
        has_player = session.world.current_floor == floor_num
        locked = False
        if floor_num == 2 and not session.world.floor_2_unlocked:
            locked = True
        elif floor_num == 3 and not session.world.floor_3_unlocked:
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
        "player_room": session.player_location,
    }

def _npc_info():
    npcs = []; pl = session.player_location
    for aid in sorted(session.agents.keys()):
        a = session.agents[aid]; st = a.state
        if not st.alive: continue
        nl = session.world.npc_locations.get(aid,""); nearby = nl == pl; met = aid in session.world.player_met_npcs
        npcs.append({"agent_id":aid,"name":a.profile.name if met else "？","age":a.profile.age if met else 0,"affection":st.affection_map.get("player",50),"threat":50 if nearby else 0,"location":nl if nearby else "（不在视野内）","nearby":nearby})
    return npcs

@meta_bp.route("/")
def index(): return send_from_directory("static","index.html")

@meta_bp.route("/api/state")
def get_state():
    s = session.scenario if session.scenario else {}
    return jsonify({"player_name":session.player_name,"player_created":session.player_created,"scene_id":session.scene_id,"scene_name":s.get("name",""),"prologue_step":session.world.prologue_step,"day":session.world.current_day,"time":session.world.current_time,"floor":session.world.current_floor,"phase":session.world.phase.value,"difficulty":session.world.difficulty.value,"location":session.player_location,"round":session.round_count,"npcs":_npc_info(),"alive_count":len(session.world.alive_npcs),"in_trial":bool(session.world.active_trial and session.world.active_trial.active),"trial_phase":session.world.active_trial.phase if session.world.active_trial else "","trial_victim":session.world.active_trial.victim_id if session.world.active_trial else "","slots":session.save_mgr.list_slots(),"inventory":list(session.world.player_inventory),"room_items":session.world.room_item_state.get(session.player_location,{}),"knowledge_flags":sorted(session.world.knowledge_flags),"cards":list_cards(),"rule_text":s.get("rule_text",""),"trial_rules":s.get("trial_rules",""),"event_times":s.get("event_times",[]) if s else [],"map_data":_map_data()})

@meta_bp.route("/api/scenes")
def api_scenes(): return jsonify({"scenes":scenarios.list_scenarios()})

@meta_bp.route("/api/cards")
def api_cards(): return jsonify({"cards":list_cards()})

@meta_bp.route("/api/cards", methods=["POST"])
def api_save_card():
    d = request.get_json(); name = d.get("name","").strip()
    if not name: return jsonify({"ok":False,"error":"角色名不能为空"})
    fname = save_card(name, d.get("age","16"), d.get("appearance",""), d.get("magic",""), d.get("personality",""))
    return jsonify({"ok":True,"filename":fname,"cards":list_cards()})

@meta_bp.route("/api/cards/<name>", methods=["DELETE"])
def api_delete_card(name: str): return jsonify({"ok":delete_card(name),"cards":list_cards()})

@meta_bp.route("/api/start_with_card", methods=["POST"])
def api_start_with_card():
    card = get_card(request.get_json().get("card_name","").strip())
    if not card: return jsonify({"ok":False,"error":"角色卡不存在"})
    text = session.prologue_step_1_mirror(card["name"], card["age"], card["appearance"])
    session.world.player_magic = card["magic"]
    if card.get("personality"): session.world.player_magic += f" （性格: {card['personality']}）"
    return jsonify({"ok":True,"name":card["name"],"age":card["age"],"appearance":card["appearance"],"magic":card["magic"],"intro_text":text})

@meta_bp.route("/api/meta", methods=["POST"])
def api_meta():
    d = request.get_json(); cmd = d.get("command","").strip()
    if not cmd: return jsonify({"ok":False,"error":"空指令"})
    result = ""
    if "检查" in cmd and ("角色" in cmd or "所有" in cmd or "全员" in cmd):
        lines = []
        for aid in sorted(session.agents.keys()):
            a = session.agents[aid]; st = a.state
            if not st.alive: lines.append(f"[死亡] {a.profile.name}[{aid}]")
            else:
                loc = session.world.npc_locations.get(aid,"?")
                met = "已认识" if aid in session.world.player_met_npcs else "未认识"
                aff = st.affection_map.get("player","?")
                lines.append(f"{a.profile.name}[{aid}] {loc} {st.emotional_state} 好感{aff} {met}")
        result = "\n".join(lines)
    elif "位置" in cmd or "地点" in cmd:
        lines = []
        for loc in sorted(set(session.world.npc_locations.values())):
            npcs_here = [aid for aid, aloc in session.world.npc_locations.items() if aloc == loc]
            names = []
            for aid in npcs_here:
                if aid in session.agents:
                    names.append(session.agents[aid].profile.name)
            lines.append(f"【{loc}】: {', '.join(names) if names else '(无)'}")
        result = "\n".join(lines)
    elif "时间" in cmd:
        result = f"第{session.world.current_day}天 {session.world.current_time} · 阶段:{session.world.phase.value} · 第{session.round_count}轮"
    else:
        result = f"未知指令：{cmd}。可用指令：检查所有角色、检查各地点、查看当前时间。"
    return jsonify({"ok":True,"result":result, "command":cmd})

@meta_bp.route("/api/free_narrative", methods=["POST"])
def api_free_narrative():
    d = request.get_json(); action = d.get("action","").strip()
    if not action: return jsonify({"ok":False,"error":"空行动"})
    gm_name = session.scenario.get("gm_name","") if session.scenario else ""
    scene_name = session.scenario.get("name","") if session.scenario else ""
    loc_npcs = [aid for aid, aloc in session.world.npc_locations.items() if aloc == session.player_location and aid != "player"]
    nearby_names = [session.agents[aid].profile.name if aid in session.agents else aid for aid in loc_npcs]
    known = [session.agents[aid].profile.name for aid in session.world.player_met_npcs if aid in session.agents]
    try:
        result = session.llm.chat_json(messages=[{"role":"user","content":f"""场景：{scene_name}。玩家在{session.player_location}。
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
        session._log("system", f"你: {action}")
        session._log("gm", narrative)
        return jsonify({"ok":True,"narrative":narrative,"options":opts})
    except Exception as e:
        return jsonify({"ok":False,"error":str(e)[:200]})
