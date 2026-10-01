---
id: addons.catalog
title: 插件行为总表（内置等价物判别入口）
aliases: [插件, 集合石, AutoInvite, ElvUI, 整合包, EUI, 老农, DBM, BigWigs, 语音包]
applies: { line: retail, versions: ">=11.0", servers: [intl, cn] }
mechanism: addon
status: unverified
verified: { date: 2026-09-25, by: "deepthink-0925" }
---

# 插件总表

判别流程第一步（见 `_meta/verification.md` 第 4 节）：玩家描述的"自动"行为先在此查；命中=插件功能。
**证据等级说明**：本表来源为 NGA/百度知道检索摘要（C 级线索），发版敏感，全部标待核。

| 插件 | 相关行为 | native_equivalent（12.x） | 出处 | 状态 |
|---|---|---|---|---|
| 集合石（CN 预创建工具） | 设置内有"自动接受邀请"；队伍过滤/自动申请 | none（12.x 设置页已无该开关） | NGA tid=46416149 摘要(2026-09) | 待核 |
| AutoInvite（自动组队助手） | 自动接受邀请和排队确认 | none | NGA 正式服版块帖(2025-11-30 摘要) | 待核 |
| ElvUI | "一般"标签底部"自动"栏含自动接受邀请 | none | NGA tid=39655237 摘要 | 待核 |
| EUI / 老农整合包 | 包内聚合了自动接受类选项 | none | 百度知道提问摘要(2015 老帖, 版本漂移风险大) | 待核·低置信 |
| Details（战斗统计） | 多窗口各挂一种数据源：伤害+治疗同屏见专条 | 未核（原生战斗日志界面不展开） | 插件源码@1fc0b3ea(S) → addons.details-dual-windows | 已核实→见专条 |
| Cell（团队框架） | 原作者停更→米利修复版 r304（miliui站）；"增益缺失"指示器=缺buff才亮，12.1 光环 API 大改后指示器分批修复中；点击施法改键（选中/菜单→Shift组合）=自家"点击施法"页，12.x 闸需带 proxy 版本线；大脚集成版前夕即废 | displayBuffs 全显/全隐（S）；点击改键=原生面板只管原生框（S）→ retail.ui.click-bind-target-menu | NGA tid=47379276 全文(S) → addons.cell-raidframes · addons.cell-click-bindings | 已核实→见专条 |
| FarmHud（双采路线） | 小地图上红色移动路径箭头=该插件所画，设置内可关 | 内置任务轨迹是金色（且无开关，见专条） | NGA tid=43398700 定案帖(S正文) | 已核实 |
| GCD Cursor Plus / CursorRing（前身 Ultimate Mouse Cursor 系 WA，12.0 已停支持） | 屏幕 GCD 转圈圈环（跟随鼠标或固定中间） | none（内置无此形态，未深核） | CursorRing README(S) + NGA摘要×3(B) → addons.gcd-ring-display | 交叉·unverified |
| DBM（Deadly Boss Mods）+ 夏一可语音包 | 首领/小怪计时条+报警；"分散/集合/传送/打小怪"语音=语音包供文件，需设置选包 | 内置只有首领报警弹窗级（无计时/语音） | 主仓 12.1.11+VoicePackSounds.lua(S) → addons.boss-mod-voice-packs | 已核实→见专条 |
| BigWigs + VV 中文语音包（+LittleWigs 大米计时条） | 同上；装 VV 包后默认即语音播报 | 同上 | BW 仓 2026-09-27+VV 仓 2026-09-27(S)+NGA tid=15396176 正文(S) → addons.boss-mod-voice-packs | 已核实→见专条 |

## 定位某玩家是否被插件秒拉（直播话术之外的操作流）
逐项禁用插件 + `/reload` 复测；或问清整合包来源后查上表。暴雪原生做不到零确认入队（见 retail.social.auto-accept-invite），所以"从没装插件却被秒拉"→ 优先怀疑：已在小队中被队长转团（静默路径），或误点过快速加入/报名。
