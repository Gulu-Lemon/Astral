"""Game blueprint — game loop, dialogue, explore, investigate, skip, sleep, ending."""
import json, queue, threading, traceback, re
from flask import Blueprint, request, jsonify, Response, stream_with_context
import session as _sess
from state import roll_risk

game_bp = Blueprint('game', __name__)

def _extract_elapsed(text: str, default: int = 8) -> int:
    """从 LLM 回答中提取分钟数。失败重试一次，再失败返回默认。"""
    if not text: return default
    for pat in [r'(\d+)\s*分', r'(\d+)\s*min', r'(\d+)\s*分钟', r'elapsed[:\s]*(\d+)']:
        m = re.search(pat, text, re.IGNORECASE)
        if m: return max(1, min(120, int(m.group(1))))
    nums = re.findall(r'\d+', text)
    if nums: return max(1, min(120, int(nums[-1])))
    return default

def _estimate_time_via_llm(llm, context: str, prompt_suffix: str = "", default: int = 8) -> int:
    """调 LLM 专门估算时间。重试一次。"""
    for attempt in range(2):
        try:
            suffix = prompt_suffix if attempt == 0 else "只回答一个数字，表示大概过了几分钟。不要任何其他文字。"
            resp = llm.chat(
                messages=[{"role": "user", "content": context + "\n\n" + suffix}],
                system="你是时间估算器。基于叙述内容估计过去了多少分钟。数字。",
                temperature=0.1, max_tokens=8,
            )
            elapsed = _extract_elapsed(resp, -1)
            if elapsed > 0: return elapsed
        except Exception:
            pass
    return default

@game_bp.route("/api/round")
def api_round():
    elapsed = int(request.args.get("elapsed", 60))
    def generate():
        q = queue.Queue()
        def worker():
            try: _sess.session.run_round(q, elapsed_minutes=elapsed)
            except Exception as e: q.put({"type":"error","message":f"{e}\n{traceback.format_exc()}"})
            finally: q.put({"type":"_done_"})
        t = threading.Thread(target=worker); t.start()
        while True:
            try: evt = q.get(timeout=120)
            except queue.Empty: yield f"event: error\ndata: {json.dumps({'type':'error','message':'超时'},ensure_ascii=False)}\n\n"; break
            if evt.get("type") == "_done_": break
            evt_type = evt.get("type", "message")
            yield f"event: {evt_type}\ndata: {json.dumps(evt,ensure_ascii=False)}\n\n"
            if evt.get("type") == "error": break
        t.join(timeout=5)
    return Response(stream_with_context(generate()), mimetype="text/event-stream", headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})

