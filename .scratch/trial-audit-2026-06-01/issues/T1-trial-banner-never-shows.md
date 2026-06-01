# Issue T1 — 审判横幅从不显示

Status: needs-triage | Priority: P0

## 现象

尸体被发现、审判触发后，服务端 `round_end` 事件包含了 `in_trial: true`，但客户端从不弹出审判横幅。

## 根因

`showTrialBanner()` 函数定义了（`app.js:719-722`）——但没有被任何代码调用。`updateInfo()` 第 665-668 行处理 `day/time/phase/location/floor/npcs/scene_name`，唯独不处理 `s.in_trial`。横幅始终 `display:none`。

## 修复

`updateInfo()` 中增加：
```javascript
if(s.in_trial){showTrialBanner(s.trial_victim||'',s.trial_phase||'')}
else{el('#trial-banner').style.display='none'}
```
同时 `round_end` 需要补传 `trial_victim` 和 `trial_phase`。

## 影响文件

- `static/app.js:665-668` — updateInfo
- `session.py:1068` — round_end 补字段
