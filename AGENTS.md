# AGENTS.md

## Playwright 窗口使用规则

- 每次会话开始需要使用浏览器时，先用 `playwright_browser_tabs action=list` 核实是否已有 Playwright 窗口/标签；如已存在，必须复用现有窗口（在现有窗口中新建或选择标签），不要另开新窗口。
- 禁止修改此 Playwright 窗口的大小（不调用 `playwright_browser_resize`，也不以其他方式改变窗口尺寸）。用户已手动调整过窗口大小，用于直播时 AI 操作浏览器的实时显示效果。
