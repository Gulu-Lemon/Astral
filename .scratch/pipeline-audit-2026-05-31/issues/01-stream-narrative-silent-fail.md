# Issue 01 — `stream_narrative()` 静默吞异常

Status: resolved (v2.6)

## 现象

LLM `chat_stream()` 失败时（认证失败、网络中断、模型不支持 streaming），管道不报任何错误，继续推进到 `generate_options()`，生成一个空叙事的选项。

## 根因

`gm.py:358-359`：

```python
except Exception:
    yield "\n"
```

任何异常被 silent catch，yield 一个换行符。调用方 `session.py:1037-1039` 收到 chunk `"\n"`，累积为 `full_text = "\n"`，然后正常调用 `generate_options("\n", ...)`。

## 修复

不应静默吞异常。两种方案：

- **方案 A**：raise 异常，让 `session.py` 的 try/except 捕获并报告
- **方案 B**：yield 一个特殊标记，并在 `session.py` 的循环中检测异常

选择：方案 A（更简单）：

```python
except Exception as e:
    raise RuntimeError(f"流式叙事生成失败: {e}") from e
```

## 影响文件

- `gm.py:358-359`

## 优先级

P0
