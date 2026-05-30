# 03 — 统一文档中的 API 计数为 37

Status: done

## 问题

AGENTS.md 三处（L12, L136, L145）声称 "39 API 端点"，但实际只有 **37 个**。差异可能源于将 `/api/cards` 和 `/api/profiles` 的 GET/POST 分别计数。

## 修复方案

`AGENTS.md` 中所有 "39" 替换为 "37"：
- L12: `39 API` → `37 API`
- L136: `Flask 39 API 端点` → `Flask 37 API 端点`
- L145: `39 个 API 端点` → `37 个 API 端点`

## 影响文件

- `AGENTS.md`：3 处替换

## 关联

P2 优先级。与 #04 一起修复文档准确性。
