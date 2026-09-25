# ASR 链路详细设计 (M3 VAD 切句 + M4 Qwen3-ASR 转写)

> 2026-09-23 工作记录（设计要点由 deepthink 2026-09-24 调研产出，证据链：本机 venv sherpa-onnx 源码、官方示例全文、PR #3399/#3409/#3472/#3873/#3907/#3912、hf-mirror LFS API）。上游：`modules.md` v3、`audio-capture-design.md` v2、`kws-design.md`。

## 0. 轮子盘点

| 复用 | 内容 |
| ---- | ---- |
| R1 | 官方 `simulate-streaming-sense-voice-microphone.py`（全文核实）：攒 buffer→512 窗喂 VAD→`while not vad.empty(): 取 front.samples→喂 recognizer→decode→print` 最小循环，M3+M4 照抄其结构与参数命名 |
| R2 | sherpa-onnx **≥1.13.8** 内置全部 Qwen3-ASR 修复链（静音幻觉 #3907、语言前缀剥离 #3472、centered-STFT #3873、PRNG 竞争 #3912）。本机 1.13.8 恰为最低干净版本：**pin 死，勿降级勿乱升** |
| R3 | `OfflineRecognizer.from_qwen3_asr(...)` 工厂（本机 `offline_recognizer.py` L461-552 核实）：conv_frontend/encoder/decoder/tokenizer 目录 + `hotwords` 逗号分隔原生支持；端点状态机/最长句保护/tokenizer/BPE/prompt 拼装全在 C++ |
| R4 | M1 `DropOldestQueue`（段队列复用）、M2 的 `KwsWorker._run` 异常不崩线程骨架 |

**一律不自研**：VAD 推理与攒句环形缓冲、端点/强制切句（Silero `max_speech_duration` 原生：超限自动提 threshold 到 0.9）、ASR 解码/KV/tokenizer/前缀剥离、标点恢复（模型原生）、ITN（qwen3 无，接受汉字数字）、interim 部分解码（官方字幕功能，砍掉）、rule_fsts 同音替换（后置）、段队列。

## 1. 边界与线程模型

- 一个目录两个文件：`src/asr/vad_sentence.py`(M3) + `src/asr/pipeline.py`(M4)；空占位目录 `src/vad/` 删除。
- **两线程（对官方单线程示例的刻意偏离）**：`VadSentencer` 线程（M1 vad 队列→VAD→整句段）→ `DropOldestQueue(8)` → `AsrWorker` 线程（段→decode）。理由：20s 句在弱 CPU decode 可达 2–4s，单线程内联解码会阻塞 VAD 喂入、令 M1 5s 队列溢出啃掉下一句头。VAD 基于样本流切句，解码慢只延迟不丢段。

## 2. 组件划分与行数预算（全局纪律：编码后勘误核对）

| 块 | 预算 |
| ---- | ---- |
| `vad_sentence.py`：常量+`VadConfig`+`build_vad`(fail-fast 断言 silero 存在)+`VadSentencer`(start/stop/set_active/_run：预卷 deque(10)、512 攒批、**front 拷贝后 pop**、段入队) | **≤80** |
| `pipeline.py`：常量+防御前缀 regex+`AsrConfig`(8 项)+`AsrText`+`build_recognizer`(qwen3/sensevoice 双分支)+`AsrWorker`(每句新 stream、strip、空文本过滤、RTF/err 统计)+`AsrPipeline` 门面+`start_asr` | **≤120** |
| **合计上限** | **200**（目标 ~180，对标 M2 实绩 156/165） |

不计入（M2 惯例）：`scripts/m3m4_asr_wav.py`（离线冒烟+RTF/RSS 实测）、`human-test/m3m4_t7_*.py`、`m3m4_t8_*.py`。

## 3. 模型获取（⚠️ 2026-09-24 下载实况已改写通路）

- 官方包 `sherpa-onnx-qwen3-asr-0.6B-int8-2026-03-25`（tar.bz2 **878,702,423 B**，asr-models tag）。文件与逐文件 sha256 前缀（HF LFS）：`conv_frontend.onnx` 44,148,281B `d22dc4423e09…`、`encoder.int8.onnx` 182,491,662B `60748d3e6744…`、`decoder.int8.onnx` 755,914,231B `4f6885be5959…`、`tokenizer/`(vocab.json+merges.txt+tokenizer_config.json)。
- **实下载记**：当晚 github release CDN 连接重置（AGENTS 预警兑现），转 hf-mirror `csukuangfj2/...` 逐文件 resolve（HEAD 200/len 吻合 ✅）；官方 test_wavs 在 hf 仓库是 LFS 指针（15B），**放弃**，离线测试改用：本地 `human-test/recordings/m1_t2_*.wav` + 自录素材。tarball 整体 sha256 官方未公布 ⚠️ → 以**字节数+分文件 sha256 前缀**双重校验。
- silero_vad.onnx（643,854 B）：github release 通路恢复后补下（当前 0/20B 无效文件已识别待覆盖），或 ModelScope 镜像源 ⚠️。
- 磁盘：净增 ~950MB（v3 拍板预算内）；回退档 sensevoice 包（155MB）**仅触发回退才下载**。
- 解压/组装：本设计按"逐文件直下到目录"完成，未走 tarball（bsdtar 挂起坑天然规避）。

