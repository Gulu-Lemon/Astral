# P3-03 — GM 可感知 NPC 实时情绪

Status: wont-fix

## 决策

游戏设计决定。GM 写玩家视角所见，不应知道 NPC 实时情绪。NPC 情绪通过 dialogue/prose 自然表达即可。

## 问题

GM prompt 中的 NPC 速写全是静态档案数据（personality, magic, play_core, habits, appearance），完全没有实时 `emotional_state`。

NPC 处于 "暴怒" 或 "恐惧" 状态，GM 叙事完全不知情——除非 dialogue/prose 恰好表达了这种情绪。

## 修复方案

在 `gm.py:_generate_narrative_and_options()` 的 NPC 速写中增加一行情绪：

```python
# 当前
sketch = f"{name}：性格{st.profile.personality}..."
# 改为
emotion = agent_states.get(aid).emotional_state or "平静"
sketch = f"{name}：性格{st.profile.personality}，当前情绪：{emotion}..."
```

同时在 `_build_narrative_materials()` 中传递 emotional_state。

## 影响文件

- `gm.py`：`_generate_narrative_and_options()` NPC 速写部分
- `arbiter.py`：`_build_narrative_materials()` 增加 emotional_state 字段

## 关联

🟠 P1 优先级。让 GM 叙事能反映 NPC 当下的真实情绪状态。
