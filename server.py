"""
Astral — 多 Agent 互动小说 Web 引擎 v0.5
Flask 服务端：序章流程 → 游戏循环 → 魔女审判
"""
from __future__ import annotations
import json, os, sys, re, queue, threading, time, random
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, request, jsonify, Response, send_from_directory, stream_with_context

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from state import (WorldState, AgentState, Intent, Event, Evidence, IntentType, GamePhase, DifficultyMode, TrialState, DEAD_NPC, roll_risk)
from llm import LLMClient
from agent_engine import NPCAgent
from arbiter import Arbiter
from gm import GMNarrator
from save_manager import SaveManager
from debug import install_all, AgentLogger
from card_manager import list_cards, save_card, delete_card, parse_card, get_card
import scenarios
from config_profiles import (list_profiles as _lcp, save_profile as _scp, activate as _acp, delete_profile as _dcp, get_active as _gac, apply_to_llm as _alc, apply_to_all_llms as _aal, PROFILES_PATH as _PFP)

app = Flask(__name__, static_folder="static", static_url_path="")

# === 模块级工具 ===

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

# === GameSession ===

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
        initial_prompt = f"""{self._player_action_prefix()}
{prompt}

【当前房间设施】{self._room_features(self.player_location)}

注意：
- 所有描写必须符合【当前房间设施】。禁止编造设施之外的物品或环境。
- 禁止让{gm_name}在此场景中出现。此时尚未登场。
- 以第三人称侧面描写 NPC，不要使用真名（用外貌特征描述）。
- 背景：12 名少女都在场内。以下是她们的真实档案，请严格按其外貌、性格、行为特征撰写：
{self._npc_profile_roster()}
- 本轮只选 2-3 名性格冲突的 NPC 创作特写场景，其余一笔带过。
- 保持直接叙述，300-400字即可。

末尾用以下精确格式输出 4 个互动选项：
【选项】
A.选项内容
B.选项内容
C.选项内容
D.选项内容"""
        text = self._safe_llm(self._prologue_context+[{"role":"user","content":initial_prompt}], self._pgm(), 1.0, 1024)
        options = self._parse_prologue_options(text)
        narrative = self._strip_prologue_options(text)
        if not options: options = ["与附近的人交谈","独自探索周围环境","仔细观察这个场所","走向最近的一扇门"]
        self._prologue_context.append({"role":"user","content":initial_prompt})
        self._prologue_context.append({"role":"assistant","content":text})
        self._player_action_log.append("序章开始：来到营地中央。")
        return {"text": narrative, "options": options, "step": 4}

    def prologue_continue(self, player_choice: str):
        self._prologue_turn += 1
        gm_name = self.scenario.get("gm_name", "")
        rule = self.scenario.get("rule_text", "")
        story_prefix = self._player_action_prefix()
        scene_id = self.scene_id

        # === Phase "chosen"：分组选择后 → 加入描述 + 唯一选项"进入游戏" ===
        if self._prologue_phase == "chosen":
            if player_choice in ("确认进入","_finish","进入游戏","开始游戏") or any(k in player_choice for k in ("确认进入","_finish","进入游戏","开始游戏")):
                self.world.prologue_step = 7
                return {"text":"","options":[],"step":7,"finished":True}
            prompt = f"""{story_prefix}玩家选择了：{player_choice}

请简短描述{self.player_name}做出选择后的瞬间——周围NPC的反应、气氛的变化、{self.player_name}做选择时的内心感受。用第二人称。100-150字。

末尾只输出1个选项：
【选项】
A. 进入游戏"""
            text = self._safe_llm(self._prologue_context+[{"role":"user","content":prompt}], self._pgm(), 0.9, 1024)
            self._prologue_truncate_context()
            self._prologue_context.append({"role":"user","content":prompt})
            self._prologue_context.append({"role":"assistant","content":text})
            options = self._parse_prologue_options(text)
            narrative = self._strip_prologue_options(text)
            if not options: options = ["进入游戏"]
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
            if self._prologue_turn >= 3:
                self._prologue_phase = "admin"
        if self._prologue_phase == "free":
            prompt = f"""{story_prefix}玩家选择：{player_choice}

描述接下来发生的事情。保持直接叙述。【当前房间】{self._room_features(self.player_location)}。禁止让{gm_name}出现。NPC 用外貌特征描述。NPC 档案如下，请严格按其外貌、性格、行为特征撰写：
{self._npc_profile_roster()}

玩家只能在当前区域活动，不要生成离开当前区域的选项。200-300字。

末尾输出4个选项：【选项】A. ... B. ... C. ... D. ..."""
            text = self._safe_llm(self._prologue_context+[{"role":"user","content":prompt}], self._pgm(), 1.0, 1024)
            self._prologue_truncate_context()
            self._prologue_context.append({"role":"user","content":prompt})
            self._prologue_context.append({"role":"assistant","content":text})
            options = self._parse_prologue_options(text)
            narrative = self._strip_prologue_options(text)
            if not options: options = ["继续探索","与附近的人交谈","仔细观察","等待事态发展"]
            self._player_action_log.append(f"玩家选择了：{player_choice}")
            return {"text": narrative, "options": options, "step": self.world.prologue_step}

        # === Phase "admin"：管理员登场/广播 + 规则宣布 → 选项=对规则的反应 ===
        if self._prologue_phase == "admin":
            if scene_id == "snow_train":
                admin_entry = f"列车长的声音从天花板上的扬声器中响起，带着轻微的电噪。广播系统发出「嗡——」的低频长音，随后是一声轻咳。「各位旅客，下午好。我是本次列车的列车长。请留意座椅口袋里的安全守则，仔细阅读。」广播在电流声中断开。他本人不会现身——只有这个声音在车厢中回荡。"
            else:
                admin_entry = f"经过一段时间的探索后，自然地引出了{gm_name}的出场。{gm_name}宣布了这里的规则。规则原文将由系统单独展示，你只需描写{gm_name}登场的气场和众人反应。"
            prompt = f"""{story_prefix}玩家选择：{player_choice}

{admin_entry}

所有人——包括{self.player_name}——都听完了规则。请描写听完规则后众人的反应：谁在沉思、谁不以为然、谁紧张地环顾四周、谁在低声交流。

末尾生成4个选项——均为{self.player_name}对规则的反应：
A. 认真记在心里
B. 和旁边的人低声讨论
C. 表面平静，内心盘算
D. 觉得荒谬/不以为然

格式：【选项】A. ... B. ... C. ... D. ...
200-300字。"""
            self.world.prologue_step = 6
            self._prologue_phase = "grouping"
        elif self._prologue_phase == "grouping":
            # === Phase "grouping"：分组场景 ===
            prompt = f"""{story_prefix}玩家对规则做出了反应。

随后，一位有领导气质的NPC站了出来，提议大家分组探索这个场所以提高效率。其他人立刻开始争论——有人想和熟人一组，有人坚持独自行动，有人试图拉拢强者。在争论中逐渐形成了2-3个小组，另有1-2人选择独自探索。

NPC 用外貌特征描述。NPC 档案如下，请严格按其外貌、性格、行为特征撰写：
{self._npc_profile_roster()}

同一组的成员在争论后会进行简短的自我介绍——自然地写出1-2句互报姓名和基本情况的对话。用外貌特征引入角色，通过对话揭示姓名。

末尾生成4个选项：
- 前2-3个选项是各组的特征简述（如"跟随栗色长发的女人和向日葵发卡的少女那一组"）
- 最后一个选项始终是"（独自探索）"

格式：【选项】A. ... B. ... C. ... D. ...
300-400字。"""
            self._prologue_phase = "chosen"
        text = self._safe_llm(self._prologue_context+[{"role":"user","content":prompt}], self._pgm(), 1.0, 1024)
        self._prologue_truncate_context()
        self._prologue_context.append({"role":"user","content":prompt})
        self._prologue_context.append({"role":"assistant","content":text})
        options = self._parse_prologue_options(text)
        narrative = self._strip_prologue_options(text)
        if not options: options = ["继续探索","与附近的人交谈","仔细观察","等待事态发展"]
        self._player_action_log.append(f"玩家选择了：{player_choice}")
        if self.world.prologue_step == 6:
            return {"text": narrative, "options": options, "step": self.world.prologue_step, "rule": rule if self._prologue_phase == "grouping" else ""}
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

    def prologue_step_5_explore(self):
        self.world.prologue_step = 5
        return "少女们分成几组开始探索周围的环境。"

    def prologue_step_6_admin(self):
        self.world.prologue_step = 6
        return ""

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
        for m in re.finditer(r'([A-D])\.\s*(.+?)(?=\n\s*[A-D]\.\s*|\Z)', section, re.DOTALL):
            opt_text = m.group(2).strip()
            if len(opt_text) > 1: opts.append(opt_text)
        return opts if len(opts) >= 2 else []

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
        """轻量校验：真名泄露、异常叙事。非阻塞，仅日志警告。"""
        if not text or len(text) < 20:
            return
        warnings = []

        # 1. 真名泄露检测
        chars = self.scenario.get("characters", {}) if self.scenario else {}
        for aid, cp in chars.items():
            if not cp.name or len(cp.name) < 2:
                continue
            if cp.name in text and aid not in self.world.player_met_npcs:
                ctx = self._snippet_around(text, cp.name, 30)
                warnings.append(f"⚠ 真名泄露：{cp.name}({aid}) 尚未被玩家认识 → \"...{ctx}...\"")

        # 2. 异常叙事关键词
        anomaly_keywords = ["尸体", "死亡", "死了", "杀戮", "血迹", "魔法阵", "恶魔", "诅咒", "幽灵"]
        found = [kw for kw in anomaly_keywords if kw in text]
        if found:
            warnings.append(f"⚠ 异常叙事关键词：{', '.join(found)}（序章不应出现）")

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
        parts.append(f"玩家：{player_name or '玩家'}")
        parts.append(f"NPC：{profile.name}（{profile.personality or '性格未知'}）")
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
        prompt = "\n".join(parts) + f"""\n\n请为{player_name or '玩家'}生成3个简洁自然的对话选项，可以对{profile.name}说。贴近当前关系、情境和剧情。输出 JSON：{{"suggestions":["...","...","..."]}} 只输出 JSON。"""
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

        # 2. 仲裁
        first_delay_active = self.world.first_murder_delayed and self.world.rounds_since_last_murder < 6
        if first_delay_active:
            for aid, il in intents.items():
                for intent in il:
                    if intent.intent_type == IntentType.ATTACK: intent.intent_type = IntentType.CONFRONT

        progress_queue.put({"type":"arbiter_start"})
        rulings = self.arbiter.process_round(intents, self.agent_states, self.world)

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
                    self.world.undiscovered_bodies.append(victim)

        newly_discovered = []
        for victim_id in list(self.world.undiscovered_bodies):
            body_loc = self.world.npc_locations.get(victim_id,"")
            if not body_loc: continue
            present = [aid for aid, aloc in self.world.npc_locations.items() if aloc == body_loc and aid != victim_id and self.agent_states.get(aid, DEAD_NPC).alive]
            if self.player_location == body_loc: present.append("player")
            if len(present) >= 2: newly_discovered.append(victim_id)
        for victim_id in newly_discovered:
            self.world.undiscovered_bodies = [v for v in self.world.undiscovered_bodies if v != victim_id]
            self.world.discovered_bodies.append(victim_id)
            if self.world.difficulty in (DifficultyMode.NORMAL, DifficultyMode.WITCH):
                self.world.active_trial = TrialState(active=True, phase="investigation", victim_id=victim_id)
            self.world.rounds_since_last_murder = 0
            self.world.first_murder_delayed = False
            vn = self.agent_states[victim_id].name if victim_id in self.agent_states else victim_id
            self._log("system", f"尸体被发现：{vn}。魔女审判开始。")

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
                        self.world.player_met_npcs.add(aid)
                        npc_approaches.append({"agent_id":aid,"agent_name":npc.profile.name,"suggestions":self._gen_dialogue_suggestions(aid, self.player_name),"opener":intent.scene_hint})
                        break
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
        materials = self.arbiter._build_narrative_materials(rulings)
        narrative = self.gm.synthesize_round(rulings, self.world, self.agent_states, self.player_location, materials=materials)
        self.last_narrative = narrative.text
        self.last_options = narrative.options
        self.world.last_narrative_summary = narrative.text[:800] if narrative.text else ""
        for f in social_facts: self._log("system", f"💬 {f}")
        self._log("gm", narrative.text)

        if self.logger: self.logger.log_narrative(narrative.text)

        progress_queue.put({"type":"narrative_done","text":narrative.text,"options":narrative.options})
        self._check_phase_transition()

        progress_queue.put({"type":"round_end","day":self.world.current_day,"time":self.world.current_time,"phase":self.world.phase.value,"location":self.player_location,"in_trial":bool(self.world.active_trial and self.world.active_trial.active),"alive_count":len(self.world.alive_npcs),"rule_text":"","time_event":getattr(self,'xbrdcst',None)})

    def _advance_time(self):
        world = self.world
        current = _parse_time(world.current_time)
        if current is None: world.current_time = "上午7点"; return
        hour = current + 1
        if hour >= 24: hour = 0; world.current_day += 1; self._apply_daily_curse()
        if hour >= 22: hour = 7; world.current_day += 1; self._apply_daily_curse(); world.current_time = "上午7点"; self.xbrdcst = "夜深了。所有人都回到自己的房间休息。新的一天开始。"; return
        world.current_time = _format_time(hour)
        if hour in (7,12,18,22): self._broadcast_event(hour)

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
        if world.phase == GamePhase.BLACKOUT and self.player_created and len(world.player_met_npcs) >= len(self.agents):
            world.phase = GamePhase.UNDERCURRENT
        if world.phase == GamePhase.UNDERCURRENT and world.difficulty != DifficultyMode.STORY and world.discovered_bodies:
            world.phase = GamePhase.HUNTING

    def trial_investigate(self, action: str) -> str:
        trial = self.world.active_trial
        if not trial or trial.phase != "investigation": return "没有进行中的调查阶段。"
        try:
            return self.llm.chat(messages=[{"role":"user","content":f"玩家调查：{action}。受害者：{trial.victim_id}。描述发现的线索，80-120字。"}], system="你是故事旁白。冷静、精确。", temperature=0.9, max_tokens=512)
        except: return "调查未发现特别的线索。"

    def trial_proceed(self) -> dict:
        trial = self.world.active_trial
        if not trial or not trial.active: return {"ok":False,"error":"没有审判","phase":""}
        trial.turn_count += 1
        if trial.phase == "investigation": trial.phase = "court_statement"; return {"ok":True,"phase":trial.phase,"text":"搜查结束。魔女审判开始。陈述阶段：每人依次发言。"}
        elif trial.phase == "court_statement": trial.phase = "court_debate"; return {"ok":True,"phase":trial.phase,"text":"辩论阶段。可以质疑证词。"}
        elif trial.phase == "court_debate": trial.phase = "closing"; return {"ok":True,"phase":trial.phase,"text":"辩论结束。如掌握足够线索可进行论告。"}
        elif trial.phase == "closing":
            if not trial.player_has_argued: return {"ok":False,"error":"请先进行论告","phase":trial.phase}
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

