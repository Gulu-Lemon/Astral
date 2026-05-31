# Issue D — 读档后历史叙事被立即清空

Status: needs-triage | Priority: P1

## 现象

读档后，存档中的 narrative_log 条目短暂闪现后消失。

## 根因

`doLoadSave` 第 771-773 行先 `addLog` 显示历史叙事，第 775 行调 `nextRound()`。`nextRound()` 开头 `clearLog()` 立刻清除 `#story-log` 全部内容。

## 修复

`nextRound()` 增加可选参数 `keepLog`，读档时传 `true` 跳过 `clearLog()`。

```javascript
function nextRound(keepLog){
  if(!keepLog)clearLog();
  ...
}
```

`doLoadSave` 中：`nextRound(true)`

## 影响文件

- `static/app.js:568`（nextRound 签名）
- `static/app.js:775`（doLoadSave 调用）
