# 13 — server.py 拆分为 Flask Blueprint

Status: done

## 问题

`server.py` 持续膨胀至 **1254 行**（AGENTS.md 预期 ~800 行，超出 53%）。包含：序章系统、游戏主循环、审判系统、存档、配置、场景、角色卡——全都混在一个模块中。

继续按此速度膨胀将变得难以维护。

## 建议方案

按功能域拆分为 Blueprint：

```
server.py           (~200行, 仅 app 创建 + main)
blueprints/
  prologue.py       序章 8 个端点
  game.py           游戏主循环 + dialogue + explore + investigate
  trial.py          审判 4 个端点
  save.py           存档 5 个端点
  config.py         配置 5 个端点 + profiles
  cards.py          场景 + 角色卡 5 个端点
  meta.py           元指令 + free_narrative
```

`GameSession` 保留在 `server.py` 或提取到 `session.py`。

## 影响文件

- `server.py`：大幅缩减
- 新建 `blueprints/` 目录下 6-7 个文件
- `main()` 调整 Blueprint 注册

## 关联

P3 优先级。需要评估投入产出比。建议在功能稳定、无紧急需求时执行。

## Comments

此类重构建议先创建 `blueprints/` 目录并逐个迁移端点组，每步验证 API 可用性。不要一次性全部迁移。
