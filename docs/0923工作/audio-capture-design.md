# 音频采集模块详细设计 (M1 Audio Capture)

> 2026-09-23 工作记录。

> 状态：**v2 重写**（评审决议后）。v1（自研 ring/soxr/热插拔重连的完整设计）已废弃，不再作为实现依据。
> 上游文档：`docs/overall-goals.md`、`docs/0923工作/modules.md`。

## 0. 决策记录（为什么重写）

| 决议 | 内容 | 理由 |
| ---- | ---- | ---- |
| 1 | **不做热插拔自动恢复**，改为**周期语音报警** | 需求中没有 7×24 直播承诺；设备停摆属低频事件，播报提醒 + 人工重启（鼠标操作，会话间隙）足够。删掉 v1 中最复杂的整块机器（重枚举、terminate/re-init、退避重连、断缝补偿）。 |
| 2 | **不造采集轮子**：复用 sounddevice（PortAudio）+ sherpa-onnx 官方麦克风示例模式 | 官方示例直接 `sd.InputStream(samplerate=16000, channels=1)` 即可工作，重采样/下混由 PortAudio 内建完成；v1 的 soxr 管线、格式协商、声道坑规避全部不需要自己写。 |
| 3 | **自研部分只允许 3 样**（见 §3） | 控制复杂度：W1 分发、W2 停摆报警、W3 与 M5 的契约。其余一律用轮子。 |

v1 中被删除的组件（不再实现）：`soxr.ResampleStream`、`FloatRing` 无锁多游标环形缓冲、格式协商回退、三路热插拔检测、指数退避重连器、loopback 参考流、`PlaybackReferenceProvider`、LevelMeter 遥测。若后续实测（§6 风险）打脸再按需最小引入。

---

## 1. 参考的三个轮子（直接照抄其模式）

| # | 轮子 | 借鉴什么 |
| ---- | ---- | ---- |
| R1 | `sherpa-onnx/python-api-examples/keyword-spotter-from-microphone.py` | 采集主循环写法：`with sd.InputStream(channels=1, dtype="float32", samplerate=16000) as s:` + 循环 `s.read(0.1*16000)` + `accept_waveform`；命中后立刻 `reset_stream`。 |
| R2 | `sherpa-onnx/python-api-examples/simulate-streaming-sense-voice-microphone.py` | 同一 InputStream 喂 Silero VAD + SenseVoice 的"伪流式"结构：VAD 持 `ring_buffer` 攒句、判停后整句 decode。M3/M4 与采集的衔接方式以此为准。 |
| R3 | sounddevice 官方文档（`query_devices`、`CallbackStream`/`InputStream` 阻塞读、`status` 标志） | 设备枚举/按名选择、回调/阻塞两种读模式、input overflow 状态感知。 |

轮子已解决的关注点（M1 不再写代码）：48k→16k 重采样、立体声→单声道、设备原生格式协商、PortAudio 缓冲与节拍。

## 2. 采集核心（照 R1/R2，约 60 行）

```python
# voicecode/audio/capture.py  —— 全部采集逻辑
import queue, threading, time
import numpy as np, sounddevice as sd

SR = 16000
BLOCK = int(0.02 * SR)          # 20ms，与消费端批量无关，仅回调粒度

class MicSource:
    """单设备 → 扇出。非焦点：无任何窗口操作；异常不抛出到主线程。"""
    def __init__(self, device: str | None, sinks: dict[str, queue.SimpleQueue]):
        self.sinks = sinks                       # W1：见 §3
        self.last_cb = time.monotonic()          # W2 心跳：见 §3
        self.device = _resolve(device)           # 按名匹配 sd.query_devices，见 §2.1
        self.stream = sd.InputStream(samplerate=SR, channels=1, dtype="float32",
                                     device=self.device, blocksize=BLOCK,
                                     callback=self._cb)

    def _resolve(device):
        # device=None → sounddevice 默认输入（即 Windows 多媒体默认设备）。
        # ⚠️ 官方建议配置显式设备名（默认设备角色 eMultimedia/eCommunications 错位坑，
        #    见 v1 调研 §5.1；配置向导文档里写死"请为 voice-code 指定麦克风"）。
        ...

    def _cb(self, indata, n, t, status):
        self.last_cb = time.monotonic()
        if status:                                   # overflow 等：计数，不中断
            self._status_count += 1
        frame = indata[:, 0].copy()                  # (n,1) → (n,)
        for q in self.sinks.values():
            if not q.full():                         # 满则丢最旧（W1 策略）
                try: q.put_nowait(frame)
                except queue.Full: pass

    def start(self): self.stream.start()
    def stop(self):  self.stream.stop(); self.stream.close()
```

