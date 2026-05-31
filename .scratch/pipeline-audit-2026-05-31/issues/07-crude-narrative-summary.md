# Issue 07 — `last_narrative_summary` 粗糙截取

Status: needs-triage

## 现象

下轮 prompt 中的"上回提要"只是本轮叙事文本的前 800 字符，不是真正的摘要。可能截到不相关的描写而非核心剧情。

## 根因

`session.py:1045`：
```python
self.world.last_narrative_summary = full_text[:800] if full_text else ""
```

## 修复

使用一个极小成本的 LLM 调用（~100 tokens 输出）生成真正摘要，在每轮结束后异步调用。或使用启发式截取：先找叙事文本中是否有"突然""就在这时"等转折词，从那里开始取。

## 影响文件

- `session.py:1045`

## 优先级

P2
