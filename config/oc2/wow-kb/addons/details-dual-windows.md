---
id: addons.details-dual-windows
title: Details 插件同时显示伤害+治疗榜（双窗口）
aliases: [Details, details双窗口, 同时显示伤害治疗, 伤害治疗两个窗口, 战斗统计双面板, 统计插件多窗口]
applies:
  line: retail
  versions: "插件自身跨版本（仓库同名多 .toc）；证据=插件 commit 而非游戏 build"
  servers: [intl, cn]
  build_ref: "-"
mechanism: addon
status: verified
superseded_by: null
evidence:
  - ref: "functions/slash.lua:50-51@1fc0b3ea"
    url: "https://cdn.jsdelivr.net/gh/Tercioo/Details-Damage-Meter@1fc0b3ea97fd7609b7784eb1967dadf4deb69548/"
    note: "/details new → Details:CriarInstancia(nil,true)；仓库=官方 Tercioo/Details-Damage-Meter（225★，2026-09-25 HEAD）"
  - ref: "classes/class_instance.lua:1870-1900@1fc0b3ea"
    note: "每个窗口独立实例（tabela_instancias 逐个建），窗口总数上限=Details.instances_amount（选项可调）"
  - ref: "frames/window_main.lua:1030-1042@1fc0b3ea"
    note: "窗口任意处（含标题条）右键 → switch:ShowMe / ShowAllSwitch 显示选择面板"
  - ref: "frames/window_switch.lua:506,865@1fc0b3ea"
    note: "面板内 Config(atributo, sub_atributo) 逐窗口切换数据源（伤害/治疗/资源/杂项）"
verified: { date: 2026-09-25, by: "v1-session-0925(源码一手+jsDelivr通路)" }
---

## TL;DR（口播底稿）
Details 本来就是"每个窗口各挂一种数据"的设计：先输 **/details new** 开第二个窗口，再**右键点这个新窗口**（标题条或面板任意处）弹出显示选择，选治疗——原窗口保持伤害，两张榜同屏同时显示。数据只采一份，第二窗口不是重复统计。

## 方向性声明
- 作用于谁：只作用于**本机的画面显示**（主播自己的客户端）。
- 在哪一侧生效：客户端本地；所有 Details 窗口读同一份采集数据，只是各窗口 feed 不同。
- 不控制什么：不改变统计/采集逻辑，也不会让队友看到你的第二个窗口；原生界面没有等价双榜同屏（未核原生细节，不展开）。

## 机制细节
- 窗口=独立 instance，各持自己的 `atributo/sub_atributo`（数据源）字段；`/details new`、小地图图标菜单"新建窗口"、右键面板三条创建路径源码同源。
- 想同步缩放/布局：窗口可成组（API 有 GetInstanceGroup），逐个拖即可。
- 中文按钮文案仓库内不可核（见常见误区第 3 条），口播用"右键窗口，弹出来的那个显示选择面板"描述。

## 版本差异
| 区间 | 状态 |
|---|---|
| 游戏 10.x~12.x | 同一份代码跨线（Classic/Cata/Mist/Wrath 等 .toc 并存）；证据为 2026-09-25 的 main HEAD |
| 新版窗口(window2) | `atributo` 字段以"向后兼容"名义保留（frames/window2/frames.lua:62-129 注释），操作路径不变 |

## 常见误区
- 以为要再装一个治疗统计插件 → 同一个 Details 开两窗各选各的即可。
- 把"切模式"按钮当成开榜中榜 → 那是把**当前窗口**整个换数据源，换完伤害榜就没了；要同屏必须第二窗口。
- 在 GitHub 仓库里搜中文按钮名找不到 → 插件仓库的 locales/zhCN 常是空壳（翻译在发布打包时注入），中文文案只能真机核对。

## 相关条目
addons._catalog

## 核验日志
- 2026-09-25 @插件commit 1fc0b3ea：四处源码 jsDelivr 拉取 grep 实锤（命令/实例化/右键面板/逐窗feed）；百度精选笔记（wenku 文库，免登录可读）与 GitHub issue #349"2 Windows"、NGA tid=23337485（已解决帖，正文需登录仅题证）三处旁证多窗口为该插件常规用法。zhCN 界面词待真机。
