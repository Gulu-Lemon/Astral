# Issue 05 — 游戏中点击 API 配置无法显示/退出

Status: resolved (v2.6)

## 现象

游戏进行中，点击"设置"或"API 配置"按钮后：
- 配置界面不显示或显示异常
- 无法退出配置界面回到游戏

## 根因猜测

`switchTab('settings')` 或相关逻辑在游戏进行中（非初始加载）被调用时，CSS `display` 切换与现有 overlay/panel 的 z-index 或 display 状态冲突。

可能涉及的 CSS 层级：
- `#prologue-screen`、`#npc-panel`、`#map-strip`、`#story-log`、`#action-bar` — 游戏界面
- `#settings-tab` — 设置面板
- `#loading-overlay` — 加载遮罩
- Modal 弹窗的 `position: fixed` + `z-index`

主界面通过 `hideMainTabs()` 隐藏了 `#main-tabs`、`#card-manager`、`#scene-screen`、`#settings-tab`，但 `switchTab('settings')` 尝试显示 `#settings-tab` 时可能与其他 overlay 冲突。

另外，"退出配置界面"需要有一个关闭按钮或返回逻辑。如果按钮被遮盖或事件未绑定，用户会卡住。

## 诊断步骤

1. 游戏中打开 DevTools，手动执行 `switchTab('settings')` 检查元素 display 和 z-index
2. 检查 `#settings-tab` 在游戏中的 `style.display` 计算值
3. 确认关闭/退出按钮的事件绑定是否存在

## 影响文件

- `static/index.html` — `#settings-tab` DOM 结构
- `static/app.js:94-98` — `switchTab()`
- `static/style.css` — 各面板的 display/z-index

## 优先级

P2 — 边缘路径，但阻塞操作
