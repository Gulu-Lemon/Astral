# Issue 04 — Agent 进度显示永远 `0/12`

Status: resolved (v2.6)

## 现象

SSE 推演期间，加载遮罩上的进度条始终显示 `Agent 0/12`，不随完成数量更新。

## 根因

`app.js:560` 读错了 key：

```javascript
var pct=d.pct||0;el('#loading-progress').textContent='Agent '+pct+'/12';
```

服务端 `session.py:927` 发送的字段是 `"completed"` 和 `"total"`：

```python
{"type":"agent_done","completed":completed,"total":total}
```

`d.pct` 永远为 `undefined` → `||0` = `0`。

## 修复

```javascript
el('#loading-progress').textContent='Agent '+d.completed+'/'+d.total;
```

## 影响文件

- `app.js:560`

## 优先级

P1
