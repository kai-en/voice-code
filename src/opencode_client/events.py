# EventHub: /api/event 消费循环 —— 过滤→allowlist 翻译→回调；断线退避重连+resync 兜底。
# 一期不做 session.log 补洞（设计 §1）：重连后靠 pending 回合的 messages 轮询自愈。
from __future__ import annotations

import asyncio
import os
from typing import Callable, Optional

from .sse import SseParser
from .types import OcLink, OcPermission, OcText, OcTurnDone

EXEC_MAP = {"session.execution.succeeded": "succeeded",
            "session.execution.failed": "failed",
            "session.execution.interrupted": "interrupted"}
_EXEC_ERR = {"session.execution.failed": "execution failed",
             "session.execution.interrupted": "interrupted"}


def _same_dir(a: str, b: str) -> bool:
    return os.path.normcase(os.path.normpath(a)) == os.path.normcase(os.path.normpath(b))


class EventHub:
    def __init__(self, rest, directory: str, on_event: Callable, idle_timeout_s: float = 35.0,
                 backoff: tuple = (1.0, 2.0, 5.0, 10.0)) -> None:
        self._rest = rest
        self._dir = directory
        self._emit = on_event
        self._idle = idle_timeout_s
        self._backoff = backoff
        self.own: set[str] = set()
        self.pending: dict[str, asyncio.Future] = {}   # sid -> send() 的回合 Future
        self._cost: dict[str, float] = {}
        self._stop = asyncio.Event()
        self.frames = 0
        self._attempt = 0

    def translate(self, ev: dict) -> Optional[object]:
        loc = ev.get("location")
        if loc and not _same_dir(loc.get("directory", ""), self._dir):
            return None
        t, data = ev.get("type", ""), ev.get("data", {}) or {}
        sid = data.get("sessionID")
        if t == "session.usage.updated":
            if sid:
                self._cost[sid] = float(data.get("cost", 0.0))
            return None
        if t.startswith("server.") or t == "session.error":
            return OcLink("connected" if t == "server.connected" else t, str(data)[:120])
        if sid not in self.own:
            return None
        if t == "session.text.delta":
            return OcText(sid, data.get("delta", ""), final=False)
        if t == "session.text.ended":
            return OcText(sid, data.get("text", ""), final=True)
        if t == "permission.asked":
            return OcPermission(sid, data.get("id", ""), data.get("action", ""),
                                str(data.get("message", "")))
        if t in EXEC_MAP:
            asyncio.get_running_loop().create_task(self._finish(sid, t, data))
            return None
        return None

    async def _finish(self, sid: str, t: str, data: dict) -> None:
        fut = self.pending.pop(sid, None)
        if fut is None or fut.done():
            return
        outcome = EXEC_MAP[t]
        text, err = await self._rest.assistant_final_text(sid)
        done = OcTurnDone(sid, outcome, text, err or _EXEC_ERR.get(t),
                          self._cost.pop(sid, 0.0))
        fut.set_result(done)

    async def _pump(self) -> None:
        parser = SseParser()
        agen = self._rest.stream_event(self._idle).__aiter__()
        while not self._stop.is_set():
            chunk = await asyncio.wait_for(agen.__anext__(), self._idle + 5)
            for ev in parser.feed(chunk):
                self.frames += 1
                if ev.get("type") == "server.connected":
                    self._attempt = 0
                out = self.translate(ev)
                if out is not None:
                    self._emit(out)

    async def run(self) -> None:
        while not self._stop.is_set():
            try:
                await self._pump()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                if self._stop.is_set():
                    return
                wait = self._backoff[min(self._attempt, len(self._backoff) - 1)]
                self._attempt += 1
                self._emit(OcLink("reconnecting", f"{type(e).__name__}: {str(e)[:80]}"))
                await asyncio.sleep(wait)
                await self._resync()

    async def _resync(self) -> None:
        for sid in list(self.pending):
            try:
                items = await self._rest.messages(sid, limit=20)
            except Exception:
                continue
            if any(i.get("type") == "idle" for i in items):     # 回合已在断线期结束
                await self._finish(sid, "session.execution.succeeded", {})

    def stop(self) -> None:
        self._stop.set()
