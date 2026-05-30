# 10 — llm.chat() system 参数语义不一致

Status: done

## 问题

`llm.py` 的 `chat()` 方法：
```python
if system is not None:
    full_messages.append({"role": "system", "content": system})
```

`system=""` 会添加空的 system 消息（语义差异），而 `system=None` 则跳过。当前无调用方传入空字符串，但类型签名暗示 `Optional[str]`，容易被误用。

## 修复方案

```python
if system:
    full_messages.append({"role": "system", "content": system})
```

将 `is not None` 改为 truthiness 检查。空字符串和 None 统一行为。

## 影响文件

- `llm.py`：`chat()` 方法

## 关联

P2 优先级。低风险防御性修复。
