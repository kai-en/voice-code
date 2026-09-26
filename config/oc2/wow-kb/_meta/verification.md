---
id: meta.verification
title: 直播快速验证手册
status: verified
verified: { date: 2026-09-25, by: "deepthink-0925" }
---

# 快速验证手册（oc2 直播侧只用 1、2 的缓存路径；全树排查交离线 deepthink）

## 1. build 确认（禁止用 .toc）
12.x 的 .toc 已删除 `## Interface` 行（改用 AllowLoad/AllowLoadGameType）。
```
GET https://api.github.com/repos/wind-addons/BlizzardInterfaceCode/commits?sha=main&per_page=1
```
提交标题即 build（如 `12.1.0.69283`），同时记 sha，后续 raw 拉取一律用该 sha。
对照 `_meta/freshness.md`：镜像超前国服 → 相关条目标记 `mirror_ahead_of_cn`，行号仅供国际服镜像版参考。

## 2. 查 CVar 消费点
1. 先查本库缓存：既有条目/glossary 已有 `CVar → file:line@build` 且 build 匹配 → 直接复用。
2. 无缓存 → `GET /git/trees/<sha>?recursive=1` 拿全树清单（一次调用），按目录筛候选：设置页=`Blizzard_SettingsDefinitions_Frame/`，全局弹窗/行为=`Blizzard_UIParent/Mainline/UIParent.lua`、`Blizzard_StaticPopup_Game/GameDialogDefs.lua`。
3. raw 拉回后 grep CVar 名。
4. 穷尽性纪律：说"唯一消费点"前必须覆盖全树候选；未穷尽则 note 写"核验范围=已列目录"。

## 3. zhCN 界面文案检索
**第 0 步（2026-09-26 新增，最快）**：官网「在线修正」页搜该词——热修条目会原样引用界面物件名（本次由此定「狩猎桌」并否掉玩家口语"狩猎沙盘"）。命中即 S 级。
GlobalStrings 编译进引擎，UI 镜像搜不到。路线：enUS 机制名 → **so.com 中文搜"功能名+设置/选项"**（bing 2026-09-26 起降为最后手段：中英长尾均失真）→ NGA 摘要/官网新闻佐证 → 回填 `_meta/glossary.md`（行：en|cn|界面位置|来源|核验日期；无来源标"待核"）。**bing 已降级为最后手段（见 sources.md 优先级表）**，中文长尾优先 so.com。
**直播纪律**：glossary 无已核实 zhCN 的，口播用位置+功能描述（"设置里社交那一页的那个开关"），不硬报按钮文案。

## 4. 内置 vs 插件判别决策树
1. grep `addons/_catalog.md` 行为关键词 → 命中 = 插件功能，回答显式说"这是插件行为"（看该条 native_equivalent）。
2. 未命中 → 按第 2 节搜 UI 镜像 → 找到 = 内置，引用 file:line@build。
3. 两边没有 → 兜底话术；禁止无证据断言"游戏有/没有这功能"。
4. 疑似服务端 gamerule → 记 `retail/gamerules/`，status=unverified 并注明"客户端镜像证明不了服务端规则"。

## 5. 方向性自检（双人机制回答前必做）
邀请/入队/交易/转团类问题，回答前默查条目"方向性声明"三问：作用于谁？哪一侧生效？不控制什么？——本次事故原型就是把"管别人进我的队"的开关答成"防我被拉走"。

## 6. 多源交叉流程（S 级够不到的内容：NPC/坐标/任务/奖励/开放时间）
1. **so.com 优先、baidu 备用**（playwright 或 bash 直取；2026-09-26 实测 so.com 给站点名+真实日期+长摘要且零验证），搜"内容名+功能词+NPC/怎么进"，收集**原创帖**摘要（贴吧/3DM/NGA/自媒体），跳过顶部 AI 卡片（so.com 的 ai.so.com 卡错误率更高，只当线索）。
2. 要求 ≥3 个独立来源，且**关键值逐项一致**（NPC 全名、坐标到小数位、任务名）；记录一致点。**按"稿"归并源**：一稿多发（163/搜狐/腾讯/百家号/3DM 互转）只算 1 源。
3. 分歧源单独记录（例：2026-09-25 虚影尖塔条目中一篇写"风暴神殿"，判孤证笔误，多数源为"虚影风暴"）。**先判专名类别**（任务名/词缀名/成就名）再比对，否则会拼出不存在的任务链。
4. 每条引用记"来源名+发布日期+检索日期"（百度 redirect 链易失效，不做持久引用）。
5. 条目 status=`unverified`；口播用"社区攻略交叉过"限定词（sources.md 顶棚原则）。
6. **战役/区域↔补丁归属类**：加查 bilibili 实录标题与官网上线公告；注意同名不同物（「光与影之战」在 Legion 也有）——见 sources.md 中文任务类第 6 条。
