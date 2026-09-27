# M14 动态热词（set-hotwords 工具 + KB 热词节）设计

日期：2026-09-27 ｜ 状态：**设计，未实现** ｜ 前置调研：deepthink 源码级核查 + 本机 token 实测（§3）
关联：`docs/0927工作/kws-gated-llm-interrupt-req.md`（同日打断门控）、`docs/0923工作/asr-design.md`、AGENTS.md「播报期自听」

## 1. 背景

1. 0927 真机事故：config 级常驻 10 个 WoW 热词，在无有效人声段（回声尾/游戏音）被 Qwen3-ASR
   逐词复读成幻觉句（18:18:44 `"周常 英雄难度 龙希 虚空侵攻 盘卷蛇岛 圣骑"`），已临时撤空热词。
2. 机制核实（sherpa-onnx v1.13.8，行号对得上本机构建）：qwen3-asr 热词是 system-prompt 偏置，
   每次 Decode 读 `stream->HasOption("hotwords")/GetOption("hotwords")`，无则回退 config 值
   （offline-recognizer-qwen3-asr-impl.cc:817-821）→ **可逐段现改**。已实测：同一 recognizer，
   每条 stream `set_option` 不同词表，debug 日志逐条显示不同 `hotwords add N tokens`。
3. 陷阱（必须写进代码注释）：`recognizer.create_stream(hotwords=...)` 是 transducer 专用路径，
   qwen3 未 override，基类默认实现直接 `exit(-1)` 杀进程（offline-recognizer-impl.h:36-40）。
   唯一正路：`stream.set_option("hotwords", "词1,词2")`，逗号 CSV，词内禁 ASCII 逗号。
4. 本项目 AsrWorker 本就每 VAD 段新建 stream（pipeline.py:81），天然适配逐段装填。

目标：LLM（oc2 voice agent）答某话题前，主动把该话题 ≤8 个专名装填为 ASR 热词，提高"毒牙祭坛/
塞塔里斯神庙"这类生僻词命中率；暴露窗口从"全天常驻"缩到"话题进行期"，把幻觉副作用也一并缩小。

## 2. 拍板记录（用户 2026-09-27）

- ① console 入站 `hotwords` 帧做**手动调试兜底**：做。
- ② **不做 TTL**：装填后永久有效（会话内），直到 LLM 再次调用覆盖 / 清空，或会话回 IDLE 自动清。
  理由：正常直播问答 LLM 会频繁调工具更新，陈旧窗口自然被覆盖。
- ③ **不做 qa 视图镜像**：热词只写在权威条目 frontmatter，单源，不引入镜像漂移例外。
- ④ token 预算实测厘清（见 §3）——"43" 是旧词表的 token 数，不是条数；超线的是 48 tokens。

## 3. Token 预算实测（本机 1.13.8，debug 日志 `hotwords add N tokens`）

| 词表 | 词数 | 汉字数 | 实测 tokens | 48 线 |
|---|---|---|---|---|
| 旧事故表 | 10 | 33 | 43 | ✅ 贴线内 |
| 池总览候选（8 副本名） | 8 | 41 | **49** | ❌ 超 |
| 毒牙祭坛条目候选 | 8 | 30 | 41 | ✅ |
| 8×4 常用字 | 8 | 32 | 31 | ✅ |
| 8×6 常用字 | 8 | 48 | 46 | ✅ 贴线 |

补充实测（scripts/m14_hotwords_probe.py，2026-09-27，"超上限报错"判明）：
**词数无硬上限，卡的是 token**（tokens ≈ 汉字数 + 词数-1 个空格 + 零碎）。三档行为，全部不抛异常不崩进程：

| 档位 | 触发 | 实测 | 后果 |
|---|---|---|---|
| ① soft | hotword tokens ≥48 | 16 词 78t：仅 WARN，照常解码 | 只有日志噪声+偏置副作用扩大 |
| ② 音频截断 | prompt+audio > max_total_len=1024 | 192 词+20s 句：`Truncating audio placeholders 260→51` | **只有 ~1/5 音频被解码**，出乱码（"language"）——静默质量坍塌 |
| ③ prompt 塞满 | before_len ≥1024 | 224 词起：`prompt scaffold exceeds max_total_len` | **该段直接空文本**（decode 短路 0.2s），无声学"失聪"，Python 侧不可见 |

