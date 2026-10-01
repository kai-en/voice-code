# 需求：打断 LLM 处理必须过激活词（KWS 门控打断）

日期：2026-09-27 ｜ 状态：**已实现（2026-09-27，113 UT 全绿）** ｜ 关联：M5 编排器 `src/orchestrator/core.py`、M2 KWS `src/kws/kws_wake.py`

## 1. 背景与问题

现状（全双工一期口径，core.py 头注释）：只要不是 IDLE，ASR 一出句就按打断处理——
RUNNING 期任何 `AsrText` → `_barge_in()`（core.py:171-172, 257-267）= `tts.stop()` + `oc.interrupt(sid)`，
整条 LLM 回合直接作废。

直播场景下这太武断：oc2 一个任务（查数据、改代码、跑工具链）往往要几分钟，
主播不可能全程闭嘴，中途与观众闲聊的每一句话都会把宝贵的 LLM 处理掐死。
而 KWS（M2）本来就常驻在跑，具备"精确判激活词"的能力，现仅用于 IDLE 唤醒
（core.py:161-164：非 IDLE 时 KwsHit 直接忽略）。

## 2. 需求（用户拍板四条）

- **R1** TTS 播报仍可被任意 ASR 出句打断；**LLM 处理不可**——要中断 LLM，必须说激活词「小码小码」。
- **R2** 激活词判定走 **KWS**，不走 ASR 文本匹配：ASR 可能把「小码」转成「小马」等
  同音词；用户自定义激活词同样受同音字影响，文本匹配不可靠。
- **R3** LLM 处理期间（纯思考/工具执行、助手没出声），未过 KWS 的 ASR 语句**一律无响应**：
  不打断、不入 buf、不回应的——此时主播在和观众说话，oc2 不许插话。
- **R4** TTS 输出期间不再需要激活词：ASR 有输出就断。主播此时抢话，必然对回答不满意，
  该断就断（维持现有 `_barge_in` 全套语义：停 TTS + 断 LLM + 回 COLLECT 收新句）。

## 3. 关键口径：怎么区分"LLM 处理中" vs "TTS 输出中"

一个 RUNNING 回合内部有两个阶段，用**本回合是否已开始出声**划分：

| 阶段 | 判据 | 任意 ASR 出句 | KWS 命中 |
|---|---|---|---|
| 思考期（还没出声） | 本回合尚未播过任何一句 | **忽略**（仅日志，R3） | 打断：`oc.interrupt` + 回 COLLECT |
| 回答期（已出声/正在播） | 本回合首次 `_speak()` 之后 | 打断（现行为不变，R4） | 同样打断（走同一路径） |

- 实现上不需要接 TTS 的 SpeakStart/SpeakFinish 事件：在 `_collect_fire()` 重置
  `self._spoke_this_turn = False`，`_speak()` 首次调用置 True，即可零延迟判"本回合出过声"。
- 句间空隙（上一句播完、下一句还在合成/送达）**算回答期**——此间隙卡在"要不要激活词"上
  会让用户觉得失灵；且既然已出声，就是 R4 场景。
- 打断语义（无论触发源）= 现有 `_barge_in`：tts.stop 双停、oc.interrupt、`pending_exit/_rest`
  作废、回 COLLECT。KWS 触发时 `_barge_in` 的 text 参数传空串（KwsHit 无文本）；
  激活词之后的新指令由 ASR 正常流入 COLLECT（`strip_wake` 会把转写出的「小码小码」剥成空串，
  core.py:167 的 `and text` 守卫天然免疫，不会污染 buf）。
- `_sent` 追加重问机制（core.py:87, 202-203, 220）保留：打断=重问仍然成立。

## 4. 各事件 × 状态 变更明细（diff 现有 `_handle`）

| 状态 | 事件 | 现状 | 新增行为 |
|---|---|---|---|
| RUNNING(思考期) | AsrText | `_barge_in(text)` | 忽略，日志一行 `mute-asr: "…"` |
| RUNNING(回答期) | AsrText | `_barge_in(text)` | 不变 |
| RUNNING | KwsHit | 忽略 | `_barge_in("")`（打断，不念 ack） |
| IDLE | KwsHit / COLLECT / PERM | — | 全部不变 |
| RUNNING | TextIn（控制台打字） | `_barge_in` | **不变，打字即打断**：敲键盘是显式意图，不受本需求限制 |
| RUNNING | OcPermission→PERM | 播授权问句 | 不变；PERM 期 ASR 仍是授权应答（R3 不侵入 PERM） |

