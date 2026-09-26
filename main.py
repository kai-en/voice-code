# voice-code 入口：python main.py 启动 M5 全流程；--probe/--sweep 走 M10 进程卫生。
# 早分流：探活/清扫绝不 import orchestrator（否则每次付 torch/sherpa 的导入成本）。
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent / "src"))

if {"--probe", "--sweep"} & set(sys.argv):
    from lifecycle import cli
    sys.exit(cli.main(sys.argv[1:]))

import asyncio                                     # noqa: E402
from orchestrator.main import amain                # noqa: E402

if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(amain()) or 0)
    except KeyboardInterrupt:
        sys.exit(130)
