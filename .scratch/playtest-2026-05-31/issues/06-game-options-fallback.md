# Issue 06 — 正文选项为默认文本

Status: resolved (v2.6)

## 现象

游戏主循环中，显示的行动选项是 fallback 默认值：
- "继续观察周围"
- "与附近的人交谈"
- "探索这个区域"
- "（自定义行动）"

而非 LLM 根据叙事上下文生成的具体选项。

## 根因

v2.5 流式输出将 GM 的叙事 + 选项生成分拆为两次 LLM 调用：
1. `stream_narrative()` — 流式叙事（纯文本，不生成选项）
2. `generate_options()` — 接收已完成叙事文本，调用 `chat_json()` 生成结构化选项

`generate_options()` 在 `gm.py:286-332` 实现。可能原因：

1. **LLM `chat_json()` 失败** — 触发 `except` 分支返回 fallback。检查 LLM API 是否返回了有效 JSON。
2. **Prompt 上下文不足** — `generate_options()` 的 prompt 只传了最近 2000 字符的叙事文本和场景名字，可能缺少 NPC 性格信息、当前社交动态等关键上下文，导致 LLM 无法生成具体选项。
3. **JSON 解析失败** — `_parse_structured_options()` 可能无法处理某些 LLM 输出格式，导致返回空列表 → fallback。

## 诊断步骤

1. 在 `gm.py:generate_options()` 的 `except` 分支加日志输出异常详情
2. 检查 LLM 返回的 raw options 数据
3. 对比原 `_generate_narrative_and_options()` 的 prompt 和新的 `generate_options()` prompt，确认上下文缺失项

## 影响文件

- `gm.py:286-332` — `generate_options()`

## 优先级

P0 — 正文选项是核心交互入口
