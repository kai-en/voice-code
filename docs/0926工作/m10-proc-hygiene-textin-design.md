# M10 进程卫生 100% + M11 本地 WebSocket 文本通道 设计

> 2026-09-26 **v2 重写版**。v1（同日早稿）把"未来可能要的网页"当成本期需求写进了设计，并含两处事实错误，勘误见 §8。
>
> 用户原话口径（唯一有效）：
> 1. 「删」——删掉 `scripts/oc2_live.py` 及其计划任务宿主路线。**已完成**：任务 `schtasks /delete`、进程树 11904/5976/12856/4188/1744 全 gone、4096 无 LISTEN。**未完成**：文件本身仍在磁盘（271 行），等你说删。
> 2. 「改设计，**不分模式**的，在**主流程不变**的前提下，开一个新的 http 本地端口，走 websocket，**全双工**，可以**收发任何文本帧**。**异步**模式。发 oc2 请求是该端口的**第一个能力**。」补充：「这个 websocket，要能同时收文本和发文本，这个能力是异步的」。
> 3. ~~「之后要做一个网页…样式照搬 opencode web」~~ → **作废并移出本期**（用户否认要求过 web）。web UI 若将来要做，另开 M12 设计；本期交付的是**通道**，不是界面。
>
> 本期不做：开机自启、崩溃自拉起、脱离会话树的常驻宿主、任何 `schtasks`、由本端口 serve 任何 HTML/静态资源、浏览器 UI。

## 0. 事故与实测证据

| # | 证据 | 位置 |
|---|---|---|
| E1 | 计划任务 `/sc onlogon` + `LogonType=InteractiveToken` → 登录自启 + 必然分配可见控制台（黑窗） | scripts/oc2_live.py:178；`Export-ScheduledTask` 实测，注册于 09-26 02:43 |
| E2 | run.bat 的 sweep 锚是 `voice-code\\main\.py`，抓不到 `scripts\oc2_live.py` → 实测 PID 11904 = MISS | run.bat:14 |
| E3 | venv python 会 re-exec 出第二层 `F:\anaconda3\python.exe`，命令行是**相对路径**、子层镜像路径在**仓库外** → 按命令行锚、按镜像锚都扫不全 | 实测 + `.venv\pyvenv.cfg`(`home=F:\anaconda3`) |
| E4 | 它的 oc2 子进程（4188/1744）反被 `tools\oc2` 锚命中 → run.bat 真实行为是「杀子留父」：僵尸占麦/TTS/GPU，再起 main.py = 双开 | run.bat:14 + 实测进程树 |
| E5 | 「常驻省重载」这条存在理由已失效：后端换 winTTS（零显存秒起），且常驻本应由 run.bat 常驻 main.py 提供 | src/tts/tts.py:249「PowerShell 子进程常驻」 |
| E6 | 清理一直靠「stop 代码写对」，没有 OS 级保证 | 会话初快照的旧 AGENTS.md「Ctrl+C 漏杀 serve 子进程，4 次共 12 个残留」（该文件现已被裁成 7 行，见 E13） |
| E7 | `4096` 是 **opencode serve 自己的默认端口**：全仓搜 `4096` 零命中，url 从 serve stdout 首行 `{"url":...}` 读来；杀 daemon 后只剩 `TimeWait`、无 LISTEN → **M11 不得占 4096** | src/opencode_client/serve.py:59-60 |
| E8 | 该 serve 页静态壳不需鉴权（Bun exe 内嵌），数据接口要 Basic auth，密码每次随机、只活在 `ServeProcess` 对象里、从不落盘 → 样式令牌可读、会话读不到 | serve.py:52 |
| E9 | **websockets 17.1 对非升级请求默认回 426**，正文即 "You cannot access a WebSocket server directly with a browser. You need a WebSocket client." → "HTTP 本地端口"这半边**零代码**得到，本期不需要写 `process_request` | .venv\Lib\site-packages\websockets\server.py:179-194 |
| E10 | `broadcast()` 无背压、跳过非 OPEN 连接、单连接写失败只 warning；`send_in_progress`（流式/可迭代发送）会让某连接**静默丢帧** | websockets\connection.py:1172-1178, 1222-1233, 1240-1249 |
| E11 | asyncio `reuse_address` **只在 Unix 默认 True**，Windows 默认 False；而 Windows 的 `SO_REUSEADDR` 语义是"允许强绑别人正在监听的端口"（MSDN 警告可被 socket 劫持）→ **禁用它来"修 TIME_WAIT"**，否则与 §2.1 的反双开冲突 | Python create_server 文档 + MSDN |
| E12 | `scripts/oc2_live.py` 仍在磁盘，**271 行**（v1 记成 269） | 实测 read |
| E13 | 现 `D:\work\voice-code\AGENTS.md` 全文 7 行，只有 Playwright 窗口规则；**无"仓库纪律"节** → v1 三处"勘误 AGENTS.md 第 3 条"悬空，性质是**新增**不是勘误 | AGENTS.md:1-7 + 全仓 grep |

