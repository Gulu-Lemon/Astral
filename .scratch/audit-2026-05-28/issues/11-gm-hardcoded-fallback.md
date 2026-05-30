# 11 — GM 房间特征硬编码回退值

Status: done

## 问题

`gm.py:_generate_narrative_and_options()` 中：
```python
feature_names = [f.get('name', '未知物品') for f in room_features] if room_features else ["周围环境"]
```

`"周围环境"` 是硬编码的中文回退字符串。应作为模块级常量，便于复用和国际化。

## 修复方案

```python
DEFAULT_ROOM_FEATURE = "周围环境"
```

然后在两处使用：
1. `gm.py` 的回退
2. `server.py:_room_features()` 的回退 `"（无记录）"` → 统一使用同一个常量体系

## 影响文件

- `gm.py`：提取常量
- `server.py`：可选，统一回退文本

## 关联

P2 优先级。低风险代码清洁度改进。
