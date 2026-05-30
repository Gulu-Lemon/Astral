# P1-02 — NPC 档案按玩家已知信息分级注入

Status: done

## 问题

`_npc_profile_roster()` 每轮把全部 12 个 NPC 的完整档案（含 `play_core`：秘密、魔女动机、内心矛盾）注入 LLM prompt，但同时要求 LLM "用外貌特征描述，不要用真名"。

**矛盾：** LLM 知道了所有秘密，却被要求假装不知道。这导致：
- LLM 倾向"不小心"泄露秘密（因为它在脑中已经构建了完整故事）
- NPC 行为可能基于 LLM 知道的秘密而非玩家可见的表面信息

## 修复方案

建立三级 NPC 信息暴露模型：

```
L1 外貌层（始终可见）：appearance[:80]
L2 性格层（互动后可见）：personality[:80]  
L3 秘密层（仅在LLM构建NPC系统提示时使用，不注入旁白prompt）：play_core, secret, witch_motive
```

修改 `_npc_profile_roster()` 为：
```python
def _npc_profile_roster(self, level: str = "L1") -> str:
    """level: 'L1'=外貌, 'L2'=外貌+性格, 'L3'=完整"""
```

序章中旁白调用使用 L2（外貌+性格，不含秘密）。Agent 决策时仍使用 L3（Agent 需要知道自己的秘密才能决策合理）。

## 影响文件

- `server.py`：`_npc_profile_roster()` 重构，所有调用处增加 level 参数
- `scenarios/`：可能需要调整 CharacterProfile 结构以更清晰分离秘密字段

## 关联

P0 优先级。与 #01 一起解决最核心的幻觉来源。