- KWS 常驻不过滤状态：`KwsWorker.set_muted` 现在无人调用（历史上为 SPEAKING 态预留），
  本需求下**继续保持不 mute**——回答期 KWS 命中同样是打断，行为一致。
- 回采自听老问题：TTS 外放把「小码小码」播回麦克风理论上可自触发打断；维持 AGENTS.md
  口径（硬件 AEC 前不设软件防护），不新增逻辑，观察计数即可。

## 5. 明确不做

- 不做"只停 TTS 不停 LLM"的静音模式（R4 语义=整轮作废，保留半途继续跑的 LLM 只会让
  后续新句被 `_turn_fut` 护栏卡住重试，core.py:197-200）。
- 不改 ASR 文本匹配做兜底激活词（R2：同音词不可靠，宁可漏断不可误断）。
- 不改 keywords.txt 生成/自定义激活词流程（M2 既有能力已覆盖）。
- 不动 COLLECT 免唤醒连续对话、voice-end 唯一退出通道（M6.1）。

## 6. 业务代码行数估计（AGENTS.md 纪律）

| 文件 | 现规模 | 估计增量 | 内容 |
|---|---|---|---|
| `src/orchestrator/core.py` | 284 行 | **+30 行以内** | `_spoke_this_turn` 标志 + RUNNING 两个分支改写 + KwsHit 分支 |
| `tests/test_m5_orch.py` | ~200 行 | +60 行 | 新 UT（§7） |
| 其他 | — | 0 | 不动 asr/kws/tts/oc/main |

## 7. 验收用例（UT 级，Fake 驱动，无需真人）

1. RUNNING 思考期：post AsrText ×3 → 无 tts.stop、无 oc.interrupt、buf 空、状态仍 RUNNING。
2. RUNNING 思考期：post KwsHit → oc.interrupt 恰一次、回 COLLECT；随后 AsrText 新指令 → 正常成轮。
3. RUNNING 回答期（先喂 OcText 触发一句 _speak）：post AsrText → 与现 `_barge_in` 行为逐项一致。
4. KwsHit 后跟 AsrText"小码小码"（strip 后为空）→ buf 不被污染、deadline 不被刷新。
5. IDLE→唤醒 ack→COLLECT 全链路回归不破；TextIn 在 RUNNING 任意子阶段仍即打断。

## 8. 待决问题（已拍板）

- Q1 思考期 KWS 打断后念不念短 ack？→ **不念**：会话已在线，打断本身即反馈。
  **⚠ 10-01 反转（用户拍板）**：0930/1001 直播实测——思考期打断是纯静默（长任务无出声），
  主播无法区分"打断成功"与"没打断"，主观以为失灵。改为：KWS 型打断成功后补念一句
  `ack_text`（"在呢。"）作确认；`_barge_in` 的 `call_later(0.4, tts.stop)` 双停压尾音在前，
  ack 在 `call_later(0.45, _speak)` 入队（早入队会被双停清掉）。仅 KWS 路径；
  回答期 AsrText 抢话型打断仍不补 ack（不抢主播话头），TextIn 打字打断不补（控制台可见）。
  行数核账：core.py +2、test_m5_orch +3（既有两用例改断言）。
- Q2 思考期忽略的 ASR 要不要在控制台/dialog view 可见？→ **可见**：事件本就先 `_tap`
  镜像再处理，零成本，仅状态机不动作。

## 9. 勘误：实际行数 vs 估计（2026-09-27 实现后核账）

| 文件 | 估计 | 实际 | 说明 |
|---|---|---|---|
| `src/orchestrator/core.py` | +30 以内 | **+12/−3（净+9）**，284→293 行 | 与 §3 方案一致：`_spoke_this_turn` 标志（`_collect_fire` 复位、OcText 首播置位）+ RUNNING 的 AsrText 分支门控 + KwsHit 增 RUNNING 分支 |
| `tests/test_m5_orch.py` | +60 | **+66** | 新增 3 个门控 UT；6 个既有 barge-in UT 各加一行"先出声进回答期"前置（真机丢话复盘的护栏语义不动） |
| 其他 | 0 | 0 | asr/kws/tts/oc/main 未动 |

## 10. 二轮补丁：KWS 时间戳回音门（2026-09-28 凌晨，deepthink 设计+实现）

问题：KWS 打断/唤醒后，ASR 也会把"小码小码"转写出来（常成同音"小马小马"），文本剥离（strip_wake）
只认正字，防不住同音垃圾进 buf。方案改为**与转写文本无关的时间戳过滤**（用户拍板方向）：

