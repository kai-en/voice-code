# M11 人工验收 H4′：本地 WS 控制台双向帧（替代"浏览器打字"——本期没有网页）。
# 跑法（两个窗口）：
#   1) .\run.bat                                  # 起助手（winTTS 口播 + opencode serve）
#   2) .\.venv\Scripts\python.exe -X utf8 human-test\m11_t8_ws-console.py
# 你要确认的三件事：
#   A. 打字回车 → 耳朵听到口播、屏幕看到 ev/speak/state 帧流，且因果顺序是 ev(OcTurnDone) 之后才 state:COLLECT
#   B. 手打 {"t":"stop"} 回车 → 播报立刻停；手打 {"t":"ping"} → 回 pong
#   C. 助手说话期间你对麦克风喊「小码小码」→ 语音链路照常工作（打字与语音共存，不分模式）
# 裸文本 = ask（协议兜底）；以 { 开头的行按原样当 JSON 帧发出。
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from websockets.asyncio.client import connect     # noqa: E402

PORT = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("VOICECODE_CONSOLE_PORT", "8765")
URL = f"ws://127.0.0.1:{PORT}/"


async def printer(ws):
    async for raw in ws:
        try:
            f = json.loads(raw)
        except ValueError:
            print(f"<< 非 JSON 帧: {raw[:120]}", flush=True)
            continue
        t = f.get("t")
        if t == "ev":
            d = f.get("d") or {}
            brief = d.get("text") or d.get("outcome") or d.get("name") or d.get("state") or ""
            print(f"  ev  {f.get('kind'):<12} {str(brief)[:60]}", flush=True)
        elif t == "speak":
            print(f" >> speak          {f.get('text')}", flush=True)
        elif t == "state":
            print(f"    state -> {f.get('state')}", flush=True)
        else:
            print(f"    {t} {raw[:100]}", flush=True)


async def inputter(ws):
    loop = asyncio.get_running_loop()
    while True:
        line = await loop.run_in_executor(None, sys.stdin.readline)
        if not line:
            return
        line = line.strip()
        if not line:
            continue
        if line == "/quit":
            return
        await ws.send(line)
        print(f"[sent] {line[:80]}", flush=True)


async def main():
    print(f"连接 {URL} （Ctrl-C 退出；/quit 亦可）", flush=True)
    async with connect(URL) as ws:
        p, i = asyncio.create_task(printer(ws)), asyncio.create_task(inputter(ws))
        await asyncio.wait({p, i}, return_when=asyncio.FIRST_COMPLETED)
        for t in (p, i):
            t.cancel()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
