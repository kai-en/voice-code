---
id: retail.ui.click-bind-target-menu
title: 内置「点击施法绑定」面板：选中目标/单位菜单可重绑修饰键组合，让出裸左/右键
aliases: [点击施法绑定, 选中目标改键, 右键菜单改键, shift左键, shift右键, 让出左键, 点击动作, click binding, 释放加血]
applies:
  line: retail
  versions: "12.x（expectBinding 闸 12.1.0.69283 已实装；面板首次引入版本未核）"
  servers: [cn, intl]
  build_ref: "12.1.0.69283"
  mirror_ahead_of_cn: true
mechanism: builtin
status: verified
superseded_by: null
evidence:
  - ref: "Blizzard_SettingsDefinitions_Frame/Mainline/KeybindingsOverrides.lua:36-49@12.1.0.69283"
    url: "https://raw.githubusercontent.com/wind-addons/BlizzardInterfaceCode/2c2973cc136bf4f90bb229dd864a402e4c75df19/Interface/AddOns/Blizzard_SettingsDefinitions_Frame/Mainline/KeybindingsOverrides.lua"
    note: "按键绑定页『点击施法绑定』按钮(CLICK_BIND_MODE)→ToggleClickBindingFrame；高级选项页镜像 AdvancedOptions.lua:13-16"
  - ref: "Blizzard_ClickBindingUI/Blizzard_ClickBindingUI.lua:112-137,176-184,474-503,340-341@12.1.0.69283"
    note: "Target/OpenContextMenu 两条 Interaction 行缺失时自动补 unbound 行（永远可改绑、不可删除）；点行捕获 button+MakeModifiers；同组合互斥挤占原绑定；保存=SetProfileByInfo"
  - ref: "Blizzard_APIDocumentationGenerated/ClickBindingsConstantsDocumentation.lua:8,13-14@12.1.0.69283"
    note: "Enum.ClickBindingInteraction 全枚举只有 Target=1、OpenContextMenu=2（NumValues=2）"
  - ref: "Blizzard_FrameXML/SecureTemplates.lua:838-841,844-889@12.1.0.69283"
    note: "*type1=target/*type2=menu 硬编码默认；OnClick 仲裁：法术/宏/宠物动作优先短路(:851-857)→Interaction 经 GetEffectiveInteractionButton 映射回默认按钮读属性(:863-867)→expectBinding 守卫：组合在点击绑定档无交互绑定则拒绝 target/menu(:871-875)"
  - ref: "Blizzard_UnitFrame/Shared/CompactUnitFrame.lua:281@12.1.0.69283"
    note: "每个团队格 CompactUnitFrame_SetUnit→SecureUnitButton_OnLoad；所有 SecureUnitButtonTemplate 系（玩家/目标/小队/团队/竞技场/首领框）全吃这套，非团队框架专属"
verified: { date: 2026-09-26, by: "deepthink-0926 全树调研（blob-sha 双镜像比对11文件）；局内实机未测" }
---

## TL;DR（口播底稿）
属实：内置选中目标、开单位菜单可以改绑到 Shift+左键、Shift+右键这类组合——但不在团队框架设置里，在**选项→按键绑定→「点击施法绑定」面板**（按钮也镜像在高级选项页）。把默认动作区那两行改到 Shift 组合，再给裸左/右键绑治疗术，点保存即可，引擎自动让裸键优先施法。对全部原生单位框生效。

## 方向性声明
- 作用于谁：自己客户端的输入绑定（C++ `C_ClickBindings` profile，按当前专精存，Lua 不可见介质）。
- 在哪一侧生效：客户端本地，SecureUnitButton_OnClick 引擎仲裁。
- 不控制什么：不影响队友；**不控制插件框体**——Cell 等自家框体不读原生面板（见 addons.cell-click-bindings），原生面板改绑对它们无效。

## 机制细节
- 入口唯一：KeybindingsOverrides.lua:43（注释"Mirrored in Advanced Options"）；全仓检索 Enum.ClickBindingInteraction 仅命中面板+枚举文档两文件，团队框架设置页（EditMode/CompactUnitFrameOptions）**无**点击行为项。
- 两条交互行不可删（showDelete 排除 InteractionBinding），profile 缺失时面板自动补 unbound 行等着玩家改绑。
- 重绑流：点行→按住修饰键+按鼠标键（支持 Button1-31）→行数据变→**必须点"保存"**（未保存关窗弹丢失确认）。同组合互斥：绑给新动作时原占用者自动变未绑定并提示。
- 点击仲裁顺序（OnClick:847-875）：该组合绑了法术/宏→直接施法 return（施法最优先）→是交互绑定→GetEffectiveInteractionButton 把 Shift+左映射回"左键"读 type1 属性→若该组合在点击绑定档里什么都不是（None）→**target/menu 拒绝执行**（expectBinding 守卫——第三方插件 12.x 修饰键改键卡的就是这道闸）。
- 重绑本体零 CVar（已查目录内无 clickToTarget/lmb/rmb 类）；相邻的 `enableMouseoverCast`（选项→战斗页，Combat.lua:46-63）是"悬停施法"，另一码事。
- zhCN 面板文案（CLICK_CAST_BINDINGS 等）=GlobalStrings 镜像核不到，**待真机**；口播用"按键绑定页里的点击施法绑定面板"定位。

## 版本差异
| 区间 | 状态 |
|---|---|
| 经典怀旧 | 无此系统（SecureTemplates:847 `if C_ClickBindings then` 注释明示 Classic 缺席） |
| 12.x | 如左全机制（@12.1.0.69283，镜像超前，国服现网 build 待核）；面板首次引入版本未核（社区口径 10.1.5 属旧点击施法系统，两回事），口播不提"从 X 版本起" |

## 常见误区
- 去"团队框架"设置/EditMode 里找点击选项 → 没有，唯一入口是按键绑定页那个面板。
- 改完忘点"保存"（点行只改 UI 数据）。
- 把"悬停施法"当"点击施法绑定"（一个在战斗页 CVar，一个是点击面板）。
- 以为原生面板改好了 Cell 就会跟着变 → 两套系统互不相通。

## 相关条目
addons.cell-click-bindings（Cell 侧对应能力）· retail.ui.raidframe-buff-missing · qa.retail-raidframe-click-rebind

## 核验日志
- 2026-09-26 @12.1.0.69283：wind-addons 全树（trees API）+CompactUnitFrame.lua 落盘精确行号；其余 11 文件与 Gethe/wow-ui-source blob sha 逐字节比对后采其行号；grep.app 检索 Enum 全仓覆盖面。局内实机未测，国服 build 未核（限定词见版本差异）。
