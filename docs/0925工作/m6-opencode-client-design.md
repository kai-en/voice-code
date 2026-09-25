# M6 opencode_client 设计（v2 唯一目标，一期最小面）2026-09-25

依据：deepthink 两轮调研（v2.0.16 源码+官方文档双源）+ 本机隔离实测（D:\Temp\opencode\oc2）。
上游约束：docs/overall-goals.md（v1=开发工具，oc2=项目支持进程）；本模块只服务语音链路，不替代 v1。

## 0. 进程与隔离架构（已实测钉死）

- `npm install @opencode/cli@2.0.16 --prefix tools/oc2`：局部 node_modules，不碰全局 v1；用 `.bin\opencode2`（厂商共存别名）。
- 隔离 env（spawn 时注入）：`XDG_{DATA,CONFIG,STATE,CACHE}_HOME → tools/oc2-home\*`（v2 全新建库，实测 `debug paths` 全分离、v1 数据目录 0 变更）；模型 key 存于该 config 内，独立 login/env，与开发 v1 互不可见。
- 生命周期：`opencode2 serve --stdio` → stdout 首行 `{"url":...}`（端口以 URL 为准）；`OPENCODE_PASSWORD` 自生成随机密码，Basic `opencode:<pw>`（无 auth→401 实测）；**关 stdin=优雅退出(0)**，不 kill。
- 版本校验：`GET /api/info` → version 必须 `2.`，记入日志。

## 1. 一期范围（串行最小面）与明确砍掉项

一期只做：spawn/就绪/关停 → 单 session → **串行** `send(text)→事件流→TurnDone` → barge-in `interrupt(resume=false)` → 权限闭环最小集（asked→播报→once/reject）。
砍掉（列二期）：delivery=steer/queue 多路复用、session.log?after=seq 补洞（一期断线=重订阅+`GET message` 重拉，实测不够再加）、form/question 通道、generate 端点（M8 再用）、reasoning 播报、v2 插件（属 M8）、service 发现模式、多 session 并行。

## 2. 接口契约（src/opencode_client/）

```python
# types.py: OcText(session_id, text, final)  OcTool(status)  OcPermission(request_id, action, message)
#           OcTurnDone(session_id, outcome, text, error)  OcLink(state)
# client.py: OpencodeClient.attach(url, password, directory, on_event)
#            session_new(title)->str / send(sid, text)->Future[OcTurnDone]（串行：未回炉不受理下一次）
#            interrupt(sid) / reply_permission(sid, rid, decision) / close()
# serve.py:  ServeProcess.start(cfg)->url/password/pid；stop()=关 stdin
# 门面: start_opencode(cfg, on_event) 对齐 start_tts/start_asr 惯例
```

事件 allowlist（其余 type 静默忽略；`event.location.directory != 本 directory` 丢弃，**无 location 的事件保留、按 sessionID 过滤**——T-M6-2 实测 `session.usage.updated` 与 `session.execution.*` 不带 location）。
✅ **T-M6-2 已实测（v2.0.16，fixture=tests/fixtures/m6_v2016_*.jsonl）**，帧形=`data:` 单行 JSON `{id,created,type,location?,data,durable?{aggregateID,seq,version}}`：
`session.text.delta{assistantMessageID,ordinal,delta}`、`session.text.ended{...,text全量}`（校准）、
`session.execution.started / succeeded{sessionID} / failed / interrupted{reason:"user"}`→TurnDone（终稿 `GET message?type=assistant` 校准；idle 条目带 outcome）、
`session.step.*`/`session.usage.updated{cost,tokens}`/`session.inbox.enqueued|delivered`(delivery 默认 "steer")/`session.reasoning.*` 一期全部忽略（usage 仅在 TurnDone 顺带记 cost）。
心跳：SSE 注释行（15s 级），35s 无帧判死→重订阅+重拉兜底。
SSE 背压红线：读帧仅入本地队列即走（订阅端 4096 溢出会断流），处理独立 task。
实测延迟：prompt 受理→首个 text.delta ≈2.6s（qwen3.8-flash 云端）。
实测鉴权：SSE 与 REST 同样必须 Basic 头（不带→401）。

## 3. 业务代码行数预算（一期，含硬上限）

| 文件 | 预算 | 上限 |
|---|---|---|
| types.py | 40 | 50 |
| sse.py | 60 | 80 |
| rest.py | 85 | 100 |
| events.py | 100 | 125 |
| serve.py | 65 | 80 |
| client.py+__init__.py | 75 | 90 |
| **合计** | **~425** | **525** |

砍出范围不占预算：二期清单（§1）、崩溃自动拉起→M10、插件→M8。编码后按纪律回填实际行数与勘误。

## 4. 单测切分（CI 无 GPU/node，MockTransport+假流）

sse 解析（注释心跳/撕裂 data 行/坏 JSON）~5；events（delta 组句、ended 校准、execution→TurnDone、location 过滤、未知忽略）~8；rest（/api 路径+Basic、prompt 受理 200/409、interrupt、reply、401/404 映射）~7；serve（env/无窗口 spawn/JSON URL 解析/stdin 关停/仅记录 PID）~4；端到端假 v2 server（send→delta→succeeded；barge-in；permission 闭环）~4。合计 ~28 用例，假 server 复用给 M5 的 FakeOpencodeClient。

## 5. 人审实测（实现前/联调时）

- T-M6-0a 正式装 `tools/oc2`（npm 同实测命令）+ `opencode2 auth login` 或 env 配 key（独立于 v1）。
- T-M6-1 serve --stdio 手跑一遍 `/api/info`。
- T-M6-2 **`human-test/m6_capture_events.py` 抓包钉契约**（delta 频率、execution 顺序、location/durable 实际形状）→ 产物转成单测 fixture，**先于 events.py 编码**。
- T-M6-3 语音项目 opencode.jsonc：`permissions` 预 allow 工作目录边界（默认基线含 external_directory/.env ask，实测会卡回合）。
- T-M6-4 真实 prompt 端到端：首 delta 延迟、句级节奏喂 TTS、barge-in、asked→语音应答→继续。

## 5b. 勘误（2026-09-25 编码后）

- 实际 441 行 / 预算 425 / 上限 525：+16 主要在 events.py（translate 纯函数化+resync 兜底比草稿多分支）与 serve.py（ready 超时参数+失败回收路径）。无设计外新行为。
- **模型策略变更（用户拍板）**：不注入任何 key，用 v2 默认 opencode 免费池（OcConfig.model=None）。曾试过的 auth.json 复制/env `ALIBABA_TOKEN_PLAN_API_KEY` 注入两条路已撤销，代码与 tools/oc2-home 无凭据残留。
- 实测补充（v2.0.16 + 免费池）：session_new 不带 model；prompt→首个 delta ~3s；"只回复明白"指令被遵守（但结构断言不依赖听话度）；serve --stdio 关 stdin 退出码 0；e2e 见 scripts/m6_e2e.py PASS。
- 单测实际 26 用例（预算~28）+ 全量 65 绿；e2e 冒烟 PASS。T-M6-4 的 barge-in/权限部分留给 M5 联调。

## 6. 残余风险（分级）

需实测：事件词表细节（以抓包为准）；409/interrupt 行为；权限 ask 卡死兜底（N 秒无人答自动 reject+播报）。
可接受：2.0.x 快迭代（钉 2.0.16 + 关 auto-update + version 校验）；experimental 端点一期不依赖（wait/log 均不用）；断线丢事件（一期重拉兜底）；共库（隔离 home 后与 v1 根本不同库）。
硬伤：无。
