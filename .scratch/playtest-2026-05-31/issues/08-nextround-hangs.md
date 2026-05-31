# Issue 08 — 点击选项后"推演中"无响应

Status: resolved (v2.6, commit pending)

## 现象

玩家点击正文选项 → 显示"推演中..."遮罩 → 永久等待，无任何后续事件（无 `agent_done`、`narrative_chunk`、`round_end`）。

## 可能原因（排查优先级从高到低）

### A. `nextRound()` 未被调用或 SSE 连接建立失败

`doStructured()` 在 `app.js:580-590` 中根据选项 type 分支：
- `dialogue` → `talkToNPC()`
- `explore` → `exploreRoom()`
- `investigate` → `doAction()`
- 无 → 不触发任何后端请求

如果选项 type 不匹配任何分支，`showLoading(true,'推演中...')` 执行后没有任何后端调用，遮罩永久存在。

检查：`generate_options()` 返回的选项 type 字段是否在 `("dialogue", "investigate", "explore", "custom")` 范围内。

### B. SSE `/api/round` 连接建立但服务端错误

如果 `doStructured` 触发了某个流程最终调了 `nextRound()`，而 SSE 连接正常建立但服务端线程立即崩溃（与 Issue 06 相关——如果 GM 选项是 fallback，GM 流式方法本身可能也在首轮失败）。

### C. `doStructured` 中的动作类型与预期不符

目前 `custom` 类型的选项调用 `doAction({action: o.label})`（app.js:582），但 `doAction` 的实现未知。如果 `doAction` 阻塞或失败，也会导致遮罩永久显示。

## 诊断步骤

1. **第一步**：在 `doStructured()` 中加 `console.log(o)`，确认收到的选项对象结构
2. **第二步**：检查 `narrative_done` 事件中 `d.options` 数组的实际数据——`type` 字段值是否合法
3. **第三步**：如果是 `custom` 类型，追踪 `doAction()` → `/api/action` 端点的请求/响应
4. **第四步**：如果是 `investigate` 或 `explore`，确认对应端点返回正常
5. **第五步**：检查 `nextRound()` 是否被正确触发——当前代码中 `doStructured` 调用后，客户端没有自动推进到下一轮的逻辑！`nextRound()` 只在 `prologueFinish()` 中被调用。游戏循环需要一种机制来触发下一轮。

## 关键发现

**游戏主循环缺少自动推进逻辑。** 首轮 `narrative_done` 渲染选项后，玩家点击选项 → `doStructured()` 执行动作 → **没有自动调 `nextRound()`**。当前代码中：
- `prologueFinish()` → `nextRound()` 只触发首轮
- 后续轮次没有任何自动推进

需要确认：原 `synthesize_round()` 阻塞版本中，`nextRound()` 的调用机制是什么？如果此前是通过某种方式在选项执行后触发，该机制在流式改造中可能被遗漏。

## 影响文件

- `static/app.js:536` — `nextRound()` 只有 `prologueFinish` 调用它
- `static/app.js:580-590` — `doStructured()`

## 优先级

P0 — 阻塞游戏循环
