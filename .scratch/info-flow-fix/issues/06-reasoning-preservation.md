# P3-06 — reasoning 不再截断 + public_description 结构化

Status: done

## 问题

`_build_ruling_description()`（arbiter.py L280-336）将 prose + reasoning 拼接为单行 summary，其中 reasoning 被截断到 120 字符。

结果：其他 Agent 通过 `perceive()` 只能看到 "动机：她想了解对方的真实身份，试探性..."（末尾截断）。

## 修复方案

Event.public_description 保持截断（给人类看的摘要），但新增完整字段供 Agent 感知：

```python
@dataclass
class Event:
    public_description: str = ""       # 人类可读摘要（保持现有逻辑）
    full_reasoning: str = ""           # 完整动机（新增，Agent 感知用）
    prose_snapshot: str = ""           # 动作描写（与 #01 的字段合并）
    dialogue_snapshot: str = ""        # 对话内容（与 #01 的字段合并）
```

`perceive()` 构建 visible_events 时使用完整字段而非仅摘要。

## 影响文件

- `state.py`：Event dataclass
- `arbiter.py`：`_build_ruling_description()`, `_apply_rulings()`
- `agent_engine.py`：`perceive()`

## 关联

🟡 P2 优先级。与 #01 配合，共同修复 Agent 感知的信息完整性。
