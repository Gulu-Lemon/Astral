# Issue G — SSE 失败无重试机制

Status: needs-triage | Priority: P2

## 现象

SSE 连接失败或 `run_round` 崩溃后，客户端只显示"推演出错，请重试。"，无自动重试或手动重试按钮。

## 根因

`app.js:630-634` 错误 handler 只设文字 + 关连接，不提供恢复路径。

## 修复

错误 handler 中增加"重试"按钮注入到 `#action-bar`：
```javascript
var retryBtn=document.createElement('button');retryBtn.className='action-btn';
retryBtn.textContent='重试';retryBtn.onclick=function(){nextRound()};
el('#action-bar').appendChild(retryBtn);
```

## 影响文件

- `static/app.js:630-634`