**结论**：计划任务宿主不是"多余"，是**反向**——它造出了 run.bat 清不掉的进程形态，而"清干净"是开发期唯一硬要求。"送文本进去"的正确落点也不是第二个 daemon，而是主进程里的一条双向通道（§3）。

## 1. 边界

| 动作 | 物件 |
|---|---|
| 删（**待执行**） | `scripts/oc2_live.py`（271 行，含全部 `schtasks` 调用）及其文件面 `logs\oc2_task.jsonl`/`oc2_replies.jsonl`/`oc2_live_status.json`/`oc2_live*.log` |
| 已完成 | `voice-oc2-live` 计划任务 + 其进程树（`schtasks /end` 一次收掉整树，复查全 gone） |
| 新增（不是勘误） | AGENTS.md 目前没有任何仓库纪律 → 需**新增**一节：启动/停止只经 run.bat/stop.bat、`src/` 5000 行红线、kill 前过滤、pip `--target` 坑（见 §6 P1）。v1 引用的"第 3 条"在现文件里不存在 |
| 留 | `scripts/oc2_ask.py`（一次性文本问答，无 TTS，不动）；`run.bat`/`stop.bat`/`log.bat` |
| 新增 | M10 `src/lifecycle/`（进程卫生）+ M11 `src/console/`（**本地 WS 文本通道，无界面**） |
| 顺手 | 空目录 `src/end_session`、`src/support`、`src/ux_adapter` 可删 |
| **不做** | 任何"文本模式/语音模式"分岔；stdin REPL；`--text` 参数；**由本端口 serve HTML/静态资源**；浏览器 UI |

## 2. M10 进程卫生：三层保证 + 端口卫生

思路：100% 不能靠"清扫正则穷举得够全"（E3 已证伪）。改成 **(a) 新实例启动即断言环境干净，不干净就启动失败**；**(b) 杀父有 OS 级连坐保证**，不依赖命令行文本。

### 2.1 存活自证（取代裸 pidfile）
- `logs\voice-code.lock`：`msvcrt.locking(fd, LK_NBLCK, 1)` 非阻塞独占。进程被 `/F` 强杀/崩溃/断电 → OS 释放 → **锁态 = 真·存活证明**，无 PID 复用误判。
- **锁文件内容 = 真解释器 PID + 启动时刻**（不是 run.bat 里 `$p.Id` 那个 cmd wrapper 的 PID）。`stop.bat` **先杀锁内这个 PID**（§2.2 job 连坐整树），再 `taskkill /T` 收 wrapper。理由见 §2.2 末：这是唯一能补上 E3「venv 启动器层不被 job 连坐」的手段，**必需项，不是可选加固**。
- 抢到锁才写 `logs\voice-code.pid`；抢不到 → 打印持锁证据 + 可疑 PID → `exit 3`（拒绝双开，不静默竞态）。
- 多入口（run.bat / 人手工 `python main.py`）共用同一把锁 ⇒ 不可能有两个实例。

### 2.2 Job Object 连坐（"杀父必杀整树"）
- `CreateJobObjectW` + `SetInformationJobObject(JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE)` + `AssignProcessToJobObject(自身)`，句柄自持。
- `opencode serve`（serve.py:53-57 `create_subprocess_exec`）与 winTTS PowerShell（tts.py:310-316 `Popen` + `_NO_WINDOW`）都是它的**直接子进程**，自动继承 job；Bun 内部 spawn 的工具进程是孙子，也在内。句柄亡 = 整树亡，**对 `/F` 强杀同样成立**。E4/E6 那类「子活着父死了」在结构上不再可能。
- **M11 控制台与此无冲突，且是加分项**：它是 main.py 内的 asyncio task，**不是进程** → 不涉及 Assign、不进清理面、`--probe/--sweep` 不用认它。
- ⚠️ 三条边界：
  1. **不被 job 覆盖的一层**：conda 版 venv 启动器（E3 的第一层 python）是第二层的**父**，job 由第二层建 → 只杀第一层，第二层 + serve + powershell 全活。→ 由 §2.1「锁内真 PID」补。
  2. **嵌套 job**：Win10 19045 支持 nested，但若外层宿主（agent 的 bash 工具）不允许 nesting，`Assign` 返 `ERROR_NOT_SUPPORTED` → 降级（stop 逐个 terminate）并**必须打 `[m10] job=UNSUPPORTED`**，`--probe` 退出码区分。否则"100%"静默退化成假保证。
  3. 本设计主动放弃"防被会话清理误杀"。将来若要常驻，需显式 `CREATE_BREAKAWAY_FROM_JOB` 并另开设计。

