---
id: retail.ui.raidframe-buff-missing
title: 团队框架长效buff显示与"缺失才提醒"（12.x 内置能力边界）
aliases: [坚韧显示, 团队buff监控, 缺buff提醒, 长时buff, 光环显示, buff列表]
applies:
  line: retail
  versions: ">=12.0"
  servers: [cn, intl]
  build_ref: "12.1.0.69283"
mechanism: builtin
status: verified
superseded_by: null
evidence:
  - ref: "Blizzard_UnitFrame/Mainline/CompactUnitFrameOptions.lua:14@12.1.0.69283"
    url: "https://cdn.jsdelivr.net/gh/wind-addons/BlizzardInterfaceCode@2c2973cc/Interface/AddOns/Blizzard_UnitFrame/Mainline/CompactUnitFrameOptions.lua"
    note: "内置团队框架光环=displayBuffs 一个布尔开关（全显/全隐），选项表无缺失指示字段"
  - ref: "Blizzard_UnitFrame/Shared/CompactUnitFrame.lua:1731,2378@12.1.0.69283"
    note: "唯一消费点：displayBuffs→ignore-buffs 属性；全文 grep 无 important/essential/missing 逻辑（核验范围=CUF/CRF/RaidFrame/CUFProfiles 所列文件）"
  - ref: "Blizzard_CooldownViewer/GroupBuffFilter.lua@12.1.0.69283"
    note: "内置另有'团队增益横幅提醒'（C_CooldownViewer.GetGroupBuffItems + VisualAlerts）——有人补团buff时提示，正向提醒而非缺失指示"
verified: { date: 2026-09-25, by: "v1-session-0925(UI镜像jsDelivr直读)" }
---

## TL;DR（口播底稿）
默认团队框架的buff图标是"一开关全有或全无"，没有"缺了才亮"的内置设置。想要缺失提醒，用 Cell 团队框架的"增益缺失"指示器——原作者停更了，现在用国服社区修复版（米利版），且 12.1 光环接口大改后指示器功能还在分批修复中，缺buff类能否即用需以实测为准。

## 方向性声明
- 作用于谁：本机界面显示层。
- 在哪一侧生效：客户端本地。
- 不控制什么：不改变 buff 本身；内置 CooldownViewer 的团增益横幅只报"有人加了"，不报"谁缺了"。

## 机制细节
- displayBuffs 在"选项→游戏→紧凑团队框架（自定 UI profile）"侧配置；关掉后 buff 全隐（含缺失提醒需求也无法在框架上表达）。
- 内置无"缺失才亮"逻辑（核验范围=CUF/CRF/RaidFrame/CUFProfiles 所列文件）。**要该效果用 Cell**：指示器"增益缺失"，12.1 现况与获取通路见 addons.cell-raidframes。
- Details_RaidCheck 只查合剂/食物/符文（含嗜血数据，无职业长效 buff 表）——不承担本需求。

## 常见误区
- 把 CooldownViewer 的团 buff 横幅当成"缺失提醒" → 它是"补上了才闪"，方向相反。
- 引用怀旧服 buff 监控插件推荐给正式服玩家 → 产品线不同。

## 相关条目
addons.cell-raidframes

## 核验日志
- 2026-09-25 @12.1.0.69283：三文件 jsDelivr 直读实锤开关唯一性与缺失逻辑不存在；生态检索 GitHub search×2、bing×1。
- 2026-09-25 二修：初版"正式服无插件可用/Cell 死亡"结论**错误**（只查了 GitHub 即下判），bing 中文交叉 4 源推翻——Cell 官方精简版+社区 r291 存活。教训已入 sources.md 第 9 条。
