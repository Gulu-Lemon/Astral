# Issue 02 — `stream_narrative()` temperature=1.0 过高

Status: needs-triage

## 现象

叙事"超长流水账"问题经多次 prompt 调优后仍复发。LLM 难以稳定遵循"不要按人逐条叙述""选取2-3组关键互动"等结构性指令。

## 根因

`gm.py:355`：`temperature=1.0` — OpenAI 兼容 API 的最大熵值。在此温度下 LLM 输出高度随机，对格式/结构类指令的遵循度显著降低。原 `_generate_narrative_and_options` 也使用 1.0，但那是 JSON 输出模式（强结构约束），而纯文本流式缺乏同等约束力。

对比：`generate_options()` 使用 `temperature=0.7`，该调用表现正常。

## 修复

将 `stream_narrative()` 的 temperature 从 1.0 降为 0.7 或 0.8：
```python
temperature=0.8, max_tokens=4096,
```

## 影响文件

- `gm.py:355`

## 优先级

P0
