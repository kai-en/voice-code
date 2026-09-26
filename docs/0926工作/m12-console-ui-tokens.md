# M12（未排期）console web UI 素材：opencode 客户端设计令牌

> 从 `m10-proc-hygiene-textin-design.md` v1 的附录 A 移出。本期（M10/M11）**不做网页**，此文件只是已实测取到的资产，避免重取。
> 取法：本机 `opencode serve`（默认 4096，E7）内嵌 web 壳，静态资源不需鉴权可读；用 `getComputedStyle(documentElement)` 枚举 CSS 自定义属性 + 截图对照（2026-09-26 实测）。数据接口要 Basic auth（密码每次启动随机、只活在 `ServeProcess` 对象里，serve.py:52），故会话列表读不到——取样式不需要它。

## 令牌

- 字体：`--font-sans: "Inter", ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif`；`--font-mono: "IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace`
- 字号/行高：13px（body/small）/ 14px（base）/ 16px（lg）/ 20px（xl）；行高 130%（normal）、20px（base）、180%（x-large）；字重 400/500
- 背景：页 `#fafafa`（`--background-base`/`--v2-background-bg-deep`/`bg-layer-01`）、卡片与输入 `#ffffff`、`#f8f8f8`（`surface-base`/`input-base`）、`#f2f2f2`（`layer-02`/hover）、`#eeeeee`（`layer-03`）、`#dbdbdb`（`layer-04`）
- 文字：`#171717` strong/stronger、`#161616` v2-text-base、`#6F6F6F` text-base、`#8F8F8F` weak、`#C7C7C7` weaker、`#5c5c5c` muted、`#aeaeae` faint
- 边框：`#DBDBDB` weak、`#E8E8E8` weaker、`#c1c0c0` base、`rgba(0,0,0,.1)` v2-border-base、`rgba(0,0,0,.2)` strong
- 主色/交互：`#054dfd` icon-interactive、`#0445e6` text-interactive、`#3b5cf6` accent(v2-blue-600)、hover `#0b34f4`、选中描边 `rgba(5,77,253,.99)`、浅交互底 `#F5FAFF` / `#d2e1fd`
- 圆角：`.125rem` xs / `.25rem` sm / `.375rem` md / `.5rem` lg；间距基准 `.25rem`
- 阴影：`--shadow-xs: 0 1px 2px -.5px #0000000a, 0 .5px 1.5px 0 #00000006, 0 1px 3px 0 #0000000d`；`--shadow-md`、`--shadow-lg` 递增；卡片描边阴影 `0 0 0 1px #DBDBDB`
- 语义色：success `#198b43`、danger `#b82d35`、warning `#cb9f34`、info `#3250df`；agent 色 build `#3250df` / plan `#c83d8b` / review `#198b43` / explore `#ac8833`
- 语法色（若显示代码/工具输出）：keyword `#c83d8b`、string `#198b43`、type `#5230c2`、property `#d16427`、comment `#5c5c5c`、diff add/delete `#198b43`/`#b82d35`
- 布局实测：左薄侧栏（项目 / 添加项目 / 设置 / 帮助）+ 右主区；顶部一条 `#f2f2f2` 圆角搜索条；未加载时是 `#fafafa` 骨架行；整体留白大、描边极淡、无重色块

## 若将来真要在 M11 同一端口发页面（本期不做）

- 可行，已冒烟实测：`process_request(connection, request)` 里**必须**判 `"websocket" in request.headers.get("Upgrade","")`，非升级才 `connection.respond(200, html)` 并改 `resp.headers["Content-Type"]="text/html; charset=utf-8"`；漏判的后果实测为客户端报 `server rejected WebSocket connection: HTTP 200`。
- 默认行为更好：不写 `process_request` 时，非升级请求由库回 **426**（websockets\server.py:179-194），本期即采用默认，不 serve 任何内容。
- 代价（不是"多写几行"级别）：库的 HTTP 响应体 `MAX_BODY_SIZE=1MiB` 且注释明说不是为传文件设计（http11.py:51-53）；无 mime/缓存/Range 要自己糊；端口一旦"是个网站"就要面对 auth/CORS/静态目录/浏览器缓存；`src/console/server.py` 从"WS 端点"变成"WS 端点 + 静态服务器"，行数与测试面同涨。
