---
id: retail.group.quick-join
title: 快速加入(Quick Join)与预创建自动接受
aliases: [快速加入, quickjoin, 气泡进组, 预创建, 自动接受申请, 秒进本]
applies:
  line: retail
  versions: ">=12.0"
  servers: [intl, cn]
  build_ref: "12.1.0.69283"
  mirror_ahead_of_cn: true
mechanism: builtin
status: verified
evidence:
  - ref: "Blizzard_QuickJoin/QuickJoinToast.lua:312-316@12.1.0.69283"
    url: "https://raw.githubusercontent.com/wind-addons/BlizzardInterfaceCode/2c2973cc136bf4f90bb229dd864a402e4c75df19/Interface/AddOns/Blizzard_QuickJoin/QuickJoinToast.lua"
    note: "点气泡只 ToggleQuickJoinPanel()，不直接进队"
  - ref: "Blizzard_QuickJoin/QuickJoin.lua:471-478, 613-637@12.1.0.69283"
    note: "AttemptJoin→LFGListApplicationDialog(报名框) 或 QuickJoinRoleSelectionFrame(职责确认框)→OnAccept→C_SocialQueue.RequestToJoin"
  - ref: "Blizzard_UIPanels_Game/Shared/SocialQueue.lua:124,143,171-172@12.1.0.69283"
    note: "isAutoAccept 是目标队伍预创建条目属性；需与队长有社交关系；tooltip 淡蓝提示行"
  - ref: "Blizzard_GroupFinder/Mainline/LFGList.lua:1261,1291,1301,1787-1812,4362-4372@12.1.0.69283"
    note: "手工建团默认 autoAccept=false；任务/剧情自动建团默认 true；AutoAcceptButton 仅队长可改"
verified: { date: 2026-09-25, by: "deepthink-0925" }
---

## TL;DR
快速加入**不存在"点一下就秒进别人队"**：至少"选条目→点加入→选职责确认"两三次主动点击。若目标队开了"自动接受"，则免队长审批瞬间入队——事后感觉像被拉，其实是你点过。看清 tooltip 淡蓝"自动接受"行再点。

## 方向性声明
- 作用于谁：`isAutoAccept` 挂在**目标队的预创建条目**上（队长侧设置），含义"自动放行加入申请"。
- 哪侧生效：审批发生在队长侧；**我方确认框始终存在**（报名/职责选择），12.x 无跳过。
- 不控制什么：不控制"我被邀请进别人的队"（那是 PARTY_INVITE）。

## 机制细节
- 链路：气泡(Toast)→面板→`AttemptJoin`→(lfglist 条目→报名框 / 其他→职责确认框)→`C_SocialQueue.RequestToJoin(guid, 坦/奶/输出)`——语义是"请求"（SocialQueueDocumentation.lua:109-124）。
- 非 lfglist 队列要求与队长有社交关系；`isAutoAccept` 才免审批（SocialQueue.lua:143 注释 "Must know the leader..."）。
- 高频雷点：**任务/剧情**自动建团路径 `autoAccept=true` 是代码默认（LFGList.lua:1291/1301）——玩家不知道就"报名即进"。
- 队长侧"接受申请"弹窗被 `autoAcceptQuickJoinRequests` 跳过的分支见 retail.social.auto-accept-invite（方向相反，勿混）。

## 常见误区
- "点气泡就进队" → 错，气泡只是开面板。
- "开了自动接受=我会被随便拉人" → 它是**入站放行**（别人进我的队），不是出站。

## 相关条目
retail.social.auto-accept-invite · qa.retail-avoid-auto-group · retail.gamerules.disable-quick-join

## 核验日志
- 2026-09-25 @12.1.0.69283：AttemptJoin/RequestToJoin 链路、isAutoAccept 语义、默认值三处逐字核读。
