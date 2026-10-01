---
id: addons.boss-mod-voice-packs
title: 团本语音播报插件与中文语音包（DBM/BigWigs，12.1 现状）
aliases: [语音播报插件, 语音插件, boss报警语音, DBM, BigWigs, BW, 夏一可, 夏一可语音包, VV语音包, 中文语音包, 语音包下载, 打本没声音]
applies:
  line: retail
  versions: ">=12.0"
  servers: [cn, intl]
  build_ref: "DBM 12.1.11 / BigWigs 2026-09 线（非 UI 镜像 build）"
mechanism: addon
status: verified
superseded_by: null
evidence:
  - ref: "DBM-Core/VoicePackSounds.lua@776b849f(12.1.11, blob经api.github.com/git/blobs取)"
    url: "https://github.com/DeadlyBossMods/DeadlyBossMods/releases/tag/12.1.11"
    note: "440 个通用喊话键：scatter/scattersoon(分散)、gathershare(集合分担)、stackhigh、teleyou/telesoon(传送)、newportal/transporter、killmob/killbigmob/mobout/attackXXX(打小怪)、movetoXXX、count 1–10；release 12.1.11=2026-09-25"
  - ref: "Mini-Dragon/DBM-VoicePack-Yike 5931fdc7 之 DBM-VPYike_Mainline.toc + voicelist.csv(S)"
    url: "https://github.com/Mini-Dragon/DBM-VoicePack-Yike"
    note: "Interface:120100；X-DBM-Voice-Name 夏一可(普通话女)；X-DBM-Voice-HasCount/MidnightCompat:1；commit 'Update to 12.1.0'(2026-08-19)；csv 352 行中文映射(集合分担/新传送门/靠近小怪/真菌食肉者快打/靠近星星等)；CC BY-ND 禁改作"
  - ref: "BigWigsMods/BigWigs master 5e0db87d(2026-09-27) + BigWigs_Voice HEAD Core.lua(注册机制)(S)"
    note: "BW 主仓仍在更新 12.1 团本(乌拉特克/哨卫)；官方 BigWigs_Voice=英文默认语音框架(Amy)，Notes 有 zhCN；BigWigsAPI:RegisterVoicePack 为语音包挂载点"
  - ref: "nanjuekaien1/BigWigs_Voice_VV d936c9a4(2026-09-27) 之 toc+Core.lua+目录树+README(S)"
    url: "https://github.com/nanjuekaien1/BigWigs_Voice_VV"
    note: "中文 VV 语音包：RegisterVoicePack('VV')、Interface:120100、Notes-zhCN v12.1；4215 文件覆盖 Midnight(12.x) 团本/五人本/地下堡 + Sounds/Added 通用(add/adds/berserk)；X-Curse-Project-ID 305210；README：装后自动播报、倒数/开怪语音内设、私有光环另装 VVSharedMedia、可删旧资料片文件夹(保留 Added+本赛季)"
  - ref: "NGA bbs.nga.cn/read.php?tid=15396176 主帖正文(登录态全文,S)+2026-09-13 楼(B)"
    url: "https://bbs.nga.cn/read.php?tid=15396176"
    note: "VV 联系帖：下载=CurseForge bigwigs-voice-chinese-voicepack-vv + 蓝奏云/百度网盘(2024 版)；BW 默认开语音无需像 DBM 选包；五人本要计时条另装 LittleWigs；2026-09-13 楼：正式服旧内容时间轴'暴雪没添加代码，任何插件都读不出来数据'"
  - ref: "百度 SERP 摘要(2026-09-28, B)：大脚插件站/178 收录两包"
    note: "'DBM Voicepack: Yike 夏一可语音包'条目 20260819 版；'Bigwigs_Voice 中文VV语音包' VV 12.0.4(109MB, 2026-06-15)；插件来源均标 curseforge"
verified: { date: 2026-09-28, by: "offline-deep-research(主会话直查仓库+NGA)" }
---

## TL;DR（口播底稿）
12.1 语音播报还是 DBM 和 BigWigs 两家，都活着、都还在跟版本更新。DBM 能喊"分散、集合、传送、打小怪"这类通用战术词，但**文本是自带中文、语音要另装中文语音包**——主流是"夏一可(普通话女)"包；BigWigs 走"VV 中文语音包"，装完默认就喊。下载走 CurseForge 或大脚/178 插件站收录页，夏一可包 GitHub 也在更。

