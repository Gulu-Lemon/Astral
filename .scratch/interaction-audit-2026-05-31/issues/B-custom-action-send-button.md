# Issue B — 自定义行动 Send 按钮失效

Status: needs-triage | Priority: P0

## 现象

自定义行动模式时，点击发送按钮（&#9654;）无任何反应。

## 根因

`app.js:17`：`#btn-send` 绑定为 `sendDialogue()`，未检查 `S.customAction`。
`sendDialogue` 中 `var aid=S.dialogueWith;if(!aid)return;` — 自定义行动时 `dialogueWith` 为空，直接 return。

## 修复

修改 `#btn-send` 绑定，自定义行动时走 Enter handler 相同逻辑（`/api/investigate` → `nextRound`），非自定义行动时走 `sendDialogue`。

## 影响文件

- `static/app.js:17`（bind）