# === Module-level session ===
_session_lock = threading.Lock()
session = GameSession()
scenarios.load("tianji_maze"); scenarios.load("cloud_holiday"); scenarios.load("snow_train")

# === API Routes ===

@app.route("/")
def index(): return send_from_directory("static","index.html")

@app.route("/api/state")
def get_state():
    s = session.scenario if session.scenario else {}
    return jsonify({"player_name":session.player_name,"player_created":session.player_created,"scene_id":session.scene_id,"scene_name":s.get("name",""),"prologue_step":session.world.prologue_step,"day":session.world.current_day,"time":session.world.current_time,"floor":session.world.current_floor,"phase":session.world.phase.value,"difficulty":session.world.difficulty.value,"location":session.player_location,"round":session.round_count,"npcs":_npc_info(),"alive_count":len(session.world.alive_npcs),"in_trial":bool(session.world.active_trial and session.world.active_trial.active),"trial_phase":session.world.active_trial.phase if session.world.active_trial else "","trial_victim":session.world.active_trial.victim_id if session.world.active_trial else "","slots":session.save_mgr.list_slots(),"inventory":list(session.world.player_inventory),"room_items":session.world.room_item_state.get(session.player_location,{}),"knowledge_flags":sorted(session.world.knowledge_flags),"cards":list_cards(),"rule_text":s.get("rule_text",""),"trial_rules":s.get("trial_rules",""),"event_times":s.get("event_times",[]) if s else [],"map_data":_map_data()})

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

