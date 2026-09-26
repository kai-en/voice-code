# M4 Qwen3-ASR 转写 (含 M3 前端) —— 设计: docs/0923工作/asr-design.md
# 复用: OfflineRecognizer.from_qwen3_asr / from_sense_voice (同一 API 家族, 回退一行切换)。
# 自研仅: 解码线程循环/门控门面/防御剥前缀/统计。
from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from audio_capture.capture import DropOldestQueue
from asr.vad_sentence import VadConfig, VadSentencer, build_vad

SR = 16000
QWEN3_DIR = "sherpa-onnx-qwen3-asr-0.6B-int8-2026-03-25"
# WoW 热词 (qwen3 system-prompt 上下文偏置; 中文按字 ≈ token 上界, 官方 ≥48 token WARN)
WOW_HOTWORDS = ("周常,英雄难度,龙希尔,虚空侵攻,盘卷蛇岛,"
                "圣骑士,潜行者,死亡骑士,萨满,恶魔猎手")
SENSEVOICE_DIR = "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17"
# 语言前缀防御 (impl 已自动剥离, #3472; 此为保险丝): "language Chinese<asr_text>..."
_PREFIX_RE = re.compile(r"^\s*language\s+\S+?<asr_text>")


@dataclass(frozen=True)
class AsrConfig:
    model: str = "qwen3"                     # qwen3 | sensevoice (回退一行切换)
    model_dir: Path = Path("models") / QWEN3_DIR
    silero_vad_model: Path = Path("models/silero_vad.onnx")
    num_threads: int = 2
    hotwords: str = WOW_HOTWORDS             # 逗号分隔, 仅 qwen3; ≥48 token 官方 WARN
    vad_min_silence_s: float = 0.6
    vad_max_speech_s: float = 20.0
    max_new_tokens: int = 192                # 默认 128 对 20s 句有截断 WARN 风险


@dataclass(frozen=True)
class AsrText:
    text: str
    ts: float
    dur_s: float
    end_ts: float = 0.0      # 语音结束时刻(monotonic, 已扣 VAD 静音判定延迟)；0=未知


def build_recognizer(cfg: AsrConfig):
    from sherpa_onnx import OfflineRecognizer

    d = Path(cfg.model_dir)
    if cfg.model == "qwen3":
        paths = {k: d / f for k, f in [
            ("conv_frontend", "conv_frontend.onnx"),
            ("encoder", "encoder.int8.onnx"),
            ("decoder", "decoder.int8.onnx"),
            ("tokenizer", "tokenizer"),
        ]}
        missing = [str(p) for p in paths.values() if not p.exists()]
        if missing:
            raise FileNotFoundError(
                "Qwen3-ASR 模型缺失:\n  " + "\n  ".join(missing)
                + "\n下载/校验见 docs/0923工作/asr-design.md §3")
        return OfflineRecognizer.from_qwen3_asr(
            **{k: str(v) for k, v in paths.items()},
            num_threads=cfg.num_threads, feature_dim=128, provider="cpu",
            max_total_len=1024, max_new_tokens=cfg.max_new_tokens,
            hotwords=cfg.hotwords,
        )
    if cfg.model == "sensevoice":
        model, tokens = d / "model.int8.onnx", d / "tokens.txt"
        if not model.exists() or not tokens.exists():
            raise FileNotFoundError(
                f"SenseVoice 回退包缺失 (需先下载 {SENSEVOICE_DIR}): {model} / {tokens}")
        return OfflineRecognizer.from_sense_voice(
            model=str(model), tokens=str(tokens), language="auto",
            use_itn=True, num_threads=cfg.num_threads, provider="cpu",
        )
    raise ValueError(f"未知 asr.model: {cfg.model} (可选 qwen3|sensevoice)")


class AsrWorker:
    """段队列 → 每段新建 stream(句间零历史, 官方契约) → decode → on_text。"""

    def __init__(self, recognizer, segments: DropOldestQueue,
                 on_text: Callable[[AsrText], None], min_silence: float = 0.6):
        self._rec = recognizer
        self._seg = segments
        self._on_text = on_text
        self._sil = min_silence
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.text_count = 0
        self.empty_count = 0
        self.err_count = 0
        self.rtf_last = -1.0
        self.rtfs: list[float] = []

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True, name="asr")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)

    def decode_segment(self, samples, seg_end: float) -> None:
        dur = samples.size / SR
        stream = self._rec.create_stream()
        stream.accept_waveform(SR, samples)
        t0 = time.monotonic()
        self._rec.decode_stream(stream)
        self.rtf_last = (time.monotonic() - t0) / max(dur, 0.1)
        self.rtfs.append(round(self.rtf_last, 3))
        text = _PREFIX_RE.sub("", stream.result.text or "").strip()
        if not text:
            self.empty_count += 1
            return
        self.text_count += 1
        self._on_text(AsrText(text=text, ts=time.time(), dur_s=round(dur, 2),
                              end_ts=seg_end - self._sil))

    def _run(self) -> None:
        while not self._stop.is_set():
            item = self._seg.get(timeout=0.1)
            if item is None:
                continue
            try:
                self.decode_segment(*item)
            except Exception:
                self.err_count += 1
                if self.err_count <= 2:
                    import traceback
                    traceback.print_exc()


class AsrPipeline:
    """M3+M4 门面。set_active 与 KwsWorker.set_muted 对称, M5 直调。"""

    def __init__(self, vad: VadSentencer, worker: AsrWorker):
        self._vad = vad
        self._worker = worker

    def start(self) -> None:
        self._vad.start()
        self._worker.start()

    def stop(self) -> None:
        self._vad.stop()
        self._worker.stop()

    def set_active(self, on: bool) -> None:
        self._vad.set_active(on)

    def stats(self) -> dict:
        return {"segments": self._vad.segment_count,
                "texts": self._worker.text_count,
                "empty": self._worker.empty_count,
                "vad_err": self._vad.err_count, "asr_err": self._worker.err_count,
                "rtf_last": round(self._worker.rtf_last, 3),
                "seg_q": self._vad._sink.qsize() if hasattr(self._vad, "_sink") else -1}


def start_asr(cfg: AsrConfig, mic, on_text: Callable[[AsrText], None],
              vad=None, recognizer=None) -> AsrPipeline:
    """装配 mic.sinks['vad'] → pipeline；模型进程启动即建（激活零加载延迟）。"""
    segments: DropOldestQueue = DropOldestQueue(8)
    vad = vad or VadSentencer(build_vad(VadConfig(
        silero_vad_model=cfg.silero_vad_model,
        min_silence_s=cfg.vad_min_silence_s,
        max_speech_s=cfg.vad_max_speech_s)),
        mic.sinks["vad"],
        lambda s, en: segments.put((s, en)))
    worker = AsrWorker(recognizer or build_recognizer(cfg), segments, on_text,
                       min_silence=cfg.vad_min_silence_s)
    return AsrPipeline(vad, worker)
