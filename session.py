"""
Astral -- GameSession core v0.5
GameSession class + module-level singleton
"""
from __future__ import annotations
import json, os, sys, re, queue, threading, time, random, traceback
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from state import (WorldState, AgentState, Intent, Event, Evidence,
                   IntentType, GamePhase, DifficultyMode, TrialState,
                   BodyRecord, DEAD_NPC, roll_risk)
from llm import LLMClient
from agent_engine import NPCAgent
from arbiter import Arbiter
from gm import GMNarrator
from save_manager import SaveManager
from debug import AgentLogger
from card_manager import list_cards, save_card, delete_card, parse_card, get_card
from prologue_engine import PrologueEngine
import scenarios
from config_profiles import (list_profiles as _lcp, save_profile as _scp,
                             activate as _acp, delete_profile as _dcp,
                             get_active as _gac, apply_to_llm as _alc,
                             apply_to_all_llms as _aal, PROFILES_PATH as _PFP)

def _parse_time(t: str) -> int|None:
    m = re.match(r'(上午|下午|晚上|中午)(\d+)点', t)
    if not m: return None
    label, h = m.group(1), m.group(2)
    hour = int(h)
    if label == "下午" and hour != 12: hour += 12
    elif label == "晚上": hour += 12
    elif label == "中午": hour = 12
    return hour

def _format_time(hour: int) -> str:
    if hour < 6 or hour >= 22: return f"晚上{hour}点"
    elif hour < 12: return f"上午{hour}点"
    elif hour == 12: return "中午12点"
    else: return f"下午{hour-12}点"

def _time_string(minutes: int) -> str:
    """分钟数 → 显示时间字符串，如 420 → '上午7点'。"""
    hour = minutes // 60
    minute = minutes % 60
    if hour < 6 or hour >= 22:
        label = "晚上"
        if hour >= 22:
            hour = hour - 12
    elif hour == 12:
        label = "中午"
    elif hour < 12:
        label = "上午"
    else:
        label = "下午"
        hour = hour - 12
    if hour == 0:
        hour = 12
    if minute == 0:
        return f"{label}{hour}点"
    return f"{label}{hour}点{minute}分"
