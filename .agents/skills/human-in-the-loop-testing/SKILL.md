---
name: human-in-the-loop-testing
description: Use when a test requires human perception (listening to audio, viewing video/screen quality) or carries high real cost (money, disk, hardware side effects, long runtime) and therefore cannot be executed repeatedly by automated UT frameworks. Creates standalone scripts under human-test/ with a short run command for the user to execute manually.
---

# Human-in-the-loop Testing（人类参与的测试）

## 何时使用本 skill

当某项测试满足以下任一条时，不走自动化测试，改用本流程：

1. **需要人的感官判定**：音频质量试听、视频/画面质量观看、音色/延迟的主观评估；
2. **实际成本较大**：花钱（云 API 计费）、大量磁盘占用（录制长素材）、不可逆硬件操作（拔插设备）、耗时过长（数小时 soak）导致无法多次执行。

## 规则

1. 测试代码一律放入仓库根目录 `human-test/`，随库入库（提交、可追溯）。
2. **绝不放在 UT 框架的收集范围内**：
   - 文件名不得匹配 `test_*.py` / `*_test.py`（pytest 默认收集模式）；
   - 命名用 `<模块>_<用例>_<动作>.py`，如 `human-test/m1_t2_audio-listen.py`；
   - 首次创建目录时，在 pytest 配置中追加 `norecursedirs = human-test`（与已有配置合并，不覆盖），双保险。
3. 每个脚本必须**自包含、可单条命令执行、面向人类**：
   - 开头打印：目的、前置条件、人要做的事（说/播/看/听什么）、通过标准；
   - 执行客观可测的部分（如采集、落盘、统计），把主观判断留给人；
   - 结束时提示人类回报 `PASS / FAIL + 备注`，并指明记录位置（`human-test/RESULTS-<日期>.md` 或对应设计文档的实测表）；
   - 依赖不超过项目已有环境（如 voice-code：numpy、sounddevice，用 `.venv` 运行）。
4. agent **只生成脚本并给出启动指令，绝不代为"脑补"结果**；脚本由人类亲自执行，人类回报后再回填文档/结果表。

## 产出清单（每次按此交付）

- [ ] `human-test/<脚本>.py`（人类可一条命令跑起来）
- [ ] 若 `human-test/` 是新建的：确认 pytest 配置含 `norecursedirs = human-test`
- [ ] 给用户的启动指令（精确到解释器路径），例如：
      `.\.venv\Scripts\python.exe human-test\m1_t2_audio-listen.py`
- [ ] 提示：测试完成后把 PASS/FAIL 回填到 `human-test/RESULTS-<日期>.md`

## 脚本模板

```python
"""<模块> <用例号> <一句话目的>。 设计出处: docs/<...>-design.md §<n>
前置: <设备/环境要求>
步骤: 1) 听到/看到什么 2) 做什么 3) 对照通过标准
通过标准: <可勾选的明确判据>
"""
# ...自动部分：采集/生成/测量，打印客观数据...
print("\n[通过标准] 1. ... 2. ...")
input("[人类] 全部满足请按 ENTER 记 PASS，否则输入 FAIL 及备注: ")
```
