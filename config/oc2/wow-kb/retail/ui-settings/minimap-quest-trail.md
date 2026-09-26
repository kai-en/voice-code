---
id: retail.ui.minimap-quest-trail
title: 小地图上的任务轨迹/标记如何不再显示（12.x 内置机制与限制）
aliases: [任务轨迹, 金色轨迹, 小地图问号, 取消追踪, untrack, 任务标记]
applies:
  line: retail
  versions: ">=12.0"
  servers: [cn, intl]
  build_ref: "12.1.0.69283"
  mirror_ahead_of_cn: true
mechanism: builtin
status: verified
superseded_by: null
evidence:
  - ref: "Blizzard_Minimap/Mainline/Minimap.lua:36-46@12.1.0.69283"
    url: "https://cdn.jsdelivr.net/gh/wind-addons/BlizzardInterfaceCode@2c2973cc/Interface/AddOns/Blizzard_Minimap/Mainline/Minimap.lua"
    note: "QuestPOIs 在 ALWAYS_ON_FILTERS——小地图追踪菜单没有'任务'开关项（TrivialQuests 在 OPTIONAL 可关灰色任务）"
  - ref: "Blizzard_SharedMapDataProviders/SuperTrackWaypointDataProvider.lua:27-37@12.1.0.69283"
    note: "轨迹=跟随'当前追踪任务'(SuperTrack)；无追踪任务时无轨迹无目标钉"
  - ref: "SuperTrackManagerDocumentation.lua:133-146@12.1.0.69283"
    note: "SetSuperTrackedQuestID 带 SecretArguments=AllowedWhenUntainted → 第三方插件仅在非战斗/副本环境可能代点取消，受限场合失效"
verified: { date: 2026-09-25, by: "v1-session-0925(UI镜像三文件S+NGA旁证)" }
---

## TL;DR（口播底稿）
老版本"右键小地图→追踪→勾掉任务轨迹"那一栏在 12.x 没有了——任务标记是内置常开的。现在唯一常规办法就是在任务日志里右键任务点"取消追踪"，金色轨迹和任务标记立刻消失；但接新任务会自动重新追踪，这是引擎默认。要是看到小地图上一串红色箭头跟随移动路径，那不是任务，多半是 FarmHud 这类采集插件，去它设置里关。

## 方向性声明
- 作用于谁：本机小地图/地图显示层。
- 在哪一侧生效：客户端本地；追踪状态是本人界面概念，队友看不见。
- 不控制什么：不影响任务数据与完成判定；"取消追踪"≠放弃任务。

## 机制细节
- 常开列表（UI 硬编码）：任务标记、交通枢纽、旅店老板、物品升级、战场大师、马厩；可选列表含"灰色任务(TrivialQuests)"与 banker/mailbox 等。
- 自动重追踪：接受任务默认把该任务设为当前追踪（SuperTrack），因此"取消"是一次性的。
- 插件代取消（QUEST_ACCEPTED→清空追踪）在非战斗户外可用，副本/战斗中因保密参数政策失效——想要"永远不追踪"要么忍受手点，要么插件+场景限制自测。
- 顺手区分：屏幕右侧文字任务列表是另一个开关（界面→名称/战斗提示类），与本条无关。

## 常见误区
- 把 FarmHud 路径红箭头当成暴雪任务轨迹（NGA tid=43398700 案例，装/查插件列表定案）。
- 在"追踪"菜单里找不到"任务"就以为插件干的——内置常开，本来就没有那一项。

## 相关条目
retail.ui.raidframe-buff-missing · addons._catalog

## 核验日志
- 2026-09-25 @12.1.0.69283：三文件 jsDelivr/api 直读；国服旁证 NGA tid=43398700（FarmHud 定案帖）、tid=42756773 摘要（"都取消追踪试试"）。mirror_ahead_of_cn 限定：12.1 行号，国服 12.0.x 客户端菜单文案可能略差。
