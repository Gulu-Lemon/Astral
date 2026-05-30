# P3-05 — 清理死字段和浪费的 token

Status: done

## 决策

| 字段 | 处理 |
|------|------|
| `Intent.internal` | **保留**。存入 `AgentState.private_motives` 作为 NPC 个人记忆。不传 GM/其他 Agent。 |
| `Intent.emotional_state` | **删除**。AgentState 已有，Intent 副本冗余。 |
| `AgentState.witnessed_events` | **填充**。在 `_apply_rulings()` 中写入。 |

## 问题

三个死字段浪费 LLM token 输出和数据结构空间：

| 死字段 | 位置 | 问题 |
|--------|------|------|
| `Intent.internal` | agent_engine.py + arbiter.py | LLM 生成了 "其实她知道对方在撒谎" 的内心独白，但 Arbiter、GM、其他 Agent 都不读取。纯浪费 token。 |
| `Intent.emotional_state` | agent_engine.py | 该字段的值来自 `self.state.emotional_state`（非 LLM 输出），Arbiter 从不读取 Intent 上的这个字段——实际 emotional_state 存在 AgentState 上。 |
| `AgentState.witnessed_events` | state.py:388 | 定义为 `list[str]`，但代码中**从未填充**。 |

## 修复方案

1. **`Intent.internal`：** 两个选择——
   - A) 保留但传递给 GM（让 GM 能写 "她表面微笑，但内心戒备"）
   - B) 删除，节省 ~50 token/Agent/轮 × 12 Agent = 600 token/轮

2. **`Intent.emotional_state`：** 从 Intent dataclass 中删除该字段，只在 AgentState 上维护。

3. **`AgentState.witnessed_events`：** 在 `_apply_rulings()` 中填充，或在 `perceive()` 中填充。如果不需要，直接删除。

## 影响文件

- `agent_engine.py`：`_build_decision_prompt()`, `_parse_intents()`, Intent 构造
- `state.py`：Intent / AgentState dataclass 定义
- `arbiter.py`：`_apply_rulings()`（如保留 witnessed_events）

## 关联

🟡 P2 优先级。性能优化 + 代码清洁度。