### 2.3 sweep 兜底 + kill 前过滤
- 锚定顺序：① `Win32_Process.ExecutablePath` 以 `D:\work\voice-code\` 开头 → ② 命令行含 `main.py` 或 `tools\oc2` → ③ 锁内真 PID + pidfile + job。
- **锚①的失效边界要写死**：E3 的第二层镜像在 `F:\anaconda3` → ① 不命中；人手 `python main.py`（相对路径）→ ② 也可能不命中。所以 ③ 是主力，①② 只是兜底。
- 每条命中**先打印 PID/Name/CommandLine 再 kill**；锁/pidfile 里的 PID 若 ①② 都不命中 → **拒绝 kill 并报告**（防 PID 复用误杀无关 node/anaconda 进程）。
- 误伤边界：opencode 自身镜像在 `F:\npm-global`、`G:\nodejs`（非 ①、无 ② 锚）；用户自己的 Chrome（含 bilibili 窗口）与 playwright-profile 都不在任何锚内。
- `run.bat` 起前 / `stop.bat` 杀后统一调 `main.py --sweep --expect-clean`：残留数 ≠ 0 → 非 0 退出并列出。
- `--probe`/`--sweep` 在**根 main.py 早分流**，早于 import orchestrator（探活不付 torch/sherpa 的导入成本）。

### 2.4 端口卫生（v1 完全缺失，本节新增）
- 正常退出必须优雅关：`_cleanup`（orchestrator/main.py:56-61）里 `srv.close()` + `await srv.wait_closed()` → 绝大多数情况不留 TIME_WAIT。
- 启动失败分形态：**有 LISTEN 占用** → `exit 4` + 打印占用 PID（`Get-NetTCPConnection -LocalPort` 的 OwningProcess，与 E7 同一套判据）；**只有 TIME_WAIT（OwningProcess=0）** → 退避重试 5×1s，仍失败才 exit 4。**禁止无脑重试、禁止自动顺延端口**（静默换端口 = 客户端连到不存在的服务，还以为助手挂了；与 §2.3"让没清干净变成响的错误"同源）。
- **禁止设 `reuse_address`/`SO_REUSEADDR`**（E11）。可选加固（本期不做，列 P4）：win32 下自建 socket 置 `SO_EXCLUSIVEADDRUSE` 经 `sock=` 传入（serve() 的 kwargs 通道，websockets\server.py:634-644），约 6 行。
- 逃生阀：`VOICECODE_CONSOLE_PORT=0` → 临时端口，实际值取 `srv.sockets[0].getsockname()[1]` 并写 `logs\voice-code.console.json`（沿用仓库既有先例：端口从运行时读、不硬编码，serve.py:59-60）。

## 3. M11 本地 WebSocket 文本通道

### 3.1 端口与形态
- 绑 `127.0.0.1:8765`（`VOICECODE_CONSOLE_PORT` 覆盖），启动第一件事断言 `port != 4096`（E7）。只绑回环、无鉴权（本机开发工具；绑 0.0.0.0 属未来产品化，另开设计）。
- **不写 `process_request`**：非升级请求由库默认回 426（E9），"HTTP 本地端口"这半边零代码兑现。
- 生命周期：main.py 内 asyncio task（三条理由见 §2.2/§0：独立进程 = 再造一条 sweep 抓不到的形态；同 loop ⇒ 出流可同步 broadcast 免跨线程 marshalling；不新增进程面）。
- **早绑**：在 TTS/ASR/KWS 装配**之前**绑端口——`tts.ready.wait(300)`（orchestrator/main.py:30）最坏等 5 分钟，端口冲突必须 1 秒内暴露。代价：早绑期 `orch` 还没 bind（main.py:27）→ 用 `ready` 标志，未就绪时对 `ask` 回 `{"t":"err","code":"not_ready"}`。**不得**依赖 `Orchestrator._pre` 缓冲（core.py:64-65），否则 t=0 发的问题会在 t=+5min 突然自己执行。
- 必须自己 print 一行 `[m11] console ws://127.0.0.1:<port>`：库的 `websockets.server` logger 无配置不会输出（websockets\server.py:259-261），run.bat 后台跑时否则没人知道端口。

### 3.2 帧协议（JSON 文本帧；未知字段忽略；只增不改语义，破坏性变更才升 `v`）
入 4 种：

| 帧 | 语义 | 复用的既有通道 |
|---|---|---|
| `{"t":"ask","text":"…"}` | **第一个能力**：送 oc2 一问 | §3.3 `TextIn` |
| `{"t":"stop"}` | 打断当前播报 | `_barge_in("")`（core.py:191-201） |
| `{"t":"perm","decision":"once\|reject"}` | 代答权限问句 | `_answer_perm` 通道（core.py:203-210），decision 直给、不经猜词 |
| `{"t":"ping"}` | 探活 → `pong` | — |

出 6 种：`hello`（连接即发 `{v:1,state,ready,port}`，版本协商 + 状态快照）、`state`（每次 `_go` 转移）、**`ev`（泛化镜像 `{"t":"ev","kind":"OcText","d":{…}}`，一个帧型覆盖 OcText/OcTool/OcPermission/OcTurnDone/OcLink/AsrText/KwsHit/TTS 全部事件类，types.py:23-60 → 将来新增事件类**零协议改动**）**、`speak`（真正进口播的句子，与 delta 区分）、`note`/`err`（协议级提示与错误）、`pong`。

