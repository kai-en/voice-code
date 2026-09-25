---
id: retail.social.auto-accept-invite
title: 自动接受组队邀请（12.x 真实现状）
aliases: [自动接邀请, autoaccept, 被拉进组, 自动进组, 拒绝邀请, 不经确认进队]
applies:
  line: retail
  versions: ">=12.0"
  servers: [intl, cn]
  build_ref: "12.1.0.69283"
  mirror_ahead_of_cn: true
mechanism: builtin
status: verified
superseded_by: null
evidence:
  - ref: "Blizzard_SettingsDefinitions_Frame/Social.lua:140-142@12.1.0.69283"
    url: "https://raw.githubusercontent.com/wind-addons/BlizzardInterfaceCode/2c2973cc136bf4f90bb229dd864a402e4c75df19/Interface/AddOns/Blizzard_SettingsDefinitions_Frame/Social.lua"
    note: "设置→社交 唯一 autoAccept 项是 autoAcceptQuickJoinRequests（条件注册：CVar 存在才显示）"
  - ref: "Blizzard_UIParent/Mainline/UIParent.lua:2423-2458@12.1.0.69283"
    note: "该 CVar 唯一消费点：AllowAutoAcceptInviteConfirmation→跳过 GROUP_INVITE_CONFIRMATION（别人进我的队，队长侧）"
  - ref: "Blizzard_StaticPopup_Game/GameDialogDefs.lua:1286-1310@12.1.0.69283"
    note: "PARTY_INVITE 必须手动点接受；见 retail.social.party-invite-dialog"
verified: { date: 2026-09-25, by: "deepthink-0925" }
---

## TL;DR（口播底稿）
12.x 正式服**没有**"自动接受组队邀请"的官方开关——普通邀请弹窗只能手动点，不点会自动拒绝。设置→社交里那个"自动接受"只管【别人快速加入我的队】，管不了【我被拉进别人的队】。若你"零操作进团"，先查插件。

## 方向性声明
- 作用于谁：`autoAcceptQuickJoinRequests` → 作用于**我作为队长/被加入方**。
- 在哪一侧生效：别人（战网好友/游戏好友/公会/社区成员）快速加入**我的**队时，跳过我这侧的 GROUP_INVITE_CONFIRMATION 确认弹窗（UIParent:2449-2455）。任务队伍(Quest Session)永不自动放行（UIParent:2460 注释原文）。
- 不控制什么：**不控制"我被人邀请进别人的队"**（那是 PARTY_INVITE，纯手动）；也不控制预创建报名审批（那是队长的 isAutoAccept，见 retail.group.quick-join）。

## 机制细节
- 注册：Social.lua 社交页 `SetupCVarCheckbox("autoAcceptQuickJoinRequests", ...)`，外层 `if C_CVar.GetCVar(...)` 条件注册。
- 消费：UIParent.lua:2424 `isQuickJoin and isSelfRelationship and GetCVarBool(...) and not C_QuestSession.Exists()`；isSelfRelationship 实为 `SocialQueueUtil_GetRelationshipInfo` 返回的任意社交关系(bnfriend/wowfriend/guild/club)（SocialQueue.lua:177-214），参数名有历史误导。
- 同页只有 block 类开关：屏蔽公会邀请(:84)/邻里(:90)/日历(:92)/频道(:96)/交易(:79)——方向都是"拒绝"，不是"自动接受"。
- 队员→团队静默转换路径（"被拉进团队"高频真因之一）：队长 ConvertToRaid 对队员无确认弹窗（API 文档 PartyInfoDocumentation.lua:134-137 "convert to raid immediately"；镜像内无队员侧 CONVERT_TO_RAID 确认框）。**无开关可关**，只能不随便进陌生小队。

## 版本差异
| 版本区间 | 状态 |
|---|---|
| ≤11.x | 据老攻略有"界面设置→自动接受邀请"与 /autoaccept 系命令——**未逐一核验，且 12.x 全灭**（本条事故原型） |
| ≥12.0 | 见上文。/autoaccept 在 UI 镜像零痕迹；命令为引擎侧，UI 层无法证伪 ⚠️，不要向玩家推荐 |

## 常见误区
- 把本开关当"防被拉进团"方案 → 方向答反（直播第一风险）。
- 暴雪原生做不到"零确认自动接受邀请"；集合石/AutoInvite/ElvUI 可以 → `addons/_catalog.md`。

## 相关条目
qa.retail-avoid-auto-group · retail.social.party-invite-dialog · retail.group.quick-join · addons._catalog

## 核验日志
- 2026-09-25 @12.1.0.69283：Social.lua 全文 grep 仅 1 处 autoAccept；UIParent 消费点/方向、Quest Session 例外、转团静默，deepthink 全树候选内证实。
