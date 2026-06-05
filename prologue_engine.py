"""
PrologueEngine — 序章 7 步流程 + 桥接 + 自我介绍

从 session.py 提取，v1.0.2-alpha
"""
from __future__ import annotations
import re
from state import DifficultyMode


class PrologueEngine:
    """序章状态机，管理 mirror→magic→difficulty→camp→continue→finish 全流程"""

    def __init__(self):
        self._prologue_context: list[dict] = []
        self._prologue_turn: int = 0
        self._post_admin_explored: bool = False
        self._player_action_log: list[str] = []
        self._prologue_phase: str = "free"
        self._last_options: list[str] = []

    # ── context helpers ──

    def _scene_prompt(self, scenario: dict, key: str, **kwargs) -> str:
        template = scenario.get(f"prologue_{key}", "")
        if template:
            try:
                result = template.format(**kwargs)
                if '{' in result and '}' in result:
                    if re.search(r'\{[^}]*\}', result):
                        return kwargs.get("default", "")
                return result
            except (KeyError, ValueError):
                return kwargs.get("default", "")
        return kwargs.get("default", "")

    def _scene_context(self, scenario: dict, world, player_location: str, prologue: bool = False) -> str:
        name = scenario.get("name", "")
        tone = scenario.get("scene_tone", "")
        gm = scenario.get("gm_name", "")
        if prologue:
            rooms_str = "（序章阶段，其他区域尚未探索，处于未知状态。所有人仍在初始区域内。）"
        else:
            fr = scenario.get("floor_rooms", {})
            rooms_here = fr.get(world.current_floor, [])
            rooms_str = "、".join(rooms_here[:8]) if rooms_here else player_location
        return (
            f"场景：{name}\n"
            f"基调：{tone}\n"
            f"你在：{player_location}\n"
            f"可前往：{rooms_str}\n"
            f"GM角色（登场前禁止出现）：{gm}"
        )

    def _npc_profile_roster(self, scenario: dict, level: str = "L2") -> str:
        chars = scenario.get("characters", {})
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

    def _room_features(self, scenario: dict, room_name: str) -> str:
        feats = scenario.get("room_features", {}).get(room_name, [])
        names = [f.get('name', '未知设施') for f in feats[:8]]
        return "、".join(names) if names else "（无记录）"

    def _is_leave_attempt(self, llm, log_func, player_location: str, choice: str) -> bool:
        try:
            result = llm.chat(
                messages=[{"role":"user","content":
                    f"序章阶段，所有人都在【{player_location}】里，尚未去过任何其他地方。\n"
                    f"玩家刚刚做出了一个选择：\n"
                    f"「{choice}」\n\n"
                    f"判断：这个选择是否暗示玩家想要离开当前区域、去另一个房间或地点？\n"
                    f"只回答 YES 或 NO。"}],
                system="你是一个精确的意图分类器。",
                temperature=0.1, max_tokens=8,
            )
            return "YES" in result.upper()
        except Exception as e:
            log_func("system", f"离开意图判定LLM失败，默认不视为离开: {str(e)[:100]}")
            return False

    # ── prologue state helpers ──

    def _prologue_truncate_context(self):
        while len(self._prologue_context) > 12:
            self._prologue_context = self._prologue_context[2:]
        while len(self._player_action_log) > 8:
            self._player_action_log = self._player_action_log[-8:]

    def _player_action_prefix(self) -> str:
        if not self._player_action_log:
            return ""
        return "【玩家行动轨迹】\n" + "\n".join(f"- {b}" for b in self._player_action_log[-6:]) + "\n"

    # ── option parsing ──

    def _parse_prologue_options(self, text: str, log_func) -> list[str]:
        opts = []
        marker = re.search(r'【选项】', text)
        section = text[marker.start():] if marker else text
        for m in re.finditer(r'([A-D])[\.\s、：:)）]\s*(.+?)(?=\n\s*[A-D][\.\s、：:)）]\s*|\Z)', section, re.DOTALL):
            opt_text = m.group(2).strip()
            if len(opt_text) > 1: opts.append(opt_text)
        if len(opts) >= 2:
            return opts
        tail = text[-500:]
        for m in re.finditer(r'^[A-D][\.\s、：:)）]\s*(.+)$', tail, re.MULTILINE):
            opt_text = m.group(1).strip()
            if len(opt_text) > 1: opts.append(opt_text)
        if len(opts) >= 2:
            return opts
        log_func("system", f"选项解析失败，LLM原文尾500字:\n{text[-500:]}")
        return []

    @staticmethod
    def _strip_prologue_options(text: str) -> str:
        marker = re.search(r'【选项】', text)
        if marker: text = text[:marker.start()]
        cut = re.search(r'\n\s*A\.\s+', text)
        if cut: text = text[:cut.start()]
        return text.strip()

    # ── validation ──

    @staticmethod
    def _snippet_around(text: str, keyword: str, radius: int = 30) -> str:
        idx = text.find(keyword)
        if idx < 0:
            return ""
        start = max(0, idx - radius)
        end = min(len(text), idx + len(keyword) + radius)
        return text[start:end].replace("\n", " ")

    def _validate_prologue_output(self, llm, log_func, scenario: dict, world, text: str):
        if not text or len(text) < 20:
            return
        warnings = []
        chars = scenario.get("characters", {})
        for aid, cp in chars.items():
            if not cp.name or len(cp.name) < 2:
                continue
            if cp.name in text and aid not in world.player_met_npcs:
                ctx = self._snippet_around(text, cp.name, 30)
                warnings.append(f"真名泄露：{cp.name}({aid}) 尚未被玩家认识 → \"...{ctx}...\"")
        try:
            result = llm.chat(
                messages=[{"role":"user","content":
                    f"序章阶段应当温馨安全，不应出现任何暴力、死亡、超自然恐怖或黑暗幻想元素。\n"
                    f"检查以下文本是否包含不适合序章的内容：\n\n{text[:2000]}\n\n"
                    f"只回答 SAFE 或 ANOMALY，ANOMALY 时用一句话说明原因。"}],
                system="你是内容安全审查引擎。",
                temperature=0.1, max_tokens=64,
            )
            if "ANOMALY" in result.upper():
                reason = result.split("\n", 1)[0].replace("ANOMALY", "").strip()
                warnings.append(f"LLM异常检测：{reason}")
        except Exception as e:
            warnings.append(f"异常检测LLM调用失败：{str(e)[:100]}")
        for w in warnings:
            log_func("validate", w)

    # ── safe LLM call ──

    def _safe_llm(self, llm, log_func, scenario, world, msgs, sys, temp=1.0, mt=2048):
        try:
            text = llm.chat(messages=msgs, system=sys, temperature=temp, max_tokens=mt)
            if world and world.prologue_step < 7:
                self._validate_prologue_output(llm, log_func, scenario, world, text)
            return text
        except Exception as e1:
            if len(sys) > 500:
                try: return llm.chat(messages=msgs, system="你是旁白。第三人称。", temperature=temp, max_tokens=mt)
                except: pass
            try: return llm.chat(messages=msgs, system=None, temperature=temp, max_tokens=mt)
            except Exception as e3:
                emsg = str(e3)[:200]
                return f"(API 调用失败：{emsg}。请检查网络、API Key 或模型名是否正确。)"

    @staticmethod
    def _pgm(scenario) -> str:
        if scenario and scenario.get("gm_prompt"):
            return scenario.get("gm_prompt")
        return """你是故事旁白。严格遵守以下规则：
1. 只描述玩家能直接看到或听到的内容，不做全知视角叙述。
2. 不要编造未发生的事件。如果无事发生，描述环境氛围即可。
3. 不要透露任何 NPC 的秘密、动机或内心想法。
4. 不要赋予 NPC 其档案中没有的能力、物品或关系。
5. 用外貌特征称呼尚未自我介绍的陌生 NPC（如"银发少女"），但 NPC 在对话中自然互报姓名、做自我介绍是正常的社交行为。
6. 所有描写必须严格基于【当前房间设施】。
7. 不要引入超自然元素（除非场景设定明确允许）。
8. 叙事简洁，每次 3-5 句即可。"""

    # ═════════════════════════════════════
    #  Step 1-4: mirror, magic, difficulty, camp
    # ═════════════════════════════════════

    def step_1_mirror(self, llm, logger, scenario, world, agent_states, log_func,
                      name: str, age: str, appearance: str, set_player: callable) -> str:
        set_player(name, age, appearance)
        agent_states["player"].name = name
        self._prologue_context = []
        self._player_action_log = []
        prompt = self._scene_prompt(scenario, "mirror", name=name, age=age, appearance=appearance, player_name=name,
            default=f"玩家名为{name}，{age}岁，{appearance}。请用叙事者角度确认形象并引出魔法。")
        text = self._safe_llm(llm, logger, scenario, world,
            [{"role":"user","content":prompt}], self._pgm(scenario), 1.0, 1024)
        self._prologue_truncate_context()
        self._prologue_context.append({"role":"user","content":prompt})
        self._prologue_context.append({"role":"assistant","content":text})
        self._player_action_log.append(f"玩家{name}，{age}岁，{appearance}。")
        world.prologue_step = 1
        return text

    def step_2_magic(self, llm, logger, scenario, world, magic: str) -> str:
        world.player_magic = magic
        prompt = self._scene_prompt(scenario, "magic", magic=magic,
            default=f"玩家描述了魔法能力：{magic}。请确认并引出难度模式选择。")
        full_prompt = self._player_action_prefix() + prompt
        text = self._safe_llm(llm, logger, scenario, world,
            self._prologue_context+[{"role":"user","content":full_prompt}], self._pgm(scenario), 1.0, 1024)
        self._prologue_truncate_context()
        self._prologue_context.append({"role":"user","content":full_prompt})
        self._prologue_context.append({"role":"assistant","content":text})
        self._player_action_log.append(f"魔法觉醒：{magic}。")
        world.prologue_step = 2
        return text

    def step_3_difficulty(self, llm, logger, scenario, world, mode: str) -> str:
        mm = {"A":DifficultyMode.STORY,"B":DifficultyMode.NORMAL,"C":DifficultyMode.WITCH,
              "a":DifficultyMode.STORY,"b":DifficultyMode.NORMAL,"c":DifficultyMode.WITCH}
        world.difficulty = mm.get(mode, DifficultyMode.NORMAL)
        mn = {DifficultyMode.STORY:"剧情模式",DifficultyMode.NORMAL:"正常模式",DifficultyMode.WITCH:"魔女模式"}
        md = {DifficultyMode.STORY:"温馨美好的日常。",DifficultyMode.NORMAL:"杀人事件会发生，魔女审判会举行。",
              DifficultyMode.WITCH:"信任破裂，杀戮与被杀。"}
        mode_name = mn[world.difficulty]
        mode_desc = md[world.difficulty]
        prompt = self._scene_prompt(scenario, "difficulty", mode_name=mode_name, mode_desc=mode_desc,
            default=f"难度确定为{mode_name}。")
        full_prompt = self._player_action_prefix() + prompt
        text = self._safe_llm(llm, logger, scenario, world,
            self._prologue_context+[{"role":"user","content":full_prompt}], self._pgm(scenario), 0.9, 1024)
        self._prologue_truncate_context()
        self._prologue_context.append({"role":"user","content":full_prompt})
        self._prologue_context.append({"role":"assistant","content":text})
        self._player_action_log.append(f"难度：{mode_name}（{mode_desc}）。")
        world.prologue_step = 3
        return f"『{mode_name}』已确认。\n\n{text}"

    def step_4_camp(self, llm, logger, scenario, world, player_name: str,
                    player_location: str) -> dict:
        world.prologue_step = 4
        self._prologue_turn = 0
        self._prologue_phase = "free"
        prompt = self._scene_prompt(scenario, "camp", player_name=player_name,
            default=f"场景：{player_name}来到营地中央。")
        gm_name = scenario.get("gm_name", "")
        initial_prompt = f"""{self._scene_context(scenario, world, player_location, prologue=True)}

{self._player_action_prefix()}
{prompt}

【当前房间设施】{self._room_features(scenario, player_location)}

注意：
- 所有人——包括玩家和全部12名NPC——都聚集在相同的初始区域内，没有任何人离开过。
- 禁止描述任何其他区域的具体样貌（所有人此刻都不知道其他地方是什么样子）。
- 所有描写必须严格符合【当前房间设施】。禁止编造设施之外的物品或环境。
- 禁止让{gm_name}在此场景中出现。此时尚未登场。
- 以第三人称侧面描写 NPC。旁白描述时用外貌特征称呼尚未自我介绍的 NPC（如"银发少女"）——但 NPC 在对话中自然互报姓名、做自我介绍是正常的社交行为，不需要回避。
- 背景：12 名少女都在场内。以下是她们的真实档案，请严格按其外貌、性格、行为特征撰写：
{self._npc_profile_roster(scenario)}
- 本轮只选 2-3 名性格冲突的 NPC 创作特写场景，其余一笔带过。
- 保持直接叙述，300-400字即可。
- 禁止生成涉及离开当前区域的选项（如"去XX房间""探索XX""走向XX"）。所有人此刻都在{player_location}内，还没有人离开过。

末尾用以下精确格式输出 4 个互动选项：
【选项】
A.选项内容
B.选项内容
C.选项内容
D.选项内容"""
        text = self._safe_llm(llm, logger, scenario, world,
            self._prologue_context+[{"role":"user","content":initial_prompt}], self._pgm(scenario), 1.0, 2048)
        options = self._parse_prologue_options(text, logger)
        narrative = self._strip_prologue_options(text)
        if not options: options = ["与附近的人交谈","仔细观察周围环境","静静等待事态发展","查看周围人的反应"]
        self._last_options = options
        self._prologue_context.append({"role":"user","content":initial_prompt})
        self._prologue_context.append({"role":"assistant","content":text})
        self._player_action_log.append(f"进入场景：{player_location}。")
        return {"text": narrative, "options": options, "step": 4}

    # ═════════════════════════════════════
    #  Continue: state machine — free → admin → introduction → grouping → chosen
    # ═════════════════════════════════════

    def continue_(self, llm, logger, scenario, world, scene_id: str,
                  player_name: str, player_location: str, log_func,
                  player_choice: str) -> dict:
        self._prologue_turn += 1
        gm_name = scenario.get("gm_name", "")
        rule = scenario.get("rule_text", "")
        story_prefix = self._player_action_prefix()
        scene_ctx = self._scene_context(scenario, world, player_location)

        # Phase "chosen"
        if self._prologue_phase == "chosen":
            if player_choice in ("确认进入","_finish","进入游戏","开始游戏") or \
               any(k in player_choice for k in ("确认进入","_finish","进入游戏","开始游戏")):
                world.prologue_step = 7
                return {"text":"","options":[],"step":7,"finished":True}
            prompt = f"""{story_prefix}玩家选择了：{player_choice}

请简短描述{player_name}做出选择后的瞬间——周围NPC的反应、气氛的变化、{player_name}做选择时的内心感受。用第二人称。100-150字。"""
            text = self._safe_llm(llm, logger, scenario, world,
                self._prologue_context+[{"role":"user","content":prompt}], self._pgm(scenario), 0.9, 2048)
            self._prologue_truncate_context()
            self._prologue_context.append({"role":"user","content":prompt})
            self._prologue_context.append({"role":"assistant","content":text})
            narrative = self._strip_prologue_options(text)
            options = ["进入游戏"]
            self._last_options = options
            self._player_action_log.append(f"玩家选择了：{player_choice}")
            world.prologue_step = 6
            return {"text": narrative, "options": options, "step": 6}

        # Termination
        finish_keywords = ("确认进入","_finish","进入游戏","开始游戏")
        if player_choice in finish_keywords or any(k in player_choice for k in finish_keywords):
            if world.prologue_step >= 6:
                world.prologue_step = 7
                return {"text":"","options":[],"step":7,"finished":True}

        if self._prologue_turn >= 5:
            world.prologue_step = 7
            log_func("system", "序章已达到最大回合数，自动进入游戏。")
            return {"text":"","options":[],"step":7,"finished":True}

        # Phase "free" → "admin"
        if self._prologue_phase == "free":
            if self._prologue_turn >= 2:
                self._prologue_phase = "admin"
            elif self._is_leave_attempt(llm, log_func, player_location, player_choice):
                self._prologue_phase = "admin"
        if self._prologue_phase == "free":
            template = self._scene_prompt(scenario, "free", default="")
            if template:
                try:
                    prompt = template.format(
                        room=player_location,
                        room_features=self._room_features(scenario, player_location),
                        npc_profiles=self._npc_profile_roster(scenario),
                        scene_context=self._scene_context(scenario, world, player_location, prologue=True),
                        story_prefix=story_prefix,
                        player_choice=player_choice,
                    )
                except (KeyError, ValueError):
                    template = ""
            if not template:
                prompt = f"""{self._scene_context(scenario, world, player_location, prologue=True)}

{story_prefix}玩家选择：{player_choice}

描述接下来发生的事情。所有人仍在{player_location}内——没有任何人离开过初始区域。保持直接叙述。【当前房间设施】{self._room_features(scenario, player_location)}。禁止让{gm_name}出现。旁白描写时用外貌特征称呼尚未自我介绍的 NPC——但 NPC 之间自然交谈、互报姓名不受限制。

NPC 档案如下，请严格按其外貌、性格、行为特征撰写：
{self._npc_profile_roster(scenario)}

重要约束：严格按照【场景基调】描写环境。禁止编造场景中不存在的区域、建筑、设施或自然景观。禁止描述任何初始区域以外的地方。禁止生成涉及离开当前区域的选项。200-300字。

末尾输出4个选项：【选项】A. ... B. ... C. ... D. ..."""
            text = self._safe_llm(llm, logger, scenario, world,
                self._prologue_context+[{"role":"user","content":prompt}], self._pgm(scenario), 1.0, 2048)
            self._prologue_truncate_context()
            self._prologue_context.append({"role":"user","content":prompt})
            self._prologue_context.append({"role":"assistant","content":text})
            options = self._parse_prologue_options(text, log_func)
            narrative = self._strip_prologue_options(text)
            if not options: options = ["与附近的人交谈","仔细观察周围环境","静静等待事态发展","查看周围人的反应"]
            self._last_options = options
            self._player_action_log.append(f"玩家选择了：{player_choice}")
            return {"text": narrative, "options": options, "step": world.prologue_step}

        # Phase "admin"
        if self._prologue_phase == "admin":
            admin_entry = self._scene_prompt(scenario, "admin", default="").format(
                player_name=player_name, gm_name=gm_name)
            if not admin_entry:
                if scene_id == "snow_train":
                    admin_entry = f"列车长的声音从天花板上的扬声器中响起。广播系统发出「嗡——」的低频长音，随后是一声轻咳。「各位旅客，下午好。我是本次列车的列车长。请仔细阅读你们座椅口袋里的安全守则。」广播在电流声中断开。他本人不会现身——只有这个声音在车厢中回荡。每个人——包括{player_name}——都低头翻看起了手中的守则。"
                else:
                    admin_entry = f"经过一段时间的探索后，自然地引出了{gm_name}的出场。{gm_name}宣布了这里的规则，并示意所有人仔细阅读。每个人——包括{player_name}——都低头翻看起了规则。"
            prompt = f"""{story_prefix}玩家选择：{player_choice}

{admin_entry}

基于上述素材进行文学化叙事。以第三人称旁白。
- 完整引述{gm_name}的广播或宣告内容（用双引号括起原文，不得省略或概括）
- 描写环境氛围、声音的质感、众人的表情变化
- 以「{player_name}低下头，看着面前的规则。」收尾
不要描写任何人看完规则后的具体评论或内心反应——那些是选项被选择之后的事。150-200字。

末尾输出4个选项：【选项】
A. ...
B. ...
C. ...
D. ..."""
            text = self._safe_llm(llm, logger, scenario, world,
                self._prologue_context+[{"role":"user","content":prompt}], self._pgm(scenario), 0.9, 2048)
            self._prologue_truncate_context()
            self._prologue_context.append({"role":"user","content":prompt})
            self._prologue_context.append({"role":"assistant","content":text})
            narrative = self._strip_prologue_options(text)
            options = self._parse_prologue_options(text, log_func)
            if not options: options = ["认真记在心里","和旁边的人低声讨论","表面平静，内心盘算","觉得荒谬/不以为然"]
            self._last_options = options
            self._player_action_log.append("管理员登场，规则宣布。")
            world.prologue_step = 6
            self._prologue_phase = "introduction"
            return {"text": narrative, "options": options, "step": world.prologue_step, "rule": rule}

        # Phase "introduction" — 自我介绍 + 自然分组（合并）
        elif self._prologue_phase == "introduction":
            story_prefix = self._player_action_prefix()
            scene_ctx = self._scene_context(scenario, world, player_location)
            npc_info_lines = []
            for aid in sorted(scenario.get("characters", {}).keys()):
                cp = scenario["characters"][aid]
                appear_short = (cp.appearance or "")[:60]
                person_short = (cp.personality or "")[:60]
                npc_info_lines.append(f"[{aid}] {cp.name} | {appear_short} | {person_short}")
            npc_roster = "\n".join(npc_info_lines)
            n01 = scenario.get("characters", {}).get("No.01")
            n01_name = n01.name if n01 else "No.01"
            n01_person = (n01.personality or "一位少女")[:40]
            n01_given = n01_name.split()[-1] if n01 and " " in (n01.name or "") else n01_name
            prompt = f"""{scene_ctx}

{story_prefix}玩家阅读规则后，做出了反应。

就在这时，No.01——{n01_name}——站了出来，拍了拍手，用冷静但有温度的声音说道：「好了，各位。规则大家都看清了吧。在分开探索之前，我们先互相认识一下。我叫{n01_name}。」

在她的带动下，其他 NPC 也依次做了简短的自我介绍。有些人大方爽快，多说了几句自己的情况；有些人支支吾吾，只报了个名字就没话了。场面有点拘谨，但{n01_given}站在中间尽力让氛围不那么僵硬。

轮到{player_name}时，她也自然地接上了自己的名字。

自我介绍结束后，有人顺势提议：「既然大家都认识了，不如分头探索这个场所吧，效率更高。」其他人立刻开始讨论——有人想和刚才聊得投机的熟人一组，有人坚持独自行动，有人试图拉拢看起来靠谱的人。在几句争论后，逐渐形成了2-3个小组，另有1-2人选择独自探索。

以下是每个人的真实姓名和性格特征，请严格按照这些数据，让每个人都开口，并自然地完成分组：
{npc_roster}

重要：
- 前半段：按 No.01→No.12 顺序依次让每人自我介绍。每人1-3句话（含姓名，剩下按性格自由发挥）。
- 后半段：介绍完毕后自然地过渡到分组讨论，形成2-3个小组。{player_name}可以选择跟随某一组或独自探索。
- 对话要自然。有人开朗大方，有人害羞内向。禁止编造新名字。
- 末尾输出4个选项（包含分组选择）：【选项】A. ... B. ... C. ... D. ...
  其中A/B/C建议是"跟随XX那组"或"和XX一起"，D是"独自探索"或"先观察一下"。"""
            text = self._safe_llm(llm, logger, scenario, world,
                self._prologue_context+[{"role":"user","content":prompt}], self._pgm(scenario), 1.0, 3072)
            self._prologue_truncate_context()
            self._prologue_context.append({"role":"user","content":prompt})
            self._prologue_context.append({"role":"assistant","content":text})
            options = self._parse_prologue_options(text, log_func)
            narrative = self._strip_prologue_options(text)
            if not options: options = ["跟随第一组","跟随第二组","跟随第三组","独自探索"]
            self._last_options = options
            self._player_action_log.append("全员自我介绍并分组。")
            for aid in sorted(scenario.get("characters", {}).keys()):
                world.player_met_npcs.add(aid)
            world.prologue_step = 6
            self._prologue_phase = "chosen"
            return {"text": narrative, "options": options, "step": world.prologue_step}

    def generate_explore_scene(self, llm, logger, scenario, world, player_name: str) -> dict:
        self._post_admin_explored = True
        prompt = f"""{self._player_action_prefix()}管理员刚刚宣布了规则。现在少女们决定分头探索周围环境。请生成一个分组探索的场景：将全部 12 名 NPC 分成 2-3 组。每组 3-5 人。用外貌特征描述每组的 NPC。NPC 档案如下，请严格按其外貌、性格、行为特征描写：
{self._npc_profile_roster(scenario)}

{player_name}站在原地看着各组分头离开。末尾生成 4 个选项，让玩家选择跟随哪一组。第4个选项始终是"（独自探索）"。格式：【选项】A. ... B. ... C. ... D. ... 200-300字。"""
        text = self._safe_llm(llm, logger, scenario, world,
            self._prologue_context+[{"role":"user","content":prompt}], self._pgm(scenario), 1.0, 1024)
        self._prologue_truncate_context()
        self._prologue_context.append({"role":"user","content":prompt})
        self._prologue_context.append({"role":"assistant","content":text})
        options = self._parse_prologue_options(text, logger)
        narrative = self._strip_prologue_options(text)
        if not options: options = ["跟随第一组","跟随第二组","跟随第三组","独自探索"]
        self._player_action_log.append("分组探索场景生成。")
        options.append("进入游戏")
        self._last_options = options
        return {"text": narrative, "options": options, "step": 6}

    # ═════════════════════════════════════
    #  Finish: summarize + bridge
    # ═════════════════════════════════════

    def finish(self, llm, world, scenario, npc_ids, agent_states, agents, log_func) -> bool:
        world.prologue_step = 7
        for aid in npc_ids:
            world.player_met_npcs.add(aid)
        self._summarize(llm, world)
        self._bridge(llm, world, scenario, npc_ids, agent_states, agents, log_func)
        return True

    def _summarize(self, llm, world):
        if not self._prologue_context:
            world.last_narrative_summary = ""
            return
        prologue_msgs = [
            msg.get("content", "") for msg in self._prologue_context
            if msg.get("role") == "assistant"
        ]
        if not prologue_msgs:
            world.last_narrative_summary = ""
            return
        try:
            summary = llm.chat(
                messages=[{"role":"user","content":"将以下序章剧情写为一段连贯的前情提要。按时间顺序叙述关键事件：谁说了什么、谁和谁互动了、玩家的选择与反应、形成的初步关系。保留细节但不冗余。用第二人称叙述语气。\n\n" + "\n\n".join(prologue_msgs)}],
                system="你是故事编辑。连贯、有细节。",
                temperature=0.7, max_tokens=2048,
            )
            world.last_narrative_summary = summary.strip()
        except Exception:
            world.last_narrative_summary = ""

    def _prologue_full_text(self) -> str:
        if not self._prologue_context:
            return ""
        return "\n\n".join(
            msg.get("content", "") for msg in self._prologue_context
            if msg.get("role") == "assistant"
        )

    def _bridge(self, llm, world, scenario, npc_ids, agent_states, agents, log_func):
        prologue_text = self._prologue_full_text()
        if not prologue_text:
            return
        chars = scenario.get("characters", {})
        if not chars:
            return
        bridge_data = self._llm_extract_bridge(llm, prologue_text, chars)
        if not bridge_data:
            return
        self._apply_player_meetings(world, agents, bridge_data, chars)
        self._apply_npc_dialogues(agents, bridge_data)
        self._apply_npc_motives(agent_states, bridge_data)
        self._bridge_affection(llm, world, agent_states, NPC_IDS=list(npc_ids),
                               prologue_text=prologue_text, bridge_data=bridge_data, chars=chars)

    def _llm_extract_bridge(self, llm, prologue_text: str, chars: dict) -> dict | None:
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
            return llm.chat_json(
                messages=[{"role":"user","content":prompt}],
                system="你是数据分析引擎。只提取原文明确存在的信息，禁止编造。",
                temperature=0.3, max_tokens=1536,
            )
        except Exception:
            return None

    def _apply_player_meetings(self, world, agents, bridge_data: dict, chars: dict):
        met_list = bridge_data.get("player_met", [])
        if not isinstance(met_list, list):
            return
        for entry in met_list:
            if not isinstance(entry, dict):
                continue
            npc_id = str(entry.get("npc_id", ""))
            if npc_id not in chars:
                continue
            world.player_met_npcs.add(npc_id)
            impression = str(entry.get("impression", "") or "")
            name_known = bool(entry.get("name_known", False))
            cp = chars[npc_id]
            label = cp.name if name_known else (cp.appearance or "")[:30]
            content = f"初遇{label}。{impression}" if impression else f"初遇{label}。"
            self._seed_chat_history(agents, npc_id, content)

    def _apply_npc_dialogues(self, agents, bridge_data: dict):
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
            self._seed_chat_history(agents, speaker, content)
            self._seed_chat_history(agents, listener, content)

    def _apply_npc_motives(self, agent_states, bridge_data: dict):
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
            st = agent_states.get(npc_id)
            if st and st.alive:
                st.private_motives.append(motive)

    @staticmethod
    def _seed_chat_history(agents, agent_id: str, content: str):
        agent = agents.get(agent_id)
        if agent and hasattr(agent, '_chat_history'):
            agent._chat_history.append({
                "speaker": "系统",
                "listener": agent_id,
                "content": content[:200],
                "tick": 0,
            })
            if len(agent._chat_history) > 10:
                agent._chat_history = agent._chat_history[-10:]

    def _bridge_affection(self, llm, world, agent_states, NPC_IDS, prologue_text: str,
                          bridge_data: dict, chars: dict):
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
            result = llm.chat_json(
                messages=[{"role":"user","content":prompt}],
                system="你是游戏剧本的社交逻辑判断引擎。根据角色性格和交互内容，输出准确的好感度变化。",
                temperature=0.9, max_tokens=1024,
            )
        except Exception:
            return
        evals = result.get("evaluations", [])
        if not isinstance(evals, list):
            return
        player_st = agent_states.get("player")
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
            if player_st:
                cur = player_st.affection_map.get(npc_id, 50)
                player_st.affection_map[npc_id] = max(0, min(100, cur + player_delta))
            npc_st = agent_states.get(npc_id)
            if npc_st and npc_st.alive:
                cur = npc_st.affection_map.get("player", 50)
                npc_st.affection_map["player"] = max(0, min(100, cur + npc_delta))
