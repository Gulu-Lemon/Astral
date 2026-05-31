# Pipeline Audit 2026-05-31 — 正文管线诊断

Status: needs-triage

逐段追踪 `gm.py → session.py → game.py → app.js` 全链路发现 7 项问题。
3 严重 + 4 中等。SSE 事件类型、data key、游戏循环链等核心通道无问题。

详见各 Issue：
- `issues/01-stream-narrative-silent-fail.md` — P0
- `issues/02-stream-temperature-too-high.md` — P0
- `issues/03-missing-player-action.md` — P1
- `issues/04-agent-done-progress-key.md` — P1
- `issues/05-generate-options-truncation.md` — P2
- `issues/06-prompt-inflation.md` — P2
- `issues/07-crude-narrative-summary.md` — P2