@game_bp.route("/api/dialogue", methods=["POST"])
def api_dialogue():
    d = request.get_json(); aid = d.get("agent_id",""); msg = d.get("message","你好。")
    if aid not in _sess.session.agents: return jsonify({"ok":False,"error":"角色不存在"})
    agent = _sess.session.agents[aid]
    if _sess.session.player_location != _sess.session.world.npc_locations.get(aid,""):
        return jsonify({"ok":False,"error":f"{agent.profile.name} 不在这里。"})
    _sess.session.world.player_met_npcs.add(aid)
    ctx = f"地点：{_sess.session.player_location}，第{_sess.session.world.current_day}天{_sess.session.world.current_time}。"
    memories = []
    for evt in _sess.session.world.public_events[-8:]:
        ed = (evt.tick // 6) + 1 if evt.tick else _sess.session.world.current_day
        if evt.actor_id == aid: memories.append(f"（第{ed}天，{evt.location}：你{evt.public_description}）")
        elif aid in evt.witnesses: memories.append(f"（第{ed}天，{evt.location}：你看到{evt.public_description}）")
    if memories: ctx += " " + " ".join(memories[-5:])
    resp = agent.dialogue(ctx, _sess.session.player_name, msg, speaker_id="player")
    agent._chat_history.append(f"玩家：{msg}")
    agent._chat_history.append(f"自己：{resp}")
    if len(agent._chat_history) > 20:
        agent._chat_history = agent._chat_history[-20:]
    _sess.session._log("dialogue", f"你: {msg}")
    _sess.session._log("dialogue", f"{agent.profile.name}: {resp}")
    micro = ""
    try:
        micro = _sess.session.llm.chat(
            messages=[{"role":"user","content":f"玩家对{agent.profile.name}说：「{msg}」\n{agent.profile.name}回答：「{resp}」\n请描述这个对话场景。以第二人称。避免元语言。"}],
            system=f"你是故事旁白。场景：{_sess.session.scenario.get('name','')}。", temperature=0.8, max_tokens=512)
    except: micro = ""
    elapsed = _estimate_time_via_llm(_sess.session.llm,
        f"玩家与{agent.profile.name}进行了如下对话：\n玩家：「{msg}」\n{agent.profile.name}：「{resp}」\n\n根据对话长度和内容深度，估计大约过了多少分钟。",
        "估计这次对话持续了多少分钟？只回答数字。", default=10)
    _sess.session._pending_player_dialogues.append({
        "agent_id": aid, "msg": msg, "resp": resp, "tick": _sess.session.world.global_tick
    })
    return jsonify({"ok":True,"agent_name":agent.profile.name,"response":resp,"affection":agent.state.affection_map.get("player",50),"micro_narrative":micro,"elapsed_minutes":elapsed})

@game_bp.route("/api/dialogue_suggestions", methods=["POST"])
def api_dialogue_suggestions():
    data = request.get_json() or {}
    return jsonify({"ok":True,"suggestions":_sess.session._gen_dialogue_suggestions(data.get("agent_id",""), data.get("player_name", _sess.session.player_name or ""))})

@game_bp.route("/api/explore", methods=["POST"])
def api_explore():
    d = request.get_json(); room = d.get("room","").strip()
    if not room: return jsonify({"ok":False,"error":"未指定房间"})
    ft = _sess.session.scenario.get("floor_transitions",{}) if _sess.session.scenario else {}
    if room in ft:
        tf = ft[room].get("to_floor",1)
        ff = ft[room].get("from_floor")
        if ff is not None and _sess.session.world.current_floor != ff:
            return jsonify({"ok":False,"error":"你无法直接前往那个区域，需要先经过中间的车厢/楼层。"})
        if tf == 2 and not _sess.session.world.floor_2_unlocked: return jsonify({"ok":False,"error":"还无法进入这个区域。"})
        if tf == 3 and not _sess.session.world.floor_3_unlocked: return jsonify({"ok":False,"error":"还无法前往更深处。"})
        if tf > 1: _sess.session.world.current_floor = tf; _sess.session.world.world_revelation_phase = tf; _sess.session.player_location = room; _sess.session.world.explored_rooms.add(room); return jsonify({"ok":True,"room":room,"description":"你来到了新的楼层。","location":_sess.session.player_location,"elapsed_minutes":10})
    _sess.session.player_location = room; _sess.session.world.explored_rooms.add(room)
    npcs_here = []
    for aid, aloc in _sess.session.world.npc_locations.items():
        if aloc == room and aid != "player":
            st = _sess.session.agent_states.get(aid)
            if st and st.alive:
                cp = _sess.session.scenario.get("characters", {}).get(aid) if _sess.session.scenario else None
                if cp:
                    label = f"{cp.name}[{aid}]" if aid in _sess.session.world.player_met_npcs else f"{cp.appearance}[{aid}]"
                    npcs_here.append(label)
    npcs_desc = "、".join(npcs_here) if npcs_here else "（空无一人）"
    try:
        desc = _sess.session.llm.chat(messages=[{"role":"user","content":f"描述场景：{room}。用第二人称。\n\n当前在此房间的角色：{npcs_desc}\n场景基调：{_sess.session.scenario.get('scene_tone','') if _sess.session.scenario else ''}\n\n注意：只能描写上述列表中的角色。未认识名字的用外貌特征描述。禁止编造不在列表中的角色。"}], system=f"你是故事旁白。场景：{_sess.session.scenario.get('name','') if _sess.session.scenario else ''}。", temperature=0.8, max_tokens=512)
    except: desc = f"你来到了{room}。"
    elapsed = _estimate_time_via_llm(_sess.session.llm,
        f"玩家移动到了新房间：{room}。当前房间有这些人：{npcs_desc}。", "估计这次移动花了多少分钟？只回答数字。", default=5)
    return jsonify({"ok":True,"room":room,"description":desc,"location":_sess.session.player_location,"elapsed_minutes":elapsed})

@game_bp.route("/api/investigate", methods=["POST"])
def api_investigate():
    d = request.get_json(); action = d.get("action","").strip()
    if not action: return jsonify({"ok":False,"error":"未指定行动"})
    room = _sess.session.player_location; world = _sess.session.world
    if world.active_trial and world.active_trial.active and world.active_trial.phase == "investigation":
        return jsonify({"ok":True,"action":action,"description":_sess.session.trial_investigate(action),"trial_evidence":True,"elapsed_minutes":8})
    room_items = world.room_item_state.get(room,{})
    items_desc = "、".join(f"{k}" if v == "存在" else f"{k}({v})" for k,v in room_items.items()) if room_items else "无"
    inv_desc = "、".join(world.player_inventory) if world.player_inventory else "无"
    try:
        result = _sess.session.llm.chat_json(messages=[{"role":"user","content":f"""玩家在【{room}】中执行了："{action}"
楼层：{world.current_floor}
环境：{_sess.session.scenario.get('name','') if _sess.session.scenario else ''} — 禁止出现现代城市、街道、交通工具等元素。

当前房间的物品状态：{items_desc}
玩家物品栏：{inv_desc}

决定这次行动的结果。输出 JSON：{{"narrative":"...","elapsed_minutes":8,"take_item":null,"remove_item":null,"add_item":null,"knowledge":null,"room_state_change":null,"risk":"低风险"}}
规则：禁止编造新名字新角色。只描写已存在的物品和NPC。以下是本场景全部角色：{_sess.session._roster()}
只有可移动的小件物品才能拿走。elapsed_minutes 是你估计这次行动花了多少分钟（整数）。""" }], system="你是故事旁白。直接、简洁。必须输出 JSON。", temperature=0.9, max_tokens=1024)
        narrative = result.get("narrative","你仔细看了看，但没有特别的发现。")
        elapsed = int(result.get("elapsed_minutes", 0) or 0)
        if elapsed <= 0: elapsed = _estimate_time_via_llm(_sess.session.llm,
            f"玩家执行了以下行动：{action}。在房间：{room}。结果：{narrative[:200]}",
            "只回答数字：这次行动花了多少分钟？", default=8)
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
        _sess.session._log("system", f"你: {action}")
        _sess.session._log("gm", narrative)
        return jsonify({"ok":True,"action":action,"description":narrative,"inventory":world.player_inventory,"elapsed_minutes":elapsed})
    except Exception as e:
        desc = _sess.session.llm.chat(messages=[{"role":"user","content":f"玩家在【{room}】中执行了：{action}。直接描写，用'你'指代玩家角色。禁止编造新角色。"}], system="你是故事旁白。", temperature=0.9, max_tokens=512)
        elapsed = _estimate_time_via_llm(_sess.session.llm,
            f"玩家执行了：{action}。在房间：{room}。", "只回答数字：这次行动花了多少分钟？", default=8)
        return jsonify({"ok":True,"action":action,"description":desc,"elapsed_minutes":elapsed})

@game_bp.route("/api/move_player", methods=["POST"])
def api_move_player():
    d = request.get_json(); target = d.get("room","").strip()
    fr = _sess.session.scenario.get("floor_rooms",{}) if _sess.session.scenario else {}
    if target and target in fr.get(_sess.session.world.current_floor,[]):
        _sess.session.player_location = target; _sess.session.world.explored_rooms.add(target)
    return jsonify({"ok":True,"location":_sess.session.player_location})

@game_bp.route("/api/skip_time", methods=["POST"])
def api_skip_time():
    d = request.get_json() or {}
    mode = d.get("mode", "skip_hours")
    kwargs = {}
    if mode == "until":
        kwargs = {"hour": int(d.get("hour", 14)), "minute": int(d.get("minute", 0))}
    elif d.get("hour") is not None and mode == "skip_hours":
        # 兼容旧格式: {hour: N} 表示跳到 N 点
        kwargs = {"target_hour": int(d.get("hour"))}
    else:
        kwargs = {"hours": int(d.get("hours", 1))}
    result = _sess.session.skip_time(mode=mode, **kwargs)
    return jsonify({"ok": True, "result": result, "time": _sess.session.world.current_time,
                    "day": _sess.session.world.current_day})

@game_bp.route("/api/sleep", methods=["POST"])
def api_sleep():
    result = _sess.session.sleep_until_morning()
    return jsonify({"ok": True, "result": result, "time": _sess.session.world.current_time,
                    "day": _sess.session.world.current_day})

@game_bp.route("/api/ending/choose", methods=["POST"])
def api_ending_choose():
    ending_id = (request.get_json() or {}).get("ending_id", "")
    text = _sess.session.choose_ending(ending_id)
    return jsonify({"ok": True, "text": text, "ending_id": ending_id,
                    "ending_resolved": _sess.session.world.ending_resolved})
