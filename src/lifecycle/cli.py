# M10 CLI（main.py --probe / --sweep）：锁内真 PID 优先，其次双锚 sweep；kill 前逐条打印。
# 锚①=镜像路径在本仓库下（不看命令行，覆盖"相对路径命令行 + 仓库外镜像"形态）；锚②=名字+命令行含 main.py/tools\oc2。
# 锁空闲时绝不按裸 PID 杀（防 PID 复用误杀无关 node/anaconda 进程）。设计 §2.3。
from __future__ import annotations

import os
import subprocess

from lifecycle import procguard as pg

_NAMES = ("python", "pythonw", "cmd", "opencode", "node", "bun")
_ROOT_DIR = str(pg.ROOT).lower().rstrip("\\/")


def _under(path):
    p = (path or "").lower().replace("/", "\\")
    return p == _ROOT_DIR or p.startswith(_ROOT_DIR + "\\")


def procs():
    import psutil
    out = []
    for p in psutil.process_iter(["pid", "ppid", "name", "exe", "cmdline", "cwd"]):
        i = p.info
        out.append({"pid": i["pid"], "ppid": i["ppid"] or 0, "name": (i["name"] or "").lower(),
                    "exe": i["exe"] or "", "cmd": " ".join(i["cmdline"] or []), "cwd": i["cwd"] or ""})
    return out


def ancestors(ps):
    by = {p["pid"]: p["ppid"] for p in ps}
    seen, cur = {os.getpid()}, os.getpid()
    while cur in by and by[cur] not in seen:
        cur = by[cur]
        seen.add(cur)
    return seen


def anchor(p, skip):
    if p["pid"] in skip:
        return ""
    if _under(p["exe"]):
        return "exe"
    cmd = p["cmd"]
    hit = "main.py" in cmd or "tools\\oc2" in cmd.lower()
    here = _under(p["cwd"]) or _ROOT_DIR in cmd.lower().replace("/", "\\")   # 必须与本仓库有关，否则别的项目也叫 main.py
    if p["name"].startswith(_NAMES) and hit and here:
        return "cmd"
    return ""


def hits_of(ps):
    skip = ancestors(ps)
    return [(p, a) for p in ps for a in [anchor(p, skip)] if a]


def sweep(expect_clean=False, ps=None):
    ps = procs() if ps is None else ps
    hits = hits_of(ps)
    held, h = pg.locked(), pg.holder()
    hp = int(h["pid"]) if str(h.get("pid", "")).isdigit() else -1
    if held and hp > 0 and pg.alive(hp) and all(p["pid"] != hp for p, _ in hits):
        p = next((q for q in ps if q["pid"] == hp), None)
        if p:
            hits.append((p, "lock"))
    for p, a in hits:
        print(f"[m10] kill[{a}] pid={p['pid']} {p['name']} :: {p['cmd'][:110]}", flush=True)
        subprocess.run(["taskkill", "/PID", str(p["pid"]), "/T", "/F"], capture_output=True)
    if hp > 0 and not held and pg.alive(hp) and all(p["pid"] != hp for p, _ in hits_of(procs())):
        print(f"[m10] 锁空闲但旧锁文件记着 pid={hp} 且不命中任何锚 → 拒绝 kill（防 PID 复用误杀）", flush=True)
    if not expect_clean:
        return 0
    left = hits_of(procs())
    if left or pg.locked():
        for p, a in left:
            print(f"[m10] 残留[{a}] pid={p['pid']} {p['name']} :: {p['cmd'][:110]}", flush=True)
        print(f"[m10] FAIL: 残留 {len(left)} 个" + ("，且锁仍被占" if pg.locked() else ""), flush=True)
        return 5
    print("[m10] clean: 0 残留，锁空闲", flush=True)
    return 0


def probe():
    held, h = pg.locked(), pg.holder()
    print(f"[m10] lock={'HELD' if held else 'FREE'} {h or '{}'}", flush=True)
    hits = hits_of(procs())
    print(f"[m10] anchored={len(hits)} " + "; ".join(f"{p['pid']}/{p['name']}/{a}" for p, a in hits[:8]), flush=True)
    job = str(h.get("job", "?"))
    if held and job != "OK":
        print(f"[m10] job={job} → 连坐保证不成立，杀父可能留子（设计 §2.2 边界2）", flush=True)
    return 0 if not held and not hits else 3


def main(argv):
    if "--probe" in argv:
        return probe()
    if "--sweep" in argv:
        return sweep(expect_clean="--expect-clean" in argv)
    print("usage: main.py --probe | --sweep [--expect-clean]")
    return 2
