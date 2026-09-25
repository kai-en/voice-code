"""M6 T-M6-2 事件抓包: 隔离 v2 server(tools/oc2) 真 prompt + interrupt 回合 → 落盘帧序列+摘要。
前置: tools/oc2 已 npm 安装; tools/oc2-home/{data,config} 已配 auth.json(key)与 opencode.json(model)。
产物(单测 fixture): tests/fixtures/m6_v2016_frames_turn1.jsonl / _turn2.jsonl, m6_v2016_msgs_turn1.json, 摘要打印。
人审点: 对照 m6-opencode-client-design.md §2 allowlist, 若词表/字段有出入 → 修订设计文档再编码。
"""
import base64
import json
import os
import secrets
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OC2 = ROOT / "tools" / "oc2"
HOME = ROOT / "tools" / "oc2-home"
WS = HOME / "ws"
FIX = ROOT / "tests" / "fixtures"
PW = secrets.token_urlsafe(16)


def env_isolated():
    env = dict(os.environ)
    env.update(XDG_DATA_HOME=str(HOME / "data"), XDG_CONFIG_HOME=str(HOME / "config"),
               XDG_STATE_HOME=str(HOME / "state"), XDG_CACHE_HOME=str(HOME / "cache"),
               OPENCODE_PASSWORD=PW)
    return env


def req(url, method="GET", body=None):
    r = urllib.request.Request(url, method=method,
                               data=json.dumps(body).encode() if body is not None else None,
                               headers={"Authorization": "Basic " + base64.b64encode(
                                   f"opencode:{PW}".encode()).decode(),
                                   "Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(r, timeout=30).read() or b"{}")


def main():
    WS.mkdir(parents=True, exist_ok=True)
    FIX.mkdir(parents=True, exist_ok=True)
    bin_cmd = str(OC2 / "node_modules" / ".bin" / "opencode2.cmd")
    p = subprocess.Popen([bin_cmd, "serve", "--stdio"], stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, env=env_isolated(), cwd=str(WS))
    stop = threading.Event()

    try:
        url = json.loads(p.stdout.readline().decode())["url"]
        print("[m6cap] serve url:", url)
        print("[m6cap] /api/info:", req(url + "/api/info").get("version"))
        sid = req(url + "/api/session", "POST",
                  {"title": "m6-capture", "location": {"directory": str(WS)}})["data"]["id"]
        print("[m6cap] session:", sid)

        box = capture_frames(url, stop, 200)
        # 回合1: 普通回复
        req(url + f"/api/session/{sid}/prompt", "POST",
            {"text": "请只回复两个字：收到。不要调用任何工具。"})
        turn_done = wait_until(stop, box, ("session.execution.succeeded",
                                           "session.execution.failed"), 120)
        dump(1, box, sid, url)
        # 回合2: 长输出 + 10s 后 interrupt
        box2 = capture_frames(url, stop, 200)
        req(url + f"/api/session/{sid}/prompt", "POST",
            {"text": "请写一篇约500字的说明文，主题是语音助手在游戏中的价值，直接输出正文。"})
        time.sleep(10)
        print("[m6cap] interrupt ->", req(url + f"/api/session/{sid}/interrupt?resume=false", "POST"))
        wait_until(stop, box2, ("session.execution.interrupted",
                                "session.execution.succeeded",
                                "session.execution.failed"), 60)
        time.sleep(1)
        dump(2, box2, sid, url)
        print("\n[m6cap] 词表统计:")
        for n, b in ((1, box), (2, box2)):
            types = {}
            for raw in b:
                try:
                    ev = json.loads(raw.split("data:", 1)[1].strip())
                    types[ev.get("type")] = types.get(ev.get("type"), 0) + 1
                except Exception:
                    types["<non-json/comment>"] = types.get("<non-json/comment>", 0) + 1
            print(f"  turn{n}: 帧数={len(b)}", json.dumps(types, ensure_ascii=False))
        print("请人审: 与设计 §2 allowlist 对照, fixture 已存 tests/fixtures/")
    finally:
        stop.set()
        try:
            p.stdin.close(); p.wait(timeout=8)
        except Exception:
            p.terminate()


_frames_lock = threading.Lock()


def capture_frames(url, stop, life):
    box = []

    def sub():
        r = None
        try:
            r = urllib.request.urlopen(urllib.request.Request(
                url + "/api/event", headers={"Authorization": "Basic " + base64.b64encode(
                    f"opencode:{PW}".encode()).decode()}), timeout=15)
            cur = []
            t0 = time.time()
            for line in r:
                if stop.is_set() or time.time() - t0 > life:
                    break
                line = line.decode("utf-8").rstrip("\r\n")
                if line == "":
                    if cur:
                        with _frames_lock:
                            box.append("\n".join(cur))
                        cur = []
                    continue
                cur.append(line)
        except Exception as e:
            print("[m6cap] SSE err:", str(e)[:80])
        finally:
            if r:
                r.close()
    threading.Thread(target=sub, daemon=True).start()
    return box


def wait_until(stop, box, types, sec):
    t0 = time.time()
    while time.time() - t0 < sec:
        for raw in list(box):
            try:
                if json.loads(raw.split("data:", 1)[1].strip()).get("type") in types:
                    return True
            except Exception:
                pass
        time.sleep(0.2)
    return False


def dump(n, box, sid, url):
    with _frames_lock:
        (FIX / f"m6_v2016_frames_turn{n}.jsonl").write_text(
            "\n\n".join(box) + "\n\n", encoding="utf-8")
    try:
        msgs = req(url + f"/api/session/{sid}/message?limit=100", "GET")
        (FIX / f"m6_v2016_msgs_turn{n}.json").write_text(
            json.dumps(msgs, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception as e:
        print("[m6cap] messages dump fail:", str(e)[:80])


if __name__ == "__main__":
    raise SystemExit(main())
