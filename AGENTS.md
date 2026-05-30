# Astral — Agent 分工方案 v1.0

> 本项目由 4 个 Agent 分工管理。每个 Agent 对其负责的文件拥有**唯一修改权**。
> 跨 Agent 变更必须先在本文件更新协议，再各自修改。
> 协议文档：[PROTOCOL.md](PROTOCOL.md)

---

## 项目架构概览

```
 玩家浏览器 ←SSE→ server.py (Flask, 37 API)
                        │
         ┌──────────────┼──────────────┐
         ▼              ▼              ▼
   agent_engine.py  arbiter.py    gm.py
   (12 NPC 并发决策) (冲突消解/掷骰) (文学叙述+选项)
         │              │              │
         └──────────────┴──────────────┘
                        │
                   state.py (6 dataclass + 3 enum)
                   characters.py (CharacterProfile)
                   llm.py (OpenAI 兼容 HTTP)
```

数据流管道：`玩家点击推进` → `ThreadPoolExecutor(8) 并发 agent.decide()` → `arbiter.process_round()` → `gm.synthesize_round()` → `SSE stream`

---

## Agent A：数据与契约管家 (Data Guardian)

### 负责文件（4 个，共 643 行）

| 文件 | 行数 | 角色 |
|------|------|------|
| `state.py` | 335 | 全部数据结构定义 |
| `characters.py` | 78 | CharacterProfile 类 + system_prompt 构建 |
| `card_manager.py` | 88 | 角色卡文件 CRUD |
| `llm.py` | 142 | LLMClient，线程安全 httpx |

### 职责

1. **state.py** — 定义和维护所有数据类/枚举：
   - 3 个枚举：`GamePhase`, `DifficultyMode`, `IntentType`
   - 6 个数据类：`WorldState`, `AgentState`, `Intent`, `Ruling`, `Event`, `Evidence`
   - 1 个子结构：`TrialState`
   - 每个数据类必须维护 `to_dict()` / `from_dict()` 序列化方法

2. **characters.py** — `CharacterProfile` 数据类 + `build_system_prompt()` + `register_character()` + 全局 `CHARACTERS` 字典

