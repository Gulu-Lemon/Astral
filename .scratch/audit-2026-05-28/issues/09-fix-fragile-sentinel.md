# 09 — 替换脆弱哨兵对象

Status: done

## 问题

`arbiter.py:96` 使用临时创建的匿名类作为哨兵：
```python
agent_states.get(aid, type('',(),{'alive':False})())
```

如果任何代码访问 `.alive` 之外的属性，会引发 `AttributeError`。虽然当前只有一个属性，但脆弱。

## 修复方案

在 `state.py` 顶部定义命名元组哨兵：
```python
from collections import namedtuple
DeadSentinel = namedtuple('DeadSentinel', ['alive'])
DEAD_NPC = DeadSentinel(alive=False)
```

然后替换所有 `type('',(),{'alive':False})()` 为 `DEAD_NPC`。

## 影响文件

- `state.py`：新增 `DEAD_NPC`
- `arbiter.py`：L96 替换
- `server.py`：搜索同模式并替换（约 3-4 处）

## 关联

P2 优先级。低风险防御性修复。
