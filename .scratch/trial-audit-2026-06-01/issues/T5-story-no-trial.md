# Issue T5 — STORY 模式无审判

Status: needs-triage | Priority: P2

## 现象

选择 STORY 难度时，即使发生命案也不触发审判。

## 根因

`session.py:968`：
```python
if self.world.difficulty in (DifficultyMode.NORMAL, DifficultyMode.WITCH):
    self.world.active_trial = TrialState(...)
```
STORY 模式被明确排除。这是设计意图——STORY 模式作为纯叙事体验不需要审判机制。

## 建议

保持现状。在难度选择时向玩家说明 STORY 模式不会触发审判。

## 影响文件

不需修改