# Prologue APIs
@app.route("/api/prologue/mirror", methods=["POST"])
def api_mirror():
    d = request.get_json()
    return jsonify({"ok":True,"step":1,"text":session.prologue_step_1_mirror(d.get("name","无名"), d.get("age","16"), d.get("appearance","普通少女"))})

@app.route("/api/prologue/magic", methods=["POST"])
def api_magic():
    return jsonify({"ok":True,"step":2,"text":session.prologue_step_2_magic(request.get_json().get("magic","尚未觉醒"))})

@app.route("/api/prologue/difficulty", methods=["POST"])
def api_difficulty():
    return jsonify({"ok":True,"step":3,"text":session.prologue_step_3_difficulty(request.get_json().get("mode","B"))})

@app.route("/api/prologue/camp", methods=["GET"])
def api_camp():
    result = session.prologue_step_4_camp()
    return jsonify({"ok":True,"step":4,"text":result["text"] if isinstance(result,dict) else result,"options":result.get("options",[]) if isinstance(result,dict) else []})

@app.route("/api/prologue/continue", methods=["POST"])
def api_prologue_continue():
    result = session.prologue_continue(request.get_json().get("choice","").strip())
    if result is None:
        return jsonify({"ok":False,"error":"序章推进失败：内部状态异常，请尝试重新开始游戏。"})
    return jsonify({"ok":True,"text":result["text"],"options":result["options"],"step":result["step"],"finished":result.get("finished",False),"rule":result.get("rule","")})

