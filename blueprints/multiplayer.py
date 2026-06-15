"""
联机 Socket.IO 事件处理 — 房间管理 + 游戏流程
"""
import json
import logging
from flask import request
from flask_socketio import emit, join_room as sio_join, leave_room as sio_leave, close_room

from multiplayer_session import mp_manager
import scenarios

logger = logging.getLogger("astral.multiplayer")


def register_events(socketio):
    mp_manager.set_sio(socketio)

    @socketio.on("connect")
    def on_connect():
        logger.info(f"Socket 连接: {request.sid}")

    @socketio.on("disconnect")
    def on_disconnect():
        sid = request.sid
        for rid, room in list(mp_manager.rooms.items()):
            for slot in room.slots.values():
                if slot.player_sid == sid:
                    slot.connected = False
                    if room.phase == "lobby":
                        slot.is_human = False
                        slot.player_sid = ""
                        slot.player_name = ""
                    emit("player_left", {"agent_id": slot.agent_id,
                         "player_name": slot.player_name}, room=rid)
                    logger.info(f"断线: {slot.player_name or sid} ({rid})")
                    break

    # ========== 房间管理 ==========

    @socketio.on("create_room")
    def on_create_room(data):
        sid = request.sid
        scene_id = data.get("scene_id", "tianji_maze")
        player_name = data.get("player_name", "玩家").strip() or "玩家"

        room = mp_manager.create_room(sid, scene_id, player_name)
        sio_join(room.room_id)

        emit("room_created", {
            "room_id": room.room_id,
            "scene_id": scene_id,
            "host_agent_id": room.host_agent_id,
            "slots": {k: v.to_dict() for k, v in room.slots.items()},
            "players": [{"agent_id": s.agent_id, "player_name": s.player_name,
                         "connected": s.connected}
                        for s in mp_manager.get_human_slots(room.room_id)],
        })

    @socketio.on("join_room")
    def on_join_room(data):
        sid = request.sid
        room_id = (data.get("room_id") or "").strip().upper()
        player_name = data.get("player_name", "玩家").strip() or "玩家"

        slot, err = mp_manager.join_room(room_id, sid, player_name)
        if err:
            emit("error", {"code": "join_failed", "message": err})
            return

        sio_join(room_id)
        emit("room_joined", {
            "room_id": room_id,
            "agent_id": slot.agent_id,
            "player_name": player_name,
            "slots": {k: v.to_dict() for k, v in mp_manager.rooms[room_id].slots.items()},
            "players": [{"agent_id": s.agent_id, "player_name": s.player_name,
                         "connected": s.connected}
                        for s in mp_manager.get_human_slots(room_id)],
        })
        emit("player_joined", {"agent_id": slot.agent_id, "player_name": player_name},
             room=room_id, include_self=False)

    @socketio.on("select_slot")
    def on_select_slot(data):
        sid = request.sid
        room_id = (data.get("room_id") or "").strip().upper()
        agent_id = data.get("agent_id", "")

        slot, err = mp_manager.select_slot(room_id, sid, agent_id)
        if err:
            emit("error", {"code": "slot_failed", "message": err})
            return

        room = mp_manager.rooms[room_id]
        emit("slot_updated", {
            "slots": {k: v.to_dict() for k, v in room.slots.items()},
            "players": [{"agent_id": s.agent_id, "player_name": s.player_name,
                         "connected": s.connected}
                        for s in mp_manager.get_human_slots(room_id)],
        }, room=room_id)

    @socketio.on("toggle_slot_ai")
    def on_toggle_slot_ai(data):
        sid = request.sid
        room_id = (data.get("room_id") or "").strip().upper()
        agent_id = data.get("agent_id", "")
        make_ai = data.get("make_ai", True)

        slot, err = mp_manager.toggle_slot_ai(room_id, sid, agent_id, make_ai)
        if err:
            emit("error", {"code": "toggle_failed", "message": err})
            return

        room = mp_manager.rooms[room_id]
        emit("slot_updated", {
            "slots": {k: v.to_dict() for k, v in room.slots.items()},
            "players": [{"agent_id": s.agent_id, "player_name": s.player_name,
                         "connected": s.connected}
                        for s in mp_manager.get_human_slots(room_id)],
        }, room=room_id)

    @socketio.on("leave_room")
    def on_leave_room(data):
        sid = request.sid
        room_id = (data.get("room_id") or "").strip().upper()
        mp_manager.leave_room(room_id, sid)
        sio_leave(room_id)
        emit("left_room", {"room_id": room_id})

        room = mp_manager.rooms.get(room_id)
        if room:
            emit("slot_updated", {
                "slots": {k: v.to_dict() for k, v in room.slots.items()},
                "players": [{"agent_id": s.agent_id, "player_name": s.player_name,
                             "connected": s.connected}
                            for s in mp_manager.get_human_slots(room_id)],
            }, room=room_id)

    # ========== 游戏流程 ==========

    @socketio.on("start_game")
    def on_start_game(data):
        sid = request.sid
        room_id = (data.get("room_id") or "").strip().upper()

        room, err = mp_manager.start_game(room_id, sid)
        if err:
            emit("error", {"code": "start_failed", "message": err})
            return

        emit("game_starting", {"room_id": room_id}, room=room_id)
        mp_manager.open_time_window(room_id)
        logger.info(f"游戏开始: {room_id}")

    @socketio.on("submit_intent")
    def on_submit_intent(data):
        sid = request.sid
        room_id = (data.get("room_id") or "").strip().upper()

        ok, err = mp_manager.submit_intent(room_id, sid, data)
        if not ok:
            emit("error", {"code": "intent_failed", "message": err})

    @socketio.on("send_dialogue")
    def on_send_dialogue(data):
        sid = request.sid
        room_id = (data.get("room_id") or "").strip().upper()
        target_id = data.get("target_id", "")
        message = (data.get("message") or "").strip()

        if not message:
            emit("error", {"code": "empty_message", "message": "消息不能为空"})
            return

        resp, err = mp_manager.player_dialogue(room_id, sid, target_id, message)
        if err:
            emit("error", {"code": "dialogue_failed", "message": err})
            return

        room = mp_manager.rooms.get(room_id)
        gs = mp_manager.sessions.get(room_id)

        # Find speaker
        speaker_slot = None
        for s in room.slots.values() if room else []:
            if s.player_sid == sid:
                speaker_slot = s
                break

        speaker_name = ""
        if speaker_slot and gs:
            agent = gs.agents.get(speaker_slot.agent_id)
            if agent:
                speaker_name = agent.profile.name

        emit("dialogue_result", {
            "from_agent": speaker_slot.agent_id if speaker_slot else "",
            "from_name": speaker_name,
            "target_id": target_id,
            "message": message,
            "response": resp,
        }, room=sid)

        # If target is NPC, broadcast to other players in the room
        target_slot = None
        for s in room.slots.values() if room else []:
            if s.agent_id == target_id and s.is_human:
                target_slot = s
                break

        if not target_slot and resp:
            # NPC response, broadcast to all players at same location
            speaker_loc = gs.world.npc_locations.get(speaker_slot.agent_id, "") if gs else ""
            for s in mp_manager.get_connected_slots(room_id):
                if s.player_sid != sid:
                    emit("dialogue_broadcast", {
                        "from_agent": speaker_slot.agent_id if speaker_slot else "",
                        "from_name": speaker_name,
                        "to_agent": target_id,
                        "message": message,
                        "response": resp,
                    }, room=s.player_sid)

    @socketio.on("set_window_minutes")
    def on_set_window_minutes(data):
        sid = request.sid
        room_id = (data.get("room_id") or "").strip().upper()
        minutes = int(data.get("minutes", 10))

        room = mp_manager.rooms.get(room_id)
        if not room or room.host_sid != sid:
            emit("error", {"code": "not_host", "message": "只有房主可修改"})
            return

        room.window_minutes = max(5, min(minutes, room.max_window_minutes))
        emit("window_updated", {"window_minutes": room.window_minutes}, room=room_id)

    # ========== 场景列表 ==========

    @socketio.on("get_scenes")
    def on_get_scenes():
        scenes = scenarios.list_scenarios()
        emit("scenes_list", {"scenes": scenes})
