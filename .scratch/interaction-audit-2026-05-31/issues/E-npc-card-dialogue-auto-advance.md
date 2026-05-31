# Issue E — NPC 卡片点击对话关闭时不应自动推进

Status: needs-triage | Priority: P1

## 现象

通过 NPC 面板点击角色卡片打开的对话，关闭后自动推进到下一轮。

## 根因

`closeDialogue` 第 689 行：`if(!S.customAction)nextRound()` — 只要不是自定义行动就无条件推进。但 NPC 卡片对话应该是探索性交互，关闭后应返回查看其他选项而非直接跳下一轮。

## 修复

在 `talkToNPC` 中设置标记 `S.npcDialogue=true`，在 `closeDialogue` 中检查：只有通过选项点击进入的（`!S.npcDialogue`）才自动 nextRound。NPC 卡片进入的在关闭后恢复选项显示。

## 影响文件

- `static/app.js:664`（talkToNPC）
- `static/app.js:689`（closeDialogue）
