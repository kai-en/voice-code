# 当前进度总览（2026-09-25）

> 本文是截至 2026-09-25 的全项目进度快照。上一阶段的详细决策记录见 `docs/0923工作/` 各设计文档；总设计见 `docs/0923工作/modules.md`（v3 ASR / v4 TTS 定版）。

## 1. 模块进度表

| 模块 | 内容 | 状态 | 代码(有效行/预算) | 单测 | 人审 |
|---|---|---|---|---|---|
| M1 | 音频采集（混音环路 WASAPI loopback + 焦点旁路） | ✅ 完成 | 152 / 160 | 17 | T2/T4 PASS |
| M2 | 激活词 KWS（"小码小码"，sherpa-onnx zipformer 3M int8） | ✅ 完成 | 152 / 180 | 7 | T5 PASS（11/10 次命中） |
| M3+M4 | VAD（silero）+ 断句 + ASR（Qwen3-ASR-0.6B int8 onnx） | ✅ 完成 | 239 / 240 | 10 | T7 已取消→并入 T7b |
| M7 | TTS（VoxCPM1.5，RTF≈0.35-0.40） | 🟡 主体完成，音色锁定未做 | 152 / 160 | 5 | 真机开口✅；**T7b 待用户跑** |
| M5 | 编排器（唤醒→监听→转写→送 opencode→播报） | ⬜ 未开始 | - | - | - |
| M6 | opencode_client（server 模式 SSE/REST） | ⬜ 未开始 | - | - | - |
| M8 | end_session 回声防护 | ⬜ 未开始 | - | - | - |
| M9 | ux_adapter 焦点/窗口适配 | ⬜ 未开始 | - | - | - |
| M10 | support（日志/看门狗/热键兜底） | ⬜ 未开始 | - | - | - |

全量单测：**39 passed**（`pytest`，human-test 已排除收集）。

## 2. 关键性能实测（i7-11700K + RTX 3080 10GB）

| 项 | 指标 | 说明 |
|---|---|---|
| ASR 离线转写 | RTF 0.4-0.65，err=0（4 段测试句全对） | 超回退线 0.3，用户拍板"就先用 qwen3" |
| ASR 内存 | RSS ≈ 1.28 GB | |
| TTS | 稳态 RTF ≈ 0.35（triton-windows 装上后 2.05→0.40） | 首次 ready 76s（torch.compile 预热） |
| TTS 显存 | 常驻 ~3 GB / 峰值 ~4 GB | 与 WoW + opencode 共存可行（10GB 卡） |
| KWS | 3M 模型 chunk-16 int8，CPU 单核占用可忽略 | 模型 sha256 校验通过 |

## 3. 关键决策记录（相对 0923 版的变更）

1. **ASR 改 Qwen3-ASR-0.6B int8 onnx**（原 SenseVoice，v3）— 理由：官方 onnx 导出、带官方 int8 量化、中英混说更稳。
2. **TTS 改 VoxCPM1.5**（原 Kokoro CPU，v4）— 理由：零样本音色克隆是刚需（锁主播音色），CPU 方案无克隆能力。int8 量化判定放弃（瓶颈在 kernel 发射不在带宽）。
3. **T7（人耳评分 ASR 质量）取消**，改为 **T7b**：TTS 播一句→M1 回录→M4 转写→与原文比 CER，一测两用（TTS 可懂度 + ASR 准确率），要求音箱外放模拟直播环境。
4. **音色锁定方案**：VoxCPM1.5 无 reference_wav（2 代功能），只能 `generate(text, prompt_wav_path, prompt_text)` 成对使用；prompt_text 必须与音频逐字一致；8-12s、44.1k mono WAV、无 BGM/混响（环境音会被一起克隆）；启动时 `build_prompt_cache` 一次、常驻复用。

## 4. 当前卡点：母音色（prompt_wav）选型 — 进行中

需求：**温柔中文女声、旁白解说风（非台词表演）、可商用授权**。

已探索并否决的路径：

| 路径 | 结果 | 否决原因 |
|---|---|---|
| CosyVoice 示例女声 | 试听否决 | AI 合成音，三流引流素材（二手克隆叠加） |
| IndexTTS B 站 demo | 试听否决 | 全是影视台词/配音表演素材，非旁白朗读 |
| AISHELL-3 via hf-mirror / ModelScope | 下载失败 | resolve 超时 / 无镜像；HF 官方仓库 parquet 分片可行，但需代理 |
| 爱给网 aigei.com "温柔女声" | 咨询否决 | 是 TTS 音色库（合成成品非母音源）；铜币会员制；用户投稿无逐条授权溯源，商用+克隆双风险 |

**下一步（二选一，待用户定）**：
- A. 用户开代理 → 我从 HF 官方 `AISHELL/AISHELL-3` 拉 2-3 个女说话人 parquet 分片 → 各截 8-12s 干净片段 → 试听挑选。
- B. 用户自行找素材扔进 `models/voice_candidates/` → 我接手：裁剪→silero 去静音→ASR 自动生成 prompt_text→build_prompt_cache 锁音色→`scripts/m7_tts_say.py` 回放验证。

音色选定后的代码改动（已设计，未实现）：`src/tts/tts.py` TtsConfig 增加 `prompt_wav`/`prompt_text` 两字段 + 启动 build_prompt_cache + generate 透传，约 **+10 行**（预算内），同步回填 `tts-design.md` §10。

## 5. 待办清单

| # | 事项 | 依赖 |
|---|---|---|
| 1 | 母音色选型 + 音色锁定扩展（上节 A/B） | 用户决定路径 |
| 2 | 跑 T7b：`human-test/m7_t7b_tts-asr-loop.py`（需音箱外放） | 音色锁定后跑一次即可 |
| 3 | M6 opencode_client（先 deepthink 调研 server API：SSE/REST、session 生命周期） | 无 |
| 4 | M5 orchestrator（串联 M1→M2→M3M4→M6→M7→M8） | M6 |
| 5 | M8 end_session 回声防护（TTS 播放期抑制回录判定） | M5 |
| 6 | M9 ux_adapter、M10 support | M5 |
| 7 | M2 遗留：物理拔麦克风热恢复（T3）低优先级补测 | - |
| 8 | 集成后回归：39 单测 + 各 human-test 复跑 | - |

## 6. 资产与环境备忘

- **模型**（均已 sha256 校验）：`models/sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20/`、`models/sherpa-onnx-qwen3-asr-0.6B-int8-2026-03-25/`、`models/silero_vad.onnx`(v5)、`models/voxcpm1.5/`（model.safetensors 1.6GB + audiovae.pth 346MB）。
- **工具**：`tools/aria2c.exe`（-x16 破限速主力）；playwright MCP 带持久 profile（B 站已登录）。
- **环境坑**（复发时先查）：pip 全局 target=F:\python-packages 冲突→`PIP_TARGET` 指 venv + `--no-build-isolation`；torch.compile 生效需 triton-windows+setuptools；sounddevice 0.5.6 无 `sd.tone`→用 `sd.play(blocking)`；PowerShell 内联中文/`$`/反引号脚本一律落成 .py 再跑；脚本里 `os.chdir` 后注意相对路径基准。
- **文档**：设计+勘误在 `docs/0923工作/`（audio-capture/kws/asr/tts-design.md，均含行数核对）；人审记录 `human-test/RESULTS-2026-09-24.md`。