另一条真上限是**延迟**（prefill 随词表线性涨）：8 词 0.87s / 32 词 1.55s / 64 词 2.75s / 128 词 5.8s /
192 词 8.2s（3s 噪声段，2 线程）。直播 3s 成轮节奏下 >32 词就已经不可用。

首批 15 条表入库前审计（D:\Temp\opencode\hw_batch_audit.py，2026-09-27）：最大 lfd 池总览
7词/34字=**40 tokens**，全部 <48；据此告警软线定为 **36 字**（≈48t），实现值见 pipeline.HW_WARN_CHARS。

结论与纪律：
- 常用汉字 ≈1 token/字；**生僻专名被 BPE 切碎 ≈1.3~1.4 token/字**（词数少 ≠ 安全，池总览 8 词就超）。
- 门面校验（§5）除 ≤8 词/≤32 字外，加一条 CSV 总长硬拒上限（≤200 字符）兜底 console 手滑，
  保证永不触及 ②③ 档（设计内的词表在最长老录音 20s 下余量也 >5 倍）。
- **入库硬线：≤8 词 且 合计汉字 ≤36 且 debug 实测 <48 tokens**。超线砍最长/最生僻的词
  （如池总览砍"纳洛拉克的洞穴"）。超 48 不会报错不会截断，只有日志 WARN + prompt 膨胀 +
  偏置副作用面扩大，功能上"能跑"——但按纪律不予入库。
- 测量工具现成：任意短 wav + 该词表跑一次 decode（debug=True），无需新写脚本。
- 副作用官方实证：偏置作用于整段转写，装热词后无关短语可能被"连带畸变"（土家族自治州→
  土家族自制粥）。热词越生僻越多，畸变风险越大 → 宁少勿多。

## 4. 架构（推荐路径 = 复刻 voice-end 模式，SSE 旁观）

```
LLM 调 set-hotwords(words=[...])                console 手动兜底
  │ opencode SSE: session.tool.called             │ ws 入站帧 {"t":"hotwords","words":[...]}
  ▼                                               ▼
OcTool(name=="set-hotwords", phase=="called", tool_input)      HotwordsSet(words)
  └────────────┐                 ┌───────────────┘
               ▼                 ▼
        orchestrator._handle → asr.set_hotwords(words)   ←—— 唯一写者
               │ 校验/去重/截断（AsrPipeline 门面内，一处）
               ├→ worker._hotwords = "csv"（不可变 str 快照，跨线程赋值原子，无锁）
                └→ _log("hotwords applied: csv")（回执只进 log，不进 ev/tap——用户 0927 拍板）
AsrWorker 每段解码：create_stream() → if self._hotwords: set_option("hotwords", 快照) → accept → decode
```

- **不选**"插件 execute 直连 ws 回注"作主通道（Bun/Node 里 WebSocket 无先例未验证）；console 那条
  只做人工调试，走既有 `_dispatch` 扩展位（"注入唯一出口 = orch.post"纪律不破）。
- **不选** 文件轮询（延迟 + 编码 + 清理都是新问题），仅当 called 帧不带 input 被证伪时作退路。
- called 帧带 `tool_input` 已有真机实证（tests/fixtures/m61_tool_events.jsonl）。

## 5. 组件设计与行数预算（AGENTS.md 纪律：组件级预算，实际超 1.5× 才解释）

