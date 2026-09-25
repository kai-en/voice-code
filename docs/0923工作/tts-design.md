# TTS 模块详细设计 (M7 VoxCPM1.5)

> 2026-09-24 工作记录。选型变更实录：modules.md v3 原推 sherpa-onnx Kokoro CPU 档 → 用户拍板试 VoxCPM → 深调研（版本谱系/常驻/量化）+ 本机实测后**定版 VoxCPM1.5**（0.8B，44.1kHz，Apache-2.0）。上游：`docs/0923工作/modules.md`（TTS 行需按本文勘误）。

## 0. 决策记录（实测数字说话，i7-11700K + RTX 3080 10GB）

| 事实 | 数字 | 出处 |
| ---- | ---- | ---- |
| 版本谱系 | 1.0=0.5B(16k,Legacy) / **1.5=0.8B(44.1k,Stable)** / 2=2B(48k,4.6GB)。"1.5"是版本号非参数量 | 官方 README 版本表（jsDelivr） |
| 权重 | model.safetensors 1.60GB + audiovae 346MB（ModelScope `OpenBMB/VoxCPM1.5`，aria2c 16 连 20s 下完） | 本机 |
| dtype | bf16；**sm_86 上 fp16 零收益**且官方源码注释自证低精度会数值漂移 | deepthink 读源码 |
| 显存 | torch 峰值 2.73GB；**nvidia-smi 口径常驻 ~3GB / 峰值 ~4GB**（+CUDA context 0.3-0.6 + 碎片）；128MB KV cache 预分配固定 | 实测+源码 |
| RTF | 无 compile 2.05 → **triton-windows 3.2 + optimize=True = 0.40**（4-5s 句合成 1.5-2s） | 实测 |
| 一次性代价 | 首次 generate 触发 torch.compile 预热 **~150s**（进程启动阶段完成） | 实测 |
| 量化结论 | int8 weight-only **不提速**（瓶颈=kernel 发射/同步 >95%，timesteps 10→4 仅降 25% 佐证），仅显存告急预案（−0.7GB）；TRT 全家 Windows+消费卡死路 | deepthink Q2 |
| 后手 | 要再快 3 倍：VoxCPM.cpp GGUF Q8_0（4060Ti 实测 0.56，RTX40/30 系兼容）或 nano-vllm（flash-attn win wheel 难产）；**当前 0.4 达标不折腾** | deepthink |

## 1. 职责与边界

- 输入：`speak(text)`（M5 在 THINKING→SPEAKING 时逐句调用，或整段丢入由 M7 分句）。
- 输出：主播耳机播放；事件 `SpeakStart/SpeakFinish/Interrupted` → M5。
- 不负责：回复文本生成（M6）、句子级切分策略（M6 按 SSE 标点切句为主，M7 的二次分句仅保险）、提示音 earcon（M9 复用本播放通道，`speak_priority()` 预留）、音量 ducking（M9）。
- 不做：voice cloning / prompt_wav（0.8B 内置音色先跑通；`reference_wav_path` 参数透传留后手）、denoiser（`load_denoiser=False`，省一份模型+显存）、WinRT/Kokoro 兜底（A 方案已达标）。

## 2. 线程模型（CUDA Graph 兼容是硬约束）

官方 FAQ：torch.compile 的 CUDA Graph 与**多线程后台调用不兼容**→ **模型加载、warm、全部 generate 调用收敛到唯一 TTS 线程**（`_run` 循环）；其他线程只允许 `speak()` 入队与 `stop()` 置旗。播放同线程顺序执行（合成→播放→下一句，天然流水：句子 n 播放期间句子 n+1 已在队列等待，**不**并发合成，避免双份激活峰值）。

## 3. 组件与行数预算（≤200，编码后按全局纪律勘误）

| 块 | 预算 |
| ---- | ---- |
| 常量+`TtsConfig`(6 项)+事件 dataclass×3 | 30 |
| `SdPlayer`：sounddevice OutputStream 分块写 + `cancel()`（barge-in） | 25 |
| `TtsEngine`：`start`（加载+warm+起线程）/`stop`/`speak`（分句入队）/`flush_now`；`_run` 合成→播放→事件；stats | 90 |
| 装配 `start_tts(cfg, on_event=None)`（注入点：`model_factory`/`player` 测试可 Fake） | 15 |
| **合计** | **160** |

不计入：`scripts/m7_tts_say.py`、`human-test/m7_t7b_tts-asr-loop.py`。

## 4. 接口

