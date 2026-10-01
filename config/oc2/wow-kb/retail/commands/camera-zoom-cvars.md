---
id: retail.commands.camera-zoom-cvars
title: 相机/滚轮缩放相关 CVar（cameraZoomSpeed 实证与边界）
aliases: [滚轮缩放, 缩放速度, 视野缩放, 镜头拉太远, 镜头拉近, cameraZoomSpeed, 滚轮不动, 放大太慢, 视角拉远]
applies:
  line: retail
  versions: ">=9.0.1（cameraZoomSpeed 起），清单核验至 12.1.5"
  servers: [intl, cn]
  build_ref: "12.1.5.69594（PTR 自动 dump）+ 镜像 12.1.0.69283"
  mirror_ahead_of_cn: true
mechanism: builtin
status: verified
superseded_by: null
evidence:
  - ref: "warcraft.wiki.gg Console_variables/Complete_list@12.1.5.69594"
    url: "https://warcraft.wiki.gg/wiki/Console_variables/Complete_list"
    note: "cameraZoomSpeed=20(since 9.0.1,官方描述为空)/cameraDistanceMaxZoomFactor=1.9(7.1.0)/cameraDistanceRateMult=1.0(1.0.0)；retail 全 dump 含 zoom 的名仅这 3+小地图 2 个"
  - ref: "Blizzard_FrameXML/Bindings_Standard.xml:1507-1520@12.1.0.69283"
    url: "https://raw.githubusercontent.com/wind-addons/BlizzardInterfaceCode/2c2973cc136bf4f90bb229dd864a402e4c75df19/Interface/AddOns/Blizzard_FrameXML/Bindings_Standard.xml"
    note: "CAMERAZOOMIN=按住 MoveViewInStart(1.0,0,true)+松开 CameraZoomIn(1.0)，OUT 对称；增量/速率写死在引擎绑定 XML"
  - ref: "Blizzard_SettingsDefinitions_Frame/Controls.lua 全文 + Mainline/ControlsOverrides.lua:3-4@12.1.0.69283"
    note: "12.x 设置→控制 鼠标组/镜头组均无'缩放速度'项；ControlsOverrides.AdjustCameraSettings 在 Mainline 是空函数（正式服不追加镜头设置）"
  - ref: "Blizzard_UIParent/Mainline/WorldFrame.lua:1-54@12.1.0.69283"
    note: "世界帧无任何 OnMouseWheel 处理——滚轮缩放由引擎原生吃，Lua 层无速度参数可读"
  - ref: "mpstark/DynamicCam Options.lua:229-234 等"
    note: "B 级语义旁证：相机插件把 cameraZoomSpeed 做成 'Camera Zoom Speed' 滑条(1–50,步长0.5,默认20)；与 dump 默认值吻合，滚轮生效方向已由主播实测证实"
verified: { date: 2026-10-01, by: "deepthink-1001" }
---

## TL;DR（口播底稿）
官方设置面板**没有"滚轮缩放速度"选项**；引擎 cvar `cameraZoomSpeed` 经主播国服 12.1 真机实测**确实作用于滚轮**——但默认 20 已是生效上限：设 40 无明显变快，设 5 明显变慢。**"加速"没有官方解**，该参数只能调慢。玩家若想"看得更广"，那是视距不是速度：`/console cameraDistanceMaxZoomFactor 2.6`。

## 方向性声明
- 作用于谁：本客户端相机缩放输入（滚轮/绑定动作/按住），存本地 Config.wtf，不影响他人与服务器。
- 在哪一侧生效：引擎侧（UI 镜像零消费点）；**作用于滚轮缩放已由主播 2026-10-01 国服 12.1 真机实测证实**（设 5 明显变慢；设 40 无感→默认 20 即生效上限，钳制方式未知）。
- 不控制什么：不控制 CameraZoomIn(1.0) 的步进增量（XML 写死）；cameraDistanceMaxZoomFactor 只抬最远视距上限，与速度无关；设置里"鼠标环视速度"=右键转视角（cameraYawMoveSpeed 90–270，默认 180），**不是**缩放速度，禁答错。

