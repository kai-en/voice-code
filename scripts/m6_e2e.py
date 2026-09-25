# M6 端到端冒烟（真 oc2 serve + 真模型，设计 §5 T-M6-4 的最小形态）：
#   attach → session_new → send → 收 OcText 流 → TurnDone 校验 → aclose(含子进程回收)
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from opencode_client import OcConfig, OcText, OcTurnDone, start_opencode  # noqa: E402


async def main() -> int:
    cfg = OcConfig(directory=str(ROOT / "tools" / "oc2-home" / "ws"))
    got = []
    c = await start_opencode(cfg, got.append)
    try:
        sid = await c.session_new("m6-smoke")
        print("[m6e2e] session:", sid)
        fut = await c.send(sid, "请只回复两个字：明白。不要调用任何工具。")
        done = await asyncio.wait_for(fut, 120)
        deltas = [g for g in got if isinstance(g, OcText) and not g.final]
        finals = [g for g in got if isinstance(g, OcText) and g.final]
        print(f"[m6e2e] deltas={len(deltas)} finals={len(finals)}")
        print("[m6e2e] TurnDone:", done)
        ok = (isinstance(done, OcTurnDone) and done.outcome == "succeeded"
              and done.text and deltas)   # 免费模型不保证逐字听话, 结构正确即 PASS
        print("[m6e2e]", "PASS" if ok else "FAIL")
        return 0 if ok else 1
    finally:
        await c.aclose()
        print("[m6e2e] serve alive after close?",
              c._serve.alive if c._serve else "n/a")


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
