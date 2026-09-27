# M11 本地 WebSocket 文本通道：只绑 127.0.0.1 单端口；**不 serve HTML**（非升级请求由库默认回 426）。
# 入帧 ask/stop/perm/ping/hotwords(M14 手动装填)，其余（含非 JSON 裸文本）一律按 ask 兜底并回 note；出帧见 frames.py。
# 注入唯一出口 orch.post(TextIn)；出流唯一入口 tap→broadcast（同 loop 线程，禁跨线程）。设计 §3。
from __future__ import annotations

import asyncio
import json
import os

from websockets.asyncio.server import broadcast, serve
from websockets.exceptions import ConnectionClosed

from orchestrator.core import PERM, HotwordsSet, TextIn

from . import frames

DEFAULT_PORT = 8765
FORBIDDEN_PORT = 4096          # opencode serve 的默认端口（设计 E7）


class BindError(RuntimeError):
    pass


class ConsoleServer:
    def __init__(self, port=None, orch=None):
        # port=None → 环境变量 → 默认；显式传 0 = 要临时端口（不能用 falsy 判断区分）
        if port is None:
            port = os.environ.get("VOICECODE_CONSOLE_PORT") or DEFAULT_PORT
        self.port = int(port)
        self.orch, self.ready = orch, orch is not None
        self.srv, self.bound = None, None

    async def start(self, retry_s: float = 5.0):
        if self.port == FORBIDDEN_PORT:
            raise BindError(f"端口 {FORBIDDEN_PORT} 是 opencode serve 的默认端口，必须避开")
        loop = asyncio.get_running_loop()
        deadline = loop.time() + retry_s
        while True:
            try:
                self.srv = await serve(self._handler, "127.0.0.1", self.port, max_size=1 << 20,
                                       max_queue=16, write_limit=1 << 15, ping_interval=20,
                                       ping_timeout=20)
                break
            except OSError as e:
                if loop.time() >= deadline:
                    raise BindError(f"控制台端口 {self.port} 绑不上: {e!r}") from e
                await asyncio.sleep(1.0)          # 只可能是 TIME_WAIT 残留；有 LISTEN 占用者第一次就抛
        self.bound = self.srv.sockets[0].getsockname()[1]
        print(f"[m11] console ws://127.0.0.1:{self.bound}", flush=True)
        return self.bound

    async def stop(self):
        if self.srv is not None:
            self.srv.close()
            await self.srv.wait_closed()          # 优雅关：不留 TIME_WAIT（设计 §2.4）
            self.srv = None

    def attach(self, orch):
        self.orch, self.ready = orch, True

    def tap(self, kind, obj):                     # orchestrator loop 线程同步调用，不得阻塞/抛
        if self.srv is None:
            return
        f = {"ev": frames.ev_frame, "state": frames.state_frame, "speak": frames.speak_frame}[kind](obj)
        conns = self.srv.connections
        if conns:
            broadcast(conns, frames.encode(f))    # 单一定向/广播路径，不混用 await ws.send（设计 §3.4 禁令2）

    async def _handler(self, ws):
        await ws.send(frames.encode(self._hello()))
        try:
            async for msg in ws:
                if isinstance(msg, bytes):
                    msg = msg.decode("utf-8", "replace")
                note = self._dispatch(msg)
                if note:
                    await ws.send(frames.encode(note))
        except ConnectionClosed:
            pass

    def _hello(self):
        return {"t": "hello", "v": 1, "port": self.bound, "ready": self.ready,
                "state": self.orch.state if self.orch else None}

    def _dispatch(self, raw):
        if not self.ready or self.orch is None:
            return {"t": "err", "code": "not_ready"}
        try:
            f = json.loads(raw)
        except (ValueError, TypeError):
            f = None
        f = f if isinstance(f, dict) else {}
        t = f.get("t")
        if t == "ping":
            return {"t": "pong"}
        if t == "stop":
            self.orch.post(TextIn(text="", src="console"))
            return None
        if t == "perm":
            if self.orch.state != PERM:
                return {"t": "err", "code": "not_in_perm", "state": self.orch.state}
            self.orch.post(TextIn(text="允许" if str(f.get("decision")) != "reject" else "拒绝",
                                  src="console"))
            return None
        if t == "hotwords":                                # M14 手动注入兜底，须在 ask 兜底之前
            fld = f.get("words")
            if not isinstance(fld, list):
                return {"t": "err", "code": "words_required"}
            self.orch.post(HotwordsSet(words=tuple(fld)))
            return None
        fld = f.get("text")
        if t == "ask":                                  # 显式 ask 不做"整帧兜底"，空文本就是空文本
            text = fld if isinstance(fld, str) else ""
        else:
            text = fld if isinstance(fld, str) and fld.strip() else raw
        text = text or ""
        if not text.strip():
            return {"t": "err", "code": "empty_text"}
        self.orch.post(TextIn(text=text, src="console"))
        return None if t == "ask" else {"t": "note", "code": "unknown_frame_as_ask", "got": t}
