# 需求：AI 建议 WoW 装备获取手段（剪贴板 simc 字符串 → 循序渐进提升路线）

日期：2026-09-30 ｜ 状态：**需求（待决问题见 §8；真机串已采集核验 §3，SimC Addon 12.1.0-04 已装）** ｜
关联：M5 PERM 语音授权链 `src/orchestrator/core.py`、oc2 配置 `config/oc2/`、知识库 `config/oc2/wow-kb/`

## 1. 背景与目标

主播想知道"我这只号下一步该打什么本、换什么装备"。手工描述装备不现实，
而游戏内 **Simulationcraft 插件**（指令 `/simc`）一键把当前角色档案（职业/专精/等级/
全身装备含 itemID/附魔宝石/特质）生成字符串并**复制到 Windows 剪贴板**。

目标链路：用户语音提问 → oc2 触发 bash 权限申请 → **语音授权**（现有 PERM 机制）→
读剪贴板取 simc 串 → 解析出职业专精+当前装备 → 查 wow-kb / 上网取证获取该专精推荐装备
与获取条件 → 按当前装等**循序渐进**给出"下一步打什么"的语音建议。

## 2. 现有底子：授权链零新代码

"获得语音许可后读剪贴板"完全复用 M5 既有 PERM 通路，**不改 src/ 一行**：

| 环节 | 现场 |
|---|---|
| oc2 申请 shell（`Get-Clipboard`） | ⚠️ **初版前提已证伪（§12）**：v2.0.16 基础策略 `*:*:allow`，"不在列→ask"不成立；**必须显式加规则** `{action:"shell",resource:"*Get-Clipboard*",effect:"ask"}`（窄匹配，不影响研究类命令） |
| 编排器播授权问句、进 PERM | core.py:258-263：`OcPermission` → `_speak(perm_prompt)` → `_go(PERM)` |
| 用户说"同意/拒绝" | core.py:357-361 `_answer_perm` → `oc.reply_permission(sid, rid, decision)` |
| 超时按拒绝 | core.py:381-383（15s，`perm_timeout_s`） |

取串命令（oc2 侧执行，无需 voice-code 提供封装）：

```powershell
powershell -NoProfile -Command "Get-Clipboard -Raw"
```

## 3. simc 串解析口径（真机样例已核验，2026-09-30）

初版"期望格式"（`sim_type=simc:` 锚、`class=` 行、`slot=<名>,<itemID>,...`）**被真机证伪**，
实际格式以本小节为准：

- **识别锚**：头部注释行 `# SimC Addon <插件版本>`（下跟 `# WoW <build>, TOC <toc>`）；无 `sim_type=` 行。
- **身份**：职业藏在角色名行的 key 里（如 `evoker="蒂思特妮亚丝"`）；`spec=`、`level=`（角色等级）、
  `role=`、`race=`、`region=cn`、`server=`、`professions=` 均在。
- **装备段**：每槽两行 = `# <中文装备名> (<单件装等>)` 注释 + `slot=,id=<itemID>,bonus_id=…,content_tuning=…`；
  16 槽（head…off_hand），**空槽=该 slot 行缺失**。
- **平均装等**：串内无 `avg_ilvl=`，但单件装等逐槽现成——**逐槽均值即得**（样例 16 槽算出 285.3，
  与角色面板一致）。⇒ 原 Q2 三候选全部不需要，**串内直算定案**。
- **额外高价值字段**（真机发现，超出初版预期）：
  - `slot_high_watermarks=0:295:295/…/14:0:0/…`：逐槽历史最高装等（`:0:0`=空槽）→ 短板槽定位比均值准；
  - `catalyst_currencies=`、`upgrade_currencies=`：化身/升级材料余量 → 判"能否立刻升装"；
  - `### Gear from Bags` 段：背包里的备选装备（同 `# 名 (装等)` 格式）→ "换上即提升"的零成本建议来源。
- **噪音**：`talents=` 本体 + 4 套 Saved Loadout 的长 base64 行（样例串 116 行/3.9KB，talents 段占约 12 行），
  建议剔除后再进模型。

裁剪策略两档（Q1 待拍板；样例总量仅 ~3.9KB，剔除 talents 段后更轻，**A 档压力比初版预估小得多**）：

