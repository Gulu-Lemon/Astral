"""
GM 叙述层 — 直接第三人称叙述 + 语境化选项
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
from state import WorldState, AgentState, Event, Ruling, GamePhase
from scenarios import get

DEFAULT_ROOM_FEATURE = "周围环境"


class GMNarrator:
    def __init__(self, llm, player_name: str = "玩家", scene_id: str = "", characters: Optional[dict] = None):
        self._llm = llm
        self.player_name: str = player_name
        self._narrative_history: list[str] = []
        self._scene_id = scene_id
        self._gm_prompt = ""
        self._characters = characters or {}
        self._social_facts: list[str] = []
        self._update_gm_prompt()

    def _update_gm_prompt(self):
        scenario = get(self._scene_id)
        self._gm_prompt = scenario.get("gm_prompt", "") if scenario else ""

    def set_scene(self, scene_id: str):
        self._scene_id = scene_id
        self._update_gm_prompt()

    def synthesize_round(self, rulings, world, agent_states, player_location, player_action="", materials=""):
        visible_rulings = [r for r in rulings if self._is_player_visible(r, world, player_location)]
        context = self._build_context(world, agent_states, player_location, visible_rulings)

        # 让 LLM 生成叙述 + 选项
        result = self._generate_narrative_and_options(context, player_action, visible_rulings, world, agent_states, player_location, materials)

        narrative_text = result.get("narrative", "")
        options = result.get("options", [])
        self._narrative_history.append(narrative_text)
        return NarrativeOutput(text=narrative_text, options=options, visible_events=visible_rulings)

    def _is_player_visible(self, ruling, world, player_loc):
        actor_loc = world.npc_locations.get(ruling.intent.agent_id, "")
        if actor_loc == player_loc:
            return True
        if ruling.intent.intent_type.value in ("attack", "trap") and ruling.success:
            return True
        if ruling.intent.intent_type.value == "confront" and ruling.success:
            witnesses = [aid for aid, aloc in world.npc_locations.items()
                        if aloc == actor_loc and aid not in (ruling.intent.agent_id, ruling.intent.target_id)]
            if len(witnesses) >= 2:
                return True
        return False

    def _build_context(self, world, agent_states, player_loc, visible_rulings):
        loc_npcs = [aid for aid, aloc in world.npc_locations.items() if aloc == player_loc and aid != "player"]
        nearby_names = [self._npc_label(aid) for aid in loc_npcs]
        return {"day": world.current_day, "time": world.current_time, "phase": world.phase.value,
                "location": player_loc, "nearby_npcs": nearby_names, "visible_rulings": visible_rulings,
                "all_met": world.all_npcs_met()}

    def _generate_narrative_and_options(self, ctx, player_action, visible_rulings, world, agent_states, player_loc, materials=""):
        rulings_desc = []
        for r in visible_rulings:
            actor = self._npc_label(r.intent.agent_id)
            desc = r.description
            reasoning = r.intent.reasoning
            if reasoning:
                desc += f"（动机：{reasoning}）"
            rulings_desc.append(f"{actor}: {desc}")

        scenario = get(self._scene_id)
        scene_name = scenario.get("name", "") if scenario else ""

        social_desc = "、".join(self._social_facts) if self._social_facts else ""

        # 房间交互特征
        room_features = scenario.get("room_features", {}).get(player_loc, []) if scenario else []
        feature_names = [f.get('name', '未知物品') for f in room_features] if room_features else [DEFAULT_ROOM_FEATURE]

        # 同位置 NPC 性格速写（完整性格，帮助写角色化对话）
        npc_sketches = []
        for aid, aloc in world.npc_locations.items():
            if aloc == player_loc and aid != "player":
                st = agent_states.get(aid)
                if st and st.alive:
                    cp = self._characters.get(aid)
                    if cp:
                        aff = st.affection_map.get('player', 50)
                        aff_hint = self._aff_hint(aff)
                        sketch_parts = []
                        sketch_parts.append(f"  {cp.name}[{aid}]: {getattr(cp, 'personality', '') or '未知'}")
                        sketch_parts.append(f"魔法: {getattr(cp, 'magic', '') or '未知'}")
                        sketch_parts.append(f"行为特征: {getattr(cp, 'play_core', '') or '未知'}")
                        sketch_parts.append(f"习惯: {getattr(cp, 'daily_habits', '') or '未知'}")
                        sketch_parts.append(f"外貌: {getattr(cp, 'appearance', '') or ''}（对你{aff_hint}）")
                        npc_sketches.append(" | ".join(sketch_parts))
        npc_sketch_str = "\n".join(npc_sketches) if npc_sketches else "（此处无人）"

        # NPC 间关系速览（仅高/低好感的关系）
        rel_lines = []
        loc_npcs = [aid for aid, aloc in world.npc_locations.items() if aloc == player_loc and aid != "player"]
        for i in range(len(loc_npcs)):
            for j in range(i + 1, len(loc_npcs)):
                a1, a2 = loc_npcs[i], loc_npcs[j]
                st1, st2 = agent_states.get(a1), agent_states.get(a2)
                if not st1 or not st2 or not st1.alive or not st2.alive:
                    continue
                aff12 = st1.affection_map.get(a2, 50)
                aff21 = st2.affection_map.get(a1, 50)
                if aff12 >= 65 or aff21 >= 65 or aff12 <= 25 or aff21 <= 25:
                    cp1 = self._characters.get(a1)
                    cp2 = self._characters.get(a2)
                    n1 = cp1.name if cp1 else a1
                    n2 = cp2.name if cp2 else a2
                    rel_lines.append(f"  {n1}[{a1}]↔{n2}[{a2}]：互信{max(aff12,aff21)}/警惕{min(aff12,aff21)}")
        rel_str = "\n".join(rel_lines) if rel_lines else "（暂无特殊关系）"

        # 玩家认识/未认识的 NPC
        known, unknown = [], []
        for aid in world.npc_locations:
            if aid == "player": continue
            st = agent_states.get(aid)
            if not st or not st.alive: continue
            if aid in world.player_met_npcs:
                cp = self._characters.get(aid)
                if cp: known.append(f"{cp.name}[{aid}]")
            else:
                cp = self._characters.get(aid)
                if cp: unknown.append(f"{cp.appearance}[{aid}]")
        known_str = "、".join(known) if known else "（还没有）"
        unknown_str = "、".join(unknown) if unknown else "无"

        # 场景基调
        scene_tone = self._scene_tone()

        # 从 world.public_events 读取最近事件的完整描述（与 Agent 共享数据源）
        event_details = ""
        recent_events = world.public_events[-8:]
        if recent_events:
            event_lines = []
            for evt in recent_events:
                desc = evt.full_description or evt.public_description
                if desc.strip():
                    event_lines.append(desc)
            event_details = "\n".join(event_lines) if event_lines else ""

        prompt = f"""{'【上回提要】\n' + world.last_narrative_summary + '\n' + '（时间已推进，请自然地接续而非重述上回内容。）\n\n' if world.last_narrative_summary else ''}第{ctx['day']}天 {ctx['time']} · {ctx['location']}