- 停摆/异常：`sd` 流操作抛 `PortAudioError`（设备拔出）→ W2 捕获 → 进 ALERTED。
- 无自动重连、无重枚举（决议 1）。

### 2.1 设备选择

配置 `capture.device_name`（子串匹配 `sd.query_devices()`），空则默认设备并启动时打印设备名到日志 + TTS 播报"正在使用麦克风 XXX"（首次会话，让主播确认没拿错设备）。

## 3. 自研的 3 样（只有这 3 样）

### W1 帧分发（sinks 字典 + 有界队列扇出）

- 结构：`dict[str, queue.SimpleQueue(maxsize=250)]`（250×20ms = **5s 容量**，每消费者一条队列，回调线程直接 `put_nowait`）。
- 消费者：`"kws"`（常驻）、`"vad"`（**门控**：队列始终存在，但 M5 在进入 ACTIVE 态时才清空积压并放行；SPEAKING 态可选择丢弃或保留以支持 barge-in——默认保留）。
- 预卷（M3 需要的 ~200ms 激活前音频）：vad 队列消费端自行持 `deque(maxlen=10)`（20ms×10）滚动缓冲，无需环形历史，v1 的 `seek_back` 取消。
- 满丢最旧：采集新鲜度优先，丢帧计数进日志。
- 明确不做：无锁环形、多游标、asyncio 桥、电平遥测、w 游标并发论证。

### W2 停摆检测 + 周期语音报警（替代热插拔重连）

```python
# watchdog（M5 的 asyncio 循环里 1Hz 跑，不单独建线程）
async def capture_watchdog(mic: MicSource, ev: Events):
    await asyncio.sleep(3)                        # 启动宽限
    while True:
        dead = (time.monotonic() - mic.last_cb > 2.0) or mic.stream.closed \
               or mic.zero_seconds >= 5           # 连续 5s 全零（拔麦后"数字死寂"，流还活着）
        if dead and state != "ALERTED":
            state = "ALERTED"
            ev.emit(CaptureDead(reason=...))      # → M5 暂停会话、托盘变红
        if state == "ALERTED":
            ev.emit(AlertTick())                  # M5/M7：每 alert_interval_s 播一次 TTS
        await asyncio.sleep(1)
```

- 报警文案："麦克风没有声音了，请检查设备。恢复后请重启 voice-code。"（走 M7 TTS，不弹窗、不抢焦点，符合非焦点约束）
- 报警节奏：首次立即播，之后每 `alert_interval_s`（默认 60s）重播一次，直到人工重启进程。恢复手段 = 用户修好设备后用托盘菜单（鼠标）/命令行重启工具。**不做**任何进程内自动恢复。
- 报警期间 KWS 自然失聪（没帧了），符合预期：主播看得见托盘红了、听得见循环提醒。

### W3 与 M5 的事件契约（唯一对外接口）

| 事件 | 产生方 | M5 动作 |
| ---- | ---- | ---- |
| `KwsHit{keyword}` | M2（消费 kws 队列后） | 开 vad 门 → ACTIVE；`reset_stream`（R1 契约，M2 内部） |
| `AsrText{text}` | M4 | THINKING → 发 opencode |
| `CaptureDead{reason}` | W2 | 会话中止 + 进入报警循环（W2） |
| `AlertTick` | W2 | M7 播报警文案 |
| 静默超时 / `voice-end` | M5/M8 | 关 vad 门 → 回 IDLE |

