# M1 单元测试（对应 audio-capture-design.md §5.1，无音频设备可跑）
import types

import numpy as np
import pytest

from audio_capture import capture as cap
from audio_capture.capture import (
    BLOCK,
    AlertTick,
    CaptureDead,
    DeviceNotFoundError,
    DropOldestQueue,
    MicSource,
    NoInputDeviceError,
    StallWatchdog,
    WatchdogConfig,
    device_line,
    resolve_device,
)


def _ones():
    return np.ones((BLOCK, 1), dtype=np.float32)


def _zeros():
    return np.zeros((BLOCK, 1), dtype=np.float32)


# ---------- W1: DropOldestQueue ----------

def test_drop_oldest_queue_drops_oldest_and_counts():
    q = DropOldestQueue(maxlen=2)
    q.put(np.array([1.0], dtype=np.float32))
    q.put(np.array([2.0], dtype=np.float32))
    q.put(np.array([3.0], dtype=np.float32))
    assert q.dropped == 1
    assert q.qsize() == 2
    a, b = q.get(), q.get()
    assert a is not None and b is not None
    assert float(a[0]) == 2.0 and float(b[0]) == 3.0


def test_drop_oldest_queue_get_timeout_returns_none():
    q = DropOldestQueue(maxlen=2)
    assert q.get(timeout=0.01) is None


def test_drop_oldest_queue_clear():
    q = DropOldestQueue(maxlen=4)
    q.put(_ones())
    q.clear()
    assert q.qsize() == 0


# ---------- MicSource._cb（直调，不开真流） ----------

def _make_mic(**kw):
    t = {"now": 100.0}
    kw.setdefault("clock", lambda: t["now"])
    return MicSource(**kw), t


def test_cb_fans_out_equal_frames():
    m, _ = _make_mic()
    m._cb(_ones(), BLOCK, None, None)
    m._cb(_zeros(), BLOCK, None, None)
    assert m.sinks["kws"].qsize() == 2
    assert m.sinks["vad"].qsize() == 2
    assert m.cb_count == 2
    f = m.sinks["kws"].get()
    assert f is not None
    assert f.shape == (BLOCK,) and f.dtype == np.float32


def test_cb_status_counted_not_fatal():
    m, _ = _make_mic()
    m._cb(_ones(), BLOCK, None, ["input overflow"])
    assert m.status_count == 1
    assert m.sinks["kws"].qsize() == 1


def test_cb_overflow_drops_oldest():
    m, _ = _make_mic(sink_len=2)
    for v in (1.0, 2.0, 3.0):
        m._cb(np.full((BLOCK, 1), v, dtype=np.float32), BLOCK, None, None)
    assert m.sinks["kws"].dropped == 1
    f = m.sinks["kws"].get()
    assert f is not None and float(f[0]) == 2.0


def test_cb_tracks_nonzero_and_stall_heartbeat():
    m, t = _make_mic()
    m._cb(_ones(), BLOCK, None, None)
    t0 = m.last_nonzero
    t["now"] = t0 + 5.0
    m._cb(_zeros(), BLOCK, None, None)
    assert m.last_nonzero == t0  # 全零帧不推进死寂时钟
    assert m.last_cb == t0 + 5.0  # 但心跳照常


def test_cb_never_raises():
    m, _ = _make_mic()
    m._cb(["坏数据"] * BLOCK, BLOCK, None, None)  # asarray 转换失败
    assert m.err_count == 1 and m.consec_err == 1


# ---------- resolve_device（假 sd 模块） ----------

def _fake_sd(devs, default_idx=-1):
    return types.SimpleNamespace(
        query_devices=lambda: devs,
        default=types.SimpleNamespace(device=(default_idx, -1)),
    )


def test_resolve_default_device():
    monkey_sd = _fake_sd([
        {"name": "HDA 扬声器", "max_input_channels": 0},
        {"name": "麦克风 (Realtek Audio)", "max_input_channels": 2},
    ], default_idx=1)
    monkeypatch_holder = cap.__dict__["_import_sd"]
    cap.__dict__["_import_sd"] = lambda: monkey_sd
    try:
        idx, name = resolve_device(None)
        assert idx == 1 and "Realtek" in name
    finally:
        cap.__dict__["_import_sd"] = monkeypatch_holder


def test_resolve_by_substring_case_insensitive_chinese():
    devs = [{"name": "耳机麦 (Jabra Evolve2 65)", "max_input_channels": 1}]
    monkey_sd = _fake_sd(devs)
    orig = cap.__dict__["_import_sd"]
    cap.__dict__["_import_sd"] = lambda: monkey_sd
    try:
        idx, name = resolve_device("evolve2")
        assert idx == 0 and name == devs[0]["name"]
    finally:
        cap.__dict__["_import_sd"] = orig


