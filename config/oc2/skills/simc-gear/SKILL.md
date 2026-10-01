---
name: simc-gear
description: Use when the streamer asks WoW gearing advice (装备怎么提升/接下来打什么本/我现在这身能不能打) — read the SimC addon string from Windows clipboard with ONE pinned PowerShell command (fires the voice permission ask), get a sanitized summary with code-computed ilvl average & worst slots, then hand analysis to the wow-kb skill.
---

# SimC 剪贴板配装工作流（oc2 直播用）

前置：玩家游戏内已输 `/simc`（插件 Simulationcraft 会把角色串复制到剪贴板）。没说过、或锚校验失败，按下方 NOT_SIMC 引导，不猜。

## 第 1 步 取串——唯一一条 shell 命令（**逐字整行复制，任何字符都不要改**；执行前系统会向用户要语音授权，同意后才跑）

```powershell
$t=Get-Clipboard -Raw; if($t -notmatch '(?m)^# SimC Addon'){'NOT_SIMC'}else{ $m=[regex]::Matches($t,'(?m)#.+?\((\d+)\)[\r\n]+([a-z0-9_]+)='); $av=[math]::Round(($m|ForEach-Object{[int]$_.Groups[1].Value}|Measure-Object -Average).Average,1); $w=($m|Sort-Object{[int]$_.Groups[1].Value}|Select-Object -First 3|ForEach-Object{$_.Groups[2].Value+':'+$_.Groups[1].Value}) -join ' '; $s=($m|ForEach-Object{$_.Groups[2].Value+'='+$_.Groups[1].Value}) -join ' '; 'SIMC_OK c='+[regex]::Match($t,'(?m)^([a-z_]+)=').Groups[1].Value+' spec='+[regex]::Match($t,'(?m)^spec=(\w+)').Groups[1].Value+' lv='+[regex]::Match($t,'(?m)^level=(\d+)').Groups[1].Value+' avg='+$av+' worst='+$w+' time='+[regex]::Match($t,'(\d{4}-\d\d-\d\d \d\d:\d\d)').Groups[0].Value; 'slots['+$s+']'}
```

## 第 2 步 输出判读（红线，违反即事故）
- `NOT_SIMC`：**不解读剪贴板任何内容**（可能是玩家隐私），只播一句"没找到 simc 字符串，游戏里输 /simc 复制好再叫我"。
- `SIMC_OK …`：`avg=`（全身平均装等）与每槽数字**全部由命令算出**——口播只准引用本行原文，**禁止自己心算、加总、改数**。
- 输出里**没有**角色名/服名（命令源头脱敏），口播与思考也一律不得出现/猜测。
- `time=` 是复制时刻：距现在超过 30 分钟 → 先播一句"这是×点×分复制的旧串，要不要游戏里重抄一份？"；用户坚持则继续。

## 第 3 步 分析作答——转 wow-kb（不在本 skill 里作答）
用 skill 工具加载 `wow-kb`，按 `qa/retail-gear-next-step` → `retail/gear/preservation-evoker-gear-path` 的运行时协议执行：
1. 播 `c=`/`spec=` 对应的中文职业名并**确认专精**（如"你是唤魔师恩护吗？"），确认才套恩护条目；
2. 恩护：一次**只推 3 件**（`worst=` 槽 × 条目分槽来源表），玩家追问"还有呢"才续下一批；
3. 必给"能不能打"：对照条目档位表（273 排随机团宽裕/约 290 普通团入场线），数字口径带"以游戏内为准"；
4. 非恩护职业：不带恩护表，按 wow-kb 五步协议现查现答（档位/槽位数字仍只引用命令输出）。
