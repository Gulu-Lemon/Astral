# Issue T3 — 论告阶段的进退顺序提示缺失

Status: needs-triage | Priority: P1

## 现象

`closing` 阶段时，玩家直接点"推进审判" → `trial_proceed()` 报错 `"请先进行论告"`。但 UI 没有任何提示告知玩家必须先提交论告才能推进。

## 根因

`session.py:1238-1240`：
```python
if not trial.player_has_argued:
    return {"ok":False,"error":"请先进行论告","phase":trial.phase}
```
`/api/trial/argue` 和 `trial_proceed` 是两个独立操作，UI 不提示先后顺序。

## 修复

进入 `closing` 阶段时，客户端应自动展示论告输入区域（类似自定义行动对话框），提交后 `trial_proceed` 按钮自动激活。或至少 `trial_proceed` 返回错误时弹出更明显的 UI 提示。

## 影响文件

- `static/app.js:725-729` — trialProceed
- `session.py:1238-1240` — closing 守卫
