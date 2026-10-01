# M13 对话流水视图：连 M11 控制台 WS，只打「你 / 助手」两方流水（直播时听不清就看这个）。
# 设计 docs/0926工作/m13-dialog-view-design.md。跑法：dialog.bat（或 python -X utf8 src\console\dialog.py）。
# RUNNING 期间占位行「思考中...(x秒)」原地刷新(\r)，每 TICK_S 一次；出现真实对话行或离开 RUNNING 时收行。
# voice-end 工具被调后状态进 IDLE → 补一行「(助手已退出)」；中途回 COLLECT（被抢话打断）清标记；hello 不算。
import asyncio
import json
import os
import sys
import time

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

TICK_S = 30.0


def render(f):
    """一帧 → 一行对话；无关帧返回 None。助手行取 speak(真正进口播的整句)，不取 OcTurnDone(含未播出的内容)。"""
    if f.get("t") == "speak":
        return f"助手：{' '.join(str(f.get('text', '')).split())}"
    d = f.get("d") or {}
    if f.get("t") == "ev" and f.get("kind") in ("AsrText", "TextIn") and d.get("text"):
        return f"你：{' '.join(str(d['text']).split())}"
    return None


def think_line(elapsed_s):
    return f"助手：思考中...({int(elapsed_s)}秒)"


def _is_running(f):
    return f.get("t") in ("state", "hello") and f.get("state") == "RUNNING"


def _is_voice_end_called(f):
    d = f.get("d") or {}
    return (f.get("t") == "ev" and f.get("kind") == "OcTool"
            and d.get("name") == "voice-end" and d.get("phase") == "called")


async def _run():
    port = os.environ.get("VOICECODE_CONSOLE_PORT", "8765")
    t0 = None                                          # RUNNING 起点(monotonic)；非 None = 占位行驻留行尾
    next_draw = 0.0                                    # 绝对时刻：帧帧不断也会准点刷新(0930 修:计时曾被来帧重置)
    voice_end = False                                  # 看到 voice-end/called → 随后的进 IDLE 才配「已退出」
    async with connect(f"ws://127.0.0.1:{port}/") as ws:
        recv = asyncio.ensure_future(ws.recv())
        while True:
            timeout = None if t0 is None else max(0.0, next_draw - time.monotonic())
            done, _ = await asyncio.wait({recv}, timeout=timeout)
            if not done:
                sys.stdout.write("\r" + think_line(time.monotonic() - t0))
                sys.stdout.flush()
                next_draw = time.monotonic() + TICK_S
                continue
            try:
                raw = recv.result()
            except ConnectionClosed:
                break
            recv = asyncio.ensure_future(ws.recv())
            f = json.loads(raw)
            if _is_running(f):
                t0 = time.monotonic()
                next_draw = t0 + TICK_S
                sys.stdout.write("\r" + think_line(0.0))
                sys.stdout.flush()
                continue
            if t0 is not None and (render(f) or f.get("t") == "state"):
                sys.stdout.write("\n")                 # 收掉占位行，后续行正常入历史
                sys.stdout.flush()
                t0 = None
            line = render(f)
            if _is_voice_end_called(f):
                voice_end = True
            elif f.get("t") == "state":
                if f.get("state") == "IDLE" and voice_end:
                    voice_end = False
                    print("(助手已退出)", flush=True)   # 告别语已由 speak 帧先行入列
                elif f.get("state") == "COLLECT":
                    voice_end = False                   # voice-end 被抢话作废，会话继续
            if line:
                print(line, flush=True)
        recv.cancel()


if __name__ == "__main__":
    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        pass
    except Exception:
        print(f"助手没起来(先 run.bat)，或端口不对：VOICECODE_CONSOLE_PORT="
              f"{os.environ.get('VOICECODE_CONSOLE_PORT', '8765')}")
