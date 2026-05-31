# Issue 07 — GM 叙事将所有 NPC 行动平铺直叙

Status: resolved (v2.6)

## 现象

正文叙述把所有 NPC 的行动逐条罗列，像清单而非文学叙事。此前项目曾解决此问题，v2.5 流式拆分后复发。

## 根因

v2.5 新增的 `stream_narrative()` 构建了独立的 prompt（`gm.py:228-280`），这个 prompt 是直接新写的，**未沿用**原 `_generate_narrative_and_options()` 中经过多轮调试优化的 prompt（`gm.py:150-202`）。

关键差异：原 prompt 有明确的导演指令——"决定互动的发生顺序和空间位置"、"突出 2-3 组关键互动，其余一笔带过"、"[可略写]的素材可合并为一句话带过"。而新 `stream_narrative()` prompt 中这些指令的措辞和位置不同，LLM 未能同等理解。

## 修复

将 `stream_narrative()` 的 prompt 与 `_generate_narrative_and_options()` 的 prompt 完全对齐，确保：
- "突出 2-3 组关键互动，其余一笔带过"
- "[可略写]素材合并为一句话"
- 导演角色的明确性

两个 prompt 应共享同一段核心指令文本，避免未来再次分叉。

## 影响文件

- `gm.py:228-280` — `stream_narrative()` 的 prompt
- `gm.py:64-202` — 原 `_generate_narrative_and_options()` 的 prompt（作为参照）

## 优先级

P0 — GM 叙事质量退化
