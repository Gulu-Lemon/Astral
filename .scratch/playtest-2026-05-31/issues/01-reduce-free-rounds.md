# Issue 01 — Free 阶段减少一轮

Status: ready-for-agent

## 现象

序章 free 阶段目前 3 轮才推进到 admin，节奏偏慢。

## 根因

`session.py:397` 硬编码 3 轮门槛：
```python
if self._prologue_turn >= 3:
    self._prologue_phase = "admin"
```

## 修复

将阈值从 3 降为 2：
```python
if self._prologue_turn >= 2:
```

## 影响文件

- `session.py:397`

## 优先级

P2 — 体验优化