## 4. 接口（签名级）

```python
class VadSentencer:                     # 线程：sink→VAD→on_segment(samples, start)
    def set_active(on)                  # inactive: 只滚动预卷不喂 VAD
class AsrPipeline:                      # 门面 = VadSentencer + 段队列(8) + AsrWorker
    def set_active(on)                  # True: 清积压+vad.reset()+灌 200ms 预卷   ← 兑现 M1 W1 预卷承诺
    def stats()                         # {segments,texts,empty,dropped_seg,err,rtf_last,qdepth,rss_mb}
def start_asr(cfg, mic, on_text) -> AsrPipeline   # 装配 mic.sinks["vad"]；模型进程启动即 build（激活零加载延迟，RAM 常驻）
@dataclass(frozen=True)
class AsrText: text: str; ts: float; dur_s: float   # 替代 modules.md 旧 AsrResult{text,lang?}（qwen3 lang 恒空, 砍）
```

`build_recognizer` 双分支：`qwen3`→`from_qwen3_asr(max_total_len=1024, max_new_tokens=cfg, hotwords=cfg, feature_dim=128)`；`sensevoice`→`from_sense_voice(language="auto", use_itn=True)`。事件回调在 AsrWorker 线程触发，M5 侧 `call_soon_threadsafe` 转投（同 M2 约定）。

## 5. VAD 参数（起步值→调参路径）

| 参数 | 起步 | 调法 |
| ---- | ---- | ---- |
| threshold | 0.5 | 误切段→0.6；漏检气声→0.4（±0.05 步进） |
| min_silence_s | **0.6** | 句中被切断→0.8；嫌慢→0.45（判停延迟线性）；官方麦克风示例 0.1 是字幕档，不采用 |
| min_speech_s | 0.25 | 挡拍掌/键盘瞬态；误挡"好/停"短命令→0.15 |
| max_speech_s | 20 | 超限原生强制切句；>20s 连读切两段，M5 按两条 AsrText 处理 |
| window=512 / buffer=30s | 写死 | 官方"don't change"/仅需 >max_speech |

## 6. 与 M1/M2/M5 契约

只读 `mic.sinks["vad"]`；停摆=队列断供→线程空转，恢复=重启（无断缝事件假设，同 M1/M2）；句间零历史（每段新建 stream，官方契约）；门控与 `KwsWorker.set_muted` 形态对称（M5 心智最小）；回退=配置一行 `asr.model`。

## 7. 延迟预算

说完→判停 0.65s + decode（官方 Xeon4T RTF 0.091–0.15 → 5s 句 0.46–0.75s；实机 2 线程 ⚠️0.7–1.5s）+ emit <5ms ⇒ **标称 1.1–1.4s / 实机预估 1.3–2.1s**。目标 <1s/句 ⇔ RTF<0.2，官方档达标，实机 T9 定夺。

## 8. 测试

- **单测**（CI 无模型，Fake 注入同 M2 风格）：512 攒批跨批余数正确（对齐 M2 丢帧教训）、**front 拷贝后 pop 不受篡改**、inactive 不喂 VAD、active 先灌预卷 ≥3200 样本、空文本不 emit、`language Chinese<asr_text>` 防御剥离、decode 异常不崩、stop ≤200ms、段队列满丢旧计数。
- **离线** `scripts/m3m4_asr_wav.py`：本地 33s wav（预期：拍掌 0 段或空文本滤掉；数数出"一二三…九"汉字形态——qwen3 无 ITN；sensevoice 档对照会出阿拉伯数字）+ 自录指令 wav；打印每段 RTF/延迟/RSS 峰值。官方 test_wavs 待 github 恢复补拉。
- **人类实测**：T7 转写质量（10 句×0/1/2 分 ≥16/20）；T8 游戏环境 30min（漏句≤1、误文本<1 次/30min、无"被切话"≥2 次）；T9 延迟 p50/p95（脚本半自动）。走 human-test skill。

## 9. 配置（8 项封顶）

```yaml
asr:
  model: qwen3               # qwen3 | sensevoice（回退一行切换）
  model_dir: models/sherpa-onnx-qwen3-asr-0.6B-int8-2026-03-25
  silero_vad_model: models/silero_vad.onnx
  num_threads: 2             # 起步 2；实测差→4；仍 RTF>0.3→切 sensevoice（三级退路）
  hotwords: ""               # 逗号分隔，≤十几个词（≥48 token 官方 WARN prompt 膨胀）
  vad_min_silence_s: 0.6
  vad_max_speech_s: 20
  max_new_tokens: 192        # 默认 128 对 20s 句有截断 WARN 风险(F7)，192 留余量
```

