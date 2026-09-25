# 模块划分与模块技术选型 (Module Breakdown & Tech Selection)

> 2026-09-23 工作记录。

## 0. 背景、硬约束与结论速览

本文档基于 `docs/overall-goals.md` 的总目标：主播打游戏时全程仅用语音与 opencode agent 交互。核心链路：

```
小模型常驻监听"激活词" → 激活后 VAD+ASR 转文本 → 送 opencode server(headless) 执行
→ 执行结果 TTS 播放 → LLM/skill 识别"结束对话" → 回到监听态
```

### 0.1 硬性约束（贯穿所有选型）

| 约束 | 含义 | 对选型的影响 |
| ---- | ---- | ---- |
| 非焦点 (non-focus) | 不得抢占游戏窗口焦点，不得弹窗 | 无窗口/托盘化设计；状态反馈全部走"声音提示音 + TTS"；可选 OBS 浏览器源覆盖层（不抢焦点） |
| 无键盘 | 监听/激活/对话/结束全部语音完成 | opencode 的 permission 询问必须能自动应答或语音应答；激活词引擎必须支持自定义中文关键词 |
| 全本地 VAD/ASR/TTS | 不依赖云端语音 API | 优先 onnx / gguf / int8 量化推理 |
| RTX 3080 10GB 与游戏共存 | 显存与 CPU 都要给游戏留余量 | **推荐全 CPU 推理方案（0 显存增量）**，GPU 仅作可选加速；线程数与进程优先级受控 |
| 中文为主 | ASR 中文准确率高、TTS 中文自然度高 | 优先 FunAudioLLM/sherpa-onnx 生态的中文模型；方言/噪声鲁棒性作加分项 |

### 0.2 结论速览（推荐方案一览）

| 模块 | 推荐方案 | 运行位置 | 体积/占用（依据） |
| ---- | ---- | ---- | ---- |
| 音频采集 | Python + **sounddevice**（PortAudio 内建 16k/mono 转换，照抄 sherpa-onnx 官方麦克风示例；v2 修订 2026-09-23） | CPU | 忽略不计 |
| 激活词监听 (KWS) | **sherpa-onnx KWS**：`sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20`（int8） | CPU 1 线程 | encoder int8 4.4MB + decoder 743KB + joiner 85KB；chunk-8 延迟 160ms / chunk-16 320ms（官方文档） |
| VAD | **Silero VAD (onnx)**（经 sherpa-onnx 内置） | CPU 1 线程 | 模型 ~2MB；单线程处理一个 30ms chunk <1ms（官方 README） |
| ASR | **Qwen3-ASR-0.6B int8**（sherpa-onnx 官方集成 PR#3399，CPU+内存档；v3 修订 2026-09-24，SenseVoiceSmall 降为回退） | CPU | sherpa 官方 int8 包 878MB；CPU RTF 0.091–0.15（Xeon 4 线程实测，PR#3399/#3409）；0 显存 |
| 会话编排 | Python 3.11+ asyncio 状态机（单进程调度各推理线程） | CPU | — |
| opencode 集成 | `opencode serve --port 4096`（headless，复用全局配置）+ REST/SSE | CPU（LLM 走云端 API，不占本地 GPU） | node 进程 ~0.3–0.6GB RAM ⚠️估算 |
| TTS（**v4 定版 2026-09-24**） | **VoxCPM1.5**（0.8B，44.1kHz，Apache-2.0）GPU 常驻 + torch.compile(triton-windows) | GPU ~3GB 常驻/4GB 峰值 | RTF **0.4**（实测，compile 前 2.0）；原推 sherpa Kokoro CPU 档降为兜底预案 |
| TTS（不启用项存档） | CosyVoice2-0.5B / GPT-SoVITS / Kokoro：质量或工程复杂度不划算；VoxCPM.cpp GGUF Q8（RTF ~0.5-0.8 外推）为 M7 提速后手 | — | 见 docs/0923工作/tts-design.md §0 |
| 结束对话 | opencode **Agent Skill（`voice-end`）+ 插件自定义 tool** 通知编排器；编排器侧文本标记兜底 | CPU | — |
| 焦点/交互适配 | 托盘进程（无主窗口）+ 提示音(earcon) + 可选 OBS overlay；永不 SetForegroundWindow | CPU | — |

⚠️ = 推断/需实测项，详见文末"风险与待实测清单"。

---

## 模块划分

### 总体架构

```
                ┌────────────────────────────────────────────────────────┐
                │                 M5 会话编排（状态机/Orchestrator）        │
                │  IDLE → KWS_ARMED → ACTIVE(拾音) → THINKING → SPEAKING │
                │        ↑                                    │          │
                │        └────── M8 结束对话检测 ←─────────────┘          │
                └───▲──────▲──────▲──────▲──────▲──────▲──────▲──────────┘
                    │      │      │      │      │      │      │
   ┌────────┐  PCM  ┌────┐ │ ┌────┐ │ ┌────┐ │ ┌──────────┐ ┌────┐ ┌──────────┐
   │M1 音频 │──────→│M2  │ │ │M3  │ │ │M4  │ │ │M6 opencode│ │M7  │ │M9 焦点/  │
   │  采集  │ 帧流  │KWS │ │ │VAD │ │ │ASR │ │ │ 集成(REST │ │TTS │ │ 交互适配 │
   └────────┘       └────┘ │ └────┘ │ └────┘ │ │ +SSE)    │ └────┘ └──────────┘
       │                   └────────┴────────┘ └──────────┘
       │ (可选 loopback：游戏声/混音，用于上下文或降噪参考)
       └────────────── M10 配置/模型管理/日志/健康监控（横切）
```

### M1 音频采集模块 (Audio Capture)

- **职责**：从主播耳机麦克风（默认通信/录音设备）持续采集 PCM；支持虚拟声卡（VoiceMeeter/VB-Cable）等混音设备；统一重采样为 16kHz 单声道 float32；向 KWS/VAD 多路分发。采集停摆/拔麦**不做自动重连**，改为**周期语音报警**提醒人工处理（v2 修订，需求未承诺 7×24 直播；详见 `audio-capture-design.md` v2）。
- **输入**：Windows 音频设备（WASAPI 共享模式，采集不需要任何窗口焦点）。
- **输出**：定长帧流（建议 10–30ms/帧），`Frame{pcm_f32, ts, device_id}`。
- **接口**：进程内异步队列/回调 → M2、M3、M5（M5 负责按状态决定帧路由到 KWS 还是 VAD+缓冲）。
- **关键约束**：采集与播放全程不创建窗口、不请求焦点；TTS 播放设备若与采集设备同一物理耳机，需防"自激"（KWS 听到自己 TTS）——设计上 TTS 播放期间 KWS 仍监听但提高阈值/或短暂抑制（barge-in 策略，见 M5）。

