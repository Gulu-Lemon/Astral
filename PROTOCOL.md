# PROTOCOL.md — Astral 跨 Agent 契约文档 v1.0.2-alpha

> 本文档定义 Agent A/B/C/D 之间的所有接口契约。
> 任何修改若涉及跨 Agent 边界，必须**先更新本文档，再修改代码**。
> 配套文档：[AGENTS.md](AGENTS.md)

---

## 1. SSE 事件类型契约

> 涉及：Agent C (session.py: `run_round()`) ↔ Agent D (app.js: `EventSource`)

| 事件类型 | 推送方字段 | 说明 |
|----------|-----------|------|
| `round_start` | `round: int` | 回合开始，包含回合编号 |
| `agent_done` | `agent_id: str, name: str, intent: str, target: str, completed: int, total: int` | 单个 Agent 决策完成 |
| `arbiter_start` | (无额外字段) | 仲裁开始 |
| `arbiter_done` | `rulings: [{agent_id, agent_name, intent, approved, success, description, downgraded}]` | description 截断至 120 字符 |
| `npc_approaches` | `npcs: [{agent_id, agent_name, suggestions: [str,str,str]}]` | 有 NPC 主动走向玩家 |
| `narrative_start` | (无额外字段) | GM 叙述开始 |
| `narrative_chunk` | `text: str` | 流式叙述文本片段（逐 token 推送） |
| `options_start` | (无额外字段) | 选项生成开始 |
| `narrative_done` | `text: str, options: [{label, type, target, room}]` | GM 叙述全文 + 4 个结构化选项 |
| `round_end` | `scene_name, day, time, phase, location, floor, in_trial, alive_count, rule_text, time_event, npcs, ending_triggered, ending_resolved` | 回合结束总结 |
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

> 涉及：Agent C (blueprints/) ↔ Agent D (app.js)

### 序章流程

| 方法 | 路径 | 请求体 | 响应体 |
|------|------|--------|--------|
| POST | `/api/prologue/mirror` | `{name, age, appearance}` | `{ok, step:1, text}` |
| POST | `/api/prologue/magic` | `{magic}` | `{ok, step:2, text}` |
| POST | `/api/prologue/difficulty` | `{mode: "A"/"B"/"C"}` | `{ok, step:3, text}` |
| GET | `/api/prologue/camp` | — | `{ok, step:4, text, options:[str]}` |
| POST | `/api/prologue/continue` | `{choice: str}` | `{ok, text, options, step, finished, rule?}` |
| POST | `/api/prologue/finish` | — | `{ok, step:7, text}` |

### 游戏循环

| 方法 | 路径 | 请求体 | 响应体 | 备注 |
|------|------|--------|--------|------|
| GET | `/api/round` | `?elapsed=60` | SSE 流 | **始终 SSE，不用 JSON。** |
| POST | `/api/dialogue` | `{agent_id, message}` | `{ok, agent_name, response, affection, micro_narrative, elapsed_minutes}` | 需同位置 |
| POST | `/api/dialogue_suggestions` | `{agent_id, player_name?}` | `{ok, suggestions: [str,str,str]}` | |
| POST | `/api/explore` | `{room}` | `{ok, room, description, location, elapsed_minutes}` | 楼层转换检查 |
| POST | `/api/investigate` | `{action}` | `{ok, action, description, inventory?, trial_evidence?, elapsed_minutes}` | 支持审判中调查 |
| POST | `/api/move_player` | `{room}` | `{ok, location}` | |

### 时间与结局

| 方法 | 路径 | 请求体 | 响应体 | 备注 |
|------|------|--------|--------|------|
| POST | `/api/skip_time` | `{mode, hours?, hour?, minute?}` | `{ok, result, time, day}` | skip_hours / until |
| POST | `/api/sleep` | — | `{ok, result, time, day}` | 睡觉至次日 7 点 |
| POST | `/api/ending/choose` | `{ending_id}` | `{ok, text, ending_id, ending_resolved}` | 选择结局分支 |

### 自由叙述与元指令

| 方法 | 路径 | 请求体 | 响应体 | 备注 |
|------|------|--------|--------|------|
| POST | `/api/meta` | `{command}` | `{ok, result, command}` | 元指令：检查角色/位置/时间 |
| POST | `/api/free_narrative` | `{action}` | `{ok, narrative, options}` | 自由行动叙述，不推进时间 |

### 审判系统

