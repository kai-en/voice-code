# 总目标 (Overall Goals)

> voice-code 项目的总体目标说明。

## 项目愿景

以 opencode 的 server 模式（headless 模式）为基础，创建语音交互工具。使用户（主播）在打游戏时，仅使用语音和 opencode agent 交互。

## 核心目标

1. 基于 opencode server（headless）模式构建语音交互链路。
2. 主播在游戏中全程免手动，仅通过语音与 opencode agent 交互。

## 开源边界（重要）

- 本项目以**源代码**形式开源，仓库**不包含模型权重与音频素材**（如 `models/` 下的 VoxCPM/ASR/KWS 权重、母音色 prompt wav、人审录音等均不入库，仅本地存在）。
- **人声素材本身不是项目的一部分**：母音色等语音素材由用户自备（自行下载模型、自行选定音色素材），其版权与商用授权由用户自行负责，不在项目的发布与承诺范围内。
- 因此代码中对素材的引用一律走**可配置路径**（如 `models/voice_candidates/`、`TtsConfig.prompt_wav`），不内置任何具体音频。

## 大体方案

1. 用小模型持续监听主播的所有语音，识别其中的"激活词"。
2. 被激活后，对主播语音进行 VAD + ASR 处理，转为文本后送入 opencode 执行。
3. 将 opencode 的执行结果通过 TTS 播放出来。
4. 直到 LLM 识别到"结束对话"（这可以是一个 skill）后，关闭"激活"模式，恢复小模型监听，直到下次激活。

## 阶段目标

| 阶段 | 目标 | 状态 |
| ---- | ---- | ---- |
| M1   | 音频采集（WASAPI，有界队列+看门狗） | ✅ 完成 |
| M2   | 激活词 KWS（"小码小码"） | ✅ 完成 |
| M3+M4 | VAD 断句 + ASR 转写（Qwen3-ASR-0.6B） | ✅ 完成 |
| M5   | 编排器（唤醒→监听→转写→opencode→播报状态机） | 未开始 |
| M6   | opencode_client（v2 免费池 REST/SSE 集成） | ✅ 完成（2026-09-25，e2e PASS） |
| M7   | TTS + 音色锁定（VoxCPM1.5 + prompt cache） | ✅ 完成（2026-09-25 T7c PASS） |
| M8   | end_session 识别 + 回声防护 | 未开始 |
| M9   | ux_adapter（非焦点/提示音/托盘） | 未开始 |
| M10  | support（日志/看门狗/热键兜底） | 未开始 |

详细进度快照见 `docs/0925工作/progress.md`。

## 非目标（Out of Scope）

- （待补充）
