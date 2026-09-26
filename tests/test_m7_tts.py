# M7 TTS 单测（CI 无 GPU：FakeModel/FakePlayer 注入，锁线程约束与队列语义）
import threading
import time

import numpy as np

from tts.tts import (Interrupted, SpeakFinish, SpeakStart, TtsConfig, TtsEngine,
                     WinTtsEngine, start_tts)

SR = 44100


class FakeStdin:
    def __init__(self):
        self.lines = []

    def write(self, b):
        self.lines.append(b.decode("utf-8"))

    def flush(self):
        pass


class FakeStdout:
    def __init__(self, lines, block_until_kill=False):
        self._lines = list(lines)
        self._block = block_until_kill
        self._ev = threading.Event()

    def kill_signal(self):
        self._ev.set()

    def readline(self):
        if self._lines:
            return (self._lines.pop(0) + "\n").encode("utf-8")
        if self._block:
            self._ev.wait(3.0)              # 模拟"句子仍在播"直到被 kill
            return b""
        return b""


class FakeProc:
    def __init__(self, stdout_lines, block_until_kill=False):
        self.stdin = FakeStdin()
        self.stdout = FakeStdout(stdout_lines, block_until_kill)
        self.killed = False

    def kill(self):
        self.killed = True
        self.stdout.kill_signal()


def _wintts(lines, block_until_kill=False):
    evs: list = []
    procs = []

    def popen(cmd, **kw):
        p = FakeProc(list(lines), block_until_kill)
        procs.append(p)
        return p

    e = WinTtsEngine(TtsConfig(backend="wintts"), evs.append, popen=popen)
    return e, evs, procs


def test_wintts_ready_and_finish_events():
    e, evs, procs = _wintts(["READY", "OK", "OK"])
    e.start()
    assert e.ready.wait(3.0)
    n = e.speak("第一句。第二句！")
    assert n == 2
    assert _wait(lambda: e.stats()["sent"] == 2)
    assert [type(x).__name__ for x in evs] == ["SpeakStart", "SpeakFinish"] * 2
    assert procs[0].stdin.lines[0].startswith("第一句")
    e.shutdown()


def test_wintts_stop_kills_and_drops_current():
    # 第 2 句"仍在播"(readline 阻塞)时 stop: 杀进程、静默丢弃、不重播、不计数
    e, evs, procs = _wintts(["READY", "OK"], block_until_kill=True)
    e.start()
    assert e.ready.wait(3.0)
    e.speak("一。二。")
    assert _wait(lambda: e.stats()["sent"] == 1)
    time.sleep(0.1)                          # 让 worker 进入第二句 readline
    e.stop()
    time.sleep(0.3)
    assert procs[0].killed
    assert e.stats()["sent"] == 1            # 第二句被丢, 未重播计成
    assert sum(isinstance(x, SpeakFinish) for x in evs) == 1
    assert procs[0].stdin.lines.count("二\n") <= 1   # 最坏只写一次就被掐, 不重播第二次
    e.shutdown()


def test_wintts_speak_after_stop_is_clean():
    """T-D 复现: stop() 把 _proc 置 None 后, 下一句在 write 处撞 AttributeError
    (真机日志 16:17:59 两段 traceback)。期望: 在飞句静默丢弃, 新句正常播出, 不记错不打栈。"""
    evs, procs = [], []

    def popen(cmd, **kw):                       # 第 1 个 proc 卡在等 OK(模拟正在播), 重生后的第 2 个正常回 OK
        p = FakeProc(["READY"] if not procs else ["READY", "OK"], block_until_kill=not procs)
        procs.append(p)
        return p

    e = WinTtsEngine(TtsConfig(backend="wintts"), evs.append, popen=popen)
    e.start()
    assert e.ready.wait(3.0)
    e.speak("正在飞的那句。")
    time.sleep(0.15)                              # worker 卡在 readline 等 OK
    e.stop()                                      # 杀正在播的句
    time.sleep(0.2)
    e.speak("打断之后的新句。")
    assert _wait(lambda: e.stats()["sent"] == 1), f"新句没播出: {[type(x).__name__ for x in evs]}"
    assert e.stats()["err"] == 0, f"stop 后不该记错/打栈: {e.stats()}"
    assert sum(isinstance(x, Interrupted) for x in evs) == 1     # 只该丢在飞那句
    assert any(isinstance(x, SpeakFinish) and x.text.startswith("打断之后") for x in evs)
    assert len(procs) == 2                                   # 重生了一次
    e.shutdown()


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