- 机制：任何 `KwsHit` 到达即记 `_wake_mono=clock()`（monotonic，与 `AsrText.end_ts` 同基准——
  end_ts=VAD 段语音真终点+量化误差，与解码延迟解耦）；随后 AsrText 若
  `Δ=end_ts−wake_mono ∈ [−0.60,+0.10]` 判为唤醒词同段回音，**整段丢弃**
  （log `echo-drop "…" Δ=…` + `echo_drops` 计数，观测不拦截其它路径）。
- 关键性质：`end_ts=0`/无锚 → fail-open（既有 20+ UT 零改动兼容）；连读段"小码小码帮我开单"
  （Δ≈+0.5~1.5）出窗保留，正字前缀仍由 strip_wake 剥（strip_wake 本轮同步升级为
  keywords.txt 动态正则+半词派生，正字/自定义词场景）；COLLECT/PERM 的 no-op 命中同样刷锚
  （顺带堵掉"回音句在 PERM 被 match_permission 判 reject"的暗坑）；fwd 窗只取 0.10s——
  宁漏勿杀（漏=同音垃圾一行进 LLM 错字规则≈现状，杀=丢指令需重说）。
- KWS 侧（P1）：cooldown 内二喊不再静默吞，改 emit `KwsHit(repeat=True)`——编排器只刷锚不动
  状态，覆盖 2s 内连喊的第二回音；`_last_hit` 语义不变（自最近真命中起算）。
- 行数核账：core.py +17（估 14±3 ✓，359 行）；kws_wake.py +5（估 4 ✓）；新增
  `tests/test_m13_echo_gate.py` 8 例 + m2 repeat 契约 1 例 + strip_wake 扩测（tmp 文件
  monkeypatch 隔离真实 keywords.txt）；133 UT 全绿。
- 真机待办：观察 `echo-drop` 行的 Δ 分布校准 ECHO_BACK_S/ECHO_FWD_S 两常量
  （风险评审：误杀最坏=丢一句、免唤醒重说即自愈，无卡死路径）。

### 10.1 三轮 review（deepthink，重点=是否用硬编码文本）后修订 F1-F5

review 判定门控路径 **100% 纯时间戳**（`_is_wake_echo` 只读 `_wake_mono`+`end_ts`，无长度/字符/
"是否含唤醒字样"任何文本条件；`keyword` 除 log/前端镜像外零决策参与），残留死词仅 1 处（兜底）。逐条修：

- **F1（数值修正）** `ECHO_BACK_S` 0.60→**1.20**：原值只算了 160ms 批延迟，漏算 chunk-16 的 320ms
  算法延迟 + trailing blanks + dispatch → 纯回音 Δ≈−L 实际落在 −0.35~−0.9，0.60 会大概率**漏杀**
  （正是思考期 CPU 最忙、最需要这道门时）。`ECHO_FWD_S` 保持 0.10。代价：COLLECT 中真句尾紧邻一个
  假 KWS 触发（<1 次/小时）会误杀一句，重说即自愈。
- **F2（观测补齐）** 未命中侧加 `echo-near` 近窗日志（Δ∈[−3,+0.5]）——原设计"观察 Δ 分布校准常量"
  若只打窗内样本则逃出窗的永远不可见，此条让校准有数据可依。
- **F3（回归修复）** `human-test/m2_t5_wake-rate.py` `on_hit` 开头 `if h.repeat: return`，防本轮
  repeat emit 污染唤醒率/误触发计数（历史 RESULTS 已现 hits=11/10 多计先例）。
- **F4（清除死词）** `strip_wake` 去掉 `or ["小码"]` 兜底：文件缺失/无 `@显示名` → **返回原文不剥**
  （并短路避免 `^(?:(?:)…)` 退化正则）。全仓再无任何死激活词参与文本处理。附带修 `test_m13`
  连读用例（原兜底使该例即使真文件不可读也过，现能真正证明动态解析）。
- **F5** `_brief`/KwsHit 分支 `getattr(ev,"repeat",False)`→直接 `ev.repeat`（dataclass 已保证字段，
  原防御与同行裸取 `ev.keyword` 自相矛盾）；补连读短令边界 UT。
  `echo_drops` 计数**保留**（已接 F2 逐条日志作为观测出口，非纯冗余）。

净行数：core.py +~8（本轮）、kws_wake.py 未再增；新增 1 UT（merged 短令牺牲）。
仍待真机：按 F1/F2 采 `echo-near`/`echo-drop` 的 Δ 分布回校两常量；若延迟档仍不理想，
F6（用 KWS `timestamps()` 取声学末 token 时刻做**声学锚**替代 dispatch 锚，窗可缩回 0.2）留下一轮。
