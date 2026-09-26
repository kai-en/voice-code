# M7 TTS (VoxCPM1.5 常驻) —— 设计: docs/0923工作/tts-design.md
# 复用: voxcpm 包 (VoxCPM.from_pretrained/generate) + sounddevice 播放。
# CUDA Graph 约束: 加载/warm/generate 全部收敛在唯一 worker 线程, 外部只 speak/stop。
# 0926 双后端(用户拍板, GPU 显存吃紧时的降级路): backend="voxcpm"(默认,原路径) | "wintts"
#   (System.Speech PowerShell 子进程, 零显存零依赖; 音色为微软 Huihui, 非克隆声)。
from __future__ import annotations

import base64
import json
import queue
import re
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import numpy as np

SR_DEFAULT = 44100
_SPLIT_RE = re.compile(r"[。！？!?；;\n]+")
_TARGET_PEAK = 10 ** (-1 / 20)          # -1 dBFS
_FLOOR_PEAK = 10 ** (-30 / 20)         # 低于 -30dB 视为近静音, 不放大防抬底噪
_NO_WINDOW = 0x08000000 if __import__("sys").platform == "win32" else 0


def normalize_peak(w):
    """每条输出按峰值归一到 -1dBFS（第1轮优化#4）。"""
    peak = float(np.max(np.abs(w))) if len(w) else 0.0
    return w * (_TARGET_PEAK / peak) if peak >= _FLOOR_PEAK else w


@dataclass(frozen=True)
class TtsConfig:
    backend: str = "voxcpm"           # "voxcpm" | "wintts"
    model_dir: Path = Path("models") / "voxcpm1.5"
    device: str = "cuda"
    optimize: bool = True               # triton-windows 已装; False=调试档 RTF~2.0
    timesteps: int = 10
    output_device: Optional[int] = None
    sample_warn_s: float = 8.0
    prompt_wav: Optional[Path] = (Path("models") / "voice_candidates"
                                  / "doubao" / "prompt_doubao.wav")
    prompt_text: str = ""       # 空 = 读同名 .json 的 asr_text（音色+文本随素材走）
    wintts_rate: int = 0                # System.Speech 语速 -10..10
    wintts_volume: int = 100            # 0..100


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
            w = np.asarray(w, dtype=np.float32).reshape(-1)      # cache 路径返 (1,N), 拍平防声道误判
        else:
            w = np.asarray(self.model.generate(text, inference_timesteps=self.cfg.timesteps),
                           dtype=np.float32)
        return normalize_peak(w)

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


_PS_TTS_SCRIPT = """
Add-Type -AssemblyName System.Speech
[Console]::InputEncoding=[Text.Encoding]::UTF8
[Console]::OutputEncoding=[Text.Encoding]::UTF8
$s=New-Object System.Speech.Synthesis.SpeechSynthesizer
if($s -eq $null){{[Console]::Out.WriteLine('ERR init-failed: System.Speech unavailable'); exit}}
$s.Rate={rate}; $s.Volume={vol}
$z=$s.GetInstalledVoices()|Where-Object{{$_.Enabled -and $_.VoiceInfo.Culture.Name -like 'zh-*'}}|Select-Object -First 1
if($z){{$s.SelectVoice($z.VoiceInfo.Name)}}
[Console]::Out.WriteLine('READY')
while($true){{try{{$l=[Console]::In.ReadLine()}}catch{{$l=$null}}
if($l -eq $null){{break}}
if($l.Trim() -eq ''){{continue}}
try{{$s.Speak($l)}}catch{{[Console]::Out.WriteLine(('ERR '+$_.Exception.Message)); continue}}
[Console]::Out.WriteLine('OK')}}
"""


