# Issue T2 — 陈述/辩论阶段无 LLM 内容

Status: needs-triage | Priority: P1

## 现象

`trial_proceed()` 在"陈述"和"辩论"阶段只切换 `trial.phase` 标签，不调用 LLM 生成任何证词或辩论对话。玩家推进后只看到 `"陈述阶段：每人依次发言。"` 一行文字，没有角色实际发言。

## 根因

`session.py:1232-1237`：
```python
elif trial.phase == "court_statement":
    trial.phase = "court_debate"
    return {"ok":True, ...}
elif trial.phase == "court_debate":
    trial.phase = "closing"
    return {"ok":True, ...}
```
只有 phase 赋值，无 LLM 调用。原设计可能是让玩家自行想象陈述/辩论内容，但这与游戏叙事驱动的定位不符。

## 修复

陈述阶段：调用 LLM 为每个存活 NPC 生成一句简短陈述。辩论阶段：调用 LLM 生成质询/反驳对话。或在此时回归正常的叙事流（让 `run_round` 继续运作，GM 在审判背景下生成叙事）。

## 影响文件

- `session.py:1222-1241` — trial_proceed
