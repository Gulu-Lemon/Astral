"""Game blueprint — 6 endpoints: round (SSE), dialogue, suggestions, explore, investigate, move_player."""
import json, queue, threading
from flask import Blueprint, request, jsonify, Response, stream_with_context
from session import session
from state import roll_risk

game_bp = Blueprint('game', __name__)

@game_bp.route("/api/round")
def api_round():
    def generate():
        q = queue.Queue()
        def worker():
            try: session.run_round(q)
            except Exception as e: q.put({"type":"error","message":str(e)})
            finally: q.put({"type":"_done_"})
        t = threading.Thread(target=worker); t.start()
        while True:
            try: evt = q.get(timeout=120)
            except queue.Empty: yield f"data: {json.dumps({'type':'error','message':'超时'},ensure_ascii=False)}\n\n"; break
            if evt.get("type") == "_done_": break
            yield f"data: {json.dumps(evt,ensure_ascii=False)}\n\n"
            if evt.get("type") == "error": break
        t.join(timeout=5)
    return Response(stream_with_context(generate()), mimetype="text/event-stream", headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})

@game_bp.route("/api/dialogue", methods=["POST"])
def api_dialogue():
    d = request.get_json(); aid = d.get("agent_id",""); msg = d.get("message","你好。")
    if aid not in session.agents: return jsonify({"ok":False,"error":"角色不存在"})
    agent = session.agents[aid]
    if session.player_location != session.world.npc_locations.get(aid,""):
        return jsonify({"ok":False,"error":f"{agent.profile.name} 不在这里。"})
    session.world.player_met_npcs.add(aid)
    ctx = f"地点：{session.player_location}，第{session.world.current_day}天{session.world.current_time}。"
    memories = []
    for evt in session.world.public_events[-8:]:
        ed = (evt.tick // 6) + 1 if evt.tick else session.world.current_day
        if evt.actor_id == aid: memories.append(f"（第{ed}天，{evt.location}：你{evt.public_description}）")
        elif aid in evt.witnesses: memories.append(f"（第{ed}天，{evt.location}：你看到{evt.public_description}）")
    if memories: ctx += " " + " ".join(memories[-5:])
    resp = agent.dialogue(ctx, session.player_name, msg, speaker_id="player")
    agent._chat_history.append(f"玩家：{msg}")
    agent._chat_history.append(f"自己：{resp}")
    if len(agent._chat_history) > 20:
        agent._chat_history = agent._chat_history[-20:]
    session._log("dialogue", f"你: {msg}")
    session._log("dialogue", f"{agent.profile.name}: {resp}")
    micro = ""
    try:
        micro = session.llm.chat(
            messages=[{"role":"user","content":f"玩家对{agent.profile.name}说：「{msg}」\n{agent.profile.name}回答：「{resp}」\n请描述这个对话场景。以第二人称。避免元语言。"}],
            system=f"你是故事旁白。场景：{session.scenario.get('name','')}。", temperature=0.8, max_tokens=512)
    except: pass
    session._pending_player_dialogues.append({
        "agent_id": aid, "msg": msg, "resp": resp, "tick": session.world.global_tick
    })
    return jsonify({"ok":True,"agent_name":agent.profile.name,"response":resp,"affection":agent.state.affection_map.get("player",50),"micro_narrative":micro})

@game_bp.route("/api/dialogue_suggestions", methods=["POST"])
def api_dialogue_suggestions():
    data = request.get_json() or {}
    return jsonify({"ok":True,"suggestions":session._gen_dialogue_suggestions(data.get("agent_id",""), data.get("player_name", session.player_name or ""))})

@game_bp.route("/api/explore", methods=["POST"])
def api_explore():
    d = request.get_json(); room = d.get("room","").strip()
    if not room: return jsonify({"ok":False,"error":"未指定房间"})
    ft = session.scenario.get("floor_transitions",{}) if session.scenario else {}
    if room in ft:
        tf = ft[room].get("to_floor",1)
        ff = ft[room].get("from_floor")
        if ff is not None and session.world.current_floor != ff:
            return jsonify({"ok":False,"error":"你无法直接前往那个区域，需要先经过中间的车厢/楼层。"})
        if tf == 2 and not session.world.floor_2_unlocked: return jsonify({"ok":False,"error":"还无法进入这个区域。"})
        if tf == 3 and not session.world.floor_3_unlocked: return jsonify({"ok":False,"error":"还无法前往更深处。"})
        if tf > 1: session.world.current_floor = tf; session.world.world_revelation_phase = tf; session.player_location = room; session.world.explored_rooms.add(room); return jsonify({"ok":True,"room":room,"description":"你来到了新的楼层。","location":session.player_location})
    session.player_location = room; session.world.explored_rooms.add(room)
    npcs_here = []
    for aid, aloc in session.world.npc_locations.items():
        if aloc == room and aid != "player":
            st = session.agent_states.get(aid)
            if st and st.alive:
                cp = session.scenario.get("characters", {}).get(aid) if session.scenario else None
                if cp:
                    label = f"{cp.name}[{aid}]" if aid in session.world.player_met_npcs else f"{cp.appearance}[{aid}]"
                    npcs_here.append(label)
    npcs_desc = "、".join(npcs_here) if npcs_here else "（空无一人）"
    try:
        desc = session.llm.chat(messages=[{"role":"user","content":f"描述场景：{room}。用第二人称。\n\n当前在此房间的角色：{npcs_desc}\n场景基调：{session.scenario.get('scene_tone','') if session.scenario else ''}\n\n注意：只能描写上述列表中的角色。未认识名字的用外貌特征描述。禁止编造不在列表中的角色。"}], system=f"你是故事旁白。场景：{session.scenario.get('name','') if session.scenario else ''}。", temperature=0.8, max_tokens=512)
    except: desc = f"你来到了{room}。"
    return jsonify({"ok":True,"room":room,"description":desc,"location":session.player_location})

@game_bp.route("/api/investigate", methods=["POST"])
def api_investigate():
    d = request.get_json(); action = d.get("action","").strip()
    if not action: return jsonify({"ok":False,"error":"未指定行动"})
    room = session.player_location; world = session.world
    if world.active_trial and world.active_trial.active and world.active_trial.phase == "investigation":
        return jsonify({"ok":True,"action":action,"description":session.trial_investigate(action),"trial_evidence":True})
    room_items = world.room_item_state.get(room,{})
    items_desc = "、".join(f"{k}" if v == "存在" else f"{k}({v})" for k,v in room_items.items()) if room_items else "无"
    inv_desc = "、".join(world.player_inventory) if world.player_inventory else "无"
    try:
        result = session.llm.chat_json(messages=[{"role":"user","content":f"""玩家在【{room}】中执行了："{action}"
楼层：{world.current_floor}
环境：{session.scenario.get('name','') if session.scenario else ''} — 禁止出现现代城市、街道、交通工具等元素。

当前房间的物品状态：{items_desc}
玩家物品栏：{inv_desc}

决定这次行动的结果。输出 JSON：{{"narrative":"...","take_item":null,"remove_item":null,"add_item":null,"knowledge":null,"room_state_change":null,"risk":"低风险"}}
规则：禁止编造新名字新角色。只描写已存在的物品和NPC。以下是本场景全部角色：{session._roster()}
只有可移动的小件物品才能拿走。""" }], system="你是故事旁白。直接、简洁。必须输出 JSON。", temperature=0.9, max_tokens=1024)
        narrative = result.get("narrative","你仔细看了看，但没有特别的发现。")
        take = result.get("take_item"); remove = result.get("remove_item"); add = result.get("add_item")
        kn = result.get("knowledge"); rsc = result.get("room_state_change"); risk = result.get("risk","低风险")
        risk_ok = roll_risk(risk)
        if not risk_ok: narrative += "（但你没能做到。）"
        else:
            if take: world.room_item_state.setdefault(room,{})[take] = "已取走"; world.player_inventory.append(take) if take not in world.player_inventory else None
            if remove and remove != take: world.room_item_state.setdefault(room,{})[remove] = "已消失"
            if add and add not in world.player_inventory: world.player_inventory.append(add)
            if kn: world.knowledge_flags.add(kn)
            if rsc and isinstance(rsc,dict):
                for k,v in rsc.items(): world.room_item_state.setdefault(room,{})[k] = v
        session._log("system", f"你: {action}")
        session._log("gm", narrative)
        return jsonify({"ok":True,"action":action,"description":narrative,"inventory":world.player_inventory})
    except Exception as e:
        desc = session.llm.chat(messages=[{"role":"user","content":f"玩家在【{room}】中执行了：{action}。直接描写，用'你'指代玩家角色。禁止编造新角色。"}], system="你是故事旁白。", temperature=0.9, max_tokens=512)
        return jsonify({"ok":True,"action":action,"description":desc})

@game_bp.route("/api/move_player", methods=["POST"])
def api_move_player():
    d = request.get_json(); target = d.get("room","").strip()
    fr = session.scenario.get("floor_rooms",{}) if session.scenario else {}
    if target and target in fr.get(session.world.current_floor,[]):
        session.player_location = target; session.world.explored_rooms.add(target)
    return jsonify({"ok":True,"location":session.player_location})