| 方案 | 做法 | src/ 业务代码 | tools/ 脚本 |
|---|---|---|---|
| **A. LLM 自读（MVP 推荐）** | 命令级剔除 `talents=` 行（PowerShell 一行 `-notmatch '^#? ?talents='`），其余全文入上下文由模型直读职业/专精/逐槽装等/短板 | 0 | 0 |
| **B. 摘要脚本（A 不够再上）** | `tools/simc_summarize.py`：stdin 进原文，stdout 出 ≤40 行 JSON（class/spec/level/平均装等/逐槽 id+装等/watermarks 短板表/背包备选） | 0 | **~60 行**（不进 src/，不算业务代码；附 UT fixture +~40 行） |

真机 fixture 现状：原始串含角色名/服务器名，入库前需脱敏（name/server/checksum 打码）；
已存 `D:\Temp\opencode\simc\clipboard-sample.txt`（临时），实现阶段再落 `tests/fixtures/`（方案 B）
或 `human-test/`（方案 A 的人测对照样本）。

## 4. 推荐知识：查库优先、现查兜底（复用 wow-kb 既有协议）

不新建检索子系统，走 `config/oc2/AGENTS.md` 的 wow-kb 五步协议（查库→自主研究→证据分级作答）：

1. **库内近路**：`wow-kb` 新增 `retail/gear/` 类目（INDEX.md 目录约定处补一行说明）：
   - `gear-progression-path.md`：通用循序渐进路线——装等区间 → 解锁活动的先后序
     （世界任务/英雄本门槛（已有 `retail/raids/lfd-heroic-121-list` 可引用）/断层等级/
     M+ 低保/LFR→普通→H 团本），每档标明"门槛数值+出处+适用版本"，按 `_meta/freshness.md` 跟版本核。
   - 专精装备条目：每个专精 1 篇（推荐装备来源表：掉落本/制造/声望/代币兑换 + 获取条件）。
     **首批只覆盖主播主玩专精 1-2 个**，其余按需补录（走 wow-kb-authoring 流程），
     **禁止**一上来铺 39 专精全量。
2. **库里没有→现查**：按 AGENTS.md 检索首选 NGA 职业区帖（S 级，登录态 profile 已就绪），
   退路 websearch/webfetch，三档口气（我现查的/交叉过的/没把握的）播报。

### 4.3 装备推荐来源实测清单（2026-09-30 本机 Playwright/HEAD 核验，恩护视角）

| 来源 | 通路/证据级 | 状态 | 能给什么 |
|---|---|---|---|
| **NGA 巨龙群岛(851)区** 恩护PVE 精贴 | S（正文） | ✅ 现役 | 12.1 团本配装/手法帖（如 tid47436848 塑焰恩护 H9/9、tid47569215 烈毒之渊 M后二）；12.0 精华帖合集 tid46486877 是入口总目录；问答/求助帖暴露真实痛点 |
| **Maxroll** `maxroll.gg/wow` | B（英文权威） | ✅ 200 可达 | `preservation-evoker-mythic-plus-guide` 标题带 **12.1.0 / Updated Aug 11**，正文有 STAT PRIORITY / GEAR / Trinkets / Enchantments 分段——**属性优先级+各槽推荐**一手结构化来源 |
| **Bloodmallet** `bloodmallet.com` | B | ✅ 200 可达 | 各内容层级(trough/dungeon/raid) BiS 与权重对比（图驱动，取数需页面渲染）；英文站，国服数值仍以游戏内为准 |
| warcraft.wiki.gg | 曾定 S | ❌ 对 12.x 装备失效 | 实测 `Item:272250`（本号头盔 itemID）**404 无该页**——wiki.gg 未收录 12.x 装备逐件来源，**不能**当"itemID→获取条件"数据库用 |
| wowhead / 灰机 / curseforge | — | ❌ 禁试（sources.md 已登记本机不通/403） | 初版 §4.2"退路 wowhead 装备页"**作废** |
| 17173 / 3DM / baidu 摘要 | C | ⚠️ 仅线索 | 中文搬运/攻略稿，混 AI 卡与旧版；须回溯原创（NGA/官网）交叉，不单独采信 |

**推论**：**"逐槽推荐 + 获取条件"的主力一手源 = NGA 恩护精贴（S，国服口径）+ Maxroll/Bloodmallet（B，结构化 BiS/权重）交叉**。
itemID→"从哪个本掉落"这类**逐件查询没有可用国际数据库**（wiki.gg/wowhead 全断），
故 §5 决策树"短板槽→最便宜获取途径"应**依赖 §4.1 已入库的专精配装表**（离线按本/团本/制造/代币归类整理好），
而非运行时逐件现查。运行时现查只用于"库里没覆盖到的槽位/新赛季变动"，且落 NGA 帖正文而非数据库。

