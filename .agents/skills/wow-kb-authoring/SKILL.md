---
name: wow-kb-authoring
description: Use when 向 oc2 的 WoW 知识库 (config/oc2/wow-kb) 补入/修订条目 — e.g. 玩家问了库里没有的 WoW 问题、直播答错要回填、要新增机制/设置路径/命令/副本流程知识。先读现有库，再按"问题类型→渠道"方法论检索核验，回写源目录并部署，新渠道发现同步回填 sources.md。
---

# 向 oc2 WoW 知识库补内容（离线侧编写流程）

## 背景

- 本项目（v1 开发环境）用子进程启动 opencode 2（oc2，`src/opencode_client/`）服务语音助手；主播直播时 oc2 靠只读加载的 wow-kb 回答 WoW 问题，**oc2 自己不写库**。
- 库的**唯一真源**是 `config/oc2/wow-kb/`（git 入库）；运行副本部署在 `tools/oc2-home/config/opencode/wow-kb/`（tools/ 被 gitignore）。铁律：**永改源不改部署区**，改完再复制部署。
- 库内规范文件是编写前的强制阅读物：`_meta/writing-guide.md`（模板+红线+行数预算）、`_meta/sources.md`（证据源优先级与可达通路）、`_meta/verification.md`（核验操作手册）、`_meta/freshness.md`（时效看板）、`INDEX.md`（总索引）。
- 补库触发场景：直播中 oc2 走了"超纲话术"（库里没有）、答错（需回填纠错）、或玩家问题涉及库里未覆盖的机制/设置/命令/副本流程。

## 目的

1. 把一次性的联网检索成果**固化为经过核验的库条目**，下次 oc2 直接命中，不再重复搜索、更不许凭模型记忆回答版本相关内容。
2. 保证增量内容符合库的防事故纪律（区分内置/插件、带版本区间、方向性声明、证据可溯源、宁可 unverified 不编造）。
3. **方法论本身也是库资产**：补库只是表，"哪类问题去哪个渠道找最全最准"才是里子——每次检索验证出的通路（含走不通的坑）回填 `_meta/sources.md`，不让下次再从零试错。

## 流程

### 第 1 步：先读现有 wow-kb（防重复、防冲突）

1. 读 `INDEX.md` 总表，grep `qa/`（玩家口语触发词）→ 再 grep 全库 `aliases|title|zhcn_terms` 中文词 → 命中则 read 那个**单个**条目文件。禁止整库读入。
2. 已有条目：只做**修订/追加核验日志**（核验日志只追加不删除）；build 不匹配或已过期 → 按 writing-guide 红线 4 处理（outdated 保留正文+superseded_by，新条目继承旧 aliases）。
3. 确认是空白 → 进第 2 步。同时判轴：产品线（retail/classic/forever，判不出默认 retail）、服务器（默认国服）。

### 第 2 步：根据用户问题搜索并核验（重点是方法论，不是抄答案）

先按问题类型路由渠道（"哪类信息在哪最全"，均已实测，详见 `_meta/sources.md`）：

| 问题类型 | 主渠道（全/准） | 替代与顶棚 |
|---|---|---|
| 内置机制、CVar、斜杠命令、设置页路径、弹窗行为 | `wind-addons/BlizzardInterfaceCode` UI 源码镜像（S 级唯一一手源：api.github.com 定 build → raw 钉 sha 读文件 → grep） | 无替代；镜像里搜不到 ≠ 游戏一定没有，走兜底话术 |
| build 版本号 | api.github.com commits（提交标题即 build） | 备镜像 husandro / manbastiencs；**禁 .toc**（12.x 已删 Interface 行） |
| zhCN 按钮/界面文案 | cn.bing 中文搜"功能名+设置/选项" | NGA 摘要/官网新闻佐证 → 回填 `_meta/glossary.md`；GlobalStrings 编译进引擎，UI 镜像搜不到 |
| NPC/坐标/任务流程/副本进入/奖励/开放时间 | baidu SERP（playwright）捞原创帖：NGA 正文（**本机持久 profile 有登录态=升 S**，纪律见 sources.md 第 10 条）/贴吧/3DM ≥3 独立源、关键值逐项一致 | 仅摘要=B/顶棚 unverified；wowhead/wowpedia 本机不通（禁试清单），别硬撞 |
| 上线日期/国服 vs 国际服节奏 | 官网 + cn.bing | bing RSS 对中文新增长尾词失真，一次不中换路 |
| 某行为是插件还是原生 | 先 grep `addons/_catalog.md` → 命中=插件 | 未命中回第 1 行查 UI 镜像；两边无=兜底，禁无证据断言。判插件**死活**必须走中文检索（bing"名+版本+还能用"）+GitHub 搜索带 `fork:all`（默认隐藏 fork），国服主分发=miliui/大脚站/NGA 搬运（Cell 误判事故 2026-09-25） |
| 疑似服务端规则(gamerule) | 客户端镜像证明不了 | 强制 unverified+证据边界节（verification.md §4.4） |

