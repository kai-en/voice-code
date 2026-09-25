---
id: retail.gamerules.disable-quick-join
title: DisableQuickJoin 游戏规则
aliases: [禁用快速加入, gamerule, 测试规则]
applies:
  line: retail
  versions: ">=12.0"
  servers: [intl, cn]
  build_ref: "12.1.0.69283"
mechanism: gamerule
status: unverified
evidence:
  - ref: "Blizzard_FriendsFrame/Mainline/FriendsFrame.lua:278@12.1.0.69283"
    url: "https://raw.githubusercontent.com/wind-addons/BlizzardInterfaceCode/2c2973cc136bf4f90bb229dd864a402e4c75df19/Interface/AddOns/Blizzard_FriendsFrame/Mainline/FriendsFrame.lua"
    note: "if C_GameRules.IsGameRuleActive(Enum.GameRule.DisableQuickJoin) then showQuickJoin=false"
verified: { date: 2026-09-25, by: "deepthink-0925" }
---

## TL;DR
客户端确实存在一个"禁用快速加入"的服务端规则开关（激活时好友列表的快速加入页签隐藏）。但哪些服务器/时段启用属于服务端配置，客户端源码证明不了——哪些服用它，未核实。

## 证据边界
- 客户端镜像只能证明：存在 `Enum.GameRule.DisableQuickJoin`，UI 据此隐藏入口（FriendsFrame.lua:257-285）。
- 客户端镜像**不能证明**：任何具体服务器（含国服）当前是否激活该规则。gamerule 由服务端下发（`C_GameRules` 系列 API 读服务器状态）。
- 因此本条 `status: unverified`；直播引用必须加"这个规则由服务器端控制，我没法核实当前国服状态"。

## 相关条目
retail.group.quick-join

## 核验日志
- 2026-09-25 @12.1.0.69283：确认客户端消费点；服务端侧留待 NGA/实测补证。
