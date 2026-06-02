# PROTOCOL.md — Astral 跨 Agent 契约文档 v1.0

> 本文档定义 Agent A/B/C/D 之间的所有接口契约。
> 任何修改若涉及跨 Agent 边界，必须**先更新本文档，再修改代码**。
> 配套文档：[AGENTS.md](AGENTS.md)

---

## 1. SSE 事件类型契约

> 涉及：Agent C (server.py: `run_round()` 第 337-447 行) ↔ Agent D (app.js: `EventSource`)

| 事件类型 | 推送方字段 | 说明 |
|----------|-----------|------|
| `round_start` | `round: int` | 回合开始，包含回合编号 |
| `agent_done` | `agent_id: str, name: str, intent: str, target: str, completed: int, total: int` | 单个 Agent 决策完成 |
| `arbiter_start` | (无额外字段) | 仲裁开始 |
| `arbiter_done` | `rulings: [{agent_id, agent_name, intent, approved, success, description, downgraded}]` | description 截断至 120 字符 |
| `npc_approaches` | `npcs: [{agent_id, agent_name, suggestions: [str,str,str]}]` | 有 NPC 主动走向玩家 |
| `narrative_start` | (无额外字段) | GM 叙述开始 |
| `narrative_done` | `text: str, options: [{label, type, target, room}]` | GM 叙述文本 + 4 个结构化选项 |
| `round_end` | `day, time, phase, location, in_trial, alive_count, rule_text, time_event, npcs, ending_triggered, ending_resolved` | 回合结束总结 |
| `error` | `message: str` | 回合级错误 |
| `ending_triggered` | `trigger_type, branches, auto_ending?, revelation_hint` | 结局触发，branches 含可选择分支，auto_ending 表示自动结局 |
| `_done_` | (sentinel, 不在前端消费) | SSE 流结束标记 |

**选项 type 枚举**（Agent B gm.py ↔ Agent D app.js）：
- `dialogue` — 与特定 NPC 交谈，target 为 NPC 编号
- `investigate` — 调查物品/观察环境
- `explore` — 前往房间，room 为房间名
- `custom` — 自由行动，始终在第 4 位

---

## 2. API 端点全清单

> 涉及：Agent C (server.py) ↔ Agent D (app.js)

### 序章流程（7 步 + 续章交互）

| 方法 | 路径 | 请求体 | 响应体 |
|------|------|--------|--------|
| POST | `/api/prologue/mirror` | `{name, age, appearance}` | `{ok, step:1, text}` |
| POST | `/api/prologue/magic` | `{magic}` | `{ok, step:2, text}` |
| POST | `/api/prologue/difficulty` | `{mode: "A"/"B"/"C"}` | `{ok, step:3, text}` |
| GET | `/api/prologue/camp` | — | `{ok, step:4, text, options:[str]}` |
| POST | `/api/prologue/continue` | `{choice: str}` | `{ok, text, options, step, finished}` |
| GET | `/api/prologue/explore` | — | `{ok, step:5, text}` |
| GET | `/api/prologue/admin` | — | `{ok, step:6, text}` |
| POST | `/api/prologue/finish` | — | `{ok, step:7, text}` |

### 游戏循环

| 方法 | 路径 | 请求体 | 响应体 | 备注 |
|------|------|--------|--------|------|
| GET | `/api/round` | — | SSE 流 | **不要在此端点使用 JSON 响应。始终 SSE。** |
| POST | `/api/dialogue` | `{agent_id, message}` | `{ok, agent_name, response, affection}` | 需同位置 |
| POST | `/api/dialogue_suggestions` | `{agent_id}` | `{ok, suggestions: [str,str,str]}` | |
| POST | `/api/explore` | `{room}` | `{ok, room, description, location}` | 楼层转换检查 |
| POST | `/api/investigate` | `{action}` | `{ok, action, description, inventory?, trial_evidence?}` | 支持审判中调查 |
| POST | `/api/move_player` | `{room}` | `{ok, location}` | |

### 自由叙述与元指令