## 方向性声明
- 作用于谁：**本人客户端**的插件报警/语音，不向队伍/团队广播任何内容。
- 在哪一侧生效：DBM=装语音包后还要在 DBM 选项里选"夏一可(普通话女)"；BigWigs=官方默认开启语音，VV 包放对 AddOns 目录即自动播报（倒数/开怪语音在设置里选）。
- 不控制什么：**不控制旧版本内容的报警语音**——12.x 战斗文本/数据限制后，正式服旧团本/旧大米的时间轴任何插件都读不出（2026-09 NGA 讨论 B 级；两家仓库同期在修 "secret" 适配，S 级提交）；不控制游戏内置报警；管不了别人客户端。

## 机制细节
- **DBM 通用喊话键**（`DBM-Core/VoicePackSounds.lua`，12.1.11，S）：语音包按固定文件名供 ogg。玩家问的四类词全有专键——分散=`scatter/scattersoon`、集合/分担=`gather/gathershare`(集合分担)、传送=`teleyou/telesoon/newportal/transporter`(新传送门)、打小怪=`killmob/killbigmob/mobout(拉开小怪)/attackXXX(××快打)`；另有 `movetoXXX`(靠近柱子/星星/大饼…mm1–mm8)、`count/1–10` 倒数。夏一可包 voicelist.csv 给出每个键的中文台本（352 行，含 12.x 本怪名）。
- **夏一可包现状**：commit "Update to 12.1.0"（2026-08-19），TOC 声明 `X-DBM-Voice-MidnightCompat:1`；版权夏一可、CC BY-ND（**二改分发违规**）。挂载=整包放 AddOns，DBM 语音列表出现"夏一可(普通话女)"。
- **BigWigs/VV**：BW 框架 `BigWigsAPI:RegisterVoicePack`；VV 包自注册"中文语音：VV(女)"，逐副本供文件（烈毒之渊/尖塔等 12.x 全团本+大米+地下堡），私有光环音效需另装 VVSharedMedia。BW 本体装好即有五人本语音文字提醒，**计时条要 LittleWigs**。
- **文本≠语音**：DBM/BigWigs 界面与文字报警自带 zhCN 翻译（localization.cn.lua），语音必须装包；只装本体=有字幕没声音。

## 版本差异
| 区间 | 状态 |
|---|---|
| ≤11.x | 两家均主流；BW 曾有 Jingjing 等旧中文包（2022，现状未核） |
| 12.x | 两家活跃适配 secret 限制（DBM 12.1.11@2026-09-25；BW master@2026-09-27，S）；**仅当季内容可靠**；怀旧服线另走内置自定义 UI（见 freshness 生态事件），老帖称 BW 语音框架 6.0 前不存在（历史口径，未重验） |

## 常见误区
- "装了 DBM 就该说中文话"——文本有中文，**语音不装包不选包就不响**；"DBM 夏一可不说话/找不到倒计时语音"高频真因=DBM 本体更新而语音包滞后（NGA 2026-06、2024-08 帖，B）。
- 拿 GitHub 网页直连下载国服玩家版——发布主渠道是 CurseForge（大脚/178 收录页均标来源 curseforge），GitHub 仓是源码/同步地；夏一可包无 GitHub release，NGA 主帖 tid=7450738 已锁。
- 把"毒蛇说(SnakeSays)"当通用语音包——那是单副本助手（见 retail.raids.dv121-poisonfall）。
- 问"以前版本的团本语音"——12.x 起旧内容数据插件读不出，别承诺 DBM 能报旧本。

## 相关条目
addons._catalog · retail.raids.dv121-poisonfall-abyss · _meta/freshness（API 限制时间线） · qa.retail-voice-addon-pick

## 核验日志
- 2026-09-28：仓库 blobs/toc/commit 直查（api.github.com 通路）+ NGA tid=15396176 正文（登录态 S）+ 百度 SERP 大脚站两条目摘要（B）；Ranran 等 DBM 新包传闻 GitHub 查无仓，未入库。
