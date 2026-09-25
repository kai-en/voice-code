---
name: playwright
description: Use whenever operating a browser via the playwright_browser_* MCP tools in this project. Enforces the fixed headed Chrome + fixed user-data-dir setup, and forbids all headless paths (live-stream OBS would break).
---

# Playwright 浏览器使用规范（项目级）

## 1. 固定配置（不得改动）

- MCP 启动命令（`~/.config/opencode/opencode.json`）：
  `npx -y @playwright/mcp@latest --browser chrome --executable-path "C:\Program Files\Google\Chrome\Application\chrome.exe" --user-data-dir C:\Users\Administrator\.config\opencode\playwright-profile`
- **固定 user-data-dir**：登录态、Cookie 全在 `playwright-profile` 里；同一 profile 同时只能被一个浏览器实例占用，另起会报 "Browser is already in use"。禁止换/删该目录。
- 窗口纪律见 `AGENTS.md`：先 `playwright_browser_tabs action=list` 复用现有窗口/标签；禁止 `playwright_browser_resize` 或任何改窗口尺寸的操作（用户手调尺寸 = 直播 OBS 画面）。

## 2. 必须可视化（headed）——headless 坑清单

MCP 默认 headed（官方 README："headed by default"；Windows 下源码不显式设置即 headed）。但一旦掉进 headless：viewport 被强制 1280x720，**直播 OBS 展示直接穿帮**。以下行为全部禁止：

1. 给 MCP 配置追加 `--headless`、设置环境变量 `PLAYWRIGHT_MCP_HEADLESS`、或 config 里写 `launchOptions.headless: true`；
2. 用 bash 自写 node/python 脚本调 `chromium.launch()` / `launchPersistentContext()` / `launchServer()`——原生 API **默认 `headless: true`**，忘传 `headless:false` 必掉坑；且脚本也进不了用户可见的直播窗口；
3. `npx playwright screenshot` / `npx playwright pdf`（源码硬编码 headless）；新 `playwright-cli` 也默认 headless（须 `--headed`）——官方现在推荐 coding agent 走 "CLI+SKILLS" 替代 MCP，**本项目拒绝该路线**；
4. 在 `browser_run_code_unsafe` 里 require/import playwright 另起浏览器：vm 上下文只注入了 `page`（实测无 require/process），launch 既默认 headless 又撞 profile 锁；
5. 把 MCP 换成 Docker 部署（官方镜像仅支持 headless chromium）。

**正确做法**：
- 只用 `playwright_browser_*` MCP 工具，所有操作落在同一个 headed Chrome；
- 截图用 `browser_take_screenshot`；需要复合/原子操作时用 `browser_run_code_unsafe`，且只准使用注入的 `page`（headed 下 `page.pdf()` 实测可用）；
- 附：headed 下 MCP 永不闲置回收（headless 默认 1 小时被关），长直播会话因此也更稳。

## 3. LLM 中转会改写工具参数里的 URL（2026-09-25 取证）

provider 中转层（routify 文件代理）会扫描模型输出中的**完整 URL 字符串**并替换为其预取的 OSS 签名链接（`routify-file-proxy-*.aliyuncs.com/...trace_.../requestId_...`），替换发生在工具参数到达 opencode 之前。症状：
- navigate/webfetch 结果是 403（routify 对象不存在/预取失败）；
- 内容与所请求 URL 完全无关（预取副本错乱，如搜魔兽返回无关大学页面）；
- `### Ran Playwright code` 回显出现 routify 地址 = 本次已被改写（对照检查用）。

**规避（按序）**：
1. 疑似被改写时用 `browser_evaluate` + `location.href`，URL 在页内**分片拼接**（`'wowh'+'ead.co'+'m'`，实测绕开且请求真实外发）；fetch 同理在 evaluate 内拼串。
2. 本地执行器直连：bash `Invoke-WebRequest`/curl 不经模型输出面，天然免疫（仅取文本内容时用）。
3. 引用/入库时记录**本想访问的真实 URL**，不要把 routify 链当目标；也禁止把 routify 残留链复制进后续调用（必 403）。
4. 一次改写≠目标站拒绝：换分片拼接重试后再下"该站不可达"结论。
