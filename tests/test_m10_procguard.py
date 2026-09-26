# M10 进程卫生单测：锁互斥(A1) + job 连坐(A2) + 降级可见(A2b) + 锚定命中/不误伤(A3) + 拒杀陌生 PID。
import os
import subprocess
import sys
import time

import pytest

from lifecycle import cli
from lifecycle import procguard as pg

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
# 孙子用 ping（单进程、无 conda-venv 重定向器）：本测试只验 job 继承；
# "venv 启动器是 job 持有者的父、不被连坐"那层是 E3/§2.2边界1，由人工 H2 专测。
CHILD = """
import sys, time, subprocess
sys.path.insert(0, r"%s")
from lifecycle import procguard as pg
job = pg.attach_job()                      # 必须先入 job：job 成员资格在 CreateProcess 时定，先 spawn 的不在内
print("JOB", job, flush=True)
print("ACQ", pg.acquire("job"), flush=True)
g = subprocess.Popen(["ping", "-n", "120", "127.0.0.1"], stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL)
print("G", g.pid, flush=True)
time.sleep(120)
""" % SRC


def _alive(pid):
    import psutil
    return psutil.pid_exists(pid)


def _spawn(lock_path):
    env = dict(os.environ, VOICECODE_LOCK=str(lock_path), PYTHONIOENCODING="utf-8")
    p = subprocess.Popen([sys.executable, "-X", "utf8", "-c", CHILD], cwd=SRC, env=env,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
    out = {}
    for _ in range(3):
        line = p.stdout.readline()
        assert line, p.stderr.read()
        k, _, v = line.partition(" ")
        out[k] = v.strip()
    return p, out


def test_lock_exclusive_and_job_kill_on_close(tmp_path):
    """A1 + A2：锁互斥、进程死即释放；只 Terminate 真解释器（不带 /T），孙子必须连坐死。"""
    import psutil
    lock = tmp_path / "voice-code.lock"
    pg.LOCK = lock
    p, out = _spawn(lock)
    try:
        assert out["ACQ"] == "True" and out["JOB"] in ("OK", "UNSUPPORTED", "SKIP")
        h = pg.holder()
        real = int(h["pid"])
        assert real > 0 and pg.alive(real) and h["job"] == "job"      # 锁内记的是真解释器 PID（可能≠wrapper PID，见 E3）
        assert pg.locked() is True
        g = int(out["G"])
        if out["JOB"] != "OK":
            pytest.skip(f"本机 job={out['JOB']}（外层 job 不允许 nesting），连坐断言跳过")
        psutil.Process(real).terminate()                              # TerminateProcess，无 /T
        deadline = time.time() + 5
        while time.time() < deadline and _alive(g):
            time.sleep(0.2)
        assert not _alive(g), f"job 连坐失败：孙子 {g} 仍活着"
        assert pg.locked() is False                                   # 锁随进程死亡由 OS 释放
    finally:
        p.kill()
        p.wait(10)


def test_probe_warns_when_job_not_ok(monkeypatch, capsys):
    monkeypatch.setattr(cli, "procs", lambda: [])
    monkeypatch.setattr(pg, "locked", lambda: True)
    monkeypatch.setattr(pg, "holder", lambda: {"pid": "4242", "job": "UNSUPPORTED"})
    assert cli.probe() == 3
    out = capsys.readouterr().out
    assert "lock=HELD" in out and "job=UNSUPPORTED" in out


def _p(pid, name, exe, cmd, cwd=""):
    return {"pid": pid, "ppid": 9999, "name": name, "exe": exe, "cmd": cmd, "cwd": cwd}


def test_anchors_hit_ours_and_ignore_others():
    root = str(pg.ROOT)
    ps = [_p(1, "python.exe", root + r"\.venv\Scripts\python.exe", r".venv\Scripts\python.exe main.py"),
          _p(2, "python.exe", r"F:\anaconda3\python.exe", "-X utf8 main.py --run", root),
          _p(3, "python.exe", r"F:\anaconda3\python.exe", "-X utf8 scripts\\oc2_live.py", r"D:\\other"),
          _p(4, "opencode.exe", r"F:\npm-global\node_modules\opencode-ai\bin\opencode.exe", "opencode"),
          _p(5, "python.exe", r"D:\other\.venv\Scripts\python.exe", "main.py", r"D:\other")]
    assert {p["pid"]: a for p, a in cli.hits_of(ps)} == {1: "exe", 2: "cmd"}


def test_sweep_refuses_to_kill_unanchored_pid(monkeypatch, capsys, tmp_path):
    pg.LOCK = tmp_path / "l"
    monkeypatch.setattr(cli, "procs", lambda: [])
    monkeypatch.setattr(pg, "locked", lambda: False)
    monkeypatch.setattr(pg, "holder", lambda: {"pid": "4242", "job": "OK"})
    monkeypatch.setattr(pg, "alive", lambda pid: True)
    assert cli.sweep(expect_clean=True) == 0
    assert "拒绝 kill" in capsys.readouterr().out