**"收发任何文本帧"的兜底规则**（这就是"任意文本帧"的语义边界）：任何不属于上述 4 种的文本帧——**含非 JSON 裸文本、JSON 但 `t` 未知或缺失**——一律当 `ask`（text 取 `text` 字段或整帧原文），并回 `{"t":"note","code":"unknown_frame_as_ask"}`；**不断开、不抛**（对齐 core.py:100-103"dispatch 永不崩"）。于是"未来扩展"的方式是以后多认一个 `t`，而不是现在留空洞——v1 的 `raw` 帧因此删除（它的语义就是这条兜底）。
客户端契约（必须写进文档）：**见未知 `t` 必须忽略而非报错**，这是协议以后能长个子的唯一前提。
库限额写死默认值，防实现时乱调：`max_size=1MiB`、`max_queue=16`、`write_limit=32KiB`、`open_timeout=10`、`ping_interval/ping_timeout=20/20`（websockets\asyncio\server.py:512-519）。本期不自建队列。

### 3.3 注入：`TextIn` 单事件（原子，不新增旁路）
否掉的三个候选：
- **(c) console 直接 `oc.send`**：硬旁路，四条硬伤——`client.send` 同 session 未收场再 send 直接 `RuntimeError`（client.py:57-58）；拿不到句级播报链（core.py:122-126）；权限/退出/barge-in 全失效（core.py:127-134、173-174）；`sid` 归属打架（core.py:151-152、176）。违背"主流程不变、不新增旁路"。
- **(b) `KwsHit`+`AsrText` 忍 3s 静默**：除 3–3.5s 延迟（core.py:117 + main.py:51 的 2Hz tick），两个硬伤——打字内容会被 `_is_echo` 静默吞掉（core.py:112-114，子串双向包含判定，粘回助手刚说的话就丢）；3s 窗口内麦克风开着（core.py:79），环境人声会 `buf += text`（core.py:115-117）把打字和噪声混成一轮。
- **(a) `KwsHit`+`AsrText`+`TurnNow` 三连 post**：方向对但三次 `post` 是三个独立 `call_soon`（core.py:67）**不原子**，麦克风线程的事件能插在中间；且 `KwsHit` 在 IDLE 会念"在呢。"（core.py:107-110），每次打字都念一句。

**采用 (a′)：一个新事件类 + 一个分支，一次 post 完成**
```python
@dataclass(frozen=True)
class TextIn:            # core.py，与 IDLE/COLLECT 常量同处；console 侧 import
    text: str
    src: str = "console"
```
`_handle` 末尾追加一个 `elif`（接在 core.py:105-138 的类名字符串链上）：IDLE → `_go(COLLECT)`（不念 ack）；PERM → `await self._answer_perm(ev.text)`；RUNNING → `self._barge_in(ev.text)`；COLLECT → `self.buf = (self.buf+"\n"+ev.text) if self.buf else ev.text` 然后 `await self._collect_fire()`。
为什么最省：`_collect_fire` **自带全部护栏**——state/buf 判空（core.py:141）、busy 重试（143-147）、懒建 sid（151-152）、置 `_turn_fut`/`spoken_len`/`_go(RUNNING)`/桥接 `_await_turn`（157-160），一行都不用重写；同时绕开 `strip_wake`（core.py:112）与 `_is_echo`（113）这两个"为语音设计"的清洗，打字内容原样进 oc2；单事件 = 原子，无插入竞态。依赖方向仍是 console→orchestrator（`from orchestrator.core import TextIn`，`orchestrator/__init__.py` 顺手导出），**core 不 import console**，与 core.py:28-42/106 的"按类名字符串分派、零耦合"一致。
**同时删掉 v1 的"asr 判空 2 行"**：生产路径 asr 必绑（main.py:22/27），测试侧照 test_m5_orch.py:69/103-105 既有套路塞 2 行 fake 即可。给生产代码加 `if self.asr` 只会把真正的装配 bug 变成静默。

**已接受的行为（回归风险，需你点头，见 §6 P3）**：
- R1 打字轮可被真人说话 barge-in 腰斩（`_go(COLLECT)`→VAD 开→`AsrText`→`_barge_in`+`oc.interrupt`，core.py:118-119/191-201）。这是"不分模式/全双工"的**必然推论**，不是 bug；要免疫就等于开模式，已被否。
- R2 回采去重不受影响（`_recent` 照常记，core.py:83）。
- R3 busy 态打字**不得覆盖**已有语音 buf → 必须 `+= "\n"+text` 而非 `=`（否则未成轮的半句被丢）。列为 A10。
- R4 PERM/RUNNING 态打字靠上面分支显式路由，否则静默无响应。
- R5 新分支是 `elif` 追加，不动 core.py:107-138 任何现有分支 → A5 回归应零改动通过。