{scene_tone}

【当前氛围与社交动态】
{social_desc if social_desc else '（暂无特别动态）'}
{', '.join(rulings_desc) if rulings_desc else '（周围平静）'}

{'【NPC互动素材】（由角色自行生成，请编织入叙述）\n' + materials + '\n' if materials else ''}
{'【本轮事件详情】\n' + event_details + '\n' if event_details else ''}
【附近角色】
{npc_sketch_str}

【角色间关系】
{rel_str}

【玩家已认识】{known_str}
【尚未认识（用外貌特征称呼）】{unknown_str}
【可互动物品】{', '.join(feature_names)}
【玩家行动】{player_action if player_action else '观察周围'}

【禁止】编造新角色/新名字。不在"附近角色"列表中的 NPC 不得出现在叙述中。

=====

以第二人称叙述（用"你"称呼玩家，NPC用"她"）。

你收到了角色自行生成的对话和动作素材（见【NPC互动素材】）。你的工作是导演——将素材编织成流畅的文学叙述，而非凭空编造角色行为。要求：
- 感官细节（光、声音、温度、气味）自然融入叙述
- 决定互动的发生顺序和空间位置；突出2-3组关键互动，其余一笔带过
- 非对话素材（动作描写、场景过渡）可以自由改写、删减、合并以优化节奏
- 角色说出的对话应尽可能保持原文。若实在影响流畅度，可微调语气或添加不超过半句的衔接语，但不可改变对话本意
- 禁止添加素材中不存在的对话内容；禁止让角色说出素材中没有的话
- 【角色忠诚度】：每个 NPC 必须严格按照其性格与行为特征行事
- 【分段】每段5-6行。场景切换、视角转移、时间推进时换段。用空行分隔。
- 【略写】标记为[可略写]的素材可合并为一句话带过。非针对玩家的NPC互动也可压缩。只对戏剧性强或与玩家直接相关的互动展开详细描写。
- 已认识的人用名字，未认识的用外貌特征
- 【叙事钩子】叙述末尾自然地埋入1-2个钩子——未说完的话、引起好奇的细节、欲言又止的眼神
- 【选项与钩子呼应】4个选项应与叙事内容形成因果链

