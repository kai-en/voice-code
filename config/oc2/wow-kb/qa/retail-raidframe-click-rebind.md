---
id: qa.retail-raidframe-click-rebind
title: "Cell 怎么把选中目标/右键菜单让给加血键"（口播底稿）
aliases: [Cell不支持改键, 没找到Cell设置, 原生能改Cell不能, 右键菜单占着]
applies: { line: retail, versions: "12.x", servers: [cn], build_ref: "-" }
mechanism: addon
status: verified
superseded_by: null
verified: { date: 2026-09-26, by: "v1-session-0926" }
---

## 问法
"原版框架能 Shift+左键选中、Shift+右键菜单，Cell 怎么不支持？是不是我没找到设置？"

## 口播底稿（≤3句）
Cell 支持的，设置不在暴雪的按键绑定里，在 Cell 自己选项页的"点击施法"标签——把默认的"目标""菜单"两行改绑到 Shift+左键、Shift+右键，再新建行把裸左键右键绑上你的治疗术就行。注意 12.x 客户端对修饰键选中/开菜单加了道安全闸，要用带修复的版本线：国服米利 r304 或 GitHub 上的 NeeRgY 线都行，原作者停更的老原版会被闸卡住。改完以你客户端实测为准，两套点击系统（原生面板和 Cell 自家）互不影响。

## 权威条目
addons.cell-click-bindings · retail.ui.click-bind-target-menu · addons.cell-raidframes