```python
def speak(text) -> int          # 返回入队句数；未启动也可调用（缓冲）
def stop()                      # 清队列+打断当前播放（不卸载模型）
def stats() -> dict             # {sent, synth_s, play_s, peak_gb, err}
ready: threading.Event          # warm 完成才置位；M5 可 await
```
显存保险：进程环境 `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`（入口脚本设置）；WoW 共存余量 ≈1.5GB 属"可行但薄"，超 10s 长句由 M5 侧拆分（M7 二次分句兜底）。

## 5. 与邻居契约

M5：进 SPEAKING `speak()`；barge-in/新指令 → `stop()`；SpeakFinish 计数归零 → 出 SPEAKING 并 `kws.set_muted(False)`（防播报自激，播报文案含激活词时尤其依赖此链路——M8/M5 设计输入）。M8：结束会话时 `stop()` 后随进程/会话清理。启动耗时（加载+150s compile）在 M10 启动流程中与 ASR/KWS 构建并行不冲突（GPU 单线程约束只限 generate）。

## 6. 测试

- 单测（CI 无 GPU）：FakeModel/FakePlayer 注入——分句正确、FIFO、stop 清队+打断、事件顺序、**synth+play 同线程断言**、speak-before-ready 缓冲。
- 真机冒烟 `scripts/m7_tts_say.py`：合成任意文本并播放，报合成/播放耗时与 nvidia-smi 峰值；用户耳朵=最终验收。
- **人类实测 T7b（一石二鸟，此前已定）**：`human-test/m7_t7b_tts-asr-loop.py`——外放播 6 已知句 → 麦回录 → Qwen3-ASR 转写 → CER 对照 + 听感评分；同时收口 M4 转写质量与 M7 音质/响度。

## 7. 配置（6 项）

```yaml
tts:
  model_dir: models/voxcpm1.5
  device: cuda
  optimize: true          # triton-windows 已装；false=调试档(RTF 2.0)
  timesteps: 10           # 官方默认；4=显存/速度换质量预案
  output_device: null     # 默认播放设备；耳机独立通道预留
  sample_warn_s: 8        # 单句超此合成时长打 WARN(防 VAE 长句峰值)
```

## 8. 风险

1. Windows triton 已知 bug（"Python int too large"，pytorch#162430）——本次实测未触发；若换版本炸：兜底 `optimize: false`（RTF 2.0 仍可用）。
2. CUDA Graph+线程约束破坏（有人从别的线程调 generate）→ 用单测③锁死；code review 项。
3. WoW 高材质 + 长句 VAE 双峰叠加 → expandable_segments + 句切 + 必要时降 `timesteps` 或 GGUF 引擎（预算外的独立进程方案）。
4. 常驻 3GB 意味着 TTS 进程不该为"偶尔播报"退出重启（加载 20s+compile 150s）；M10 生命周期=整个直播 session。
5. 播报自激（KWS 听见自己）：链路已在 §5 设计（set_muted 配合），T7b 外放回录正好实测其反面（漏音可被 ASR 识别=KWS 同样能听到）。

## 9. 里程碑

| 阶段 | 内容 | 退出标准 |
| ---- | ---- | ---- |
| M7-a (0.5d) | tts.py + 单测 + m7_tts_say 真机 | CI 绿；真机任意文本"开口说话"，合成 RTF ≤0.5、nvidia-smi 峰值 ≤4.2GB |
| M7-b (0.5d) | T7b 人类实测 + 与 M5 事件契约联调 | T7b CER ≤5% 且听感 PASS（用户耳朵）；stop 打断即时生效 |

## 10. 勘误与实测回填（2026-09-24 编码后）

- **行数核对**：`src/tts/tts.py` 有效代码 **152 行**（总 185）vs 预算 160 → **达标**（-8）。全局回归 **39 passed**（M7 新增 5：warm后ready、单线程generate约束、分句FIFO+事件序、stop清队打断、synth/play同线程、异常不杀worker）。
- **分句语义记录**：`_SPLIT_RE` 会剥掉标点，worker 收到的 text 不含 `。！？`（单测曾据此踩坑）；对 VoxCPM 无碍（不带标点也能合成），M6 切句时同样如此。
- **真机冒烟**（scripts/m7_tts_say.py，3 句 14s 音频）：ready **76s**（inductor 缓存命中；首次冷编译 150s）；端到端 16.2s（≈音频时长+首句合成 2s）；synth_s 合计 4.2s / play 12.0s，**稳态 RTF ≈0.35**；err=0。**"开口说话"验收 PASS（用户已听到）**。
- T7b 脚本已备（human-test/m7_t7b_tts-asr-loop.py，需**音箱外放**执行）。
- modules.md TTS 行已同步勘误为 VoxCPM1.5。
