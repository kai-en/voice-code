# voice-code

游戏直播间的**语音助手**：主播打游戏时全程免手动，仅通过语音与 opencode agent（oc2）交互。

核心链路：

```
小模型常驻监听唤醒词（KWS） → 激活后 VAD + ASR 转文本 → 送 opencode server（headless）执行
→ 执行结果 TTS 播报 → 模型调用 voice-end 工具结束会话 → 回到监听态
```

- 全本地 VAD / ASR / KWS / TTS（winTTS 零 GPU；VoxCPM 可选），不依赖云端语音 API。
- LLM 侧通过本地 `opencode2 serve` 走云端模型 API。
- 非焦点设计：不抢游戏窗口焦点、不弹窗。

## 目录结构

| 路径 | 用途 |
|---|---|
| `main.py` | 入口：直接运行启动全流程；`--probe` / `--sweep` 走进程卫生 CLI |
| `run.bat` / `stop.bat` | 唯一启动 / 停止入口 |
| `log.bat` / `dialog.bat` | 日志跟随查看 / 「你·助手」对话流水视图 |
| `src/` | 业务代码（audio_capture / kws / asr / orchestrator / opencode_client / tts / lifecycle / console） |
| `config/` | 唤醒词源文件 + oc2 配置唯一真源（含 `wow-kb/` 知识库） |
| `models/` | 模型权重与音色素材（**gitignore，用户自备**，见下节） |
| `tools/` | oc2 局部安装、XDG 隔离运行区、下载工具（**gitignore**，含密钥，勿提交） |
| `docs/` | 设计文档（按工作日期分目录，M1–M13 里程碑） |
| `tests/` / `human-test/` / `scripts/` | pytest 单测（全 mock） / 需人耳人眼的主观测试 / 离线冒烟脚本 |

## 环境准备

### Python

- 要求 **Python 3.11+**，本仓库实测环境为 **3.12.7**（venv 由 anaconda 创建；依赖 wheel 为 cp312）。
- venv 位于仓库根 `.venv/`。

### 依赖安装

`requirements.txt` 目前只登记了增量依赖（`websockets`）；torch / sherpa-onnx / sounddevice / numpy / psutil / httpx 等历史依赖**未登记**，需按下面的"事实清单"自行安装。

