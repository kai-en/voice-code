# M13 对话流水视图：连 M11 控制台 WS，只打「你 / 助手」两方流水（直播时听不清就看这个）。
# 设计 docs/0926工作/m13-dialog-view-design.md。跑法：dialog.bat（或 python -X utf8 src\console\dialog.py）。
import asyncio
import json
import os

from websockets.asyncio.client import connect


def render(f):
    """一帧 → 一行对话；无关帧返回 None。助手行取 speak(真正进口播的整句)，不取 OcTurnDone(含未播出的内容)。"""
    if f.get("t") == "speak":
        return f"助手：{' '.join(str(f.get('text', '')).split())}"
    d = f.get("d") or {}
    if f.get("t") == "ev" and f.get("kind") in ("AsrText", "TextIn") and d.get("text"):
        return f"你：{' '.join(str(d['text']).split())}"
    return None


async def _run():
    port = os.environ.get("VOICECODE_CONSOLE_PORT", "8765")
    async with connect(f"ws://127.0.0.1:{port}/") as ws:
        async for raw in ws:
            line = render(json.loads(raw))
            if line:
                print(line, flush=True)


if __name__ == "__main__":
    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        pass
    except Exception:
        print(f"助手没起来(先 run.bat)，或端口不对：VOICECODE_CONSOLE_PORT="
              f"{os.environ.get('VOICECODE_CONSOLE_PORT', '8765')}")
