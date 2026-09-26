# 第1轮优化（2026-09-25 首次真机 run.bat 实测）

现象来自用户实测 + logs\voice-code.log 取证。本轮只记录，修复下轮动手（修复前不动 run/stop 脚本）。

## 问题1：log.bat 中文乱码
- 现象：查看日志全是乱码。
- 根因：python 以 `-X utf8` 写 UTF-8；log.bat 的 Get-Content 默认按 GBK 解码。
- 方案：log.bat 读取加 `-Encoding UTF8`（run.bat 里 echo 的 %date% 中文星期是 GBK 混入，顺手改成 ASCII 时间戳）。

## 问题2：没有详细日志
- 现象：日志只有 tqdm 进度条和 traceback，看不出状态机在干什么（唤醒/成轮/打断/权限/退出无轨迹），无法排障。
- 方案：core.py 加结构化事件日志（每事件/状态转移/超时一行：时间+态变化+事件摘要），走 print 进 voice-code.log；关键参数（buf 长度、spoken_len、deadline）带上。

## 问题3：打断+退出请求 → 死循环（根因已定位）
- 现象：TTS 反复播"上一个任务还在收尾，稍等"（日志刷 82 步进度条，82≈12字×6+10，正是 busy_text）。
- 根因（M5 设计缺陷，单测被手工 post OcTurnDone 掩盖）：
  M6 契约是 `send()` 返回 Future，OcTurnDone **不走 on_event**；
  M5 `_collect_fire` 存了 `_turn_fut` 但从不 await 它 → 回合结束时没人把 TurnDone 投进 `_q` →
  `_end_turn` 永不执行 → `_turn_fut` 永不清空 → 之后每 2s 触发 busy 护栏；
  且无 AEC 环境下 busy 语音被麦回采 → COLLECT buf 又被填 → 循环自激。
- 修复方案：`_collect_fire` 里 send 成功后 `create_task(self._await_turn(fut))`，把 Future 结果 post 回 `_q`；
  同时 COLLECT 对"与上次 TTS 播出文本相同/前缀"的 ASR 回采做去重（问题2的自激链一并观察）。
- 验证：新增单测——send 返回的 Future 完成后，队列必须收到 OcTurnDone（堵住测试掩盖路径）。

## 问题4：TTS 输出音量归一化到 -1dB
- 需求：每条合成音频按峰值归一到 -1dBFS（≈0.891），解决不同句响度忽大忽小。
- 方案：`tts.py` 播放前对样本做 peak normalize：`w *= 10**(-1/20) / max(peak, eps)`；
  峰低于阈值（≈-30dB）不放大（防把底噪抬起来），只做衰减或保持。归一化放 `_gen` 出口统一生效。

## 问题5：oc2 会话专用语音 agent
- 需求：给 opencode 会话固定用"语音助手"人设——回答尽量简短（会被 TTS 念出来）、禁用表格/markdown 排版。
- 方案：`tools/oc2-home/config/opencode/agent/voice.md`（v2 agent 定义：description + prompt 约束：
  口语化短句、一次 ≤3 句、无表格/列表/代码块格式、适合播报）；
  M5 `session_new` 改传 `agent="voice"`（M6 client 增加 agent 参数，session_create body 加字段）。
- 关联：模型若不听"简短"约束，二期再加 max_tokens/steps 限制。

## 关联待办
- 修复后重跑真机 T-M5-1/2（全流程+barge-in）与 T-M6.1 退出链。
- tts.py `_gen` cache 路径 reshape(-1) 已修（本轮启动前已合入，渠道数崩溃未复现）。


## 修复结果（2026-09-25 全部落地）

| # | 修复 | 位置 |
|---|---|---|
| 1 | log.bat 加 `-Encoding UTF8`；run.bat 起始标记改纯 ASCII（时间戳由 python 行给） | log.bat / run.bat |
| 2 | 结构化日志：每事件一行 `[m5 HH:MM:SS] 态 | <事件> 摘要`，含状态转移/speak/超时/错误 | orchestrator/core.py `_log/_brief` |
| 3 | `_await_turn` 把 send-Future 结果桥回队列（死循环根断）；TTS 回采去重 `_is_echo`（norm 比对，busy/ack/正文全防回采） | core.py + textproc.norm |
| 4 | 每条 TTS 输出峰值归一 -1dBFS（<-30dB 近静音不放大） | tts.py `normalize_peak` |
| 5 | 专用 agent：`config/oc2/agent/voice.md`（口语≤3句/禁表格/结束调 voice-end），部署至 oc2-home；`OcConfig.agent="voice"` → session body | config/oc2 + M6 types/rest/client + main.py |

- 回归用例 +4（85 passed）：`test_turn_fut_bridge_posts_end`（不手工 post 也必须回 COLLECT）、`test_busy_loop_broken_by_echo`（回采不进 buf）、normalize_peak、norm。
- 行数勘误：M5 实际 333/预算254（1.31 倍，未及 1.5 倍红线；超出部分=问题2日志与问题3去重的固有成本，无法砍）；tts.py 216→227（+normalize_peak 11 行）。
- 待用户重启 run.bat 后复测：唤醒→短答（应≤3句且更短）、打断、退出链、busy 是否绝迹；乱码/日志详略。

## 复现与验证（2026-09-25 20:22，获用户授权代跑 run.bat）

- **新发现#6（我的修复引入的回归）**：run.bat 里 echo 文案含嵌套括号 `(ascii; see ...)` 破坏 cmd 组重定向 `( ... ) > log` → 重启后日志既不覆盖也无输出，表现即用户所见"重启无效/狗屁不通"。已改为纯 `==== starting ====`，实测覆盖+落日志正常。
- **教训**：run.bat 的 echo 文本禁用括号/中文；重定向验证必须真跑。
- 真后端自测 `scripts/m5_loop_selftest.py`（第二 oc2 实例+注入事件）：
  `KwsHit→ack→COLLECT→send→(4s)voice-end called→告别 delta→TurnDone→speak→IDLE`，busy=0，VAD 终关。**死循环修复确认**。
- 副产品结论修正：**不钉 model 也能调 voice-end**（agent=voice + AGENTS 规则生效）——m61 期"必须钉模型"的结论是 XDG 错位 bug 时期的污染观察，二期可放宽。
- 生产服务现以新代码运行中（干净日志），等用户真 voice 实测 T-M5-1/2。