### 3.4 出流：`tap` 回调 + 单一 broadcast 路径
- 否掉"post 装饰器包装"：只看到**入队前**的事件，看不到 state 转移与 speak；且 post 从麦克风/ASR/KWS/TTS 各线程调入（core.py:63-67）→ 包装体在**任意线程**执行，还得 `call_soon_threadsafe`；更糟的是把"事件到达"当"事件已处理"，客户端会看到 `OcTurnDone` 早于 state 回 COLLECT，**因果顺序反了**（钉成 A9）。
- 否掉"在 `_speak`/`_log` 里直塞 console 调用"：core 反向 import console，破坏解耦。
- **采用 tap**：`__init__` 加 `self.tap = None`（1 行）+ `_tap(obj)` 吞异常帮助函数（3 行，照抄 tts.py:304-308 `_emit` 写法）+ 三个调用点各 1 行：`run()` 出队后（core.py:96-99）、`_go()`（75-78）、`_speak()`（81-84）。**共约 7 行**，全在 loop 线程内（run/_handle/tick 都是 loop task）→ 契约写死"在 orchestrator loop 线程被同步调用，不得阻塞、不得抛"。
- tap 传**已构造好的 dict**，core 不 import json、不认识 console；序列化在 console 侧做**一次**，N 个客户端共享同一 str。多客户端广播放 console server 层（它持有 `srv.connections`，只含 OPEN 连接的 set property，websockets\server.py:274-288），core 只调一次 tap → "任一客户端发 ask 全员看到同一条流"是广播的自然结果，零额外代码。
- 四条禁令：① `broadcast` 必须在 loop 线程调（它直连 `transport.write`，connection.py:1236-1239）；若将来从别的线程 tap，必须换成 `loop.call_soon_threadsafe`。② **定向帧也走 `broadcast([ws], s)`**，保持单一路径，不混用 `await ws.send()`——因为 broadcast 会静默跳过 `send_in_progress` 的连接（E10），本期纯 str 发送不分片所以无风险，但要防后人拿生成器发大文本。③ 不在 tap 里加自建队列（broadcast 无背压，靠 ping/write_limit 收尸）。④ `ConnectionClosed` 只在 handler 的 `async for` 退出时出现，捕获即丢连接；tap 路径不会抛。

### 3.5 本期不做网页
本端口不 serve 任何 HTML/静态资源。将来若做 web UI（M12）：单端口复用与 `Upgrade` 判据已冒烟实测通过（v1 的 ws_smoke 结论），届时的代价是纯 UI 工作、**无协议风险**；真要同端口发页面才需要 `process_request`，代价是 `MAX_BODY_SIZE=1MiB` 且库注释明说不是为传文件设计（http11.py:51-53）、要自己糊 mime/缓存/Range、并把端口拖进 auth/CORS/静态目录这些产品化议题。设计令牌实测清单已移出至 `docs/0926工作/m12-console-ui-tokens.md`。

## 4. 业务代码行数估计（含上限；HTML 全删）

| 文件 | 动作 | 估计 | 上限 |
|---|---|---|---|
| `src/lifecycle/__init__.py` | 新 | 2 | 5 |
| `src/lifecycle/procguard.py` | 新（锁含真 PID + job + probe 证据） | 80 | 100 |
| `src/lifecycle/cli.py` | 新（`--probe`/`--sweep`） | 50 | 65 |
| `src/console/__init__.py` | 新 | 2 | 5 |
| `src/console/server.py` | 新（serve + 帧分派 + 广播，**无 HTML/process_request**） | 65 | 85 |
| `src/console/frames.py` | 新（事件 dict→帧 str，纯函数，可免 socket 单测） | 25 | 35 |
| `src/orchestrator/core.py` | 改（TextIn 4 + 分支 10 + tap 7） | 218 → 239 | 245 |
| `src/orchestrator/__init__.py` | 改（导出 TextIn） | 3 → 4 | 5 |
| `src/orchestrator/main.py` | 改（早绑 server + tap 装配 + `_cleanup` 关 server） | 61 → 84 | 95 |
| `main.py`（根 shim） | 改（`--probe`/`--sweep` 早分流） | 7 → 15 | 18 |
| `run.bat` / `stop.bat` | 改（换锚 + 先杀锁内真 PID + 起后断言 + 打印 ws 地址） | 19→34 / 6→18 | 各 ≤45 |
| `tests/test_m10_procguard.py` | 新 | 75 | 90 |
| `tests/test_m11_console.py` | 新（A4/A6′–A10） | 90 | 115 |
| `human-test/m11_t8_ws-console.py` | 新（替代 H4/H5，非 py 业务） | 60 | 80 |

小计：**py 业务 +276**（上限 +358）；tests +165；human-test +60；**非 py 的 200 行 HTML 归零**。删 `scripts/oc2_live.py` **−271** → **py 业务净 +5 行**。`src/` 实测基线 **1889 → 约 2165**（上限约 2247），红线 5000 用掉 43%（上限 45%）。
记账：新增里 ~132 行是"清理保证"（用户硬要求）、~92 行是 WS 通道本体、~21 行是 core 最小接入；被删的 oc2_live 用 271 行 + 一套 jsonl 文件面 + 一个计划任务，提供了远弱于此的能力。

## 5. 验收

