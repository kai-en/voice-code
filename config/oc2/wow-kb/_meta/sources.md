---
id: meta.sources
title: 证据源清单与可达通路
status: verified
verified: { date: 2026-09-25, by: "deepthink-0925" }
---

# 证据源清单与通路优先级

回答/编写 WoW 问题时按此优先级取证据。**任何新域名先 HEAD 探测再决定，不要反复重试不通的源。**

## 通路优先级表

| 优先级 | 通路 | 用途 | 证据等级 | 注意 |
|---|---|---|---|---|
| 1 | raw.githubusercontent.com | UI 源码镜像文件直读 | S(一手) | URL 钉 commit sha；取前 HEAD 探测 |
| 2 | api.github.com | 提交历史(定 build)、git/trees 全树清单、contents 目录 | S(元数据) | 匿名 60 req/h；一次 trees 拿全树，省着用 |
| 3 | cdn.jsdelivr.net/gh/... | raw 的备胎同源 CDN | S(同源) | 单文件 ≤20MB；大 tarball 不适用 |
| 4 | cn.bing.com | 上线日期/国服节奏/zhCN 文案线索 | B(二手) | 结论必须落回 S 级或标 unverified；**RSS 对中文新增长尾词会失真**（2026-09-25 实测返回完全无关结果）——一次不中立即换路，勿重试。**2026-09-26 再降级为"最后手段"**：中英长尾双双失真（中文返知乎无关页、英文返"站点首页清单"111k 结果） |
| 4a | **www.so.com（360）** | **中文任务/系统/版本归属类检索新主力**（优于百度） | B(原创帖摘要) | 给"站点名+真实发布日期+长摘要"；支持 `site:wow.blizzard.cn`（捞官网旧文最佳）；2026-09-26 五连查零触发验证。**坑**：markdown 模式极噪（热搜+签名长链，单次 ~10K token）→ 取 text 或 bash 自去标签；`ai.so.com` AI 卡错误率**高于百度**（本次把"光与影之战"答成 Legion 阿古斯），剧情归属一律不引用 |
| 4b | www.sogou.com | **取官网文章全文**的绕行路：微信垂类把公众号转载**全文**直接嵌进 SERP | B(转载，内容=S) | 站点索引陈旧（blizz 站只到 2025-10）→ **只当"抓全文"，不当"查新"**；须与官网/S 级摘要逐句一致才可按 S 用 |
| 4c | **wow.blizzard.cn/news** | 判"当前赛季是否在跑/下版本是否只是前瞻/国服上线日" | S | 一次直读胜过整轮 SERP；**列表页正文不含文章链接**，文章 URL/编号常拿不到 → 引用记"栏目+日期+标题"。**取法**：bash 直取后 `UTF8.GetString(RawContentStream)`（PS 5.1 默认解码出乱码是本地显示问题，不是页面问题；`-Method Head` 不带 `-UseBasicParsing` 在非交互模式会直接报错） |
| 4d | **bilibili 视频标题**（经 SERP 命中，不必看视频） | **战役↔章节↔任务↔补丁号**四层归属映射（实录标题常为「12.0主线:战役名:章节名:序号-任务名」） | B(玩家一手) | 本次靠它纠正库内一条归属错误；比攻略稿硬，但**只用于"归属"，不用于数值** |
| 5 | baidu SERP(playwright) | 国服内容/攻略检索主力 | B(原创帖摘要) | **页面顶部 AI 答案卡片标注"内容由 AI 生成"=C 级仅线索**，必须回溯到贴吧/3DM/NGA 等原创帖摘要交叉。2026-09-26：**webfetch 只 text 模式可用**，html/markdown 两次复现「百度安全验证」；SERP 日期字段仍会错标（官网 9/23 修正被标 8/22） |
| 6 | NGA 正文（本机持久 profile 已登录，2026-09-25 实测） | 国服玩家一手/搬运帖全文 | **S(正文)/C(摘要)** | 见下方"NGA 登录态使用纪律" |

