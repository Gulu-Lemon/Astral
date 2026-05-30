# Astral — 当前所有已实现功能

## 核心引擎

- **`state.py`**：6 个数据类（WorldState / AgentState / Intent / Ruling / Event / Evidence / TrialState）和 3 个枚举（GamePhase / DifficultyMode / IntentType），全部带完整的 `to_dict` / `from_dict` 序列化
- **`llm.py`**：LLMClient，线程安全的 httpx 连接池，`chat()` 和 `chat_json()` 方法，从 LLM 响应中提取 JSON（支持 markdown 去除、多种回退解析）
- **`agent_engine.py`**：NPCAgent 类，含 perceive / decide / dialogue / update_affection / update_threat；基于阶段的意图系统 `_allowed_intents()`；Perception 快照数据类；`_parse_intent_type()` 字符串→枚举映射
- **`arbiter.py`**：Arbiter 类，process_round → detect_conflicts → rule_on_intent → apply_rulings 管线；基于阶段的攻击/陷阱/破坏行为权限控制；目击者检测；LLM 证据生成；风险评估骰子系统；好感度/威胁度裁定修改
- **`gm.py`**：GMNarrator，synthesize_round → build_context → generate_narrative_and_options → parse_options / strip_options；基于位置/目击者的 NPC 可见性规则；`_npc_label()` 角色感知标注
- **`server.py`**：GameSession 编排器；6 步序章流程（镜子→魔法→难度→营地→探索→管理员）；run_round 带 ThreadPoolExecutor agent 并行 + SSE 流式推送；谋杀检测、尸体发现（2+ 目击者触发）、审判自动启动；trial_investigate / trial_proceed / _trial_vote / _trial_execution；NPC 对话建议；check_floor_unlock / check_phase_transition / advance_time / broadcast_event；/api/meta 元指令；/api/free_narrative 自由叙述

## 服务端 API（39 个端点）

- **序章**：`/api/prologue/mirror`、`/magic`、`/difficulty`、`/camp`、`/explore`、`/admin`、`/finish`
- **游戏**：`/api/round`（SSE）、`/api/dialogue`、`/api/dialogue_suggestions`、`/api/explore`、`/api/investigate`、`/api/move_player`
- **自由与指令**：`/api/free_narrative`（自由行动叙述）、`/api/meta`（元指令：检查角色/位置/时间）
- **审判**：`/api/trial/investigate`、`/trial/proceed`、`/trial/argue`、`/trial/state`
- **存档**：`/api/save/<slot>`、`/api/load/<slot>`、`/api/slots`、`/api/new_game`、`/api/select_scene`
- **配置**：`/api/profiles`（GET/POST）、`/api/profiles/activate`、`/api/profiles/delete`、`/api/test_connection`
- **角色卡**：`/api/cards`（GET/POST/DELETE）、`/api/start_with_card`
- **其他**：`/api/scenes`、`/api/state`、静态文件 `/`

## 场景系统

- **`scenarios/__init__.py`**：场景注册系统（add_module / list_scenarios / get / load），支持动态导入
- **3 个内置场景**：tianji_maze（天际迷宫）、cloud_holiday（云端假期）、snow_train（风雪列车）

## 角色与角色卡

- **`characters.py`**：CharacterProfile 数据类 + build_system_prompt()；register_character() 注册；12 名完整 NPC（性格/魔法/秘密/魔女动机）
- **`card_manager.py`**：parse_card / format_card / list_cards / get_card / save_card / delete_card — 基于文件的角色卡持久化（`cards/` 目录）

## 前端

- **`index.html`**：序章画面、场景选择、角色卡选择、NPC 侧栏面板、叙事区、对话框、审判横幅、存档面板、设置面板、角色卡编辑器、加载遮罩
- **`app.js`**（732 行）：序章步骤推进、SSE 回合流、NPC 渲染（好感度条/情绪标签）、对话系统（含建议选项）、审判流程（搜查→陈述→辩论→论告→投票→处刑）、存档/读档 UI、API 设置/配置管理、角色卡编辑器、场景选择、元指令检测、自由行动叙述、组合选项链、调试面板
- **`style.css`**：暗色主题 CSS 变量、NPC 卡片动画、审判横幅、操作栏、模态框、加载动画

## 工具模块

- **`debug.py`**：RingBuffer 文件日志器、RequestLogger（Flask 中间件）、ExceptionCatcher（全局异常 + 线程钩子）、AgentLogger（决策/叙事/仲裁日志）
- **`config_profiles.py`**：多配置 API 管理（`config_profiles.json`）
- **`save_manager.py`**：自动存档 + 6 个手动槽位、apply_loaded_state 存档恢复