⚠️ 本机 pip 有全局 `global.target=F:\python-packages` 且该目录不在 sys.path → 普通 `pip install` 显示成功但 python 不认。必须：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt --target .venv\Lib\site-packages -i https://mirrors.aliyun.com/pypi/simple/
```

事实上的运行时依赖清单（当前 venv 实测版本）：

| 包 | 版本 | 用途 |
|---|---|---|
| sherpa-onnx | **1.13.8（pin 死，勿降级勿乱升）** | KWS / VAD / ASR（≥1.13.8 内置全部 Qwen3-ASR 修复链） |
| sounddevice | 0.5.6 | 麦克风采集 / TTS 播放 |
| numpy | 2.5.3 | 音频帧处理 |
| websockets | 17.x | M11 本地控制台 |
| httpx | 0.28.1 | oc2 REST/SSE 客户端 |
| psutil | 7.2.2 | `--sweep` 进程枚举 |
| pytest | 9.1.1 | 单测 |

可选 —— VoxCPM TTS 后端（需 CUDA GPU，默认后端 winTTS 不需要）：
`torch 2.6.0+cu124`、`torchaudio 2.6.0+cu124`（本地 wheel 在 `tools/wheels/`）、`triton-windows`、`voxcpm 2.0.3`、`transformers` 等。

可选 —— 自定义唤醒词生成（一次性）：`click`、`sentencepiece`、`pypinyin`。

### 外部程序

- **PowerShell**（隐藏窗口启动、wintts 后端、日志跟随均依赖）。
- **oc2（opencode 2.0.16）**：LLM 后端，局部安装（跑原生 exe，本身不需要 Node）：

  ```powershell
  npm install @opencode/cli@2.0.16 --prefix tools/oc2
  ```

  配置唯一真源在 `config/oc2/`，需手动复制到部署区（`tools/` 整体 gitignore）：

  ```powershell
  Copy-Item -Recurse -Force config\oc2\* tools\oc2-home\config\opencode\
  ```

  ⚠️ `config/oc2/opencode.json` 里有**绝对路径硬编码**（API key 文件、Chrome 路径、playwright profile），换机器必须改。LLM API key 自备于 `tools/oc2-home/secrets/alibaba.key`。**secrets / service.json / playwright-profile 含敏感信息，切勿提交或分发 `tools/`。**
- **Google Chrome + Node.js**：仅当用到 playwright MCP（agent 操作浏览器）时需要。
- ffmpeg 不需要；OBS 无代码集成（仅直播玩法，见「启动/停止」）。

### 环境变量

| 变量 | 用途 | 默认 |
|---|---|---|
| `VOICECODE_CONSOLE_PORT` | 本地控制台 WS 端口（禁用 4096，那是 opencode serve 默认口） | `8765` |
| `VOICECODE_TTS_BACKEND` | TTS 后端：`wintts` \| `voxcpm` | `wintts` |
| `VOICECODE_VOX_GAIN` | voxcpm 播放增益 | `0.5` |
| `VOICECODE_LOCK` | 单实例锁文件路径 | `logs\voice-code.lock` |

麦克风/扬声器**无配置项**，取系统默认设备（换设备需改代码或调系统默认值）。

### 测试

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

全 mock，不碰真设备、不需 GPU / 模型 / node。需人耳验收的项目（音质、唤醒率等）在 `human-test/` 下，按其 README 手动执行。

## 模型准备

`models/` 整体 gitignore——**本项目以源代码开源，不含模型权重与音频素材**，需自行下载（可用 `tools/aria2c.exe -x16` 加速；github release 不通时优先 ModelScope / hf-mirror，先 HEAD 探测再下载）。

| 角色 | 模型 | 放置路径（相对 `models/`） | 体积 |
|---|---|---|---|
| KWS 唤醒 | sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20 | `sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20/` | 31.4MB（包内含 fp32+int8） |
| VAD | Silero VAD (onnx) | `silero_vad.onnx` | 643,854 B |
| ASR（默认） | Qwen3-ASR-0.6B int8 | `sherpa-onnx-qwen3-asr-0.6B-int8-2026-03-25/` | tarball ~879MB，净增 ~950MB |
| ASR（回退档，未下载） | SenseVoiceSmall int8（代码分支保留，一行可切） | `sherpa-onnx-sense-voice-...` | 155MB |
| TTS（可选） | VoxCPM1.5（ModelScope `OpenBMB/VoxCPM1.5`） | `voxcpm1.5/` | model 1.60GB + audiovae 346MB |
| TTS 母音色（可选，用户自备） | prompt wav + 同名 `.json`（`asr_text` 逐字一致） | `voice_candidates/<音色>/prompt_*.wav` | 素材版权自担 |
| TTS（默认） | winTTS（Windows System.Speech，无需模型文件） | — | — |
| LLM | 云端模型，经 oc2 serve（`config/oc2/opencode.json`） | — | — |

下载与逐文件 sha256 校验细节见设计文档：

- KWS：`docs/0923工作/kws-design.md` §2（⚠️ 本机 bsdtar 解 .tar.bz2 会挂起，改用 `python -c "import tarfile; ..."`）
- ASR + VAD：`docs/0923工作/asr-design.md` §3（主推 hf-mirror `csukuangfj2/...` 逐文件 resolve；以字节数+分文件 sha256 双重校验）
- TTS：`docs/0923工作/tts-design.md` §0

模型缺失时启动会 fail-loud 并给出处置指引。

## 启动 / 停止

启动/停止**只经 `run.bat` / `stop.bat`**，内部都是 `main.py --sweep --expect-clean`（先清扫再断言残留为 0），不要绕过它手工再起一个。

```powershell
run.bat            # 启动（默认 winTTS）
run.bat vox        # 启动并切 VoxCPM TTS 后端（需 GPU）
log.bat            # tail -f 日志（logs\voice-code.log）
dialog.bat         # 「你 / 助手」两方对话流水（直播时听不清就看这个）
stop.bat           # 停止；报"残留不为 0"就是没清干净，排查后重试
```

机制说明：

- **单一实例**：由 `logs\voice-code.lock` 的 OS 字节锁证明（进程死即释放，不受 PID 复用骗）。双开会拒绝启动（exit 3）。
- **进程连坐**：主进程起任何子进程前先 `attach_job()`（Job Object，KILL_ON_JOB_CLOSE），opencode serve、wintts powershell 等子孙一并收编，Ctrl-C / 强杀都不留孤儿。
- **kill 前必过滤**：只杀「锁内真 PID / 镜像路径在本仓库下 / 命令行含 `main.py` 或 `tools\oc2` 且与本仓库相关」的进程，逐条打印，绝不盲杀无关 node/anaconda 进程。
- 启动成功后：说唤醒词即可对话（见下节）；也可向控制台 `ws://127.0.0.1:8765` 打字注入（只绑回环、无鉴权、不 serve HTML，非 WS 请求返回 426）。
- 退出会话：无结束词、无静默超时——由模型调用 `voice-end` 工具结束，回到待机监听。
- 直播玩法：无 OBS 代码集成；agent 经 playwright MCP 开**可见的** Chrome 窗口（固定 profile、禁止改窗口大小、禁止 headless），由 OBS 手动取窗展示。