## 5. "循序渐进"的输出口径

- 只报**接下来 1-2 步**，不念全路线清单（TTS 线性，voice agent 已有 ≤3 句纪律，
  `config/oc2/agent/voice.md`）。
- 决策树（写进 AGENTS.md 新节，供 oc2 执行）：
  ①先补短板：空槽/明显低于均值槽位 → 给该槽位**最便宜获取途径**（对应 §4 表）；
  ②装够门槛：达到下一活动门槛 → 解锁推荐"打什么本"（引用 KB 副本条目的排本顺序）；
  ③都够：给下一档目标（更高 M+/H 团本/断层升级路线）。
- 播报必带适用版本与证据档次；数值门槛一律来自 KB/取证，**模型不得口算编造装等数字**。

## 6. 权限与隐私红线

- 剪贴板可能装着与 simc 无关的隐私内容。解析前先验头部锚（§3 真机锚 `# SimC Addon`）：
  不匹配 → 拒解析，只播"没找到 simc 字符串，请先在游戏里输 /simc 生成再问我"。
- 原文**不落盘、不转述**：日志/镜像只记"命中/未命中 + 串长度"，不记内容；回答只输出解析后的游戏字段。
- 授权语义不变：读剪贴板=一次 bash ask=一次语音"同意"，每次会话重新申请，不做持久放行。

## 7. 明确不做

- 不做剪贴板常驻监听/轮询（只在语音触发、拿到授权后读一次）。
- 不读 WoW 进程内存、不做游戏内自动化操作。
- 不建立角色档案数据库（每次实时解析，跨会话不记忆装备）。
- 不改 `src/` 状态机（PERM 通路现成）；不动 ASR/TTS/KWS/控制台。
- 不做全专精知识库一次性铺量（先主号专精，按 §4 补录机制滚动）。

## 8. 待决问题（已拍板，2026-09-30）

- **Q1** 解析档位：**拍板=A；deepthink 复核后修正为 A+**（形态调研见 §12：命令模板本体做锚校验/均值/脱敏，
  0 新代码；plugin 工具形态被 v2.0.16 权限证据否决；真机不过→C-lite skill 捆绑脚本升级位）。
- **Q2** 装等来源：**已定案**：真机样例每槽注释行自带单件装等，均值串内直算（见 §3），口报与映射表都不需要。
- **Q3** 首批专精：**定案**=唤魔师·恩护（Preservation）。**运行时口径**：解析出 class/spec 后，
  先语音向用户确认"你是唤魔师恩护吗"——确认后才按恩护条目作答；串里 spec 非 preservation
  或用户否认 → 说明库未覆盖该专精，降级为现查作答（§4.2），不硬套恩护内容。
- **Q4** 触发与新鲜度：**定案**——含"装备/提升/打什么本"类意图即走本流程，不要求主播先声明"我已复制"
  （§3 头部锚 `# SimC Addon` 校验本身就是防误读闸）。串头注释自带复制时刻（`… - 2026-09-30 22:45 - …`），
  时刻距本次会话 >30 分钟 → 播报一句"这是×点×分复制的旧串，要不要我先让你在 /simc 重抄一份？"，
  用户口头坚持用旧串则继续；锚不命中 → 播引导话术（§6）。

## 9. 业务代码行数估计（AGENTS.md 纪律）

| 文件/类别 | 现规模 | 估计增量 | 内容 |
|---|---|---|---|
| `src/**`（业务代码） | — | **0 行** | PERM/编排/控制台全部复用 |
| `tools/simc_summarize.py`（仅 Q1=B 时） | 新建 | **~60 行** | simc 串→JSON 摘要，不进 src/ |
| `config/oc2/AGENTS.md` | 24 行 | **+12 行以内** | 新节「装备建议工作流」：取串命令、锚校验、决策树、隐私红线 |
| `config/oc2/wow-kb/retail/gear/*.md` | 新建 | 2-3 篇知识文件 | 通用路线 1 篇 + 主玩专精 1-2 篇（知识非代码） |
| `config/oc2/wow-kb/INDEX.md` | 79 行 | +3 行 | 新类目登记 |
| `tests/`（仅 Q1=B 时） | — | +~40 行 | fixture 解析断言（fixture 用脱敏样例） |

## 10. 验收

