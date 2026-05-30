# 06 — 统一 CSS/JS 版本号

Status: done

## 问题

`style.css:1` 标注 `v0.3`，而 `app.js:1` 标注 `v0.4`。版本号不同步。

## 修复方案

统一为当前项目版本 `v0.5`：

- `style.css:1`：`v0.3` → `v0.5`
- `app.js:1`：`v0.4` → `v0.5`

## 影响文件

- `static/style.css`：L1
- `static/app.js`：L1

## 关联

P2 优先级。与 #03、#04、#05 一起修复文档准确性。