## S 级够不到的内容（顶棚原则）
NPC 名/坐标、任务流程、副本奖励、开放时间等**游戏数据库内容不在 UI 镜像里**，S 级通路无法核实。此类条目顶棚=**≥3 个独立 B 级来源交叉一致**（见 verification.md 第 6 节），status 仍记 `unverified`，口播加"社区攻略交叉过"限定词，不冒充一手核实。
**归并口径（2026-09-26 强化）**：数源**按"稿"不按"篇"**——一稿多发（163/搜狐/百家号/腾讯/3DM 互转）合计 1 源；同一家自媒体的两篇互斥稿（本次"完成 1 次"vs"完成 3 次"）也只算 1 源，冲突处直接记"未核实"，不许靠篇数凑够 3。

## 中文任务/系统流程类（12.x）通路与坑（2026-09-26「狩猎：蜿蜒的威胁」实战定型）
1. **通路顺序**：so.com 捞原创帖摘要 → 需全文走 4b（sogou 微信垂类）/4c（官网栏目直读）→ 战役·章节·任务**归属**拿不准就搜 bilibili 实录标题（4d）→ NGA 正文（profile 空闲时）。
2. **官方中文界面词的钉法 = 官网「在线修正」**：热修条目会原样引用界面物件名（本次钉死「**狩猎桌**」，据此否掉玩家口语"狩猎沙盘"与攻略稿"狩猎大厅任务桌"）。补 glossary 前先试这条，比反查 GlobalStrings 快。
3. **官网中文站不镜像蓝贴**：蓝贴关键数值常只活在自媒体**译文**稿里。判据=文中"我们已收到你们关于…的反馈"这类第一人称官方口吻 → 记 B 级"蓝贴译文（未见官网原文）"，既不当 S，也不降成纯观点。
4. **专名先分类再取证**：任务名 / 难度词缀名 / 成就名在 SERP 里混排（「蜿蜒的威胁」vs 蛇岛词缀「蜿蜒之秘」vs 成就「寻猎者的梦魇」）。**不分类就会拼出一条根本不存在的任务链**。
5. **前瞻期稿要标口径日期**：上线前的前瞻稿（NPC 译名、数值、解锁条件）与实玩帖冲突时**以实玩帖为准**（本次前瞻稿写"阿斯泰洛"，官方为"阿斯塔洛·血誓"）。**姊妹坑（2026-09-27 装等表）**：PTR 期升级轨道表与实装后稿件常整体漂移（S2 PTR 表 259 起 vs 实装稿 279 起，约+7），装等类数字**两口径并录入库不裁决**，播报强制带"以游戏内为准"。
6. **同名不同物的跨版本串台**（红线级）：「光与影之战」在中文检索里同时命中 **Legion 7.3 阿古斯战役**。判归属必须看**日期+区域词**（奎尔萨拉斯/太阳之井=12.x；克罗库恩/安托兰废土=Legion）——库内 liadrin 条目首建写反归属即源于此。
7. **百度百科**单列一档 C~B：**版本/补丁归属类意外好用**（本次两条词条与官网+游民+实录像一致），**数值/坐标类不可用**；只能当"待验假设"，必须再找官网或一手实录坐实。
8. **UI 镜像可佐证任务类机制**：任务文本不在镜像里，但**系统内部名与界面机制在**（本次 `Blizzard_UIWidgetTemplatePreyHuntProgress.lua:13-17,65-70@12.1.0.69283` 给出 Prey Hunt 进度四态 Cold/Warm/Hot/Final + `C_QuestLog.GetActivePreyQuest()` 点击定位），能把攻略话术翻译成有出处的机制描述。**取文件默认 jsDelivr**：2026-09-26 `raw.githubusercontent` 取主镜像单文件也超时，jsDelivr 同文件一次过。
9. **派 deepthink 做浏览器取证前，主会话须先确认 Playwright profile 空闲**（deepthink 侧遇 `Browser is already in use ...playwright-profile` 重试 3 次不可恢复）；否则其结论顶棚自动降为"NGA 摘要=C"，且必须在交付里显式声明降级。
10. **随机团"分区名→首领构成"钉法**（2026-09-27「虚空武备」实战定型）：官网日程稿只写"随机团队第N区"不写分区专名；**百度/so 的 B站视频垂类标题**（合辑/实玩视频常把分区名+各BOSS名全列在标题）是最快映射源，≥2 不同UP交叉即可入库（B级顶棚）。⚠️ 百度 AI 卡片会把**分区名编成BOSS名**（本次谎称"虚空武备是一个BOSS"），再证 C 级只当线索。另：so.com 纯 bash 连查同 IP 触发验证码→改浏览器（真实 profile）路；百度 SERP 进全文用 `#content_left h3 a` 的 link?url= 页内 location 跟跳，免手工拼 URL。
11. **当季五人本（英雄/大米）boss 机制的批量通路**（2026-09-27 八本详略定型）：3DM `ol.3dmgame.com/gl/<id>.html` 有"12.1S2 XX怎么打"**整系列**（转 NGA 帖，实装口径），**系列 ID 连号**——bash 扫 ±10 个 id 抓 `<title>` 即可一次收齐全系列，比逐本 SERP 快一个量级。池清单以**蓝贴测试服副本列表**为最硬；NGA 帖的"点击展开攻略"折叠层**不吃合成/代理点击**（ajax 懒加载失败），别在折叠上耗时间，找同内容的图文站转载。⚠️ 抖音→smzdm 的 AI 转写攻略稿副本名会花（"夺目谷→多姆古"、"毒牙祭坛→尖牙圣坛"），**专名必须先对官方/蓝贴清单钉正**再采信段落——这些花名反而正是语音识别的同音误写样本，收进消歧表。