- **人测主项（真机，含音频）**：游戏内 `/simc` → 语音"看我接下来打什么本提升装备" →
  听到授权问句 → 说"同意" → 助手正确报出职业/专精/等级，并给出与装等匹配的下一步建议
  （与角色面板和 KB 路线一致）。剪贴板无 simc 串场景 → 播引导话术、不瞎解析。
- **人测次项（采集 fixture）**：**已完成（2026-09-30）**——SimC Addon 升到 12.1.0-04 后真机 `/simc`，
  `Get-Clipboard -Raw` 取串成功（116 行/3.9KB），§3 期望字段核对完毕：锚/class/装备行格式三处证伪，
  已按真机改写 §3；意外收获 watermarks/背包备选/升级货币三类字段。原始串暂存
  `D:\Temp\opencode\simc\clipboard-sample.txt`，实现阶段脱敏（角色名/服名/Checksum）后入仓。
- **UT（仅 Q1=B）**：fixture → 摘要 JSON 断言（class/spec/槽位数/空槽识别/非 simc 串拒解析）。

## 11. 首轮试点记录（2026-09-30，真号+真库，用户指令"先推 3 件、核实能不能打"）

- **来源已固化进 wow-kb**（非临时调研）：`retail/gear/preservation-evoker-gear-path.md`
  （分槽来源表 + 装等档位判定 + 运行时协议：语音确认专精→首推 3 件→追问再续 3 件）
  + `qa/retail-gear-next-step.md`；`_meta/sources.md` 新增「装备建议/专精配装类渠道」节
  （主力=Maxroll 表(B)+NGA 职业分区钉中文正名(S)+simc.org 档位参照；证伪死路 8 项含
  wiki.gg 12.x 无逐件页、db.17173 死站）。INDEX/freshness 同步，已复制部署区
  （oc2 需新 session 才读到）。
- **试点分析**（真机号：唤魔师·恩护·均装 285.3；短板=腿 259/披风 276/饰品 1 号 276/副手 272）：
  - **能不能打**：LFR 门槛 273 → 285 **宽裕**（超线 12 装等，据库内多源交叉值）；
    普通团入场 ~290（simc.org MID1 样号口径）→ **勉强**，且腿 259 单槽比均值更拖累进组评分；
    英雄团/高层钥匙 → 未达档，不推。英雄本/低层钥匙未见装等硬闸（游戏内排队面板为准，不编数）。
  - **首推 3 件话术（口播样例）**：①先排随机团烈毒之渊摸盘魂者内克扎莉出的饰品，这季奶龙 S 档，
    你 285 进门宽裕；②最烂的腿盯盘卷祭坛出的腿件，随机团四区已全开能排到，或用化生台转套装腿；
    ③披风同出盘卷祭坛，不想等团本就制造披风打上织梦附饰（S 级槽里最便宜一件），
    手里老兵纹章先把升满一件再拿新。英文装名一律不口播（红线 7）。
- **行数核账（对 §9 预算）**：src/ **0 行** ✓；KB 实际=gear 条目 64（≤80）、qa 13（≤30）、
  INDEX 81（≤150）、sources 104（≤200）、freshness 38（≤200）✓；`config/oc2/AGENTS.md`
  工作流节**未动**（留待实现阶段：Q1=A 已拍板，AGENTS 节+oc2 端到端试跑是下一步）。
- **遗留**：Maxroll 表体=单源 B（NGA 精贴 tid=47436848 开荒中"补稿码字ing"，成形后作二次交叉升格）；
  12.1.5/S3 上线整表换版重验（已挂 freshness 触发）。

## 12. 形态调研：工具 vs skill（deepthink，2026-09-30，opencode v2.0.16 源码+官方文档实证）

**问题**：本功能给 oc2 做"plugin 工具+skill / 仅工具 / 仅 skill"？
**结论=仅 skill 层（B+：一条逐字钉死的授权命令模板 + 既有 wow-kb），不做 plugin 工具；预留 C-lite 升级位。**

### 12.1 一票否决项：v2.0.16 的 plugin 工具触发不了授权 ask
源码逐层核实（api.github.com/jsDelivr，tag=v2.0.16）：`packages/schema/src/tool.ts` 的 Tool.Context
**无 ask/permission API**；`packages/core/src/tool.ts` 对 plugin 工具的 `options.permission` 只做
"整段 deny 时隐藏工具"的可见性过滤，运行时**无人替它 assert**；内置 shell/MCP 工具才自行
`permission.assert()`（action 分别为 `shell` / `<server>_<tool>`）。"plugin 工具可 ask"在 dev 分支
`registry.ts`（`ctx.ask` 桥）**未发版**（v2.0.20 亦无）。→ 做 plugin 工具=剪贴板读取**无声绕过**
§2 语音授权硬需求；`opencode.json` 给它配 ask 是死规则。MCP server 形态可 ask，但要新增常驻子进程
（startup 超时面，playwright MCP 90s 先例），维护成本>收益，不取。

