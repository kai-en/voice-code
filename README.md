# voice-code

游戏直播间的**语音助手**：主播打游戏时全程免手动，只靠语音与 opencode agent 交互——

```
说唤醒词「小码小码」 → 说话被本地识别成文字 → 交给 opencode agent 执行 → 结果用语音播报 → 说"结束对话"回到待机
```

- 唤醒、断句、语音识别、语音合成全部在本地跑，不依赖云端语音服务；只有大模型（LLM）走 API。
- 不抢游戏窗口焦点、不弹窗，专为"手在键盘上、嘴空着"的直播场景设计。
- 默认自带一套魔兽世界（WoW）国服知识库，直播答玩家问题用。

## 环境准备

- **系统**：Windows（脚本为 bat/PowerShell）。
- **Python**：3.11+（本仓库实测 3.12），仓库根建 `.venv/`。
- **依赖安装**（注意：本机 pip 有全局 target 冲突，必须带 `--target` 装进 venv）：

  ```powershell
  .\.venv\Scripts\python.exe -m pip install -r requirements.txt --target .venv\Lib\site-packages -i https://mirrors.aliyun.com/pypi/simple/
  ```

  `requirements.txt` 只登记了增量依赖，全量清单（sherpa-onnx / sounddevice / numpy / httpx / psutil 等）见 `AGENTS.md` 与 `docs/` 各设计文档。
- **LLM 后端 oc2**（opencode 2.0.16，局部安装、与全局版本隔离）：

  ```powershell
  npm install @opencode/cli@2.0.16 --prefix tools/oc2
  Copy-Item -Recurse -Force config\oc2\* tools\oc2-home\config\opencode\
  ```

  模型 API key 自备；`config/oc2/opencode.json` 内有绝对路径（key 文件、Chrome），换机器需改。`tools/` 不入库，内含密钥，**切勿提交**。
- **可选**：Google Chrome + Node.js（仅 agent 演示操作浏览器时用到）；GPU + torch 全家桶（仅启用 VoxCPM 高质量音色时用到）。

## 模型准备

出于开源边界，仓库**不含任何模型权重与音频素材**（`models/` 整体不入库），需自行下载放置：

| 用途 | 模型 | 说明 |
|---|---|---|
| 唤醒词监听 | sherpa-onnx KWS（中英 3M） | 约 31MB，放 `models/` |
| 语音断句 | Silero VAD | 单文件 `models/silero_vad.onnx` |
| 语音识别 | Qwen3-ASR-0.6B int8 | 约 950MB，sherpa-onnx **1.13.8 必须 pin 死** |
| 语音合成（默认） | winTTS | Windows 自带，零下载零显存 |
| 语音合成（可选） | VoxCPM1.5 + 母音色素材 | 需 GPU；音色素材用户自备，版权自担 |

各模型的下载渠道、校验值、踩坑记录见 `docs/0923工作/` 下 kws / asr / tts 设计文档。缺模型时启动会直接报错并指引。

## 启动 / 停止

```powershell
run.bat            # 启动（可加参数 vox 切换高质量 TTS）
stop.bat           # 停止
log.bat            # 看日志
dialog.bat         # 看「你 / 助手」对话文字流水（直播时听不清就看这个）
```

- 单一实例：双开会拒绝启动；停止不干净会明确报"残留 N 个"，不会留孤儿进程。
- 启动后听到「在呢。」即可开说；也可以向本地控制台 `ws://127.0.0.1:8765` **打字**注入指令（只绑回环、无鉴权，仅限本机）。
- 结束会话：直接说"结束这次对话吧"，助手回到待机等你下次唤醒。

## 避免回音（重要）

助手的外放声音会被麦克风重新收回去，造成"自问自答"。这是**硬件问题**，软件侧刻意不做防护，请二选一：

1. **使用带硬件 AEC（声学回声消除）的麦克风**——说话与播报可同时进行，体验最好；
2. **戴耳机**——助手的声音只进耳机，物理上收不回去，同样干净。

> 注意：蓝牙耳机一开麦会切到通话模式，游戏声压成窄带音质，直播场景建议有线耳机。

## 唤醒词

**「小码小码」**。说一次即唤醒；唤醒后的会话中**无需再唤醒**，回合结束自动衔接下一句（免唤醒连续对话）。

想换唤醒词：改 `config/kws/keywords_raw.txt` 后按 `docs/0923工作/kws-design.md` §3 的流程生成并冒烟验证（一次性人工步骤）。

## 语言

**只支持中文（普通话）**。唤醒词、话术、语音合成、断句、纠错都按中文调优；识别模型本身支持多语言，但整条链路不为英文/方言服务。

## WoW 知识库（默认自带，可自主编译）

仓库自带一套魔兽世界知识库（`config/oc2/wow-kb/`，39 条），覆盖副本流程、界面设置、组队社交、插件等，默认口径**国服正式服**。玩家问 WoW 问题时，agent 先查库；库里没有的会自主联网研究后按证据可信度分级作答，拿不准就直说不确定。

想扩充/修订知识库（离线做，直播中不写库）：按 `.agents/skills/wow-kb-authoring/` 的编写流程——检索核验 → 写条目 → 部署：

```powershell
Copy-Item -Recurse -Force config\oc2\wow-kb\* tools\oc2-home\config\opencode\wow-kb\
```

部署后在新会话生效（直播中的会话不热更）。
