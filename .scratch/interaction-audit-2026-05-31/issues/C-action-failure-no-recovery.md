# Issue C — 移动/调查失败后无恢复机制

Status: needs-triage | Priority: P0

## 现象

探索或调查 API 返回失败时，`alert()` 弹窗后用户面对空白界面——选项按钮已被 `hideActionBar()` 清除，loading 已被 `showLoading(false)` 关闭。无任何方式重试或继续。

## 根因

`app.js:695-696`（exploreRoom）+ `app.js:703-704`（doAction）：
```javascript
else{alert(d.error||'移动失败');hideActionBar();showLoading(false)}
```
onclick 先调了 `hideActionBar()`，失败分支又调一次（重复但无害）。然而没有恢复选项按钮或提供"重试"入口。

## 修复

失败时恢复显示选项按钮。可通过闭包保留原始 `o` 对象，失败时重新生成按钮并追加到 `#action-bar`：
```javascript
else{
  alert(d.error||'移动失败');
  // 恢复选项按钮
  var btn=document.createElement('button');btn.className='action-btn';
  btn.textContent='重试';btn.onclick=function(){...original onclick...};
  el('#action-bar').innerHTML='';el('#action-bar').appendChild(btn);
}
```

## 影响文件

- `static/app.js:692-698`（exploreRoom）
- `static/app.js:700-706`（doAction）
