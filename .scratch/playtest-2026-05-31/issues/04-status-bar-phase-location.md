# Issue 04 — 状态栏显示 "blackout" 而非地点名

Status: ready-for-agent

## 现象

顶部状态栏（`#difficulty-badge`）显示 `blackout` 而非当前房间名称。

## 根因

`round_end` SSE 事件包含 `"phase": self.world.phase.value` 和 `"location": self.player_location`。`updateInfo()` 中将 `s.phase` 写入 `#difficulty-badge`。

`GamePhase` 枚举值为 `BLACKOUT / UNDERCURRENT / HUNTING`。游戏首轮 phase 很可能是 `UNDERCURRENT`，但如果初始化为 `BLACKOUT`，就会显示 `blackout`。

`WorldState` 初始化时 phase 的默认值需要确认。查看 `state.py` 中 `WorldState.__init__` 的 `phase` 默认值。

## 诊断步骤

1. 检查 `WorldState.__init__` 中 `phase` 的初始值
2. 检查序章 bridge (`_prologue_bridge`) 是否修改了 phase
3. 确认 `_check_phase_transition()` 在首轮的行为

注意：`#difficulty-badge` 元素原本设计用于显示难度模式（STORY/NORMAL/WITCH），但现在被复用为 phase 显示。首轮初始化时 phase 应该是 `UNDERCURRENT`（第二个枚举值），不应该显示为 `BLACKOUT`。

## 影响文件

- `state.py` — `WorldState.phase` 默认值
- `session.py` — 序章 bridge 中的 phase 设置

## 优先级

P1 — 顶部栏是核心状态显示
