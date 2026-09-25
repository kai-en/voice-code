"""M3+M4 离线 wav 实测：真 VAD+真 Qwen3-ASR，量 RTF/RSS/判停延迟。设计: asr-design.md §7/§8
用法:
  python scripts/m3m4_asr_wav.py <wav...> [--fast] [--model qwen3|sensevoice]
素材建议: human-test/recordings/m1_t2_*.wav (拍掌×10+数数+说话, 预期见 asr-design.md §8)
"""
import argparse
import sys
import time
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from audio_capture.capture import DropOldestQueue  # noqa: E402
from asr.pipeline import AsrConfig, build_recognizer, AsrWorker  # noqa: E402
from asr.vad_sentence import VadConfig, VadSentencer, build_vad  # noqa: E402

SR = 16000
BLOCK = 320


def read_wav(p):
    with wave.open(p, "rb") as w:
        assert w.getnchannels() == 1 and w.getsampwidth() == 2, f"{p}: 需 16bit mono"
        x = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
        rate = w.getframerate()
    x = x.astype(np.float32) / 32768.0
    if rate != SR:  # 简单整数比抽取
        k = rate // SR
        assert rate % SR == 0, f"{p}: {rate}Hz 非 16k 整数倍"
        x = x[::k]
    return x


def rss_mb():
    import psutil
    return psutil.Process().memory_info().rss / 1048576


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("wavs", nargs="+")
    ap.add_argument("--fast", action="store_true", help="不等实时节拍, 全速喂(只测解码 RTF)")
    ap.add_argument("--model", default="qwen3")
    ap.add_argument("--threads", type=int, default=2)
    args = ap.parse_args()

    from dataclasses import replace as _repl
    if args.model == "qwen3":  # 目录名随 sensevoice 换
        cfg = _repl(AsrConfig(), num_threads=args.threads)
    else:
        from asr.pipeline import SENSEVOICE_DIR
        cfg = AsrConfig(model="sensevoice", model_dir=Path("models") / SENSEVOICE_DIR)

    t0 = time.monotonic()
    rec = build_recognizer(cfg)
    vad = build_vad(VadConfig(silero_vad_model=cfg.silero_vad_model))
    print(f"[load] {time.monotonic()-t0:.1f}s  model={cfg.model}  RSS={rss_mb():.0f}MB")

    for wp in args.wavs:
        x = read_wav(wp)
        segq = DropOldestQueue(8)
        results = []
        sent = VadSentencer(vad, DropOldestQueue(250),
                            lambda s, st: segq.put((s, st)))
        sent._active = True
        worker = AsrWorker(rec, segq, lambda t: results.append(t))
        worker.start()                      # 喂入前启动, 防 segq(8) 溢出丢段
        t0 = time.monotonic()
        for i in range(0, len(x), BLOCK):
            sent.feed(x[i:i + BLOCK])
            if not args.fast:
                ahead = (i + BLOCK) / SR - (time.monotonic() - t0)
                if ahead > 0:
                    time.sleep(ahead)
        sent.feed(np.zeros(BLOCK, np.float32))  # 尾巴推一帧促 flush
        t_end = time.monotonic()
        deadline = time.monotonic() + max(6.0, len(x) / SR * 0.5)
        while time.monotonic() < deadline and segq.qsize():
            time.sleep(0.2)
        time.sleep(1.0)                     # 末段解码静默期
        worker.stop()
        print(f"\n=== {wp}  ({len(x)/SR:.1f}s, 喂入 {t_end-t0:.1f}s) ===")
        for r in results:
            print(f"  [{r.ts and ''}{r.dur_s:>5.2f}s] {r.text}")
        if not results:
            print("  (无文本段)")
        print(f"  stats: segments={sent.segment_count} empty={worker.empty_count} "
              f"err={worker.err_count} rtfs={worker.rtfs} RSS={rss_mb():.0f}MB")


if __name__ == "__main__":
    raise SystemExit(main())
