# 12 — save_manager.apply_loaded_state 冗余重建

Status: done

## 问题

`save_manager.py:102-104`：
```python
ws = WorldState.from_dict(wd)
world.public_events = ws.public_events
world.phase = ws.phase
world.difficulty = ws.difficulty
```

为仅提取 3 个字段（`public_events`, `phase`, `difficulty`）而调用 `WorldState.from_dict(wd)`，触发完整 `Event.from_dict` 重建链（O(n) 开销）。其他字段已经在 L97-123 中逐一手动设置。

## 修复方案

直接解析需要的字段，去掉中间的 `from_dict` 调用：

```python
world.public_events = [Event.from_dict(e) for e in wd.get("public_events", [])]
world.phase = GamePhase(wd.get("phase", "blackout"))
world.difficulty = DifficultyMode(wd.get("difficulty", "normal"))
```

并删除 L102-104。

## 影响文件

- `save_manager.py`：`apply_loaded_state` 方法

## 关联

P2 优先级。非破坏性优化。