| 方法 | 路径 | 请求体 | 响应体 |
|------|------|--------|--------|
| POST | `/api/trial/investigate` | `{action}` | `{ok, description}` |
| POST | `/api/trial/proceed` | — | `{ok, phase, text, stream_url?}` |
| GET | `/api/trial/debate_stream` | — | SSE 流（narrative_chunk / error / _done_） |
| POST | `/api/trial/debate_option` | `{type, target, argument?}` | `{ok, phase, ready_for_stream?}` |
| POST | `/api/trial/argue` | `{argument}` | `{ok: true}` |
| GET | `/api/trial/state` | — | `{active, phase, victim_id, victim_name, turn_count, timer_remaining, evidence_count}` |
| GET | `/api/trial/evidence` | — | `{evidence: [...], count}` |
| POST | `/api/trial/evidence/add` | `{item}` | `{ok, evidence?, narrative?, error?}` |

### 存档系统

| 方法 | 路径 | 请求体 | 响应体 |
|------|------|--------|--------|
| POST | `/api/save` | — | `{ok, filename, slots}` | 手动存档（生成时间戳文件名） |
| POST | `/api/save/auto` | — | `{ok, slots}` | 自动存档到 autosave.json |
| POST | `/api/load/<filename>` | — | `{ok, player_name, scene_id, scene_name, day, time, location, round, npcs, narrative_log, options}` | |
| DELETE | `/api/save/<filename>` | — | `{ok, slots}` | 删除存档（不删 autosave） |
| GET | `/api/slots` | — | `{slots: [{filename, auto, scene_id, player_name, description, timestamp, round_count, alive_count, total_npc, mtime, fsize}]}` | |
| POST | `/api/new_game` | `{scene_id}` | `{ok, scene_id, scene_name}` | 重置全局 session |
| POST | `/api/select_scene` | `{scene_id}` | `{ok, scene_id, scene_name}` | 同 new_game |

### 配置管理

| 方法 | 路径 | 请求体 | 响应体 |
|------|------|--------|--------|
| GET | `/api/profiles` | — | `{profiles: [...], active: str}` |
| POST | `/api/profiles` | `{name, base_url, api_key, model, temperature?, top_p?, agent_model?, arbiter_model?, gm_model?, thinking_mode?, thinking_budget?, agent_thinking?, arbiter_thinking?, gm_thinking?}` | `{ok, profiles}` |
| POST | `/api/profiles/activate` | `{name}` | `{ok, active}` |
| POST | `/api/profiles/delete` | `{name}` | `{ok, profiles}` |
| GET | `/api/test_connection` | — | `{ok, model?, latency_ms?, response?, error?}` |

### 场景与角色卡

| 方法 | 路径 | 请求体 | 响应体 |
|------|------|--------|--------|
| GET | `/api/scenes` | — | `{scenes: [{id, name, desc}]}` |
| GET | `/api/cards` | — | `{cards: [{name, age, appearance, magic, personality, filename, ...}]}` |
| POST | `/api/cards` | `{name, age, appearance, magic, personality?, raw_text?}` | `{ok, filename, cards}` |
| DELETE | `/api/cards/<name>` | — | `{ok, cards}` |
| POST | `/api/start_with_card` | `{card_name}` | `{ok, name, age, appearance, magic, intro_text}` |
| GET | `/api/cards/watch` | — | SSE 流（cards_updated 事件，2s 轮询） |