@app.route("/api/prologue/explore", methods=["GET"])
def api_prologue_explore():
    return jsonify({"ok":True,"step":5,"text":session.prologue_step_5_explore()})

@app.route("/api/prologue/admin", methods=["GET"])
def api_admin():
    return jsonify({"ok":True,"step":6,"text":session.prologue_step_6_admin()})

@app.route("/api/prologue/finish", methods=["POST"])
def api_finish():
    session.prologue_finish()
    return jsonify({"ok":True,"step":7,"text":"序章结束。"})

# Game
@app.route("/api/round")
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

@app.route("/api/dialogue", methods=["POST"])
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
    # 微型叙事（纯场景描写，不含好感评估）
    micro = ""
    try:
        micro = session.llm.chat(
            messages=[{"role":"user","content":f"玩家对{agent.profile.name}说：「{msg}」\n{agent.profile.name}回答：「{resp}」\n请描述这个对话场景。以第二人称。避免元语言。"}],
            system=f"你是故事旁白。场景：{session.scenario.get('name','')}。", temperature=0.8, max_tokens=512)
    except: pass
    # 存入待结算队列，由下轮 run_round 批量评估好感变化
    session._pending_player_dialogues.append({
        "agent_id": aid, "msg": msg, "resp": resp, "tick": session.world.global_tick
    })
    return jsonify({"ok":True,"agent_name":agent.profile.name,"response":resp,"affection":agent.state.affection_map.get("player",50),"micro_narrative":micro})

