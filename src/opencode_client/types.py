# M6 事件/配置类型 —— 契约见 docs/0925工作/m6-opencode-client-design.md §2（v2.0.16 实测）
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class OcConfig:
    bin: Path = Path("tools") / "oc2" / "node_modules" / ".bin" / "opencode2.cmd"
    home: Path = Path("tools") / "oc2-home"        # XDG 隔离根（data/config/state/cache）
    directory: str = "."                            # 语音会话工作区（location）
    model: str | None = None    # None=v2 默认(opencode 免费池, 用户拍板自带 key 方案)
    manage_serve: bool = True                       # False=attach 已有 url
    url: str | None = None
    password: str | None = None                     # manage_serve=False 时必填(若开密码)
    sse_idle_timeout_s: float = 35.0
    reconnect_backoff_s: tuple = (1.0, 2.0, 5.0, 10.0)
    turn_timeout_s: float = 180.0


@dataclass(frozen=True)
class OcText:
    session_id: str
    text: str          # final=False 时为增量 delta；final=True 时为 text.ended 全量(校准)
    final: bool = False


@dataclass(frozen=True)
class OcPermission:
    session_id: str
    request_id: str
    action: str
    message: str


@dataclass(frozen=True)
class OcTool:
    # v2.0.16 实测: 工具名只在 input.started, called 帧无 name → hub 按 callID 关联回填
    session_id: str
    call_id: str
    name: str
    phase: str                                  # started | called
    tool_input: dict | None = None


@dataclass(frozen=True)
class OcTurnDone:
    session_id: str
    outcome: str       # succeeded | failed | interrupted
    text: str          # GET messages 校准后的终稿
    error: str | None = None
    cost: float = 0.0


@dataclass(frozen=True)
class OcLink:
    state: str         # connected | reconnecting | disconnected | version_warn
    detail: str = ""
