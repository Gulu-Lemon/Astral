# Issue 05 — `generate_options` 截断叙事为末尾 3000 字符

Status: needs-triage

## 现象

生成的选项可能与叙事开头的事件/对话脱节，因为 LLM 看不到全文。

## 根因

`gm.py:435`：
```python
{narrative_text[-3000:]}
```

较长的叙事（>3000 字符）的前半部分被切除。选项 LLM 只知道故事怎么结束的，不知道从哪里开始的。

## 修复

将截断长度提升到 5000 字符，或使用 `narrative_text[:2000] + "\n...\n" + narrative_text[-3000:]` 同时保留开头和结尾。也可以将 narrative_text 不做截断，靠 `max_tokens=512` 限制输出而非限制输入。

## 影响文件

- `gm.py:435`

## 优先级

P2