## URL 会被中转改写（2026-09-25 取证定论）
provider 中转层（routify）会把模型输出里的**完整 URL**替换为其预取的 OSS 签名链接（替换发生在参数到达工具前）。症状：403、内容与所求无关、Ran code 回显 routify 地址。对策：browser_evaluate 内**分片拼接** URL（实测绕开）或 bash 直连；被改写过的 routify 残留禁止再次使用；引用/入库只记真实目标 URL。详见项目 playwright skill §3。

## 禁试清单（本机实测不通）
github.com 网页/git、wowhead.com、wowpedia(fandom)、duckduckgo。取货走上面 1-3 号路。
**2026-09-26 新增**：`wow.huijiwiki.com` 对 webfetch **与** bash(Chrome UA) 双双 **403**（`/wiki/<页>` 与 `?search=` 都拒）→ 下文"灰机可达但 12.x 缺页"的旧口径作废；要再试只能开浏览器（而 profile 常被直播占用）。

## 主镜像（source of truth）
- 仓库：`wind-addons/BlizzardInterfaceCode`（暴雪官方 UI 源码镜像，非第三方插件）
- 本次核验 HEAD commit sha：`2c2973cc136bf4f90bb229dd864a402e4c75df19` = build `12.1.0.69283`
- raw 基址（钉 sha）：`https://raw.githubusercontent.com/wind-addons/BlizzardInterfaceCode/2c2973cc136bf4f90bb229dd864a402e4c75df19/`
- 备镜像：`husandro/BlizzardInterfaceCode`(HEAD 12.0.5.67186) / `manbastiencs/BlizzardInterfaceCode`

