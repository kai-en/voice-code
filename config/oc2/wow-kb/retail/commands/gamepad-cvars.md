---
id: retail.commands.gamepad-cvars
title: 手柄(GamePad)CVar 与 console 命令全表（Retail）
aliases: [手柄, 手柄命令, 手柄开关, 游戏手柄, gamepad, 控制器, GamePadEnable, 手柄光标, 吐息, 红喷, 绿喷, 鼠标转不动, SetGamePadFreeLook]
applies:
  line: retail
  versions: ">=9.0.1，清单核验至 12.1.5"
  servers: [intl, cn]
  build_ref: "12.1.5.69594（PTR 自动 dump）"
  mirror_ahead_of_cn: true
mechanism: builtin
status: verified
superseded_by: null
evidence:
  - ref: "warcraft.wiki.gg Console_variables/Complete_list@12.1.5.69594（客户端自动 dump，1753 条）"
    url: "https://warcraft.wiki.gg/wiki/Console_variables/Complete_list"
    note: "GamePad* 前缀 34 + CameraFollowGamepad* 2 + SoftTarget* 3 = 39；默认值/描述/加入版本出处"
  - ref: "Gethe/wow-ui-source@live + Ketho/wow-ui-source-standard-ptr@ptr2 git trees 对照"
    note: "Retail UI 仅 2 个 GamePad API 文档 lua、无手柄面板/动作条；forever 分支 128 个手柄文件 + 6 个 Blizzard_Gamepad* AddOn"
  - ref: "us.forums.blizzard.com en/wow/t/683913（Duff 2020-10-17，9.0.1 手柄指南）"
    note: "激活=/console GamePadEnable 1；PAD 令牌合法值表（与 dump 的 CVar 名一致）"
verified: { date: 2026-09-30, by: "deepthink-0930" }
---

## TL;DR（口播底稿）
Retail PC 手柄支持官方只给**输入层、没有"游戏手柄"选项面板**；手柄相关 cvar 共 **39 个** + 2 条 console 命令，总开关 `GamePadEnable`，激活打 `/console GamePadEnable 1`。网传的 `gamePad`（小写）cvar 和 `EnableGamePad` 斜杠命令均已证伪——不存在。

## 方向性声明
- 作用于谁：本客户端的手柄输入/光标/镜头/移动仲裁（builtin，非插件功能）。
- 在哪一侧生效：存本地 Config.wtf（这批 cvar Category/Scope 空 = 不跟服务器同步、不按角色区分），同客户端每次登录都受影响。
- 不控制什么：不生成手柄 UI/动作条（那是插件 ConsolePort 或 Forever 客户端的事）；不涉"主机版"——Xbox/PS 不存在 WoW 主机版，这批 cvar 就是 PC/Mac 通用。

