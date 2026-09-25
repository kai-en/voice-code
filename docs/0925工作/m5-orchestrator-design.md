# M5 orchestrator 设计 v2（全双工版）2026-09-25 —— 待人工审核

按用户 4 条决定重写 v1 设计：**①LLM 流式边出边按"句号/换行/结束"简单分句，首句完成即 TTS；②LLM 输出期 VAD/ASR 不停（全双工，硬件 AEC 保证，软件不做回声抑制），ASR 一有输出→立即停 TTS+interrupt LLM；③VAD 断句不即发，累计缓冲直到用户静默 3s 才整批发给 OC（不论长度）；④会话退出唯一通道 = opencode 插件注册的退出工具（LLM 主动调用），无结束词、无静默超时退出。**

## §0 结构变化（vs v1 设计）

- 删除：VAD 门控回声防护（全双工不需要）、KWS barge-in 哨兵（barge-in 由语音直通）、ASR 结束词表、T1 静默 120s 退出。
- 新增：**3s 收集定时器**；**PERM 态例外路由**（权限问句期间 AsrText→reply_permission 而非打断）；**退出工具监听**（M6 allowlist 需 +5 行透传 `session.tool.called`/`rpc.*`，记 M6 补丁）。
- 前置依赖（阻塞项）：v2 插件注册"模型可调用 tool"跑通（原 T-M6-9/M8 范畴，提前到本包）——插件为 ≤50 行 TS，独立交付物 `tools/oc2-home/plugins/voice-end.ts`，经 v2 config 加载。若 tool 注册 API 不通则本包退出通道重审。

## §1 状态机（4 态）

```
IDLE ──KwsHit──▶ COLLECT（ack 并行播，VAD 全开；sid=新会话懒建于首次 send）
COLLECT ──AsrText──▶ 入缓冲+重置 3s 计时（ack 期间来的话术同样收编：若 ack 未播完且用户在说话→tts.stop()，收编不中断 ack 语义）
COLLECT ──3s 静默且缓冲非空──▶ RUNNING：session_new?→send(全部文本)
RUNNING ──OcText.delta──▶ 简单分句(仅 。！？\n 或流结束)→首句即 tts.speak；后续句进 TtsEngine 队列
RUNNING ──AsrText──▶ 【barge-in 主通道】tts.stop()×2(0.4s 补刀) + interrupt(sid) → 该句入缓冲 → COLLECT
RUNNING ──TurnDone──▶ 尾句 flush+speak → 播完仍回 COLLECT（会话续用，免唤醒连续对话）
RUNNING ──OcPermission──▶ PERM：播"需要授权X，说允许或拒绝"；此态 AsrText→匹配 once/reject→reply→回 RUNNING；15s 无应答→reject
任意非IDLE ──退出工具被调用──▶ tts.stop + (执行未完则 interrupt) + bye 话术 → sid=None → IDLE
任意非IDLE ──KwsHit──▶ 视为重开：缓冲丢弃、执行 interrupt、sid=None → 走 COLLECT 新会话 ack
```

计时器只剩 3 个：3s 收集、15s 权限、30s TTS 假死对账（pending 清零）；另 1Hz watchdog check（E 类报警=播话术，fire-and-forget）。**没有回合总超时**——卡住由用户开口打断或退出工具收场。

## §2 线程模型（不变项）

单 asyncio loop + `post()`=call_soon_threadsafe 统一汇入串行 dispatch；M5→模块控制走各模块既定"M5 直调"路径。全双工后 set_active 只在 唤醒(True)/退出 IDLE(False) 两处调用，竞态窗口比 v1 更少。

## §3 与 M6 的两处接缝

1. **M6 补丁（+~8 行）**：events.py allowlist 放行 `session.tool.called`→新事件 `OcTool(sid, tool_id, name, status, input)`，M5 按 `name=="voice_end"`（插件注册名）判退出；同时保留 TurnDone 语义不变。补丁后 M6 单测 fixture 补 1 用例。
2. **插件 voice-end**：`Rpc/tool` 注册 + 模型描述"任务完成或用户要求结束时必须调用"；调用即 emit，M5 收到即走退出转移。**一期无 system prompt 注入通道问题**——退出完全由工具触发，工具 description 自带引导。

## §4 首响延迟预算

说完→3s 静默→send→免费池首 delta ~3s→首句(≤20字)合成 RTF0.35 ≈0.4-1.5s：典型 **说完到开播 ~6-8s**；barge-in 打断成本≈立即（stop 尾音 ≤1 短句，双 stop 缓解 tts.py:74 竞态）。

## §5 交付物与预算（业务代码）

| 文件 | 预算/上限 | 说明 |
|---|---|---|
| src/orchestrator/__init__.py | 4/6 | |
| src/orchestrator/textproc.py | 40/50 | 纯函数：sentence_split(仅。！？\n+结束)、ack 文案常量（词表砍掉大半） |
| src/orchestrator/core.py | 150/170 | 状态机+缓冲+3 计时器+权限映射（拒绝优先匹配保留） |
| src/orchestrator/main.py | 55/65 | 装配/回收同 v1 §3 |
| 根 main.py shim | 5/7 | |
| tools/oc2-home/plugins/voice-end.ts | ≤50(TS) | 插件交付物，独立于 Python 预算 |
| **Python 合计** | **254/300** | |

## §6 测试

单测 ~14（纯函数 4：分句/缓冲 3s 归并/权限映射/ack 收编；状态机 10：唤醒→采集→3s 发送→流式开播→**语音打断回 COLLECT**→续用免唤醒→退出工具→IDLE→再唤醒新会话；PERM 三路径；双 stop；重开）。Fake 四件套沿用 v1 方案，M6 假 client 复用。
人审 T-M5-0..4（真机全流程首版）：冒烟/孤儿检查 → 唤醒→"列出目录文件"→听流式→**直接开口打断**→新指令→"结束这次对话吧"(诱导模型调工具)→退出→再唤醒验证上下文已清。判据含：**3s 整批发**（说一句等 2s 再说第二句→两句一起送出）、权限闭环、尾音≤1 短句。假设声明：硬件 AEC 在场，播报期自听误打断为已知可接受项（观察计数，不设防护）。

## §7 风险

高1：v2 插件 tool 注册 API 未实测（阻塞退出通道，先行 spike 半天）。中2：全双工下自听误打断→计数观察，必要时"缓冲句须≥N 字才触发 barge-in"一行阈值；M6 补丁引入事件面变更。低2：卡住无总超时（用户可打断/退工具收场，接受）；退出依赖模型听话调工具（不准则记 M8 优化 system prompt）。

## §8 勘误占位

编码后回填行数核对、插件实测记录、T-M5-x 数据（3s 归并正确性、打断尾音、自激计数）。