3. **card_manager.py** — 基于文件的角色卡管理：
   - `parse_card()` — 解析 cards/*.txt 格式
   - `format_card()` — 生成标准格式
   - `save_card()` / `delete_card()` / `list_cards()` / `get_card()`

4. **llm.py** — `LLMClient`：线程局部 `httpx.Client`，支持 `chat()` 和 `chat_json()`，`_extract_json()` 多级 JSON 回退解析

### 关键约束

- **修改任何数据类字段时，必须同步更新 `to_dict()` 和 `from_dict()`**。这是存档兼容性的生命线。
- `state.py` 的 `WorldState` 字段变更 → 立即通知 Agent C 检查 `save_manager.py:84-124` 的 `apply_loaded_state`
- `llm.py` 的接口签名（`chat()` / `chat_json()`）保持稳定，其余 Agent 都依赖此接口
- `card_manager.py` 的角色卡格式 `name: / age: / appearance: / magic: / personality:` 是外部接口，不要随意修改

### 被依赖关系

```
state.py      ← Agent B (agent_engine, arbiter, gm) + Agent C (server, save_manager)
characters.py ← Agent B (agent_engine, arbiter) + Agent D (scenarios)
llm.py        ← Agent B (agent_engine, arbiter, gm) + Agent C (server)
card_manager.py ← Agent C (server)
```

---

## Agent B：游戏逻辑引擎 (Game Logic)

### 负责文件（3 个，共 837 行）

| 文件 | 行数 | 角色 |
|------|------|------|
| `agent_engine.py` | 234 | NPCAgent 类，perceive/decide/dialogue |
| `arbiter.py` | 384 | Arbiter，冲突消解 + d6 掷骰 + 证据生成 |
| `gm.py` | 219 | GMNarrator，文学叙事 + 语境化选项 |

### 职责

1. **agent_engine.py** — NPC 决策核心：
   - `NPCAgent.__init__()` — 初始化单个 Agent
   - `perceive()` — 构建 Perception 快照（附近 NPC、可见事件）
   - `decide()` — 调用 LLM 生成多意图 JSON，解析为 Intent 列表
   - `dialogue()` — 生成 NPC 对话回应
   - `update_affection()` / `update_threat()` — 数值修改
   - `_allowed_intents()` — 基于 GamePhase 的行动权限（与 arbiter 的阶段审查必须同步）
   - `_parse_intent_type()` — 字符串→IntentType 映射

2. **arbiter.py** — 仲裁管线：
   - `process_round()` → `_detect_conflicts()` → `_rule_on_intent()` → `_apply_rulings()`
   - 阶段权限控制：BLACKOUT 禁攻击/陷阱/破坏，UNDERCURRENT 禁攻击/陷阱，HUNTING 全开放
   - 目击者检测：攻击时同位置有第三者 → 自动降级为对峙
   - 毁尸灭迹拦截：SABOTAGE 在尸体位置 → 自动失败
   - d6 风险掷骰系统：0-5 随机数 vs 风险等级阈值
   - 陷阱风险 = LLM 自评 + 旁观者人数加成（每 1 人 +1 级，最多 +3 级）
   - 证据生成：仅对 ATTACK/SABOTAGE 等恶意行为，ATTACK 用 LLM 生成 2-4 条证据
   - 好感度/威胁度修正：SOCIALIZE +5，ATTACK/TRAP/CONFRONT -10

3. **gm.py** — 叙述生成层：
   - `synthesize_round()` → `_build_context()` → `_generate_narrative_and_options()`
   - 玩家已认识/未认识 NPC 的区分（已知用名字，未知用外貌特征）
   - 场景边界规则（`_scene_tone()`）：3 个场景互斥内容限制
   - 结构化选项解析（`_parse_structured_options()`）
   - NPC 性格速写注入 GM prompt

### 关键约束

- **`agent_engine._allowed_intents()` 与 `arbiter._rule_on_intent()` 的阶段权限必须同步**。新增 IntentType 时两处都要更新。
- GM prompt 格式（任务 A 叙述 + 任务 B 选项 JSON）是 server.py 的 SSE 消费者依赖，修改 output JSON schema 时通知 Agent C。
- `gm._scene_tone()` 的内容与 Agent D 的场景包一一对应，新增场景时通知 Agent D。

### 被依赖关系

```
agent_engine.py ← Agent C (server.py: GameSession._init_agents, run_round, dialogue)
arbiter.py      ← Agent C (server.py: run_round)
gm.py           ← Agent C (server.py: run_round, prologue)
```

---

## Agent C：服务端与基础设施 (Infrastructure)

### 负责文件（4 个，共 1349 行）

| 文件 | 行数 | 角色 |
|------|------|------|
| `server.py` | ~1589 | Flask 37 API 端点 + GameSession 编排器 |
| `debug.py` | 151 | 4 个环形缓冲日志器 |
| `save_manager.py` | 130 | 自动存档 + 6 手动槽位 |
| `config_profiles.py` | 106 | API 多配置管理 |

### 职责

1. **server.py** — 整个项目的入口和编排层：
   - `GameSession` 类：序章 7 步流程、游戏主循环 `run_round()`、审判流程
   - 37 个 API 端点（详见 [PROTOCOL.md](PROTOCOL.md)）
   - SSE 流式推送（ThreadPoolExecutor 8 workers）
   - 时间推进系统：`_advance_time()` / `_broadcast_event()` / `_apply_daily_curse()`
   - 楼层解锁：`_check_floor_unlock()`
   - 阶段转换：`_check_phase_transition()`
   - 尸体发现：`undiscovered_bodies` + `newly_discovered` 机制
   - 审判自动启动：发现尸体 → `TrialState` 初始化 → 调查→陈述→辩论→论告→投票→处刑
   - 模块级 `session` 全局变量

2. **debug.py** — 日志基础设施：
   - `RingBuffer`：固定容量（5000 行）文件环形缓冲
   - `RequestLogger`：Flask 中间件，记录所有 API 请求耗时
   - `ExceptionCatcher`：全局异常捕获 + 线程异常钩子
   - `AgentLogger`：Agent 决策/仲裁/GM 叙事日志
   - `install_all()`：一行初始化全部

3. **save_manager.py** — 存档持久化：
   - `SaveManager.save()` — 序列化 WorldState + AgentStates → JSON
   - `SaveManager.load()` — 反序列化
   - `SaveManager.apply_loaded_state()` — 将 JSON 数据恢复到运行时对象（**最关键函数，必须与 state.py 同步**）
   - 7 个槽位：auto + slot_1~6

4. **config_profiles.py** — 多 API 配置：
   - `config_profiles.json` 读写
   - 支持增/删/改/激活配置
   - `apply_to_llm()` 将 active 配置注入 LLMClient

### 关键约束

- **`save_manager.apply_loaded_state()` (第 84-124 行) 是存档恢复的核心**。每次 Agent A 修改 `WorldState` 的字段，此函数必须同步更新恢复逻辑。
- **SSE 事件类型** (`run_round()` 中 push 的各种 `{"type": "..."}`) 必须与 Agent D 的 `app.js` 消费的事件类型一致。
- `debug.py` 的日志文件路径约定（`logs/requests.log` 等）是诊断基础，不要随意改名。
- **全局 `session` 变量**位于 server.py 模块作用域，是单例模式，注意多线程安全。

### 被依赖关系

```
server.py       ← Agent D (app.js 通过 SSE/API 消费)
debug.py        ← Agent C 内部 (server 启动时 install_all)
save_manager.py ← Agent C 内部 (server: save/load API)
config_profiles.py ← Agent C 内部 (server: profiles API)
```

---

## Agent D：内容与表现层 (Content & Frontend)

### 负责文件（7 个）

| 文件 | 行数 | 角色 |
|------|------|------|
| `scenarios/__init__.py` | 63 | 场景注册与加载器 |
| `scenarios/tianji_maze.py` | ~289 | 天际迷宫场景包 |
| `scenarios/cloud_holiday.py` | ~222 | 云端假期场景包 |
| `scenarios/snow_train.py` | ~308 | 风雪列车场景包 |
| `static/index.html` | ~159 | 单页面 UI 结构 |
| `static/app.js` | ~732 | 客户端逻辑（SSE/API 消费） |
| `static/style.css` | ~212 | 暗色主题样式 |

### 职责

1. **Scenarios 场景包** — 每个场景模块必须暴露以下属性（与 `__init__.py` 的 `add_module()` 对应）：

   | 属性 | 类型 | 说明 |
   |------|------|------|
   | `SCENE_ID` | str | 场景唯一 ID |
   | `SCENE_NAME` | str | 显示名称 |
   | `GM_NAME` | str | GM 角色名 |
   | `SCENE_DESC` | str | 场景简介 |
   | `START_ROOM` | str | 起始房间名 |
   | `NPC_IDS` | list[str] | 12 个 NPC 编号 |
   | `CHARACTERS` | dict | {agent_id: CharacterProfile} |
   | `ROOM_FEATURES` | dict | {room_name: [{name, description}]} |
   | `FLOOR_ROOMS` | dict | {floor_num: [room_names]} |
   | `FLOOR_TRANSITIONS` | dict | {room: {to_floor: n}} |
   | `GM_SYSTEM_PROMPT` | str | GM 的 system prompt |
   | `PROLOGUE_MIRROR` ~ `PROLOGUE_ADMIN` | str | 序章各步骤文案模板 |
   | `RULE_TEXT` | str | 规则原文 |
   | `TRIAL_RULES` | str | 审判规则 |
   | `EVENT_TIMES` | list | 定时事件列表 |

2. **static/index.html** — UI DOM 结构：
   - 顶栏：logo、场景标签、背包显示、游戏信息、难度徽章、楼层徽章、新游戏/设置/存档/退出按钮
   - 左侧：NPC 面板（好感度条、情绪标签、位置、同室绿标）
   - 中央：叙事区、序章界面、场景选择、审判横幅、对话框
   - 模态：存档面板、设置面板、角色卡编辑器

3. **static/app.js** — 客户端逻辑（732 行）：
   - SSE 消费：`EventSource` 监听 `/api/round`，处理 `round_start` / `agent_done` / `arbiter_done` / `narrative_done` / `round_end` / `npc_approaches` / `error` 事件
   - 序章流程：`prologueSubmit()` / `prologueChoose()` 驱动 7 步序章
   - 对话系统：`sendDialogue()` / `openDialogue()` / `closeDialogue()`
   - 审判 UI：`trialProceed()` 驱动调查→陈述→辩论→论告→投票→处刑
   - 存档管理：`toggleSave()` / `doSave()` / `doLoad()`
   - 设置管理：`showSettings()` / `saveSettings()` / `testAPIConnectionFromSettings()`
   - 场景选择：`showSceneSelection()` / `selectScene()`
   - 角色卡编辑器：`showCardEditor()` / `saveCardFromEditor()`
   - NPC 渲染：`renderNPCs()` 生成好感度条 + 情绪 + 位置

4. **static/style.css** — CSS 变量系统（`--bg` / `--accent` / `--danger` 等），暗色主题

### 关键约束

- **场景模块暴露的属性名与 `scenarios/__init__.py` 的 `add_module()` 中 `getattr()` 提取的属性名必须完全一致**。新增属性时，`__init__.py` 和所有 3 个场景模块必须同步。
- **`app.js` 的 SSE 事件类型**必须与 Agent C 的 `server.py:run_round()` 推送的事件类型一致。参见 [PROTOCOL.md](PROTOCOL.md) § SSE 事件类型表。
- **`app.js` 的 API 端点路径**必须与 `server.py` 的路由声明一致。
- 前端 CSS 类名和 HTML ID 不要在未通知 Agent C 的情况下修改（server.py 的 API 响应格式有时依赖前端特定的 key 名，如 `npcs` 数组的字段）。

### 被依赖关系

```
scenarios/     ← Agent C (server.py: GameSession.__init__, get_scene, etc.)
                ← Agent B (gm.py: _scene_tone, _generate_narrative_and_options)
static/        ← 浏览器直接加载，通过 SSE/API 与 Agent C 通信
```

---

## Agent 间协作流程

```
修改请求 → 判断影响范围
  │
  ├─ 只涉及自己文件 → 直接修改
  │
  ├─ 涉及 Agent A 的数据结构
  │   ├─ 在 AGENTS.md 记录变更
  │   ├─ Agent A 修改 state.py / characters.py（同步 to_dict/from_dict）
  │   ├─ Agent C 检查 save_manager.apply_loaded_state
  │   └─ Agent B/D 检查各自的消费代码
  │
  ├─ 涉及 SSE/API 契约
  │   ├─ 在 PROTOCOL.md 更新对应表格
  │   ├─ Agent C 修改 server.py
  │   └─ Agent D 修改 app.js
  │
  └─ 涉及场景内容
      ├─ Agent D 修改场景模块
      └─ Agent B 检查 gm._scene_tone() 是否需要更新
```

---

## 变更后维护

> **每次修改完成后，必须检查并更新以下两个文件：**

| 文件 | 维护内容 |
|------|---------|
| `FEATURES.md` | 新增/修改/删除的功能点，按分类更新功能清单 |
| `PROJECT_STATE.md` | 当前项目整体状态、已知问题、待办事项、版本号 |

这两个文件是项目的**状态地图**——任何 Agent 接手时首先读它们来理解项目当前情况。不维护会导致后续 Agent 基于过时信息做决策。

---

## 关联项目

| 项目 | 路径 | 关系 |
|------|------|------|
| **MythrosAgent** | `../MythrosAgent/` | CLI 原型 v0.1，共享相同模块名（state/agent_engine/arbiter/gm/llm/characters/save_manager），但无 Web 层、无场景系统、无角色卡。是 Astral 的前身/简化版。 |
| **模块/** | `../模块/` | 15 个 Word 设计文档（世界观、核心规则、叙事准则、协议框架、序章流程、章节总结、场景感知、角色库×4、备用角色库×4），是设计阶段的原始文档，不参与运行时。 |
| **角色卡/** | `../角色卡/` | 角色卡原始文件（.txt + .docx），部分已复制到 `Astral/cards/` |
| **魔法少女的系列/** | `../魔法少女的系列/` | 三个剧本的完整提示词文本（.txt + .docx），是场景 prompt 的原始素材 |

---

## 变更记录

### 2026-05-10 — v1.1 全面修复（21 项）

**跨 Agent 变更：FLOOR_TRANSITIONS 增加 `from_floor` 字段**
- Agent D（场景模块）：`tianji_maze.py`、`cloud_holiday.py`、`snow_train.py` 的 `FLOOR_TRANSITIONS` 每项增加 `from_floor` 键，声明该过渡的出发楼层
- Agent C（server.py）：`api_explore()` 在过渡前检查 `current_floor == ft[room].get("from_floor")`，拒绝跨层跳跃
- 新增 `SCENE_TONE` 属性：3 个场景模块 + `scenarios/__init__.py` 注册 + `gm._scene_tone()` 改为从注册表读取

**Agent A 变更（state.py / characters.py / llm.py / card_manager.py）：**
- `WorldState.atmosphere` 加入 `to_dict()`/`from_dict()`（存档不丢失氛围）
- `Intent`、`Ruling` 增加 `to_dict()`/`from_dict()` 序列化
- `Event.type` 改为 `event_type`（property 兼容旧代码，不再覆盖内置 `type`）
- `CharacterProfile` 增加 `to_dict()`/`from_dict()`；`register_character()` 覆盖时写日志
- `card_manager.parse_card()` 支持多行字段（personality 等）
- `LLMClient.chat()` 异常处理覆盖 `HTTPStatusError`；`reload_config()` 保留 `_config_path`

**Agent B 变更（agent_engine.py / arbiter.py / gm.py）：**
- `arbiter._apply_rulings()` 好感度修正前检查 `agent_states.get()` 防 KeyError
- `arbiter._rule_on_intent()` 增加 DEFEND 阶段守卫（非 HUNTING 期降级为 REST）
- `arbiter._generate_evidence()` 改用 `chat_json()` 替代私有 `_extract_json()`
- `agent_engine.decide()` 返回类型修正 `-> list[Intent]`
- `agent_engine` 日志改用 `logging` 替代 `print()`；修复 `recent_dialogue` dict 拼接
- `gm._scene_tone()` 改为从场景元数据读取 `scene_tone`
- `gm` 房间特征/CharacterProfile 字段增加 `getattr`/`get` 防御

**Agent C 变更（server.py / save_manager.py / style.css）：**
- 删除重复且损坏的 `prologue_continue` 方法（引用未定义变量 `text`）
- `save_manager.apply_loaded_state()` 恢复 `active_trial` 审判状态；`current_time` 默认值修正
- `server._get_common_room` 改为实例方法；`_atmosphere()` 改用场景元数据
- `api_new_game`/`api_select_scene` 会话替换加 `_session_lock`
- `style.css` 补 `#loading-overlay` 全屏遮罩 CSS 定位
- `GameSession.__init__()` 增加 `self._lock`

**Agent D 变更（场景模块）：**
- `cloud_holiday.py`：阳光茶室从迎宾大厅 ROOM_FEATURES 移除，为独立房间；补后勤/顶层楼梯特征
- `snow_train.py`：5 节车厢线性连接，`FLOOR_TRANSITIONS` 使用房间名作键，补车厢连接通道特征和第 5 节车厢过渡
- `tianji_maze.py`：删除重复 `import CharacterProfile`

---

*最后更新：2026-05-10 | 版本 v1.1*

---

## Agent skills

### Issue tracker

议题以本地 markdown 文件存储在 `.scratch/` 目录下。详见 `docs/agents/issue-tracker.md`。

### Triage labels

使用五个标准标签名：`needs-triage` / `needs-info` / `ready-for-agent` / `ready-for-human` / `wontfix`。详见 `docs/agents/triage-labels.md`。

### Domain docs

单上下文布局（`CONTEXT.md` + `docs/adr/` 在项目根目录）。详见 `docs/agents/domain.md`。