## 机制细节（分组；名=默认值，括号=加入版本）
- **总开关/设备(4)**：GamePadEnable=0（9.0.1 总开关）GamePadSingleActiveID=0（0=合并所有设备）GamePadVibrationStrength=1（9.1.5，0–1）GamePadFactionColor=1（9.2，DS4 灯条跟阵营色）
- **键盘修饰键模拟(4)**：GamePadEmulateCtrl=PADLSHOULDER GamePadEmulateShift=PADLTRIGGER GamePadEmulateAlt=none GamePadEmulateTapWindowMs=350（9.2.5，点按判定毫秒）
- **光标(14)**：GamePadCursorLeftClick=PADRTRIGGER RightClick=PADRSHOULDER Centering=0（锁屏幕正中，社区最常用）CenteredEmulation=1 ForTargeting=1（9.1.5，2=从目标位置起）AutoEnable=1 OnLogin=1 AutoDisableJump=1 AutoDisableSticks=2 PushCamera=1（9.1）SpeedStart=0.1 SpeedMax=1 SpeedAccel=2 GamePadTouchCursorEnable=1（DualSense 触摸板）
- **镜头(6)**：GamePadCameraYawSpeed=1 PitchSpeed=1 LookMaxYaw=0 LookMaxPitch=0 CameraFollowGamepadAdjustDelay=1 AdjustEaseIn=1
- **移动/朝向(7)**：GamePadAnalogMovement=1（9.1；两 dump 冲突为 0，见误区）RunThreshold=0.5（10.0，走→跑阈值）FaceMovementMaxAngle=0 / MaxAngleCombat=180（9.1.5，0=永远朝向移动方向，180=从不）TurnWithCamera=1（9.1，2=总是）TankTurnSpeed=0 StickAxisButtons=0（9.0.5，摇杆四向生成虚拟按键）
- **输入仲裁(1)**：GamePadOverlapMouseMs=2000（10.0，需持续鼠标输入满该毫秒数才切回鼠标；语义修正见实战技巧）
- **软目标(3)**：SoftTargetEnemy=1 SoftTargetFriend=0 SoftTargetInteract=1 —— 取值 0=关 1=手柄 2=键鼠 3=总是
- **Console 命令(2，非 cvar，GetCVar 查不到)**：GamePadListDevices（列已连手柄）GamePadPlunderstormDefaults（一键设抢滩乱斗手柄默认值）
- **PAD 令牌取值**（按钮类 cvar 填这个，不是 0/1）：NONE / PADDUP·PADDOWN·PADDLEFT·PADDRIGHT / PAD1–PAD6 / PADL(R)SHOULDER / PADL(R)TRIGGER / PADL(R)STICK 及四向 / PADPADDLE1–4 / PADFORWARD(Start) PADBACK(Back) PADSYSTEM(PS 键) PADSOCIAL(Share 键)

## 查询与激活命令
- 激活：`/console GamePadEnable 1`（关=0）；宏等价 `/run SetCVar("GamePadEnable",1)`——39 个均非 secure cvar，`/console` 随便设。
- 一把全查：`/console cvarlist GamePad`；单查 `/dump GetCVar("GamePadEnable")`；值+默认+作用域 `/run print(C_CVar.GetCVarInfo("名字"))`。
- 状态：`/run print(C_GamePad.IsEnabled())`、`/run print(IsUsingGamepad())`（10.0.5+）；列设备用 console 命令 GamePadListDevices。
- 复位：`/console cvar_default <名>`（本次启动值用 cvar_reset）；按钮类示例 `/console GamePadCursorLeftClick PADLTRIGGER`。
- 改完稳妥打一次 `/reload`（是否即时生效社区报告不一，官方文档未说明）。

## 版本差异
- 9.0.1 上线驱动+首批 cvar；9.1/9.1.5/9.2/9.2.5/10.0 陆续补（最后三个新增=RunThreshold/OverlapMouseMs/SoftTarget*，10.0.0）；**11.x/12.x 零新增零移除**（dump 对照）。
- 已消失（勿再推荐）：GamePadEmulateEsc（wiki 人工页还在=幽灵条目）、GamePadForceXInput；GamePadFaceMovement 9.1.5 拆为 MaxAngle/MaxAngleCombat 两条。
- **Forever 客户端**（国服 beta 2026-10-06）：另有 57 个独有手柄 cvar（小写 `Gamepad*` UI 层）+ Blizzard_Gamepad 全套官方手柄选项面板/动作条；Retail 一个都没有，两线禁互相类比。

## 常见误区
- `/console gamePad 1`（小写）、consoleKeyBinds、EnableGamePad —— 全不存在；正名 **GamePadEnable**（大写 P）。
- `enableMovePad`/`movePadLocked` 等 MovePad*=无障碍屏幕虚拟方向键，与手柄硬件无关；含 "Pad" 不等于手柄。
- 报"选项→游戏手柄"路径=Forever 界面，Retail 没有；Retail 绑 PAD 键走普通按键绑定菜单；"手柄舒服 UI"=插件 ConsolePort（说时标注插件）。
- 默认值两 dump 冲突（GamePadAnalogMovement、SoftTargetEnemy/Interact）：以 Retail 专表报数，口播带"以游戏内 GetCVarInfo 为准"。

