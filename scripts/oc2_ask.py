# oc2 调试问答回路（离线，不进语音链路）：
#   问题 → oc2 serve(agent=voice) → 收流式答案 → 结构报告(工具/权限/时延/cost) → 原始事件落 logs/
# 用法:  .\.venv\Scripts\python.exe -X utf8 scripts\oc2_ask.py "团队框架怎么只显示缺的buff"
#        .\.venv\Scripts\python.exe -X utf8 scripts\oc2_ask.py --file questions.txt   # 每行一问，同 session 连问
# 权限策略: 命中 wow-kb 读/skill → 自动 once 放行并记录；其余默认 reject（--yes 全放行）。
import argparse
import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from opencode_client import OcConfig, start_opencode  # noqa: E402
from opencode_client.types import OcLink, OcPermission, OcText, OcTool, OcTurnDone  # noqa: E402


class Debug:
    def __init__(self, args, client, sid, turn=1):
        self.args, self.c, self.sid, self.turn = args, client, sid, turn
        self.raw, self.tools, self.perms = [], [], []

    def on_event(self, ev):
        if isinstance(ev, (OcText, OcTool, OcPermission, OcTurnDone, OcLink)):
            self.raw.append(ev)
        if isinstance(ev, OcText):
            if not ev.final and ev.text:
                print(ev.text, end="", flush=True)
        elif isinstance(ev, OcTool):
            if ev.phase == "started":
                print(f"\n[tool] {ev.name}", flush=True)
            self.tools.append((ev.phase, ev.name))
        elif isinstance(ev, OcPermission):
            allow = self.args.yes or ("wow-kb" in (ev.message or "") or "skill" in (ev.action or ""))
            self.perms.append((ev.action, ev.message, "once" if allow else "reject"))
            print(f"\n[perm] action={ev.action!r} msg={ev.message!r} -> {'once' if allow else 'reject'}", flush=True)
            asyncio.get_running_loop().create_task(
                self.c.reply_permission(self.sid, ev.request_id, "once" if allow else "reject"))

    def report(self, t0, done):
        print("\n---- 报告 ----")
        if done is None:
            print("[!] 未收到 TurnDone（超时/断链？）")
        else:
            print(f"outcome={done.outcome} cost={done.cost}")
            if done.error:
                print(f"error={done.error}")
            if done.text:
                print(f"[终稿] {done.text}")
        d = [e for e in self.raw if isinstance(e, OcText)]
        print(f"时延={time.time()-t0:.1f}s deltas={sum(1 for e in d if not e.final)} "
              f"finals={sum(1 for e in d if e.final)}")
        called = sorted({n for p, n in self.tools if p == "called" and n})
        started = sorted({n for p, n in self.tools if p == "started" and n})
        print(f"工具 started={started}\n     called={called}")
        if self.perms:
            print(f"权限={self.perms}")
        log = ROOT / "logs" / f"oc2_ask_{datetime.now():%Y%m%d_%H%M%S}_{self.turn}.jsonl"
        log.parent.mkdir(exist_ok=True)
        with open(log, "w", encoding="utf-8") as f:
            for e in self.raw:
                f.write(json.dumps({"type": type(e).__name__,
                                    **{k: str(v) for k, v in getattr(e, "__dict__", {}).items()}}) + "\n")
        print(f"原始事件: {log}")
        return 0 if (done and done.outcome == "succeeded" and done.text) else 1


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("question", nargs="?", default=None)
    ap.add_argument("--file", default=None, help="每行一问，同一 session 连问")
    ap.add_argument("--agent", default="voice")
    ap.add_argument("--timeout", type=float, default=180.0)
    ap.add_argument("--yes", action="store_true", help="权限全部 once 放行")
    args = ap.parse_args()
    qs = [q.strip() for q in Path(args.file).read_text(encoding="utf-8").splitlines() if q.strip()] \
        if args.file else ([args.question.strip()] if args.question else [])
    if not qs:
        ap.error("给一个问句或 --file")

    cfg = OcConfig(directory=str(ROOT / "tools" / "oc2-home" / "ws"), agent=args.agent)
    holder = {}
    c = await start_opencode(cfg, lambda ev: holder["d"].on_event(ev) if "d" in holder else None)
    rc = 0
    try:
        info = await c._rest.info()
        print(f"[oc2] version={info.get('version')} agent={args.agent}")
        sid = await c.session_new(f"debug-{datetime.now():%H%M%S}")
        holder["d"] = Debug(args, c, sid)
        for i, q in enumerate(qs, 1):
            holder["d"].turn = i
            print(f"\n=== Q{i}: {q}")
            t0 = time.time()
            fut = await c.send(sid, q)
            try:
                done = await asyncio.wait_for(fut, args.timeout)
            except asyncio.TimeoutError:
                done = None
                await c.interrupt(sid)
            rc |= holder["d"].report(t0, done)
            holder["d"].raw.clear(); holder["d"].tools.clear(); holder["d"].perms.clear()
        return rc
    finally:
        await c.aclose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