### 其他

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/state` | 完整游戏状态快照（含 map_data、npcs、inventory、trial 等） |
| GET | `/api/shutdown` | 关闭服务端（`os._exit(0)`） |
| GET | `/` | 静态 index.html |

---

## 3. 存档格式契约

> 涉及：Agent A (state.py: to_dict/from_dict) ↔ Agent C (save_manager.py)

### 存档 JSON 顶层结构

```json
{
  "version": 2,
  "scene_id": "str",
  "timestamp": "ISO 8601",
  "player_name": "str",
  "player_location": "str",
  "round_count": "int",
  "description": "str",
  "world": { /* WorldState.to_dict() */ },
  "agent_states": { "No.01": {/* AgentState.to_dict() */}, ... },
  "narrative_log": [{"type":"...","text":"...",...}],
  "prologue_context": [...],
  "prologue_turn": 0,
  "post_admin_explored": false,
  "player_action_log": [...],
  "last_options": [...]
}
```

### WorldState 存档字段清单（必须与 `save_manager.apply_loaded_state` 一致）

| 字段 | 类型 | from_dict 序列化 |
|------|------|-----------------|
| `current_day` | int | ✓ |
| `current_time` | str | ✓ |
| `time_minutes` | int | ✓ |
| `current_floor` | int | ✓ |
| `explored_rooms` | set[str] | ✓ |
| `npc_locations` | dict | ✓ |
| `public_events` | list[Event] | ✓ (via from_dict) |
| `phase` | GamePhase | ✓ |
| `difficulty` | DifficultyMode | ✓ |
| `player_met_npcs` | set[str] | ✓ |
| `global_tick` | int | ✓ |
| `discovered_bodies` | list[str] | ✓ |
| `active_trial` | Optional[TrialState] | ✓ (via from_dict) |
| `player_inventory` | list[str] | ✓ |
| `room_item_state` | dict | ✓ |
| `knowledge_flags` | set[str] | ✓ |
| `rounds_since_last_murder` | int | ✓ |
| `first_murder_delayed` | bool | ✓ |
| `prologue_step` | int | ✓ |
| `floor_2_unlocked` | bool | ✓ |
| `floor_3_unlocked` | bool | ✓ |
| `world_revelation_phase` | int | ✓ |
| `player_magic` | str | ✓ |
| `alive_npcs` | set[str] | ✓ |
| `undiscovered_bodies` | list[BodyRecord] | ✓ (via from_dict) |
| `cursed_npc` | str | ✓ |
| `atmosphere` | str | ✓ |
| `last_narrative_summary` | str | ✓ |
| `ending_triggered` | bool | ✓ |
| `ending_chosen` | str | ✓ |
| `ending_resolved` | bool | ✓ |
| `player_is_murderer` | bool | ✓ |

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

| IntentType 值 | 字符串 | 说明 |
|---------------|--------|------|
| `SOCIALIZE` | `"socialize"` | 社交互动 |
| `EXPLORE` | `"explore"` | 探索房间 |
| `REST` | `"rest"` | 休息 |
| `CONFRONT` | `"confront"` | 对峙 |
| `ISOLATE` | `"isolate"` | 孤立/冷落 |
| `STALK` | `"stalk"` | 跟踪 |
| `SABOTAGE` | `"sabotage"` | 破坏（尸体旁被拦截） |
| `ATTACK` | `"attack"` | 直接攻击（有目击者→降级） |
| `TRAP` | `"trap"` | 陷阱攻击（风险=LLM自评+旁观者加成） |
| `DEFEND` | `"defend"` | 防守 |
| `SEARCH` | `"search"` | 搜索证据（审判专用） |
| `INTERROGATE` | `"interrogate"` | 询问NPC（审判专用） |
| `GUARD` | `"guard"` | 看守现场（审判专用） |
| `WATCH` | `"watch"` | 观察他人（审判专用） |

> **v1.4 变更**：`_allowed_intents()` 已移除所有阶段权限限制，全部 10 种基础意图始终开放。审判专用 4 种仅在审判期间使用。

### 好感度规则

| 行动 | 修正值 | 位置 |
|------|--------|------|
| SOCIALIZE 成功 | +5 (双方) | arbiter.py `_fallback_affection` |
| ATTACK/TRAP/CONFRONT 成功 | -10 (actor→target) | arbiter.py `_fallback_affection` |
| 玩家与 NPC 对话 | LLM 动态评估 | session.py `_settle_player_affection` |

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

## 6. 前端状态对象契约

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

## 7. 日志文件约定

> 涉及：Agent C (debug.py)

| 文件 | 路径 | 最大行数 | 写入者 |
|------|------|----------|--------|
| requests.log | `logs/requests.log` | 5000 | RequestLogger |
| agents.log | `logs/agents.log` | 5000 | AgentLogger |
| errors.log | `logs/errors.log` | 5000 | ExceptionCatcher |
| thread_errors.log | `logs/thread_errors.log` | 5000 | ExceptionCatcher (thread hook) |

---

## 8. 角色卡文件格式

> 涉及：Agent A (card_manager.py) ↔ Agent C (server: cards API)

```
name: 角色名
age: 16
appearance: 外貌描述
magic: 魔法能力描述
personality: 性格描述（可选）
```

存储在 `cards/*.txt`，文件名 = 角色名（sanitized, max 30 chars）。支持三种格式：legacy（key:value）、star（『』章节）、Ajisai（<#> markdown）。

---

*最后更新：2026-06-05 | 版本 v1.0.2-alpha*
