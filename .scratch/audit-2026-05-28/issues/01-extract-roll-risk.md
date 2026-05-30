# 01 — 提取 `_roll_risk` 到共享模块

Status: done

## 问题

`_roll_risk()` 函数在 **两处** 重复实现：
- `arbiter.py:230-242`（Arbiter 类中使用）
- `server.py:43-46`（`api_investigate` 中使用）

PROTOCOL.md §5 已标记同步警告，但未修复。任何一方修改风险阈值会导致行为不一致。

## 修复方案

将 `_roll_risk` 提取到 `state.py` 或新建 `utils.py`，两处改为 import 调用。

```python
# state.py 新增
RISK_THRESHOLDS = {
    "不可能": [],
    "极高风险": [0],
    "高风险": [0, 1],
    "中风险": [0, 1, 2],
    "较低风险": [0, 1, 2, 3],
    "低风险": [0, 1, 2, 3, 4],
    "无风险": [0, 1, 2, 3, 4, 5],
}

def roll_risk(risk: str, rng=None) -> bool:
    """d6 随机掷骰。返回 True 表示成功。"""
    roll = (rng or random).randint(0, 5)
    return roll in RISK_THRESHOLDS.get(risk, [0, 1, 2])
```

## 影响文件

- `state.py`：新增 `RISK_THRESHOLDS` + `roll_risk()`
- `arbiter.py`：`_roll_risk()` → `from state import roll_risk`，调用改为 `roll_risk(risk, self._rng)`
- `server.py`：`_roll_risk()` → `from state import roll_risk`
- `PROTOCOL.md` §5：移除"同步警告"标记

## 关联

P0 优先级。修复后消除已知重复 bug 源。
