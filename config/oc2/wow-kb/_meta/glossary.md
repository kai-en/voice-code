---
id: meta.glossary
title: enUS↔zhCN 界面术语对照
status: verified
verified: { date: 2026-09-25, by: "deepthink-0925" }
---

# 界面术语对照表

zhCN 字符串编译进引擎（GlobalStrings），UI 镜像只能看到常量名，故本表独立维护。
**纪律**：cn 列无出处一律标（待核）；口播不硬报未核实文案。

| en（常量/英文界面） | cn（国服） | 界面位置 | 来源 | 核验日期 |
|---|---|---|---|---|
| Auto Accept Quick Join Requests (`AUTO_ACCEPT_QUICK_JOIN_TEXT`) | 自动接受快速加入申请（待核） | ESC→选项(设置)→社交 | NGA 帖引用（2026-09 检索摘要） | 2026-09-25 |
| Quick Join | 快速加入（待核） | 好友/社交面板页签 + 小地图旁气泡按钮 | 社区通用译法 | 2026-09-25 |
| PARTY_INVITE 弹窗 接受/拒绝 | 接受 / 拒绝 | 弹屏邀请框按钮 | 游戏通用，高置信 | 2026-09-25 |
| Group Finder / Raid Finder | 团队查找器 / 团队副本查找器（待核） | I 键面板 | 通用译法 | - |
| Premade Groups / LFGList | 预创建队伍 | 团队查找器内 | NGA 通用说法 | 2026-09-25 |
| Auto-accept (listing option, `LFG_LIST_AUTO_ACCEPT`) | 自动接受（申请）（待核） | 预创建队伍发布/管理项 | 代码+社区 | 2026-09-25 |
| Click-Castings (`L["Click-Castings"]`, Cell) | 点击施法 | Cell 选项→点击施法页签 | 本机安装件 zhCN.lua:213（S，插件自带 locale） | 2026-09-26 |
| Always Targeting (Cell) | 总是选中目标 | 同上页 | 本机 zhCN.lua:251 | 2026-09-26 |
| Click Cast Bindings (`CLICK_CAST_BINDINGS`, 暴雪面板) | 待核 | 选项→按键绑定 | GlobalStrings 镜像不可核 | 2026-09-26 |
| Prey Hunt（`Enum.PreyHuntProgressState`、`C_QuestLog.GetActivePreyQuest`） | 狩猎 / 猎物任务 | 银月城密谋小径·阿斯塔洛建筑内的**狩猎桌** | UI 镜像@12.1.0.69283 + 官网在线修正 2026-03-02（163 转载） | 2026-09-26 |
| Hunting difficulty（三档） | 普通 / 困难 / 梦魇 | 狩猎桌接取时选档 | 官网"至暗之夜"内容更新说明 2026-02-27 | 2026-09-26 |
| （困难/梦魇敌人额外能力） | 折磨 | 无界面项，机制词 | 官网 2026-02-19 狩猎系统文（英文常量待核） | 2026-09-26 |
| 12.0 / 12.1 战役名 | 光与影之战（12.0，含"黑暗之井"章节） / 乌拉特克的诅咒（12.1，盘卷蛇岛） | 战役进度界面 | bilibili 实录标题+游民星空+官网公告（主会话 bash 复核） | 2026-09-26 |
| 狩猎旅程（英文常量待核） | 待核（并存三写法：寻猎者旅程/寻猎者的旅程/猎踪者之旅，均非官网措辞） | 狩猎进度页 | 蓝贴译文稿+攻略稿，官方中文名未坐实 | 2026-09-26 |

## 常用检索词（玩家口语 → 库内别名）
"被拉进组/自动进组/秒进本" → alias: 自动接受邀请；"集合石自动收人" → addons；"老的那个自动接受开关怎么没了" → retail.social.auto-accept-invite 版本差异节；"梦魇任务/梦魇怎么做" → retail.quests.midnight-prey-hunt-nightmare（12.x 狩猎难度档，**不是**翡翠梦魇团本）；"蜿蜒的威胁/苦痛之岛" → 同上；"蛇岛" → 盘卷蛇岛（12.1 区域）。
