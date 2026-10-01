# M2 常驻激活词监听 —— 设计: docs/0923工作/kws-design.md
# 复用: sherpa-onnx KeywordSpotter + 官方麦克风示例调用序(R1)。
# 自研仅: 消费线程/去抖/mute/装配。目标 ≤200 行。
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np

SR = 16000
MODEL_DIR_NAME = "sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20"
STEM = "epoch-13-avg-2-chunk-16-left-64"  # chunk-16=精度档，换 variant 只改这里


@dataclass(frozen=True)
class KwsConfig:
    model_dir: Path = Path("models") / MODEL_DIR_NAME
    keywords_file: Path = Path("config/kws/keywords.txt")
    keywords_threshold: float = 0.25  # 调大→更难触发
    keywords_score: float = 1.5       # 全局 boost；每词 :x 可覆盖
    cooldown_s: float = 2.0
    num_threads: int = 1


@dataclass(frozen=True)
class KwsHit:
    keyword: str
    ts: float
    repeat: bool = False     # cooldown 内的二喊：只用于编排器刷新回音锚，不动状态


def build_spotter(cfg: KwsConfig, model_dir: Path | None = None):
    import sherpa_onnx

    d = Path(model_dir or cfg.model_dir)
    files = {
        "encoder": d / f"encoder-{STEM}.int8.onnx",
        "decoder": d / f"decoder-{STEM}.onnx",  # 官方仅提供 fp32 decoder
        "joiner": d / f"joiner-{STEM}.int8.onnx",
        "tokens": d / "tokens.txt",
    }
    missing = [str(p) for p in files.values() if not p.exists()]
    if missing:
        raise FileNotFoundError(
            "KWS 模型缺失:\n  " + "\n  ".join(missing)
            + f"\n下载/校验见 docs/0923工作/kws-design.md §2 (解压到 {d.parent}/)"
        )
    if not Path(cfg.keywords_file).exists():
        raise FileNotFoundError(
            f"keywords 文件不存在: {cfg.keywords_file}，生成流程见 kws-design.md §3"
        )
    return sherpa_onnx.KeywordSpotter(
        tokens=str(files["tokens"]),
        encoder=str(files["encoder"]),
        decoder=str(files["decoder"]),
        joiner=str(files["joiner"]),
        num_threads=cfg.num_threads,
        keywords_file=str(cfg.keywords_file),
        keywords_threshold=cfg.keywords_threshold,
        keywords_score=cfg.keywords_score,
        provider="cpu",
    )


class KwsWorker:
    """消费 M1 kws 队列(20ms f32 帧) → KeywordSpotter → on_hit(KwsHit)。

    命中契约(R1): get_result 非空 → 立即 reset_stream → 过滤(cooldown/muted) → emit。
    停摆时 sink 断供，本线程自然空转（M1 watchdog 负责报警，恢复=重启进程）。
    """

    BATCH_CAP = 8  # 每次 accept_waveform ≤8 帧 = 160ms

    def __init__(
        self,
        spotter,
        sink,
        on_hit: Callable[[KwsHit], None],
        cfg: KwsConfig = KwsConfig(),
        clock: Callable[[], float] = time.monotonic,
    ):
        self._sp = spotter
        self._sink = sink
        self._on_hit = on_hit
        self._cfg = cfg
        self._clock = clock
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._stream = spotter.create_stream()
        self._muted = False
        self._last_hit = 0.0
        self.hit_count = 0
        self.dropped_count = 0
        self.err_count = 0

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True, name="kws")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)

    def set_muted(self, on: bool) -> None:
        """M5 进/出 SPEAKING 直调。unmute 时丢弃播报期积压与部分匹配。"""
        if on == self._muted:
            return
        self._muted = on
        if not on:
            self._sink.clear()
            self._sp.reset_stream(self._stream)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                first = self._sink.get(timeout=0.1)
                if first is None:
                    continue
                frames = [first]
                while len(frames) < self.BATCH_CAP:
                    g = self._sink.get(timeout=0)
                    if g is None:
                        break
                    frames.append(g)
                chunk = frames[0] if len(frames) == 1 else np.concatenate(frames)
                self._stream.accept_waveform(SR, chunk)
                while self._sp.is_ready(self._stream):
                    self._sp.decode_stream(self._stream)
                    r = self._sp.get_result(self._stream)
                    if r:
                        self._sp.reset_stream(self._stream)
                        self._handle(r)
            except Exception:
                self.err_count += 1
                if self.err_count <= 2:      # 首次异常打印, 不再静默吞错误
                    import traceback
                    traceback.print_exc()

    def _handle(self, keyword: str) -> None:
        now = self._clock()
        if self._muted:
            self.dropped_count += 1
            return
        if now - self._last_hit < self._cfg.cooldown_s:
            self.dropped_count += 1          # _last_hit 不更新：cooldown 自最近一次真命中起算
            self._on_hit(KwsHit(keyword=keyword, ts=time.time(), repeat=True))
            return
        self._last_hit = now
        self.hit_count += 1
        self._on_hit(KwsHit(keyword=keyword, ts=time.time()))


def start_kws(cfg: KwsConfig, mic, on_hit: Callable[[KwsHit], None]) -> KwsWorker:
    """装配入口：M1 mic.sinks['kws'] → KwsWorker（已启动）。"""
    w = KwsWorker(build_spotter(cfg), mic.sinks["kws"], on_hit, cfg)
    w.start()
    return w
