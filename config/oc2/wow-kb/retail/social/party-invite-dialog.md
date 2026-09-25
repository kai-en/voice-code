---
id: retail.social.party-invite-dialog
title: 组队邀请弹窗（PARTY_INVITE）的行为
aliases: [邀请弹窗, 组队邀请, 拒绝邀请, 邀请超时, 自动拒绝]
applies:
  line: retail
  versions: ">=12.0"
  servers: [intl, cn]
  build_ref: "12.1.0.69283"
  mirror_ahead_of_cn: true
mechanism: builtin
status: verified
evidence:
  - ref: "Blizzard_StaticPopup_Game/GameDialogDefs.lua:1286-1310@12.1.0.69283"
    url: "https://raw.githubusercontent.com/wind-addons/BlizzardInterfaceCode/2c2973cc136bf4f90bb229dd864a402e4c75df19/Interface/AddOns/Blizzard_StaticPopup_Game/GameDialogDefs.lua"
  - ref: "Blizzard_UIParent/Mainline/UIParent.lua:1398-1426@12.1.0.69283"
    note: "PARTY_INVITE_REQUEST 三分支入口"
verified: { date: 2026-09-25, by: "deepthink-0925" }
---

## TL;DR
收到组队邀请弹窗：点"接受"才进队；**放着不管会自动拒绝**（关闭即 Decline）。不想进队什么都不用做，别手快点接受。

## 方向性声明
- 作用于谁：被邀请方（我）。
- 哪侧生效：我这侧弹窗；无内置自动接受分支（12.x 核验范围内）。
- 不控制什么：管不了别人加入"我的"队（那是 retail.social.auto-accept-invite 的 CVar）。

## 机制细节
- `StaticPopupDialogs["PARTY_INVITE"]`：button1 ACCEPT→`AcceptGroup()`；OnCancel/OnHide 未接受则 `DeclineGroup()`（GameDialogDefs:1286-1310）。
- 拒绝键有 0.5 秒锁定防误拒（`SetupLockOnDeclineButtonAndEscape`，同文件 :19-42）；**接受键没有锁**——误点接受是真实事故路径。
- 事件入口（UIParent:1398-1426）：带职责的 LFG 邀请走 `LFGInvitePopup`、任务队伍走 QuestSession 确认框、其余走 PARTY_INVITE——三支都需显式确认。

## 常见误区
- "不点会一直挂着" → 错，超时/关闭即自动拒绝。
- "能设成不弹邀请" → 12.x 无此开关；只有 block 类（公会/频道/日历邀请）在设置→社交。

## 相关条目
retail.social.auto-accept-invite · qa.retail-avoid-auto-group

## 核验日志
- 2026-09-25 @12.1.0.69283：弹窗定义与事件入口逐字核读。
