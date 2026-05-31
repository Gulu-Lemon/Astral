# Issue A — 对话选项玩家文字重复显示

Status: needs-triage | Priority: P0

## 现象

点击对话选项后，玩家消息出现两次："你：选项标签"（不应出现）+ "你：实际输入"。

## 根因

第一处 `app.js:600`（onclick）：
```javascript
addLog('dialogue','你：'+o.label);  // 选项标签被当作玩家消息显示
```
第二处 `app.js:685`（sendDialogue）：
```javascript
addLog('dialogue','你：'+msg);      // 实际键入内容
```

## 修复

删除 onclick 中的第一处 `addLog`。改为将选项文字作为上下文传入 `talkToNPC(target, o.label)`，在对话框标题或 placeholder 中显示语境。

## 影响文件

- `static/app.js:598-604`（onclick）
- `static/app.js:664-676`（talkToNPC 签名）