然后生成 4 个行动选项。D 始终是"（自定义行动）"或开放选项。不要用"前往XX""查看XX"的干瘪动宾结构，写成完整的句子。

输出 JSON：
{{
  "narrative": "叙述文本",
  "options": [
    {{"label":"选项1","type":"dialogue|investigate|explore|custom","target":"No.01或null","room":"房间名或null"}},
    {{"label":"选项2","type":"...","target":"...","room":"..."}},
    {{"label":"选项3","type":"...","target":"...","room":"..."}},
    {{"label":"选项4","type":"custom","target":null,"room":null}}
  ]
}}
type: dialogue(talk to NPC, target=ID), investigate(survey items), explore(move rooms, room=name), custom(free action, position 4)
"""

        gm_prompt = self._gm_prompt or "你是故事旁白和场景导演。你收到的是角色自行生成的对话和动作素材，你的工作是编织、安排、取舍——而非替角色说话。直接叙述，不要使用元语言。用简洁有力的文学语言，像小说而非攻略。"
        gm_prompt += f"\n\n场景：{scene_name}。{scene_tone}\n未认识的角色用外貌特征称呼，认识后用名字。每个角色的行为必须与其【行为特征】【习惯】严格一致，禁止OOC。\n\n【世界观】本作中的'魔法'是个人超常能力的代称。角色均来自普通现代世界（现代日本），她们的思维方式和认知是当代人的。禁止传统奇幻魔法比喻（魔法阵、魔力、魔杖、咒语），禁止魔法学院等奇幻设定。"

        try:
            result = self._llm.chat_json(
                messages=[{"role": "user", "content": prompt}],
                system=gm_prompt,
                temperature=1.0, max_tokens=4096,
            )
            narrative = result.get("narrative", "") or ""
            raw_options = result.get("options", []) or []
            options = GMNarrator._parse_structured_options(raw_options)
        except Exception:
            narrative = ""
            options = [{"label": "继续观察周围", "type": "investigate", "target": None, "room": None},
                       {"label": "与附近的人交谈", "type": "custom", "target": None, "room": None},
                       {"label": "探索这个区域", "type": "custom", "target": None, "room": None},
                       {"label": "（自定义行动）", "type": "custom", "target": None, "room": None}]
        return {"narrative": narrative, "options": options}

    def stream_narrative(self, rulings, world, agent_states, player_location, materials="", player_action=""):
        """流式生成纯叙述文本（不含选项），逐 chunk yield"""
        visible_rulings = [r for r in rulings if self._is_player_visible(r, world, player_location)]
        ctx = self._build_context(world, agent_states, player_location, visible_rulings)

        rulings_desc = []
        for r in visible_rulings:
            actor = self._npc_label(r.intent.agent_id)
            desc = r.description
            reasoning = r.intent.reasoning
            if reasoning:
                desc += f"（动机：{reasoning}）"
            rulings_desc.append(f"{actor}: {desc}")

        scenario = get(self._scene_id)
        scene_name = scenario.get("name", "") if scenario else ""
        social_desc = "、".join(self._social_facts) if self._social_facts else ""

        room_features = scenario.get("room_features", {}).get(player_location, []) if scenario else []
        feature_names = [f.get('name', '未知物品') for f in room_features] if room_features else [DEFAULT_ROOM_FEATURE]

        npc_sketches = []
        for aid, aloc in world.npc_locations.items():
            if aloc == player_location and aid != "player":
                st = agent_states.get(aid)
                if st and st.alive:
                    cp = self._characters.get(aid)
                    if cp:
                        aff = st.affection_map.get('player', 50)
                        aff_hint = self._aff_hint(aff)
                        met = aid in world.player_met_npcs
                        label = cp.name if met else getattr(cp, 'appearance', '某人')
                        sketch_parts = [f"  {label}[{aid}]: {getattr(cp, 'personality', '') or '未知'}"]
                        sketch_parts.append(f"魔法: {getattr(cp, 'magic', '') or '未知'}")
                        sketch_parts.append(f"行为特征: {getattr(cp, 'play_core', '') or '未知'}")
                        sketch_parts.append(f"习惯: {getattr(cp, 'daily_habits', '') or '未知'}")
                        sketch_parts.append(f"外貌: {getattr(cp, 'appearance', '') or ''}（对你{aff_hint}）")
                        npc_sketches.append(" | ".join(sketch_parts))
        npc_sketch_str = "\n".join(npc_sketches) if npc_sketches else "（此处无人）"

        rel_lines = []
        loc_npcs = [aid for aid, aloc in world.npc_locations.items() if aloc == player_location and aid != "player"]
        for i in range(len(loc_npcs)):
            for j in range(i + 1, len(loc_npcs)):
                a1, a2 = loc_npcs[i], loc_npcs[j]
                st1, st2 = agent_states.get(a1), agent_states.get(a2)
                if not st1 or not st2 or not st1.alive or not st2.alive:
                    continue
                aff12 = st1.affection_map.get(a2, 50)
                aff21 = st2.affection_map.get(a1, 50)
                if aff12 >= 65 or aff21 >= 65 or aff12 <= 25 or aff21 <= 25:
                    cp1 = self._characters.get(a1)
                    cp2 = self._characters.get(a2)
                    n1 = cp1.name if cp1 else a1
                    n2 = cp2.name if cp2 else a2
                    rel_lines.append(f"  {n1}[{a1}]↔{n2}[{a2}]：互信{max(aff12,aff21)}/警惕{min(aff12,aff21)}")
        rel_str = "\n".join(rel_lines) if rel_lines else "（暂无特殊关系）"

        known, unknown = [], []
        for aid in world.npc_locations:
            if aid == "player": continue
            st = agent_states.get(aid)
            if not st or not st.alive: continue
            if aid in world.player_met_npcs:
                cp = self._characters.get(aid)
                if cp: known.append(f"{cp.name}[{aid}]")
            else:
                cp = self._characters.get(aid)
                if cp: unknown.append(f"{cp.appearance}[{aid}]")
        known_str = "、".join(known) if known else "（还没有）"
        unknown_str = "、".join(unknown) if unknown else "无"

        scene_tone = self._scene_tone()

        event_details = ""
        recent_events = world.public_events[-8:]
        if recent_events:
            event_lines = []
            for evt in recent_events:
                desc = evt.full_description or evt.public_description
                if desc.strip():
                    event_lines.append(desc)
            event_details = "\n".join(event_lines) if event_lines else ""

        prompt = f"""{'【上回提要】\n' + world.last_narrative_summary + '\n' + '（时间已推进，请自然地接续而非重述上回内容。）\n\n' if world.last_narrative_summary else ''}第{ctx['day']}天 {ctx['time']} · {ctx['location']}