### 12.2 共同前提缺陷（🔴 本调研最重要的发现，§2 表已勘误）
v2.0.16 每个 agent 基础策略第一条=`{action:"*",resource:"*",effect:"allow"}`
（`packages/schema/src/agent.ts`），现网 `opencode.json` 无 shell 规则 → **现状下
`Get-Clipboard` 直接放行、不产生 permission.asked，语音授权链根本不会触发**（与 M6 稿
T-M6-3"会 ask 的只有 external_directory/.env 两类"实测一致）。修复=`config/oc2/opencode.json`
permissions 数组加一行（源+部署副本同步）：
```json
{ "action": "shell", "resource": "*Get-Clipboard*", "effect": "ask" }
```
后匹配覆盖基础 allow；Windows 匹配不分大小写；管道复合命令"any ask asks"整体触发授权；
编排器只回 once/reject（match_permission 无 always）→ §6"每次重新申请、不持久放行"自动满足。
授权问句将播"需要授权：shell。说允许或拒绝。"（action 字符串=`"shell"`，events.py:58 透传）。

### 12.3 社区一手原则映射（Anthropic Engineering ×2 + MCP 官方 ×1）
- 《Equipping agents…Agent Skills》：skill=指令+**脚本**+资源；"deterministic reliability that
  only code can provide"→ **锚校验/剔talents/装等均值/脱敏属确定性环节，下沉进命令/脚本**，
  专精确认/推3件/能不能打属判断，留 KB（§11 运行时协议原样复用）。opencode Skills 文档同款
  "keep related scripts beside SKILL.md"。
- 《Writing effective tools for agents》：工具应"consolidate frequently chained multi-step
  tasks in a single tool call"→ 取串+校验+清洗+算数**合并为一次调用**；且"agent 可能幻觉漏调工具"
  → 授权闸必须建在配置规则×shell assert 上，不能建在"模型会先调某工具"的自觉上。
- MCP 官方：Tools=model-controlled 且"may require user consent"→ 读剪贴板=action 走 consent
  通道；KB 条目=resource；工作流指令=prompt/skill。各归其位。

### 12.4 对 Q1 拍板的修正
Q1"A=LLM 自读、0 代码"**保留但升级为 A+**：单条 PowerShell 命令模板逐字写进 oc2 侧指令
（AGENTS.md「装备建议工作流」节 +8-12 行；或独立 `skills/simc-gear/SKILL.md` ~25-30 行，二选一，
倾向后者以免 AGENTS 膨胀），命令本体含：UTF8 编码自设（PS5.1 cp936 中文打花坑）→ 锚判定
（不中输出 `NOT_SIMC`）→ 剔 `talents=` → `Measure-Object -Average` 出均值（**§5"不口算"红线
由命令保证**）→ name/server 行打码（**§6 隐私：全名不进模型上下文/中转层**）。新增代码文件 **0**。
**升级位 C-lite**：真机验收若出现小模型抄错长命令（模板 ~450 字符，风险真实）或仍口算数字，
即转 skill 捆绑 `scripts/read-simc.ps1`（~55-70 行，只吐脱敏 JSON 摘要，模型抄短命令
`powershell -NoProfile -File …`）。plugin 工具=存档为"opencode 发版含 ctx.ask 后的远期选项"
（届时 ask 问句还能带具体工具名）。

### 12.5 落地清单（B+ 形态，src/ 0 行、plugins/ 0 新文件）
| 文件 | 增量 | 内容 |
|---|---|---|
| `config/oc2/opencode.json`（源+部署副本） | **+1 行** | §12.2 窄规则——**唯一不可省项** |
| `config/oc2/skills/simc-gear/SKILL.md`（或 AGENTS.md 节） | ~25-30 行 | 钉死命令模板+三条纪律（引用命令输出/NOT_SIMC 只播引导/旧串提醒 Q4）+转 wow-kb 运行时协议 |
| `config/oc2/wow-kb/retail/gear/…path.md` | +1 行 | 协议第 0 步注明"数据源=授权命令输出（已脱敏+已算均值）" |
| 验收追加 | — | a) 真机确认 ask 触发、语音同意后执行、15s 超时拒绝；b) 中文无乱码（UTF8 自设生效） |

