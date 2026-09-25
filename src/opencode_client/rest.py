# v2 REST 薄封装（httpx.AsyncClient + Basic("opencode", pw)）。端点与语义 = 设计 §2（T-M6-2 实测）。
from __future__ import annotations

from typing import AsyncIterator, Optional

import httpx


class OcRest:
    def __init__(self, base_url: str, password: Optional[str],
                 client: Optional[httpx.AsyncClient] = None) -> None:
        auth = ("opencode", password) if password else None
        self._c = client or httpx.AsyncClient(base_url=base_url, auth=auth, timeout=30.0)

    async def info(self) -> dict:
        r = await self._c.get("/api/info")
        r.raise_for_status()
        return r.json()

    async def session_create(self, title: str, directory: str,
                             model: Optional[str] = None) -> str:
        body: dict = {"title": title, "location": {"directory": directory}}
        if model:
            pid, _, mid = model.partition("/")
            body["model"] = {"providerID": pid, "id": mid}   # v2.0.16 实测键名 id
        r = await self._c.post("/api/session", json=body)
        r.raise_for_status()
        return r.json()["data"]["id"]

    async def prompt(self, sid: str, text: str) -> None:
        r = await self._c.post(f"/api/session/{sid}/prompt", json={"text": text})
        r.raise_for_status()          # 200=已受理入队; 409 由上层处理

    async def interrupt(self, sid: str, resume: bool = False) -> bool:
        r = await self._c.post(f"/api/session/{sid}/interrupt",
                               params={"resume": str(resume).lower()})
        r.raise_for_status()
        return bool(r.json().get("interrupted"))

    async def reply_permission(self, sid: str, rid: str, decision: str) -> None:
        r = await self._c.post(f"/api/session/{sid}/permission/{rid}/reply",
                               json={"decision": decision})
        r.raise_for_status()

    async def messages(self, sid: str, limit: int = 200) -> list[dict]:
        r = await self._c.get(f"/api/session/{sid}/message", params={"limit": limit})
        r.raise_for_status()
        body = r.json()
        if isinstance(body, dict):
            return body.get("items") or body.get("data") or []
        return body or []

    async def assistant_final_text(self, sid: str) -> tuple[str, Optional[str]]:
        """终稿校准：最后一条 assistant 消息 → (text, error|None)。"""
        err = None
        for item in reversed(await self.messages(sid)):   # 倒序取最后一条非空 text（多 step 回合末条可能只有 tool part）
            if item.get("type") != "assistant":
                continue
            parts = item.get("content") or []
            text = "".join(p.get("text", "") for p in parts if p.get("type") == "text")
            if isinstance(item.get("error"), dict):
                err = err or item["error"].get("message")
            if text:
                return text, err
        return "", err

    async def stream_event(self, idle_timeout: float) -> AsyncIterator[bytes]:
        async with self._c.stream("GET", "/api/event",
                                  timeout=httpx.Timeout(5.0, read=idle_timeout)) as r:
            r.raise_for_status()
            async for chunk in r.aiter_bytes():
                yield chunk

    async def aclose(self) -> None:
        await self._c.aclose()
