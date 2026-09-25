---
id: meta.sources
title: 证据源清单与可达通路
status: verified
verified: { date: 2026-09-25, by: "deepthink-0925" }
---

# 证据源清单与通路优先级

回答/编写 WoW 问题时按此优先级取证据。**任何新域名先 HEAD 探测再决定，不要反复重试不通的源。**

## 通路优先级表

| 优先级 | 通路 | 用途 | 证据等级 | 注意 |
|---|---|---|---|---|
| 1 | raw.githubusercontent.com | UI 源码镜像文件直读 | S(一手) | URL 钉 commit sha；取前 HEAD 探测 |
| 2 | api.github.com | 提交历史(定 build)、git/trees 全树清单、contents 目录 | S(元数据) | 匿名 60 req/h；一次 trees 拿全树，省着用 |
| 3 | cdn.jsdelivr.net/gh/... | raw 的备胎同源 CDN | S(同源) | 单文件 ≤20MB；大 tarball 不适用 |
| 4 | cn.bing.com | 上线日期/国服节奏/zhCN 文案线索 | B(二手) | 结论必须落回 S 级或标 unverified；**RSS 对中文新增长尾词会失真**（2026-09-25 实测返回完全无关结果）——一次不中立即换路，勿重试 |
| 5 | baidu SERP(playwright) | 国服内容/攻略检索主力 | B(原创帖摘要) | **页面顶部 AI 答案卡片标注"内容由 AI 生成"=C 级仅线索**，必须回溯到贴吧/3DM/NGA 等原创帖摘要交叉 |
| 6 | NGA 摘要(读正文常要登录) | 国服文案/玩家实测/gamerule 线索 | C(仅线索) | 不作结论依据 |

## S 级够不到的内容（顶棚原则）
NPC 名/坐标、任务流程、副本奖励、开放时间等**游戏数据库内容不在 UI 镜像里**，S 级通路无法核实。此类条目顶棚=**≥3 个独立 B 级来源交叉一致**（见 verification.md 第 6 节），status 仍记 `unverified`，口播加"社区攻略交叉过"限定词，不冒充一手核实。

## URL 卫生（2026-09-25 三次踩坑）
上一轮工具输出里出现的 `routify-file-proxy...aliyuncs.com` 均为环境代理残留（403），**禁止整段复制粘贴 URL**，目标地址一律手写。

## 禁试清单（本机实测不通）
github.com 网页/git、wowhead.com、wowpedia(fandom)、duckduckgo。取货走上面 1-3 号路。

## 主镜像（source of truth）
- 仓库：`wind-addons/BlizzardInterfaceCode`（暴雪官方 UI 源码镜像，非第三方插件）
- 本次核验 HEAD commit sha：`2c2973cc136bf4f90bb229dd864a402e4c75df19` = build `12.1.0.69283`
- raw 基址（钉 sha）：`https://raw.githubusercontent.com/wind-addons/BlizzardInterfaceCode/2c2973cc136bf4f90bb229dd864a402e4c75df19/`
- 备镜像：`husandro/BlizzardInterfaceCode`(HEAD 12.0.5.67186) / `manbastiencs/BlizzardInterfaceCode`

## 引用纪律
- 短格式（正文）：`UIParent.lua:2423-2458@12.1.0.69283`
- 长格式（evidence.url）：raw URL 钉 commit sha；build 给人看，sha 防 HEAD 漂移。
- 版本证据 = 提交号（见 verification.md）；**禁止用 .toc 的 `## Interface` 行**（12.x 已删该行）。
