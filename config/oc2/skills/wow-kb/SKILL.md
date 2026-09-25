---
name: wow-kb
description: Use when answering World of Warcraft questions in livestream (mechanics, settings paths, slash commands, group/invite behavior, addon vs builtin) — loads the WoW knowledge base retrieval protocol, freshness rules and TTS fallback scripts.
---

# WoW 知识库检索协议（oc2 直播用）

KB 根目录（部署后绝对路径）：`D:\work\voice-code\tools\oc2-home\config\opencode\wow-kb`

## 四步检索
1. **定轴**：判产品线(retail/classic/forever；判不出默认 retail 并在口播里说明)与服务器(默认国服)。classic 分不清哪个服就反问一句或两版各给半句。
2. **取条目**：先 grep `qa/`（玩家口语触发词）→ 命中即用其口播底稿；未命中 grep 全库 `aliases|title|zhcn_terms` 中文词 → read 命中的**单个**条目文件；再无则看 `INDEX.md`。禁止整库读入。
3. **核状态**：读 `_meta/freshness.md`；条目 build 与看板比对——大版本一致可引；小版本落后加"按 12.0 核的，新版本可能微调"；`outdated` 沿 superseded_by 走；`unverified` 必须带限定词。
4. **输出**：口播 ≤3 句、必含方向性(管谁/不管谁)与版本限定；不念行号/build 细节（说"客户端源码核实过"即可）。

## 兜底话术（TTS 可直接播）
- 已核实："我在客户端源码里核实过，当前版本这个开关只管别人加入你的队伍，管不了你被人拉走。"
- 版本存疑："这个设置新版本改过，我核实的是 12.1 的情况，你客户端更旧的话在社交设置页再确认下。"
- 超纲："这个超出我核实过的范围了，不敢说死，建议去 NGA 确认下，免得误导你。"
- 插件混淆："原生界面做不到自动接受邀请，那是集合石这类插件的功能，没装插件就得手动点。"

## 铁律
- 内置/插件必区分（查 `addons/_catalog.md`）；命令/路径必带版本区间（查条目的版本差异节）。
- 库里没有且验证成本高的问题：走超纲话术，禁止凭模型记忆补细节。
- zhCN 按钮文案未在 `_meta/glossary.md` 核实的，用位置+功能描述代替。
