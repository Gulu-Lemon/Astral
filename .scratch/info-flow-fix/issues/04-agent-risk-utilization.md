# P3-04 — 让 Agent 自评 risk 生效（或删除该字段）

Status: done

## 决策

采用方案 A：`final_risk = max(assess_risk, llm_risk)` — Arbiter 可上调风险不可下调。

## 问题

Agent 在 `decide()` 中生成 `Intent.risk`（LLM 对自己行动风险的自评），但 Arbiter 仅对 TRAP 类型读取该字段，其他所有类型（ATTACK/SABOTAGE/STALK/CONFRONT 等）的 LLM 风险自评被 `_assess_risk()` 完全覆盖。

这意味着 LLM 的 "我觉得这个行动很危险" 的信号被丢弃了。

## 修复方案

**方案 A（推荐）：** 让 Arbiter 在评估风险时参考 Agent 自评，而非完全覆盖。公式：`final_risk = max(assess_risk(intent_type, target), llm_risk)` —— Arbiter 可以上调风险但不能下调。

**方案 B：** 从 Intent 和 Agent prompt 中删除 `risk` 字段，减少 LLM token 浪费。Agent 不需要自评风险，全由 Arbiter 统一判定。

## 影响文件

- `arbiter.py`：`_assess_risk()` 方法
- `agent_engine.py`：`_build_decision_prompt()` 和 Intent 解析（如选方案 B）

## 关联

🟠 P1 优先级。选择方案 A 或 B。