自动化（pytest，全 mock，不碰真设备、**不开浏览器**）：
- A1 抢锁：一个赢、一个 `exit 3`；赢家被 `taskkill /F` 后锁可再抢，且锁内 PID 与实际持锁者一致。
- A2 job 连坐：起"spawn sleep 子进程"的 python → `kill /F` 父 → WMI 复查子已消失。A2b job 降级：mock `AssignProcessToJobObject` 返 `ERROR_NOT_SUPPORTED` → 断言 `[m10] job=UNSUPPORTED` 且 `--probe` 退出码区分。
- A3 sweep 锚：相对路径命令行的假目标 → 命中；`F:\anaconda3\python.exe` 无关进程 → **不命中**。
- A4 **`TextIn` 单事件**走完 IDLE→COLLECT→RUNNING 且 `speak ≥ 1`、**不等 3s**。
- A5 回归：`test_m5_orch`/`test_m7_tts` 全绿（core 只加 TextIn/tap，不动现有分支）。
- A6′ **`GET /` 返回 426** 且正文含 "You cannot access a WebSocket server directly"（断言我们没去覆盖库默认行为，反向钉住 v1 那个坑）；同端口 WS 握手 101 + 双向收发。
- A7 帧协议：`ask`→断言 orch 收到 `TextIn`；tap→断言 `ev/state/speak` 广播；未知字段不炸；`ping`→`pong`；**非 JSON 裸文本 → 按 ask 兜底 + 回 `note`**。
- A8a 端口被 LISTEN 占用 → `exit 4` 且日志含占用 PID；A8b 只剩 TIME_WAIT → 退避重试后成功。
- A9 tap 因果顺序：`ev(OcTurnDone)` 必须先于 `state(→COLLECT)`。
- A10 busy 态收到 `TextIn` 时不吞已有语音 buf（对应 R3）。

人工（`human-test/`，真机 + 真人耳/眼）：
- **"用浏览器测试"整体作废**：本期无网页，浏览器无从测起；AGENTS.md 的 Playwright 窗口规则本期**完全不触发**。
- **H4′ 替代品 `human-test\m11_t8_ws-console.py`**：用 `websockets.asyncio.client.connect` 连 `ws://127.0.0.1:8765`，stdin 一行一帧直发（裸文本即 ask；可手打 `{"t":"stop"}` 测打断、`{"t":"perm","decision":"once"}` 测代答、故意发非 JSON 验兜底），同时逐行打印收到的每个帧（含 `ev` 的 kind）。验收点：人耳听到口播、眼看帧流因果正确、**并行喊「小码小码」麦克风路径不受影响**（原 H4 语义全保留，载体从浏览器换成脚本）。命名遵循 human-test/README.md:4-5（不得匹配 `test_*.py`）+ pytest.ini:4（`norecursedirs = human-test`）。
- H1 `run.bat` → **故意跳过 stop.bat** 再 `run.bat` → 旧树 0 残留、新实例 UP、无第二窗口。
- H2 分别「只杀中间层」：venv 父 python、opencode serve、wintts powershell → 不留孤儿，且 run.bat 再起能 100% 收干净；**补一条：只杀 venv 启动器层（第一层）→ 断言不留孤儿**（对应 §2.2 那个 job 覆盖不到的真实漏洞）。
- H3 **重启机器** → 不再有任何自动启动进程，且 `schtasks /query /tn voice-oc2-live` 返回"找不到"（本次回退的核心验收）。
- 运行命令：`.\.venv\Scripts\python.exe -X utf8 human-test\m11_t8_ws-console.py`

## 6. 已定与待定

已定（用户拍板）：不分模式；控制台常驻主进程内、单端口 WS、全双工、任意文本帧、异步；`ask` 只是第一个能力；端口 8765 避开 4096、只绑 127.0.0.1、无鉴权；计划任务路线整体废弃；**本期不做网页**。

待定（需你一句话，括号内是我的推荐默认值）：
- **P1 依赖声明落点**：根目录实测**没有** `requirements.txt`（AGENTS.md 旧文提到的那个文件不存在）。推荐**两者都做**：新建 `requirements.txt` 写 `websockets>=15,<18`，同时在 AGENTS.md 新增一行 pip 纪律（本机 `pip config list` 有 `global.target=F:\python-packages` 且不在 sys.path，普通 install 装了等于没装，必须 `python -m pip install X --target .venv\Lib\site-packages`；pypi 直连不通走 `mirrors.aliyun.com/pypi/simple/`）。本轮 `websockets==17.1` 已按此装好并 import 验证。
- **P2 端口绑不上的语义**：推荐 **fail-loud `exit 4` + 打印占用 PID**，保留 `VOICECODE_CONSOLE_PORT=0` 作人工逃生阀；不采纳"自动顺延端口"（理由见 §2.4）。
- **P3 打字轮与麦克风的相互作用**：推荐**两条都接受**——① 打字发起的轮次可被环境人声打断（R1）；② 打字时不念"在呢。"。两者都是"不分模式/全双工"的直接推论，代码为零或为负。若要打字轮免疫打断，等于开模式，需要你显式改口径。
- P4（可选，不进本期必做）：`SO_EXCLUSIVEADDRUSE` 加固，约 6 行。

## 7. 实现顺序（等你说开工）

