# Issue 06 — Prompt 臃肿，输入可能超 10K tokens

Status: needs-triage

## 现象

`stream_narrative()` 的 prompt (`gm.py:307-346`) 包含：
- 12 个 NPC 的全量 sketch（每人 5 字段：personality/magic/play_core/habits/appearance）
- 全量关系矩阵（所有好感>65 或 <25 的对）
- 8 个最近事件的 `full_description`（含对话、描写、推理）
- arbiter materials（所有 NPC 动作的 prose/dialogue/reasoning）

合计输入可能轻松超过 15,000 字符（~7,500 tokens），加上 narrative 输出 4,096 tokens，对 16K 上下文窗口的模型已接近边界。

## 修复

在 `session.py` 侧增加输入 token 估算，当 prompt 超过阈值时裁剪 materials 到最近 5 个角色，事件减到 5 个，NPC sketch 只保留同房间的。或由 `stream_narrative()` 内部自适应裁剪。

## 影响文件

- `gm.py:307-346` — prompt 构建
- `session.py:1036` — materials 传入

## 优先级

P2
