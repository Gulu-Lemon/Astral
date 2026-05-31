# Issue F — 自定义行动关闭后无法推进

Status: needs-triage | Priority: P1

## 现象

自定义行动模式下点击关闭按钮后，玩家卡住无法推进。

## 根因

`closeDialogue` 第 689 行：
```javascript
if(!S.customAction)nextRound();S.customAction=false
```
执行顺序问题：先判断 `S.customAction`（此时为 `true`，不进 nextRound），再设 `false`。自定义行动关闭后既不发送动作也不推进——玩家只能通过 Enter 回车退出。

## 修复

先保存值再判断：
```javascript
var wasCustom=S.customAction;S.customAction=false;
if(!wasCustom)nextRound();
```

## 影响文件

- `static/app.js:689`