取证纪律：

1. 结论必须落在证据等级上：S 级可 verified；B 级 ≥3 交叉顶棚 unverified；C 级（百度 AI 卡片、NGA 正文）只当线索不当依据。
2. 核验操作照 `_meta/verification.md` 对应节执行：build 确认、CVar 消费点全树 grep（说"唯一消费点"前必须穷尽候选目录）、内置 vs 插件决策树、双人机制方向性三问。
3. 硬约束：任何新域名先 HEAD 探测；URL 防 routify 改写（evaluate 分片拼接或 bash 直连，routify 残留禁入库）；浏览器操作遵守项目 playwright skill；全树排查等复杂调研用 Task 工具派 **deepthink** subagent 执行，结论回收后由本会话落笔。
4. 检索中发现**新的类型→渠道映射或新坑**（某站对某类内容特别全/特别坑、新可用域名）→ 记入第 3 步，回填 `_meta/sources.md` 通路表或禁试清单。

### 第 3 步：补入库并部署

1. 新条目**照抄 `retail/social/auto-accept-invite.md` 模板**：frontmatter 必含 id/title/aliases/applies/mechanism/status/superseded_by/evidence/verified；正文必含 TL;DR(≤3行)/方向性声明(三项强制)/机制细节/版本差异/常见误区/相关条目/核验日志。
2. 行数预算：条目 ≤80、qa ≤30、INDEX ≤150、_meta 各 ≤200；qa/ 只写问法+口播底稿+权威条目指针，禁止写机制细节。
3. 回写 `INDEX.md` 加一行（id|文件|status|build_ref）；涉及时效的同步 `_meta/freshness.md`。**删改与新增同级**：本次检索触及生态级事实（插件政策、站点停运、机制变更）→ 当轮同步修订或删除所有受影响条目的过时表述（核验日志记理由，新鲜事实进 freshness 生态事件节），对直播不再有价值的内容删文件+INDEX 除名（git 保历史），禁止新旧口径并存。
4. 方法论回填：本次新探明的"类型→渠道"、新可用域名、新踩的坑写入 `_meta/sources.md`（通路优先级表/禁试清单/顶棚原则相应节），同样遵守 ≤200 行预算。
5. 部署（源→部署区单向复制，覆盖同名）：
   ```powershell
   Copy-Item -Recurse -Force config\oc2\wow-kb\* tools\oc2-home\config\opencode\wow-kb\
   ```
   oc2 只在 session_new 时读库，直播中的会话不热更——部署后需新回合/新 session 才生效。
6. 收尾：向用户汇报新增/修订条目与证据等级；变更**不提交 git**（等用户明确指示）。

## 产出清单（每次按此交付）

- [ ] 查重记录（命中已有条目则注明修订点）
- [ ] `config/oc2/wow-kb/<目录>/<条目>.md`（模板齐全、status/evidence 如实）
- [ ] `INDEX.md`（及必要时 `freshness.md`/`glossary.md`）更新
- [ ] 若涉事实修正：受影响条目已全部同步修订/删除并注明理由
- [ ] `_meta/sources.md` 方法论回填（无增量则注明"本次无新渠道发现"）
- [ ] 已复制到 `tools/oc2-home/.../wow-kb/` 部署区
- [ ] 一句话告知用户：口播该条目时需要的限定词（如"社区攻略交叉过"/"镜像超前"）
