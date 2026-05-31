# 序章三问题 — 回退选项固化 + 规则不显示 + 推演失败

Status: resolved (v2.1–v2.3)

## 问题 1：Free 阶段选项始终是 4 个回退值 ✅ v2.2

**现象**：序章每轮的选项始终是同一个固定列表：
> A.与附近的人交谈  B.仔细观察周围环境  C.静静等待事态发展  D.查看周围人的反应

**根因**：LLM 生成文本中的选项格式与 `_parse_prologue_options()` 的解析器不匹配，解析失败 → `options` 为空 → 输出回退值。

```
LLM 输出: ...（叙述文本）... 
          A. 走向银发少女和她搭话
          B. 观察拿记事本的少女在记录什么

_parse_prologue_options() 查找 【选项】 标记 → 未找到 → 返回 []
                                                      ↓
                                           fallback 选项列表
```

**可能原因**：
1. 当前 prompt 中约束文本过多（场景上下文 + 禁止约束 + NPC 档案），max_tokens=1024 被 LLM 优先用于写叙述，选项部分被截断。
2. `_pgm()` → `GM_SYSTEM_PROMPT` 中没有要求输出 `【选项】` 格式。所有场景的 GM_SYSTEM_PROMPT 都只约束"叙述风格"，从不提选项输出格式。
3. LLM 输出选项但不含 `【选项】` 标记行，导致 `_parse_prologue_options()` 搜索失败。

**影响文件**：`session.py` `_pgm()` / `_parse_prologue_options()` / 各场景 `GM_SYSTEM_PROMPT`

---

## 问题 2：风雪列车列车长广播后规则未显示 ✅ v2.1

**现象**：admin 阶段结束后，应该在叙述区显示 rule_text（安全守则），但前端不显示。

**根因**：后端 `_prologue_continue()` 在 admin→grouping 转换时返回了 `"rule": rule`：
```python
# session.py:503 — 后端正确返回了 rule
return {"text": narrative, "options": options, "step": self.world.prologue_step, "rule": rule}
```
但前端 `app.js:prologueFromOption()` 只处理 `d.text` 和 `d.options`，**从不检查 `d.rule`**：
```javascript
// app.js:prologueFromOption
addPrologueText(d.text);
if(d.options&&d.options.length>0){showPrologueOptions(d.options)}
// d.rule — 从未被读取！
```
`addRuleText()` 辅助函数存在（`app.js:395-399`）但从未被调用。

**影响文件**：`app.js` `prologueFromOption()` + `prologueContinue()`

---

## 问题 3：序章结束后正文显示"推演失败，请重试" ✅ v2.3

**现象**：`prologue_finish()` → `nextRound()` → SSE `error` 事件 → "推演失败，请重试。"

**根因**：`run_round()` 内部某处抛出未被捕获的异常。序章 bridge 结束后首轮 `run_round()` 包括：

```
1. _settle_player_affection()  ← _pending_player_dialogues 为空，立即返回 ✓
2. _advance_time()              ← 时间推进 ✓
3. ThreadPoolExecutor agent.decide()
   └→ _build_decision_prompt()
      └→ recent_dialogue 处理中 d.get('speaker', d.get('role', '?'))
         _chat_history 存在 dict (speaker:"系统") 和 str ("玩家：你好") 混存
         _seed_chat_history 写入 {"tick": 0} 整数，其他字段是字符串
4. arbiter.process_round()
5. gm.synthesize_round()         ← 调用 llm.chat()
```

**可能原因**（按概率排序）：

A. **`_is_leave_attempt()` 被调用时的连锁崩溃** — 在 `prologue_continue()` 第 393 行，free 阶段每轮都调用 LLM 判定离开意图。如果 LLM 失败 → 异常 → `prologue_continue` 返回错误 → 前端可能继续但状态已脏 → `run_round()` 用脏状态启动 → crash。

具体链：`_is_leave_attempt` 失败 → `prologue_continue` 抛异常 → Flask 返回 500 → 前端 `d.error` 显示错误但 `prologue_step` 可能已被修改 → 后续 `prologue_finish` 调用 → `run_round` 时的 `self.world` 不一致。

B. **`_chat_history` 类型混存** — `_seed_chat_history` 写入 `{"speaker":"系统", "listener":..., "content":..., "tick":0}`。但 `_build_decision_prompt` 中 `dia_parts` 遍历最近 3 条，取 `d.get('content', d.get('text',''))` 再 `str()` 包装。如果 `{"content": None}` → `str(None)` = `"None"` 不会 crash。但如果 _chat_history 中存在意外的数据类型（非 dict 非 str），`isinstance` 检查不匹配 → 跳过 → dia_parts 为空 → 不 crash。

C. **场景数据不一致** — `_init_agents()` 使用 `self.scenario.get("characters", {})`，但 `select_scene` 后 `_init_agents()` 在 `__init__` 中执行 → 应该正确。

D. **LLM API 调用超时** — `agent.decide()` 调用 LLM，如果超时或返回 malformed JSON，`chat_json()` 的 `_extract_json()` 有回退逻辑，但极端情况可能返回 None → `Intent` 构造 crash。

**影响文件**：`session.py` `run_round()` / `prologue_continue()` / `_is_leave_attempt()`；`agent_engine.py` `_build_decision_prompt()`

---

## 修复计划

### 问题 1：选项解析失败

**A. 强化 `_pgm()` 输出约束**：在 GM_SYSTEM_PROMPT 中增加选项格式强制要求。

**B. 放宽 `_parse_prologue_options()`**：容忍 LLM 不输出 `【选项】` 标记行的情况，直接从文本中搜索 `A./B./C./D.` 模式。

**C. 增加 max_tokens**：free 阶段从 1024 提升到 1536，确保选项不被截断。

### 问题 2：规则显示

在 `app.js:prologueFromOption()` 和 `prologueContinue()` 的响应处理中增加规则显示：
```javascript
if(d.rule){addRuleText(d.rule)}
```

### 问题 3：推演失败

**第一步诊断**：在 `run_round()` 中增加 try/except 包裹每个步骤，捕获具体异常信息写入日志。当前只有一个大 try/except 在 SSE worker 层（`"type":"error","message":str(e)`），无法定位。

**A. 防御 `_is_leave_attempt()` 的副作用**：将 `_is_leave_attempt()` 调用包装 try/except，LLM 失败时不抛异常而是默认返回 False（当作不离开）。

**B. 检查 `run_round()` 各步骤的返回值**：确认 `agent.decide()` 返回的 Intent 列表不为 None。

## 影响文件

| 文件 | 改动 |
|------|------|
| `session.py` | `_parse_prologue_options()` 放宽匹配 + free 阶段 max_tokens 提升 + `_is_leave_attempt()` try/except |
| `app.js` | `prologueFromOption()` / `prologueContinue()` 增加 `d.rule` → `addRuleText()` 调用 |
| 各场景 `GM_SYSTEM_PROMPT` | 增加选项格式强制要求 |

## 关联

P0 优先级。三个问题分别影响序章交互可用性、关键信息展示、和游戏正式阶段的启动。