{scene_tone}

【当前氛围与社交动态】
{social_desc if social_desc else '（暂无特别动态）'}
{', '.join(rulings_desc) if rulings_desc else '（周围平静）'}

{'【NPC互动素材】（由角色自行生成，请编织入叙述）\n' + materials + '\n' if materials else ''}
{'【本轮事件详情】\n' + event_details + '\n' if event_details else ''}
【附近角色】
{npc_sketch_str}

【角色间关系】
{rel_str}

【玩家已认识】{known_str}
【尚未认识（用外貌特征称呼）】{unknown_str}
【可互动物品】{', '.join(feature_names)}
【玩家行动】{player_action if player_action else '观察周围'}

【禁止】编造新角色/新名字。不在"附近角色"列表中的 NPC 不得出现在叙述中。

=====

以第二人称叙述（用"你"称呼玩家，NPC用"她"）。

你是故事导演——将素材编织成流畅的文学叙述，而非凭空编造角色行为。要求：
- 不要按人逐条叙述。选取最重要的2-3组互动展开详细描写，其余压缩为一句话带过或完全省略
- 感官细节（光、声音、温度、气味）自然融入叙述
- 决定互动的发生顺序和空间位置；突出2-3组关键互动，其余一笔带过
- 非对话素材（动作描写、场景过渡）可以自由改写、删减、合并以优化节奏
- 角色说出的对话应尽可能保持原文。若实在影响流畅度，可微调语气或添加不超过半句的衔接语，但不可改变对话本意
- 禁止添加素材中不存在的对话内容；禁止让角色说出素材中没有的话
- 【角色忠诚度】：每个 NPC 必须严格按照其性格与行为特征行事
- 【分段】每段5-6行。场景切换、视角转移、时间推进时换段。用空行分隔。
- 【略写】标记为[可略写]的素材可合并为一句话带过。非针对玩家的NPC互动也可压缩。只对戏剧性强或与玩家直接相关的互动展开详细描写。
- 已认识的人用名字，未认识的用外貌特征
- 【叙事钩子】叙述末尾自然地埋入1-2个钩子——未说完的话、引起好奇的细节、欲言又止的眼神