class WinTtsEngine:
    """System.Speech 后端: PowerShell 子进程常驻, UTF-8 行协议(一句→'OK')。零显存/零 GPU。"""

    def __init__(self, cfg: TtsConfig, on_event: Callable | None = None,
                 popen: Callable = subprocess.Popen) -> None:
        self.cfg = cfg
        self._on_event = on_event or (lambda e: None)
        self._popen = popen
        self._q: queue.SimpleQueue = queue.SimpleQueue()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._proc = None
        self._cur: Optional[str] = None
        self._killed_by_stop = False
        self.ready = threading.Event()
        self.sent = 0
        self.err_count = 0
        self.synth_s_total = 0.0
        self.play_s_total = 0.0

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True, name="wintts")
        self._thread.start()

    def speak(self, text: str) -> int:
        parts = [p.strip() for p in _SPLIT_RE.split(text) if p.strip()]
        for p in parts:
            self._q.put(p)
        return len(parts)

    def stop(self) -> None:
        """立刻消音: 杀进程(kill 自记录句柄) + 清队列; 下一句自动重生。当前句报 Interrupted。"""
        while True:
            try:
                self._q.get_nowait()
            except queue.Empty:
                break
        cur, self._cur = self._cur, None
        if self._proc is not None:
            self._killed_by_stop = True
            self._proc.kill()
            self._proc = None
        if cur is not None:
            self._emit(Interrupted(cur, time.time()))

    def shutdown(self) -> None:
        self._stop.set()
        self.stop()
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    def stats(self) -> dict:
        return {"sent": self.sent, "err": self.err_count,
                "synth_s": round(self.synth_s_total, 1),
                "play_s": round(self.play_s_total, 1)}

    def _emit(self, ev) -> None:
        try:
            self._on_event(ev)
        except Exception:
            pass

    def _spawn(self):
        script = _PS_TTS_SCRIPT.format(rate=self.cfg.wintts_rate, vol=self.cfg.wintts_volume)
        enc = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
        proc = self._popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                            "-EncodedCommand", enc],
                           stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                           stderr=subprocess.DEVNULL, creationflags=_NO_WINDOW)
        line = proc.stdout.readline()          # READY 握手(30s 依赖 OS 拉 powershell, 自设超时在调用侧)
        if line.strip() != b"READY":
            proc.kill()
            raise RuntimeError(f"wintts 握手失败: {line!r}")
        return proc

    def _run(self) -> None:
        try:
            self._proc = self._spawn()
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
            self._cur = text
            self._emit(SpeakStart(text, time.time()))
            t0 = time.monotonic()
            try:
                self._proc.stdin.write((text + "\n").encode("utf-8"))
                self._proc.stdin.flush()
                ack = self._proc.stdout.readline()
                if ack.strip() != b"OK":
                    raise RuntimeError(f"wintts ack 异常: {ack!r}")
            except Exception:
                self.err_count += 1
                import traceback
                traceback.print_exc()          # 落 daemon 崩溃通道, ERR 不再静默
                with_proc, self._proc = self._proc, None
                if with_proc:
                    with_proc.kill()
                if self._killed_by_stop:          # stop() 杀句 = 静默丢弃, 不重播
                    self._killed_by_stop = False
                    continue
                cur, self._cur = self._cur, None
                if cur is not None and not self._stop.is_set():
                    self._emit(Interrupted(cur, time.time()))
                try:
                    self._proc = self._spawn()      # 重生重试一次当前句
                    self._proc.stdin.write((text + "\n").encode("utf-8"))
                    self._proc.stdin.flush()
                    if self._proc.stdout.readline().strip() != b"OK":
                        continue
                except Exception:
                    self.err_count += 1
                    self._proc = None
                    continue
            play = time.monotonic() - t0
            self._cur = None
            self.sent += 1
            self.play_s_total += play
            self._emit(SpeakFinish(text, 0.0, round(play, 2), time.time()))


def start_tts(cfg: TtsConfig = TtsConfig(), on_event: Callable | None = None,
              model_factory: Callable = default_model_factory,
              player=None) -> "TtsEngine | WinTtsEngine":
    if cfg.backend == "wintts":
        e = WinTtsEngine(cfg, on_event)
    else:
        e = TtsEngine(cfg, on_event, model_factory, player)
    e.start()
    return e