| 文件 | 改动 | 预算 |
|---|---|---|
| `config/oc2/plugins/set-hotwords.ts`（新） | 照抄 voice-end.ts 结构：name/description（引导"答含 hotwords 条目前必调"）、input `{words:{type:"array",items:{type:"string"},maxItems:8}}`、**`options:{codemode:false}`**、execute 返回静态"已装填，继续回答" | ~35 行 TS（不计 Python） |
| `src/orchestrator/core.py` | ① `_handle` 加 `OcTool name=="set-hotwords" called` 分支→`self.asr.set_hotwords(ev.tool_input.get("words"))`+log 回执；② `HotwordsSet` 事件类 + 分支（console 入口，同调门面）；③ `_go(IDLE)` 内清表（2 行）；④ `_brief` 补两行 | **+20 以内**（现 293） |
| `src/asr/pipeline.py` | ① `AsrWorker._hotwords=""` + decode 前读快照 `set_option`（3 行）；② `AsrPipeline.set_hotwords(words)` 门面：**校验唯一落点**——strip 丢空、剔含 ASCII 逗号/空白/控制字符词、去重（互含留长）、>8 截前 8、汉字合计 >32 只告警不拒、返回 csv；③ stats 增 `hotwords` 当前值 | **+18 以内**（现 172） |
| `src/console/server.py` | `_dispatch` 在 ask 兜底**之前**加 `t=="hotwords"` 分支 → `orch.post(HotwordsSet(...))`（顺序关键：否则被当主播说话注入） | **+8 以内** |
| `config/oc2/skills/wow-kb/SKILL.md` | grep 关键字 `aliases|title|zhcn_terms` 加 `|hotwords`；协议句 2 行："命中条目 frontmatter 有 hotwords → 先调 set-hotwords 原样传词表再作答；换到无 hotwords 条目 → set-hotwords([])" | +4 |
| `config/oc2/AGENTS.md`（voice agent 侧） | 一条硬规则：set-hotwords 词表原样照抄，禁止自己编词/加常用词 | +2 |
| `config/oc2/wow-kb/**/…md` frontmatter | 首批 12~15 条（dg121 家族、池总览(砍词后)、lfr/spire、addons、glossary），每条 +1 行 `hotwords: [...]`，**全部过 §3 硬线** | +15 行 md |
| `tests/test_m14_hotwords.py`（新） | UT（§8） | ~50 行（测试不计业务） |
| 业务 Python 合计 | — | **≈ +46，上限 60** |

## 6. 生命周期（拍板②：无 TTL）

| 动作 | 触发 | 位置 |
|---|---|---|
| 装填/覆盖 | `OcTool(set-hotwords, called)` 或 `HotwordsSet`（console） | core 两分支 → 同一门面，覆盖式替换 |
| 清空 | LLM 显式 `words=[]`；**回 IDLE**（voice-end/出错/会话销毁） | SKILL 协议 / `_go(IDLE)` |
| 保留 | 跨回合、跨打断（COLLECT/RUNNING/PERM 全程）、会话内常驻 | 默认即如此 |
| 失败语义 | 校验后空表 = 清空；类型错/无 words 字段 = **保留旧表**+log，永不抛 | 门面/core |

观测计数（不拦截，AGENTS「播报期自听」口径）：AsrWorker 解码结果若"去标点后完全由当前词表词拼成"
→ log 一行 + 计数（幻觉回潮的哨兵，人肉看趋势；不做丢弃，因为"毒牙祭坛"单独成句是合法问句）。

## 7. 选词纪律（写进 writing-guide，条目作者与 LLM 共同遵守）

1. 只收专名生僻词（副本/首领/机制/装备名），不收常用词（无收益只有畸变风险）。
2. **只收正名**；误听形（"尖牙圣坛"）留在同音消歧表，永不进 hotwords（偏置错形=灾难）。
3. 每词 2~8 字，词内禁 ASCII 逗号/空白；全表去重、互含留长。
4. ≤8 词 且 汉字合计 ≤36 且 debug 实测 <48 tokens（§3）。
5. 有消歧表变体的词 = 最值得装填的词（ASR 恰恰在这些词上失手）。

## 8. 验收

- UT（Fake 四件套，无模型）：OcTool called 帧→FakeAsr 收到 csv；`words>8` 截断；含逗号词被剔；
   `[]`→清；`_go(IDLE)`→清；`HotwordsSet` 走同一校验；回执只进 log、ev 流不得出现 HotwordsApplied（0927 改拍）。
- pipeline 层：monkeypatch OfflineRecognizer，断言 decode 前 set_option 恰好被调、词表为空时不调。
- 真机（human-test 脚本 m14，走 human-in-the-loop-testing skill）：问"英雄本周常都有啥"→
  dialog 出现 set-hotwords 装填帧 → 对麦克风念带生僻词的问句验证命中率；对照组撤热词。

