# OpencodeClient 门面: attach(自管 serve 或外接) → session_new → send(串行回合)
#   → interrupt(barge-in) / reply_permission(无键盘闭环) → aclose。
# 惯例对齐 start_tts/start_asr: start_opencode(cfg, on_event)（协程）。
from __future__ import annotations

import asyncio
import contextlib
import time
from typing import Callable, Optional

from .events import EventHub
from .rest import OcRest
from .serve import ServeProcess
from .types import OcConfig, OcLink, OcTurnDone


class OpencodeClient:
    def __init__(self, cfg: OcConfig, rest: OcRest, hub: EventHub,
                 serve: Optional[ServeProcess],
                 task: Optional[asyncio.Task]) -> None:
        self.cfg = cfg
        self._rest = rest
        self._hub = hub
        self._serve = serve
        self._task = task

    @classmethod
    async def attach(cls, cfg: OcConfig,
                     on_event: Callable = lambda ev: None) -> "OpencodeClient":
        serve = await ServeProcess.start(cfg) if cfg.manage_serve else None
        url, pw = (serve.url, serve.password) if serve else (cfg.url, cfg.password)
        if not url:
            raise ValueError("manage_serve=False 时必须提供 cfg.url")
        rest = OcRest(url, pw)
        try:
            info = await rest.info()
            if not str(info.get("version", "")).startswith("2."):
                on_event(OcLink("version_warn", str(info.get("version"))))
        except Exception:
            await rest.aclose()
            if serve:
                await serve.stop()
            raise
        hub = EventHub(rest, cfg.directory, on_event,
                       cfg.sse_idle_timeout_s, cfg.reconnect_backoff_s)
        task = asyncio.create_task(hub.run(), name="oc-event-hub")
        return cls(cfg, rest, hub, serve, task)

    async def session_new(self, title: Optional[str] = None) -> str:
        sid = await self._rest.session_create(title or f"voice-{int(time.time())}",
                                              self.cfg.directory, self.cfg.model)
        self._hub.own.add(sid)
        return sid

    async def send(self, session_id: str, text: str) -> "asyncio.Future[OcTurnDone]":
        if session_id in self._hub.pending:
            raise RuntimeError("串行一期: 上一回合未结束，禁止并发 send")
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._hub.pending[session_id] = fut
        try:
            await self._rest.prompt(session_id, text)
        except Exception:
            self._hub.pending.pop(session_id, None)
            raise
        return fut

    async def interrupt(self, session_id: str, resume: bool = False) -> bool:
        return await self._rest.interrupt(session_id, resume)

    async def reply_permission(self, session_id: str, request_id: str,
                               decision: str) -> None:
        await self._rest.reply_permission(session_id, request_id, decision)

    async def aclose(self) -> None:
        self._hub.stop()
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        await self._rest.aclose()
        if self._serve:
            await self._serve.stop()


async def start_opencode(cfg: Optional[OcConfig] = None,
                         on_event: Optional[Callable] = None) -> OpencodeClient:
    return await OpencodeClient.attach(cfg or OcConfig(), on_event or (lambda ev: None))
