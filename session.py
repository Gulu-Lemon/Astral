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
        self._prologue_context: list[dict] = []
        self._prologue_turn: int = 0
        self._post_admin_explored: bool = False
        self._player_action_log: list[str] = []
        self._prologue_phase: str = "free"  # free → admin → grouping → chosen
        self._pending_player_dialogues: list[dict] = []

        self.llm = LLMClient("")
        self.agent_llm = LLMClient("")
        self.gm_llm = LLMClient("")
        self.arbiter_llm = LLMClient("")
        self._load_llm_config()
        self.world = WorldState()
        self.agents: dict[str, NPCAgent] = {}
        self.agent_states: dict[str, AgentState] = {}
        scene_chars = self.scenario.get("characters", {}) if self.scenario else {}
        self.arbiter = Arbiter(self.arbiter_llm, characters=scene_chars)
        self.gm = GMNarrator(self.gm_llm, scene_id=scene_id, characters=scene_chars)
        self.save_mgr = SaveManager()
        self.player_name = ""
        self.player_location = self.scenario.get("start_room", "")
        self.player_created = False
        self.player_age = "16"
        self.player_appearance = ""
        self.round_count = 0
        self.npc_ids = self.scenario.get("npc_ids", [f"No.{i:02d}" for i in range(1,13)])
        self.last_narrative = None
        self.last_options = []
        self.narrative_log: list[dict] = []
        self._init_agents()

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

    def _init_agents(self):
        init_aff = 25 if self.world.difficulty == DifficultyMode.WITCH else 15
        # 天际迷宫主打场景探索，楼层有锁；其余场景全解锁
        if self.scene_id != "tianji_maze":
            self.world.floor_2_unlocked = True
            self.world.floor_3_unlocked = True
        for aid in self.npc_ids:
            scene_chars = self.scenario.get("characters", {}) if self.scenario else {}
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
            text = self.llm.chat(messages=msgs, system=sys, temperature=temp, max_tokens=mt)
            if self.world and self.world.prologue_step < 7:
                self._validate_prologue_output(text)
            return text
        except Exception as e1:
            if len(sys) > 500:
                try: return self.llm.chat(messages=msgs, system="你是旁白。第三人称。", temperature=temp, max_tokens=mt)
                except: pass
            try: return self.llm.chat(messages=msgs, system=None, temperature=temp, max_tokens=mt)
            except Exception as e3:
                emsg = str(e3)[:200]
                if hasattr(self,'logger'): self.logger.log_arbiter([f"LLM ERROR: {emsg}"])
                return f"(API 调用失败：{emsg}。请检查网络、API Key 或模型名是否正确。)"

    def _scene_prompt(self, key: str, **kwargs) -> str:
        template = self.scenario.get(f"prologue_{key}", "")
        if template:
            try:
                result = template.format(**kwargs)
                if '{' in result and '}' in result:
                    import re
                    if re.search(r'\{[^}]*\}', result):
                        return kwargs.get("default", "")
                return result
            except (KeyError, ValueError):
                return kwargs.get("default", "")
        return kwargs.get("default", "")

    def _pgm(self) -> str:
        if self.scenario and self.scenario.get("gm_prompt"):
            return self.scenario.get("gm_prompt")
        return """你是故事旁白。严格遵守以下规则：
1. 只描述玩家能直接看到或听到的内容，不做全知视角叙述。
2. 不要编造未发生的事件。如果无事发生，描述环境氛围即可。
3. 不要透露任何 NPC 的秘密、动机或内心想法。
4. 不要赋予 NPC 其档案中没有的能力、物品或关系。
5. 用外貌特征称呼陌生 NPC（如"银发少女"），只有当 NPC 自己说出名字或玩家已知时才使用真名。
6. 所有描写必须严格基于【当前房间设施】。
7. 不要引入超自然元素（除非场景设定明确允许）。
8. 叙事简洁，每次 3-5 句即可。"""

    def _scene_context(self, prologue: bool = False) -> str:
        """生成场景锚点文本，注入每条 prologue prompt。prologue=True 时屏蔽其他房间。"""
        name = self.scenario.get("name", "") if self.scenario else ""
        tone = self.scenario.get("scene_tone", "") if self.scenario else ""
        gm = self.scenario.get("gm_name", "") if self.scenario else ""
        if prologue:
            rooms_str = "（序章阶段，其他区域尚未探索，处于未知状态。所有人仍在初始区域内。）"
        else:
            fr = self.scenario.get("floor_rooms", {}) if self.scenario else {}
            current_floor = self.world.current_floor
            rooms_here = fr.get(current_floor, [])
            rooms_str = "、".join(rooms_here[:8]) if rooms_here else self.player_location
        return (
            f"场景：{name}\n"
            f"基调：{tone}\n"
            f"你在：{self.player_location}\n"
            f"可前往：{rooms_str}\n"
            f"GM角色（登场前禁止出现）：{gm}"
        )

    def _is_leave_attempt(self, choice: str) -> bool:
        try:
            result = self.llm.chat(
                messages=[{"role":"user","content":
                    f"序章阶段，所有人都在【{self.player_location}】里，尚未去过任何其他地方。\n"
                    f"玩家刚刚做出了一个选择：\n"
                    f"「{choice}」\n\n"
                    f"判断：这个选择是否暗示玩家想要离开当前区域、去另一个房间或地点？\n"
                    f"只回答 YES 或 NO。"}],
                system="你是一个精确的意图分类器。",
                temperature=0.1, max_tokens=8,
            )
            return "YES" in result.upper()
        except Exception as e:
            self._log("system", f"离开意图判定LLM失败，默认不视为离开: {str(e)[:100]}")
            return False

    def _roster(self) -> str:
        chars = self.scenario.get("characters", {}) if self.scenario else {}
        names = [c.name for _, c in sorted(chars.items())]
        return "、".join(names) if names else "无"

    def _npc_profile_roster(self, level: str = "L2") -> str:
        """NPC 档案分级注入，供序章 LLM 依角色撰写。

        level:
          "L1" — 仅外貌（旁白初次介绍用）
          "L2" — 外貌 + 性格（旁白互动场景用，不含秘密）
          "L3" — 完整档案（Agent 决策用，含 play_core）
        """
        chars = self.scenario.get("characters", {}) if self.scenario else {}
        lines = []
        for aid, cp in sorted(chars.items()):
            appear = (cp.appearance or "")[:80]
            if level == "L1":
                lines.append(f"[{aid}] {appear}")
                continue
            person = (cp.personality or "")[:80]
            if level == "L2":
                lines.append(f"[{aid}] {appear} | {person}")
                continue
            core = (cp.play_core or "")[:80]
            habits = (cp.daily_habits or "")[:40] if hasattr(cp, 'daily_habits') else ""
            lines.append(f"[{aid}] {appear} | {person} | {core} | {habits}")
        return "\n".join(lines) if lines else "无"

    def _room_features(self, room_name: str) -> str:
        feats = self.scenario.get("room_features", {}).get(room_name, []) if self.scenario else []
        names = [f.get('name', '未知设施') for f in feats[:8]]
        return "、".join(names) if names else "（无记录）"

    def _npc_roster(self) -> str:
        chars = self.scenario.get("characters", {}) if self.scenario else {}
        names = [c.name for _,c in sorted(chars.items())]
        return "、".join(names) if names else "无"

    # === Prologue ===

    def prologue_step_1_mirror(self, name, age, appearance):
        self.player_name = name
        self.player_age = age
        self.player_appearance = appearance
        self.player_location = self.scenario.get("start_room", "")
        self.agent_states["player"].name = name
        self._prologue_context = []
        self._player_action_log = []
        prompt = self._scene_prompt("mirror", name=name, age=age, appearance=appearance, player_name=name,
            default=f"玩家名为{name}，{age}岁，{appearance}。请用叙事者角度确认形象并引出魔法。")
        text = self._safe_llm([{"role":"user","content":prompt}], self._pgm(), 1.0, 1024)
        self._prologue_truncate_context()
        self._prologue_context.append({"role":"user","content":prompt})
        self._prologue_context.append({"role":"assistant","content":text})
        self._player_action_log.append(f"玩家{name}，{age}岁，{appearance}。")
        self.world.prologue_step = 1
        return text

    def prologue_step_2_magic(self, magic):
        self.world.player_magic = magic
        prompt = self._scene_prompt("magic", magic=magic, default=f"玩家描述了魔法能力：{magic}。请确认并引出难度模式选择。")
        full_prompt = self._player_action_prefix() + prompt
        text = self._safe_llm(self._prologue_context+[{"role":"user","content":full_prompt}], self._pgm(), 1.0, 1024)
        self._prologue_truncate_context()
        self._prologue_context.append({"role":"user","content":full_prompt})
        self._prologue_context.append({"role":"assistant","content":text})
        self._player_action_log.append(f"魔法觉醒：{magic}。")
        self.world.prologue_step = 2
        return text

    def prologue_step_3_difficulty(self, mode):
        mm = {"A":DifficultyMode.STORY,"B":DifficultyMode.NORMAL,"C":DifficultyMode.WITCH,"a":DifficultyMode.STORY,"b":DifficultyMode.NORMAL,"c":DifficultyMode.WITCH}
        self.world.difficulty = mm.get(mode, DifficultyMode.NORMAL)
        mn = {DifficultyMode.STORY:"剧情模式",DifficultyMode.NORMAL:"正常模式",DifficultyMode.WITCH:"魔女模式"}
        md = {DifficultyMode.STORY:"温馨美好的日常。",DifficultyMode.NORMAL:"杀人事件会发生，魔女审判会举行。",DifficultyMode.WITCH:"信任破裂，杀戮与被杀。"}
        mode_name = mn[self.world.difficulty]
        mode_desc = md[self.world.difficulty]
        prompt = self._scene_prompt("difficulty", mode_name=mode_name, mode_desc=mode_desc, default=f"难度确定为{mode_name}。")
        full_prompt = self._player_action_prefix() + prompt
        text = self._safe_llm(self._prologue_context+[{"role":"user","content":full_prompt}], self._pgm(), 0.9, 1024)
        self._prologue_truncate_context()
        self._prologue_context.append({"role":"user","content":full_prompt})
        self._prologue_context.append({"role":"assistant","content":text})
        self._player_action_log.append(f"难度：{mode_name}（{mode_desc}）。")
        self.world.prologue_step = 3
        return f"『{mode_name}』已确认。\n\n{text}"

    def prologue_step_4_camp(self):
        self.player_created = True
        self.player_location = self.scenario.get("start_room", "")
        self.world.prologue_step = 4
        self._prologue_turn = 0
        self._prologue_phase = "free"
        prompt = self._scene_prompt("camp", player_name=self.player_name, default=f"场景：{self.player_name}来到营地中央。")
        gm_name = self.scenario.get("gm_name", "")
        initial_prompt = f"""{self._scene_context(prologue=True)}

{self._player_action_prefix()}
{prompt}

【当前房间设施】{self._room_features(self.player_location)}

注意：
- 所有人——包括玩家和全部12名NPC——都聚集在相同的初始区域内，没有任何人离开过。
- 禁止描述任何其他区域的具体样貌（所有人此刻都不知道其他地方是什么样子）。
- 所有描写必须严格符合【当前房间设施】。禁止编造设施之外的物品或环境。
- 禁止让{gm_name}在此场景中出现。此时尚未登场。
- 以第三人称侧面描写 NPC，不要使用真名（用外貌特征描述）。
- 背景：12 名少女都在场内。以下是她们的真实档案，请严格按其外貌、性格、行为特征撰写：
{self._npc_profile_roster()}
- 本轮只选 2-3 名性格冲突的 NPC 创作特写场景，其余一笔带过。
- 保持直接叙述，300-400字即可。
- 禁止生成涉及离开当前区域的选项（如"去XX房间""探索XX""走向XX"）。所有人此刻都在{self.player_location}内，还没有人离开过。

末尾用以下精确格式输出 4 个互动选项：
【选项】
A.选项内容
B.选项内容
C.选项内容
D.选项内容"""
        text = self._safe_llm(self._prologue_context+[{"role":"user","content":initial_prompt}], self._pgm(), 1.0, 2048)
        options = self._parse_prologue_options(text)
        narrative = self._strip_prologue_options(text)
        if not options: options = ["与附近的人交谈","仔细观察周围环境","静静等待事态发展","查看周围人的反应"]
        self._prologue_context.append({"role":"user","content":initial_prompt})
        self._prologue_context.append({"role":"assistant","content":text})
        self._player_action_log.append(f"进入场景：{self.player_location}。")
        return {"text": narrative, "options": options, "step": 4}

    def prologue_continue(self, player_choice: str):
        self._prologue_turn += 1
        gm_name = self.scenario.get("gm_name", "")
        rule = self.scenario.get("rule_text", "")
        story_prefix = self._player_action_prefix()
        scene_id = self.scene_id
        scene_ctx = self._scene_context()

        # === Phase "chosen"：分组选择后 → 加入描述 + 唯一选项"进入游戏" ===
        if self._prologue_phase == "chosen":
            if player_choice in ("确认进入","_finish","进入游戏","开始游戏") or any(k in player_choice for k in ("确认进入","_finish","进入游戏","开始游戏")):
                self.world.prologue_step = 7
                return {"text":"","options":[],"step":7,"finished":True}
            prompt = f"""{story_prefix}玩家选择了：{player_choice}

请简短描述{self.player_name}做出选择后的瞬间——周围NPC的反应、气氛的变化、{self.player_name}做选择时的内心感受。用第二人称。100-150字。"""
            text = self._safe_llm(self._prologue_context+[{"role":"user","content":prompt}], self._pgm(), 0.9, 2048)
            self._prologue_truncate_context()
            self._prologue_context.append({"role":"user","content":prompt})
            self._prologue_context.append({"role":"assistant","content":text})
            narrative = self._strip_prologue_options(text)
            options = ["进入游戏"]
            self._player_action_log.append(f"玩家选择了：{player_choice}")
            self.world.prologue_step = 6
            return {"text": narrative, "options": options, "step": 6}

        # === 终止条件 ===
        finish_keywords = ("确认进入","_finish","进入游戏","开始游戏")
        if player_choice in finish_keywords or any(k in player_choice for k in finish_keywords):
            if self.world.prologue_step >= 6:
                self.world.prologue_step = 7
                return {"text":"","options":[],"step":7,"finished":True}

        if self._prologue_turn >= 5:
            self.world.prologue_step = 7
            self._log("system", "序章已达到最大回合数，自动进入游戏。")
            return {"text":"","options":[],"step":7,"finished":True}

        # === Phase "free" → "admin"：自由探索到管理员登场 ===
        if self._prologue_phase == "free":
            if self._prologue_turn >= 2:
                self._prologue_phase = "admin"
            elif self._is_leave_attempt(player_choice):
                self._prologue_phase = "admin"
        if self._prologue_phase == "free":
            template = self._scene_prompt("free", default="")
            if template:
                try:
                    prompt = template.format(
                        room=self.player_location,
                        room_features=self._room_features(self.player_location),
                        npc_profiles=self._npc_profile_roster(),
                        scene_context=self._scene_context(prologue=True),
                        story_prefix=story_prefix,
                        player_choice=player_choice,
                    )
                except (KeyError, ValueError):
                    template = ""
            if not template:
                prompt = f"""{self._scene_context(prologue=True)}

{story_prefix}玩家选择：{player_choice}

描述接下来发生的事情。所有人仍在{self.player_location}内——没有任何人离开过初始区域。保持直接叙述。【当前房间设施】{self._room_features(self.player_location)}。禁止让{gm_name}出现。NPC 用外貌特征描述。

NPC 档案如下，请严格按其外貌、性格、行为特征撰写：
{self._npc_profile_roster()}

重要约束：严格按照【场景基调】描写环境。禁止编造场景中不存在的区域、建筑、设施或自然景观。禁止描述任何初始区域以外的地方。禁止生成涉及离开当前区域的选项。200-300字。

末尾输出4个选项：【选项】A. ... B. ... C. ... D. ..."""
            text = self._safe_llm(self._prologue_context+[{"role":"user","content":prompt}], self._pgm(), 1.0, 2048)
            self._prologue_truncate_context()
            self._prologue_context.append({"role":"user","content":prompt})
            self._prologue_context.append({"role":"assistant","content":text})
            options = self._parse_prologue_options(text)
            narrative = self._strip_prologue_options(text)
            if not options: options = ["与附近的人交谈","仔细观察周围环境","静静等待事态发展","查看周围人的反应"]
            self._player_action_log.append(f"玩家选择了：{player_choice}")
            return {"text": narrative, "options": options, "step": self.world.prologue_step}

        # === Phase "admin"：管理员登场/广播 + 规则硬输出 ===
        if self._prologue_phase == "admin":
            admin_entry = self._scene_prompt("admin", default="").format(
                player_name=self.player_name, gm_name=gm_name)
            if not admin_entry:
                if scene_id == "snow_train":
                    admin_entry = f"列车长的声音从天花板上的扬声器中响起。广播系统发出「嗡——」的低频长音，随后是一声轻咳。「各位旅客，下午好。我是本次列车的列车长。请仔细阅读你们座椅口袋里的安全守则。」广播在电流声中断开。他本人不会现身——只有这个声音在车厢中回荡。每个人——包括{self.player_name}——都低头翻看起了手中的守则。"
                else:
                    admin_entry = f"经过一段时间的探索后，自然地引出了{gm_name}的出场。{gm_name}宣布了这里的规则，并示意所有人仔细阅读。每个人——包括{self.player_name}——都低头翻看起了规则。"
            prompt = f"""{story_prefix}玩家选择：{player_choice}

{admin_entry}

基于上述素材进行文学化叙事。以第三人称旁白。
- 完整引述{gm_name}的广播或宣告内容（用双引号括起原文，不得省略或概括）
- 描写环境氛围、声音的质感、众人的表情变化
- 以「{self.player_name}低下头，看着面前的规则。」收尾
不要描写任何人看完规则后的具体评论或内心反应——那些是选项被选择之后的事。150-200字。

末尾输出4个选项：【选项】
A. ...
B. ...
C. ...
D. ..."""
            text = self._safe_llm(self._prologue_context+[{"role":"user","content":prompt}], self._pgm(), 0.9, 2048)
            self._prologue_truncate_context()
            self._prologue_context.append({"role":"user","content":prompt})
            self._prologue_context.append({"role":"assistant","content":text})
            narrative = self._strip_prologue_options(text)
            options = self._parse_prologue_options(text)
            if not options: options = ["认真记在心里","和旁边的人低声讨论","表面平静，内心盘算","觉得荒谬/不以为然"]
            self._player_action_log.append("管理员登场，规则宣布。")
            self.world.prologue_step = 6
            self._prologue_phase = "grouping"
            return {"text": narrative, "options": options, "step": self.world.prologue_step, "rule": rule}
        elif self._prologue_phase == "grouping":
            # === Phase "grouping"：分组场景 ===
            explore_template = self._scene_prompt("explore", default="")
            if explore_template:
                try:
                    prompt = explore_template.format(
                        story_prefix=story_prefix,
                        scene_context=scene_ctx,
                        player_name=self.player_name,
                        npc_profiles=self._npc_profile_roster(),
                    )
                except (KeyError, ValueError):
                    explore_template = ""
            if not explore_template:
                prompt = f"""{scene_ctx}

{story_prefix}玩家对规则做出了反应。

随后，一位有领导气质的NPC站了出来，提议大家分组探索这个场所以提高效率。其他人立刻开始争论——有人想和熟人一组，有人坚持独自行动，有人试图拉拢强者。在争论中逐渐形成了2-3个小组，另有1-2人选择独自探索。

NPC 用外貌特征描述。NPC 档案如下，请严格按其外貌、性格、行为特征撰写：
{self._npc_profile_roster()}

重要约束：严格按照【场景基调】描写环境和分组探索方式。禁止编造不存在的区域。

同一组的成员在争论后会进行简短的自我介绍——自然地写出1-2句互报姓名和基本情况的对话。用外貌特征引入角色，通过对话揭示姓名。

末尾生成4个选项：【选项】
A. ...
B. ...
C. ...
D. ...
300-400字。"""
            self._prologue_phase = "chosen"
        text = self._safe_llm(self._prologue_context+[{"role":"user","content":prompt}], self._pgm(), 1.0, 3072)
        self._prologue_truncate_context()
        self._prologue_context.append({"role":"user","content":prompt})
        self._prologue_context.append({"role":"assistant","content":text})
        options = self._parse_prologue_options(text)
        narrative = self._strip_prologue_options(text)
        if not options: options = ["继续观察","与附近的人交谈","仔细思考","等待事态发展"]
        self._player_action_log.append(f"玩家选择了：{player_choice}")
        if self.world.prologue_step == 6:
            return {"text": narrative, "options": options, "step": self.world.prologue_step}
        return {"text": narrative, "options": options, "step": self.world.prologue_step}

    def _generate_explore_scene(self):
        self._post_admin_explored = True
        prompt = f"""{self._player_action_prefix()}管理员刚刚宣布了规则。现在少女们决定分头探索周围环境。请生成一个分组探索的场景：将全部 12 名 NPC 分成 2-3 组。每组 3-5 人。用外貌特征描述每组的 NPC。NPC 档案如下，请严格按其外貌、性格、行为特征描写：
{self._npc_profile_roster()}

{self.player_name}站在原地看着各组分头离开。末尾生成 4 个选项，让玩家选择跟随哪一组。第4个选项始终是"（独自探索）"。格式：【选项】A. ... B. ... C. ... D. ... 200-300字。"""
        text = self._safe_llm(self._prologue_context+[{"role":"user","content":prompt}], self._pgm(), 1.0, 1024)
        self._prologue_truncate_context()
        self._prologue_context.append({"role":"user","content":prompt})
        self._prologue_context.append({"role":"assistant","content":text})
        options = self._parse_prologue_options(text)
        narrative = self._strip_prologue_options(text)
        if not options: options = ["跟随第一组","跟随第二组","跟随第三组","独自探索"]
        self._player_action_log.append("分组探索场景生成。")
        options.append("进入游戏")
        return {"text": narrative, "options": options, "step": 6}

    def _prologue_truncate_context(self):
        """保留最近 6 轮对话（12 条消息）"""
        while len(self._prologue_context) > 12:
            self._prologue_context = self._prologue_context[2:]
        while len(self._player_action_log) > 8:
            self._player_action_log = self._player_action_log[-8:]

    def _player_action_prefix(self) -> str:
        if not self._player_action_log:
            return ""
        return "【玩家行动轨迹】\n" + "\n".join(f"- {b}" for b in self._player_action_log[-6:]) + "\n"

    def prologue_finish(self):
        self.world.prologue_step = 7
        self._prologue_summarize()
        self._prologue_bridge()
        return True

    def _prologue_summarize(self):
        """生成 200-300 字前情提要供 GM 首轮承接"""
        if not self._prologue_context:
            self.world.last_narrative_summary = ""
            return
        prologue_msgs = [
            msg.get("content", "") for msg in self._prologue_context
            if msg.get("role") == "assistant"
        ]
        if not prologue_msgs:
            self.world.last_narrative_summary = ""
            return
        try:
            summary = self.llm.chat(
                messages=[{"role":"user","content":"将以下序章剧情压缩为一段200-300字的连贯摘要，用作下一章的'前情提要'。用叙述语气，不是要点列表。\n\n" + "\n\n".join(prologue_msgs)}],
                system="你是故事编辑。简洁、连贯。",
                temperature=0.7, max_tokens=512,
            )
            self.world.last_narrative_summary = summary.strip()
        except Exception:
            self.world.last_narrative_summary = ""

    def _prologue_bridge(self):
        """序章→正文桥接：提取结构化信息"""
        prologue_text = self._prologue_full_text()
        if not prologue_text:
            return
        chars = self.scenario.get("characters", {}) if self.scenario else {}
        if not chars:
            return

        # 步骤 1：LLM 提取玩家见面 + NPC 对话 + 动机
        bridge_data = self._llm_extract_bridge(prologue_text, chars)
        if not bridge_data:
            return

        # 步骤 2：登记玩家认识的 NPC
        self._apply_player_meetings(bridge_data, chars)

        # 步骤 3：播入 NPC-NPC 对话
        self._apply_npc_dialogues(bridge_data)

        # 步骤 4：播入 NPC 内心动机
        self._apply_npc_motives(bridge_data)

        # 步骤 5：评估好感变动
        self._bridge_affection(prologue_text, bridge_data, chars)

    def _parse_prologue_options(self, text: str) -> list[str]:
        opts = []
        marker = re.search(r'【选项】', text)
        section = text[marker.start():] if marker else text
        # 主路径：兼容 . : ： ) 、 空格 等多种 LLM 分隔符
        for m in re.finditer(r'([A-D])[\.\s、：:)]\s*(.+?)(?=\n\s*[A-D][\.\s、：:)]\s*|\Z)', section, re.DOTALL):
            opt_text = m.group(2).strip()
            if len(opt_text) > 1: opts.append(opt_text)
        if len(opts) >= 2:
            return opts
        # 回退：文本末尾 500 字符按行匹配
        tail = text[-500:]
        for m in re.finditer(r'^[A-D][\.\s、：:)]\s*(.+)$', tail, re.MULTILINE):
            opt_text = m.group(1).strip()
            if len(opt_text) > 1: opts.append(opt_text)
        if len(opts) >= 2:
            return opts
        # 全部失败：记录日志供诊断
        self._log("system", f"选项解析失败，LLM原文尾500字:\n{text[-500:]}")
        return []

    def _strip_prologue_options(self, text: str) -> str:
        marker = re.search(r'【选项】', text)
        if marker: text = text[:marker.start()]
        cut = re.search(r'\n\s*A\.\s+', text)
        if cut: text = text[:cut.start()]
        return text.strip()

    # ====== 序章桥接方法 ======

    def _prologue_full_text(self) -> str:
        """拼接序章完整叙述文本"""
        if not self._prologue_context:
            return ""
        return "\n\n".join(
            msg.get("content", "") for msg in self._prologue_context
            if msg.get("role") == "assistant"
        )

    def _llm_extract_bridge(self, prologue_text: str, chars: dict) -> dict | None:
        """LLM 一次提取：玩家见面、NPC 对话、NPC 动机"""
        npc_list = "\n".join(
            f"[{aid}] {cp.name} — {(cp.appearance or '')[:60]}"
            for aid, cp in sorted(chars.items())
        )
        prompt = f"""从以下序章叙述中提取结构化信息。

=== NPC 名册（仅含外貌，不含性格/秘密）===
{npc_list}

=== 序章原文 ===
{prologue_text[:6000]}

=== 提取规则 ===
1. player_met：玩家**直接互动过的** NPC。仅当满足以下条件之一才算"认识"：
   - NPC 向玩家自我介绍（说出名字并指向自己）
   - 玩家直接与该 NPC 对过话（从上下文可推断）
   - 玩家做出了明确指向该 NPC 的选择（如"走向银发少女"）
   不算认识：仅在远处看到、听到别人提到名字但未对上号、群体场景中一笔带过。
   "name_known" 表示玩家是否知道了该 NPC 的真名。

2. npc_dialogues：NPC 之间的对话摘录（原文中已有的，禁止编造）。
   只提取有实际信息交换的对话（自我介绍、争论、组队协商等）。

3. npc_motives：NPC 在序章结束时可能形成的初步意图或印象（基于原文推断，50 字以内）。

输出 JSON：
{{"player_met":[{{"npc_id":"npc_02","name_known":true,"impression":"慵懒天才"}}],"npc_dialogues":[{{"speaker":"npc_02","listener":"npc_05","content":"我叫朔夜，请多指教"}}],"npc_motives":[{{"npc_id":"npc_03","motive":"对银发少女的漫不经心产生了警惕"}}]}}"""
        try:
            return self.llm.chat_json(
                messages=[{"role":"user","content":prompt}],
                system="你是数据分析引擎。只提取原文明确存在的信息，禁止编造。",
                temperature=0.3, max_tokens=1536,
            )
        except Exception:
            return None

    def _apply_player_meetings(self, bridge_data: dict, chars: dict):
        """登记玩家认识的 NPC + 写入初印象 chat_history"""
        met_list = bridge_data.get("player_met", [])
        if not isinstance(met_list, list):
            return
        for entry in met_list:
            if not isinstance(entry, dict):
                continue
            npc_id = str(entry.get("npc_id", ""))
            if npc_id not in chars:
                continue
            self.world.player_met_npcs.add(npc_id)
            # 初印象 → chat_history seed
            impression = str(entry.get("impression", "") or "")
            name_known = bool(entry.get("name_known", False))
            cp = chars[npc_id]
            label = cp.name if name_known else (cp.appearance or "")[:30]
            content = f"初遇{label}。{impression}" if impression else f"初遇{label}。"
            self._seed_chat_history(npc_id, content)

    def _apply_npc_dialogues(self, bridge_data: dict):
        """播入 NPC-NPC 对话 → 双方 chat_history"""
        dialogues = bridge_data.get("npc_dialogues", [])
        if not isinstance(dialogues, list):
            return
        for d in dialogues:
            if not isinstance(d, dict):
                continue
            speaker = str(d.get("speaker", ""))
            listener = str(d.get("listener", ""))
            content = str(d.get("content", ""))[:200]
            if not speaker or not listener or not content:
                continue
            entry = {"speaker": speaker, "listener": listener, "content": content, "tick": 0}
            self._seed_chat_history(speaker, content)
            self._seed_chat_history(listener, content)

    def _apply_npc_motives(self, bridge_data: dict):
        """播入 NPC 内心动机 → private_motives"""
        motives = bridge_data.get("npc_motives", [])
        if not isinstance(motives, list):
            return
        for m in motives:
            if not isinstance(m, dict):
                continue
            npc_id = str(m.get("npc_id", ""))
            motive = str(m.get("motive", ""))[:200]
            if not npc_id or not motive:
                continue
            st = self.agent_states.get(npc_id)
            if st and st.alive:
                st.private_motives.append(motive)

    def _seed_chat_history(self, agent_id: str, content: str):
        """向 Agent 的 chat_history 写入一条种子记录"""
        agent = self.agents.get(agent_id)
        if agent and hasattr(agent, '_chat_history'):
            agent._chat_history.append({
                "speaker": "系统",
                "listener": agent_id,
                "content": content[:200],
                "tick": 0,
            })
            if len(agent._chat_history) > 10:
                agent._chat_history = agent._chat_history[-10:]

    def _bridge_affection(self, prologue_text: str, bridge_data: dict, chars: dict):
        """仿 _evaluate_affection 逻辑评估玩家↔NPC 好感变动"""
        met_list = bridge_data.get("player_met", [])
        if not isinstance(met_list, list) or not met_list:
            return
        interactions = []
        for entry in met_list:
            if not isinstance(entry, dict):
                continue
            npc_id = str(entry.get("npc_id", ""))
            if npc_id not in chars:
                continue
            cp = chars[npc_id]
            interactions.append({
                "npc_id": npc_id,
                "npc_name": cp.name or npc_id,
                "npc_personality": (cp.personality or "")[:80],
                "impression": str(entry.get("impression", "") or ""),
            })
        if not interactions:
            return

        items = []
        for i, inter in enumerate(interactions):
            items.append(
                f"交互{i+1}：玩家与 {inter['npc_name']}({inter['npc_personality']}) 初遇。"
                f"玩家印象：「{inter['impression']}」"
                f"\n  当前好感：玩家→{inter['npc_name']}=50，{inter['npc_name']}→玩家=50"
            )
        prompt = f"""评估玩家与以下 NPC 的初遇对好感度的影响。根据 NPC 性格和互动内容，判断好感度变化（-10 到 +10）。

{chr(10).join(items)}

规则：
- 双方好感独立评估（玩家→NPC 可能与 NPC→玩家不同）
- 友好/好奇的初遇通常正向(+1~+6)
- 冷漠/警惕的初遇倾向负向(-1~-4)
- 高冷性格的 NPC 初遇可能对玩家变化很小(0~+2)
- delta=0 表示关系不变

输出 JSON：
{{"evaluations":[{{"npc_id":"npc_02","player_delta":4,"npc_delta":2,"reason":"一句话原因"}}]}}"""
        try:
            result = self.llm.chat_json(
                messages=[{"role":"user","content":prompt}],
                system="你是游戏剧本的社交逻辑判断引擎。根据角色性格和交互内容，输出准确的好感度变化。",
                temperature=0.9, max_tokens=1024,
            )
        except Exception:
            return

        evals = result.get("evaluations", [])
        if not isinstance(evals, list):
            return

        player_st = self.agent_states.get("player")
        for ev in evals:
            if not isinstance(ev, dict):
                continue
            npc_id = str(ev.get("npc_id", ""))
            if npc_id not in chars:
                continue
            try:
                player_delta = max(-10, min(10, int(ev.get("player_delta", 0))))
                npc_delta = max(-10, min(10, int(ev.get("npc_delta", 0))))
            except (ValueError, TypeError):
                continue

            # 玩家→NPC
            if player_st:
                cur = player_st.affection_map.get(npc_id, 50)
                player_st.affection_map[npc_id] = max(0, min(100, cur + player_delta))

            # NPC→玩家
            npc_st = self.agent_states.get(npc_id)
            if npc_st and npc_st.alive:
                cur = npc_st.affection_map.get("player", 50)
                npc_st.affection_map["player"] = max(0, min(100, cur + npc_delta))

    # ====== 序章输出校验 ======

    def _validate_prologue_output(self, text: str):
        """校验：真名泄露 + LLM 异常叙事检测。非阻塞，仅日志警告。"""
        if not text or len(text) < 20:
            return
        warnings = []

        # 1. 真名泄露检测（NPC 名册比对，结构匹配）
        chars = self.scenario.get("characters", {}) if self.scenario else {}
        for aid, cp in chars.items():
            if not cp.name or len(cp.name) < 2:
                continue
            if cp.name in text and aid not in self.world.player_met_npcs:
                ctx = self._snippet_around(text, cp.name, 30)
                warnings.append(f"⚠ 真名泄露：{cp.name}({aid}) 尚未被玩家认识 → \"...{ctx}...\"")

        # 2. LLM 异常叙事检测
        try:
            result = self.llm.chat(
                messages=[{"role":"user","content":
                    f"序章阶段应当温馨安全，不应出现任何暴力、死亡、超自然恐怖或黑暗幻想元素。\n"
                    f"检查以下文本是否包含不适合序章的内容：\n\n{text[:2000]}\n\n"
                    f"只回答 SAFE 或 ANOMALY，ANOMALY 时用一句话说明原因。"}],
                system="你是内容安全审查引擎。",
                temperature=0.1, max_tokens=64,
            )
            if "ANOMALY" in result.upper():
                reason = result.split("\n", 1)[0].replace("ANOMALY", "").strip()
                warnings.append(f"⚠ LLM异常检测：{reason}")
        except Exception as e:
            warnings.append(f"⚠ 异常检测LLM调用失败：{str(e)[:100]}")

        for w in warnings:
            self._log("validate", w)

    @staticmethod
    def _snippet_around(text: str, keyword: str, radius: int = 30) -> str:
        """提取关键词周围的文本片段"""
        idx = text.find(keyword)
        if idx < 0:
            return ""
        start = max(0, idx - radius)
        end = min(len(text), idx + len(keyword) + radius)
        return text[start:end].replace("\n", " ")

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

    def run_round(self, progress_queue: queue.Queue):
        self.round_count += 1
        self.world.global_tick += 1
        self._advance_time()
        self.world.npc_locations["player"] = self.player_location
        progress_queue.put({"type":"round_start","round":self.round_count})
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
        first_delay_active = self.world.first_murder_delayed and self.world.rounds_since_last_murder < 6
        if first_delay_active:
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
        self._check_phase_transition()

        _npc_list = [{"agent_id":aid,"name":self.agents[aid].profile.name if aid in self.world.player_met_npcs else "？","affection":self.agent_states[aid].affection_map.get("player",50) if aid in self.agent_states else 50,"location":self.world.npc_locations.get(aid,""),"nearby":self.world.npc_locations.get(aid,"")==self.player_location,"alive":self.agent_states.get(aid,DEAD_NPC).alive,"emotion":self.agent_states[aid].emotional_state if aid in self.agent_states else ""} for aid in sorted(self.agents.keys())]
        _scene_label = self.scenario.get("name", self.scene_id) if self.scenario else self.scene_id
        progress_queue.put({"type":"round_end","scene_name":_scene_label,"day":self.world.current_day,"time":self.world.current_time,"phase":self.world.phase.value,"location":self.player_location,"floor":self.world.current_floor,"in_trial":bool(self.world.active_trial and self.world.active_trial.active),"alive_count":len(self.world.alive_npcs),"rule_text":"","time_event":getattr(self,'xbrdcst',None),"npcs":_npc_list,"ending_triggered":self.world.ending_triggered,"ending_resolved":self.world.ending_resolved})

    def _tick(self, minutes: int = 1):
        """推进游戏时间并执行所有 Agent 的 ActionPlan。"""
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
                        agent.plan(self.world, "当前计划完成，生成下一步")

            self._check_time_broadcasts(old_minutes, new_minutes)

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
        """推进游戏时间（分钟级）。正常模式默认 +60 分钟/轮。"""
        old_minutes = self.world.time_minutes
        old_day = self.world.current_day

        self._tick(minutes)

        if self.world.time_minutes >= 1440:
            self.world.time_minutes -= 1440
            self.world.current_day += 1
            self.world.current_time = _time_string(self.world.time_minutes)
            self._apply_daily_curse()

        if self.world.current_day > old_day:
            self.xbrdcst = "夜深了。新的一天开始。"

    def skip_time(self, target_hour: int) -> str:
        """跳过时间到指定整点，仅在玩家位于自己房间时可用。
        返回中断原因或完成摘要。"""
        from state import IntentType as _IT
        target_minutes = target_hour * 60
        if target_minutes <= self.world.time_minutes:
            target_minutes += 1440
        total = target_minutes - self.world.time_minutes

        for _ in range(total // 10):
            before = self.world.time_minutes
            self._tick(10)

            if self.world.time_minutes >= target_minutes:
                self.world.time_minutes = target_minutes
                self.world.current_time = _time_string(self.world.time_minutes)
                break

            if getattr(self, 'xbrdcst', None):
                msg = self.xbrdcst
                self.xbrdcst = None
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

    def _check_phase_transition(self):
        world = self.world
        if world.phase == GamePhase.BLACKOUT and self.player_created and len(world.player_met_npcs) >= 3:
            world.phase = GamePhase.UNDERCURRENT
        if world.phase == GamePhase.UNDERCURRENT and world.difficulty != DifficultyMode.STORY and world.discovered_bodies:
            world.phase = GamePhase.HUNTING

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
        trial = self.world.active_trial; defendant = trial.defendant_id; victim = trial.victim_id
        if not defendant: return "无法确定真凶。一名被怀疑者被带入阴影。"
        en = self.agent_states[defendant].name if defendant in self.agent_states else "未知"
        self.agent_states[defendant].alive = False; self.world.alive_npcs.discard(defendant); trial.executed_id = defendant
        is_guilty = (defendant == self.world.public_events[-1].actor_id) if self.world.public_events else False
        try:
            text = self.llm.chat(messages=[{"role":"user","content":f"魔女审判结果：{en}被指认为魔女。{'她是真凶。结合她的魔法、性格、动机和绝望，创作揭露创伤的处刑演出。' if is_guilty else '她是无辜的。创作充满遗言与抗争的处刑演出。'} 150-250字。"}], system="你是故事旁白。冷静精准且富有悲剧美学。", temperature=1.0, max_tokens=1024)
        except: text = f"{en}被处刑。{'她的罪孽随她一同消逝。' if is_guilty else '她的无辜随着执行成为永恒的遗憾。'}"
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
        branches = []
        for b in cfg.get("branches", []):
            cond = b.get("condition", "")
            if not cond: branches.append(b); continue
            if cond == "trial_executed_wrong":
                if self.world.active_trial and self.world.active_trial.defendant_id != self.world.active_trial.murder_actor_id:
                    branches.append(b)
        return {"trigger_type": tt, "revelation_hint": cfg.get("revelation_hint", ""), "branches": branches}

    def choose_ending(self, ending_id: str) -> str:
        if not self.world.ending_triggered or self.world.ending_resolved: return "结局不可用。"
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

_session_lock = threading.Lock()
session = GameSession()
scenarios.load("tianji_maze"); scenarios.load("cloud_holiday"); scenarios.load("snow_train")