| 方法 | 路径 | 请求体 | 响应体 | 备注 |
|------|------|--------|--------|------|
| POST | `/api/meta` | `{command}` | `{ok, result, command}` | 元指令：检查角色/位置/时间 |
| POST | `/api/free_narrative` | `{action}` | `{ok, narrative, options}` | 自由行动叙述，不推进时间 |

### 时间与结局

| 方法 | 路径 | 请求体 | 响应体 | 备注 |
|------|------|--------|--------|------|
| POST | `/api/skip_time` | `{hour}` | `{ok, result, time, day}` | 跳过时间至整点 |
| POST | `/api/sleep` | — | `{ok, result, time, day}` | 睡觉至次日 7 点 |
| POST | `/api/ending/choose` | `{ending_id}` | `{ok, text, ending_id, ending_resolved}` | 选择结局分支 |

### 审判系统

| 方法 | 路径 | 请求体 | 响应体 |
|------|------|--------|--------|
| POST | `/api/trial/investigate` | `{action}` | `{ok, description}` |
| POST | `/api/trial/proceed` | — | `{ok, phase, text, stream_url?}` |
| GET | `/api/trial/debate_stream` | — | SSE 流（narrative_chunk / debate_done / error）|
| POST | `/api/trial/debate_option` | `{type, target, argument?}` | `{ok, phase, ready_for_stream?}` |
| POST | `/api/trial/argue` | `{argument}` | `{ok: true}` |
| GET | `/api/trial/state` | — | `{active, phase, victim_id, victim_name, turn_count, timer_remaining, evidence_count}` |
| GET | `/api/trial/evidence` | — | `{evidence: [...], count}` |
| POST | `/api/trial/evidence/add` | `{item}` | `{ok, evidence?, narrative?, error?}` |

### 存档系统

| 方法 | 路径 | 请求体 | 响应体 |
|------|------|--------|--------|
| POST | `/api/save/<slot>` | — | `{ok, slots}` | slot: 1-6 或 "auto" |
| POST | `/api/load/<slot>` | — | `{ok, player_name, day, time, location, round, npcs, narrative_log}` | |
| GET | `/api/slots` | — | `{slots: [{slot, label, description, timestamp, round_count}]}` | |
| POST | `/api/new_game` | `{scene_id}` | `{ok, scene_id, scene_name}` | 重置全局 session |
| POST | `/api/select_scene` | `{scene_id}` | `{ok, scene_id, scene_name}` | 同 new_game |

### 配置管理

| 方法 | 路径 | 请求体 | 响应体 |
|------|------|--------|--------|
| GET | `/api/profiles` | — | `{profiles: [...], active: str}` |
| POST | `/api/profiles` | `{name, base_url, api_key, model}` | `{ok, profiles}` |
| POST | `/api/profiles/activate` | `{name}` | `{ok, active}` |
| POST | `/api/profiles/delete` | `{name}` | `{ok, profiles}` |
| GET | `/api/test_connection` | — | `{ok, model?, latency_ms?, response?, error?}` |

### 场景与角色卡

| 方法 | 路径 | 请求体 | 响应体 |
|------|------|--------|--------|
| GET | `/api/scenes` | — | `{scenes: [{id, name, desc}]}` |
| GET | `/api/cards` | — | `{cards: [{name, age, appearance, magic, personality, filename}]}` |
| POST | `/api/cards` | `{name, age, appearance, magic, personality?}` | `{ok, filename, cards}` |
| DELETE | `/api/cards/<name>` | — | `{ok, cards}` |
| POST | `/api/start_with_card` | `{card_name}` | `{ok, name, age, appearance, magic, intro_text}` |

