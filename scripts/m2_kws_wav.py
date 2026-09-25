"""M2 离线 wav 冒烟（非人类测试，无需麦）。设计: kws-design.md §9
复刻官方 keyword-spotter.py 调用序: 读 wav → 分批 accept_waveform
→ tail_paddings 0.66s → input_finished → decode 至 is_ready=False → 打印命中。

用法:
  python scripts/m2_kws_wav.py <wav...> [--keywords 路径] [--model-dir 路径]
缺省用项目 models/ 与生成的 config/kws/keywords.txt；
官方素材自测: --keywords models/.../test_wavs/keywords.txt 配 test_wavs/*.wav。
"""
import argparse
import sys
import wave
from dataclasses import replace
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kws.kws_wake import KwsConfig, build_spotter, SR  # noqa: E402

TAIL_S = 0.66


def read_wav(p: str) -> np.ndarray:
    with wave.open(p, "rb") as w:
        assert w.getframerate() == SR, f"{p}: 需 {SR}Hz, 实际 {w.getframerate()}"
        assert w.getnchannels() == 1 and w.getsampwidth() == 2, f"{p}: 需 16bit mono"
        x = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
    return x.astype(np.float32) / 32768.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("wavs", nargs="+")
    ap.add_argument("--keywords", default="config/kws/keywords.txt")
    ap.add_argument("--model-dir", default=None)
    args = ap.parse_args()

    cfg = KwsConfig(keywords_file=Path(args.keywords))
    if args.model_dir:
        cfg = replace(cfg, model_dir=Path(args.model_dir))
    spotter = build_spotter(cfg)
    tail = np.zeros(int(TAIL_S * SR), dtype=np.float32)
    n_ok = 0

    for wp in args.wavs:
        stream = spotter.create_stream()
        x = read_wav(wp)
        for i in range(0, len(x), 1600):
            stream.accept_waveform(SR, x[i:i + 1600])
        stream.accept_waveform(SR, tail)
        stream.input_finished()
        hits = []
        while spotter.is_ready(stream):
            spotter.decode_stream(stream)
            r = spotter.get_result(stream)
            if r:
                hits.append(r)
                spotter.reset_stream(stream)
        print(f"{wp}: {hits if hits else '(无命中)'}")
        n_ok += bool(hits)
    print(f"[m2_kws_wav] {n_ok}/{len(args.wavs)} 文件命中")
    return 0 if n_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