1. `src/lifecycle/procguard.py` + `cli.py`（锁含真 PID + job + `--probe`/`--sweep`），**先于 WS**：端口卫生的前提是进程卫生。
2. `core.py`：`TextIn` + 一个 `elif` 分支 + `tap`；`orchestrator/__init__.py` 导出。
3. `src/console/frames.py` + `server.py`（早绑、426 默认、兜底、广播、`[m11]` 打印）；`orchestrator/main.py` 装配 + `_cleanup` 优雅关。
4. 根 `main.py` 早分流；`run.bat`/`stop.bat` 换锚 + 先杀锁内真 PID + 起后断言 + 打印 ws 地址；AGENTS.md **新增**仓库纪律节（见 §1、§6 P1）。
5. 删 `scripts/oc2_live.py` 与其 jsonl 文件面（任务与进程树已清完）。
6. A1–A10 补齐 → `pytest -q` 全绿 → 交人工 H1–H4′ → 回填 §9。

## 8. v1 → v2 事实勘误

- v1 记 `oc2_live.py` 269 行 → 实测 **271 行**，且**文件仍在磁盘**（v1 把"任务/进程树已清"写成了"删"已完成）。
- v1 三处「勘误 AGENTS.md 仓库纪律第 3 条」→ 现 AGENTS.md 全文 7 行、**无该节**，性质改为**新增**。
- v1 记 `src/` 基线 1851 行 → 实测 **1889 行**。
- v1 §3.1「单端口双用：GET / 返回网页」+ 附录 A 设计令牌 + `console.html` 200 行预算 + H5 样式对照 + P2 raw 面板 → **全部撤出本期**（用户否认要求过 web）；令牌清单移至 `m12-console-ui-tokens.md`。
- v1 的注入方案 `KwsHit + AsrText + TurnNow` 三连 post → 改 `TextIn` 单事件（三连 post 不原子、会念"在呢"、且打字内容可能被 `_is_echo` 静默吞，core.py:112-114）。
- v1 的"asr 判空 2 行" → 撤（生产必绑，测试用 fake），避免把装配 bug 变静默。
- v1 完全缺端口卫生 → 新增 §2.4。
- 文件名 `m10-proc-hygiene-textin-design.md` 里的 "textin" 已成历史名（内容已改为 TextIn 事件 + WS 通道），暂不改名以免动目录，记此一行。

## 9. 实现勘误（2026-09-26 编码后回填）

### 9.1 实际行数 vs §4 估计

| 文件 | 估计/上限 | 实际 | 判定 |
|---|---|---|---|
| `src/lifecycle/procguard.py` | 80 / 100 | **140** | **超上限，1.75× 估计 → 需解释，待裁决** |
| `src/lifecycle/cli.py` | 50 / 65 | **97** | **超上限，1.94× → 需解释，待裁决** |
| `src/console/server.py` | 65 / 85 | **105** | **超上限，1.62× → 需解释，待裁决** |
| `src/console/frames.py` | 25 / 35 | 32 | 内 |
| `src/lifecycle/__init__.py` + `src/console/__init__.py` | 4 / 10 | 8 | 内 |
| `src/orchestrator/core.py` | 239 / 245 | 244 | 内（+26） |
| `src/orchestrator/main.py` | 84 / 95 | 83 | 内 |
| `src/orchestrator/__init__.py` | 4 / 5 | 3 | 内 |
| `main.py`（根 shim） | 15 / 18 | 17 | 内 |
| `run.bat` / `stop.bat` | 34 / 18（上限各 45） | 18 / 7 | **低于估计**：清扫逻辑整体下沉到 `--sweep`，bat 只剩调用 |
| `tests/test_m10_procguard.py` | 75 / 90 | 99 | 测试，非业务代码 |
| `tests/test_m11_console.py` | 90 / 115 | 180 | 测试，非业务代码 |

`src/` 合计（py）：**1889 → 2287**（估 2165，红线 5000，用掉 45.7%）。删 `scripts/oc2_live.py` −271 → 本轮净 +398（其中 +279 是测试）。

**三处超 1.5× 的解释（按纪律只解释、不自行处理，等你裁决保留/删除/重设计）**：
1. `procguard.py` 140：① `SetInformationJobObject` 实测**必须**用 class 9 扩展结构（class 2 + `0x2000` 直接 `ERROR_INVALID_PARAMETER(87)`），于是多出 `_IoCounters` + `_ExtendedLimits` 两个 ctypes 结构体 ≈ +22 行；② `Affinity` 在 winnt.h 里是 `ULONG_PTR` 不是 `ULONG`（按 ULONG 算 sizeof=56 → `ERROR_BAD_LENGTH(24)`）≈ +2 行；③ x64 上必须显式声明 8 条 `restype/argtypes`，否则 HANDLE 被截断成 32 位 ≈ +12 行；④ 锁位偏移 `_LOCK_AT` 与 seek 逻辑（见 ②'）≈ +6 行。全是"不写就错"的行，没有设计外的功能。
2. `cli.py` 97：① 锚② 补了"必须与本仓库有关（cwd/命令行含仓库路径）"的判据——**测试逼出来的真 bug**：原写法会把别的项目里也叫 `main.py` 的 python 进程杀掉；② `--probe` 的 job 降级告警、③ 锁空闲时拒杀陌生 PID、④ `--expect-clean` 复扫，各 5–10 行。
3. `server.py` 105：① `_dispatch` 的兜底比预估细（显式 `ask` 不做"整帧兜底"、`perm` 校验当前态、空文本回 `err`）；② `port=0` 与"未指定"必须区分（预估里没考虑临时端口的三态）；③ `BindError` 与 TIME_WAIT 退避重试。

