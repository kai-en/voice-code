---
id: qa.retail-gamepad-enable
title: 手柄怎么开/手柄命令有几个
aliases: [手柄怎么开, 手柄模式, 用手柄, 手柄指令, gamepad开关, 手柄没反应, 吐息转不动, 红喷绿喷朝向]
status: verified
applies: { line: retail, servers: [intl, cn] }
verified: { date: 2026-09-30, by: "offline-0930" }
---

## 问法
- WoW 能用手柄吗？开手柄打什么命令？
- 选项里有没有"游戏手柄"设置页？
- 手柄相关的 cvar/开关一共几个？怎么全列出来？
- 动作条上的手柄提示（LB+A 那种）怎么去掉？
- 用手柄移动、鼠标瞄准，放吐息（红喷/绿喷）时角色不跟鼠标转，怎么回事？

## 口播底稿
能用手柄。聊天框打 `/console GamePadEnable 1` 就是总开关，关就填 0；手柄相关开关一共 39 个，打 `/console cvarlist GamePad` 能一次全列出来。注意正式服**没有**"选项→游戏手柄"面板（那是 Forever 客户端的），手柄键在普通按键绑定菜单里绑；要舒服的手柄界面得靠插件 ConsolePort。别信小写的 gamePad 命令，正名是 GamePadEnable，改完顺手 `/reload` 一次。
想藏手柄角标提示（摇杆+键盘混用场景）：没有 cvar，去按键绑定里把动作条的手柄快捷键全解绑就行，键盘角标照常显示。
吐息转不动=gamepad 模式抢了镜头控制权：吐息宏里加一行 `/run SetGamePadFreeLook(false)` 强制交还鼠标即可（主播实机验证零副作用；前提是 ActionButtonUseKeyDown 保持 0）。细节与诊断命令看权威条目实战技巧节。

## 权威条目
retail.commands.gamepad-cvars（含"实战技巧"节：拇指摇杆+键盘混用去提示）

## 核验日志
- 2026-09-30 随权威条目建立（deepthink 三路交叉）。
- 2026-09-30 追加"去手柄角标提示"问法与底稿（来源=主播实机）。
- 2026-09-30 追加"吐息鼠标转不动"问法与底稿（deepthink 取证+主播 12.1 实机验证）。