## 避免回音（播报期自听）

助手说话时，其外放声会被自家麦克风收回去，造成"自问自答 / 误打断"。**当前版本对此没有任何软件防护**（`src/orchestrator/core.py` 明示"播报期自听不设软件防护"；历史上的 `_is_echo` 文本去重只是缓解不是消除，已随断句重写移除）。

设计口径：**这是硬件问题，靠硬件解决**——

1. **推荐：带硬件 AEC（回声消除）的麦克风/会议扬声器**。全双工打断（LLM 输出期间可开口打断）即建立在"硬件 AEC 在场"的假设上。
2. **或者：戴耳机**。助手播到耳机里，麦克风收不到外放，自听即消失。耳机注意蓝牙 HFP 坑：常驻开麦会把蓝牙耳机压成窄带音质，建议有线或独立麦。
3. 反面案例：本机实测曾把麦和喇叭设成同一台 USB 会议设备（系统默认输入/输出同源），自听最严重。

⚠️ 禁止为此在软件侧新增防护逻辑（额外门限、播放期禁麦、相似度加强等）——见 `AGENTS.md`「播报期自听」节。

## 唤醒词

唤醒词：**「小码小码」**（助手名"小码"）。说一次即可进入收集态，播 ack「在呢。」。

- 常驻监听由 sherpa-onnx KeywordSpotter（zh-en 3M 模型，CPU 占用可忽略，chunk-16 精度档，唤醒延迟约 320ms）实现。
- 会话进行中（收集/执行/播报态）KWS 不再参与，唤醒词作为句首会被正则剥掉；回合结束**免唤醒连续对话**，直到 `voice-end` 回到待机。
- 调灵敏度：`src/kws/kws_wake.py` 的 `KwsConfig`（`keywords_threshold=0.25` 调大更难触发，`keywords_score=1.5` 全局加分，`cooldown_s=2.0` 命中冷却）。
- 唤醒率人审实测：10 呼 11 命中、误触发阈值内（`human-test/RESULTS-2026-09-24.md`）。

### 自定义唤醒词（一次性流程，禁止手写 token）

1. 人写 `config/kws/keywords_raw.txt`，格式 `词 [:boost] [#threshold] [@显示名]`，如 `小码小码 :1.5 @小码小码`。选词建议 3–4 音节、含翘舌/开口音。
2. 生成 token 文件：

   ```powershell
   sherpa-onnx-cli text2token --tokens models/sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20/tokens.txt --tokens-type phone+ppinyin --lexicon models/sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20/en.phone config/kws/keywords_raw.txt config/kws/keywords.txt
   ```

   ⚠️ pip 包内无 `sherpa-onnx-cli.exe`，可用兜底：`python -c "import sys; sys.argv=[...]; from sherpa_onnx.cli import cli; cli()"`（需补装 click / sentencepiece / pypinyin）。
