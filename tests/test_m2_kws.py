# M2 KWS 单元测试（无麦/无模型；用 FakeSpotter 验证消费/去抖/mute/reset 契约）
import queue
import time

import numpy as np

from audio_capture.capture import DropOldestQueue
from kws.kws_wake import KwsConfig, KwsHit, KwsWorker

SR = 16000
BLOCK = int(0.02 * SR)


def _frame(v=0.1):
    return np.full(BLOCK, v, dtype=np.float32)


class FakeStream:
    def __init__(self):
        self.accepted = []          # [(sample_count,)]
        self.reset_count = 0

    def accept_waveform(self, rate, samples):
        assert rate == SR
        self.accepted.append(len(samples))


class FakeSpotter:
    """脚本化 is_ready/get_result：每次 decode 产出一个预设结果序列。"""

    def __init__(self, results):
        self.results = list(results)
        self.stream = FakeStream()
        self.decode_calls = 0
        self.reset_count = 0

    def create_stream(self):
        return self.stream

    def is_ready(self, stream):
        return len(self.results) > 0

    def decode_stream(self, stream):
        self.decode_calls += 1

    def get_result(self, stream):
        return self.results.pop(0)

    def reset_stream(self, stream):
        self.reset_count += 1
        stream.reset_count += 1


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += dt


def _drain_to(worker, sink, nframes=20):
    """灌 nframes 帧让 worker 至少消费一批，再等 stop。"""
    for _ in range(nframes):
        sink.put(_frame())


def test_hit_emits_kwhit_after_reset():
    sink = DropOldestQueue(250)
    sp = FakeSpotter(["小码小码"])
    hits = queue.Queue()
    clk = Clock()
    w = KwsWorker(sp, sink, hits.put, KwsConfig(cooldown_s=0.0), clock=clk)
    _drain_to(w, sink, 20)
    w.start()
    evt = hits.get(timeout=2.0)
    w.stop()
    assert isinstance(evt, KwsHit) and evt.keyword == "小码小码"
    assert sp.reset_count >= 1           # 命中即 reset
    assert w.hit_count == 1


def test_batch_caps_at_8_frames():
    sink = DropOldestQueue(250)
    sp = FakeSpotter([])                  # 永不命中，只观察拼接
    w = KwsWorker(sp, sink, lambda h: None, KwsConfig(), clock=Clock())
    for _ in range(40):
        sink.put(_frame())
    w.start()
    time.sleep(0.4)
    w.stop()
    assert sp.stream.accepted, "应至少 accept 一次"
    assert max(sp.stream.accepted) <= 8 * BLOCK   # ≤8 帧=160ms
    assert sum(sp.stream.accepted) == 40 * BLOCK   # 全部样本被消费, 无丢失


def test_cooldown_suppresses_second_hit():
    sink = DropOldestQueue(250)
    sp = FakeSpotter(["A", "B", "C", "D"])  # 四个连续结果
    hits = queue.Queue()
    clk = Clock()
    w = KwsWorker(sp, sink, hits.put, KwsConfig(cooldown_s=2.0), clock=clk)
    _drain_to(w, sink, 20)
    w.start()
    first = hits.get(timeout=2.0)
    time.sleep(0.3)                        # 时钟不推进 → 后续全在冷却内
    w.stop()
    assert first.keyword == "A"
    assert w.hit_count == 1 and w.dropped_count >= 1


def test_cooldown_expiry_emits_again():
    sink = DropOldestQueue(250)
    sp = FakeSpotter(["A"])
    hits = queue.Queue()
    clk = Clock()
    w = KwsWorker(sp, sink, hits.put, KwsConfig(cooldown_s=1.0), clock=clk)
    _drain_to(w, sink, 10)
    w.start()
    assert hits.get(timeout=2.0).keyword == "A"
    clk.advance(2.0)                       # 越过冷却
    sp.results.append("B")                 # 第二批数据驱动第二个命中
    _drain_to(w, sink, 10)
    assert hits.get(timeout=2.0).keyword == "B"
    w.stop()


def test_muted_drops_hit_and_unmute_clears():
    sink = DropOldestQueue(250)
    sp = FakeSpotter(["X"])
    hits = queue.Queue()
    w = KwsWorker(sp, sink, hits.put, KwsConfig(cooldown_s=0.0), clock=Clock())
    w.set_muted(True)
    _drain_to(w, sink, 10)
    w.start()
    time.sleep(0.3)
    w.stop()
    assert hits.empty() and w.dropped_count >= 1   # muted 期间命中被丢

    sink.put(_frame())
    w.set_muted(False)
    assert sink.qsize() == 0               # unmute 清空积压
    # reset 在构造 unmute 时多调用一次
    assert sp.reset_count >= 2


def test_stop_responsiveness():
    sink = DropOldestQueue(250)
    sp = FakeSpotter([])
    w = KwsWorker(sp, sink, lambda h: None, KwsConfig(), clock=Clock())
    w.start()
    t0 = time.monotonic()
    w.stop()
    assert time.monotonic() - t0 < 0.3     # get timeout=0.1 保证及时退出


def test_exception_does_not_kill_thread():
    sink = DropOldestQueue(250)
    sp = FakeSpotter(["A"])
    calls = {"n": 0}

    def boom(hit):
        calls["n"] += 1
        raise RuntimeError("on_hit 崩了")

    w = KwsWorker(sp, sink, boom, KwsConfig(cooldown_s=0.0), clock=Clock())
    _drain_to(w, sink, 10)
    w.start()
    time.sleep(0.3)
    assert w._thread.is_alive()            # 异常没杀死线程
    assert w.err_count >= 1
    w.stop()