## 实战技巧（主播实机经验，2026-09-30）
- **前提=拇指摇杆(XINPUT)+键盘混用**（本主播玩法：摇杆只管移动，操作全在键盘）。此场景下原生动作条 HotKey 角标会显示手柄快捷键提示（LB+A 这类 PAD 文本），看着碍事。
- **解法（无 cvar，纯绑键操作）**：在按键绑定里把动作条上的手柄快捷键**全部解绑**即可；键盘角标（1/2/3/Q/E/R）照常显示，互不影响。不需要为此关 GamePadEnable（摇杆移动照用）。
- 反推出一条源码外事实：Retail 原生动作条 HotKey **会**渲染 PAD 绑定文本——本条"Retail 无手柄 UI"指无面板/动作条 AddOn，不指此角标。机制层未回镜像钉行号，按 unverified 实践口径引用。
- **吐息瞄准鼠标转不动（2026-09-30 主播 12.1 实机验证✅，零副作用）**：摇杆只管移动+鼠标转瞄准，放吐息（龙希尔红喷/绿喷）时角色有时不跟鼠标转——镜头所有权被 gamepad 模式占着；`GamePadOverlapMouseMs=2000` 真实语义="需**持续划鼠标满 2 秒**才夺回"（非等 2 秒自动回，社区受控实验+dump 交叉，B/C）。
- **首选修法**：吐息宏最前加一行 `/run SetGamePadFreeLook(false)`（与 /cast 前后顺序各试一次）——强制把镜头交还鼠标，左摇杆移动不受影响。前提：保持 `ActionButtonUseKeyDown 0`（设 1 会使此行失效，论坛实测）。函数存在性=wiki Global_functions S；语义=ConsolePort Mouse.lua 源码+论坛实测双源 B，无官方文字定义。
- **诊断一行**：失败瞬间打 `/run print(IsUsingGamepad(), IsUsingMouse(), IsGamePadFreelookEnabled())`——true/false/true=确诊仲裁抢占。想根治频率可另试 `/console GamePadOverlapMouseMs 0`（即时生效；代价=手柄光标基本作废，鼠标瞄准党净收益）。
- **"有时"的间歇元凶候选**：Discord 游戏内覆盖注入幽灵输入污染设备探测器（WoWUIBugs #506，B）——关覆盖对照观察。禁忌：`GamePadTurnWithCamera` 勿设 0（=镜头→角色传动轴，吐息正靠它）；`GamePadStickAxisButtons` 勿设 1（摇杆偏转生成本柄按键事件，反而立刻冻镜头）。

## 相关条目
qa.retail-gamepad-enable · _meta/sources.md（cvar 全量清单通路节）

## 核验日志
- 2026-09-30 deepthink-0930 @12.1.5.69594：三路交叉=wiki 自动 dump（名单/默认/版本）× UI 源码 trees（Retail 无手柄 UI、Forever 128 文件实锤）× 暴雪论坛 9.0.1 指南（激活命令/PAD 令牌）。候选名 9 个全证伪；stevesong.com 超时、kevinschaich/wow-cvars 仓不存在（404）。
- 2026-09-30 追加"实战技巧"节：来源=主播本尊实机（拇指摇杆+键盘，动作条解绑手柄键消 PAD 角标），机制未回镜像核，标实践口径。
- 2026-09-30 追加"吐息鼠标转不动"三条+OverlapMouseMs 语义修正：deepthink 取证（wiki dump S × 暴雪论坛 t/1538136 受控实验 × ConsolePort Mouse.lua × WoWUIBugs#506）；宏修法经主播 12.1 实机零副作用验证。社区证据版本分布 3.4.x/10.0.2/10.2.0，12.x 一手实测=主播本人。
