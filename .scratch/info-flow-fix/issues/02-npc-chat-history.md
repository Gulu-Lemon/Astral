# P3-02 — 建立 NPC-NPC chat_history 通道

Status: done

## 问题

`_chat_history` 只在 `api_dialogue()`（玩家-NPC）时写入。NPC 之间的对话从未写入任何 Agent 的 chat_history。

导致：NPC A 上轮对 NPC B 说 "我觉得你有秘密"，下轮 NPC B 的 `recent_dialogue` 完全不知道这段对话发生过。

## 修复方案

在 `_apply_rulings()` 或 `run_round()` 中，裁决完成后，对成功的 SOCIALIZE/CONFRONT/ATTACK 意图：

```python
# 写入双方 chat_history
if ruling.success and ruling.intent.dialogue:
    dialogue_entry = {
        "speaker": ruling.intent.agent_id,
        "listener": ruling.intent.target_id,
        "content": ruling.intent.dialogue[:200],
        "tick": world.global_tick,
    }
    # 写入选定者的 chat_history
    actor_agent = self.agents.get(ruling.intent.agent_id)
    if actor_agent:
        actor_agent._chat_history.append(dialogue_entry)
    # 写入目标的 chat_history
    if ruling.intent.target_id and ruling.intent.target_id in self.agents:
        self.agents[ruling.intent.target_id]._chat_history.append(dialogue_entry)
```

限制 `_chat_history` 最多保留 10 条，避免无限增长。

## 影响文件

- `arbiter.py`：`_apply_rulings()` 或新增 `_populate_chat_history()`
- `agent_engine.py`：可能需要 chat_history 上限逻辑

## 关联

🔴 P0 优先级。与 #01 配套——Event 让 NPC "听到"别人做了什么，chat_history 让 NPC "记住"别人说了什么。