只输出纯叙述文本。不要生成选项。不要输出 JSON。不要用 markdown。"""

        gm_prompt = self._gm_prompt or "你是故事旁白和场景导演。你收到的是角色自行生成的对话和动作素材，你的工作是编织、安排、取舍——而非替角色说话。直接叙述，不要使用元语言。用简洁有力的文学语言，像小说而非攻略。"
        gm_prompt += f"\n\n场景：{scene_name}。{scene_tone}\n未认识的角色用外貌特征称呼，认识后用名字。每个角色的行为必须与其【行为特征】【习惯】严格一致，禁止OOC。\n\n【世界观】本作中的'魔法'是个人超常能力的代称。角色均来自普通现代世界（现代日本），她们的思维方式和认知是当代人的。禁止传统奇幻魔法比喻（魔法阵、魔力、魔杖、咒语），禁止魔法学院等奇幻设定。"

        try:
            for chunk in self._llm.chat_stream(
                messages=[{"role": "user", "content": prompt}],
                system=gm_prompt,
                temperature=0.8, max_tokens=4096,
            ):
                yield chunk
        except Exception as e:
            raise RuntimeError(f"流式叙事生成失败: {e}") from e

    def generate_options(self, narrative_text, rulings, world, agent_states, player_location):
        """基于已生成的叙述文本，生成结构化行动选项"""
        scenario = get(self._scene_id)
        scene_name = scenario.get("name", "") if scenario else ""
        scene_tone = self._scene_tone()

        loc_npcs = [aid for aid, aloc in world.npc_locations.items() if aloc == player_location and aid != "player"]

        npc_sketches = []
        for aid in loc_npcs:
            st = agent_states.get(aid)
            if st and st.alive:
                cp = self._characters.get(aid)
                if cp:
                    aff = st.affection_map.get('player', 50)
                    met = aid in world.player_met_npcs
                    label = cp.name if met else getattr(cp, 'appearance', '某人')
                    sketch_parts = [f"  {label}[{aid}]: {getattr(cp, 'personality', '') or '未知'}"]
                    sketch_parts.append(f"外貌: {getattr(cp, 'appearance', '') or ''}（对你{self._aff_hint(aff)}）")
                    npc_sketches.append(" | ".join(sketch_parts))
            npc_sketch_str = "\n".join(npc_sketches) if npc_sketches else "（此处无人）"

            rel_lines = []
        for i in range(len(loc_npcs)):
            for j in range(i + 1, len(loc_npcs)):
                a1, a2 = loc_npcs[i], loc_npcs[j]
                st1, st2 = agent_states.get(a1), agent_states.get(a2)
                if not st1 or not st2 or not st1.alive or not st2.alive:
                    continue
                aff12 = st1.affection_map.get(a2, 50)
                aff21 = st2.affection_map.get(a1, 50)
                if aff12 >= 65 or aff21 >= 65 or aff12 <= 25 or aff21 <= 25:
                    cp1 = self._characters.get(a1)
                    cp2 = self._characters.get(a2)
                    n1 = cp1.name if cp1 else a1
                    n2 = cp2.name if cp2 else a2
                    rel_lines.append(f"  {n1}[{a1}]↔{n2}[{a2}]：互信{max(aff12,aff21)}/警惕{min(aff12,aff21)}")
        rel_str = "\n".join(rel_lines) if rel_lines else "（暂无特殊关系）"

        known, unknown = [], []
        for aid in world.npc_locations:
            if aid == "player": continue
            st = agent_states.get(aid)
            if not st or not st.alive: continue
            if aid in world.player_met_npcs:
                cp = self._characters.get(aid)
                if cp: known.append(f"{cp.name}[{aid}]")
            else:
                cp = self._characters.get(aid)
                if cp: unknown.append(f"{cp.appearance}[{aid}]")
        known_str = "、".join(known) if known else "（还没有）"
        unknown_str = "、".join(unknown) if unknown else "无"

        room_features = scenario.get("room_features", {}).get(player_location, []) if scenario else []
        feature_names = [f.get('name', '未知物品') for f in room_features] if room_features else [DEFAULT_ROOM_FEATURE]

        social_desc = "、".join(self._social_facts) if self._social_facts else "（暂无特别动态）"

        prompt = f"""场景：{scene_name}。{scene_tone}
