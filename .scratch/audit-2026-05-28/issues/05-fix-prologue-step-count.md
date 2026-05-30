# 05 — 修正序章步骤计数

Status: done

## 问题

`PROTOCOL.md` L38 标题写 "序章流程（**7 步**）"，但表格中实际列出了 **8 个** 端点：
mirror, magic, difficulty, camp, continue, explore, admin, finish

## 修复方案

两种选择：
1. (推荐) 不计入 `continue`（它是 camp 的延续交互），改为 "7 步 + 续章交互"
2. 改为 "8 步"

选择方案 1 更贴近设计意图。

## 影响文件

- `PROTOCOL.md`：L38 标题修改

## 关联

P2 优先级。与 #03、#04、#06 一起修复文档准确性。
