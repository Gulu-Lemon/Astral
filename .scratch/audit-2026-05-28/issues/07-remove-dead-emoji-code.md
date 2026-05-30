# 07 — 清理 emoji/emote 死代码

Status: done

## 问题

`app.js` 中 `emojiColor()` 和 `emoji()` 函数已声明但**未被调用**。NPC 渲染仅使用 `affLabel()`，不使用 emoji 函数。同时 `.npc-card .emote` CSS 类也未使用。

## 修复方案

1. `app.js`：删除 `emojiColor()` 和 `emoji()` 函数声明
2. `style.css`：删除 `.npc-card .emote` 相关样式规则

## 影响文件

- `static/app.js`
- `static/style.css`

## 关联

P2 优先级。低风险清理。
