# M3 VAD 切句 —— 设计: docs/0923工作/asr-design.md
# 复用: sherpa-onnx VoiceActivityDetector(Silero) + 官方 simulate-streaming 示例攒句循环(R1)。
# 自研仅: 预卷/512 攒批/门控/段拷贝搬运。端点状态机与强制切句(max_speech)为 VAD 原生。
from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np

SR = 16000
WINDOW = 512          # Silero 固定窗 (16k 下 32ms)，官方"please don't change"
PREROLL_FRAMES = 10   # 200ms 预卷 (M1 20ms 帧 x10)


@dataclass(frozen=True)
class VadConfig:
    silero_vad_model: Path = Path("models/silero_vad.onnx")
    threshold: float = 0.5
    min_silence_s: float = 0.6
    min_speech_s: float = 0.25
    max_speech_s: float = 20.0


def build_vad(cfg: VadConfig):
    from sherpa_onnx import (SileroVadModelConfig, VadModelConfig,
                             VoiceActivityDetector)

    if not Path(cfg.silero_vad_model).exists():
        raise FileNotFoundError(
            f"silero_vad.onnx 不存在: {cfg.silero_vad_model}，"
            "下载见 asr-design.md §3 (asr-models tag, 643854B)")
    sv = SileroVadModelConfig()
    sv.model = str(cfg.silero_vad_model)
    sv.threshold = cfg.threshold
    sv.min_silence_duration = cfg.min_silence_s
    sv.min_speech_duration = cfg.min_speech_s
    sv.window_size = WINDOW
    sv.max_speech_duration = cfg.max_speech_s
    vc = VadModelConfig()
    vc.silero_vad = sv
    vc.sample_rate = SR
    vc.num_threads = 1
    return VoiceActivityDetector(vc, buffer_size_in_seconds=30)


class VadSentencer:
    """消费 M1 vad 队列(20ms f32 帧) → Silero → on_segment(samples, seg_end)。

    seg_end = 段出队时刻(monotonic)，即"用户说完这句 + 静音判定"的那一刻；
    M4 用它减去 min_silence 得到真实语音结束时刻，供 M5 的 3s 收集窗口锚定（锚在说话结束，不是解码结束）。
    inactive: 只滚动预卷不喂 VAD；active 首刻把预卷灌回，兑现 200ms 句首保护。
    段必须 numpy 拷贝后再 pop（front.samples 随 pop 失效，设计 §10-7）。
    """

    def __init__(self, vad, sink, on_segment: Callable[[np.ndarray, float], None],
                 clock: Callable[[], float] = time.monotonic):
        self._vad = vad
        self._sink = sink
        self._on_segment = on_segment
        self.clock = clock
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._active = False
        self._preroll: deque = deque(maxlen=PREROLL_FRAMES)
        self._buf = np.zeros(0, dtype=np.float32)
        self.segment_count = 0
        self.err_count = 0
        self.speaking = False        # 此刻是否在语音段中(vad 线程写/主 loop 读,GIL 单值原子)

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True, name="vad")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)

    def set_active(self, on: bool) -> None:
        if on == self._active:
            return
        self._active = on
        if not on:
            self.speaking = False                     # 卫生：inactive 期间 speaking 不得残留 True
        if on:
            self._vad.reset()
            self._buf = np.zeros(0, dtype=np.float32)
            self.feed(np.concatenate(list(self._preroll)) if self._preroll
                      else np.zeros(0, dtype=np.float32))

    def feed(self, samples: np.ndarray) -> None:
        """喂样本（active 才进 VAD；inactive 仅滚预卷）。拆出来便于单测直调。"""
        if not self._active:
            self._preroll.append(samples)
            return
        self._buf = np.concatenate([self._buf, samples])
        off = 0
        while len(self._buf) - off >= WINDOW:
            self._vad.accept_waveform(self._buf[off:off + WINDOW])
            off += WINDOW
        self._buf = self._buf[off:]
        while not self._vad.empty():
            seg = np.array(self._vad.front.samples, dtype=np.float32)  # 拷贝!
            seg_end = self.clock()          # 出队时刻 = 语音结束 + min_silence 判定延迟
            self._vad.pop()
            if seg.size:
                self.segment_count += 1
                self._on_segment(seg, seg_end)
        self.speaking = self._vad.is_speech_detected()   # 在说/尾静音判定中=True；段 finalize 即 False(早于 pop)。M5 用它推迟提交

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                f = self._sink.get(timeout=0.1)
                if f is None:
                    continue
                self.feed(f)
            except Exception:
                self.err_count += 1
                if self.err_count <= 2:
                    import traceback
                    traceback.print_exc()
