# Issue 03 — `stream_narrative()` 缺少 `player_action` 上下文

Status: resolved (v2.6)

## 现象

GM 生成的叙事不知道玩家本轮做了什么，缺乏聚焦点。

## 根因

`gm.py:225` 的 `stream_narrative()` 签名不包含 `player_action` 参数。原 `_generate_narrative_and_options()` 在 prompt 中包含：

```
【玩家行动】{player_action if player_action else '观察周围'}
```

（行 169）

拆分后，`stream_narrative()` prompt 中缺失此字段。GM 只能看到 NPC 的动作素材，不知道叙事应该围绕什么展开。

## 修复

给 `stream_narrative()` 添加可选 `player_action=""` 参数，并在 prompt 中恢复 `【玩家行动】` 行。调用处 `session.py:1037` 传入 `player_action`（可通过 `run_round()` 自行追踪，或先传空字符串）。

## 影响文件

- `gm.py:225` — 方法签名 + prompt
- `session.py:1037` — 调用处传参

## 优先级

P1
