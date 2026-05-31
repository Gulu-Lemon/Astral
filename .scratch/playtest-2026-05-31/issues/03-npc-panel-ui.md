# Issue 03 — NPC 角色栏 UI 异常

Status: resolved (v2.6, commit ce39d77)

## 现象

左侧 NPC 面板排列/样式"非常奇怪"。需现场检查`渲染格式、CSS 布局、数据字段。

## 可能根因

需要排查以下几方面：

1. **CSS 布局**：`style.css` 中 `.npc-card`、`.npc-list`、`#npc-panel` 的 flex/grid、overflow、宽高、字体大小可能在近期改动中退化。

2. **渲染数据格式**：`renderNPCs()` 现在接收两路数据——`prologueFinish()` 中的 `/api/state` 返回的 npcs 数组（meta.py `_npc_info()` 格式），和 `round_end` 中新加的 `_npc_list`（session.py 第 1048 行格式）。两路数据字段略有差异：

   - `/api/state`（meta.py `_npc_info()`）：`agent_id, name, age, affection, threat, location, nearby`
   - `round_end`（session.py `_npc_list`）：`agent_id, name, affection, location, nearby, alive, emotion`

   **都没有 `alive`** 字段的保底。`renderNPCs()` 第 515 行读 `n.alive` → 可能是 `undefined` → `!undefined` = `true` → 不会应用半透明样式，但也不 crash。

3. **位置显示逻辑**：`nearby` 判断基于 `self.world.npc_locations.get(aid, "") == self.player_location`，但玩家位置可能在 `prologue_finish` 后尚未从序章位置更新。

## 诊断步骤

1. 在浏览器 DevTools 中检查 `#npc-list` 的 computed styles
2. 检查 `renderNPCs()` 收到的 npcs 数组结构
3. 对比 `/api/state` 和 `round_end` npcs 数据的字段差异

## 影响文件

- `static/style.css`
- `static/app.js:509-523` — `renderNPCs()`
- `session.py:1048` — `_npc_list` 构建
- `blueprints/meta.py:44-51` — `_npc_info()`

## 优先级

P1 — 主要 UI 元素异常
