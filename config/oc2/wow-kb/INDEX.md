# WoW 知识库总索引

> **默认约定（全局，优先级最高）**：玩家问题未特别说明时，一律按【**国服（国内服务器）+ 正式服 retail 最新版本，当前 12.x**】处理；classic/forever 与"国际服"仅在玩家明确提到时才切换。
> **本表不是答案白名单**：条目=已核实缓存与示例；表里没有的问题按 SKILL 五步协议自主研究后作答。

格式：id | 标题 | status | build_ref（`-`=不依赖 build）。先 grep 本表未命中再进子目录。
时效核对一律读 `_meta/freshness.md`。

| id | 文件 | status | build_ref |
|---|---|---|---|
| meta.sources | _meta/sources.md | verified | - |
| meta.verification | _meta/verification.md | verified | - |
| meta.freshness | _meta/freshness.md | verified | 12.1.0.69283 |
| meta.glossary | _meta/glossary.md | verified | - |
| meta.writing-guide | _meta/writing-guide.md | verified | - |
| retail.social.auto-accept-invite | retail/social/auto-accept-invite.md | verified | 12.1.0.69283 |
| retail.social.party-invite-dialog | retail/social/party-invite-dialog.md | verified | 12.1.0.69283 |
| retail.group.quick-join | retail/group/quick-join.md | verified | 12.1.0.69283 |
| retail.raids.spire-story-mode-entry | retail/raids/spire-story-mode-entry.md | unverified(多源交叉) | - |
| retail.gamerules.disable-quick-join | retail/gamerules/disable-quick-join.md | unverified | 12.1.0.69283 |
| addons.catalog | addons/_catalog.md | unverified | - |
| addons.details-dual-windows | addons/details-dual-windows.md | verified | - |
| addons.gcd-ring-display | addons/gcd-ring-display.md | unverified | - |
| retail.ui.raidframe-buff-missing | retail/ui-settings/raidframe-buff-missing.md | verified | 12.1.0.69283 |
| addons.cell-raidframes | addons/cell-raidframes.md | verified | - |
| retail.ui.minimap-quest-trail | retail/ui-settings/minimap-quest-trail.md | verified | 12.1.0.69283 |
| qa.retail-raidframe-buff-missing | qa/retail-raidframe-buff-missing.md | verified | - |
| qa.retail-gcd-ring | qa/retail-gcd-ring.md | unverified | - |
| qa.retail-avoid-auto-group | qa/retail-avoid-auto-group.md | verified | 12.1.0.69283 |
| qa.retail-spire-story-mode | qa/retail-spire-story-mode.md | unverified | - |
| retail.quests.liadrin-well-phasing-bug | retail/quests/liadrin-well-phasing-bug.md | verified | 在线修正2026-09-04 |
| qa.retail-hour-of-need-liadrin-missing | qa/retail-hour-of-need-liadrin-missing.md | verified | - |
| retail.ui.click-bind-target-menu | retail/ui-settings/click-bind-target-menu.md | verified | 12.1.0.69283 |
| addons.cell-click-bindings | addons/cell-click-bindings.md | verified | - |
| qa.retail-raidframe-click-rebind | qa/retail-raidframe-click-rebind.md | verified | - |
| retail.quests.midnight-prey-hunt-nightmare | retail/quests/midnight-prey-hunt-nightmare.md | unverified(多源交叉) | - |
| qa.retail-nightmare-hunt-howto | qa/retail-nightmare-hunt-howto.md | unverified | - |

## 空目录占位（勿删，结构即承诺）
retail/commands、classic/*、forever、universal —— 首批未覆盖；新增条目须走 `_meta/verification.md` 核验流程后置状态。副本/任务进入流程类放 `retail/raids/`（首例已建）。任务 BUG/流程类放 `retail/quests/`（liadrin-well-phasing-bug、midnight-prey-hunt-nightmare）。ui-settings 首例已建（raidframe-buff-missing）。
