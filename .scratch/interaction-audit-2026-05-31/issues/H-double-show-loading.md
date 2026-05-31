# Issue H — `showLoading(false)` 每轮双重调用

Status: needs-triage | Priority: P2

## 现象

`narrative_start`（line 579）和 `narrative_done`（line 618）各调一次 `showLoading(false)`。

## 根因

两个处理器各自独立关闭 loading。第一次是正确时机（流式开始），第二次是历史遗留（`narrative_done` 的旧行为——非流式时在这里关 loading）。冗余但无害。

## 修复

从 `narrative_done` 中移除 `showLoading(false)`，只保留 `narrative_start` 中的调用。

## 影响文件

- `static/app.js:618`