@app.route("/api/dialogue_suggestions", methods=["POST"])
def api_dialogue_suggestions():
    data = request.get_json() or {}
    return jsonify({"ok":True,"suggestions":session._gen_dialogue_suggestions(data.get("agent_id",""), data.get("player_name", session.player_name or ""))})

@app.route("/api/explore", methods=["POST"])
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

@app.route("/api/investigate", methods=["POST"])
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

@app.route("/api/move_player", methods=["POST"])
def api_move_player():
    d = request.get_json(); target = d.get("room","").strip()
    fr = session.scenario.get("floor_rooms",{}) if session.scenario else {}
    if target and target in fr.get(session.world.current_floor,[]):
        session.player_location = target; session.world.explored_rooms.add(target)
    return jsonify({"ok":True,"location":session.player_location})

# Trial
@app.route("/api/trial/investigate", methods=["POST"])
def api_trial_investigate():
    return jsonify({"ok":True,"description":session.trial_investigate(request.get_json().get("action","查看现场"))})

@app.route("/api/trial/proceed", methods=["POST"])
def api_trial_proceed(): return jsonify(session.trial_proceed())

@app.route("/api/trial/argue", methods=["POST"])
def api_trial_argue():
    trial = session.world.active_trial
    if trial: trial.statements.append({"role":"player","content":request.get_json().get("argument",""),"type":"closing"}); trial.player_has_argued = True
    return jsonify({"ok":True})

