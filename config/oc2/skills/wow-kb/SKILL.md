---
name: wow-kb
description: Use when answering World of Warcraft questions in livestream (mechanics, settings paths, slash commands, group/invite behavior, addon vs builtin) — a META knowledge base: retrieval protocol + autonomous research playbook (webfetch/websearch) + evidence grading + TTS answer format. Library entries are examples/cache, NOT an allowlist of answerable topics.
---

# WoW 元知识库协议（oc2 直播用）

KB 根目录（部署后绝对路径）：`D:\work\voice-code\tools\oc2-home\config\opencode\wow-kb`
定位：本库存的是**怎么研究、怎么作答**（元知识），具体条目只是高频事实缓存和写法示例。**库里查不到 ≠ 不能答**——进入第 3 步自主研究。

## 五步协议
1. **定轴**：判产品线(retail/classic/forever；判不出默认 retail 并在口播里说明)与服务器(默认国服)。classic 分不清哪个服就反问一句或两版各给半句。
2. **查库（抄近路）**：先 grep `qa/`（玩家口语触发词）→ 命中即用其口播底稿；未命中 grep 全库 `aliases|title|zhcn_terms` → read 命中的**单个**条目；再看 `INDEX.md` 与 `_meta/freshness.md`（build 比对：大版本一致可引；小版本落后加"按 12.0 核的，新版本可能微调"；`outdated` 沿 superseded_by 走；`unverified` 带限定词）。库里有可用条目 → 直接第 5 步。
3. **自主研究（库查不到/查到了但玩家追问细节时）**：读 `_meta/sources.md`（问题类型→渠道表+证据分级），**工具用实测存在的这几个**：`websearch` / `webfetch` / `execute` / `playwright_browser_*`（tabs/evaluate/navigate/snapshot；浏览器操作先 `playwright_browser_tabs` 复用已有标签）：
   - 机制/命令/设置路径 → webfetch UI 源码镜像（raw.githubusercontent，URL 分片拼法见"URL 防改写"）；
   - 国服攻略/插件现状 → websearch 中文关键词，回溯 ≥2 个独立原创帖摘要互证；NGA 正文用 playwright 打开（本机 profile 已登录，**别动输入框以外的写操作**）；
   - **预算硬线：websearch+webfetch/browser 研究合计 ≤3 次**；到预算就用已有证据进第 4 步定级作答——直播玩家等不了第四轮搜索。
4. **定级**：给结论贴档——S 一手源码实锤→"我核实过"；B 多源交叉→"社区攻略交叉过"；孤证/没把握→"我不确定，倾向于…"。**研究与查库都拿不到证据才用兜底话术**。
5. **输出**：口播 ≤3 句、必含方向性(管谁/不管谁)与版本限定、带出第 4 步的证据档位口气；不念行号/URL/build 细节（说"客户端源码核实过"即可）。

## 兜底话术（TTS 可直接播）
- 已核实："我在客户端源码里核实过，当前版本这个开关只管别人加入你的队伍，管不了你被人拉走。"
- 版本存疑："这个设置新版本改过，我核实的是 12.1 的情况，你客户端更旧的话在社交设置页再确认下。"
- 超纲（研究后仍无据）："这个我现查了一圈也没找到靠谱说法，不敢说死，建议去 NGA 确认下，免得误导你。"
- 插件混淆："原生界面做不到自动接受邀请，那是集合石这类插件的功能，没装插件就得手动点。"

## 铁律
- 内置/插件必区分（查 `addons/_catalog.md`，插件死活看 NGA 摘要）；命令/路径必带版本区间。
- 新知只口播不落库：研究结论留给离线侧补录，会话内**不改任何库文件**。
- zhCN 按钮文案未在 `_meta/glossary.md` 核实的，用位置+功能描述代替。

## URL 防改写（千问中转层实测，研究时用）
- 症状：provider 中转层会扫描模型输出、把其中**完整 URL** 替换成它预取的 routify OSS 签名链接（替换发生在工具收到参数之前）。表现为：403、返回内容与目标无关、工具回显出现 `routify-file-proxy`。
- 对策（按序）：① 浏览器导航用 `playwright_browser_evaluate`，URL 在页内**分片拼接**后 `location.href`/`fetch`（如 `'cn.'+'bing'+'.com'`，实测可绕）；② 纯取文本用 `execute` 里 Invoke-WebRequest 直连（不经模型输出面，天然免疫）；③ 引用/入库只记**真实目标 URL**，被改写过的 routify 残留禁止复用（必 403）；④ 一次改写≠目标站不可达，换法重试再定论。