## 10. 风险清单

1. 实机 RTF（#3569 实证 EPYC 偏差大）→ §9 三级退路，>0.3 即切；
2. RAM 1.5–2.5GB ⚠️未实测：M3M4-a 退出标准含 RSS 实测；超 2.5GB→sensevoice；
3. 长句/热词 max_total_len 截断（F7）：日志现 "Truncating"→max_speech 降 15 或减热词；
4. 静音幻觉历史 bug：版本 pin 1.13.8（F1 修复链）+ T8 观察空段兜底；
5. 数字无 ITN：M8 结束词规则按"汉字+阿拉伯"双形态匹配（设计输入）；
6. 拍掌瞬态误段：min_speech 0.25 + 空文本过滤双保险，T8 验收线 <1 次/30min；
7. **front.samples 生命周期**：pop 后 C++ 缓冲失效，跨线程必须 numpy 拷贝（单测②锁定）——本 WP 唯一内存安全暗坑；
8. 下载通路：github CDN 时断（§3 实况），hf-mirror 兜底；无时间戳输出（#3552 open），未来字幕需求另行评估。

## 11. 里程碑

| 阶段 | 内容 | 退出标准 |
| ---- | ---- | ---- |
| M3M4-a (~0.5d) | 模型下载校验、build_vad/build_recognizer、m3m4_asr_wav.py、Fake 单测全绿 | 本地 wav 转写人眼 PASS；RTF/RSS 实测值回填本文档（RTF>0.3 当场回退评审）；CI 无模型全绿 |
| M3M4-b (~0.5d) | 消费循环+门控+预卷、真麦联调、T7/T8/T9 | T7≥16/20；T8 达标；说完→文本 p50≤1.6s；**行数勘误回填（实际 vs 预算，超支必须解释）** |

## 12. 勘误与实测回填（2026-09-24，M3M4-a 编码期）

**行数核对（全局纪律）**：实际有效代码 239 行（vad_sentence 101 + pipeline 138）vs 预算 200，**+39 (+19.5%)**。逐块解释：
- `feed()` 从 `_run` 拆出（~+15）：设计 §8 要求"VAD 可直调单测"，注入分离是测试性成本，预算未单列；
- sensevoice 回退分支完整实现（+22）：预算表给 build_recognizer 双分支仅 30 行，qwen3 分支已占大半；
- 关键契约 docstring（front 拷贝坑/门控语义）写在代码侧便于评审（~+8）。
无设计外功能，**接受超支并修订预算为 240**。

**RTF/RSS 实测（i7-11700K 8C16T，本机）**：
- Qwen3-0.6B int8：2 线程 RTF 0.40–0.65，4 线程 0.30–0.50（4 段 1–3.4s 短语音，--fast 口径）；官方 0.09–0.15 来自 Xeon+长音频，**短段 prefill 固定开销主导，桌面 CPU 不达标实锤**（印证 #3569）。
- **用户决策 2026-09-24：维持 Qwen3 不降级**，接受"说完→文本 ≈1.5–2.5s（3s 句）"，sensevoice 回退档不下载（代码分支保留，一行配置仍可切换）。
- RSS：模型载入后 ~1.28GB（预算 1.5–2.5 内低端 ✓）；载入耗时 5–6s（进程启动一次性）。

**模型通路勘误**：
- 官方包 tarball/test_wavs/silero v4 的 github release CDN 当晚完全不通（连接重置/超时），**hf-mirror `csukuangfj2/...` 逐文件 resolve 为主通路**；三 onnx sha256 与 HF LFS oid **完全一致**（校验升级为全文比对）。
- silero 以 deepghs 镜像 **v5 (2.3MB)** 替代官方 v4 (643KB)：加载+300 窗静音空转验证 OK；v5 为官方兼容模型。
- test_wavs 在 hf 仓库是 LFS 指针（15B），**放弃**；离线素材改用 `human-test/recordings/m1_t2_*.wav`（33s 真人录音：4 段全部正确转写、err=0——M3M4-a 退出标准之"人眼 PASS"达成）。

**测试计划变更（用户决策）**：T7 朗读评分**取消**；改为 **T7b：M7 TTS 落地后，"TTS 播一段已知文本 → 麦回录 → 比对 ASR 转写"**，人类只需听 TTS（一并覆盖 M4 质量、M1 回路与未来 M7 验收）。T8（游戏环境 30min）保留待做。

**状态判定**：M3+M4 = 代码 ✓ 单测 34 passed ✓ 模型+校验 ✓ 离线转写 ✓ —— **开发完成**；真麦 realtime（T9 延迟）与 T7b/T8 并入 M5/M7 联调里程碑。