### 9.2 编码期实测新知（原设计未覆盖，已回写代码）

- **`msvcrt.locking` 锁 offset 0 会让别的进程读不了锁文件**：`Path.read_text()` 从 0 开始读 → 撞上字节锁 → `PermissionError(13)`。改为**锁位放 4096、元数据写 0**，才能"边持有边读 holder 的 pid/job"。设计 §2.1 未预见。
- **job 成员资格在 CreateProcess 时定**：测试第一版"先 spawn 孙子、后 attach_job"→ 孙子逃过连坐、断言失败。→ 已把"`attach_job()` 必须先于任何 spawn"写进 AGENTS.md 与 `orchestrator/main.py` 的第一行逻辑。
- **nested job 本机可用**：opencode 的 bash 工具确实把我们放在某个 job 里（`IsProcessInJob=True`），但 `AssignProcessToJobObject` 到新建 job 仍成功 → §2.2 边界1 的降级路径在本机没被触发（代码仍保留 UNSUPPORTED 分支与告警）。
- **`ConsoleServer(port=0)`**：0 = "要临时端口"，不能用 `port or default` 的 falsy 判断混同（第一版就踩了，导致测试里 `port=0` 实际去抢 8765）。
- **E9 已在真机复现**：`GET /` → **426**，正文含 "You cannot access a WebSocket server directly"；同端口 WS 握手/收发/tap 广播全通。

### 9.3 与设计偏离项

- 注入事件类最终命名 `TextIn`（与 §3.3 一致）；未新增 `TurnNow`（§3.3 已改口，无偏离）。
- 未做 `{"t":"raw"}` 帧（§3.2 已删，由"未知帧按 ask 兜底 + note"取代）——实现与之一致。
- `stop.bat` 从"powershell 正则扫 + taskkill"改为**只调 `main.py --sweep --expect-clean`**（清扫逻辑单一权威实现，避免两处规则漂移）。
- 未做 P4（`SO_EXCLUSIVEADDRUSE`），按设计留待裁决。

### 9.4 测试结果

- `pytest -q`：**99 passed**（含新增 M10 4 例 + M11 7 例；A1/A2/A2b/A3/A4/A6′/A7/A9/A10 + 既有 M1–M7 回归全绿）。
- 未跑（需真机/真人）：A8a/A8b（端口占用形态，已实现但只在临时端口路径上验证过 bind 成功）、H1–H4′（run.bat 起停、只杀中间层、重启机器无自启、WS 脚本口播）。

### 9.5 2026-09-26 真机日志复盘：三件事必须分开归因（防止误修）

`run.bat` 起来跑了一轮，`logs\voice-code.log` 观察到三个现象，**归因各不相同，只有两个该动代码**：

1. **播报期自听 / 自问自答 = 硬件缺位，禁止改代码**。日志里 `10:53:11 <AsrText> "会让你见识"` → `10:53:14 COLLECT->RUNNING`，是助手外放被自家麦克风收回去续了一轮。本机**没有带硬件 AEC 的麦**（未到货），`_is_echo`（core.py:86-88，`_recent` 归一化子串比对）只是缓解不是消除。此行为在 m5 设计里早已作为**假设声明**接受（m5-orchestrator-design.md §6「硬件 AEC 在场，播报期自听误打断为已知可接受项（观察计数，不设防护）」）。→ 本期与后续都**不得**为它新增防护逻辑；已同步写进 AGENTS.md「播报期自听」节。
2. **残句不播 = 真缺陷（T3）**。`校准差 12->118（不重播）`：118 字的答案只送了 12 字进 TTS。`split_sentences` 硬断只认 。/\n、软断要 ≥40 字，模型爱用逗号 → delta 攒的残句在 `OcTurnDone` 时从不 flush（core.py:185-188 只 log 不补播）。与 AEC 无关，独立成立。
3. **VoxCPM 慢 = 配置默认值错（已改）**。run.bat 不设 `VOICECODE_TTS_BACKEND` → 代码默认 voxcpm → 单句合成 24.6s/28.3s/30.5s/**167.1s**/195.5s，队列必然积压，于是"退下"之后 IDLE 了喇叭还在出声（`10:45:39 RUNNING->IDLE` → `10:49:21` 才 SpeakFinish）。已把 `orchestrator/main.py:38` 默认改 `wintts`（`TtsConfig` 库级默认仍留 voxcpm，供 `scripts/m7_tts_say.py` 等试听脚本用）。
   - 另有一处独立真缺陷（T4）：退下那轮 `<OcTurnDone> outcome=succeeded len=53` 与上一轮一字不差 → `_end_turn` 的 pending_exit 兜底播的是**上一条答案**而不是道别语，说明 M6 侧 TurnDone 的终稿文本取错了条目。

> 记录这条的目的：现象 1 与现象 2 在日志里挨着出现，极易被误读成"echo 去重不够 → 加防护"。**方向是反的**——是"该播的没播 → 没进 `_recent` → 去重无从命中"。修 2 会顺带减少 1 的表观频次，但 1 的根因仍是硬件，不得为此加任何逻辑。
