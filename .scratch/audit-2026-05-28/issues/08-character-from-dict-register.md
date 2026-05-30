# 08 — CharacterProfile.from_dict 不注册到全局字典

Status: done

## 问题

`characters.py` 中 `CharacterProfile.from_dict()` 调用 `build_system_prompt()` 重建 system_prompt，但**不将角色注册回全局 `CHARACTERS` 字典**。这与其他创建路径（`register_character()`、场景 `_cp()`）行为不一致。

调用方必须手动注册，否则静默产生孤立对象。

## 修复方案

方案 A（推荐）：在 `from_dict` 末尾增加注册：
```python
@classmethod
def from_dict(cls, d: dict) -> "CharacterProfile":
    p = cls(...)
    p.system_prompt = cls.build_system_prompt(p)
    # 注册到全局字典（如果 agent_id 有效）
    if p.agent_id:
        CHARACTERS[p.agent_id] = p
    return p
```

方案 B：改为在调用方 `save_manager.apply_loaded_state` 中显式注册。

## 影响文件

- `characters.py`：`from_dict` 方法

## 关联

P1 优先级。防止存档加载后角色丢失。
