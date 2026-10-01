# M3+M4 单测（CI 无麦无模型；FakeVad/FakeRecognizer 注入，真 DropOldestQueue）
import queue
import time

import numpy as np

from audio_capture.capture import DropOldestQueue
from asr.vad_sentence import WINDOW, VadSentencer
from asr.pipeline import AsrText, AsrWorker, _PREFIX_RE

SR = 16000
FRAME = np.full(320, 0.1, dtype=np.float32)


def _frames(n, v=0.1):
    return [np.full(320, v, dtype=np.float32) for _ in range(n)]


class FakeSegment:
    def __init__(self, samples, start=0.0):
        self.samples = samples
        self.start = start


class FakeVad:
    def __init__(self, script=None, detected=False):
        self.wins = []                 # 收到的每个 512 窗
        self.reset_count = 0
        self.queue = list(script or [])  # [FakeSegment]
        self._current = None
        self.detected = detected       # is_speech_detected() 返回值(speaking 闸用例)

    def accept_waveform(self, w):
        self.wins.append(w.copy())
        self._current = w

    def is_speech_detected(self):
        return self.detected

    def empty(self):
        return len(self.queue) == 0

    @property
    def front(self):
        return self.queue[0]

    def pop(self):
        seg = self.queue.pop(0)
        seg.samples[:] = 9.99          # 模拟 pop 后 C++ 缓冲失效/被覆写
        return None

    def reset(self):
        self.reset_count += 1


def _sentencer(script=None):
    sink = DropOldestQueue(250)
    vad = FakeVad(script)
    segs = queue.Queue()
    s = VadSentencer(vad, sink, lambda x, st: segs.put((x, st)))
    return s, vad, sink, segs


def test_window_batching_keeps_remainder_across_batches():
    s, vad, sink, segs = _sentencer()
    s._active = True
    for f in _frames(5):               # 5×320=1600 → 3 窗×512, 余 164
        s.feed(f)
    assert len(vad.wins) == 3
    assert all(len(w) == WINDOW for w in vad.wins)
    assert len(s._buf) == 1600 - 3 * WINDOW          # 余数保留（M2 丢帧教训固化）
    for f in _frames(2):               # 64+640=704 → 1 窗 512, 余 192
        s.feed(f)
    assert len(vad.wins) == 4
    assert len(s._buf) == 192


def test_segment_copied_before_pop():
    seg = FakeSegment(np.full(1000, 0.5, dtype=np.float32))
    s, vad, sink, segs = _sentencer([seg])
    s._active = True
    s.feed(np.full(WINDOW, 0.5, dtype=np.float32))   # 触发一次 accept→drain
    out, _start = segs.get(timeout=1)
    assert np.all(out == 0.5)          # pop 后 FakeVad 覆写原数组也不影响已拷贝段
    assert s.segment_count == 1


def test_inactive_rolls_preroll_not_vad():
    s, vad, sink, segs = _sentencer()
    for f in _frames(20):              # inactive 10 帧只留最后 10
        s.feed(f)
    assert vad.wins == []
    assert len(s._preroll) == 10


def test_activate_injects_preroll_and_resets():
    s, vad, sink, segs = _sentencer()
    for f in _frames(15):
        s.feed(f)
    s.set_active(True)
    assert vad.reset_count == 1
    fed = sum(len(w) for w in vad.wins)
    assert fed >= 10 * 320 - WINDOW    # 预卷 10 帧(3200) 已被喂入(差数留在 _buf)
    s.set_active(False)                # 清掉 10 激活前
    s2, vad2, sink2, segs2 = _sentencer()
    for f in _frames(15):
        s2.feed(f)
    s2.set_active(True)
    assert vad2.reset_count == 1
    assert sum(len(w) for w in vad2.wins) >= 3200 - WINDOW


def test_speaking_mirrors_is_speech_detected_and_deactivate_clears():
    vad = FakeVad(None, detected=True)
    s = VadSentencer(vad, DropOldestQueue(8), lambda x, st: None)
    s._active = True
    s.feed(np.full(WINDOW, 0.5, dtype=np.float32))
    assert s.speaking is True                       # 在说/尾静音判定 → M5 提交闸推迟
    s.set_active(False)
    assert s.speaking is False                      # 卫生: 停用即清零, 不残留


def test_empty_text_not_emitted():
    rec = FakeRec(["  ", "好"])
    q = DropOldestQueue(8)
    out = queue.Queue()
    w = AsrWorker(rec, q, out.put)
    q.put((np.zeros(1600, np.float32), 0.0))
    q.put((np.zeros(1600, np.float32), 0.0))
    w.start(); time.sleep(0.3); w.stop()
    got = [out.get(timeout=1) for _ in range(1)]
    assert out.empty() and w.empty_count == 1
    assert got[0].text == "好"


class FakeStream:
    def __init__(self):
        self.result = type("R", (), {"text": ""})()

    def accept_waveform(self, sr, x):
        pass


class FakeRec:
    def __init__(self, texts):
        self.texts = list(texts)
        self.stream = FakeStream()

    def create_stream(self):
        return self.stream

    def decode_stream(self, st):
        st.result.text = self.texts.pop(0) if self.texts else ""


def test_prefix_defense_stripped():
    rec = FakeRec(["language Chinese<asr_text>打开地图"])
    q = DropOldestQueue(8)
    out = queue.Queue()
    w = AsrWorker(rec, q, out.put)
    q.put((np.zeros(1600, np.float32), 0.0))
    w.start(); time.sleep(0.3); w.stop()
    assert out.get(timeout=1).text == "打开地图"


def test_decode_exception_keeps_thread_alive():
    class Boom(FakeRec):
        def decode_stream(self, st):
            raise RuntimeError("boom")

    q = DropOldestQueue(8)
    w = AsrWorker(Boom([]), q, lambda t: None)
    q.put((np.zeros(1600, np.float32), 0.0))
    w.start(); time.sleep(0.3)
    assert w._thread.is_alive() and w.err_count >= 1
    w.stop()


def test_stop_responsive():
    q = DropOldestQueue(8)
    s, vad, sink, segs = _sentencer()
    w = AsrWorker(FakeRec([]), q, lambda t: None)
    s.start(); w.start()
    t0 = time.monotonic()
    s.stop(); w.stop()
    assert time.monotonic() - t0 < 0.5


def test_seg_queue_drop_oldest():
    q = DropOldestQueue(8)
    for i in range(10):
        q.put((np.zeros(10, np.float32), float(i)))
    assert q.dropped == 2 and q.qsize() == 8


def test_stats_shape():
    from asr.pipeline import AsrPipeline
    s, vad, sink, segs = _sentencer()
    w = AsrWorker(FakeRec([]), DropOldestQueue(8), lambda t: None)
    p = AsrPipeline(s, w)
    st = p.stats()
    assert set(st) >= {"segments", "texts", "empty", "rtf_last"}


def test_audio_pending_union():
    from asr.pipeline import AsrPipeline

    class FakeQ:
        def __init__(self, n): self.n = n
        def qsize(self): return self.n

    class FakeW:
        busy = False
        _seg = FakeQ(0)

    class FakeV:
        speaking = False

    v, w = FakeV(), FakeW()
    p = AsrPipeline(v, w)
    assert p.audio_pending() is False                 # 三源全空 → 可提交
    v.speaking = True
    assert p.audio_pending() is True                  # 在说/尾静音
    v.speaking = False
    w.busy = True
    assert p.audio_pending() is True                  # 解码在飞
    w.busy = False
    w._seg = FakeQ(2)
    assert p.audio_pending() is True                  # 段在队未取
