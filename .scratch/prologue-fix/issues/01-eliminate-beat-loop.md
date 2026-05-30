# P1-01 — 消除故事节拍自循环

Status: done

## 问题

当前序章的 `_extract_beat()` → `_prologue_story_beats` → `_prologue_story_prefix()` 形成自循环：LLM 输出的第一句话被自动提取为「事实」，下轮注入为【故事脉络】，LLM 在此基础上继续编造。

**示例级联：**
1. Turn 1: LLM "银发少女打着哈欠靠在墙边。她的白大褂口袋里露出半包饼干…"
2. Beat: "银发少女打着哈欠靠在墙边。"
3. Turn 2: LLM "银发少女已经睡着了，鼾声轻微…"（基于上轮 beat）
4. Beat: "银发少女已经睡着了。"
5. Turn 3: LLM 编造她被下药了
6. 5 轮后 NPC 完全偏离原始档案

## 修复方案

**方案 A（推荐）：** 将 story beats 从"LLM 输出自动提取"改为"仅记录玩家选择"。

- `_extract_beat()` 不再从 LLM 输出提取，改为记录玩家的选择文本
- `_prologue_story_beats` 变为 `["玩家选择了A：走向银发少女", "玩家选择了C：独自探索走廊"]`
- `_prologue_story_prefix()` 改为 `"【玩家行动轨迹】\n- ..."`

**方案 B：** 保留自动提取但增加校验——拒绝包含 NPC 名字、动作动词（拔出/攻击/死亡）的 beat。

**方案 C：** 完全删除 story beats 机制，依赖完整的 `_prologue_context`（12 条消息足够提供连续性）。

## 影响文件

- `server.py`：`_extract_beat()`, `_prologue_story_beats_append()`, `_prologue_story_prefix()`, `prologue_continue()`

## 关联

P0 优先级。这是序章幻觉得最核心的机制性 bug。