def test_resolve_by_index():
    devs = [
        {"name": "Speakers", "max_input_channels": 0},
        {"name": "麦克风 (5- Realtek High Definition", "max_input_channels": 2},
    ]
    orig = cap.__dict__["_import_sd"]
    cap.__dict__["_import_sd"] = lambda: _fake_sd(devs)
    try:
        idx, name = resolve_device("1")
        assert idx == 1 and name == devs[1]["name"]
        try:
            resolve_device("9")
            assert False, "index out of range should raise"
        except DeviceNotFoundError:
            pass
    finally:
        cap.__dict__["_import_sd"] = orig


def test_resolve_not_found_and_no_input():
    orig = cap.__dict__["_import_sd"]
    cap.__dict__["_import_sd"] = lambda: _fake_sd(
        [{"name": "Speakers", "max_input_channels": 0}]
    )
    try:
        with pytest.raises(NoInputDeviceError):
            resolve_device(None)
        cap.__dict__["_import_sd"] = lambda: _fake_sd(
            [{"name": "Mic A", "max_input_channels": 1}]
        )
        with pytest.raises(DeviceNotFoundError):
            resolve_device("NoSuchMic")
    finally:
        cap.__dict__["_import_sd"] = orig


# ---------- W2: StallWatchdog ----------

class FakeMic:
    def __init__(self, now):
        self.running = True
        self.last_cb = now
        self.last_nonzero = now


CFG = WatchdogConfig(
    stall_timeout_s=2.0, zero_timeout_s=5.0,
    alert_interval_s=60.0, startup_grace_s=3.0,
)


def test_watchdog_grace_then_stall_alert():
    mic = FakeMic(0.0)
    w = StallWatchdog(mic, CFG, clock=lambda: 0.0, started_at=0.0)
    assert w.check(2.0) == []          # 宽限期内
    evts = w.check(4.0)                # last_cb=0 → stall>2s
    assert isinstance(evts[0], CaptureDead) and evts[0].reason == "callback stall"
    assert isinstance(evts[1], AlertTick)
    assert w.check(50.0) == []         # 间隔未到
    evts = w.check(64.0)               # 首个 AlertTick@4 + 60
    assert len(evts) == 1 and isinstance(evts[0], AlertTick)
    assert isinstance(w.check(124.0)[0], AlertTick)  # 持续循环播报


def test_watchdog_zero_signal_reason():
    mic = FakeMic(0.0)
    mic.last_cb = 10.0                 # 心跳正常
    mic.last_nonzero = 3.0             # 死寂 >5s
    w = StallWatchdog(mic, CFG, clock=lambda: 0.0, started_at=0.0)
    evts = w.check(10.0)
    assert evts[0].reason == "no signal (digital silence)"


def test_watchdog_stream_dead():
    mic = FakeMic(0.0)
    mic.running = False
    w = StallWatchdog(mic, CFG, clock=lambda: 0.0, started_at=0.0)
    assert w.check(4.0)[0].reason == "stream dead"


def test_watchdog_healthy_stays_armed():
    mic = FakeMic(0.0)
    w = StallWatchdog(mic, CFG, clock=lambda: 0.0, started_at=0.0)
    for now in (4.0, 8.0, 12.0):
        mic.last_cb = now
        mic.last_nonzero = now
        assert w.check(now) == []
    assert w.state == "ARMED"


def test_device_line_reports_mic_and_speaker():
    devs = [{"name": "回音消除话筒 (Jabra SPEAK 410 USB)", "max_input_channels": 1, "max_output_channels": 0},
            {"name": "扬声器 (Realtek)", "max_input_channels": 0, "max_output_channels": 2}]
    fake = types.SimpleNamespace(
        query_devices=lambda idx=None: devs if idx is None else devs[idx],
        default=types.SimpleNamespace(device=(0, 1)))
    orig = cap.__dict__["_import_sd"]
    cap.__dict__["_import_sd"] = lambda: fake
    try:
        mic = types.SimpleNamespace(device_index=0, device_name_resolved="回音消除话筒 (Jabra SPEAK 410 USB)")
        assert device_line(mic) == ("mic=#0 回音消除话筒 (Jabra SPEAK 410 USB) | speaker=#1 扬声器 (Realtek)")
    finally:
        cap.__dict__["_import_sd"] = orig