对外没有 subscribe/unsubscribe API、没有 FrameConsumer 类——sinks 字典在构造时写死两个 key，够简单且无动态竞态。

## 4. 配置（全部 M1 配置项）

```yaml
capture:
  device_name: null        # 建议显式配置；null=系统默认 ⚠️见 §2.1
  alert_interval_s: 60     # 周期语音报警间隔
  stall_timeout_s: 2.0     # 心跳超时判停摆
  zero_timeout_s: 5.0      # 全零死寂超时
  sink_queue_len: 250      # 5s @ 20ms
```

（v1 的 resampler/loopback/reconnect/level_meter/silence_watchdog/debug 等 40+ 项全部删除。）

## 5. 测试

### 5.1 自动化（CI，无音频设备也能跑）

| 层 | 用例 | 说明 |
| ---- | ---- | ---- |
| 单元 | `_cb` 扇出：两队列等长、满丢最旧计数、status 标志不崩 | Fake 数组直调 |
| 单元 | watchdog 状态机：心跳停 2s→CaptureDead→AlertTick 周期正确（fake clock） | pytest-asyncio |
| 集成 | 无设备 CI：`sd.query_devices()` 为空 → 启动即 ALERTED 并播报（断言不弹窗、不崩） | Linux/无麦 CI 天然覆盖 |

### 5.2 单模块实测（本机 = 目标 3080 直播机，逐项打勾）

**环境矩阵**（每项设备跑 T1/T2/T3）：

| 设备 | 型号/角色 | T1 | T2 | T3 | 备注 |
| ---- | ---- | ---- | ---- | ---- | ---- |
| 板载 Realtek 麦 | 默认设备 | ☐ | ☐ | ☐ | 48k 立体声 |
| USB 耳麦 | 显式 `device_name` | ☑ | ☑ | ☐ | 中文名含括号；T1=冒烟帧率比1.00，T2=人类PASS(见 human-test/RESULTS-2026-09-24.md) |
| 蓝牙耳机 Hands-Free | 反面教材 | ☐ | ☐ | ☐ | 16k/8k，验证警告 |
| VoiceMeeter（可选） | 虚拟路由 | ☐ | ☐ | ☐ | 44.1k 验证 SRC |

**用例**（工具自备：`sd.rec` 录 wav、`psutil` 采 CPU、日志 stats）：

| # | 用例 | 步骤 | 通过标准 |
| ---- | ---- | ---- | ---- |
| T1 基线正确性 | 启动 M1，kws/vad 双队列拉 60s | 设备以 `InputStream(samplerate=16000)` 打开成功（任一设备抛 `BadSampleRateError` → 记录并触发 §6-1 预案评审 ⚠️）；帧率 50±2 帧/s；两队列长度差 ≤2；总时长守恒 ±1% |
| T2 音质肉眼检 | 对拍掌×10 + 数"123456789" + 正常说话各录 30s 存 wav | 试听无咔哒/断续；拍掌峰值间隔 ≥300ms 不吞并；数数无掉字（人耳判，为 M4 铺路） |
| T3 停摆报警与恢复 | 运行中拔 USB 麦；另测：麦克风物理静音键。报警状态下插回麦重启工具 | 拔麦/死寂 ≤7s 听到首条"麦克风没有声音了…"并每 60s 重复、托盘变红、无弹窗；重启后恢复正常采集 |
| T4 双声道下混 | USB 麦（2ch）录"只在右麦吹气"（或对左右孔分别拍掌） | mono 输出两位置均有信号、音量差 ≤6dB；若明显只有一侧 → 启用 §6-2 兜底（channels=2+自行下混）⚠️ |
| T5 真消费者冒烟 | kws 队列挂真实 sherpa-onnx KeywordSpotter（用激活词"小码小码"），10 次呼唤间隔 30s | 命中 ≥9/10；命中后 `reset_stream` 无异常；vad 门控：ACTIVE 开窗前积压被清空、开窗后有帧 |
| T6 资源与稳定 | 矩阵全设备各跑 30min（含一次 10min 纯播报干扰：M7 循环播长句）+ 一台设备跑 2h 待机（只消费 kws，vad 关门） | CPU ≤2% 单核（psutil 均值）、内存增量 <50MB；2h 内 dropped=0、`last_cb` 无 >2s 空洞 ⚠️记录 poll 线程+`timeBeginPeriod` 实际开销 |

