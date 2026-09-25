# M7 TTS (VoxCPM1.5 常驻) —— 设计: docs/0923工作/tts-design.md
# 复用: voxcpm 包 (VoxCPM.from_pretrained/generate) + sounddevice 播放。
# CUDA Graph 约束: 加载/warm/generate 全部收敛在唯一 worker 线程, 外部只 speak/stop。
from __future__ import annotations

import json
import queue
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import numpy as np

SR_DEFAULT = 44100
_SPLIT_RE = re.compile(r"[。！？!?；;\n]+")


@dataclass(frozen=True)
class TtsConfig:
    model_dir: Path = Path("models") / "voxcpm1.5"
    device: str = "cuda"
    optimize: bool = True               # triton-windows 已装; False=调试档 RTF~2.0
    timesteps: int = 10
    output_device: Optional[int] = None
    sample_warn_s: float = 8.0
    prompt_wav: Optional[Path] = (Path("models") / "voice_candidates"
                                  / "doubao" / "prompt_doubao.wav")
    prompt_text: str = ""       # 空 = 读同名 .json 的 asr_text（音色+文本随素材走）


@dataclass(frozen=True)
class SpeakStart:
    text: str
    ts: float


@dataclass(frozen=True)
class SpeakFinish:
    text: str
    synth_s: float
    play_s: float
    ts: float


@dataclass(frozen=True)
class Interrupted:
    text: str
    ts: float


def default_model_factory(cfg: TtsConfig):
    from voxcpm import VoxCPM
    if not Path(cfg.model_dir).exists():
        raise FileNotFoundError(
            f"TTS 模型缺失: {cfg.model_dir}，下载见 docs/0923工作/tts-design.md §0")
    return VoxCPM.from_pretrained(str(cfg.model_dir), load_denoiser=False,
                                  optimize=cfg.optimize, device=cfg.device)


class SdPlayer:
    """阻塞式分块播放, 支持 cancel(barge-in)。仅被 worker 线程调用。"""

    def __init__(self, output_device=None):
        self._dev = output_device
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def play(self, samples: np.ndarray, sr: int) -> None:
        import sounddevice as sd
        self._cancelled = False
        step = sr // 10                       # 100ms 块
        with sd.OutputStream(samplerate=sr, channels=1, dtype="float32",
                             device=self._dev) as out:
            for i in range(0, len(samples), step):
                if self._cancelled:
                    return
                out.write(np.clip(samples[i:i + step], -1.0, 1.0))


class TtsEngine:
    """单 worker 线程: 出队 → generate → 播放 → 事件。模型常驻 GPU (设计 §2/§4)。"""

    def __init__(self, cfg: TtsConfig, on_event: Callable | None = None,
                 model_factory: Callable = default_model_factory,
                 player=None):
        self.cfg = cfg
        self._on_event = on_event or (lambda e: None)
        self._factory = model_factory
        self._player = player or SdPlayer(cfg.output_device)
        self._q: queue.SimpleQueue = queue.SimpleQueue()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.model = None
        self._pcache = None
        self.ready = threading.Event()
        self.sent = 0
        self.err_count = 0
        self.synth_s_total = 0.0
        self.play_s_total = 0.0
        self._cur_synth: Optional[float] = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True, name="tts")
        self._thread.start()

    def stop(self) -> None:
        """清队列 + 打断当前播放 (不卸载模型)。"""
        self._player.cancel()
        while True:
            try:
                self._q.get_nowait()
            except queue.Empty:
                break

    def shutdown(self) -> None:
        self._stop.set()
        self._player.cancel()
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    def speak(self, text: str) -> int:
        parts = [p.strip() for p in _SPLIT_RE.split(text) if p.strip()]
        for p in parts:
            self._q.put(p)
        return len(parts)

    def stats(self) -> dict:
        return {"sent": self.sent, "err": self.err_count,
                "synth_s": round(self.synth_s_total, 1),
                "play_s": round(self.play_s_total, 1)}

    def _build_prompt_cache(self):
        """母音色常驻: 素材+官方转写 → voxcpm 官方 prompt cache (音色锁定基线, T7c PASS)。"""
        wav = self.cfg.prompt_wav
        if wav is None:
            return None
        tm = getattr(self.model, "tts_model", None)
        if not hasattr(tm, "build_prompt_cache"):
            print("[tts] WARN 模型不支持 prompt cache, 回落无音色锁定", flush=True)
            return None
        wav = Path(wav)
        if not wav.exists():
            raise FileNotFoundError(
                f"音色素材缺失: {wav} (路径约定见 docs/0925工作/tts-voice-lock-plan.md)")
        text = self.cfg.prompt_text or json.loads(
            wav.with_suffix(".json").read_text(encoding="utf-8"))["asr_text"]
        return tm.build_prompt_cache(text, str(wav))

    def _gen(self, text: str):
        if self._pcache is not None:
            w, _, _ = self.model.tts_model.generate_with_prompt_cache(
                text, prompt_cache=self._pcache,
                inference_timesteps=self.cfg.timesteps)
            return w
        return self.model.generate(text, inference_timesteps=self.cfg.timesteps)

    def _emit(self, ev) -> None:
        try:
            self._on_event(ev)
        except Exception:
            pass

    def _run(self) -> None:
        try:
            t0 = time.monotonic()
            self.model = self._factory(self.cfg)
            sr = int(getattr(self.model.tts_model, "sample_rate", SR_DEFAULT))
            self._pcache = self._build_prompt_cache()
            self._gen("好的。" if self._pcache else "预热。")   # compile/首载一次性
            self.ready.set()
        except Exception:
            self.err_count += 1
            import traceback
            traceback.print_exc()
            return
        while not self._stop.is_set():
            text = self._q.get()
            if self._stop.is_set():
                return
            self._emit(SpeakStart(text, time.time()))
            try:
                t0 = time.monotonic()
                w = self._gen(text)
                synth = time.monotonic() - t0
                dur = len(w) / sr
                if synth > self.cfg.sample_warn_s:
                    print(f"[tts] WARN 合成 {synth:.1f}s 超阈值 (句长 {dur:.1f}s) "
                          "→ 建议 M5 拆短句", flush=True)
                t1 = time.monotonic()
                self._player.play(np.asarray(w, dtype=np.float32), sr)
                play = time.monotonic() - t1
                if self._player._cancelled:
                    self._emit(Interrupted(text, time.time()))
                else:
                    self.sent += 1
                    self.synth_s_total += synth
                    self.play_s_total += play
                    self._emit(SpeakFinish(text, round(synth, 2), round(play, 2),
                                           time.time()))
            except Exception:
                self.err_count += 1
                import traceback
                traceback.print_exc()


def start_tts(cfg: TtsConfig = TtsConfig(), on_event: Callable | None = None,
              model_factory: Callable = default_model_factory,
              player=None) -> TtsEngine:
    e = TtsEngine(cfg, on_event, model_factory, player)
    e.start()
    return e
