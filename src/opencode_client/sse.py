# SSE 增量解析器（纯同步、可单测）：喂字节块 → 事件 dict 列表。
# v2 帧形（T-M6-2 实测）：`data: <单行JSON>`；注释行(`: heartbeat`)忽略；跨块撕裂可容忍。
from __future__ import annotations

import json


class SseParser:
    def __init__(self) -> None:
        self._buf = b""
        self._data: list[dict] | None = None   # 当前帧内已解析出的 data 事件

    def feed(self, chunk: bytes) -> list[dict]:
        out: list[dict] = []
        self._buf += chunk
        while True:
            nl = self._buf.find(b"\n")
            if nl < 0:
                break
            line, self._buf = self._buf[:nl], self._buf[nl + 1:]
            line = line.rstrip(b"\r")
            if not line:                                # 空行 = 帧结束
                if self._data:
                    out.extend(self._data)
                    self._data = None
                continue
            if line.startswith(b"data:"):
                try:
                    ev = json.loads(line[5:].strip())
                except (ValueError, UnicodeDecodeError):
                    continue
                if self._data is None:
                    self._data = []
                self._data.append(ev)
            # ":" 开头注释(心跳)与其它字段直接丢弃
        return out

    def flush(self) -> list[dict]:
        if self._data:
            out, self._data = self._data, None
            return out
        return []
