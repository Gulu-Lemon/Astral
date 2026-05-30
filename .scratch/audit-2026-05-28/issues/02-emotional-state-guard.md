# 02 — emotional_state 空字符串静默覆盖

Status: done

## 问题

`agent_engine.py:113`：
```python
self.state.emotional_state = result.get("e", result.get("emotional_state", self.state.emotional_state))
```

如果 LLM 返回 `{"e": ""}` 或 `{"emotional_state": ""}`，空字符串会**静默覆盖**当前 emotional_state，导致 NPC 丢失情绪状态。

## 修复方案

增加非空校验：

```python
new_emotion = result.get("e") or result.get("emotional_state") or ""
if new_emotion.strip():
    self.state.emotional_state = new_emotion
```

## 影响文件

- `agent_engine.py`：仅 L113 修改

## 关联

P1 优先级。防止 NPC 情绪状态静默丢失。
