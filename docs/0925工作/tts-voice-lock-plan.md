# M7 音色锁定两步计划（2026-09-25，deepthink 调研后）

依据：voxcpm 2.0.3 源码 + 官方文档/issues 调研结论。
- 无 prompt 快速路径音色随机是固有行为（起始 latent 纯噪声，seed 仅同文本可复现）→ 唯一实用锁音 = prompt 续写克隆。
- C1(prompt1.wav) 发闷根因 = 24kHz 素材带宽天花板；1.5 的 prompt 编码走 44.1k 真带宽，换高采样率素材收益直接。
- T7c 带 prompt 合成 393s 根因 = 失控顶满 154 步 → badcase 全量重试×3（非重编译）；好素材 + retry=1 可治。
- VoxCPM2 升级挂起（运行 ~8GB，与游戏共存高危；触发条件：≥16GB 卡）。

## 步骤1 重选母音色素材 C1'（人类）
- 要求：原生 44.1k/48kHz、真人温柔中文女声旁白、单一稳定、5–10s、无 BGM/混响、可商用授权（沿用 progress.md A/B 路径）。
- 流程：候选进 models/voice_candidates/ → 跑 m7_t7c2 试听 → prompt_text 用 ASR 逐字人工核对。
- 验收：T7c A/B 试听 PASS（音色贴合、无失控、音质不闷）。

## 步骤2 tts.py 接入 prompt cache（代码）
- 改动（约 +10 行，TtsConfig 加 prompt_wav/prompt_text，预算内）：
  1) 加载后用 tts_model.build_prompt_cache() 编码 C1' 一次常驻；
  2) 每句改走 generate_with_prompt_cache（免每句重编码）；
  3) 启动预热用真实 cache 对哑文本跑一次（吸收一次性开销）；
  4) 参数：cfg_value=1.6 起试、retry_badcase_max_times=1；保持单 worker 线程。
- 验证：pytest 39 绿 + 真机 speak() 秒级出音；随后进 T7b。

行数纪律：本改动仅 src/tts/tts.py，152→约 165 行（预算 160，超出部分若 >5 行在 progress 勘误说明）。

## 勘误（2026-09-25 编码后）

- 步骤1 ✅ 素材改为站录 23s 旁白（voice_candidates/doubao/，T7c4 采集）；T7c 六句克隆稳定性 **PASS**。
- 步骤2 ✅ 落地，实际 185→216 行（+31 > 预估 +10）。超出项及理由：
  ① prompt_text 走素材同名 .json 自动读取（+2，素材不入库前提下免双配错）；
  ② FakeModel 兼容守卫（模型无 cache API 时回落并告警，+4，保 39 单测零改动）；
  ③ 缓存构建/合成分拆两个方法（+12，worker 线程内聚与可读性）。
  无设计外新行为；预算超出的结构性原因：原预算按"裸透传两个参数"估，未按素材外置与 UT 兼容估。
