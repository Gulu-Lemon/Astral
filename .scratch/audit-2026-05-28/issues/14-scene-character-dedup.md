# 14 — 场景角色去重（tianji_maze / cloud_holiday）

Status: done

## 实际修复

- `scenarios/shared_characters.py`：新建，导出 `_cp` 工厂 + `MAZE_HOLIDAY_CHARACTERS`（12 个共享角色，来自设计文档 v1.3 验证）
- `scenarios/tianji_maze.py`：`CHARACTERS = dict(MAZE_HOLIDAY_CHARACTERS)`
- `scenarios/cloud_holiday.py`：`CHARACTERS = dict(MAZE_HOLIDAY_CHARACTERS)`
- 两个场景现在共享同一份角色数据，修改一处自动同步。

## 问题

`tianji_maze.py` 和 `cloud_holiday.py` 包含**完全相同的 12 个 CHARACTERS 定义**（名字、属性、秘密、魔女动机完全一致，仅 `_cp` 方法签名略有差异）。

这是维护分叉——任何角色改动需要同步修改两处，极易遗漏。

## 建议方案

方案 A（推荐）：提取共享角色库到 `scenarios/shared_characters.py`：
```python
# scenarios/shared_characters.py
MAZE_HOLIDAY_CHARACTERS = { ... }  # 12 个 CharacterProfile
```

方案 B：`cloud_holiday` 直接 import `tianji_maze.CHARACTERS`

## 关联

P4 优先级。低优先级，不影响功能。但每次改角色时省掉一次手动同步的麻烦。
