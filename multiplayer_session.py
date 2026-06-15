"""
联机管理器 — MultiplayerManager (模块级单例)
管理房间、时间窗口、玩家意图收集、回合解析、每玩家叙事
"""
from __future__ import annotations
import threading
import random
import string
import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from state import (PlayerSlot, MultiplayerRoom, PlayerAction, Intent, IntentType,
                   WorldState, AgentState, Ruling)
from session import GameSession, _time_string

logger = logging.getLogger("astral.multiplayer")


class MultiplayerManager:
    """全局联机管理器（模块级单例）"""

    def __init__(self):
        self._lock = threading.Lock()
        self.rooms: dict[str, MultiplayerRoom] = {}
        self.sessions: dict[str, GameSession] = {}
        self._window_timers: dict[str, threading.Timer] = {}
        self._pending_intents: dict[str, dict[str, list[PlayerAction]]] = {}
        self._sio = None

    @property
    def sio(self):
        return self._sio

    def set_sio(self, sio):
        self._sio = sio

    # ========== Room CRUD ==========

    def _gen_room_id(self) -> str:
        while True:
            rid = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
            if rid not in self.rooms:
                return rid

    def create_room(self, host_sid: str, scene_id: str = "tianji_maze",
                    player_name: str = "") -> MultiplayerRoom:
        room_id = self._gen_room_id()
        slots = {}
        for i in range(1, 13):
            aid = f"No.{i:02d}"
            slots[aid] = PlayerSlot(agent_id=aid)

        # 房主自动占据第一个空槽位
        host_agent = ""
        for aid, slot in slots.items():
            if not slot.is_human:
                slot.is_human = True
                slot.player_sid = host_sid
                slot.player_name = player_name
                slot.connected = True
                host_agent = aid
                break

        room = MultiplayerRoom(
            room_id=room_id, host_sid=host_sid,
            host_agent_id=host_agent, scene_id=scene_id,
            slots=slots, created_at=time.time(),
        )

        with self._lock:
            self.rooms[room_id] = room
            self._pending_intents[room_id] = {}

        logger.info(f"房间创建: {room_id} 房主={player_name}({host_agent}) 场景={scene_id}")
        return room

    def join_room(self, room_id: str, player_sid: str, player_name: str):
        with self._lock:
            room = self.rooms.get(room_id)
            if not room:
                return None, "房间不存在"
            if room.phase != "lobby":
                return None, "游戏已开始"

            # 重连断线槽位
            for slot in room.slots.values():
                if slot.is_human and not slot.connected:
                    slot.player_sid = player_sid
                    slot.player_name = player_name
                    slot.connected = True
                    logger.info(f"重连: {player_name} → {slot.agent_id} ({room_id})")
                    return slot, None

            # 分配新槽位
            human_count = sum(1 for s in room.slots.values() if s.is_human and s.connected)
            if human_count >= 12:
                return None, "房间已满"

            for aid in sorted(room.slots.keys()):
                slot = room.slots[aid]
                if not slot.is_human:
                    slot.is_human = True
                    slot.player_sid = player_sid
                    slot.player_name = player_name
                    slot.connected = True
                    logger.info(f"加入: {player_name} → {slot.agent_id} ({room_id})")
                    return slot, None
            return None, "房间已满"

    def select_slot(self, room_id: str, player_sid: str, agent_id: str):
        with self._lock:
            room = self.rooms.get(room_id)
            if not room:
                return None, "房间不存在"
            if room.phase != "lobby":
                return None, "游戏已开始"
            slot = room.slots.get(agent_id)
            if not slot:
                return None, "无效槽位"
            if slot.is_human and slot.connected and slot.player_sid != player_sid:
                return None, "该槽位已被占用"
            if slot.is_human and slot.player_sid == player_sid:
                return slot, None

            for s in room.slots.values():
                if s.player_sid == player_sid:
                    s.is_human = False
                    s.player_sid = ""
                    s.player_name = ""
                    s.connected = False
            slot.is_human = True
            slot.player_sid = player_sid
            slot.connected = True
            logger.info(f"切换槽位: {player_sid} → {agent_id} ({room_id})")
            return slot, None

    def toggle_slot_ai(self, room_id: str, host_sid: str, agent_id: str, make_ai: bool):
        with self._lock:
            room = self.rooms.get(room_id)
            if not room:
                return None, "房间不存在"
            if room.host_sid != host_sid:
                return None, "只有房主可操作"
            slot = room.slots.get(agent_id)
            if not slot:
                return None, "无效槽位"
            if make_ai and agent_id == room.host_agent_id:
                return None, "不能移除房主槽位"
            if make_ai:
                slot.is_human = False
                slot.player_sid = ""
                slot.player_name = ""
                slot.connected = False
            else:
                slot.is_human = True
            return slot, None

    def leave_room(self, room_id: str, player_sid: str):
        with self._lock:
            room = self.rooms.get(room_id)
            if not room:
                return
            for slot in room.slots.values():
                if slot.player_sid == player_sid:
                    name = slot.player_name or player_sid
                    slot.connected = False
                    if room.phase == "lobby":
                        slot.is_human = False
                        slot.player_sid = ""
                        slot.player_name = ""
                    logger.info(f"离开: {name} ({room_id})")
                    break

    def get_human_slots(self, room_id: str) -> list[PlayerSlot]:
        room = self.rooms.get(room_id)
        if not room:
            return []
        return [s for s in room.slots.values() if s.is_human]

    def get_connected_slots(self, room_id: str) -> list[PlayerSlot]:
        return [s for s in self.get_human_slots(room_id) if s.connected]

    def destroy_room(self, room_id: str):
        with self._lock:
            if room_id in self._window_timers:
                self._window_timers[room_id].cancel()
                del self._window_timers[room_id]
            self.rooms.pop(room_id, None)
            self.sessions.pop(room_id, None)
            self._pending_intents.pop(room_id, None)
            logger.info(f"房间销毁: {room_id}")

    # ========== Game Startup ==========

    def start_game(self, room_id: str, host_sid: str):
        with self._lock:
            room = self.rooms.get(room_id)
            if not room:
                return None, "房间不存在"
            if room.host_sid != host_sid:
                return None, "只有房主可开始"
            connected = self.get_connected_slots(room_id)
            if not connected:
                return None, "没有玩家"
            room.phase = "playing"

        gs = GameSession(scene_id=room.scene_id)
        for slot in room.slots.values():
            if slot.is_human and slot.connected:
                st = gs.agent_states.get(slot.agent_id)
                if st:
                    st.is_human = True
                    st.busy_until = 0

        first = connected[0]
        gs.player_name = first.player_name
        gs.player_location = gs.scenario.get("start_room", "")

        with self._lock:
            self.sessions[room_id] = gs

        human_cnt = len(connected)
        logger.info(f"游戏开始: {room_id} 场景={room.scene_id} 真人={human_cnt} AI={12-human_cnt}")
        return room, None

    # ========== Time Window ==========

    def open_time_window(self, room_id: str):
        with self._lock:
            room = self.rooms.get(room_id)
            gs = self.sessions.get(room_id)
            if not room or not gs or room.phase != "playing":
                return

        for slot in room.slots.values():
            slot.ready = False
        self._pending_intents[room_id] = {}

        for slot in self.get_connected_slots(room_id):
            self._send_intent_request(room_id, slot, gs)
        self._start_window_timer(room_id)

        if self._sio:
            self._sio.emit("window_start", {
                "window_minutes": room.window_minutes,
                "day": gs.world.current_day,
                "time": gs.world.current_time,
                "time_minutes": gs.world.time_minutes,
            }, room=room_id)

    def _send_intent_request(self, room_id: str, slot: PlayerSlot, gs: GameSession):
        agent_id = slot.agent_id
        agent = gs.agents.get(agent_id)
        if not agent:
            return
        p = agent.perceive(gs.world)
        loc = gs.world.npc_locations.get(agent_id, "")

        nearby = []
        for aid, aloc in gs.world.npc_locations.items():
            if aloc == loc and aid != agent_id:
                char = gs.arbiter._characters.get(aid)
                name = char.name if char else aid
                st = gs.agent_states.get(aid)
                alive = st.alive if st else True
                nearby.append({"id": aid, "name": name, "alive": alive})

        recent = []
        for evt in gs.world.public_events[-6:]:
            if agent_id in evt.witnesses or evt.location == loc:
                recent.append({
                    "desc": (evt.full_description or evt.public_description)[:150],
                    "actor": evt.actor_id,
                    "loc": evt.location,
                })

        aff_map = {}
        for k, v in p.affection_snapshot.items():
            if k != agent_id:
                aff_map[k] = v

        if self._sio:
            self._sio.emit("intent_request", {
                "agent_id": agent_id,
                "agent_name": agent.profile.name,
                "location": loc,
                "nearby_npcs": nearby,
                "recent_events": recent,
                "emotional_state": p.emotional_state,
                "threat_level": p.threat_level,
                "affection_snapshot": aff_map,
                "day": gs.world.current_day,
                "time": gs.world.current_time,
                "time_minutes": gs.world.time_minutes,
                "window_minutes": self.rooms[room_id].window_minutes,
            }, room=slot.player_sid)

    def _start_window_timer(self, room_id: str):
        room = self.rooms.get(room_id)
        if not room:
            return
        if room_id in self._window_timers:
            self._window_timers[room_id].cancel()
        t = threading.Timer(room.intent_timeout, self._on_window_timeout, args=[room_id])
        t.daemon = True
        self._window_timers[room_id] = t
        t.start()

    def _on_window_timeout(self, room_id: str):
        room = self.rooms.get(room_id)
        if not room or room.phase != "playing":
            return
        missing = [s.agent_id for s in self.get_connected_slots(room_id) if not s.ready]
        if missing:
            logger.info(f"窗口超时，未提交: {missing} ({room_id})")
        self._resolve_window(room_id)

    def submit_intent(self, room_id: str, player_sid: str, intent_data: dict):
        with self._lock:
            room = self.rooms.get(room_id)
            if not room or room.phase != "playing":
                return False, "游戏未进行"
            slot = None
            for s in room.slots.values():
                if s.player_sid == player_sid:
                    slot = s
                    break
            if not slot:
                return False, "未找到角色"

            it = (intent_data.get("intent_type") or "rest").lower()
            action = PlayerAction(
                agent_id=slot.agent_id,
                intent_type=it,
                target_id=intent_data.get("target_id") or None,
                target_location=intent_data.get("target_location") or None,
                reasoning=intent_data.get("reasoning", ""),
                dialogue=intent_data.get("dialogue", ""),
                prose=intent_data.get("prose", ""),
                internal=intent_data.get("internal", ""),
                risk=intent_data.get("risk", ""),
                scene_hint=intent_data.get("scene_hint", ""),
                estimated_duration=int(intent_data.get("duration", 10)),
            )
            self._pending_intents.setdefault(room_id, {})[slot.agent_id] = [action]
            slot.ready = True
            logger.info(f"意图: {slot.agent_id}({slot.player_name}) → {it}")

        if self._sio:
            self._sio.emit("intent_confirmed", {
                "agent_id": slot.agent_id,
                "intent_type": it,
            }, room=player_sid)

        # Broadcast ready status
        self._broadcast_ready_status(room_id)

        if self._all_ready(room_id):
            if room_id in self._window_timers:
                self._window_timers[room_id].cancel()
            threading.Thread(target=self._resolve_window, args=(room_id,), daemon=True).start()

        return True, None

    def _all_ready(self, room_id: str) -> bool:
        room = self.rooms.get(room_id)
        if not room:
            return False
        return all(s.ready for s in self.get_connected_slots(room_id))

    def _broadcast_ready_status(self, room_id: str):
        room = self.rooms.get(room_id)
        if not room or not self._sio:
            return
        status = []
        for s in self.get_human_slots(room_id):
            status.append({
                "agent_id": s.agent_id,
                "player_name": s.player_name,
                "connected": s.connected,
                "ready": s.ready,
            })
        self._sio.emit("ready_status", {"players": status}, room=room_id)

    # ========== Window Resolution ==========

    def _resolve_window(self, room_id: str):
        with self._lock:
            room = self.rooms.get(room_id)
            gs = self.sessions.get(room_id)
            if not room or not gs:
                return

        window_min = room.window_minutes
        pending = self._pending_intents.get(room_id, {})
        logger.info(f"窗口解析: {room_id}, {len(pending)} 真人意图, +{window_min}min")

        # 1. 推进时间
        gs._advance_time(window_min)

        # 2. 真人意图转 Intent
        all_intents: dict[str, list[Intent]] = {}
        for aid, actions in pending.items():
            for a in actions:
                all_intents.setdefault(aid, []).append(a.to_intent())

        # 3. AI 意图 (并发)
        ai_ids = [aid for aid in gs.agents
                  if gs.agent_states[aid].alive and not gs.agent_states[aid].is_human]
        if ai_ids:
            with ThreadPoolExecutor(max_workers=8) as ex:
                fut_map = {ex.submit(gs.agents[aid].decide, gs.world): aid for aid in ai_ids}
                for f in as_completed(fut_map):
                    aid = fut_map[f]
                    try:
                        all_intents[aid] = f.result()
                    except Exception as e:
                        logger.warning(f"AI {aid} 决策失败: {e}")
                        all_intents[aid] = [Intent(agent_id=aid, intent_type=IntentType.REST,
                                                   reasoning="暂不行动")]

        # 4. Arbiter
        rulings = gs.arbiter.process_round(all_intents, gs.agent_states, gs.world)
        gs._check_body_discovery(all_intents)

        # 5. NPC 对话记录
        for aid, il in all_intents.items():
            agent = gs.agents.get(aid)
            if not agent:
                continue
            for intent in il:
                if intent.intent_type in (IntentType.SOCIALIZE, IntentType.CONFRONT) and \
                   intent.target_id and intent.dialogue:
                    target_agent = gs.agents.get(intent.target_id)
                    entry = {"speaker": aid, "content": intent.dialogue.strip("「」"),
                            "tick": gs.world.global_tick}
                    agent._chat_history.append(entry)
                    agent._chat_history = agent._chat_history[-10:]
                    if target_agent:
                        target_agent._chat_history.append(entry)
                        target_agent._chat_history = target_agent._chat_history[-10:]

        # 6. 每玩家叙事 (并发)
        connected = self.get_connected_slots(room_id)
        materials = self._build_materials(rulings)
        if connected:
            with ThreadPoolExecutor(max_workers=min(8, len(connected))) as ex:
                for slot in connected:
                    ex.submit(self._generate_player_narrative, room_id, gs, slot, rulings, materials)

        # 7. 每玩家选项
        for slot in connected:
            self._generate_player_options(room_id, gs, slot, rulings)

        # 8. 广播 round_end
        self._broadcast_round_end(room_id, gs)

        # 9. 新窗口
        self.open_time_window(room_id)

    def _build_materials(self, rulings: list[Ruling]) -> str:
        if not rulings:
            return "暂无事件"
        parts = []
        for r in rulings[:10]:
            parts.append(f"{r.intent.agent_id}: {r.intent.intent_type.value} → {r.description[:80]}")
        return "\n".join(parts)

    def _filter_visible_rulings(self, agent_id: str, loc: str,
                                 rulings: list[Ruling], world: WorldState) -> list[Ruling]:
        visible = []
        for r in rulings:
            intent = r.intent
            actor_loc = world.npc_locations.get(intent.agent_id, "")
            if intent.agent_id == agent_id:
                visible.append(r)
            elif intent.target_id == agent_id:
                visible.append(r)
            elif actor_loc == loc:
                visible.append(r)
            elif intent.intent_type in (IntentType.ATTACK, IntentType.TRAP) and r.success:
                visible.append(r)
            elif intent.intent_type == IntentType.CONFRONT and r.success:
                witnesses = [a for a, al in world.npc_locations.items()
                            if al == actor_loc and a not in (intent.agent_id, intent.target_id)]
                if len(witnesses) >= 2:
                    visible.append(r)
        return visible

    def _generate_player_narrative(self, room_id: str, gs: GameSession,
                                    slot: PlayerSlot, rulings: list[Ruling], materials: str):
        agent_id = slot.agent_id
        loc = gs.world.npc_locations.get(agent_id, "")
        visible = self._filter_visible_rulings(agent_id, loc, rulings, gs.world)
        mat = self._build_materials(visible)

        try:
            narrative = ""
            for chunk in gs.gm.stream_narrative_for_agent(
                agent_id=agent_id, rulings=visible, world=gs.world,
                agent_states=gs.agent_states, location=loc, materials=mat,
            ):
                narrative += chunk
                if self._sio:
                    self._sio.emit("narrative_chunk", {"text": chunk}, room=slot.player_sid)
            if self._sio:
                self._sio.emit("narrative_done", {"text": narrative, "agent_id": agent_id},
                               room=slot.player_sid)
        except Exception as e:
            logger.error(f"叙事失败 {agent_id}: {e}")
            if self._sio:
                self._sio.emit("narrative_done", {"text": "一切如常。", "agent_id": agent_id},
                               room=slot.player_sid)

    def _generate_player_options(self, room_id: str, gs: GameSession,
                                  slot: PlayerSlot, rulings: list[Ruling]):
        agent_id = slot.agent_id
        loc = gs.world.npc_locations.get(agent_id, "")
        visible = self._filter_visible_rulings(agent_id, loc, rulings, gs.world)
        try:
            options = gs.gm.generate_options_for_agent(
                agent_id=agent_id, rulings=visible, world=gs.world,
                agent_states=gs.agent_states, location=loc,
            )
        except Exception as e:
            logger.error(f"选项失败 {agent_id}: {e}")
            options = [
                {"label": "观察周围", "type": "investigate", "target": None, "room": None},
                {"label": "与附近的人交谈", "type": "dialogue", "target": None, "room": None},
                {"label": "移动到其他地方", "type": "explore", "target": None, "room": None},
                {"label": "（自由行动）", "type": "custom", "target": None, "room": None},
            ]
        if self._sio:
            self._sio.emit("player_options", {"agent_id": agent_id, "options": options},
                           room=slot.player_sid)

    def _broadcast_round_end(self, room_id: str, gs: GameSession):
        room = self.rooms.get(room_id)
        if not room:
            return
        for slot in self.get_connected_slots(room_id):
            aid = slot.agent_id
            loc = gs.world.npc_locations.get(aid, "")
            npcs = []
            for _aid, _aloc in gs.world.npc_locations.items():
                if _aid == aid:
                    continue
                st = gs.agent_states.get(_aid)
                if not st or not st.alive:
                    continue
                char = gs.arbiter._characters.get(_aid)
                npcs.append({
                    "agent_id": _aid,
                    "name": char.name if char else _aid,
                    "location": _aloc,
                    "nearby": _aloc == loc,
                    "emotion": st.emotional_state,
                    "alive": st.alive,
                    "is_human": st.is_human,
                })
            if self._sio:
                self._sio.emit("round_end", {
                    "agent_id": aid, "day": gs.world.current_day,
                    "time": gs.world.current_time,
                    "time_minutes": gs.world.time_minutes,
                    "location": loc, "npcs": npcs,
                    "phase": gs.world.phase.value,
                    "alive_count": len(gs.world.alive_npcs),
                }, room=slot.player_sid)

    # ========== Player Dialogue ==========

    def player_dialogue(self, room_id: str, player_sid: str, target_id: str, message: str):
        room = self.rooms.get(room_id)
        gs = self.sessions.get(room_id)
        if not room or not gs:
            return None, "游戏不存在"

        speaker_slot = None
        for s in room.slots.values():
            if s.player_sid == player_sid:
                speaker_slot = s
                break
        if not speaker_slot:
            return None, "未找到角色"

        speaker_id = speaker_slot.agent_id
        speaker_agent = gs.agents.get(speaker_id)
        if not speaker_agent:
            return None, "角色不存在"

        speaker_loc = gs.world.npc_locations.get(speaker_id, "")
        target_loc = gs.world.npc_locations.get(target_id, "")
        if speaker_loc != target_loc:
            return None, "目标不在同一房间"

        # 真人 → 真人
        target_slot = None
        for s in room.slots.values():
            if s.agent_id == target_id and s.is_human and s.connected:
                target_slot = s
                break

        if target_slot:
            speaker_name = speaker_agent.profile.name
            if self._sio:
                self._sio.emit("dialogue_received", {
                    "from_agent": speaker_id,
                    "from_name": speaker_name,
                    "message": message,
                    "to_agent": target_id,
                }, room=target_slot.player_sid)
            return f"（你对 {target_id} 说：{message}）", None

        # 真人 → NPC
        target_agent = gs.agents.get(target_id)
        if not target_agent:
            return None, "目标不存在"

        ctx = f"位置: {speaker_loc}, 第{gs.world.current_day}天 {gs.world.current_time}"
        sname = speaker_agent.profile.name
        resp = target_agent.dialogue(ctx, sname, message, speaker_id)

        entry = {"speaker": speaker_id, "content": message, "tick": gs.world.global_tick}
        speaker_agent._chat_history.append(entry)
        target_agent._chat_history.append(entry)
        speaker_agent._chat_history = speaker_agent._chat_history[-10:]
        target_agent._chat_history = target_agent._chat_history[-10:]

        return resp, None


mp_manager = MultiplayerManager()
