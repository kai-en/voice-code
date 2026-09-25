# human-test

需人类亲自执行的测试脚本（主观听/看判定、高成本、破坏性硬件操作）。
约定与模板见 `.agents/skills/human-in-the-loop-testing/SKILL.md`：
文件名不得匹配 `test_*.py`/`*_test.py`，本目录已在 pytest `norecursedirs` 中排除。