## 9. 部署 checklist（无脚本，人工双落，改源必改部署区）

1. `config/oc2/plugins/set-hotwords.ts` → 复制到 `tools/oc2-home/config/opencode/plugins/`。
2. wow-kb 源条目 hotwords 行 → 同步部署区 kb 副本（按既有 wow-kb 部署方式）。
3. SKILL.md / AGENTS.md（voice）改动同步部署区。
4. `stop.bat` → `run.bat`，log 首行确认无插件加载错误；dialog 里验证一次调用链。

## 10. 风险登记

| 风险 | 处置 |
|---|---|
| LLM 忘调工具 | 三重引导（tool description + SKILL 协议 + voice AGENTS）；m61 教训=必须 agent 钉死+硬规则；装填/拒绝回执 `_log` 可观测（不进 ev 流，0927 拍板） |
| LLM 自创词表 | AGENTS 硬规则"原样照抄"+ 校验门截脏词 |
| 词表陈旧 | 无 TTL（拍板②），靠 IDLE 清 + LLM 高频覆盖；哨兵=幻觉观测计数 |
| 连带畸变 | §7 纪律"宁少勿多"；dialog 观察回答质量 |
| called 帧不带 input（版本变更） | 退路=插件直连 console ws（协议已因①就位）；文件轮询最后备 |
| 回采念热词自激 | 硬件 AEC 已在场，AGENTS 禁软件防护，仅计数观察 |

## 11. 勘误（2026-09-27 实现后核账）

| 文件 | 预算 | 实际(净) | 说明 |
|---|---|---|---|
| core.py | +20 | **+30**（293→323） | 恰在 1.5× 线：两个 dataclass 含空行/文档串 16 行是大头，逻辑本体 ~14 行 |
| pipeline.py | +18 | **+40**（175→215）**超 1.5×** | 超额块=`normalize_hotwords` 校验函数本体 28 行（预算时把它当"3 行截断"低估了）：非 list 拒绝/脏词剔除/单词超长/去重/互含留长/截 8/软线告警七条规则全是 §5"校验唯一落点"的既定内容，**未引入设计外机制**；worker 快照+set_option 6、门面 6、stats 1 |
| server.py | +8 | +6 ✓ | |
| 合计业务 Python | ≈46(上限60) | **+76** | 超上限成因同上：预算没给校验函数留够行数，非功能膨胀 |

处置选项（待用户拍板，未自行处理）：A. 保留（规则都是设计内的，砍任何一条都会把脏词放进来）；
B. normalize 瘦身：砍"互含留长/去重"两规则（LLM 照抄词表时本来就极少触发）可省 ~6 行。

### 11.1 二轮（deepthink 审查后修复，2026-09-27）

审查判定：核心链路正确、选 **A 全保留**（B 实为伪节流，去重/互含各挡真实脏输入面）；用户拍板按审查要求修。

| 修复项 | 落点 | 净行数 |
|---|---|---|
| X1 qa 命中路径漏装填 | SKILL.md 第2步补"仍按「权威条目」节读 frontmatter"（+源+部署双落） | md 1 句 |
| X2 §6 幻觉哨兵兑现（上轮静默缺项） | pipeline：`_pure_hotword_echo` 静态判定+计数+log+stats `hw_echo`，纯观测不拦截 | +15 |
| 小项 | normalize 前置截 64（防 console 手滑 O(n²)）；set-hotwords 分支 `state!=IDLE` guard；`_brief` 补 HotwordsSet；UT 缺口 1/3/4+哨兵+console非list | +2+2+3 |

**最终核账（vs §5 预算）**：core.py +33（预算 ≤20）、pipeline.py +55（预算 ≤18）——超 1.5× 成因逐块：
校验函数 29（§5 低估）+ 哨兵 15（§6 明文承诺、预算漏计）+ worker/门面/stats 14 + 事件类 16 + 分支/回执 15；
全部对应设计文档既有条款，**无设计外机制**；tests 181 行不计业务。合计 124 UT 绿。