### 12.6 落地记录（2026-09-30，用户"全部按 deepthink 要求改"）

| 项 | 估计 | 实际 | 状态 |
|---|---|---|---|
| `config/oc2/opencode.json`（+部署副本）| +1 行 | **+1 行** `{action:"shell",resource:"*Get-Clipboard*",effect:"ask"}` | ✅ JSON 校验过 |
| `config/oc2/skills/simc-gear/SKILL.md` | 25-30 行 | **27 行**（钉死命令+红线判读+转 wow-kb 协议） | ✅ 已部署 |
| `retail/gear/preservation-evoker-gear-path.md` | +1 行 | **+1 步**（协议第 0 步：数据源=SIMC_OK 摘要，禁心算）→65 行≤80 | ✅ 已部署 |
| `src/**`、`config/oc2/plugins/**` | 0 | **0** | ✅ 未动 |

- **命令正路测试**：真机串跑 2 次+样本文件回放，输出一致——16 槽、`avg=285.3`、`worst=legs:259
  off_hand:272 trinket1:276`、`time=2026-09-30 22:45`，输出中无角色名/服名（脱敏在源头）。
- **命令阴路测试**（意外实机验证）：剪贴板被玩家换成游戏控制台一行（28 字符）→ 输出 `NOT_SIMC`，
  锚卫兵按 §6 拒绝解读 ✓。
- **形态坑记录**：命令必须**裸一行**执行（opencode shell=PowerShell 5.1 直连）；套
  `powershell -Command "…"` 双引包装会被外层展开 `$变量` 打碎——SKILL 钉死原样正是防这个。
- **待办**：a/b 两条真机验收（ask 触发+语音授权+超时、长命令抄写稳定性）需下一次 `run.bat`
  会话做；小模型若抄错 700 字符命令 → 切 §12.4 预留的 C-lite（`skills/simc-gear/scripts/` +ps1）。

## 13. 真机验收记录与卡点修复（2026-10-01 凌晨，logs/voice-code.log 00:41-00:46）

**通过项**：
- 验收 a ✅：`OcPermission shell` 首枪触发 → 播"需要授权：shell" → 语音"允许"→放行（§12.2 窄规则生效）。
- 验收 b ✅：命令原样执行成功；口播"平均装等二百八十五点三"与 SIMC_OK 输出逐字一致（无心算）；
  中文数字由模型自然转读，无乱码暴露。
- 流程 1-5 全对：加载 simc-gear→授权→SIMC_OK→确认专精问句→**推 3 件**（腿=盘卷祭坛套装件/化生台、
  饰品=盘魂者内克扎莉、副手=尼姆瑞莎，"随机团烈毒之渊就出"）+能不能打判定（285.3 排 LFR 宽裕、
  普通团入场线约 290、别硬挤英雄）+版本限定+"还有呢再续三件"。C-lite 未触发（抄写零误差）。

**卡点（用户体感"卡住没继续"）= `question` 工具死锁**：
- 00:45:14 追问轮 oc2 调 `question`（v2 内置**交互式选项工具**，TUI 弹按钮等人选；语音/REST 会话
  无人应答→回合永久阻塞，用户再催的 AsrText 按 R3 被忽略——卡死观感来源）。
- 修复（已部署，src/ 0 行）：`opencode.json` permissions 追加 `{action:"question",resource:"*",effect:"deny"}`
  （官方文档 Actions 表证实该 action 存在；deny 即工具不可见）；`agent/voice.md` 加一句双保险
  （"追问只用口语问句，绝不调交互式选项工具"）。**待重测**：重启 run.bat → 说"还有呢"→ 应续第二批 3 件。

**观察项（不拦截、记录待议）**：
- O1 热词幻听句：00:43:32（确认专精窗口）ASR 吐出**纯 hotwords 列表句**"盘卷祭坛。乌拉特克。…潮缚石窟"
  ——set-hotwords 装填后 SenseVoice 偏置解码在无人声时的幻觉，asr sentinel 已标（#1）但仍入 COLLECT；
  本次侥幸被判成"确认"。是否让编排器丢弃"纯热词句"属代码改动，单独立项再议（AGENTS.md 自听纪律：只观察不设防）。
- O2 回合无 watchdog：question 挂起期间 RUNNING 无任何兜底（用户只感知沉默）。若社区形态再出
  "会阻塞等 UI 应答的工具"，需给 RUNNING 加长静音提醒/超时——列为后续需求候选，不在本条范围。
