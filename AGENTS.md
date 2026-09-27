# AGENTS.md

## Playwright 窗口使用规则

- 每次会话开始需要使用浏览器时，先用 `playwright_browser_tabs action=list` 核实是否已有 Playwright 窗口/标签；如已存在，必须复用现有窗口（在现有窗口中新建或选择标签），不要另开新窗口。
- 禁止修改此 Playwright 窗口的大小（不调用 `playwright_browser_resize`，也不以其他方式改变窗口尺寸）。用户已手动调整过窗口大小，用于直播时 AI 操作浏览器的实时显示效果。
- 详细使用 playwright 的方法（固定 user-data-dir、强制 headed 可视化的禁止清单）必须参考项目级 playwright skill：`.agents/skills/playwright/SKILL.md`（操作浏览器前用 skill 工具加载）。

## 启停与进程卫生（M10，设计 docs/0926工作/m10-proc-hygiene-textin-design.md）

- 启动/停止只经 `run.bat` / `stop.bat`（内部都是 `main.py --sweep --expect-clean`）；它报"残留不为 0"就是没清干净，不要绕过它手工再起一个。
- kill 前必须先过滤并逐条打印：锁内真 PID、镜像路径在本仓库下、命令行含 `main.py`/`tools\oc2` 且 cwd 在本仓库；严禁盲杀（本机常驻无关 node / anaconda 进程）。
- 单一实例由 `logs\voice-code.lock` 的 OS 字节锁证明（进程死即释放，不受 PID 复用骗）；`attach_job()` 必须在 spawn 任何子进程之前调用——job 成员资格在 CreateProcess 时定，先起的孩子逃过连坐。

## 依赖（M11）

- 本机 pip 有全局 `global.target=F:\python-packages`，该目录不在 sys.path → 普通 `pip install` 显示成功但 python 不认。必须：
  `.\.venv\Scripts\python.exe -m pip install -r requirements.txt --target .venv\Lib\site-packages -i https://mirrors.aliyun.com/pypi/simple/`
- 新增运行依赖登记进 `requirements.txt`（现仅 websockets；torch/sherpa-onnx/sounddevice 等历史依赖未登记，待补）。

## 播报期自听（硬件 AEC 已在场，仍禁止改代码）

- 助手外放被自家麦克风收回去（回采/自问自答/误打断）**不是软件缺陷**：本机现已配带硬件 AEC 的麦+音箱一体机，回声消除归硬件管；代码里也没有回声去重（`_is_echo` 已随 M10/M11 重构删除）。设计口径见 `docs/0925工作/m5-orchestrator-design.md` §6「假设声明：硬件 AEC 在场，播报期自听误打断为已知可接受项（观察计数，不设防护）」。
- 因此**禁止**为自听新增防护逻辑（额外门限、播放期禁麦、文本相似度加强等）；若观察到误打断仍频发，先查硬件链路（AEC 参考通道、音量、走线），软件侧只记录不设防。

## 本地控制台（M11）

- `ws://127.0.0.1:8765`（`VOICECODE_CONSOLE_PORT` 覆盖；禁用 4096——那是 opencode serve 的默认口）。只绑回环、无鉴权、**不 serve HTML**（非升级请求由库回 426）。
