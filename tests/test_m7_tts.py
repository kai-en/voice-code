# M7 TTS 单测（CI 无 GPU：FakeModel/FakePlayer 注入，锁线程约束与队列语义）
import threading
import time

import numpy as np

from tts.tts import (Interrupted, SpeakFinish, SpeakStart, TtsConfig, TtsEngine,
                     start_tts)

SR = 44100


class FakeModel:
    def __init__(self):
        self.calls = []                    # (text, thread_ident)
        self.tts_model = type("T", (), {"sample_rate": SR})()

    def generate(self, text, inference_timesteps=10):
        self.calls.append((text, threading.get_ident()))
        return np.full(SR // 2, 0.1, dtype=np.float32)     # 0.5s 音频


class FakePlayer:
    def __init__(self, hold=0.0):
        self.played = []
        self.threads = []
        self._cancelled = False
        self.hold = hold
        self.started = threading.Event()

    def play(self, samples, sr):
        self.threads.append(threading.get_ident())
        self.started.set()
        t0 = time.monotonic()
        while time.monotonic() - t0 < self.hold and not self._cancelled:
            time.sleep(0.005)
        if not self._cancelled:
            self.played.append(len(samples))

    def cancel(self):
        self._cancelled = True


def _engine(player=None):
    model = FakeModel()
    evs: list = []
    e = TtsEngine(TtsConfig(model_dir="."), lambda ev: evs.append(ev),
                  model_factory=lambda cfg: model, player=player or FakePlayer())
    return e, model, evs


def _wait(cond, timeout=3.0):
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        if cond():
            return True
        time.sleep(0.01)
    return False


def test_warm_then_ready_and_single_thread():
    e, model, evs = _engine()
    e.speak("排队一句。")                  # start 之前 speak → 缓冲
    e.start()
    assert e.ready.wait(3.0)
    assert _wait(lambda: len(model.calls) == 2)   # 预热 + 缓冲句
    assert model.calls[0][0] == "预热。"
    idents = {t for _, t in model.calls}
    assert len(idents) == 1               # 全部 generate 同一线程(CUDA Graph 约束)
    e.shutdown()


def test_sentence_split_fifo_and_events():
    e, model, evs = _engine()
    e.start()
    assert e.ready.wait(3.0)
    n = e.speak("第一句。第二句！第三句?第四句")
    assert n == 4
    assert _wait(lambda: model.calls and model.calls[-1][0] == "第四句")
    assert _wait(lambda: sum(isinstance(x, SpeakFinish) for x in evs) == 4)
    seq = [type(x).__name__ for x in evs]
    assert seq == ["SpeakStart", "SpeakFinish"] * 4   # 顺序不错位
    e.shutdown()


def test_stop_clears_queue_and_interrupts():
    player = FakePlayer(hold=0.4)
    e, model, evs = _engine(player)
    e.start()
    assert e.ready.wait(3.0)
    e.speak("一。二。三。四。五。")
    assert player.started.wait(2.0)
    e.stop()
    assert _wait(lambda: any(isinstance(x, Interrupted) for x in evs))
    time.sleep(0.3)
    assert e.stats()["sent"] <= 2         # 后续句全被清
    e.shutdown()


def test_play_same_thread_as_synth():
    e, model, evs = _engine()
    e.start()
    e.ready.wait(3.0)
    e.speak("查线程。")
    assert _wait(lambda: e.stats()["sent"] == 1)
    synth_t = model.calls[-1][1]
    assert e._player.threads[-1] == synth_t          # 合成与播放同线程
    assert synth_t != threading.get_ident()          # 且不是调用者线程
    e.shutdown()


def test_stats_shape_and_err_not_fatal():
    class Boom(FakeModel):
        def generate(self, text, inference_timesteps=10):
            if "炸" in text:               # 注意: 分句器会剥掉标点, 匹配裸词
                raise RuntimeError("gpu boom")
            return super().generate(text)

    evs: list = []
    e = TtsEngine(TtsConfig(model_dir="."), lambda ev: evs.append(ev),
                  model_factory=lambda cfg: Boom(), player=FakePlayer())
    e.start()
    assert e.ready.wait(3.0)
    e.speak("炸了。")
    assert _wait(lambda: e.err_count >= 1)
    assert e._thread.is_alive()           # 异常不杀 worker
    assert any(isinstance(x, SpeakStart) for x in evs)
    e.speak("好了。")
    assert _wait(lambda: e.stats()["sent"] == 1)
    e.shutdown()
