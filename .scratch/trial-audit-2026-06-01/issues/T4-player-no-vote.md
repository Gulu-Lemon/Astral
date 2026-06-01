# Issue T4 — 投票阶段玩家无参与

Status: needs-triage | Priority: P2

## 现象

投票阶段 `_trial_vote()` 完全自动化——每个 NPC 按 `suspicion_map` 投给最高嫌疑者，玩家不能参与投票。玩家只能提交论告，但论告对投票结果没有影响（投票只看 suspicion_map）。

## 根因

`session.py:1243-1254` — `_trial_vote()` 只循环 `self.world.alive_npcs`，不包含 "player"。投票结果完全由 `suspicion_map` 决定，而 `suspicion_map` 在整个游戏中几乎没有被修改过（没有查到增加怀疑值的代码）。

## 修复

两种方向：
1. 允许玩家投票——加权影响最终结果
2. 玩家的论告内容通过 LLM 分析后调整 `suspicion_map`（命中了证据指向者则降低其嫌疑或升高他人嫌疑）

## 影响文件

- `session.py:1243-1254` — _trial_vote