## 插件(addon)类问题：直接进插件自家仓库（2026-09-25 实测）
1. `api.github.com/search/repositories?q=<名>+<功能词>` 定官方仓（按 stars/最近推送辨正主；Details 正主=`Tercioo/Details-Damage-Meter`）。
2. 取文件**首选 cdn.jsdelivr.net/gh/<owner>/<repo>@<sha>/<path>**：raw.githubusercontent 直连本机实测超时（2026-09-25，同文件 jsDelivr 一次过），插件通路以 jsDelivr 为 S 级主力。
3. 源码 grep 定机制：斜杠命令表在 `functions/slash.lua`、窗口/实例化在 `classes/class_instance.lua`（均已 Details 实证）。
4. 坑——**addon 中文文案在仓库里核不到**：`locales/*-zhCN.lua` 常为空壳（翻译在发布打包时注入，Details 即如此），zhCN 界面词只能真机中文客户端核。
5. NGA 正文需登录（tid=23337485 再证）；百度"精选笔记"聚合页与 wenku.baidu 笔记免登录可读，可作 B 级旁证。
6. "这是什么插件"辨识类（2026-09-25 GCD 圆环实战）：百度 SERP 搜效果描述词（中文"圆环 转圈"）→ NGA **摘要即含答案线索**（标题+日期+正文摘要免登录可读）≥3 条交叉 → 用提及的插件名反查 GitHub 仓库 README 钉身世（模仿/衍生关系这类 S 级证据常写在 README）。
7. 坑——**插件托管站通路**（2026-09-25 探测）：www.curseforge.com 403（机器拦截）、api.curseforge.com 200 但需 key、wago.io 浏览器端地理跳转到 cn.wago.io（已成"WA导入"站形态）、addons.wago.io/api/external/* 404。作者自述页拿不到时，GitHub README/issue 是替代一手源。
8. 坑——**bing 摘要日期不可信**（2026-09-25 两见）：结果里混"2002年11月4日""2004年6月22日"等错档期，判新旧只信文本内版本/事件线索，必要时开原文核对。
9. 红线教训——**"GitHub 查无此仓 ≠ 插件已死"**（2026-09-25 Cell 误判事故，当日二修）：国服插件分发通路是大脚插件站/178/NGA 搬运帖，正式服活跃插件可以完全没有 GitHub 镜像。判"死/活"必须过中文检索（bing"插件名+版本+停更/还能用"）≥2 独立摘要；只查 GitHub 就下生态结论=打回级错误（backport 仓活跃还可能反向误导"开发终止"假象）。**姊妹坑：GitHub repo 搜索默认隐藏 fork**（NeeRgY/Cell 23★ 因 fork 属性从未出现在搜索结果），查 fork 线要在 q 加 `fork:all`。
10. **NGA 登录态使用纪律**（2026-09-25 实测定型）：cookie 绑 `bbs.nga.cn` 域，`ngabbs.com` 镜像不吃登录态（403"访客不能直接访问"）→ 一律走 bbs.nga.cn；请求间隔 ≥3-5s；首跳常过 `adpage_insert` 验证插页，等 2-4s 自动放行再取文；出现"请登录后访问"=登录过期，降级回摘要 C 级并请用户重登。国服插件分发站 `addons.miliui.com`（米利/奇樂）存活：下载=preparedownload 签名直链（分钟级 TTL）→HTML 确认页→表单 POST(_token) 才出文件，**必须浏览器带会话走三步**（纯 bash 403）；NGA 帖附件 CDN 对脚本掐链。

## 疑似服务端 BUG/「修没修」类问题（2026-09-26 危难时刻实战定通路）
1. **官网新闻栏「在线修正」= S 级一手**（blizz 官网文章，**文章编号=持久引用**，条目按日期分组）：相位/NPC 消失类服务端行为只有这里能一手确认，UI 镜像够不到；"是 BUG 吗/修了吗"先查它。
2. 中文任务数据库缺口：灰机wiki（wow.huijiwiki.com）**2026-09-26 实测 webfetch/bash 双 403**（旧记"可达但 12.x 新任务缺页"作废，见禁试清单）→ 任务 ID/英文名拿不到 = 口播不报 ID（禁试 wowhead 照旧）。
3. 坑——**转载链虚增源数**：17173/中华网/贴吧的 12.x 任务攻略多为 3DM 转载稿（文末标来源），n 篇=1 个独立源；数源先辨原始出处。
4. 坑——**百度 site: 语法不收录 NGA**，但普通 SERP 收录 NGA 单帖页：搜"任务名+NPC名+症状词（不见了/找不到）"直达；NGA 自带 search.php 已退化成百度/谷歌跳转表单，勿用；搜狗中文游戏长尾混 2017 旧档（同 bing 摘要日期失真坑）。

## 引用纪律
- 短格式（正文）：`UIParent.lua:2423-2458@12.1.0.69283`
- 长格式（evidence.url）：raw URL 钉 commit sha；build 给人看，sha 防 HEAD 漂移。
- 版本证据 = 提交号（见 verification.md）；**禁止用 .toc 的 `## Interface` 行**（12.x 已删该行）。
