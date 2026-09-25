# M1 音频采集 (v2) —— 设计文档: docs/0923工作/audio-capture-design.md
# 自研仅 3 样: DropOldestQueue 扇出(W1)、StallWatchdog 周期报警(W2)、事件(W3)。
from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable, Optional, Protocol, runtime_checkable


@runtime_checkable
class MicLike(Protocol):
    @property
    def running(self) -> bool: ...
    last_cb: float
    last_nonzero: float

import numpy as np

SR = 16000
FRAME_MS = 20
BLOCK = int(SR * FRAME_MS / 1000)


def _import_sd():
    import sounddevice as sd
    return sd


class NoInputDeviceError(RuntimeError):
    pass


class DeviceNotFoundError(RuntimeError):
    pass


class DropOldestQueue:
    """W1: 有界帧队列，满则丢最旧（语音新鲜度优先）。"""

    def __init__(self, maxlen: int):
        self._d: deque = deque(maxlen=maxlen)
        self._cv = threading.Condition()
        self.maxlen = maxlen
        self.dropped = 0

    def put(self, item) -> None:
        with self._cv:
            if len(self._d) == self.maxlen:
                self.dropped += 1
            self._d.append(item)
            self._cv.notify()

    def get(self, timeout: Optional[float] = None):
        with self._cv:
            if not self._d and timeout:
                self._cv.wait(timeout)
            return self._d.popleft() if self._d else None

    def qsize(self) -> int:
        with self._cv:
            return len(self._d)

    def clear(self) -> None:
        with self._cv:
            self._d.clear()


def resolve_device(name: Optional[str] = None):
    """按子串(不区分大小写)匹配输入设备；name=None 时取系统默认输入。

    返回 (index, device_name, is_hand_free)。
    """
    sd = _import_sd()
    devs = sd.query_devices()
    inputs = [(i, d) for i, d in enumerate(devs) if d["max_input_channels"] > 0]
    if not inputs:
        raise NoInputDeviceError("no input device available")
    if name:
        s = name.strip()
        if s.isdigit():  # 纯数字 = 设备索引
            hits = [(i, d) for i, d in inputs if i == int(s)]
            if not hits:
                raise DeviceNotFoundError(f"input index {s}")
        else:
            hits = [(i, d) for i, d in inputs if s.lower() in d["name"].lower()]
            if not hits:
                raise DeviceNotFoundError(name)
    else:
        default_idx = sd.default.device[0]
        hits = [(i, d) for i, d in inputs if i == default_idx] or inputs
    i, d = hits[0]
    return i, d["name"], "hands-free" in d["name"].lower()


class MicSource:
    """单麦克风 → 有界队列扇出。非焦点：不创建任何窗口，异常不外抛。

    生命周期：__init__ → start() → [回调线程持续 put] → stop()。
    不做热插拔自动恢复（决议1）：停摆由 StallWatchdog 检出 → 周期语音报警。
    """

    def __init__(
        self,
        device_name: Optional[str] = None,
        sink_names: tuple = ("kws", "vad"),
        sink_len: int = 250,  # 250 × 20ms = 5s
        clock: Callable[[], float] = time.monotonic,
    ):
        self.sinks = {n: DropOldestQueue(sink_len) for n in sink_names}
        self.clock = clock
        self.last_cb = 0.0
        self.last_nonzero = 0.0
        self.cb_count = 0
        self.status_count = 0
        self.err_count = 0
        self.consec_err = 0
        self.device_index: Optional[int] = None
        self.device_name_resolved: Optional[str] = None
        self.is_hand_free = False
        self._spec = device_name
        self._stream = None

    def start(self):
        sd = _import_sd()
        idx, name, hf = resolve_device(self._spec)
        self.device_index, self.device_name_resolved, self.is_hand_free = idx, name, hf
        self._stream = sd.InputStream(
            samplerate=SR, channels=1, dtype="float32",
            device=idx, blocksize=BLOCK, callback=self._cb,
        )
        now = self.clock()
        self.last_cb = now
        self.last_nonzero = now
        self._stream.start()

    def _cb(self, indata, frames, t, status):
        # 铁律：任何异常不得逃逸（否则 PortAudio 停流）。
        now = self.clock()
        self.last_cb = now
        self.cb_count += 1
        if status:
            self.status_count += 1
        try:
            arr = np.asarray(indata, dtype=np.float32)
            frame = (arr[:, 0] if arr.ndim > 1 else arr.reshape(-1)).copy()
            if frame.size and np.abs(frame).max() > 0.0:
                self.last_nonzero = now
            for q in self.sinks.values():
                q.put(frame)
            self.consec_err = 0
        except Exception:
            self.err_count += 1
            self.consec_err += 1

    @property
    def running(self) -> bool:
        return self._stream is not None and self._stream.active

    def stop(self):
        s, self._stream = self._stream, None
        if s is not None:
            try:
                s.stop()
                s.close()
            except Exception:
                pass

    def stats(self) -> dict:
        return {
            "cb": self.cb_count,
            "status": self.status_count,
            "err": self.err_count,
            "dropped": {n: q.dropped for n, q in self.sinks.items()},
            "device": self.device_name_resolved,
            "hands_free": self.is_hand_free,
        }


@dataclass(frozen=True)
class WatchdogConfig:
    stall_timeout_s: float = 2.0
    zero_timeout_s: float = 5.0
    alert_interval_s: float = 60.0
    startup_grace_s: float = 3.0


@dataclass(frozen=True)
class CaptureDead:
    ts: float
    reason: str


@dataclass(frozen=True)
class AlertTick:
    ts: float


class StallWatchdog:
    """W2: 停摆检测 + 周期语音报警（替代热插拔自动重连）。

    由 M5 以 ~1Hz 调用 check(now)；ALERTED 后进程内不自动恢复（人工重启）。
    """

    def __init__(
        self,
        mic: MicLike,
        cfg: WatchdogConfig = WatchdogConfig(),
        clock: Callable[[], float] = time.monotonic,
        started_at: Optional[float] = None,
    ):
        self.mic = mic
        self.cfg = cfg
        self.clock = clock
        self.state = "ARMED"
        self.started_at = clock() if started_at is None else started_at
        self._last_alert: Optional[float] = None

    def _dead_reason(self, now: float) -> Optional[str]:
        m = self.mic
        if not m.running:
            return "stream dead"
        if now - m.last_cb > self.cfg.stall_timeout_s:
            return "callback stall"
        if now - m.last_nonzero > self.cfg.zero_timeout_s:
            return "no signal (digital silence)"
        return None

    def check(self, now: Optional[float] = None) -> list:
        if now is None:
            now = self.clock()
        if self.state == "ARMED":
            if now - self.started_at < self.cfg.startup_grace_s:
                return []
            reason = self._dead_reason(now)
            if reason:
                self.state = "ALERTED"
                self._last_alert = now
                return [CaptureDead(now, reason), AlertTick(now)]
            return []
        if self._last_alert is not None and now - self._last_alert >= self.cfg.alert_interval_s:
            self._last_alert = now
            return [AlertTick(now)]
        return []