玩家位置：{player_location}

【社交动态】{social_desc}

【附近角色与可互动对象】
{npc_sketch_str}

【角色间关系】
{rel_str}

【已认识（用名字称呼）】{known_str}
【尚未认识（用外貌特征称呼）】{unknown_str}
【可互动物品】{', '.join(feature_names)}

=====

以下是本轮叙事内容：
=====
{narrative_text}
=====

基于上述叙事，生成 4 个行动选项。要求：
- 与叙事内容形成因果链（钩子→探索→追问）；选项应与前面叙述有直接联系
- target 必须从上述【已认识】或【尚未认识】列表中选取，用 ID 格式（如 No.01）
- D 始终是"（自定义行动）"或开放选项
- 不要用"前往XX""查看XX"的干瘪动宾结构，写成完整的句子

输出 JSON：
{{
  "options": [
    {{"label":"选项1","type":"dialogue|investigate|explore|custom","target":"No.01或null","room":"房间名或null"}},
    {{"label":"选项2","type":"...","target":"...","room":"..."}},
    {{"label":"选项3","type":"...","target":"...","room":"..."}},
    {{"label":"选项4","type":"custom","target":null,"room":null}}
  ]
}}
type: dialogue(talk to NPC, target=ID), investigate(survey items), explore(move rooms, room=name), custom(free action, position 4)
"""

        gm_prompt = self._gm_prompt or "你是故事旁白和场景导演。"
        gm_prompt += f"\n\n场景：{scene_name}。{scene_tone}\n未认识的角色用外貌特征称呼，认识后用名字。\n\n【世界观】本作中的'魔法'是个人超常能力的代称。角色均来自普通现代世界（现代日本），她们的思维方式和认知是当代人的。禁止传统奇幻魔法比喻（魔法阵、魔力、魔杖、咒语），禁止魔法学院等奇幻设定。"

        try:
            result = self._llm.chat_json(
                messages=[{"role": "user", "content": prompt}],
                system=gm_prompt,
                temperature=0.7, max_tokens=512,
            )
            raw_options = result.get("options", []) or []
            if not raw_options:
                print(f"[generate_options] empty options from LLM, result keys: {list(result.keys())[:5]}")
            options = GMNarrator._parse_structured_options(raw_options)
        except Exception as e:
            import traceback
            print(f"[generate_options] FAILED: {e}\n{traceback.format_exc()}")
            options = [{"label": "继续观察周围", "type": "investigate", "target": None, "room": None},
                       {"label": "与附近的人交谈", "type": "custom", "target": None, "room": None},
                       {"label": "探索这个区域", "type": "custom", "target": None, "room": None},
                       {"label": "（自定义行动）", "type": "custom", "target": None, "room": None}]
        return options

    @staticmethod
    def _aff_hint(v):
        if v >= 70: return "很亲近"
        if v >= 50: return "友善"
        if v >= 35: return "比较陌生"
        if v >= 20: return "冷淡"
        return "有敌意"

    @staticmethod
    def _parse_structured_options(raw: list) -> list[dict]:
        opts = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            label = item.get("label", "") or ""
            if not label.strip():
                continue
            t = (item.get("type", "") or "investigate").strip()
            if t not in ("dialogue", "investigate", "explore", "custom"):
                t = "investigate"
            target = item.get("target") or None
            room = item.get("room") or None
            opts.append({"label": label.strip(), "type": t, "target": target, "room": room})
        if not opts:
            opts = [{"label": "（自定义行动）", "type": "custom", "target": None, "room": None}]
        return opts

    def _scene_tone(self) -> str:
        scenario = get(self._scene_id)
        if scenario:
            return scenario.get("scene_tone", "")
        return ""

    def _npc_label(self, agent_id):
        cp = self._characters.get(agent_id) if self._characters else None
        return f"{cp.name}[{agent_id}]" if cp else agent_id


@dataclass
class NarrativeOutput:
    text: str
    options: list  # list[dict] with label/type/target/room
    visible_events: list[Ruling]
