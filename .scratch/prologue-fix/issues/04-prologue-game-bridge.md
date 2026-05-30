# P1-04 — 序章→正文桥接增强

Status: done

## 实现

修正了原始方案的三个问题：

1. **NPC 见面判断**：不再扫描名字，改为 LLM 判断玩家是否真正与之互动（自我介绍/直接对话/选择指向）。听到名字但未对上号不算认识。
2. **好感初始化**：复用与 `_evaluate_affection` 相同的 LLM 评估逻辑（性格+场景→delta→clamp），而非重新发明。
3. **NPC-NPC 对话**：LLM 从序章原文提取（禁止编造），写入双方 chat_history。

新增：NPC 在序章中形成的初步动机 → `AgentState.private_motives`。

## 问题

`prologue_finish()` 将整个序章压缩为一条 200-300 字的 LLM 摘要，写入 `world.last_narrative_summary`。**所有其他信息丢失：**
- 哪些 NPC 被玩家认识了（`player_met_npcs` 仅从消息中扫描真名，不完整）
- 序章中形成的初印象和关系
- 具体发生过的事件

正文开始时 NPC 全为陌生人，`chat_history` 为空。

## 修复方案

在 `prologue_finish()` 中额外提取结构化信息：

1. **NPC 见面记录：** 扫描序章消息中所有出现的 NPC 角色名和编号 → 填入 `world.player_met_npcs`
2. **初印象快照：** 为每个见过的 NPC 生成一条 `_chat_history` 记录，描述初遇印象
3. **关系初始化：** 根据序章互动密度，给见过的 NPC 设置 `affection_map["player"]` 初始偏移（如多次互动+10，未互动保持50）

```python
def prologue_finish(self):
    # ... 现有 summary 生成 ...
    # 新增：提取结构化桥接数据
    self._bridge_player_met_npcs()      # 扫描名字 → met_npcs
    self._bridge_initial_impressions()  # 生成初印象 → chat_history seeds
    self._bridge_affection_seeds()      # 设置初始好感偏移
```

## 影响文件

- `server.py`：`prologue_finish()` + 新增 `_bridge_*` 方法
- `agent_engine.py`：可能需要在 Agent 初始化时接收 seed chat_history

## 关联

P1 优先级。解决序章→正文的体验断裂。
