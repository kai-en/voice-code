---
id: qa.retail-mousewheel-zoom-speed
title: 滚轮缩放太慢，有没有速度参数
aliases: [滚轮缩放太慢, 滚轮加速, 视野放大速度, 镜头缩放速度, 滚轮拉远]
status: verified
applies: { line: retail, servers: [intl, cn] }
verified: { date: 2026-10-01, by: "offline-1001" }
---

## 问法
- 鼠标滚轮缩放镜头太慢，有没有 cvar 能加速？
- 设置里有没有"相机缩放速度"滑条？（老版本有吗？）
- 想让镜头拉得更远/更广，打什么命令？

## 口播底稿
官方设置里**没有**缩放速度选项。引擎参数 `cameraZoomSpeed`（默认 20）经真机实测确实管滚轮缩放——但**只能调慢不能加速**：设 5 明显变慢，设 40 没感觉，默认 20 就是上限，"加速滚轮"官方侧无解。注意两点：设置里那个"鼠标环视速度"管的是右键转视角，不是缩放；要"看得更广"应该打 `/console cameraDistanceMaxZoomFactor 2.6`，那是视距上限、不是速度。网传的 CamZoomInDistance 那几个名字现在客户端里已经不存在了，别照着设。

## 权威条目
retail.commands.camera-zoom-cvars

## 核验日志
- 2026-10-01 随权威条目建立（deepthink 镜像+dump 双路交叉）。