3. `keywords_raw.txt` 与生成物 `keywords.txt` 一起入库；改词后跑离线冒烟 `scripts/m2_kws_wav.py` 验证。

## 语言限制：中文

本项目**面向中文（普通话）语音交互设计与调优，非中文输入不受支持**。各处合力：

- winTTS 强制挑选第一个 `zh-*` 语音（本机为微软 Huihui）；VoxCPM 母音色亦为中文素材。
- 唤醒词、ack/退出/权限应答等全部固定话术为中文；权限判定词表（允许/拒绝…）按中文匹配。
- 断句标点集以中文全角为主；ASR 热词内置中文 WoW 术语（Qwen3 system-prompt 上下文偏置）。
- voice agent 的 system prompt 全中文，要求口语化短答、禁表格/代码块；输出走中文 TTS。
- ASR 模型（Qwen3-ASR / KWS zh-en）本身支持多语言/英文，但链路上下游均按中文调优，**不要指望英文或方言可用**。另注意 Qwen3-ASR 无 ITN，数字以汉字形态输出（"二百八十九"）。

## WoW 知识库（默认自带，可自主编译）

仓库默认自带一套 **WoW（魔兽世界）国服正式服（retail 12.x）** 知识库，位于 `config/oc2/wow-kb/`（git 唯一真源），部署副本在 `tools/oc2-home/config/opencode/wow-kb/`（对库只读）。

- 内容：39 条知识条目 + 5 条元文件——副本流程（`retail/raids/`）、UI/设置路径（`retail/ui-settings/`）、社交/组队、插件目录（`addons/_catalog.md`）、任务 bug 等；`qa/` 提供「玩家口语问法 → 口播底稿」视图；`INDEX.md` 为总索引。
- 使用方式：玩家问 WoW 问题时，oc2 先加载 `wow-kb` skill，按其五步协议「grep 查库 → 查不到自主研究（联网检索，预算硬线）→ 证据分级（一手源码=‘我核实过’，孤证=‘我不确定’）→ 口播作答 → 无据兜底」。库里没有 ≠ 拒答。
- 默认口径：未特别说明一律按**国服 + 正式服最新版本**；时效核对以 `_meta/freshness.md` 为唯一真源（当前基准 build `12.1.0.69283`）。

### 自主编译（离线侧补录/修订条目）

直播中 agent **不写库**；研究出的新结论由离线侧走 `.agents/skills/wow-kb-authoring/SKILL.md` 流程固化成条目：

1. 先读现有库防重复（`INDEX.md` → grep `qa/` → 读单条），判轴（retail/classic/forever）。
2. 按「问题类型 → 渠道」路由检索并核验（暴雪 UI 源码镜像 `wind-addons/BlizzardInterfaceCode` 为 S 级一手源；中文流程走百度 SERP+NGA 多源交叉；新域名先 HEAD 探测；不通源见 `_meta/sources.md` 禁试清单）。
3. 照模板写条目（frontmatter + TL;DR + 方向性声明强制；行数预算：条目 ≤60、qa ≤20），回写 `INDEX.md` 与 `_meta/freshness.md`，方法论回填 `_meta/sources.md`。
4. 部署（永改源不改部署区）：

   ```powershell
   Copy-Item -Recurse -Force config\oc2\wow-kb\* tools\oc2-home\config\opencode\wow-kb\
   ```

5. 生效时机：oc2 只在新 session 读库，**直播中的会话不热更**。

## 已知限制（摘要）

- 播报期自听无软件防护，必须硬件 AEC 或耳机（见上）。
- 控制台仅回环、无鉴权；端口 4096 被硬拒；绑定失败 exit 4，不自动顺延。
- 会话退出依赖模型听话调用 `voice-end`；无回合总超时，卡住靠开口打断或 stop.bat。
- 麦克风不做热插拔自动恢复：采集停摆会周期语音报警，需人工重启。
- VoxCPM 后端吃显存（~3GB 常驻）且偶发超长合成，默认 winTTS 更稳。
- 无应用级配置文件（YAML/JSON）：设备、阈值等以代码内 dataclass 默认值为准，改动即改代码。