@app.route("/api/trial/state")
def api_trial_state():
    trial = session.world.active_trial
    if not trial: return jsonify({"active":False})
    return jsonify({"active":trial.active,"phase":trial.phase,"victim_id":trial.victim_id,"victim_name":session.agent_states[trial.victim_id].name if trial.victim_id in session.agent_states else "未知","turn_count":trial.turn_count})

# Save/Load
@app.route("/api/save/<slot>", methods=["POST"])
def api_save(slot):
    if slot == "auto": pass
    else:
        try: slot = int(slot); assert 1 <= slot <= 6
        except: return jsonify({"ok":False,"error":"槽位 1-6 或 auto"})
    session.save_mgr.save(slot=slot, world=session.world, agent_states=session.agent_states, player_name=session.player_name, player_location=session.player_location, round_count=session.round_count, narrative_log=session.narrative_log, prologue_context=list(session._prologue_context), prologue_turn=session._prologue_turn, post_admin_explored=session._post_admin_explored, player_action_log=list(session._player_action_log))
    return jsonify({"ok":True,"slots":session.save_mgr.list_slots()})

@app.route("/api/load/<slot>", methods=["POST"])
def api_load(slot):
    if slot != "auto":
        try: slot = int(slot)
        except: return jsonify({"ok":False,"error":"无效槽位"})
    data = session.save_mgr.load(slot)
    if not data: return jsonify({"ok":False,"error":"槽位无存档"})
    session.player_name, session.player_location, session.round_count, action_log = session.save_mgr.apply_loaded_state(data, session.world, session.agents, session.agent_states)
    session._prologue_context = list(data.get("prologue_context", []))
    session._prologue_turn = data.get("prologue_turn", 0)
    session._post_admin_explored = data.get("post_admin_explored", False)
    session._player_action_log = action_log
    session.player_created = True; session.agent_states["player"].name = session.player_name
    if not session.world.room_item_state or all(not v for v in session.world.room_item_state.values()): session._init_room_items()
    return jsonify({"ok":True,"player_name":session.player_name,"day":session.world.current_day,"time":session.world.current_time,"location":session.player_location,"round":session.round_count,"npcs":_npc_info(),"narrative_log":data.get("narrative_log",[])})

@app.route("/api/slots")
def api_slots(): return jsonify({"slots":session.save_mgr.list_slots()})

@app.route("/api/new_game", methods=["POST"])
def api_new_game():
    global session
    sid = request.get_json().get("scene_id","tianji_maze")
    with _session_lock:
        session = GameSession(scene_id=sid)
    return jsonify({"ok":True,"scene_id":sid,"scene_name":session.scenario.get("name",sid) if session.scenario else sid})

@app.route("/api/select_scene", methods=["POST"])
def api_select_scene():
    global session
    sid = request.get_json().get("scene_id","tianji_maze")
    if sid not in {s["id"] for s in scenarios.list_scenarios()}: scenarios.load(sid)
    with _session_lock:
        session = GameSession(scene_id=sid)
    return jsonify({"ok":True,"scene_id":sid,"scene_name":session.scenario.get("name","")})

