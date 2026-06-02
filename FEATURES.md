# Astral — 当前所有已实现功能

## 核心引擎

- **`state.py`**：13 个数据类（WorldState / AgentState / Intent / Ruling / Event / Evidence / TrialState / ActionStep / ActionPlan / EvidenceItem / EndingBranch / EndingConfig / AffectionEntry / BodyRecord）和 3 个枚举（GamePhase / DifficultyMode / IntentType 含 SEARCH 等新类型），全部带完整的 to_dict / from_dict 序列化
- **`llm.py`**：LLMClient，线程安全的 httpx 连接池，chat() / chat_json() / chat_stream() 流式方法，从 LLM 响应中提取 JSON（支持 markdown 去除、多种回退解析）
- **`agent_engine.py`**：NPCAgent 类，含 perceive / decide / plan / ensure_plan / dialogue / update_affection / update_threat；ActionPlan 调度引擎；Player→No.13 身份抹除翻译；Perception 快照数据类
- **`arbiter.py`**：Arbiter 类，process_round → detect_conflicts → rule_on_intent → apply_rulings 管线；计划冲突检测（detect_plan_conflicts）；基于阶段的权限控制；目击者检测；风险评估骰子系统；好感度/威胁度裁定修改
- **`gm.py`**：GMNarrator，synthesize_round → build_context → generate_narrative_and_options → stream_narrative；基于位置/目击者的 NPC 可见性规则；_npc_label() 角色感知标注

## 时间系统

- **分钟级时间**：WorldState.time_minutes，_tick() 逐分钟推进，_time_string() 格式化显示
- **ActionPlan 调度**：NPC 生成 3-5 步行动计划，按 duration 逐分钟执行，支持被打断重计划
- **Skip/Sleep**：玩家可跳过时间/睡觉，后台 Agent 继续跑
- **审判计时**：搜查/辩论阶段 60 分钟倒计时

## 审判系统（重构后）

- **搜查阶段**：限时 60 分钟，NPC 自由调查，玩家调查/添加证物（LLM 校验）
- **证物系统**：EvidenceItem CRUD，LLM 模型校验物品可获取性，右侧栏面板
- **陈述阶段**：LLM 生成 NPC 开场陈述，玩家可选补充
- **辩论阶段**：SSE 流式叙事，4 个选项（质疑/出示证物/推理/静观），手动共识→可选投票
- **投票**：NPC 嫌疑度计算 + 玩家手动投票，前端投票弹窗
- **处刑阶段**：LLM 叙事生成，云端假期全员抹杀规则

## 结局系统

- **EndingConfig**：场景级结局配置（触发类型/条件/分支）
- **多分支结局**：天际迷宫 2 分支（到达引航台）、云端假期 4+1 分支（幸存 ≤5）
- **自动结局**：玩家死亡立即触发死亡画面
- **SSE 推送 + 前端结局画面**

## API（47 个端点）

- **序章**：`/api/prologue/mirror`、`/magic`、`/difficulty`、`/camp`、`/continue`、`/finish`
- **游戏**：`/api/round`（SSE）、`/api/dialogue`、`/api/dialogue_suggestions`、`/api/explore`、`/api/investigate`、`/api/move_player`
- **时间**：`/api/skip_time`、`/api/sleep`
- **结局**：`/api/ending/choose`
- **审判**：`/api/trial/investigate`、`/trial/proceed`、`/trial/argue`、`/trial/state`、`/trial/debate_stream`（SSE）、`/trial/debate_option`、`/trial/evidence`、`/trial/evidence/add`
- **存档**：`/api/save/...`、`/api/load/...`、`/api/slots`、`/api/new_game`、`/api/select_scene`
- **配置**：`/api/profiles`（GET/POST）、`/api/profiles/activate`、`/api/profiles/delete`、`/api/test_connection`
- **角色卡**：`/api/cards`（GET/POST/DELETE）、`/api/start_with_card`
- **其他**：`/api/scenes`、`/api/state`、`/api/meta`、`/api/free_narrative`、`/api/shutdown`、静态文件 `/`

## NPC 感知平等

- Prompt 中 player → No.13 翻译层
- NPC 无法从编号/名称区分玩家和其他 NPC
- GM 叙事中 _npc_label 正确处理玩家

## 剧情模式

- ATTACK/TRAP/SABOTAGE 降级为 CONFRONT
- 审判不触发（NORMAL/WITCH 守卫）
- 无命案设计

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
