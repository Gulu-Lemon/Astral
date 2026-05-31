# Issue 02 — 流式输出开始时撤掉加载遮罩

Status: resolved (v2.6)

## 现象

`narrative_start` SSE 事件到达后，客户端仍显示"推演中..."遮罩，直到 `narrative_done` 才关闭。玩家看不到逐字流出的文本。

## 根因

`app.js` 的 `narrative_start` 处理器（行 547-551）只创建了流式 div，**未调用 `showLoading(false)`**。遮罩在 `narrative_done` 中（行 575 `showLoading(false)`）才关闭。

## 修复

`narrative_start` handler 中加入 `showLoading(false)`：
```javascript
es.addEventListener('narrative_start',function(e){
  showLoading(false);
  _streamDiv=document.createElement('div');
  _streamDiv.className='log-block log-narrative';
  el('#story-log').appendChild(_streamDiv);
});
```

## 影响文件

- `static/app.js:547`

## 优先级

P1 — 流式输出的用户体验核心