### M2 常驻激活词监听模块 (KWS / Wake)

- **职责**：直播期间常驻低功耗监听主播语音，检测自定义中文激活词（如"小码小码"/"你好问问"）；给出命中事件与置信度；支持多关键词与阈值调节（游戏噪声下防误触发）。
- **输入**：M1 帧流。
- **输出**：事件 `KwsHit{keyword, ts}` → M5（v2 更正：官方 Python `get_result()` 不暴露置信度，无 score 字段，把关靠 `keywords_threshold` 硬阈值）。
- **接口**：sherpa-onnx `KeywordSpotter` 流式 API（`accept_waveform` / `decode`）；配置项：keywords 文件（拼音 token 形式）、`keywords_threshold`、`keywords_score`。
- **资源要求**：CPU 单线程即可实时（模型仅 3M 参数、int8 ~5MB 级）。

### M3 VAD 与语音端点模块 (VAD / Endpointing)

- **职责**：激活后判定语音开始/结束（endpointing）；把连续音频切成"一句话"片段；控制静音判停时长（如 600ms）、最长单句（如 20–30s，防呆）；同时供 M4 做伪流式切分。
- **输入**：M1 帧流（仅 ACTIVE 态路由进来）。
- **输出**：`SpeechStart` / `SpeechEnd{pcm_segment, duration}` → M5、M4。
- **接口**：sherpa-onnx 内置 Silero VAD（`VoiceActivityDetector`），或独立 silero-vad onnxruntime 推理。
- **备注**：监听态（KWS_ARMED）不需要 VAD 常开；TTS 播放态可用 VAD 辅助 barge-in 判定（可选）。

### M4 ASR 转写模块 (Speech-to-Text)

- **职责**：将 M3 切出的语音片段转成中文文本；输出规范文本（Qwen3-ASR：多语言+22 中文方言，唱歌/BGM 鲁棒）；对游戏术语/自定义命令词做热词（Qwen3-ASR 原生热词支持，sherpa-onnx 侧亦保留 homophone-replacer/rule_fsts）。回退档 SenseVoice 额外提供情绪/音频事件标签。
- **输入**：`pcm_segment`（16kHz）。
- **输出**：`AsrResult{text, lang?}` → M5（置信度不暴露）。
- **接口**：同步调用（一次一句话），内部独立工作线程避免阻塞事件循环；sherpa-onnx `OfflineRecognizer`（Qwen3-ASR int8，与 SenseVoice 同一 API 家族，直接换模型包）。
- **质量要求**：中文 CER 优先；游戏噪声/口音鲁棒为加分项。

### M5 会话管理与编排模块 (Orchestrator，系统核心)

- **职责**：全局状态机与各模块调度：
  - `IDLE/KWS_ARMED`：帧流→M2；
  - `ACTIVE`：帧流→M3(→M4)，收到文本后进入 THINKING；
  - `THINKING`：调 M6 发送 prompt，订阅流式结果；
  - `SPEAKING`：把回复按句切分喂 M7；期间处理 barge-in（听到激活词/长时间插话→中断 TTS 与当前请求，`POST /session/:id/abort`）；
  - `ENDING`：收到 M8 结束信号→播放结束语→回 KWS_ARMED。
  - 超时与异常恢复（ASR 空文本、opencode 无响应、设备拔出）；会话生命周期映射（一次语音对话 ↔ 一个 opencode session，或复用长 session——建议每次激活新建 session、结束后保留可续）；权限询问事件的自动/语音应答（配合 M6）。
- **输入**：M2/M3/M4/M6/M7/M8 的全部事件。
- **输出**：对各模块的控制指令（开始拾音、发送文本、播放、中止）。
- **接口**：进程内事件总线（asyncio.Queue / 回调注册）；对外仅暴露本地控制端口（可选，供 overlay/调试面板）。

### M6 opencode Server 集成模块 (opencode Client)

- **职责**：
  1. **进程管理**：以子进程方式在目标工作目录启动 `opencode serve --port 4096 --hostname 127.0.0.1`（或连接已运行实例）；健康检查 `GET /global/health`；崩溃拉起。
  2. **配置复用**：完全复用当前 opencode 全局配置（见 §模块技术选型 M6 详述）。
  3. **REST 客户端**：创建/管理 session、发消息（同步 `POST /session/:id/message` 或异步 `prompt_async`）、执行 command、中止、权限应答。
  4. **SSE 订阅**：`GET /event` 接收 `server.connected` 及消息/分片流式事件，把增量文本按句推给 M7（边生成边播，降低体感延迟）。
  5. **Agent/skill 选择**：请求体可带 `agent`、`model`、`system`、`tools` 字段；语音场景可指定专用 agent。
- **输入**：M5 的文本与指令。
- **输出**：流式 assistant 消息 parts（text/tool 调用状态）→ M5/M7。
- **接口**：HTTP(REST) + SSE；OpenAPI 3.1 规范见 `http://127.0.0.1:4096/doc`；官方 JS SDK `@opencode-ai/sdk`（Python 侧建议直接 httpx + SSE 解析）。

### M7 TTS 播放模块 (Text-to-Speech & Playback)

- **职责**：把回复文本规整（数字/符号读法、按句切分）→ 合成 PCM → 播放到主播耳机（指定输出设备，独立于游戏音频通道亦可）；播放队列与优先级（提示音 > 正文）；支持随时中断（barge-in）；开头/结尾播放固定 earcon（激活成功音、结束音），替代一切视觉弹窗。
- **输入**：M5/M6 的文本流（句级）。
- **输出**：音频输出（WASAPI 播放）；状态事件 `SpeakStart/SpeakFinish/Interrupted` → M5。
- **接口**：sherpa-onnx `OfflineTts`（generate → numpy → 播放）；可选 CosyVoice2 流式服务（本地 HTTP/进程内）。

