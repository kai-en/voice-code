---
id: qa.retail-avoid-auto-group
title: "正式服怎么避免被自动拉进组/团"
triggers: [不经确认进队, 被拉进团队, 自动进组, 怎么不让别人组我, 秒进本]
authority: [retail.social.auto-accept-invite, retail.social.party-invite-dialog, retail.group.quick-join, addons.catalog]
applies: { line: retail, versions: ">=12.0", servers: [cn, intl], build_ref: "12.1.0.69283" }
status: verified
---

## 口播底稿（≤3 句）
"正式版现在没有自动接受邀请的官方开关，邀请弹窗不点就会自动拒绝。你能被秒拉进去，基本是集合石这类插件在自动替你点接受，去插件设置里关。另外注意别随便进陌生小队——队长转团那一刻是全队静默的，没有确认。"

## 完整处置清单（文字侧）
1. 插件：集合石/AutoInvite/ElvUI/整合包内"自动接受邀请"关掉（addons/_catalog.md）。
2. 不点邀请弹窗=自动拒绝（retail.social.party-invite-dialog）。
3. 不点快速加入/预创建"加入、报名"按钮；带淡蓝"自动接受"行的条目=点击即入（retail.group.quick-join）。
4. 别进不放心的小队：转团静默（auto-accept-invite 机制细节末段）。
5. 屏蔽项可用：设置→社交→屏蔽公会/频道/日历邀请（防骚扰向，非防拉人向）。
