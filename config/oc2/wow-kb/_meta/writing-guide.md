---
id: meta.writing-guide
title: WoW 知识库目录编写指南 v1
status: verified
verified: { date: 2026-09-25, by: "deepthink-0925(方案)" }
---

# 编写指南 v1（浓缩自 deepthink 方案稿，2026-09-25）

## 消费模型（三层，知识本体永不常驻上下文）
AGENTS.md 常驻纪律(≤10行) → wow-kb skill(检索协议+兜底话术) → 单条 md(grep 定位、read 单文件)。oc2 回答经 TTS：口播 ≤3 句、无表格代码；知识库是书面层，口播是压缩层，两层分开写。

## 目录切分决策
| 轴 | 处理 | 理由 |
|---|---|---|
| 产品线 retail/classic/forever | 一级目录 | 三线 UI/命令/证据全不同，混线=版本漂移事故根源 |
| 小版本 10/11/12 | frontmatter 区间+内联差异表 | 正式服无并存版本，目录化=翻倍+漂移 |
| 国服/国际服 | 字段+国服差异节 | 差异只有时差与 zhCN 文案两件事 |
| 内置/插件/gamerule | mechanism 字段+addons/ 目录 | 直播最高发混淆点 |
| classic 例外 | 按并存版本目录化(era-60/season/_archive) | 并存版本同表内联必被拿错 |

深度 ≤3 层；目录英文 kebab-case，中文可发现性靠 frontmatter `title/aliases/zhcn_terms`。
副本/任务进入流程放 `retail/raids/`：必含字段=前置(任务线)/进入NPC(全名+坐标)/奖励/可选性/孤证分歧。
universal/ 准入：跨现役全版本核验一致+跨≥2大版本未变；大版本后逐条复核退出。
qa/ 是"视图"不是"源"：问法+口播底稿+权威条目指针，禁止写机制细节（双源必漂移）。检索先 qa 后线索引。

## 条目模板（照抄 auto-accept-invite.md 即可）
必含节：TL;DR(≤3行含方向) / 方向性声明(作用于谁·哪侧生效·不控制什么，三项强制) / 机制细节 / 版本差异 / 常见误区 / 相关条目 / 核验日志(只追加)。
frontmatter 必含：id, title, aliases, applies{line,versions,servers,build_ref,mirror_ahead_of_cn}, mechanism{builtin|addon|gamerule}, status{verified|unverified|outdated}, superseded_by, evidence[{ref,url,note}], verified{date,by}。

## 红线（各对应一类已发生事故）
1. evidence.ref 必须 `file:line@build`，裸行号禁入库（镜像会随 PTR 漂移）。
2. 命令/UI 路径必须带版本区间；"未核验的老说法"与"已证伪"是两种状态不许混写。
3. 双人机制缺"不控制什么"一项 = 打回（方向答反事故）。
4. outdated 条目保留正文+superseded_by，且新条目继承旧 aliases（玩家用旧词提问）。
5. 版本证据=提交号；禁引 .toc（12.x 已删 Interface 行）；URL 钉 sha。
6. gamerule 条目客户端证明不了服务端 → 强制 unverified + 证据边界节。
7. zhcn 文案无出处不填；口播不硬报未核实按钮文字。
8. 篇幅：条目≤80行、qa≤30、INDEX≤150、_meta 各≤200。
9. S 级够不到的内容（NPC/坐标/任务流程/奖励/开放时间）→ 按 verification.md 第 6 节多源交叉（≥3 独立源、关键值逐项一致、孤证记录），status 一律 unverified，口播带"社区攻略交叉过"限定词。
10. URL 卫生：禁止从历史工具输出整段复制 URL（存在 routify 代理残留 403）；检索一次不中立即换通路（bing RSS 中文长尾失真→百度；百度顶部 AI 卡片=C 级线索不作源）。

## 更新机制
触发式重验矩阵在 `_meta/freshness.md`；条目 90 天自动降 unverified。
oc2 只读；新结论/错答由离线侧（人/deepthink）回填源目录再部署，**永改源不改部署区**（tools/ 被 gitignore）。
直播兜底四话术见 SKILL.md；兜底≠拒答：先给已核实部分再划边界。

## 勘误（行数纪律）
预算：AGENTS 追加≤10 / SKILL≤60 / INDEX≤150 / 条目≤80 / qa≤30 / _meta 各≤200。
实际（2026-09-25 首批建库+小幅修订后总行数实测，含空行）：
- sources 33 / verification 17 / freshness 16 / glossary 19 / writing-guide(本文件) 29
- auto-accept-invite 41 / party-invite-dialog 32 / quick-join 37 / disable-quick-join 27 / raids.spire-entry 26
- addons/_catalog 21 / qa(防拉人) 13 / qa(尖塔) 13 / INDEX 19 / SKILL 17 / AGENTS 追加 5
全部在预算内，无需解释项。
