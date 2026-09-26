---
id: addons.cell-raidframes
title: Cell 团队框架在 12.x 的存活现状（停更→米利修复版）与增益缺失指示器
aliases: [Cell, 团队框架, 指示器, 增益缺失, rebuff, 框体, miliui, 米利]
applies:
  line: retail
  versions: "12.1+（12.1 光环 API 大改是分水岭；怀旧服不兼容）"
  servers: [cn]
  build_ref: "-"
mechanism: addon
status: verified
superseded_by: null
evidence:
  - ref: "NGA tid=47379276 #0(2026-08-15,改08-18)"
    note: "S：原作者 enderneko 停更、12.1 API 改动原版报错；米利重写光环代码适配，仅正式服，完整简中；下载=miliui 原站+帖附件"
  - ref: "NGA tid=47379276 #8/#13/#18(米利本人回复)"
    note: "S：'12.1光环大改，确实很多指示器功能不能用了'；r289 修护盾、r290/291/292 滚动更新中"
  - ref: "addons.miliui.com/wow/cell(2026-09-25 实测200)"
    note: "S：国服插件分发站存活；bug 反馈走该站留言+BugGrabber"
  - ref: "github.com/NeeRgY/Cell(23★,fork,推2026-09-21)+parent krysiolol/Cell"
    note: "S：GitHub 另有 fork 线（r277.9.8.x，含 forever 分支 BETA），史诗本报错反馈(NGA #6)"
verified: { date: 2026-09-25, by: "v1-session-0925(NGA登录态S+miliui+GitHub fork)" }
---

## TL;DR（口播底稿）
Cell 原作者停更了，但国服有社区接手：现在用"米利修复版"（NGA 搬运帖 tid 四七三七八二七六，或米利插件站直接下），完整支持简中、只兼容正式服 12.1。"队友缺 buff 才亮图标"就是它的增益缺失指示器——不过 12.1 光环接口大改后指示器功能在分批修复中，副本减益一类还是空的，装前把 WTF 里旧 Cell 配置删干净重调。

## 方向性声明
- 作用于谁：本机团队框体显示层。
- 在哪一侧生效：客户端本地读团队光环。
- 不控制什么：不替玩家补 buff；队友看不到你的指示器配置；点击施法行为另论。

## 机制细节
- 指示器系统（icon/bar/rect/text）支持"增益缺失"条件——目标缺指定法术时显示，否则隐藏（=玩家要的"没有才显示"）。
- 版本分叉：米利修复线（r289→**r304**，2026-09-22 现值，miliui 站 2.00MB/200 次下载）vs NeeRgY/krysiolol GitHub fork 线（r277.9.8.x，团本报错反馈）；两者配置不通用。
- 12.1 起光环 API 大改：所有依赖旧光环接口的框体插件都要重写适配（不止 Cell），旧配置（WTF）不清会触发"指示器全空"假象。

## 常见误区
- 用大脚自带旧 Cell → 12.0 前夕即废（报错）。
- 装修复版不删旧 WTF 配置 → 指示器空白以为坏了。
- 把 GitHub 搜不到当 Cell 死亡 → 主分发在 miliui/NGA 搬运；且 GitHub 搜索默认隐藏 fork（要 fork:all 才看得到 NeeRgY 线）。
- 把怀旧 backport（3.3.5a）装正式服 → 产品线错配。

## 相关条目
retail.ui.raidframe-buff-missing（内置只有全显/全隐的 S 级事实）· addons._catalog

## 核验日志
- 2026-09-25 初版：bing 摘要×4（unverified 顶棚）。
- 2026-09-25 二修（NGA 登录态实测可用后升 S）：tid=47379276 主楼+米利回复逐层核读；miliui 站 200；GitHub fork 链核出。r292 时点"增益缺失"指示器是否已修好未见明说——**给玩家推荐前留一句"缺buff指示器可能要等后续更新"**，已在口播体现。
- 2026-09-26 三修：miliui 回访最新=r304（Interface 120007/120100/120105 适配 12.1.x）；取包流程实测=preparedownload 签名页(分钟级 TTL)→确认页 form POST(_token)→浏览器下载，纯 bash 403；NGA 帖附件 CDN 掐链不通。本机已装 r304（旧 r274 备份于 D 盘 temp，WTF 无 Cell 配置残留）。