### M8 结束对话识别模块 (End-of-Session Skill)

- **职责**：识别"结束对话"意图并通知 M5。三条通道（主+兜底）：
  1. **LLM 主通道**：定义 Agent Skill `voice-end`（`~/.config/opencode/skills/voice-end/SKILL.md`，或项目 `.agents/skills/voice-end/SKILL.md`——与现有 `connect-gitee` skill 同机制），指导模型在用户表达结束意图时调用一个由 **opencode 插件注册的自定义 tool**（如 `voice_control(action="end")`），该 tool 回调编排器本地 HTTP 端点；
  2. **文本标记兜底**：约定 assistant 回复末尾输出 `[VOICE_END]` 类标记，M5 用 SSE 文本流正则检测；
  3. **编排器侧直判**：M4 的 ASR 文本命中"结束/退出/拜拜/先这样"等规则或小分类器时，直接由 M5 结束（不依赖 LLM 往返，最快）。
  4. 超时兜底：ACTIVE 态 N 分钟无语音自动结束。
- **输入**：opencode tool 调用 / assistant 文本 / ASR 文本。
- **输出**：`EndSession{reason}` → M5。

### M9 焦点与交互适配层 (Non-focus UX Adapter)

- **职责**：保证全链路零焦点抢占、零键盘：
  - 进程无主窗口，仅托盘图标（状态色：灰=待机、绿=激活中、蓝=思考、黄=播报）；托盘菜单仅鼠标操作，属调试用途；
  - 一切即时反馈用 earcon（短提示音）+ TTS 语音；
  - 禁用任何 `SetForegroundWindow`/`MessageBox`/WinForm 弹窗；Windows Toast 仅在检测到游戏非全屏独占时才可选使用；
  - 可选：本地起一个 localhost 网页作为 OBS"浏览器源"叠加显示状态/字幕（浏览器源由 OBS 离屏渲染，不产生焦点窗口）；
  - 全屏独占检测（D3D 全屏窗口枚举）用于决定通知策略；
  - 游戏内音量闪避（ducking）：TTS 播放时可临时调低指定音频会话音量（Windows Core Audio API，不抢焦点）。
- **输入**：M5 状态事件。
- **输出**：托盘/overlay/ducking 控制。

### M10 系统支撑模块（配置/模型管理/日志/健康监控）

- **职责**：统一配置（设备选择、关键词、阈值、opencode URL/agent、TTS 音色语速）；模型文件下载与版本锁定（sherpa-onnx 模型均提供 GitHub Release/ModelScope 直链）；结构化日志与可选音频片段落盘（用于调误触发）；看门狗（KWS/opencode serve 假死重启）；进程优先级与线程数管控（BELOW_NORMAL 优先级，onnxruntime `num_threads=1~2`，避免影响游戏帧率）。

---

## 模块技术选型

### M1 音频采集：候选与推荐

