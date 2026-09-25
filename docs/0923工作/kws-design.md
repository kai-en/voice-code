# 激活词监听模块详细设计 (M2 KWS)

> 2026-09-23 工作记录（deepthink 调研产出，官方源码/Release 已核实）。上游：`docs/0923工作/modules.md` M2 章节、`audio-capture-design.md`（M1 v2）。

## 0. 轮子盘点（先说复用，再说自研）

| 复用 | 内容 |
| ---- | ---- |
| R1 | 官方 [keyword-spotter-from-microphone.py](https://github.com/k2-fsa/sherpa-onnx/blob/master/python-api-examples/keyword-spotter-from-microphone.py) 的调用序（全文核实）：`KeywordSpotter(...)` → `create_stream()` 一次 → 循环 `stream.accept_waveform(16000, samples)` → `while kws.is_ready(stream): kws.decode_stream(stream); r = kws.get_result(stream); if r: kws.reset_stream(stream)` |
| R2 | 官方离线示例 [keyword-spotter.py](https://github.com/k2-fsa/sherpa-onnx/blob/master/python-api-examples/keyword-spotter.py)（read_wave → 喂入 → `tail_paddings=0.66s` → `input_finished()` → 解码）——测试脚本照抄 |
| R3 | pip 包自带 CLI `sherpa-onnx-cli text2token`——拼音 token 化是**一次性人工步骤**，运行时零逻辑 |
| 高级 API 结论 | **不用**。无工厂方法、无 KWS websocket server；进程内最短路径就是 Python `KeywordSpotter` + 示例调用序 |

自研合计预算 ≈165 行（上限 200）：消费线程、去抖/mute、装配。不写解码器、不写关键词解析、不写重连。

## 1. 组件与行数预算（单文件 `src/kws/kws_wake.py`）

| 块 | 行数 |
| ---- | ---- |
| 头注释 + import + 常量（`SR=16000`、文件名模板 `epoch-13-avg-2-chunk-16-left-64`） | 15 |
| `KwsConfig` dataclass | 12 |
| `KwsHit` dataclass（`{keyword: str, ts: float}`，**无 score**，见 §7） | 5 |
| `build_spotter(cfg)`：拼 4 个模型路径 + 断言存在（fail fast 附下载指引）→ 构造 `sherpa_onnx.KeywordSpotter` | 25 |
| `KwsWorker`：`start/stop/_run/set_muted` | 95 |
| `start_kws(cfg, mic, on_hit) -> KwsWorker` 装配 | 12 |

`scripts/m2_kws_wav.py`（离线测试）与模型下载脚本不计入预算。

## 2. 模型资源获取

```powershell
curl.exe -L -o kws.tar.bz2 https://github.com/k2-fsa/sherpa-onnx/releases/download/kws-models/sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20.tar.bz2
Get-FileHash kws.tar.bz2 -Algorithm SHA256   # 期望 68447F4FBC67E70EEE3A93961F36E81E98F47AEF73CE7E7CA00885C6CD3616A6
tar xf kws.tar.bz2 -C models/
```

- 包大小 31.4MB；int8 **不单独打包**，同包含 fp32+int8。运行时 4 个文件：`encoder-…chunk-16-left-64.int8.onnx`(4.4M)、`decoder-…chunk-16-left-64.onnx`(743K，仅 fp32)、`joiner-…chunk-16-left-64.int8.onnx`(85K)、`tokens.txt`；`en.phone` 仅生成 keywords 用；`test_wavs/` 留给离线测试。
- **chunk 选择：chunk-16（精度档，官方明示"低延迟通常低精度"，modules.md 旧表述方向已更正）**；嫌唤醒慢可换 chunk-8（160ms 批、精度略降）。
- ⚠️ 本机 github release 直连可能超时（hf-mirror 实测挂、ModelScope 无此新模型）→ 代理机手动转运 + sha256 校验。
- ⚠️ 模型权重包内无 license 文件；个人自用无碍，商用前自查（同系模型训练集 WenetSpeech 商用需授权）。
- `models/` 目录入 `.gitignore`。

## 3. 激活词定义（一次性人工流程，禁止手写 token）

1. 人写 `config/kws/keywords_raw.txt`（UTF-8）：`小码小码 :1.5 @小码小码`（格式 `词 [:boost] [#threshold] [@显示名]`，`:`/`#` 后不留空格）；
2. 生成：
   `sherpa-onnx-cli text2token --tokens models/…/tokens.txt --tokens-type phone+ppinyin --lexicon models/…/en.phone config/kws/keywords_raw.txt config/kws/keywords.txt`
   预期 `x iǎo m ǎ x iǎo m ǎ :1.5 @小码小码`（中文=ppinyin 声母韵母+声调符，英文自动走 en.phone 转 CMU phone；漏 `--lexicon` CLI 会报错）；
3. `keywords_raw.txt`、`keywords.txt`（生成物）、生成命令（README）一起**入库**；改词 = 重跑生成 + `m2_kws_wav.py` 冒烟。
4. 选词：3–4 音节、含翘舌/开口音；多关键词同文件多行，`get_result()` 返回 @显示名，M5 分派。

## 4. 消费循环（`KwsWorker._run`，daemon 线程，不进 asyncio）

- 唯一线程触碰 stream，无锁；解码是 pybind/C++ 同步调用。
- 节拍：`sink.get(timeout=0.1)` 返回 `None` → continue（天然心跳）；取到首帧后**非阻塞续 drain ≤7 帧**（共 ≤8 帧 = 160ms）→ `np.concatenate` → 一次 `accept_waveform(16000, chunk)`。
- 无需手工对齐模型 chunk：特征提取器内缓冲，`is_ready()` 自行推进（chunk-16 每 320ms 音频一步，RTF≪1 不积压）。
- 防御：循环体 try/except 计数不崩线程（M1 铁律）；`stop()` 置 flag，100ms 内退出；`qsize()>50` 持续出现打一条 WARN（预期恒≈0）。

## 5. 命中处理与去抖（顺序固定）

`get_result()` 非空 → **立即 `reset_stream`**（否则重复返回）→ 过滤 → emit：
1. `muted` → 丢弃计数；
2. `now - last_hit < cooldown_s`(2.0) → 丢弃；
3. 否则 `on_hit(KwsHit(keyword=r, ts=…))`，更新时间戳。

`on_hit` 回调由 M5 提供（M5 侧自行 `call_soon_threadsafe` 转投 asyncio，M2 不管线程安全）。

## 6. 防自激钩子（最简一个方法）

`worker.set_muted(bool)`（M5 进/出 SPEAKING 直调）：
- True：muted 期间**照常消费+解码**（保持流热），命中吞掉但仍 reset；
- False：`sink.clear()` + `reset_stream()`（丢弃播报期积压与部分匹配）→ 立即可唤醒。
- 不做"运行期提阈值"（threshold 是构造期参数，双实例 +几十 MB 内存 ⚠️，200 行内禁止；实测 TTS 期误触发多再升级）。M5 亦可选择**不 mute**、把命中当 barge-in。播报文案避免含激活词（M5/M7 约束）。

## 7. 对 M1 的契约遵从

只读 `mic.sinks["kws"]`（20ms/320 样本 f32@16k，采样率与构造默认一致）；不假设断缝/重连事件——M1 停摆时 sink 断供，KWS 自然失聪并自旋等待，恢复=人工重启进程重建 spotter/stream；不调 `input_finished()`（离线专用）；不碰 `vad` 队列。**modules.md 的 `KwsHit{keyword, score, ts}` 修正为 `{keyword, ts}`：Python `get_result()` 不暴露置信度，把关靠 `keywords_threshold` 硬阈值。**

## 8. 配置（6 项封顶）

```yaml
kws:
  model_dir: models/sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20
  keywords_file: config/kws/keywords.txt
  keywords_threshold: 0.25   # 调大→更难触发
  keywords_score: 1.5        # 全局 boost；每词 :x 可覆盖
  cooldown_s: 2.0
  num_threads: 1             # 显式传 1（wrapper 默认 2）
```

chunk-16 + int8(encoder/joiner)+fp32(decoder) 写死为代码常量；`max_active_paths=4`、`num_trailing_blanks=1` 用默认。

## 9. 测试

| 层 | 内容 |
| ---- | ---- |
| 单测（CI，无麦无模型） | FakeSpotter/FakeStream 脚本化 + 真 `DropOldestQueue` 塞帧：批拼接长度、**命中后必先 reset**、cooldown 窗口不 emit、muted 不 emit、unmute 触发 clear+reset、stop ≤100ms 退出、异常不崩线程 |
| 离线 wav（模型缺失则 skip） | `scripts/m2_kws_wav.py` 复刻 R2：①模型自带 `test_wavs/*.wav + keywords.txt` 应命中官方词；②自录"小码小码" wav + 入库 keywords.txt 验证自定词 |
| 人类实测 | = M1 文档 T5：真麦挂 KwsWorker，10 次呼唤间隔 30s，命中 ≥9/10（走 human-test skill：`m2_t5_wake-rate.py`）；另录 30–60min 游戏实盘音频离线数误触发，目标 <1 次/小时 ⚠️ |

## 10. 风险清单

1. 游戏噪声误触发：threshold↑ / 每词 `#0.4` / score↓ → 仍不行才考虑降噪前置（超 M2 范围）⚠️需实盘回测；
2. 拼音 token 写错→永不命中：制度缓解（只用 CLI 生成、生成物入库、改词必冒烟）；
3. 唤醒延迟 ≈0.5–0.9s（160ms 批 + 320ms chunk + trailing blanks 确认）：可接受；嫌慢换 chunk-8（精度反向）；
4. 无置信度：做不了软决策，仅硬阈值；
5. "小码小码"音节重复若命中迟疑/重复触发：`num_trailing_blanks` 1→2–8（官方明示用途，代价=确认延迟↑）；
6. 下载通路：见 §2 ⚠️；
7. Windows 控制台打印声调字符需 UTF-8（CHCP 65001），文件读写显式 `encoding="utf-8"`；
8. 解码是否释放 GIL ⚠️未逐调用核实，由 M1 T6 长跑/延迟实测兜底。

## 11. 里程碑

| 阶段 | 内容 | 退出标准 |
| ---- | ---- | ---- |
| M2-a（~0.5d） | 模型下载校验 + keywords 生成 + kws_wake.py + 单测全绿 | CI 通过；离线 wav 冒烟命中官方测试词 |
| M2-b（~0.5d） | 真麦接 M1 队列 + human-test T5 | 唤醒 ≥9/10；30min 运行 CPU、误触发可接受 |

## 12. 实测勘误（2026-09-24 编码期回填）

- **下载**：github release 直连 HEAD/GET 实际可通（31.4MB，sha256 校验通过 32885699 B），无需代理转运（§2 ⚠️ 解除）。
- **解压**：本机 `tar`(bsdtar) 解 .tar.bz2 挂起无输出 → 改用 venv `python -c "import tarfile; tarfile.open('models/kws.tar.bz2','r:bz2').extractall('models')"`，3.4s 完成。
- **模型文件名**：与常量 `epoch-13-avg-2-chunk-16-left-64` 完全一致（encoder/joiner 有 int8+fp32 双份，decoder 仅 fp32，如 §2 所述）。
- **text2token CLI 实态**：pip 包内无 `sherpa-onnx-cli.exe`；`python -m sherpa_onnx.cli` 静默不执行（cli.py 无 `__main__` 入口）。可用方式：`python -c "import sys; sys.argv=[...]; from sherpa_onnx.cli import cli; cli()"`。额外 pip 依赖（venv 内补装）：`click`、`sentencepiece`、`pypinyin`。
- **离线冒烟（M2-a 标准①）**：官方 keywords 对官测 wav：zh_3→'文森特卡索','法国'；zh_4→'蒋友伯','女儿'；zh_5→'周望军'；zh_6→'见面会'；en_0→'LIGHT_UP'（zh_0-2 素材不含关键词）；自定词'小码小码' keywords.txt 构造成功、静音 0 误触发。
- **消费循环修正**：单测抓到真 bug——drain 循环预取的第 9 帧会被丢弃（跨批丢帧），`_run` 已改为"首帧阻塞取 + while len<8 非阻塞续取"；40 帧全量消费有断言固化。
- **脚本**：`scripts/m2_kws_wav.py`（离线冒烟，已验证）；`human-test/m2_t5_wake-rate.py`（人类实测 10 唤×30s + 误触发观察，自动写 RESULTS）。
