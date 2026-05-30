# NPC Agent 信息流修复

## 背景

审计发现 Agent → Arbiter → GM → Agent 管道中存在严重的信息丢失，NPC 之间互相"失聪"，GM 看不到实时情绪，Agent 自评风险被覆盖。

## 核心问题

`public_events` 是 NPC 感知世界的唯一窗口，但 8 个维度的丰富数据在此坍缩为一行摘要，对话内容、动作描写、内心独白全部丢失。

## 目标

- 修复 public_events 信息瓶颈，让 NPC 能看到彼此的对话内容
- 让 GM 能看到 Agent 实时情绪
- 消除死字段和浪费的 LLM token
- 建立 NPC-NPC 对话的 chat_history 通道
