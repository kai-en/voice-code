---
id: meta.freshness
title: 时效性看板（唯一真源）
status: verified
verified: { date: 2026-09-25, by: "deepthink-0925" }
---

# 时效性看板

| 线 | 国服现网 | 国际服/镜像 HEAD | 差值状态 | 该区最后全量核验 | 备注 |
|---|---|---|---|---|---|
| retail | 12.0.x（具体 build 待核） | `12.1.0.69283`（sha 2c2973cc，2026-08-14） | **镜像超前(PTR)** | 2026-09-25（仅 social/group/邀请链路） | 引用 12.1 行号时加"镜像超前"限定 |
| classic | 未核验 | 未核验 | - | - | 首批不覆盖 |
| forever《无限》 | 未上线（官宣 2026-11-05 全球同步；国服 beta 2026-10-06） | 同左 | - | 2026-09-25（仅发布日期） | 证据源：官网/bing 检索；禁止用 retail 条目类比 |

## 触发式重验矩阵（摘要，全文见 writing-guide.md）
- 镜像小版本变化（12.0→12.1 类）→ 重验 `ui-settings/`、`commands/`、`social/` 优先。
- 国服上线追平 → 去 `mirror_ahead_of_cn`，按国服 build 复核行号 + glossary 补国服文案。
- 大版本/资料片 → 该线全量重验；`universal/` 逐条复核准入。
- 插件发版 → 对应 `addons/` 条目全标待重验。
- 条目 90 天未核验 → verified 自动降 unverified。

## build 引用基准
当前全库默认 `build_ref: 12.1.0.69283`，镜像 commit sha `2c2973cc136bf4f90bb229dd864a402e4c75df19`。
