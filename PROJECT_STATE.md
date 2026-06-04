# Astral — 项目状态摘要

## 版本
v0.9（2026-06-04）— v1.5 审计修复 + 3 致命 bug 修复 + PROTOCOL 全面同步

## 项目路径
`E:\dd\文档们\AI互动小说计划\Astral\`

## 启动方式
双击 `启动.bat` → 浏览器打开 http://127.0.0.1:8640

## 文件结构
```
Astral/
├── server.py              # Flask 入口（34 行，Blueprint 注册）
├── session.py             # GameSession 编排器（~1750 行）
├── state.py               # 核心数据结构（13 dataclass + 3 enum）
├── llm.py                 # 线程安全 LLM 客户端
├── agent_engine.py        # 12 独立 NPC Agent + ActionPlan 引擎
├── arbiter.py             # 仲裁层（冲突消解 + d6 掷骰 + 计划冲突检测）
├── gm.py                  # GM 叙述层（文学性叙事 + 语境化选项）
├── characters.py          # CharacterProfile 类定义
├── card_manager.py        # 角色卡文件管理
├── config_profiles.py     # API 多配置管理（含思考模式）
├── save_manager.py        # 存档管理（自动 + 手动槽位）
├── debug.py               # 日志系统（4 个环形缓冲日志文件）
├── blueprints/            # Flask Blueprint 路由模块（47 API）
│   ├── prologue.py        # 序章 8 端点
│   ├── game.py            # 游戏主循环 9 端点（含 SSE + skip/sleep/ending）
│   ├── trial.py           # 审判 8 端点（含辩论 SSE + 证物 CRUD）
│   ├── save.py            # 存档/Load/新游戏 5 端点
│   ├── settings.py        # API 配置/连接测试/shutdown 6 端点
│   └── meta.py            # 场景/角色卡/状态/元指令 8 端点
├── scenarios/
│   ├── __init__.py        # 场景注册/加载器
│   ├── tianji_maze.py     # 天际迷宫（含 ENDING_CONFIG）
│   ├── cloud_holiday.py   # 云端假期（含 ENDING_CONFIG）
│   └── snow_train.py      # 风雪列车
├── static/
│   ├── index.html         # 单页面 UI（含结局画面 + 投票弹窗 + 证物面板）
│   ├── style.css          # 暗色主题
│   └── app.js             # 客户端逻辑（~1200 行）
├── cards/                 # 角色卡 .txt 文件
├── saves/                 # 存档 JSON
├── logs/                  # debug 日志
├── config_profiles.json   # API 配置（多配置档案）
├── FEATURES.md            # 完整功能清单
├── AGENTS.md              # Agent 分工方案
├── PROTOCOL.md            # 跨 Agent 契约
└── 许愿书.md              # 设计需求 + 重构方案
```

## 核心数据流
```
正常模式：
  Agent.plan() → ActionPlan（3-5步） → _tick() 分钟级推进
  玩家行动 → 仲裁 → GM 叙事 → SSE

审判模式：
  尸体发现 → 审判 ActionPlan → 搜查(限时) → 陈述 → 辩论(SSE) → 投票 → 处刑

结局模式：
  幸存 ≤ N 或 到达某地 → 结局横幅 → 选择分支 → 结局画面
```

## 核心功能数
- 13 个数据类 + 3 个枚举
- 47 个 API 端点
- 3 个场景（含结局配置）
- SSE 事件类型：6 → 新增 ending_triggered
- 12 独立 NPC Agent（支持 ActionPlan 调度）
- 4 个新的 IntentType（审判专用）

## 核心数据流（一轮游戏）
```
玩家点击"推进" → 12 Agent 并发决策(ThreadPoolExecutor 8 workers)
  → 仲裁官(冲突消解 + d6掷骰 + 证据生成 + 旁观者检测)
  → 谋杀检测 + 尸体发现(undiscovered_bodies, 2+目击者触发)
  → NPC 社交记录 + 时间广播事件
  → GM 叙述(400-600字文学叙事 + 4个语境化选项 + NPC性格速写)
  → SSE 流式推送至前端