## 机制细节
- 滚轮通路：引擎原生 → 默认绑到 CAMERA 类别"镜头拉近/拉远"动作（DefaultBindings 在引擎层、镜像不含，真机验：`/run print(GetBindingKey("CAMERAZOOMIN"))`）→ 动作体=**按住连续（MoveViewInStart(1.0,0,true)）+ 点按单步（CameraZoomIn(1.0)）**混合。
- 在册 camera-zoom cvar（名=默认值）：cameraZoomSpeed=20（9.0.1，描述空）；cameraDistanceRateMult=1.0（1.0.0，三份来源描述全空，**第二实测候选**）；cameraDistanceMaxZoomFactor=1.9（7.1.0，视距倍数，DynamicCam 推荐 2.6）。
- 已证伪（当前 retail+五客户端 dump 全零命中，勿再推荐）：CamZoomInDistance1-4 / CamZoomOutDistance1-4、CamZoomSpeed、CameraZoomSpeed（大写名老滑条）、mouseWheelCameraZoom、cameraDistanceMaxFactor（7.1 起 retail 除名）。易混：GamePadMapZoomSpeed=手柄**地图**缩放。
- 命令面：/console 命令表**无任何相机/缩放专属命令**，走通用 set；`ZoomCamera` 函数查无（玩家口语=CameraZoomIn/Out）。宏可用（非保护函数）：`/run MoveViewInStart(3)` speed 参数=连续缩放速率（B 级 API 文档"Speed at which to begin zooming"）——对滚轮单步是否生效未证。
- 查询/设置：`/dump GetCVar("cameraZoomSpeed")`；`/run print(C_CVar.GetCVarInfo("cameraZoomSpeed"))`（回显未显示 min/max 钳制，默认 20 之上设 40 不吃）；降速可用 `/console cameraZoomSpeed 5`（实测明显变慢）；复位 `/console cvar_default cameraZoomSpeed`。
- 实测边界（主播 2026-10-01 国服 12.1）：**20→40 滚轮无明显变快；→5 明显变慢** → 生效区间在默认值以下封顶，"加速滚轮"此路不通；>20 是否被钳制还是动画已到最大速率，机制未证。

## 版本差异
| 版本区间 | 状态 |
|---|---|
| 1.12.1 / 3.3.5 | 面板仅"最大跟随距离"滑条（cameraDistanceMaxFactor 1–2）+环视/跟随速度，**无缩放速度滑条**（"老版本有过"传闻已被一手源码证伪）；滚轮=纯步进 |
| 7.1.0 | cameraDistanceMaxZoomFactor 出现，MaxFactor 自 retail 除名 |
| 9.0.1 | cameraZoomSpeed 出现；同期绑定变连续+步进混合（相机平滑化，时间吻合=B 级推断） |
| 当前（12.1.5 dump） | 三条 camera cvar 五客户端全在册（含 Classic Era 1.15.9；其面板是否暴露滑条未核） |

## 常见误区
- 答"调鼠标灵敏度/环视速度"=答非所问（那是转向，不是缩放）。
- 把 cameraDistanceMaxZoomFactor 当速度参数报——先问清玩家要"更快"还是"更广"。
- CamZoomInDistance1-4 / 大写 CameraZoomSpeed / mouseWheelCameraZoom 全是不存在的名字。
- 向玩家推荐"设大 cameraZoomSpeed 加速"——实测无效（20→40 无感），只能反向调慢；"加速滚轮缩放"官方侧无解，别再给数值建议。

## 相关条目
qa.retail-mousewheel-zoom-speed · retail.commands.gamepad-cvars（手柄线另册）

## 核验日志
- 2026-10-01 deepthink-1001 @镜像12.1.0.69283×dump12.1.5.69594：WorldFrame/Bindings_Standard/Controls(+Mainline Overrides)/AdvancedOptions/C_Camera 文档全文穷尽；wiki.gg 两份 dump 全名锚定 grep；1.12.1/3.3.5 一手源码核"老滑条"传闻；grep.app 双镜像仓证 MoveViewInStart/cameraZoomSpeed 消费点唯一性。未尽：DefaultBindings 滚轮默认键 B 级；cameraDistanceRateMult 语义。
- 2026-10-01 追加主播真机实测（国服 12.1）：cameraZoomSpeed 40=无感、5=明显变慢，GetCVarInfo 第二项=20；判"作用于滚轮但默认即上限"。cameraDistanceRateMult 未测，保持候选不裁决。