# Profiles
@app.route("/api/profiles")
def api_profiles(): return jsonify({"profiles":_lcp(),"active":_gac().get("name","")})

@app.route("/api/profiles", methods=["POST"])
def api_save_profile():
    d = request.get_json(); name = d.get("name","").strip()
    if not name: return jsonify({"ok":False,"error":"配置名不能为空"})
    _scp(name, d.get("base_url",""), d.get("api_key",""), d.get("model",""),
         d.get("temperature", 1.0), d.get("top_p", 0.95),
         d.get("agent_model",""), d.get("arbiter_model",""), d.get("gm_model",""))
    return jsonify({"ok":True,"profiles":_lcp()})

@app.route("/api/profiles/activate", methods=["POST"])
def api_activate_profile():
    name = request.get_json().get("name","").strip()
    if not name or not _acp(name): return jsonify({"ok":False,"error":"配置不存在"})
    _aal(session.llm, session.agent_llm, session.gm_llm)
    session._sync_arbiter_llm()
    return jsonify({"ok":True,"active":name})

@app.route("/api/profiles/delete", methods=["POST"])
def api_delete_profile():
    _dcp(request.get_json().get("name","").strip())
    if _gac():
        _aal(session.llm, session.agent_llm, session.gm_llm)
        session._sync_arbiter_llm()
    return jsonify({"ok":True,"profiles":_lcp()})

@app.route("/api/test_connection")
def api_test_connection():
    bu = session.llm.base_url.strip()
    if not bu: return jsonify({"ok":False,"error":"接口地址为空。","base_url":""})
    if not session.llm.api_key or not session.llm.api_key.strip(): return jsonify({"ok":False,"error":"API Key 为空。","base_url":bu})
    try:
        start = time.time()
        resp = session.llm.chat(messages=[{"role":"user","content":"回复一个词：连通"}], temperature=0.1, max_tokens=16)
        return jsonify({"ok":True,"model":session.llm.model,"latency_ms":round((time.time()-start)*1000),"response":resp[:50]})
    except Exception as e: return jsonify({"ok":False,"error":str(e)[:300],"base_url":bu})

@app.route("/api/shutdown")
def api_shutdown():
    import os as _os; _os._exit(0)

# Scenes & Cards
@app.route("/api/scenes")
def api_scenes(): return jsonify({"scenes":scenarios.list_scenarios()})

@app.route("/api/cards")
def api_cards(): return jsonify({"cards":list_cards()})

@app.route("/api/cards", methods=["POST"])
def api_save_card():
    d = request.get_json(); name = d.get("name","").strip()
    if not name: return jsonify({"ok":False,"error":"角色名不能为空"})
    fname = save_card(name, d.get("age","16"), d.get("appearance",""), d.get("magic",""), d.get("personality",""))
    return jsonify({"ok":True,"filename":fname,"cards":list_cards()})

@app.route("/api/cards/<name>", methods=["DELETE"])
def api_delete_card(name: str): return jsonify({"ok":delete_card(name),"cards":list_cards()})

@app.route("/api/start_with_card", methods=["POST"])
def api_start_with_card():
    card = get_card(request.get_json().get("card_name","").strip())
    if not card: return jsonify({"ok":False,"error":"角色卡不存在"})
    text = session.prologue_step_1_mirror(card["name"], card["age"], card["appearance"])
    session.world.player_magic = card["magic"]
    if card.get("personality"): session.world.player_magic += f" （性格: {card['personality']}）"
    return jsonify({"ok":True,"name":card["name"],"age":card["age"],"appearance":card["appearance"],"magic":card["magic"],"intro_text":text})

@app.route("/api/meta", methods=["POST"])
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

@app.route("/api/free_narrative", methods=["POST"])
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

# === Main ===
def main():
    print("="*50); print("  Astral v0.5 — 多 Agent 互动小说引擎"); print("  3 场景 · 12 NPC · 37 API"); print("  http://127.0.0.1:8640"); print("="*50)
    install_all(app); app.run(host="0.0.0.0", port=8640, debug=False, threaded=True)

if __name__ == "__main__": main()