| 候选 | 说明 | 焦点/混音能力 | 结论 |
| ---- | ---- | ---- | ---- |
| **sounddevice（v2 推荐）** | PortAudio 官方绑定，`sd.InputStream(samplerate=16000, channels=1)` 重采样/下混由 PortAudio 内建完成；sherpa-onnx 全部麦克风示例（KWS/VAD+SenseVoice）基于此 | 采集天然无需焦点；不支持 WASAPI loopback（v2 不再需要） | ✅ 主选（v2 修订 2026-09-23，复用官方示例，不自造采集轮子） |
| PyAudioWPatch | PyAudio 的 Windows WASAPI 补丁版，支持 loopback；MIT | 同上；loopback 可拿系统混音 | 备选（仅当实测 PortAudio SRC 不可用或需要 loopback 时启用） |
| soundcard (python) | 纯 Python，支持 loopback | 同上 | 备选 |
| miniaudio / PortAudio 原语 | C 库，低开销 | 需自己写绑定 | 性能敏感时备选 |
| NAudio / CSCore (C#) | 若编排层改用 C# | — | 暂不考虑 |
| VoiceMeeter Banana / VB-Cable | 虚拟声卡路由：把"耳机麦+游戏声"混成一路虚拟设备，或分离出纯净麦路 | 系统级方案，与采集库正交 | ✅ 作为部署侧可选组件：主播已有 VoiceMeeter 时直接采其虚拟输出；也解决"蓝牙耳机麦 Hands-free 模式音质差"的路由问题 |

**推荐（v2 修订）**：sounddevice 采默认/显式指定录音设备（16k mono f32 一步到位，复用 sherpa-onnx 官方示例）；需要复杂路由时叠加 VoiceMeeter/VB-Cable；热插拔自动重连与 loopback 参考流从范围内删除（停摆→周期语音报警，人工重启）。

**要点（非焦点论证）**：WASAPI 采集是后台音频会话操作，与前台窗口/焦点完全无关；播放（TTS 输出）同理不产生焦点。唯一要注意的是不要在采集失败时弹系统对话框——错误一律走 M9 的提示音+日志。

### M2 激活词监听 (KWS)：候选与推荐

| 候选 | 中文支持 | 体积/资源 | 自定义关键词 | 授权 | 结论 |
| ---- | ---- | ---- | ---- | ---- | ---- |
| **sherpa-onnx KWS `zipformer-zh-en-3M-2025-12-20`（推荐）** | ✅ 中英混合，WenetSpeech 系训练 | 3M 参数；encoder int8 4.4MB、joiner int8 85KB、decoder 743KB；CPU 单线程流式实时；chunk-8 延迟 160ms / chunk-16 320ms | ✅ 开放词表：任意中文词经 `text2token`（pinyin）转拼音 token 即可，无需重训；`keywords_threshold`/`keywords_score` 可调 | Apache-2.0（代码）；模型 icefall 训练 ⚠️以 release 页为准 | ✅ 首选 |
| sherpa-onnx KWS `zipformer-wenetspeech-3.3M` | ✅ 纯中文（WenetSpeech 1 万小时） | encoder int8 4.6MB 等，同上量级 | 同上 | 同上 | 备选（新 zh-en-3M 模型更新且支持英文命令词） |
| openWakeWord | ❌ 仅英文（官方明确"only supports English"）；训练新词需英文 TTS 合成数据 | 模型每个 ~几 MB，80ms 帧，树莓派 3 单核可同时跑 15–20 个模型 | 需合成数据训练（Colab <1h） | 代码 Apache-2.0；**预训练模型 CC BY-NC-SA** | 中文激活词不可行，排除 |
| Picovoice Porcupine | 商业引擎，多语言（含普通话 ⚠️需以官网语言表核实） | 极轻量（CPU 占用极低） | 控制台生成 .ppn 关键词文件 | **商业授权**：个人免费需 AccessKey，商用需 Enterprise license | 备选（若 sherpa KWS 误触发不达标再评估，注意授权成本） |
| FunASR 流式 Paraformer + 文本关键词过滤 | ✅ | 流式模型数百 MB，CPU/GPU 均可但远重于专用 KWS | 任意文本匹配 | FunASR 模型许可 | 常驻场景功耗/误触发不划算，排除为主通道；可作"全命令词"扩展 |
| Snowboy / Mycroft Precise | Snowboy 已停止维护（2020 归档）；Precise 亦不活跃 | — | — | — | 排除（openWakeWord README 亦确认其不再维护） |

**推荐**：sherpa-onnx KWS（zh-en-3M，int8，**chunk-16 起步=精度档**；官方明示"低延迟通常低精度"，故提速才换 chunk-8，精度反向。v2 更正 2026-09-24，详见 `kws-design.md`）。激活词建议 3–4 音节、含翘舌/开口音（如"小码小码"），用 `keywords_score` 提升其权重；游戏噪声下先录 30–60 分钟实盘音频测误触发率（目标：<1 次/小时 ⚠️需实测）。可选叠加 Speex/RNNoise 降噪前置（openWakeWord 的经验表明降噪能同时降误触发与漏检，sherpa-onnx 也有 speech-enhancement 模块可复用）。

### M3 VAD：候选与推荐

| 候选 | 精度 | 体积/开销 | 授权 | 结论 |
| ---- | ---- | ---- | ---- | ---- |
| **Silero VAD v5/v6 (onnx)（推荐）** | 官方称企业级精度，6000+ 语言语料训练，抗噪好 | JIT/onnx 模型 ~2MB；单 CPU 线程处理一个 30ms chunk **<1ms**；支持 8k/16k | MIT | ✅ 首选（sherpa-onnx 原生集成，`silero_vad.onnx` 官方直链） |
| webrtcvad | 传统 GMM，噪声下误判多 | <1MB，极快 | BSD | 仅兜底 |
| FunASR FSMN-VAD | 好，中文场景验证多 | ~1MB 级，但绑定 FunASR runtime | FunASR 模型许可 | 若 M4 选 FunASR 全家桶则顺带使用 |
| whisper.cpp 内置 VAD（silero ggml 864KB） | 同 Silero | 极小 | MIT | 仅当 ASR 选 whisper.cpp 时内置使用 |

**推荐**：Silero VAD onnx（经 sherpa-onnx `VoiceActivityDetector` 使用），参数：`threshold≈0.5`、`min_silence_duration≈0.6s`（游戏环境宁可稍长防句中停顿被切断）、`min_speech_duration≈0.25s`、`speech_pad_ms≈100–200` ⚠️需实测调优。

### M4 ASR：候选与推荐

| 候选 | 中文效果 | 体积/显存 | 速度 | 流式 | 授权 | 结论 |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| **Qwen3-ASR-0.6B int8（sherpa-onnx，v3 推荐）** | **官方基准最强中文**：AISHELL-2 WER 3.15（Whisper-large-v3 5.06）、WenetSpeech-net 4.97–5.97、KeSpeech 方言 5.10–7.08、强噪集 16–17.9（Whisper 63.2）；30 语言+22 方言+粤语、原生热词 | 官方 sherpa 包 `sherpa-onnx-qwen3-asr-0.6B-int8-2026-03-25` **878MB**；CPU+RAM（~1.5–2.5GB ⚠️）；**0 显存** | 官方 CPU 实测 RTF 0.091–0.15（Xeon 4 线程）→ 5s 句 0.5–0.8s <1s | LLM-style 流式/离线统一；本项目 VAD 判停整句即可 | **Apache-2.0**（2026-01-29 开源 0.6B/1.7B） | ✅ **首选（默认档：CPU+内存）**；1.7B 官方 int8 包未发布（issue#3535），需自导出 |
| SenseVoiceSmall int8（sherpa-onnx，**回退档**） | 官方基准：中文/粤语优于 Whisper 同量级（弱于 Qwen3 一档）；带标点/ITN、情绪与音频事件标签 | `model.int8.onnx` **228MB**；CPU 运行 RAM ~1GB ⚠️ | 非自回归快：桌面 CPU 单线程 RTF≈0.10（官方文档，RK3588 A76 0.099） | 原生非流式；配 Silero VAD 伪流式 | 代码 MIT；权重 FunASR Model License（商用需署名 ⚠️） | ✅ **回退**：主播实机 CPU 上 Qwen3 RTF>0.3 时切回（模型小 3 倍）；情绪标签为独有彩蛋 |
| FunASR Paraformer-large（paraformer-zh，GPU） | 中文工业级强 | ~220M 参数（模型 ~840MB），GPU 显存 ~2GB ⚠️ | GPU RTF ≪0.1 | 有 `paraformer-zh-streaming` 流式版；sherpa-onnx 亦有 `streaming-paraformer-bilingual-zh-en`（int8 数百 MB ⚠️以 release 为准） | FunASR Model License | 真流式需求时的备选 |
| whisper.cpp（ggml small/medium） | small 中文一般；medium/large-v3 好但重 | small 466MB 文件/~852MB 内存；medium 1.5GB/~2.1GB；large 2.9GB/~3.9GB（官方 README 内存表）；支持 q5_0 量化再降 | CUDA/Vulkan/CPU 均可；CPU medium 难以实时 | 天然按 30s 窗，流式需 hack | MIT | 备选（生态成熟、量化方便，但同体积中文弱于 SenseVoice） |
| faster-whisper (CTranslate2) | 同上 | int8 CPU/GPU 灵活 | GPU 快 | 同上 | MIT | 备选 |
| Moonshine (tiny/base) | ❌ 仅英文 | 小 | 极快 | — | MIT | 排除（中文不支持） |
| Dolphin（DataoceanAI，sherpa-onnx 支持） | 主打**中文方言**（数十种） | 小模型级 ⚠️ | — | — | ⚠️以仓库为准 | 方言主播加分项，可作 A/B 实测对象 |
| Qwen3-ASR torch fp16 / TRT-EP / TRT-LLM（GPU 路线） | 同上（精度档） | torch bf16 0.6B 显存 3.5–4.5GB、1.7B ~7GB；社区 TRT-EP 0.6B fp16 ~3–4GB | GPU ≪实时（TRT-EP 实测 4.2s 音频 50–60ms） | 流式仅 vLLM(Linux) | Apache-2.0 | **排除 GPU 常驻**（2026-09-24 TRT 调研）：TRT-LLM 无该模型实现+无 Windows 原生；TRT-EP 显存与游戏共存冲突且收益仅 0.6s→0.1s。GPU 需求改用 llama.cpp GGUF 档（见推荐） |

**推荐（v3 修订 2026-09-24，用户拍板 CPU+内存默认档）**：**Qwen3-ASR-0.6B int8 + sherpa-onnx `OfflineRecognizer`（CPU，1–2 线程）+ Silero VAD 切句**。理由：
1. 中文 WER 全面强于 SenseVoice/Whisper 同场（官方 AISHELL-2 3.15 / 强噪 17.9 vs Whisper 63.2；22 方言+粤语+原生热词，正中游戏术语场景）；
2. 走 **CPU+内存**（0 显存），与游戏共存约束不变；官方 CPU RTF 0.091–0.15 → 5s 句 0.5–0.8s <1s；
3. 与 M2/M3/M7 同属 sherpa-onnx 栈，官方集成包下载即用（878MB，GitHub release 本机通路已验证），一个依赖部署全链路；
4. Apache-2.0，许可比 SenseVoice 的 FunASR Model License 干净；
5. **回退开关**：主播实机（CPU 弱于 Xeon）若实测 RTF>0.3 → 切回 SenseVoiceSmall int8（228MB，同 API，配置项一行切换 ⚠️待实测）；
6. 可选 GPU 档（不默认）：llama.cpp GGUF Q4（0.6B ≈1–1.5GB 显存 ⚠️估算，sm_86 路径已被 Fun-ASR 移植实测），仅游戏显存 ≤7–8GB 或空闲时启用。

真流式（边说边出字）不是本场景刚需：对话是"一句指令→执行"，VAD 判停后 1s 内出全文即可。若后续要"实时字幕 overlay"，再引入 streaming-paraformer/zipformer 双轨。

### M5 编排语言/框架：候选与推荐

| 候选 | 优点 | 缺点 | 结论 |
| ---- | ---- | ---- | ---- |
| **Python 3.11+ asyncio（推荐）** | sherpa-onnx 官方 Python API（KWS/VAD/ASR/TTS 全覆盖）；httpx+aiohttp SSE 生态成熟；开发迭代最快；PyAudioWPatch 直接可用 | GIL（但推理都在 C++/onnxruntime 内，Python 只做调度，实际无碍） | ✅ 首选 |
| Rust（sherpa-rs / ort crate） | 单二进制、低内存 | 开发慢、SSE/托盘/音频设备热插拔都要自己拼 | 性能瓶颈出现后再局部重写 |
| C++（sherpa-onnx C API） | 最省资源 | 开发成本最高 | 排除 |
| Node/C# 混合 | opencode SDK 是 JS | 音频/推理生态弱于 Python | 排除 |

**推荐**：单 Python 进程 + asyncio；每个重负载推理（KWS 常驻、ASR 突发、TTS 突发）放独立线程/进程池，帧流走有界队列；`psutil` 设置 BELOW_NORMAL 优先级。进程拓扑：`voice-code.exe(python)` + 子进程 `opencode serve`。

### M6 opencode Server 集成：headless 复用现有配置 + REST 用法

#### 本机现状（已核实，2026-09-23）

- 全局配置 `C:\Users\Administrator\.config\opencode\opencode.json`（885B）：
  - `model: "anthropic/claude-sonnet-4-5"`（默认主模型，走云端 API，**不占本地显存**）；
  - 自定义 provider `minimax`：`npm: @ai-sdk/anthropic`、`baseURL: https://api.minimaxi.com/anthropic/v1`、模型 `MiniMax-M2.7`（apiKey 已配置，此处**不记录密钥**）；
  - `server.port: 4096`；`shell: "pwsh"`；`lsp: true`；`snapshot: true`；`autoupdate: true`；`share: "manual"`；
  - `mcp.playwright`（local，chrome）。
- 全局 `AGENTS.md`（含 kill 进程前必须按端口/PID/命令行过滤等规则）、全局 `agent/deepthink.md`（deepthink subagent 定义）；凭据在 `C:\Users\Administrator\.local\share\opencode\auth.json`；插件依赖 `@opencode-ai/plugin 1.14.28` 已就位。
- 项目侧 `D:\work\voice-code\.agents\skills\connect-gitee\SKILL.md`——证明 `.agents/skills/<name>/SKILL.md` 的项目级 skill 发现路径已在用（M8 的 `voice-end` skill 可放同处）。

#### 复用方式

opencode 配置是**合并加载**的（官方 Config 文档）：`远程组织配置 → 全局 ~/.config/opencode/opencode.json → OPENCODE_CONFIG → 项目 opencode.json → .opencode/.agents 目录（agents/commands/skills/plugins）→ OPENCODE_CONFIG_CONTENT → 托管配置`。因此：

1. `opencode serve` **不需要任何额外配置**即可继承上述全局 provider/model/mcp/AGENTS.md/skills/agents；
2. **工作目录决定项目**：编排器应以"主播要操作的目标仓库"为 cwd 启动 serve（或 `--cwd` 类参数 ⚠️以 `opencode serve --help` 为准）；voice-code 自身目录亦可作为默认演示项目；
3. 如需为语音场景覆盖（例如换更快/更便宜的模型、放宽 permission），放**项目级 `opencode.json`** 或用 `OPENCODE_CONFIG`/`OPENCODE_CONFIG_CONTENT` 环境变量注入，不动全局配置；
4. 与已开的 TUI 互不干扰：官方文档明确 `opencode serve` 会启动**新的独立 server**（TUI 自带随机端口 server）。

#### 启动与鉴权

```bash
# 在目标项目目录（headless）
opencode serve --port 4096 --hostname 127.0.0.1
# 可选：HTTP Basic Auth（只绑 127.0.0.1 时可不设）
OPENCODE_SERVER_PASSWORD=xxx opencode serve
```

#### REST/SSE 基本用法（依官方 Server 文档，2026-09-22 版）

| 用途 | 调用 |
| ---- | ---- |
| 健康检查/版本 | `GET /global/health` → `{healthy, version}` |
| OpenAPI 3.1 规范（类型以此为准） | `GET /doc` |
| 校验生效配置 | `GET /config`；可用模型 `GET /config/providers`；agent 列表 `GET /agent`；命令列表 `GET /command` |
| 新建会话 | `POST /session`，body `{"title":"voice-…"}` → `Session{id,…}` |
| 发消息（同步等结果） | `POST /session/:id/message`，body `{"agent":"build","model":{"providerID":"anthropic","modelID":"claude-sonnet-4-5"},"parts":[{"type":"text","text":"<ASR文本>"}]}`（还支持 `noReply/system/tools` 字段） |
| 发消息（异步，配合 SSE） | `POST /session/:id/prompt_async` → 204 |
| 事件流 | `GET /event`（SSE，首个事件 `server.connected`，随后是总线事件：消息/part 增量、session 状态、permission 请求等，⚠️具体事件名以 /doc 与实测为准） |
| 会话状态/中止 | `GET /session/status`；`POST /session/:id/abort` |
| **权限应答（无键盘关键）** | `POST /session/:id/permissions/:permissionID`，body `{"response":"allow"}` —— SSE 收到 permission 事件后由编排器自动放行或语音询问主播后应答 |
| 执行斜杠命令 | `POST /session/:id/command` |
| 历史/回滚 | `GET /session/:id/message`；`POST /session/:id/revert` |

**语音场景的 permission 策略（重要）**：本机全局配置未设置 `permission` 字段，opencode 默认放行所有操作；但存在项目级/托管级 deny 规则的可能（如 external_directory）。无键盘约束下推荐：语音专用项目的 `opencode.json` 里显式配置 `permission`（如 `edit/bash` 常用命令 allow、危险命令 deny），同时编排器实现"SSE permission 事件 → TTS 播报请求内容 → 主播口头'同意/拒绝' → ASR 判定 → REST 应答"的闭环作为兜底。

**推荐集成形态**：Python `httpx.AsyncClient` + SSE 增量解析；session-per-activation；`agent` 固定为语音定制 agent（可新建 `.opencode/agents/voice.md`，system prompt 里写"回复必须口语化、短句、不用 Markdown、可用 voice-end skill 结束"）；流式 part 按标点切句 → M7 边生成边播。

### M7 TTS：候选与推荐

| 候选 | 中文自然度 | 体积 | 显存/CPU | 延迟/流式 | 授权 | 结论 |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| **sherpa-onnx Kokoro `kokoro-multi-lang-v1_1`（推荐默认）** | 好（82M 参数小模型里第一梯队；中英 103 音色） | onnx 311MB | **CPU 即可，0 显存**；RPi4-4线程 RTF 3.19 → 桌面 CPU 外推 ~0.3–0.6 ⚠️ | 非流式，按句合成；首句 0.3–1s ⚠️ | Kokoro 权重 Apache-2.0 ⚠️以模型卡为准 | ✅ 默认 |
| sherpa-onnx `vits-melo-tts-zh_en`（MeloTTS） | 中上（单一音色） | 163MB | CPU，0 显存；RPi4-4T RTF 2.52 → 桌面外推 ~0.3 ⚠️ | 非流式，句级 | MIT | ✅ 更轻备选（与 Kokoro A/B 试听定夺） |
| sherpa-onnx `matcha-icefall-zh-baker` | 中（单女声，标贝数据） | 73MB | CPU 极轻（RPi4 RTF 0.39 → 桌面 ~0.05） | 句级、最快 | Apache-2.0 ⚠️ | 低配兜底/提示音级播报 |
| piper (zh_CN-huayan) | 中下（机械感明显） | ~60MB | CPU 极轻 | 句级 | MIT | 不推荐（中文质量弱于上述） |
| **CosyVoice2-0.5B / Fun-CosyVoice3-0.5B（音质升级可选）** | **很高**（zero-shot 克隆、instruct 情感/语速、18+ 方言；CV2 test-zh CER 1.45%，CV3-RL 0.81%） | 权重 ~1GB 级 | **GPU 建议**：估 2.5–4GB 显存 ⚠️需实测能否与游戏共存；CPU 太慢 | **双向流式，官方标称最低 150ms 首包**（CV3；CV2 论文同 150ms） | 代码 Apache-2.0；权重 ⚠️以模型卡为准 | ✅ 若实测显存 ≤3GB 且游戏留得出，则作"高自然度模式" |
| GPT-SoVITS v2 ProPlus | 高（1 分钟微调音色克隆；zh/en/ja/ko/yue） | 权重数 GB 磁盘 | GPU 推理 RTF 0.028(4060Ti)/0.014(4090)（官方 README）；显存社区口径 ~2–4GB ⚠️ | 非流式整句 | MIT | 备选（想要"主播自己的声音"时用；工程链路较重） |
| F5-TTS | 高 | 0.3B | GPU RTF 0.147(PyTorch)/0.04(TRT-LLM L20) | 非流式 | 代码 MIT，**权重 CC-BY-NC（禁商用）** | 排除优先（授权限制），个人使用可试 |
| IndexTTS 1.5/2 | 高（bilibili） | 1.5B 级 | 显存更重 ⚠️ | 非流式 | ⚠️ | 暂不推荐（3080 共存压力大） |

**推荐**：双层策略——
- **默认层（保证共存）**：sherpa-onnx CPU TTS，Kokoro-multi-lang-v1_1 与 vits-melo-tts-zh_en 二选一（先各合成 10 条游戏场景常用回复盲听投票）；0 显存、句级延迟可接受、与 KWS/VAD/ASR 同一依赖栈。
- **增强层（可选开关）**：CosyVoice2-0.5B（本地常驻小服务，streaming 模式），仅当 `nvidia-smi` 探测游戏占用后剩余显存 ≥4GB 时启用 ⚠️；带来 150ms 级首包与明显更自然的韵律/方言能力。
- 播报工程细节：句级流水线（SSE 文本 → 按 `。！？；\n` 切句 → TTS 队列 → 播放队列）；首句优先；数字/代码块读法归一化（代码 diff 不逐字念，念摘要——由 M6 的 voice agent system prompt 约束 LLM 输出口语化摘要）。

### M8 结束对话 skill：设计与推荐

依官方 Agent Skills 文档：skill = `SKILL.md`（frontmatter 必须有 `name`、`description`；name 须与目录名一致、小写连字符），发现路径含 `~/.config/opencode/skills/<name>/`、项目 `.opencode/skills/<name>/`、`.agents/skills/<name>/`（本项目已用后者）；模型通过内置 `skill` tool 按需加载，可用 `permission.skill` 模式控制。

**推荐实现（三通道）**：
1. 新建 `.agents/skills/voice-end/SKILL.md`：描述"当主播表达结束/告别/收工意图时，先调用 `voice_control` 工具（action=end），再用一句话口语化道别"；
2. opencode **plugin**（`~/.config/opencode/plugins/voice.js`，本机已有 `@opencode-ai/plugin` 依赖）注册自定义 tool `voice_control`，实现为 `POST http://127.0.0.1:<orchestrator_port>/control {action:"end"}`（⚠️插件 API 细节以 /docs/plugins 与 /docs/custom-tools 为准）；
3. 兜底 A：voice agent 的 system prompt 要求结束语后输出 `[VOICE_END]`，M5 在 SSE 文本流上正则匹配；兜底 B：M5 直接对 ASR 文本做规则/轻量分类（"结束|退出|收工|拜拜|就这样|不用了"），零 LLM 往返；兜底 C：ACTIVE 静默超时（如 5 分钟）自动结束。

### M9 焦点/交互适配：技术要点（无独立重型选型）

- 托盘：`pystray`（Python，跨后端，Win 下用 Win32 API，不创建可聚焦窗口）；
- 提示音：预生成 wav（激活确认"叮"、结束"咚"、错误"buzz"），经 M7 播放通道混出；
- 全屏检测：枚举前台窗口 `GetWindowRect` 对比屏幕分辨率 + `DwmGetWindowAttribute`（cloaked）判断游戏是否全屏独占，决定 Toast 是否静默；
- Overlay（可选）：本地 `http://127.0.0.1:<port>/overlay` 网页 + OBS 浏览器源（离屏渲染，绝不抢焦点），显示当前状态/最近转写/最近回复；
- 音量 ducking（可选）：Windows Core Audio `IAudioSessionControl` 按进程调低游戏音量，无焦点操作；
- 红线清单：全程禁止 `SetForegroundWindow`、`BringWindowToTop`、模态对话框、`console` 窗口（pythonw/服务化启动）。

---

## 显存/性能预算

前提：RTX 3080 10GB，与游戏同机同时运行；本机 opencode 的 LLM 走云端 API（anthropic/claude-sonnet-4-5、MiniMax-M2.7），**本地无 LLM 显存开销**——这是全链路能塞进 10GB 共存的关键。

### 显存预算（推荐方案：全 CPU 推理）

| 组件 | 运行位置 | 显存 | RAM（估） |
| ---- | ---- | ---- | ---- |
| M1 采集 + M9 适配 | CPU | 0 | ~100MB |
| M2 KWS（sherpa-onnx int8） | CPU 1 线程 | 0 | ~80–150MB |
| M3 VAD（Silero onnx） | CPU 1 线程 | 0 | ~30MB |
| M4 ASR（Qwen3-ASR-0.6B int8 onnx，v3） | CPU 1–2 线程 | 0 | ~1.5–2.5GB ⚠️（含 878MB 权重映射；SenseVoice 回退档 ~1GB） |
| M7 TTS（Kokoro/Melo onnx） | CPU 2–4 线程（突发） | 0 | ~0.8–1.5GB ⚠️ |
| M6 opencode serve（node） | CPU | 0 | ~0.3–0.6GB ⚠️ |
| M5 编排器（python） | CPU | 0 | ~150–300MB |
| **合计（本工具）** | — | **≈0（仅桌面合成器基础占用）** | **≈3–5.5GB** |
| 游戏 | GPU | 6–9.5GB | — |

可选 GPU 加速档（需实测后开关，v3）：ASR 用 llama.cpp GGUF Q4 0.6B +1–1.5GB ⚠️估算（游戏显存 ≤7–8GB 时启用）；TTS 用 CosyVoice2-0.5B +2.5–4GB ⚠️。两者不建议同时开。**TRT 路线不落地**（TRT-LLM 无该模型；TRT-EP 3–4GB 与共存冲突、收益仅 0.6s→0.1s，2026-09-24 调研结论）。

### CPU 预算（假设 8 核以上桌面 CPU ⚠️以主播实机为准）

| 组件 | 常态 | 突发 |
| ---- | ---- | ---- |
| KWS 常驻 | ~5–10% 单核 ⚠️ | — |
| VAD（仅 ACTIVE 态） | <2% 单核 | — |
| ASR | 0 | Qwen3-0.6B int8 RTF 0.09–0.15 → 说话期约 15–30% 单核（4线程口径折算 ⚠️需实测） |
| TTS | 0 | RTF≈0.3–0.6 ⚠️ → 播报期 1–2 核 |
| 采集/编排 | ~2% | — |

对策：进程 BELOW_NORMAL 优先级；onnxruntime `intra_op_num_threads` 限 1–2；TTS 合成避开 KWS 线程绑核。目标：游戏帧率影响 <3% ⚠️需实盘 A/B 验证。

### 端到端延迟预算（不含 LLM 思考）

| 环节 | 延迟 |
| ---- | ---- |
| 激活词命中 | 160–320ms（chunk）+ 平滑 ≈ 0.3–0.5s |
| 说完→判停（VAD 静音窗） | 0.6–0.8s |
| ASR（5s 语音，Qwen3-0.6B int8，RTF 0.09–0.15） | 0.5–0.8s |
| opencode 首 token（云端 LLM） | 1–5s ⚠️取决于模型/网络；工具执行另计 |
| TTS 首句（CPU 方案） | 0.3–1s ⚠️（CosyVoice2 流式官方标称 150ms） |
| **语音说完→开始回话（不含 agent 干活）** | **≈1.5–2.5s** |

---

## 风险与待实测清单

1. **KWS 实盘误触发/漏检率**：游戏音效+队友语音环境下，zh-en-3M 模型对自定义激活词的 FAR/FRR 无公开数据，需录实盘音频回测（阈值、chunk、降噪开关三维调参）⚠️。
2. **barge-in 自激**：TTS 从耳机漏音进麦克风可能误触发 KWS/ASR，需实测"播报期间 KWS 阈值提升/暂停"策略；必要时引入 AEC（WebRTC AEC3 ⚠️工程量）。
3. **Qwen3-ASR-0.6B 桌面 CPU RTF（v3 更新）**：官方 0.091–0.15 来自 Xeon 4 线程 int8，主播实机 CPU 型号未知、LLM-style 解码对单核更敏感，需实测；**>0.3 回退 SenseVoiceSmall（同 API 一行切换）**；仍不达标再考虑 GGUF GPU 档 ⚠️。
4. **CosyVoice2-0.5B 在 3080 上与游戏共存的真实显存**（含 CUDA context、KV/flow 缓存）：官方无数字，社区口径 2.5–4GB，必须先 `nvidia-smi` 压测再决定是否默认开启 ⚠️。
5. **Kokoro 中文自然度主观评价**：103 音色中中文音色质量参差，需盲听选音色；不满意则升级到 CosyVoice2 或 GPT-SoVITS 微调 ⚠️。
6. **模型授权**：Qwen3-ASR（Apache-2.0，干净）、SenseVoiceSmall 权重（FunASR Model License，商用需署名，现为回退档）、Kokoro 权重、sherpa KWS 模型、CosyVoice2 权重授权各异；F5-TTS 权重 CC-BY-NC、openWakeWord 预训练模型 CC BY-NC-SA 已因此降级/排除。若工具仅个人使用风险低，分发前需逐一核对模型卡 ⚠️。
7. **opencode SSE 事件名与 message part 结构**：文档只给出端点，未枚举事件类型，需以 `GET /doc`（OpenAPI 3.1）与实测为准 ⚠️。
8. **opencode plugin 自定义 tool 的准确 API**（注册方式、schema、权限）：以 /docs/plugins、/docs/custom-tools 为准；若插件路线受阻，M8 退化为"文本标记+编排器直判"双兜底（已设计，无单点依赖）⚠️。
9. **`opencode serve` 的 cwd/项目选择**与 voice 专用 agent 的 `permission` 白名单需要联调：无键盘场景下任何 `ask` 权限都会阻塞会话，必须自动应答或预先 allow ⚠️。
10. **蓝牙耳机麦克风**：Hands-free 模式 8/16k 窄带音质对 ASR 的影响需实测（Silero 支持 8k；Qwen3-ASR 输入按 16k 上采样送入，窄带对 LLM-style 解码影响 ⚠️待实测，回退档 SenseVoice 支持 8k），KWS 精度同样待验证 ⚠️。

## 参考资料（2026-09-23 核实；v3 ASR 条目 2026-09-24 增补）

- **Qwen3-ASR 官方仓库/博客（0.6B/1.7B 开源、Apache-2.0、benchmark 表）**：https://github.com/QwenLM/Qwen3-ASR 、https://qwen.ai/blog?id=qwen3asr 、arxiv.org/abs/2601.21337
- **sherpa-onnx Qwen3-ASR 集成（CPU int8 包 878MB、RTF 实测）**：https://github.com/k2-fsa/sherpa-onnx/pull/3399 、#3409；ModelScope `Qwen/Qwen3-ASR-0.6B`
- Qwen3-ASR TRT/GPU 调研（2026-09-24，结论不落地）：TRT-EP 社区版 https://github.com/ShirasawaSama/Qwen3-ASR-TensorRT （0.6B fp16 ~3-4GB，Windows 实测非 3080）；llama.cpp GGUF（mradermacher/Qwen3-ASR-1.7B-GGUF）；SenseVoice 官方 https://github.com/FunAudioLLM/SenseVoice （回退档）
- opencode Server / Config / Agent Skills / Plugins 文档：https://opencode.ai/docs/server/ 、/docs/config/ 、/docs/skills/ 、/docs/plugins/ 、/docs/custom-tools/
- sherpa-onnx KWS 预训练模型（zh-en-3M、wenetspeech-3.3M）：https://k2-fsa.github.io/sherpa/onnx/kws/pretrained_models/index.html
- sherpa-onnx SenseVoice（模型体积/RTF/伪流式）：https://k2-fsa.github.io/sherpa/onnx/sense-voice/index.html 、/pretrained.html
- sherpa-onnx TTS RTF 表（melo/kokoro/matcha/piper）：https://k2-fsa.github.io/sherpa/onnx/tts/pretrained_models/rtf.html
- sherpa-onnx Online Paraformer（流式备选）：https://k2-fsa.github.io/sherpa/onnx/pretrained_models/online-paraformer/index.html
- Silero VAD：https://github.com/snakers4/silero-vad （MIT，~2MB，<1ms/chunk）
- SenseVoice：https://github.com/FunAudioLLM/SenseVoice （llama.cpp/GGUF CPU 运行时、FunASR 部署、许可澄清 issue #334）
- whisper.cpp（内存表 tiny→large、内置 Silero VAD、量化）：https://github.com/ggml-org/whisper.cpp
- CosyVoice（CV2/CV3、流式 150ms、评测表）：https://github.com/FunAudioLLM/CosyVoice
- GPT-SoVITS（RTF 0.028@4060Ti、MIT、多语言）：https://github.com/RVC-Boss/GPT-SoVITS
- F5-TTS（RTF、CC-BY-NC 权重）：https://github.com/SWivid/F5-TTS
- openWakeWord（仅英文、性能指标、Porcupine 对比）：https://github.com/dscripka/openWakeWord
- PyAudioWPatch（WASAPI loopback）：https://github.com/s0d3s/pyaudiowpatch
- Porcupine（商业授权备选）：https://picovoice.ai/platform/porcupine/
- 本机配置：`C:\Users\Administrator\.config\opencode\opencode.json`（server.port 4096、model anthropic/claude-sonnet-4-5、provider minimax/MiniMax-M2.7、shell pwsh、mcp playwright；apiKey 不在本文档记录）、`agent\deepthink.md`、项目 `.agents\skills\connect-gitee\SKILL.md`
