# ServeProcess: 隔离环境 spawn `opencode2 serve --stdio`（v2 子进程协议，实测设计 §0）
#   - XDG_* 全量重定向到 cfg.home，模型 key 走独立 auth 存储
#   - OPENCODE_PASSWORD 随机生成，仅存本对象（Basic 用户名固定 opencode）
#   - stdout 首行机器可读 JSON {"url": ...}；stop()=关 stdin（官方退出协议），超时才 terminate 自记录 PID
from __future__ import annotations

import asyncio
import json
import os
import secrets
import sys
from pathlib import Path

from .types import OcConfig

NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def isolated_env(cfg: OcConfig, password: str) -> dict:
    env = os.environ.copy()
    home = Path(cfg.home).resolve()   # 必须绝对化: 子进程 cwd=directory, 相对 XDG 会被错位解析
    env.update(
        XDG_DATA_HOME=str(home / "data"),
        XDG_CONFIG_HOME=str(home / "config"),
        XDG_STATE_HOME=str(home / "state"),
        XDG_CACHE_HOME=str(home / "cache"),
        OPENCODE_PASSWORD=password,
    )
    return env


def parse_ready(line: str) -> str:
    return json.loads(line)["url"]


class ServeProcess:
    def __init__(self, proc: asyncio.subprocess.Process, url: str, password: str) -> None:
        self.proc = proc
        self.url = url
        self.password = password

    @property
    def pid(self) -> int:
        return self.proc.pid

    @property
    def alive(self) -> bool:
        return self.proc.returncode is None

    @classmethod
    async def start(cls, cfg: OcConfig, ready_timeout_s: float = 60.0) -> "ServeProcess":
        pw = secrets.token_urlsafe(16)
        proc = await asyncio.create_subprocess_exec(
            str(Path(cfg.bin).resolve()), "serve", "--stdio",
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=None, env=isolated_env(cfg, pw), cwd=str(Path(cfg.directory).resolve()),
            creationflags=NO_WINDOW)
        try:
            line = await asyncio.wait_for(proc.stdout.readline(), ready_timeout_s)
            url = parse_ready(line.decode("utf-8"))
        except Exception:
            proc.terminate()          # 仅自记录 PID（AGENTS kill 纪律）
            raise
        return cls(proc, url, pw)

    async def stop(self, grace_s: float = 8.0) -> None:
        if not self.alive:
            return
        try:
            self.proc.stdin.close()   # 官方协议：stdin 关闭 → server 退出
            await asyncio.wait_for(self.proc.wait(), grace_s)
        except Exception:
            self.proc.terminate()
            await self.proc.wait()
