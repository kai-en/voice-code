---
id: addons.cell-click-bindings
title: Cell 自家「点击施法」页改键（选中/菜单→修饰键组合）与 12.x 安全动作闸的 proxy 绕过
aliases: [Cell点击施法, Cell改键, Cell选中目标, Cell右键菜单, Cell不支持, proxy, EnsureClickProxy, 米利点击施法]
applies:
  line: retail
  versions: "12.1.x（Interface 120007/120100/120105 实测线；闸随 12.x 客户端存在）"
  servers: [cn]
  build_ref: "-"
mechanism: addon
status: verified
superseded_by: null
evidence:
  - ref: "本地 G:\World of Warcraft\_retail_\Interface\AddOns\Cell(r304_MiliUI) Modules/ClickCastings/ClickCastings.lua:76-174,649-674@git-blob d4a141d19521ce7bef3ecd6bd594f2e214ae2909"
    note: "S(主会话直测 2026-09-26)：安装版含 EnsureClickProxy/IsGatedAction/RouteProxyAction 全套（proxy 命中 45 处）；blob 与 GitHub 三线全不同=米利自有衍生；toc=120007/120100/120105"
  - ref: "NeeRgY/Cell@commit d18e435：Core.lua:524-570 + Modules/ClickCastings/ClickCastings.lua:65-101,343-364,834-975,955-974@git-blob c869a78c"
    note: "S(主会话 contents API 复核 sha)：默认 {type1=target},{type2=togglemenu} 是可编辑绑定数据非硬编码；闸注释逐字引用暴雪 expectBinding 守卫"
  - ref: "enderneko/Cell@master Modules/ClickCastings/ClickCastings.lua@git-blob 68f8769a(66589B)"
    note: "S(主会话复核存在)：原始线 blob 显著小于 fork 线（66.6KB vs 83.8KB）——proxy/gate 代码不在原始线，12.x 修饰键改键可被闸卡死"
  - ref: "NeeRgY/Cell@63469f0:RaidFrames/UnitButton.lua:4440-4441；@d18e435:Widgets/Widgets.lua:3189-3271"
    note: "S(deepthink 落盘 grep，主会话未逐行复核)：点击动作先过 IsGatedAction；键位捕获支持 Alt/Ctrl/Shift+左右中键/Button4-31/滚轮/键盘"
  - ref: "wind-addons SecureTemplates.lua:871-875@12.1.0.69283 + 本地 r304 文件:141-164 注释"
    note: "闸=暴雪原生 expectBinding 守卫（target/menu 需该组合在点击绑定档有交互绑定），非 Cell bug；局内实机未测"
  - ref: "addons.miliui.com/wow/cell(2026-09-26 主会话直连 200)"
    note: "米利线现值仍 r304（页面列 r300-r304）"
verified: { date: 2026-09-26, by: "deepthink-0926×2 + 主会话本地/GitHub blob 直测（并打假 deepthink 两处虚构）" }
---

## TL;DR（口播底稿）
Cell 支持，而且从来支持：入口在 **Cell 自己的选项（/cell options）→"点击施法"页**，不在暴雪按键绑定设置里。默认"目标/菜单"两条就是可编辑绑定行——把选中目标改绑 Shift+左键、菜单改绑 Shift+右键，再新建行把裸左/右键绑治疗术。一个前提：12.x 客户端对修饰键 target/menu 有道安全闸，**要装带修复的版本线**（米利 r304 或 GitHub NeeRgY 线都有；原作者停更的原始线没有）。

## 方向性声明
- 作用于谁：自己客户端 Cell 框体的点击行为。
- 在哪一侧生效：CellDB SavedVariables 绑定表 → 登录时 SetAttribute 到每个 SecureUnitButton 框体。
- 不控制什么：与暴雪原生「点击施法绑定」面板**互不相通**（Cell 不参与原生点击帧表）——原生面板改绑对 Cell 无效，反之亦然；队友无感。

## 机制细节
- 绑定数据驱动：`{"type1","target"}/{"type2","togglemenu"}` 只是 DB 默认值（Core.lua:524-570），改键=改行键位格（"点击按键以绑定"），无硬编码 OnClick。
- 常规动作：目标/焦点/协助/菜单/**菜单（非战斗中）**（后者=战斗时自动摘菜单属性，防误触）；另有"总是选中目标"（禁用/左键法术/所有法术，施法宏自动前置 /tar [@mouseover]）。
- zhCN 界面词本机 r304 实钉（插件自带 locale，S 级非 GlobalStrings）：页签"**点击施法**"（zhCN.lua:213）、"**总是选中目标**"(:251)、"鼠标施法提示"(:214)。
- 12.x 闸与绕过：暴雪把 target/menu 安全动作关进"点击绑定白名单"（原生守卫见 retail.ui.click-bind-target-menu），插件属性够不到→fork 线给每个框体挂 SecureActionButton 子 proxy（无闸）路由（IsGatedAction 判定：裸左键 target 豁免，修饰键 target 与一切 menu 走 proxy）。
- 版本线 proxy 覆盖：米利 r304（本机装，含"fix from MiliUI"自有补丁）✅ / NeeRgY r277.9.8.x ✅ / krysiolol ✅（blob 均不同，各有衍生）/ enderneko 原始 ❌。
- NeeRgY 线删掉整条 type2 行会被兜底恢复成裸右键菜单（:955-974）——腾裸右键须**改绑**不能删行。

## 版本差异
| Cell 线 | 12.x 改键可用 | 通路 |
|---|---|---|
| 米利 r301-r304 | ✅ 含 proxy+自有修复 | miliui 站/NGA tid=47379276 |
| NeeRgY r277.9.8.x（活跃） | ✅ proxy 主力线 | GitHub fork |
| enderneko 原版(≤r276) | ❌ 无 proxy，修饰键 target/menu 可被闸 | GitHub 归档态 |

## 常见误区
- 去暴雪"选项→按键绑定"里找 Cell 设置 → 找不到属正常，Cell 入口在自己选项页。
- 用停更原版 Cell 改 Shift+菜单失灵 → 不是改法错，是缺 proxy，换米利/NeeRgY 线。
- 删行腾裸右键 → NeeRgY 线会被恢复，要改绑。
- 与"增益缺失指示器分批修复"混谈：显示层（光环 API）与点击层（本条）是两回事，点击层现行版本完整。

## 相关条目
retail.ui.click-bind-target-menu（原生侧同款能力）· addons.cell-raidframes（版本获取通路）· qa.retail-raidframe-click-rebind

## 核验日志
- 2026-09-26：deepthink 源码调研后主会话直测复核——安装版=米利 r304（G 盘，非 deepthink 所称 NeeRgY 4415），ClickCastings.lua 实含 proxy 全套（纠正 deepthink 首轮"米利无 proxy"推断：其读了旧缓存页）；三 GitHub 线 blob sha 全部 API 钉死。**纪律教训入 sources.md 第 12 条**：deepthink 报的"本地实测/新镜像/新版本号"未经主会话复核不得入库。局内实机（Shift+右键真开菜单）未测，口播带"以你客户端实测为准"。