### 其他

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/state` | 完整游戏状态快照 |
| GET | `/api/shutdown` | 关闭服务端（`os._exit(0)`） |
| GET | `/` | 静态 index.html |

---

## 3. 存档格式契约

> 涉及：Agent A (state.py: to_dict/from_dict) ↔ Agent C (save_manager.py)

### 存档 JSON 顶层结构

```json
{
  "version": 1,
  "timestamp": "ISO 8601",
  "player_name": "str",
  "player_location": "str",
  "round_count": "int",
  "description": "str",
  "world": { /* WorldState.to_dict() */ },
  "agent_states": { "No.01": {/* AgentState.to_dict() */}, ... },
  "narrative_log": [{"type":"...","text":"...",...}]
}
```

### WorldState 存档字段清单（必须与 `save_manager.apply_loaded_state` 一致）

| 字段 | 类型 | save.py 映射行 | from_dict 序列化 |
|------|------|---------------|-----------------|
| `current_day` | int | L89 | ✓ |
| `current_time` | str | L90 | ✓ |
| `current_floor` | int | L91 | ✓ |
| `explored_rooms` | set[str] | L92 | ✓ |
| `npc_locations` | dict | L93 | ✓ |
| `public_events` | list[Event] | L94-95 (via from_dict) | ✓ |
| `phase` | GamePhase | L96 | ✓ |
| `difficulty` | DifficultyMode | L97 | ✓ |
| `player_met_npcs` | set[str] | L98 | ✓ |
| `global_tick` | int | L99 | ✓ |
| `discovered_bodies` | list[str] | L100 | ✓ |
| `player_inventory` | list[str] | L101 | ✓ |
| `room_item_state` | dict | L102 | ✓ |
| `knowledge_flags` | set[str] | L103 | ✓ |
| `rounds_since_last_murder` | int | L104 | ✓ |
| `first_murder_delayed` | bool | L105 | ✓ |
| `prologue_step` | int | L106 | ✓ |
| `floor_2_unlocked` | bool | L107 | ✓ |
| `floor_3_unlocked` | bool | L108 | ✓ |
| `world_revelation_phase` | int | L109 | ✓ |
| `player_magic` | str | L110 | ✓ |
| `alive_npcs` | set[str] | L111 | ✓ |
| `undiscovered_bodies` | list[str] | L112 | ✓ |
| `cursed_npc` | str | L113 | ✓ |

> **关键不变量**：此表中的字段名必须与 `state.py:WorldState` 的 dataclass 字段名一致，且 `save_manager.apply_loaded_state` 中的 `wd.get(...)` 调用必须覆盖所有字段。新增 WorldState 字段时，必须同步更新此表、`to_dict()`、`from_dict()`、`apply_loaded_state()` 四处。

---

## 4. 场景模块属性契约

> 涉及：Agent D (scenarios/*.py) ↔ Agent B (gm.py) ↔ Agent C (server.py)
> 所有场景模块通过 `scenarios/__init__.py` 的 `add_module()` 注册。

### 场景模块必须暴露的属性

| 属性 | 类型 | extract at `__init__.py:L?` | 消费者 |
|------|------|---------------------------|--------|
| `SCENE_ID` | str | L12 | server, gm |
| `SCENE_NAME` | str | L17 | server, gm |
| `GM_NAME` | str | L18 | server, gm |
| `GM_SYSTEM_PROMPT` | str | L19 | gm |
| `SCENE_DESC` | str | L35 | frontend |
| `START_ROOM` | str | L33 | server |
| `NPC_IDS` | list[str] | L34 | server |
| `CHARACTERS` | dict[str, CharacterProfile] | L20 | server, agent_engine, arbiter, gm |
| `ROOM_FEATURES` | dict[str, list] | L21 | server, gm |
| `FLOOR_ROOMS` | dict[int, list] | L22 | server |
| `FLOOR_TRANSITIONS` | dict | L23 | server |
| `PROLOGUE_MIRROR` | str | L24 | server |
| `PROLOGUE_MAGIC` | str | L25 | server |
| `PROLOGUE_DIFFICULTY` | str | L26 | server |
| `PROLOGUE_CAMP` | str | L27 | server |
| `PROLOGUE_EXPLORE` | str | L28 | server |
| `PROLOGUE_ADMIN` | str | L29 | server |
| `RULE_TEXT` | str | L30 | server, frontend |
| `TRIAL_RULES` | str | L31 | server, frontend |
| `EVENT_TIMES` | list | L32 | server, frontend |

> **命名合同**：属性名是字符串常量，在 `__init__.py:add_module()` 和全部 3 个场景模块中必须拼写一致。新增属性时必须：1) 在 `add_module()` 添加 `getattr()` 提取  2) 在 3 个场景模块添加定义  3) 更新此表。

---

## 5. 数据类不变量

> 涉及：Agent A (state.py)

### IntentType 枚举 ↔ 字符串映射

> 涉及：Agent A (state.py: IntentType enum) ↔ Agent B (agent_engine.py: `_parse_intent_type()`)

| IntentType 值 | 字符串 | agent_engine 映射 | arbiter 阶段权限 |
|---------------|--------|-------------------|-----------------|
| `SOCIALIZE` | `"socialize"` | 始终允许 | — |
| `EXPLORE` | `"explore"` | 始终允许 | — |
| `REST` | `"rest"` | 始终允许 | — |
| `CONFRONT` | `"confront"` | 始终允许 | — |
| `ISOLATE` | `"isolate"` | 始终允许 | — |
| `STALK` | `"stalk"` | UNDERCURRENT + HUNTING | — |
| `SABOTAGE` | `"sabotage"` | UNDERCURRENT + HUNTING | BLACKOUT 禁止，尸体旁被拦截 |
| `ATTACK` | `"attack"` | HUNTING only | 非 HUNTING → 降级为 CONFRONT；有目击者 → 降级 |
| `TRAP` | `"trap"` | HUNTING only | 非 HUNTING → 降级为 ISOLATE；风险 = LLM 自评 + 旁观者加成 |
| `DEFEND` | `"defend"` | HUNTING only | — |

### 好感度规则

| 行动 | 修正值 | 位置 |
|------|--------|------|
| SOCIALIZE 成功 | +5 (双方) | arbiter.py L357-358 |
| ATTACK/TRAP/CONFRONT 成功 | -10 (actor→target) | arbiter.py L355-356 |
| 玩家与 NPC 对话 | +5 (NPC→player) | server.py L677 |

### 好感度等级映射（0-100）

| 范围 | 等级 |
|------|------|
| 0-9 | 仇恨 |
| 10-19 | 敌对 |
| 20-29 | 冷淡 |
| 30-39 | 陌生 |
| 40-49 | 相识 |
| 50-59 | 友人 |
| 60-79 | 知己 |
| 80-100 | 恋人 |

### d6 风险掷骰阈值

> 涉及：`state.py:roll_risk()`（共享模块，arbiter 和 server 共用）

| 风险等级 | 成功骰值 (0-5) | 成功概率 |
|----------|---------------|----------|
| 不可能 | 无 | 0% |
| 极高风险 | [0] | 1/6 |
| 高风险 | [0, 1] | 2/6 |
| 中风险 | [0, 1, 2] | 3/6 |
| 较低风险 | [0, 1, 2, 3] | 4/6 |
| 低风险 | [0, 1, 2, 3, 4] | 5/6 |
| 无风险 | [0, 1, 2, 3, 4, 5] | 100% |


---

## 6. 三阶段游戏进程

> 涉及：Agent B (agent_engine: `_allowed_intents()`, arbiter: `_rule_on_intent()`) ↔ Agent C (server: `_check_phase_transition()`)

| 阶段 | GamePhase | 触发条件 | Agent 开放行动 | 攻击规则 |
|------|-----------|----------|---------------|----------|
| 黑箱沉默期 | `BLACKOUT` | 游戏开始 | socialize, explore, rest, confront, isolate | 禁止（降级为对峙） |
| 暗流缓冲期 | `UNDERCURRENT` | 认识全部 12 NPC | + stalk, sabotage | 禁止（降级为对峙） |
| 猎杀期 | `HUNTING` | 首起案件发生（尸体被发现） | + attack, trap, defend | 开放（需无人目击） |

### 首案延迟机制

前 6 轮 (`rounds_since_last_murder < 6` 且 `first_murder_delayed == True`) 中，所有 ATTACK 意图在 `server.py:run_round()` 中被强制改为 CONFRONT（第 363-367 行），在 arbiter 阶段审查之前。

---

## 7. 前端状态对象契约

> 涉及：Agent D (app.js: 全局 `S` 对象)

```javascript
S = {
  inPrologue: bool,        // 是否在序章
  prologueStep: int,       // 序章步骤 0-7
  playersTurn: bool,       // 玩家是否可以行动
  dialogueWith: str|null,  // 当前对话的 NPC agent_id
  debug: bool,             // 调试模式（URL ?debug=1 开启）
  npcData: [{             // NPC 面板数据
    agent_id, name, age, affection, threat, emotion,
    location, nearby
  }],
  _scene: str,             // 当前场景 ID
  _selectedCard: str|null  // 选中的角色卡名
}
```

---

## 8. 日志文件约定

> 涉及：Agent C (debug.py)

| 文件 | 路径 | 最大行数 | 写入者 |
|------|------|----------|--------|
| requests.log | `logs/requests.log` | 5000 | RequestLogger |
| agents.log | `logs/agents.log` | 5000 | AgentLogger |
| errors.log | `logs/errors.log` | 5000 | ExceptionCatcher |
| thread_errors.log | `logs/thread_errors.log` | 5000 | ExceptionCatcher (thread hook) |

---

## 9. 角色卡文件格式

> 涉及：Agent A (card_manager.py) ↔ Agent C (server: cards API)

```
name: 角色名
age: 16
appearance: 外貌描述
magic: 魔法能力描述
personality: 性格描述（可选）
```

存储在 `cards/*.txt`，文件名 = 角色名（sanitized, max 30 chars）。

---

## 10. 关键文件布局伪代码

> 此节提供 Agent B 各函数的行号索引，便于定位修改点。

### agent_engine.py 函数索引

| 函数 | 行号 | 作用 |
|------|------|------|
| `NPCAgent.__init__` | 14-24 | 初始化 Agent |
| `NPCAgent.perceive` | 28-57 | 构建 Perception 快照 |
| `NPCAgent.decide` | 59-108 | LLM 决策（多意图 JSON 解析） |
| `NPCAgent._build_decision_prompt` | 110-161 | 构建决策 prompt |
| `NPCAgent._allowed_intents` | 163-169 | 基于阶段的行动权限 |
| `NPCAgent.dialogue` | 171-199 | 对话回应生成 |
| `NPCAgent.update_affection` | 201-203 | 好感度修改 |
| `NPCAgent.update_threat` | 205-206 | 威胁度修改 |
| `_parse_intent_type` | 226-234 | 字符串→IntentType |

### arbiter.py 函数索引

| 函数 | 行号 | 作用 |
|------|------|------|
| `Arbiter.process_round` | 20-56 | 完整仲裁管线 |
| `Arbiter._detect_conflicts` | 58-69 | 冲突矩阵检测 |
| `Arbiter._rule_on_intent` | 71-160 | 单个意图裁决（阶段审查+目击者+风险+证据） |
| `Arbiter._assess_risk` | 162-219 | 风险评估（陷阱含旁观者加成） |
| `state.roll_risk` | state.py | d6 随机掷骰（共享） |
| `Arbiter._generate_evidence` | 237-282 | LLM 证据生成 |
| `Arbiter._build_ruling_description` | 284-326 | 裁定描述文本 |
| `Arbiter._apply_rulings` | 328-375 | 裁定结果写入世界状态 |

### server.py 核心函数索引

| 函数 | 行号 | 作用 |
|------|------|------|
| `GameSession.__init__` | 66-92 | 初始化游戏会话 |
| `GameSession.run_round` | 337-447 | **核心游戏循环**（Agent→仲裁→GM→SSE） |
| `GameSession._advance_time` | 449-456 | 时间推进 |
| `GameSession._broadcast_event` | 459-465 | 时间事件广播 |
| `GameSession._apply_daily_curse` | 474-484 | 每日诅咒 |
| `GameSession._atmosphere` | 486-512 | 氛围上下文生成 |
| `GameSession._check_phase_transition` | 522-527 | 阶段转换检测 |
| `GameSession.trial_proceed` | 536-555 | 审判阶段推进 |

---

*最后更新：2026-05-08 | 版本 v1.0 | 与 Astral v0.5 源码一致 | 对照 PRJECT_STATE.md 已修复问题清单核实*
