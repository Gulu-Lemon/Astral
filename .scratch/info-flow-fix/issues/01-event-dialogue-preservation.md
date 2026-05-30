# P3-01 — public_events 保留 NPC 对话内容

Status: done

## 问题

`public_events` 是 NPC 感知世界的**唯一窗口**，但 `_apply_rulings()` 创建 Event 时将 `Intent` 的 8 个丰富字段坍缩为一行 `public_description` 摘要。具体：
- `dialogue`（"你就是凶手"）→ ❌ 丢弃
- `prose`（动作描写）→ ❌ 丢弃
- `internal` → ❌ 丢弃
- `reasoning` → ⚠️ 截断 120 字符

导致：NPC A 对 NPC B 说了 "你就是凶手，我在你房间发现了血迹"，NPC B 和旁观 NPC C 只能看到 `"小林优花 在 宴会厅 与 铃木真由子 互动。"`

## 修复方案

在 `Event` 中新增两个可选字段：

```python
@dataclass
class Event:
    # ... 现有字段 ...
    dialogue_snapshot: str = ""       # NPC 对话内容（如有），最多 200 字
    prose_snapshot: str = ""          # 动作描写摘要，最多 150 字
```

`_apply_rulings()` 创建 Event 时：
```python
Event(
    # ... 现有字段 ...
    dialogue_snapshot=(ruling.intent.dialogue or "")[:200],
    prose_snapshot=(ruling.intent.prose or "")[:150],
)
```

`perceive()` 读取时扩展：
```python
visible_events = []
for evt in world.public_events[-8:]:
    if self.agent_id in evt.witnesses or evt.location == loc:
        entry = evt.public_description
        if evt.dialogue_snapshot:
            entry += f" 对话：{evt.dialogue_snapshot}"
        visible_events.append(entry)
```

## 影响文件

- `state.py`：Event dataclass + to_dict/from_dict
- `arbiter.py`：`_apply_rulings()` 中 Event 构造
- `agent_engine.py`：`perceive()` 中 visible_events 构建

## 关联

🔴 P0 优先级。问题三最核心的修复——消除 NPC "互相失聪"。