**记录**：结果回填本表并归档 `tests/m1/RESULTS-<日期>.md`（设备名/驱动版本/CPU 型号 + T1–T6 数据），作为 M2/M4 实测的准入依据。

## 6. 风险与实测项（保留的少量）

1. ⚠️ **PortAudio 内建 SRC 质量/可用性**：官方示例假定 `samplerate=16000` 可被接受；个别驱动可能抛 `BadSampleRateError`。预案（此时才引入第 4 个组件）：原生率打开 + soxr 兜底——**默认不实现**。
2. ⚠️ **mono 下混行为**：PA 内部 2→1 可能只取左声道（v1 源码结论）；耳麦单麦阵列无碍，双麦主播实测确认音量；必要时配置指定 `channels=2` + `(L+R)/2`（一行代码，不算新组件）。
3. ⚠️ **蓝牙耳机 HFP 劫持**（v1 风险 1 依然成立，与热插拔无关故保留）：常驻开麦会把 BT 耳机游戏声压成窄带。文档引导：蓝牙耳机主播需将 voice-code 麦克风设为独立设备，或接受音质降级；检测到设备名含 "Hands-Free" 时启动即 TTS 警告一次。
4. TTS 播报自激误唤醒：与 M1 解耦，策略在 M2/M5（SPEAKING 态提高 KWS 阈值），M1 不再提供任何 AEC 接口。

## 7. 里程碑

| 阶段 | 内容 | 退出标准 |
| ---- | ---- | ---- |
| M1-a（~1d） | MicSource + W1 扇出 + 设备选择 + §5 单元/集成测试 | 真机 10min 采集，kws/vad 队列等长，CPU ≤2% 单核 |
| M1-b（~0.5d） | W2 watchdog + 报警闭环（与 M5/M7 联调） | 拔麦 ≤7s 听到首条报警，循环播报，零弹窗零崩溃 |

## 8. 参考

- R1: https://github.com/k2-fsa/sherpa-onnx/blob/master/python-api-examples/keyword-spotter-from-microphone.py （2026-09-23 已核实全文）
- R2: https://github.com/k2-fsa/sherpa-onnx/blob/master/python-api-examples/simulate-streaming-sense-voice-microphone.py （目录清单已核实存在）
- R3: sounddevice 文档 https://python-sounddevice.readthedocs.io/
- v1 调研结论中仍有效的部分（PortAudio 默认设备角色 eMultimedia、蓝牙 HFP 行为、2→1 下混取左声道）引用于 §2.1/§6，源码依据见 v1（git 历史）。


## 9. 进度记录

- 2026-09-24 **编码完成**：src/audio_capture/capture.py（MicSource/DropOldestQueue/resolve_device/StallWatchdog）。
- 2026-09-24 **单测通过**：17 passed（tests/test_m1_capture.py，含设备索引解析回归）。
- 2026-09-24 **T1 冒烟 PASS**：scripts/m1_smoke.py，默认 USB 麦 3s，帧率比 1.00、双队列无丢失、CPU≈0%、44.1k→16k SRC 正常（§6-1 风险未触发）。
- 2026-09-24 **T2/T4 人类实测 PASS**（录音 30s 试听无瑕疵、10 拍掌不吞并、数数无掉字）：见 human-test/RESULTS-2026-09-24.md 与 human-test/recordings/。
- 停摆报警链路已用软件停流验证（stream dead→立即 AlertTick→60s 循环），**物理拔线（T3）**、真 KWS 消费者（T5，依赖 M2）、30min/2h 资源长跑（T6）待做。
- 判定：**M1 模块功能开发完成（v2 范围内）**，剩余为排期内的真机补充实测，不阻塞下游模块开工。