```

## 完整功能清单
详细版见 [FEATURES.md](FEATURES.md)。

### 引擎层
- 12 独立 NPC Agent，每轮并发决策
- 仲裁官：三阶段权限(BLACKOUT/UNDERCURRENT/HUNTING)
- d6 随机风险判定（不可能→极高→高→中→较低→低→无）
- 三个难度模式（剧情/正常/魔女）
- 好感度系统（0-100，等级名仇恨→恋人）
- 威胁度系统（0-1）
- 物品系统（房间物品状态 + 玩家背包，取走即永久消失）
- 审判系统（搜查→陈述→辩论→论告→投票→处刑）
- 尸体发现机制（undiscovered_bodies，需 2+ 目击者触发）
- 首案延迟（前 6 轮攻击自动降级为对峙）
- NPC 间社交日志自然融入 GM 叙述

### 攻击机制
- ATTACK（直接攻击）：需无人目击，有目击者降级为对峙
- TRAP（陷阱攻击）：不要求无人，风险 = LLM 自评 + 旁观者人数加成
- 毁尸灭迹被拦截，尸体始终存在

### GM 叙述
- 400-600 字文学性叙事 + 感官细节
- 多角色同场时描写对话、神态、小动作
- 未知角色用外貌特征，已知角色用名字
- LLM 每轮生成 4 个语境化选项（A/B/C/D），D 始终是自由行动
- NPC 性格速写注入 GM prompt 实现角色化语感
- 时间广播事件（晚餐广播、灯光变暗等）融入叙事

### 前端
- 场景选择（3 场景卡片）
- 角色卡系统（文件式 + 编辑器，支持 personality）
- API 设置面板（多配置保存/选择/测试，首次启动自动弹出）
- NPC 面板（好感度条+等级标签+情绪+位置+同室绿标）
- 对话系统（建议按钮 + 自由输入）
- 自由输入（任何文字被当作调查/交互指令）
- 调查风险判定（LLM 评估 + d6 掷骰）
- 审判横幅（阶段标签 + 论告输入框代替 prompt()）
- 背包显示（顶栏）
- 新游戏按钮（任何时候点"新游戏"重置，无需重启服务端）
- 加载遮罩（所有操作都有 loading）
- 存档面板（自动存档 + 6 槽位）

### API（37 个端点）
- 序章: mirror / magic / difficulty / camp / explore / admin / finish
- 游戏: round(SSE) / dialogue / dialogue_suggestions / explore / investigate / move_player
- 审判: trial/investigate / trial/proceed / trial/argue / trial/state
- 存档: save / load / slots / new_game
- 场景: scenes / select_scene
- 配置: profiles(GET/POST) / profiles/activate / profiles/delete / test_connection
- 角色卡: cards(GET/POST/DELETE) / start_with_card

## 3 个场景包

| 场景 | GM | 舞台 | 角色 |
|------|----|------|------|
| tianji_maze | 管理员（盔甲） | 3层迷宫 | 露娜/宁宁/可可萝/和奈/爱丽丝/彩香/柔/莉莎/小鸠/香具矢/瑞秋/索拉 |
| cloud_holiday | 经理（电视机头） | 4层酒店 | 同上12人 |
| snow_train | 列车长（广播） | 5节豪华列车 | 艾拉/莉莉安/亚子/艾琳娜/暮夜/夜子/坂那/奈奈/怜奈/铃/千华/美树 |

## 3 个难度模式

| 模式 | 特点 |
|------|------|
| 剧情模式 | 无案件，纯日常探索 |
| 正常模式 | 案件发生，审判举行，推理为王 |
| 魔女模式 | 线索指向玩家，可主动杀戮，全员敌意 |

## 角色卡格式

文件放入 `cards/` 目录：
```
name: 七海 澪
age: 15
appearance: 黑色齐短发，浅色瞳孔
magic: 【残响剪定】——剥离物体属性
personality: 说话轻声细语（可选）
```
也可在游戏内编辑器创建。

## 存档

| 槽位 | 用途 |
|------|------|
| 自动存档 | 退出时自动保存 |
| 槽位 1-6 | 手动存/读 |

## API 配置

配置文件：`config_profiles.json`

支持多配置（DeepSeek / OpenAI / Gemini 等一键切换）。首次启动自动弹出设置面板。所有配置存在 `profiles` 数组中，`active` 标记当前使用的配置。

## Debug

运行后 `logs/` 目录自动生成环形缓冲日志（每文件最多 5000 行）：
- `requests.log` — API 请求耗时
- `agents.log` — Agent 决策记录
- `errors.log` — 全局异常堆栈
- `thread_errors.log` — 线程异常

## 已知已修复问题

本次审计发现并修复了 28 个问题，包括 3 个致命、6 个高影响、7 个中影响、12 个低影响。详见会话记录。主要修复：

| 问题 | 影响 |
|------|------|
| `__init__` 代码误放入 `@staticmethod` → Agent 全部未初始化 | 致命 |
| 尸体发现无限循环（`newly_discovered.append`） | 致命 |
| `CONFIG_PATH` 未定义导致老旧端点崩溃 | 致命 |
| `nearby_names` 永远为空 → NPC 看不到附近有谁 | 高 |
| `apply_loaded_state` 缺失 8 个字段恢复 | 高 |
| 空 `system` 被当作 None → JSON 指令丢失 | 高 |
| 重复 HTML ID 导致设置面板显示错乱 | 高 |
| `#conn-status` 引用不存在元素 | 高 |
| 三个 `WorldState.from_dict(wd)` 调用 | 中 |
| `hasattr` + `getattr` 冗余模式 | 中 |
| `isinstance(method_hint, str)` 死分支 | 低 |
| `'resp' in dir()` 丑陋检测 | 低 |
| `max()` 在字符串集上投票无意义 | 低 |
| `.save-slot.auto` CSS 缺失 | 低 |
