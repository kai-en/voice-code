---
id: addons.gcd-ring-display
title: 屏幕中间"转一圈就消失"的 GCD 小圆环是什么插件
aliases: [GCD圆环, gcd环, 公共冷却圈, 中间转圈, GCD Circle, Ultimate Mouse Cursor, GCD Cursor Plus, CursorRing]
applies:
  line: retail
  versions: ">=11.0（社区检索均 2026 年国服语境）"
  servers: [cn, intl]
  build_ref: "-"
mechanism: addon
status: unverified
superseded_by: null
evidence:
  - ref: "RedAntisocial/CursorRing README@3e98c1af(2026-09)"
    url: "https://cdn.jsdelivr.net/gh/RedAntisocial/CursorRing@main/README.md"
    note: "S级：'Ultimate Mouse Cursor' 是 WeakAura（wago.io/ZbjlsgMkp），CursorRing 是模仿它的独立插件（鼠标跟随环+施法进度）"
  - ref: "NGA tid检索摘要×3(2026-02-22/03-03/03-16)"
    note: "B级交叉：'GCD Cursor Plus 2026.3.30 更新后可实现'；'固定屏幕中间不跟随鼠标'是明确需求分支；'外环/主环/内环任设 GCD'系 cursor 类设置"
  - ref: "360问答老题(年代不明)"
    note: "屏幕中间显示公共CD转圈=历史高频需求，旧解法主流是 WA 自制字符串"
verified: { date: 2026-09-25, by: "v1-session-0925(GitHub S + NGA摘要B×3)" }
---

## TL;DR（口播底稿）
那不是游戏内置、也不是 Details 的效果——现在是**专用 GCD 圆环小插件**做的，比如 GCD Cursor Plus、CursorRing 这类（早两年流行的 Ultimate Mouse Cursor 本体是条 WeakAura，但 **WA 已停止支持 12.0**，现役主播基本转独立插件了）。跟鼠标转和固定屏幕中间是同一类插件的两种位置模式。想确认装没装，插件列表搜 cursor 或 gcd 即可。

## 方向性声明
- 作用于谁：只影响本机画面显示，无任何游戏机制作用。
- 在哪一侧生效：客户端本地；GCD 数据来自引擎公开的 spell queue 信息，各插件读同一个。
- 不控制什么：不改变 GCD 实际长度；也不代表主播"有特殊客户端"。

## 机制细节
- 两类形态：跟随鼠标转圈（UMC 血统的 cursor 类插件默认）vs 固定位置小环（插件位置模式；WA 时代靠自制字符串，已成历史方案）。
- WA 退场时间线见 `_meta/freshness.md`"生态事件"节：CursorRing 仓库（2026-09 活跃）自述动机就是"WA's are going away"。

## 常见误区
- 认成暴雪内置战斗日志功能 → 内置无此圆环形态（未深核，不下死结论）。
- 以为是 Details 的组件 → Details 的 GCD 相关只在窗口微型显示条，不是屏幕中间的独立环（本条按社区检索所得，未逐行核 Details 源码 GCD 模块）。

## 相关条目
addons._catalog

## 核验日志
- 2026-09-25：GitHub 仓库 README 定 UMC=WA 身世（S）；NGA 摘要三条+360问答交叉定"中间环"答案域（B，status 顶棚 unverified）。GCD Cursor Plus 本体自述页未获取（curseforge web 403、wago 地理跳转），待真机或作者页补核。
- 2026-09-25 二修：**WA 现役表述降级为历史**（生态事实：WA 停止支持 12.0，见 freshness 生态事件节），证据=bing 新闻摘要时间线 5 条 + CursorRing README + 用户告知，status 仍 unverified。