class GameSession:
    def __init__(self, scene_id: str = ""):
        if not scene_id: scene_id = "tianji_maze"
        self.scene_id = scene_id
        self.scenario = scenarios.load(scene_id)
        self.logger = AgentLogger()
        self._lock = threading.Lock()
        self.prologue = PrologueEngine()
        self._pending_player_dialogues: list[dict] = []

        self.llm = LLMClient("")
        self.agent_llm = LLMClient("")
        self.gm_llm = LLMClient("")
        self.arbiter_llm = LLMClient("")
        self._load_llm_config()
        self.world = WorldState()
        self.agents: dict[str, NPCAgent] = {}
        self.agent_states: dict[str, AgentState] = {}
        self.npc_ids = self.scenario.get("npc_ids", [f"No.{i:02d}" for i in range(1,13)])
        scene_chars = self._resolve_characters()
        self.arbiter = Arbiter(self.arbiter_llm, characters=scene_chars)
        self.gm = GMNarrator(self.gm_llm, scene_id=scene_id, characters=scene_chars)
        self.save_mgr = SaveManager()
        self.player_name = ""
        self.player_location = self.scenario.get("start_room", "")
        self.player_created = False
        self.player_age = "16"
        self.player_appearance = ""
        self.round_count = 0
        self.last_narrative = None
        self.last_options = []
        self.narrative_log: list[dict] = []
        self._init_agents(scene_chars)

    def _load_llm_config(self):
        ok = _aal(self.llm, self.agent_llm, self.gm_llm)
        self._sync_arbiter_llm()
        if not ok:
            self._migrate_old_config()
            _aal(self.llm, self.agent_llm, self.gm_llm)
            self._sync_arbiter_llm()

    def _sync_arbiter_llm(self):
        """将 arbiter_llm 与 gm_llm 同步（arbiter 复用 gm 的基础配置，模型可独立覆盖）"""
        cfg = _gac()
        if cfg:
            self.arbiter_llm.base_url = self.gm_llm.base_url
            self.arbiter_llm.api_key = self.gm_llm.api_key
            self.arbiter_llm.model = cfg.get("arbiter_model", "").strip() or cfg.get("gm_model", "").strip() or cfg.get("model", "").strip()
            self.arbiter_llm.default_temperature = self.gm_llm.default_temperature
            self.arbiter_llm.default_top_p = self.gm_llm.default_top_p
            self.arbiter_llm.close()

    @staticmethod
    def _migrate_old_config():
        old = os.path.join(os.path.dirname(__file__), "config.json")
        if os.path.exists(_PFP): return
        if not os.path.exists(old): return
        try:
            import json as _j
            with open(old,"r",encoding="utf-8") as f: c=_j.load(f)
            name = c.get("model_name","default").strip() or "default"
            _scp(name, c.get("api_base_url",""), c.get("api_key",""), c.get("model_name",""))
            _acp(name)
            os.remove(old)
        except: pass

    def _resolve_characters(self) -> dict:
        """加载场景角色 → NPC_cards 富角色卡覆盖 → 返回最终角色字典"""
        scene_chars = dict(self.scenario.get("characters", {}) or {})
        scene_name = self.scenario.get("name", "") if self.scenario else ""
        if scene_name:
            from card_manager import load_all_npc_library_cards
            from characters import from_rich_card
            lib_cards = load_all_npc_library_cards(scene_name, self.npc_ids)
            if lib_cards:
                for aid, card in lib_cards.items():
                    try:
                        scene_chars[aid] = from_rich_card(card, agent_id=aid)
                    except Exception:
                        pass
        if scene_chars:
            self.scenario["characters"] = scene_chars
        return scene_chars

    def _init_agents(self, scene_chars=None):
        if scene_chars is None:
            scene_chars = self._resolve_characters()
        init_aff = 25 if self.world.difficulty == DifficultyMode.WITCH else 15
        if self.scene_id != "tianji_maze":
            self.world.floor_2_unlocked = True
            self.world.floor_3_unlocked = True

        for aid in self.npc_ids:
            agent = NPCAgent(aid, self.agent_llm, characters=scene_chars, player_name=self.player_name)
            self.agents[aid] = agent
            self.agent_states[aid] = agent.state
            self.world.npc_locations[aid] = self.player_location
            for other_id in self.npc_ids:
                if other_id != aid: agent.state.affection_map[other_id] = init_aff
            agent.state.affection_map["player"] = init_aff
        self.agent_states["player"] = AgentState(agent_id="player", name="玩家")
        self._init_room_items()

    def _init_room_items(self):
        for room, features in self.scenario.get("room_features", {}).items():
            items = {f["name"]: "存在" for f in features}
            self.world.room_item_state[room] = items

    def _log(self, typ: str, text: str, **extra):
        entry = {"type": typ, "text": text}
        if extra: entry.update(extra)
        self.narrative_log.append(entry)

    def _safe_llm(self, msgs, sys, temp=1.0, mt=2048):
        try:
            return self.llm.chat(messages=msgs, system=sys, temperature=temp, max_tokens=mt)
        except Exception as e1:
            if len(sys) > 500:
                try: return self.llm.chat(messages=msgs, system="你是旁白。第三人称。", temperature=temp, max_tokens=mt)
                except: pass
            try: return self.llm.chat(messages=msgs, system=None, temperature=temp, max_tokens=mt)
            except Exception as e3:
                emsg = str(e3)[:200]
                if hasattr(self,'logger'): self.logger.log_arbiter([f"LLM ERROR: {emsg}"])
                return f"(API 调用失败：{emsg}。请检查网络、API Key 或模型名是否正确。)"

    def _pgm(self) -> str:
        if self.scenario and self.scenario.get("gm_prompt"):
            return self.scenario.get("gm_prompt")
        return """你是故事旁白。严格遵守以下规则：
1. 只描述玩家能直接看到或听到的内容，不做全知视角叙述。
2. 不要编造未发生的事件。如果无事发生，描述环境氛围即可。
3. 不要透露任何 NPC 的秘密、动机或内心想法。
4. 不要赋予 NPC 其档案中没有的能力、物品或关系。
5. 用外貌特征称呼尚未自我介绍的陌生 NPC（如"银发少女"），但 NPC 在对话中自然互报姓名、做自我介绍是正常的社交行为。
6. 所有描写必须严格基于【当前房间设施】。
7. 不要引入超自然元素（除非场景设定明确允许）。
8. 叙事简洁，每次 3-5 句即可。"""

    def _roster(self) -> str:
        chars = self.scenario.get("characters", {}) if self.scenario else {}
        names = [c.name for _, c in sorted(chars.items())]
        return "、".join(names) if names else "无"

    # === Prologue delegation ===

    def prologue_step_1_mirror(self, name, age, appearance):
        return self.prologue.step_1_mirror(
            self.llm, self._log, self.scenario, self.world, self.agent_states, self._log,
            name, age, appearance,
            lambda n, a, ap: (
                setattr(self, 'player_name', n),
                setattr(self, 'player_age', a),
                setattr(self, 'player_appearance', ap),
                setattr(self, 'player_location', self.scenario.get("start_room", ""))
            )
        )

    def prologue_step_2_magic(self, magic):
        return self.prologue.step_2_magic(self.llm, self._log, self.scenario, self.world, magic)

    def prologue_step_3_difficulty(self, mode):
        return self.prologue.step_3_difficulty(self.llm, self._log, self.scenario, self.world, mode)

    def prologue_step_4_camp(self):
        self.player_created = True
        self.player_location = self.scenario.get("start_room", "")
        return self.prologue.step_4_camp(
            self.llm, self._log, self.scenario, self.world,
            self.player_name, self.player_location
        )

    def prologue_continue(self, player_choice: str):
        return self.prologue.continue_(
            self.llm, self._log, self.scenario, self.world, self.scene_id,
            self.player_name, self.player_location, self._log,
            player_choice
        )

    def prologue_finish(self):
        return self.prologue.finish(
            self.llm, self.world, self.scenario, self.npc_ids,
            self.agent_states, self.agents, self._log
        )

    # === Dialogue Suggestions ===

    def _gen_dialogue_suggestions(self, agent_id: str, player_name: str = "") -> list[str]:
        if agent_id not in self.agents: return ["你好。","你还好吗？","能聊聊吗？"]
        agent = self.agents[agent_id]
        profile = agent.profile
        st = self.agent_states.get(agent_id)
        # 构建上下文
        parts = []
        met = agent_id in self.world.player_met_npcs
        display_name = profile.name if met else getattr(profile, 'appearance', '某人')
        parts.append(f"玩家：{player_name or '玩家'}")
        parts.append(f"NPC：{display_name}（{profile.personality or '性格未知'}）")
        parts.append(f"位置：{self.world.npc_locations.get(agent_id, '未知')}")
        parts.append(f"时间：第{self.world.current_day}天 {self.world.current_time}")
        if self.world.last_narrative_summary:
            parts.append(f"【最近剧情】{self.world.last_narrative_summary[:300]}")
        if st:
            aff = st.affection_map.get("player", 50)
            parts.append(f"对玩家的好感度：{aff}/100")
            if st.emotional_state:
                parts.append(f"当前情绪：{st.emotional_state}")
        # 最近对话历史（含玩家或NPC间的互动）
        recent = getattr(agent, '_chat_history', [])[-3:]
        if recent:
            parts.append("最近对话：" + "；".join([f"{d.get('speaker','?')}:{d.get('content','')[:60]}" for d in recent]))
        # 该NPC目击的最近公共事件
        loc = self.world.npc_locations.get(agent_id, "")
        visible = [e.public_description[:100] for e in self.world.public_events[-6:]
                    if loc and (agent_id in getattr(e, 'witnesses', []) or getattr(e, 'location', '') == loc)]
        if visible:
            parts.append("近期周围事件：" + "；".join(visible[-2:]))
        prompt = "\n".join(parts) + f"""\n\n请为{player_name or '玩家'}生成3个简洁自然的对话选项，可以对{display_name}说。贴近当前关系、情境和剧情。输出 JSON：{{"suggestions":["...","...","..."]}} 只输出 JSON。"""
        try:
            result = self.llm.chat_json(messages=[{"role":"user","content":prompt}], temperature=0.8, max_tokens=512)
            suggestions = result.get("suggestions",[])
            return suggestions[:3] if len(suggestions) >= 3 else suggestions + ["你还好吗？","能聊聊吗？"][:3-len(suggestions)]
        except: return ["你好。","你还好吗？","能聊聊吗？"]

    # === Game Loop ===

    def run_round(self, progress_queue: queue.Queue, elapsed_minutes: int = 60):
        self.round_count += 1
        self.world.global_tick += 1
        self._advance_time(elapsed_minutes)
        if elapsed_minutes >= 60:
            self._log("system", f"round_start elapsed={elapsed_minutes}min")
        self.world.npc_locations["player"] = self.player_location
        progress_queue.put({"type":"round_start","round":self.round_count,"day":self.world.current_day,"time":self.world.current_time})
        self._check_floor_unlock()
        self.world.atmosphere = self._atmosphere()
        self._settle_player_affection()

        # 1. Agent 决策
        intents: dict[str, list] = {}
        completed = 0
        total = len(self.agents)
        try:
            with ThreadPoolExecutor(max_workers=8) as executor:
                future_to_aid = {executor.submit(agent.decide, self.world): aid for aid, agent in self.agents.items() if self.agent_states.get(aid, DEAD_NPC).alive}
                for future in as_completed(future_to_aid):
                    aid = future_to_aid[future]
                    intent_list = future.result()
                    intents[aid] = intent_list
                    completed += 1
                    cp = self.agents[aid].profile
                    main = intent_list[0] if intent_list else Intent(agent_id=aid, intent_type=IntentType.REST, reasoning="")
                    if self.logger: self.logger.log_decision(aid, cp.name, main.intent_type.value, main.target_id or "", main.reasoning, (self.agent_states[aid].emotional_state if aid in self.agent_states else ""))
                    progress_queue.put({"type":"agent_done","agent_id":aid,"name":cp.name,"intent":main.intent_type.value,"target":main.target_id or "","completed":completed,"total":total})
        except Exception as e:
            raise RuntimeError(f"Agent决策失败: {e}\n{traceback.format_exc()}") from e

        # 2. 仲裁
        if self.world.current_day == 1:
            for aid, il in intents.items():
                for intent in il:
                    if intent.intent_type == IntentType.ATTACK: intent.intent_type = IntentType.CONFRONT

        # 剧情模式：禁止一切恶意行为
        if self.world.difficulty == DifficultyMode.STORY:
            for aid, il in intents.items():
                for intent in il:
                    if intent.intent_type in (IntentType.ATTACK, IntentType.TRAP, IntentType.SABOTAGE):
                        intent.intent_type = IntentType.CONFRONT

        progress_queue.put({"type":"arbiter_start"})
        try:
            rulings = self.arbiter.process_round(intents, self.agent_states, self.world)
        except Exception as e:
            raise RuntimeError(f"Arbiter仲裁失败: {e}\n{traceback.format_exc()}") from e

        self.world.rounds_since_last_murder += 1
        murder_events = []
        first_delay_active = self.world.current_day == 1 and self.world.first_murder_delayed
        for r in rulings:
            if r.intent.intent_type in (IntentType.ATTACK, IntentType.TRAP) and r.success and not first_delay_active:
                victim = r.intent.target_id
                if victim:
                    evt = Event(tick=self.world.global_tick, event_type="murder", actor_id=r.intent.agent_id, victim_id=victim, location=self.world.npc_locations.get(victim,""), public_description=r.description, is_murder=True)
                    self.world.public_events.append(evt)
                    murder_events.append(evt)
                    if victim in self.agent_states: self.agent_states[victim].alive = False; self.world.alive_npcs.discard(victim)
                    # 提取藏尸位置：从 intent prose 或 room features 推断
                    hiding = r.intent.prose or r.intent.reasoning or ""
                    if not hiding or len(hiding) < 3:
                        rf = self.scenario.get("room_features", {}).get(self.world.npc_locations.get(victim,""), []) if self.scenario else []
                        hiding = (rf[0].get("name","") if rf else "") + "旁" if rf else ""
                    br = BodyRecord(victim_id=victim, actor_id=r.intent.agent_id, location=self.world.npc_locations.get(victim,""), hiding_spot=hiding[:80], tick=self.world.global_tick)
                    self.world.undiscovered_bodies.append(br)

        self._check_body_discovery(intents)

        # 写入 NPC-NPC 对话到 chat_history
        for ruling in rulings:
            intent = ruling.intent
            if not ruling.success: continue
            if not intent.dialogue: continue
            if intent.intent_type not in (IntentType.SOCIALIZE, IntentType.CONFRONT, IntentType.ATTACK):
                continue
            entry = {
                "speaker": intent.agent_id,
                "listener": intent.target_id or "",
                "content": intent.dialogue[:200],
                "tick": self.world.global_tick,
            }
            # 写入说话者
            actor_agent = self.agents.get(intent.agent_id)
            if actor_agent:
                actor_agent._chat_history.append(entry)
                if len(actor_agent._chat_history) > 10:
                    actor_agent._chat_history = actor_agent._chat_history[-10:]
            # 写入目标
            if intent.target_id and intent.target_id in self.agents:
                listener_agent = self.agents[intent.target_id]
                listener_agent._chat_history.append(entry)
                if len(listener_agent._chat_history) > 10:
                    listener_agent._chat_history = listener_agent._chat_history[-10:]

        npc_approaches = []
        for aid, il in intents.items():
            for intent in il:
                if intent.intent_type == IntentType.SOCIALIZE and intent.target_id == "player":
                    if aid in self.agents and self.agent_states.get(aid, DEAD_NPC).alive:
                        npc = self.agents[aid]
                        met = aid in self.world.player_met_npcs
                        self.world.player_met_npcs.add(aid)
                        npc_approaches.append({"agent_id":aid,"agent_name":npc.profile.name if met else getattr(npc.profile,'appearance','某人'),"suggestions":self._gen_dialogue_suggestions(aid, self.player_name),"opener":intent.scene_hint})
            if npc_approaches: break
        if npc_approaches: progress_queue.put({"type":"npc_approaches","npcs":npc_approaches})
        _approach_notes = [f"{na['agent_name']}走向玩家，想要交谈" for na in npc_approaches]

        ruling_list = []
        for r in rulings:
            an = self.agents[r.intent.agent_id].profile.name if r.intent.agent_id in self.agents else r.intent.agent_id
            ruling_list.append({"agent_id":r.intent.agent_id,"agent_name":an,"intent":r.intent.intent_type.value,"approved":r.approved,"success":r.success,"description":r.description[:120],"downgraded":r.downgraded_to.value if r.downgraded_to else None})
        progress_queue.put({"type":"arbiter_done","rulings":ruling_list})
        for r in ruling_list:
            status = "✓" if r["success"] else "✗"
            self._log("system", f"{status} {r['agent_name']}: {r['description']}"+(f"→{r['downgraded']}" if r.get('downgraded') else ""))

        if self.logger: self.logger.log_arbiter([f"{r['agent_name']}:{r['intent']}({'OK' if r['success'] else 'FAIL'})" for r in ruling_list])

        social_facts = []
        for r in rulings:
            if r.intent.intent_type == IntentType.SOCIALIZE and r.success and r.intent.target_id:
                if r.intent.target_id in self.agents and r.intent.agent_id in self.agents and self.agent_states.get(r.intent.agent_id, DEAD_NPC).alive and self.agent_states.get(r.intent.target_id, DEAD_NPC).alive:
                    a1 = self.agents[r.intent.agent_id]; a2 = self.agents[r.intent.target_id]
                    social_facts.append(f"{a1.profile.name}与{a2.profile.name}进行了交谈")

        progress_queue.put({"type":"narrative_start"})
        self.gm._social_facts = social_facts + _approach_notes
        self.gm._social_facts.append(self._atmosphere())
        bcast = getattr(self, 'xbrdcst', None)
        if bcast: self.gm._social_facts.append(bcast); self.xbrdcst = None
        full_text = ""
        try:
            materials = self.arbiter._build_narrative_materials(rulings)
            for chunk in self.gm.stream_narrative(rulings, self.world, self.agent_states, self.player_location, materials=materials, player_action=""):
                full_text += chunk
                progress_queue.put({"type":"narrative_chunk","text":chunk})
        except Exception as e:
            progress_queue.put({"type":"narrative_chunk","text":"（推演受阻，请稍后重试。）"})
            self._log("system", f"GM叙事生成失败: {e}")
        progress_queue.put({"type":"options_start"})
        try:
            options = self.gm.generate_options(full_text, rulings, self.world, self.agent_states, self.player_location)
        except Exception as e:
            self._log("system", f"选项生成失败: {e}")
            options = [{"label": "继续观察周围", "type": "investigate", "target": None, "room": None},
                       {"label": "与附近的人交谈", "type": "custom", "target": None, "room": None},
                       {"label": "探索这个区域", "type": "custom", "target": None, "room": None},
                       {"label": "（自定义行动）", "type": "custom", "target": None, "room": None}]
        self.last_narrative = full_text
        self.last_options = options
        self.world.last_narrative_summary = full_text if full_text else ""

        # 结局检查
        ending_data = self._check_ending_trigger()
        if ending_data:
            progress_queue.put({"type": "ending_triggered", **ending_data})

        for f in social_facts: self._log("system", f"💬 {f}")
        self._log("gm", full_text)

        if self.logger: self.logger.log_narrative(full_text)

        progress_queue.put({"type":"narrative_done","text":full_text,"options":options})

        _npc_list = [{"agent_id":aid,"name":self.agents[aid].profile.name if aid in self.world.player_met_npcs else "？","affection":self.agent_states[aid].affection_map.get("player",50) if aid in self.agent_states else 50,"location":self.world.npc_locations.get(aid,""),"nearby":self.world.npc_locations.get(aid,"")==self.player_location,"alive":self.agent_states.get(aid,DEAD_NPC).alive,"emotion":self.agent_states[aid].emotional_state if aid in self.agent_states else ""} for aid in sorted(self.agents.keys())]
        _scene_label = self.scenario.get("name", self.scene_id) if self.scenario else self.scene_id
        progress_queue.put({"type":"round_end","scene_name":_scene_label,"day":self.world.current_day,"time":self.world.current_time,"phase":self.world.phase.value,"location":self.player_location,"floor":self.world.current_floor,"in_trial":bool(self.world.active_trial and self.world.active_trial.active),"alive_count":len(self.world.alive_npcs),"rule_text":"","time_event":getattr(self,'xbrdcst',None),"npcs":_npc_list,"ending_triggered":self.world.ending_triggered,"ending_resolved":self.world.ending_resolved})

    def _execute_step(self, aid: str, step):
        """执行单个 ActionStep 的副作用。"""
        from state import ActionStep as _AS
        action = step.action_type.upper() if step.action_type else ""
        if action in ("MOVE",) and step.target_location:
            self.world.npc_locations[aid] = step.target_location
        elif action in ("REST", "EAT") and step.target_location:
            self.world.npc_locations[aid] = step.target_location

    def _check_time_broadcasts(self, old_minutes: int, new_minutes: int):
        """检查时间是否跨过广播点。"""
        broadcast_hours = {7: "清晨广播", 12: "午餐广播", 18: "晚餐广播", 22: "夜铃"}
        for h in broadcast_hours:
            h_minutes = h * 60
            if old_minutes < h_minutes <= new_minutes:
                self._broadcast_event(h)

    def _advance_time(self, minutes: int = 60):
        """推进游戏时间。正常模式调用 _tick 驱动 ActionPlan。"""
        self._tick(minutes)
        if self.world.time_minutes >= 1440:
            self.world.time_minutes -= 1440
            self.world.current_day += 1
            self._apply_daily_curse()
        self.world.current_time = _time_string(self.world.time_minutes)

    def _tick(self, minutes: int = 1):
        """ActionPlan 驱动的逐分钟推进（用于 skip/sleep）。"""
        for _ in range(minutes):
            old_minutes = self.world.time_minutes
            self.world.time_minutes += 1
            self.world.current_time = _time_string(self.world.time_minutes)
            new_minutes = self.world.time_minutes

            for aid, agent in self.agents.items():
                st = self.agent_states.get(aid, DEAD_NPC)
                if not st.alive:
                    continue
                plan = agent.ensure_plan(self.world)
                if plan.is_completed or plan.current_step_idx >= len(plan.steps):
                    continue
                step = plan.steps[plan.current_step_idx]
                elapsed = self.world.time_minutes - plan.step_start_time
                if elapsed >= step.duration:
                    self._execute_step(aid, step)
                    plan.current_step_idx += 1
                    plan.step_start_time = self.world.time_minutes
                    if plan.current_step_idx >= len(plan.steps):
                        plan.is_completed = True
                        agent.plan(self.world, "计划完成")
            self._check_time_broadcasts(old_minutes, new_minutes)

    def skip_time(self, target_hour: int = None, mode: str = "skip_hours", hours: int = 1, hour: int = 14, minute: int = 0) -> str:
        """跳过时间到指定整点或指定时长。
        mode='skip_hours': 跳过 hours 小时
        mode='until': 推进至当天的 hour:minute
        """
        if mode == "until":
            target_minutes = hour * 60 + minute
            if target_minutes <= self.world.time_minutes:
                target_minutes += 1440
        elif target_hour is not None:
            # 兼容旧格式
            target_minutes = target_hour * 60
            if target_minutes <= self.world.time_minutes:
                target_minutes += 1440
        else:
            target_minutes = self.world.time_minutes + hours * 60

        total = target_minutes - self.world.time_minutes
        for _ in range(max(1, total // 10)):
            self._tick(10)
            if self.world.time_minutes >= target_minutes:
                self.world.time_minutes = target_minutes
                self.world.current_time = _time_string(self.world.time_minutes)
                break
            if getattr(self, 'xbrdcst', None):
                msg = self.xbrdcst; self.xbrdcst = None
                return f"skip_interrupted: {msg}"

        self.world.current_time = _time_string(self.world.time_minutes)
        return f"skipped_to: {_time_string(target_minutes)}"

    def sleep_until_morning(self) -> str:
        """睡觉到次日上午 7:00，只在房间内可用。不因敲门中断。"""
        next_7 = 7 * 60
        current = self.world.time_minutes
        if current >= next_7:
            self.world.current_day += 1
        self.world.time_minutes = next_7
        self.world.current_time = _time_string(next_7)
        self._apply_daily_curse()
        return f"睡到第{self.world.current_day}天早上7点"

    def _broadcast_event(self, hour: int):
        events = {7:"清晨的阳光洒进房间。新的一天开始了。",12:"正午时分。该吃午饭了——人们向用餐区聚集。",18:"夕阳西下。晚餐时间到了。",22:"夜色深沉。多数人感到困倦，准备回房间休息。"}
        if hour in events: self.xbrdcst = events[hour]
        if hour in (12,18):
            common = self._get_common_room_for_scene()
            if common:
                for aid in self.world.alive_npcs: self.world.npc_locations[aid] = common

    @staticmethod
    def _get_common_room():
        return "宴会厅"

    def _get_common_room_for_scene(self) -> str:
        sid = self.scene_id or ""
        if "cloud" in sid: return "迎宾大厅"
        if "snow" in sid: return "观景车厢"
        return "宴会厅"

    def _apply_daily_curse(self):
        if self.world.difficulty == DifficultyMode.STORY: return
        alive = [aid for aid in self.world.alive_npcs if aid not in self.world.discovered_bodies]
        if not alive: return
        prev = self.world.cursed_npc
        candidates = [a for a in alive if a != prev] if len(alive) > 1 else alive
        chosen = random.choice(candidates)
        self.world.cursed_npc = chosen
        cp = self.scenario.get("characters",{}).get(chosen) if self.scenario else None
        name = cp.name if cp else chosen
        self._log("system", f"🔮 魔女诅咒降临：{name}")

    def _atmosphere(self) -> str:
        world = self.world
        parts = []
        if world.difficulty == DifficultyMode.STORY: parts.append("【模式】剧情模式——温馨美好，同伴互相信任。")
        elif world.difficulty == DifficultyMode.NORMAL: parts.append("【模式】正常模式——日常脆弱，案件可能发生。")
        elif world.difficulty == DifficultyMode.WITCH: parts.append("【模式】魔女模式——信任崩裂，互相猜忌提防。")
        met_count = len(world.player_met_npcs)
        if met_count < 3: parts.append("【相处】初次见面。彼此完全陌生。")
        elif met_count < 8: parts.append("【相处】刚认识不久。了解尚浅。")
        else: parts.append("【相处】逐渐熟悉。深层秘密仍未知。")
        ts = world.current_time
        if "上午" in ts: parts.append("【时间】清晨/上午，空气清新。")
        elif "中午" in ts: parts.append("【时间】正午，阳光明亮。")
        elif "下午" in ts: parts.append("【时间】午后，略显慵懒。")
        elif "晚上" in ts: parts.append("【时间】夜晚，警惕和不安加剧。")
        sid = self.scene_id
        scene_tone = self.scenario.get("scene_tone", "") if self.scenario else ""
        if scene_tone:
            parts.append(f"【世界观】{scene_tone}")
        total_npc = len(self.npc_ids)
        alive = len(world.alive_npcs)
        parts.append(f"【人员】共 {total_npc} 名 NPC + 玩家 = {total_npc+1} 人。存活: {alive}。禁止编造额外编号或名字。")
        if world.cursed_npc and world.difficulty != DifficultyMode.STORY:
            cp = self.scenario.get("characters",{}).get(world.cursed_npc) if self.scenario else None
            cname = cp.name if cp else world.cursed_npc
            parts.append(f"【诅咒】今日诅咒：{cname}。魔法被封，情绪放大，身体增强。")
        return "\n".join(parts)

    def _settle_player_affection(self):
        """批量评估上轮玩家与 NPC 对话的好感变化"""
        if not self._pending_player_dialogues:
            return
        items = []
        for d in self._pending_player_dialogues:
            aid = d["agent_id"]
            agent = self.agents.get(aid)
            if not agent: continue
            current_aff = agent.state.affection_map.get("player", 50)
            items.append({
                "agent_id": aid,
                "name": agent.profile.name,
                "personality": agent.profile.personality,
                "aff": current_aff,
                "msg": d["msg"],
                "resp": d["resp"],
            })
        if not items:
            self._pending_player_dialogues = []
            return
        lines = []
        for i, it in enumerate(items):
            lines.append(
                f"对话{i+1}：{it['name']}({it['personality']}) | "
                f"当前好感:{it['aff']} | "
                f"玩家说:「{it['msg']}」 | "
                f"她回答:「{it['resp']}」"
            )
        prompt = f"""评估以下 NPC 与玩家的对话对好感度的影响。根据 NPC 性格、对话内容和当前好感基数，判断好感变化（-10 到 +10）。

{chr(10).join(lines)}

规则：
- 基于 NPC 性格和说话内容判断——友好共情→正向，冒犯冷漠→负向，无聊客套→变化微小
- 变化幅度受当前好感制约：高好感上升空间小下降空间大，低好感则反之
- delta=0 表示关系不变

输出 JSON：
{{"evaluations":[{{"agent_id":"No.01","delta":3,"reason":"一句话原因"}}]}}
"""
        try:
            result = self.llm.chat_json(
                messages=[{"role":"user","content":prompt}],
                system="你是社交逻辑引擎。基于角色性格和对话内容，准确输出好感度变化。",
                temperature=0.8, max_tokens=512,
            )
            tick = self.world.global_tick
            for ev in result.get("evaluations", []):
                if not isinstance(ev, dict): continue
                aid = str(ev.get("agent_id", ""))
                if aid in self.agents and self.agent_states.get(aid, DEAD_NPC).alive:
                    try:
                        delta = max(-10, min(10, int(ev.get("delta", 0))))
                    except (ValueError, TypeError):
                        delta = 0
                    reason = str(ev.get("reason", "")) or ""
                    self.agents[aid].update_affection("player", delta, reason=reason, tick=tick)
        except Exception:
            pass
        self._pending_player_dialogues = []

    def _check_floor_unlock(self):
        world = self.world
        fr = self.scenario.get("floor_rooms",{}) if self.scenario else {}
        f1 = [r for r in world.explored_rooms if r in fr.get(1,[])]
        if len(f1) >= 3 and not world.floor_2_unlocked: world.floor_2_unlocked = True
        f2 = [r for r in world.explored_rooms if r in fr.get(2,[])]
        if len(f2) >= len(fr.get(2,[]))-1 and not world.floor_3_unlocked: world.floor_3_unlocked = True

    def _check_body_discovery(self, intents: dict):
        """LLM判定尸体发现：对尸体所在房间的每个活人，根据其行动判断是否发现尸体。"""
        import re
        newly_found = []
        for br in list(self.world.undiscovered_bodies):
            if br.broadcast:
                newly_found.append(br); continue
            body_loc = br.location
            candidates = []
            # NPC candidates
            for aid, il in intents.items():
                if self.world.npc_locations.get(aid,"") != body_loc: continue
                if aid == br.victim_id: continue
                if aid not in self.agent_states or not self.agent_states[aid].alive: continue
                action = ""
                for i in il:
                    if i.prose: action = i.prose; break
                    if i.reasoning: action = i.reasoning; break
                if not action: action = f"{self.agents[aid].profile.name if aid in self.agents else aid}在{body_loc}停留"
                candidates.append(("npc", aid, action))
            # Player candidate
            if self.player_location == body_loc:
                candidates.append(("player", "player", f"玩家在{body_loc}观察周围环境"))
            if not candidates: continue

            for kind, pid, action in candidates:
                name = self.agents[pid].profile.name if kind == "npc" and pid in self.agents else self.player_name
                try:
                    found = self.arbiter.check_body_discovery(name, action, body_loc, br.hiding_spot)
                except Exception:
                    found = False
                if not found: continue
                br.discovered_by.append(pid)
                if not br.first_discoverer:
                    br.first_discoverer = pid
                if len(br.discovered_by) >= 2 and not br.broadcast:
                    br.broadcast = True
                    vn = self.agent_states[br.victim_id].name if br.victim_id in self.agent_states else br.victim_id
                    fd_name = self.agents[br.first_discoverer].profile.name if br.first_discoverer in self.agents else self.player_name
                    self._log("system", f"尸体被发现：{vn}。{fd_name}在{br.hiding_spot}发现了尸体。魔女审判开始。")
                    self.gm._social_facts.append(f"【紧急】{fd_name}在{br.location}的{br.hiding_spot}发现了{vn}的尸体！")
                    self.world.discovered_bodies.append(br.victim_id)
                    if self.world.difficulty in (DifficultyMode.NORMAL, DifficultyMode.WITCH):
                        self.world.active_trial = TrialState(active=True, phase="investigation", victim_id=br.victim_id)
                    self.world.rounds_since_last_murder = 0
                    self.world.first_murder_delayed = False
                    newly_found.append(br)
                    break
        # 清理已广播的
        for br in newly_found:
            if br in self.world.undiscovered_bodies:
                self.world.undiscovered_bodies.remove(br)

    def trial_investigate(self, action: str) -> str:
        trial = self.world.active_trial
        if not trial or trial.phase != "investigation": return "没有进行中的调查阶段。"
        try:
            return self.llm.chat(messages=[{"role":"user","content":f"玩家调查：{action}。受害者：{trial.victim_id}。描述发现的线索，80-120字。"}], system="你是故事旁白。冷静、精确。", temperature=0.9, max_tokens=512)
        except: return "调查未发现特别的线索。"

    def add_evidence(self, item_desc: str) -> dict:
        """添加证物到当前审判中，含 LLM 模型校验。"""
        from state import EvidenceItem
        trial = self.world.active_trial
        if not trial or not trial.active:
            return {"ok": False, "error": "没有进行中的审判。"}

        loc = self.player_location
        room_items = self.world.room_item_state.get(loc, {})
        items_desc = "、".join(f"{k}" for k, v in room_items.items() if v == "存在") or "无"

        # LLM 校验：物品是否存在、能否取走
        try:
            check = self.llm.chat_json(messages=[{"role":"user","content":f"""玩家在【{loc}】想将以下物品作为证物收起来：「{item_desc}」

当前房间存在的物品：{items_desc}
玩家背包：{'、'.join(self.world.player_inventory) or '无'}

判断：
1. 这个物品在当前场景中是否存在？（回答 yes/no）
2. 它的实际名称是什么？（如"匕首"、"茶杯"、"纸条"）  
3. 玩家能否取走它？（合理吗？有阻碍吗？回答 yes/no）
4. 如果不存在或不能取走，给出简短理由。

输出 JSON：{{"exists":true/false,"actual_name":"...","can_take":true/false,"reason":""}}"""}], system="你是场景物品校验器。严格、精确。只输出 JSON。", temperature=0.3, max_tokens=512)
        except Exception:
            check = {"exists": True, "actual_name": item_desc, "can_take": True, "reason": ""}

        if not check.get("exists", False):
            return {"ok": False, "error": check.get("reason", "这里似乎没有那样的物品。")}
        if not check.get("can_take", True):
            return {"ok": False, "error": check.get("reason", "这件物品无法取走。")}

        name = check.get("actual_name", item_desc)
        ev = EvidenceItem(
            name=name,
            description=f"{name}——{check.get('reason', item_desc)}",
            found_by="player",
            location=loc,
            found_time_tick=self.world.global_tick,
        )
        trial.case_evidence_items.append(ev)

        # 从房间物品中移除
        if name in room_items:
            room_items[name] = "已取走（证物）"

        return {"ok": True, "evidence": ev.to_dict(),
                "narrative": f"你将{name}小心地收好，作为证物保存了起来。"}

    def trial_proceed(self) -> dict:
        trial = self.world.active_trial
        if not trial or not trial.active: return {"ok":False,"error":"没有审判","phase":""}
        trial.turn_count += 1
        if trial.phase == "investigation": trial.phase = "court_statement"; return {"ok":True,"phase":trial.phase,"text":"搜查结束。魔女审判开始。陈述阶段：每人依次发言。"}
        elif trial.phase == "court_statement": trial.phase = "court_debate"; return {"ok":True,"phase":trial.phase,"text":"辩论阶段。可以质疑证词。"}
        elif trial.phase == "court_debate":
            trial.phase = "voting"
            votes = self._trial_vote(); trial.votes = votes
            from collections import Counter
            counts = Counter(votes.values())
            if counts:
                max_votes = max(counts.values())
                tied = [pid for pid,c in counts.items() if c == max_votes]
                trial.defendant_id = random.choice(tied) if len(tied) > 1 else tied[0]
            trial.phase = "execution"
            return {"ok":True,"phase":"execution","text":self._trial_execution(),"votes":trial.votes,"defendant":trial.defendant_id}
        return {"ok":False,"error":"未知阶段","phase":trial.phase}

    def _trial_vote(self) -> dict[str,str]:
        votes = {}
        for aid in self.world.alive_npcs:
            if aid == self.world.active_trial.victim_id: continue
            agent = self.agents[aid]; st = agent.state
            suspects = [(oid, st.suspicion_map.get(oid,0)) for oid in self.world.alive_npcs if oid != aid and oid != self.world.active_trial.victim_id]
            suspects.sort(key=lambda x: -x[1])
            if suspects: votes[aid] = suspects[0][0]
            else:
                candidates = list(self.world.alive_npcs - {aid, self.world.active_trial.victim_id})
                votes[aid] = random.choice(candidates) if candidates else "No.01"
        return votes

    def _trial_execution(self) -> str:
        trial = self.world.active_trial
        defendant = trial.defendant_id
        victim = trial.victim_id
        is_guilty = (defendant == trial.murder_actor_id)

        if not defendant:
            trial.active = False
            return "无法确定真凶。一名被怀疑者被带入阴影。"

        en = self.agent_states[defendant].name if defendant in self.agent_states else "未知"
        is_player = (defendant == "player")
        scene_id = self.scene_id or ""

        # 玩家是谋杀犯：标记
        if trial.murder_actor_id == "player":
            self.world.player_is_murderer = True

        # 云端假期特殊规则：指认错误 = 凶手外全员抹杀
        if not is_guilty and "cloud" in scene_id:
            murderer = trial.murder_actor_id
            for aid in list(self.world.alive_npcs):
                if aid != murderer:
                    if aid in self.agent_states:
                        self.agent_states[aid].alive = False
                    self.world.alive_npcs.discard(aid)
            trial.executed_id = defendant
            trial.active = False
            text = f"指认错误。{'凶手以外' if murderer else ''}所有幸存者被集体清退。"
            self._log("system", f"云端假期全员抹杀: 真凶{murderer}存活，其余被清退。")
            return text

        # 常规处刑
        if is_player:
            st = self.agent_states.get("player")
            if st: st.alive = False
        else:
            self.agent_states[defendant].alive = False
            self.world.alive_npcs.discard(defendant)
        trial.executed_id = defendant

        try:
            if is_guilty:
                prompt = f"魔女审判结果：{en}被指认为魔女。她是真凶。结合她的魔法、性格、动机和绝望，创作揭露创伤的处刑演出。150-250字。"
            else:
                prompt = f"魔女审判结果：{en}被指认为魔女。她是无辜的。创作充满遗言与抗争的处刑演出。150-250字。"
            text = self.llm.chat(messages=[{"role":"user","content":prompt}],
                system="你是故事旁白。冷静精准且富有悲剧美学。", temperature=1.0, max_tokens=1024)
        except Exception:
            text = f"{en}被处刑。{'罪孽随她消逝。' if is_guilty else '她的无辜成为永恒遗憾。'}"
        trial.active = False
        return text

    def generate_statement(self) -> dict:
        """生成陈述阶段的开场白。"""
        trial = self.world.active_trial
        if not trial or trial.phase != "court_statement":
            return {"ok": False, "error": "不在陈述阶段"}

        # 找调查发现最多的 NPC
        best_npc = None
        best_count = 0
        for aid, results in trial.investigation_notes.items():
            if len(results) > best_count:
                best_count = len(results)
                best_npc = aid
        if best_npc is None:
            best_npc = trial.victim_id
            while best_npc == trial.victim_id:
                from random import choice
                best_npc = choice(list(self.world.alive_npcs))

        npc = self.agents.get(best_npc)
        npc_name = npc.profile.name if npc else "一名少女"
        findings = "；".join(trial.investigation_notes.get(best_npc, ["没有特别的发现"]))

        try:
            text = self.llm.chat(messages=[{"role":"user","content":f"""魔女审判陈述阶段。
被害者：{self.agent_states[trial.victim_id].name if trial.victim_id in self.agent_states else trial.victim_id}

现在请{npc_name}进行开场陈述。她在搜查中发现了：{findings}

请以她的性格和语气，生成一段 100-200 字的陈述。用第三人称叙述。"""}], system="你是故事旁白。", temperature=0.9, max_tokens=512)
        except Exception:
            text = f"{npc_name}站了出来，开始陈述搜查中的发现。"

        return {"ok": True, "phase": "court_statement", "text": text, "speaker": npc_name}

    def generate_debate_context(self) -> dict:
        """构建辩论阶段的上下文数据，供 SSE 流使用。"""
        trial = self.world.active_trial
        if not trial or trial.phase != "court_debate":
            return {"ok": False, "error": "不在辩论阶段"}

        victim_name = self.agent_states[trial.victim_id].name if trial.victim_id in self.agent_states else trial.victim_id

        evidence_lines = []
        for ev in trial.case_evidence_items:
            finder_name = "玩家"
            if ev.found_by != "player" and ev.found_by in self.agents:
                finder_name = self.agents[ev.found_by].profile.name
            evidence_lines.append(f"- {ev.name}（{ev.location}，发现者：{finder_name}）")
        evidence_str = "\n".join(evidence_lines) if evidence_lines else "（尚无证物）"

        notes_lines = []
        for aid, results in trial.investigation_notes.items():
            if aid in self.agents:
                name = self.agents[aid].profile.name
                for r in results:
                    notes_lines.append(f"- {name}({aid}): {r}")
        notes_str = "\n".join(notes_lines[-10:]) if notes_lines else "（无）"

        history_str = ""
        for s in trial.statements[-5:]:
            role = s.get("role", "?")
            content = s.get("content", "")
            history_str += f"[{role}]: {content}\n"

        npc_opinions = self._compute_npc_opinions(trial)

        # 存活 NPC 列表
        npc_list = []
        for aid in sorted(self.world.alive_npcs):
            if aid == trial.victim_id:
                continue
            name = self.agents[aid].profile.name if aid in self.agents else aid
            npc_list.append(f"{name}({aid})")

        context = {
            "victim_name": victim_name,
            "victim_id": trial.victim_id,
            "location": self.world.npc_locations.get(trial.victim_id, ""),
            "turn_count": trial.turn_count,
            "evidence_str": evidence_str,
            "notes_str": notes_str,
            "history_str": history_str,
            "npc_opinions": npc_opinions,
            "npc_list": npc_list,
            "timer_remaining": max(0, 60 - trial.timer_elapsed),
        }
        return {"ok": True, "phase": "court_debate", "context": context}

    def stream_debate(self, last_player_action: dict = None):
        """SSE 生成器：生成辩论叙事并流式推送。"""
        trial = self.world.active_trial
        if not trial or trial.phase != "court_debate":
            yield f"event: error\ndata: {{\"error\":\"不在辩论阶段\"}}\n\n"
            return

        ctx = self.generate_debate_context()
        if not ctx["ok"]:
            yield f"event: error\ndata: {{\"error\":\"{ctx.get('error')}\"}}\n\n"
            return
        c = ctx["context"]

        player_action_desc = ""
        if last_player_action:
            pa = last_player_action
            pa_type = pa.get("type", "")
            target = pa.get("target", "")
            argument = pa.get("argument", "")
            if pa_type == "challenge" and target:
                target_name = self.agents[target].profile.name if target in self.agents else target
                player_action_desc = f"玩家刚刚质疑了{target_name}的证词。"
            elif pa_type == "present_evidence" and target:
                for ev in trial.case_evidence_items:
                    if ev.item_id == target:
                        player_action_desc = f"玩家刚刚出示了证物「{ev.name}」。"
                        break
            elif pa_type == "reason":
                player_action_desc = f"玩家提出了自己的推理：{argument}"
            if not player_action_desc:
                player_action_desc = "玩家在思考。"

        prompt = f"""你正在主持一场魔女审判的辩论阶段。

【背景】
- 被害者：{c['victim_name']} ({c['victim_id']})
- 辩论轮次：第 {c['turn_count']} 轮
- 存活角色：{', '.join(c['npc_list'])}

【证物清单】
{c['evidence_str']}

【调查记录】
{c['notes_str']}

【辩论历史】
{c['history_str'] or '（首次辩论）'}

【玩家行动】
{player_action_desc}

任务：生成一段 2-3 个 NPC 交替发言的辩论叙事（200-400 字）。
- NPC 发言必须引用具体证物名称
- 对话要有来有回（质疑→反驳→补充）
- 发言风格符合角色性格

输出 JSON：{{"narrative":"...","elapsed_minutes":8,"consensus_reached":false,"consensus_target":null,"consensus_ratio":0,"options":[{{"label":"...","type":"challenge/present_evidence/reason/wait","target":"...","room":null}}]}}"""

        try:
            for chunk_text in self.gm_llm.chat_stream(
                messages=[{"role": "user", "content": prompt}],
                system=self._pgm(),
                temperature=0.9,
                max_tokens=2048,
            ):
                yield f"event: narrative_chunk\ndata: {json.dumps({'text': chunk_text}, ensure_ascii=False)}\n\n"
        except Exception:
            # Fallback: non-streaming
            try:
                result = self.gm_llm.chat(
                    messages=[{"role": "user", "content": prompt}],
                    system=self._pgm(),
                    temperature=0.9,
                    max_tokens=2048,
                )
                yield f"event: narrative_chunk\ndata: {json.dumps({'text': result}, ensure_ascii=False)}\n\n"
            except Exception as e:
                yield f"event: error\ndata: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
                return

    def process_debate_option(self, choice: dict) -> dict:
        """处理玩家在辩论中的选择。"""
        trial = self.world.active_trial
        if not trial or trial.phase != "court_debate":
            return {"ok": False, "error": "不在辩论阶段"}

        trial.turn_count += 1
        choice_type = choice.get("type", "")

        if choice_type == "suggest_vote":
            trial.phase = "voting"
            return {"ok": True, "phase": "voting", "text": "你提出了进入投票。大家开始投票。"}

        # 记录玩家行动
        trial.statements.append({
            "role": "player",
            "content": f"[{choice_type}] {choice.get('argument', choice.get('label', ''))}",
            "type": choice_type,
            "target": choice.get("target"),
        })

        return {"ok": True, "phase": "court_debate", "ready_for_stream": True}

    def _compute_npc_opinions(self, trial) -> dict:
        """计算各 NPC 的怀疑倾向。"""
        opinions = {}
        for aid in self.world.alive_npcs:
            if aid == trial.victim_id:
                continue
            st = self.agent_states.get(aid)
            if st is None:
                continue
            top_suspect = None
            top_weight = 0
            for oid in self.world.alive_npcs:
                if oid == aid or oid == trial.victim_id:
                    continue
                weight = st.suspicion_map.get(oid, 0) * 0.6
                aff = st.affection_map.get(oid, 50)
                if aff < 35:
                    weight += (35 - aff) / 100 * 0.25
                for ev in trial.case_evidence_items:
                    if oid in ev.description or oid in ev.name:
                        weight += 0.15
                if weight > top_weight:
                    top_weight = weight
                    top_suspect = oid
            opinions[aid] = {"top_suspect": top_suspect, "confidence": round(top_weight, 2)}
        return opinions

    def _check_ending_trigger(self) -> dict | None:
        if self.world.ending_triggered or self.world.ending_resolved:
            return None
        cfg = self.scenario.get("ending_config") if self.scenario else None
        if not cfg: return None

        # 玩家死亡 → 自动死亡结局
        pst = self.agent_states.get("player")
        if pst and not pst.alive:
            self.world.ending_triggered = True
            self.world.ending_chosen = "player_dead"
            self._log("system", "玩家死亡，触发死亡结局。")
            return {"trigger_type": "player_dead", "auto_ending": "player_dead",
                    "revelation_hint": "", "branches": []}

        tt = cfg.get("trigger_type", ""); tv = cfg.get("trigger_value", "")
        trig = False
        if tt == "survivor_count":
            try:
                if len(self.world.alive_npcs) <= int(tv): trig = True
            except: pass
        elif tt == "location_reached":
            if self.player_location == str(tv): trig = True
        if not trig: return None

        self.world.ending_triggered = True; self._log("system", "结局触发。")

        # 评估条件分支
        branches = []
        player_murderer = self.world.player_is_murderer
        for b in cfg.get("branches", []):
            cond = b.get("condition", "")
            if not cond:
                branches.append(b)
            elif cond == "player_is_murderer" and player_murderer:
                branches.append(b)
            elif cond == "player_not_murderer" and not player_murderer:
                branches.append(b)
            elif cond == "trial_executed_wrong":
                trial = self.world.active_trial
                if trial and trial.defendant_id != trial.murder_actor_id:
                    branches.append(b)

        return {"trigger_type": tt, "revelation_hint": cfg.get("revelation_hint", ""), "branches": branches}

    def choose_ending(self, ending_id: str) -> str:
        if not self.world.ending_triggered or self.world.ending_resolved: return "结局不可用。"
        if ending_id == "player_dead" or ending_id == "_revelation_only":
            self.world.ending_chosen = ending_id
            self.world.ending_resolved = True
            return self._death_ending_text()

        cfg = self.scenario.get("ending_config") if self.scenario else None
        if not cfg: return "本场景未定义结局。"
        branch = next((b for b in cfg.get("branches", []) if b.get("ending_id") == ending_id), None)
        if not branch: return "未知结局分支。"
        self.world.ending_chosen = ending_id
        self.world.ending_resolved = True
        hint = branch.get("narrative_hint", "故事结束。")
        surv = [self.agents[aid].profile.name for aid in self.world.alive_npcs if aid in self.agents]
        dead = [self.agents[aid].profile.name for aid in self.npc_ids if aid not in self.world.alive_npcs and aid in self.agents]
        try:
            return self.llm.chat(messages=[{"role":"user","content":f"""请根据以下指导生成结局叙事（300-500字）。
指导：{hint}
玩家：{self.player_name} | 幸存者：{'、'.join(surv) or '无'} | 逝者：{'、'.join(dead) or '无'}
场景：{self.scenario.get('name','') if self.scenario else ''}
用第二人称叙述，情感饱满。结局。"""}], system="你是故事旁白。结局叙事，文笔精美、情感深沉。", temperature=1.0, max_tokens=1024)
        except: return f"故事结束。{self.player_name}做出了选择。——{branch.get('label','')}"

    def _death_ending_text(self) -> str:
        """生成玩家死亡结局的叙事文本。不写外界现实。"""
        scene_name = self.scenario.get("name", "这个世界") if self.scenario else "这个世界"
        try:
            return self.llm.chat(messages=[{"role":"user","content":f"""玩家{self.player_name}已经死亡。
这是游戏的终点。请用第二人称，直接描写死亡本身的感受——
意识的消散、最后的感知、或宁静的虚无。不要写天堂、地狱、轮回。
不要写外界现实（如废土、苏醒舱等）。150-200字。
场景：{scene_name}。"""}], system="你是故事旁白。死亡结局，静谧、诚实、不粉饰。", temperature=0.9, max_tokens=512)
        except:
            return f"{self.player_name}的旅程结束了。在{scene_name}的某个角落，一切归于平静。"

_session_lock = threading.Lock()
session = GameSession()
scenarios.load("tianji_maze"); scenarios.load("cloud_holiday"); scenarios.load("snow_train")
