# M14 热词边界探针: qwen3-asr 到底支持几个热词 + 超 max_total_len 三种报错的真实行为(设计 docs/0927工作/m14-dynamic-hotwords-design.md §3)
# 用法: .\.venv\Scripts\python.exe scripts\m14_hotwords_probe.py [--max-total-len 1024]
# 非 pytest UT: 要加载 878MB 模型(~30s), 走 scripts/ 手工跑; 纯逻辑校验 UT 待实现时进 tests/
import argparse
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from sherpa_onnx import OfflineRecognizer  # noqa: E402

from asr.pipeline import QWEN3_DIR, SR  # noqa: E402

POOL = "天地玄黄宇宙洪荒日月盈昃辰宿列张寒来暑往秋收冬藏金生丽水玉出昆冈剑号巨阙珠称夜光"


def words(n, wlen=4):
    out, s = [], 0
    for i in range(n):
        out.append(POOL[(s + i * wlen) % len(POOL): (s + i * wlen) % len(POOL) + wlen] or "天地玄黄")
        s = (s + 1) % len(POOL)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-total-len", type=int, default=1024)
    args = ap.parse_args()
    d = ROOT / "models" / QWEN3_DIR
    rec = OfflineRecognizer.from_qwen3_asr(
        conv_frontend=str(d / "conv_frontend.onnx"), encoder=str(d / "encoder.int8.onnx"),
        decoder=str(d / "decoder.int8.onnx"), tokenizer=str(d / "tokenizer"),
        num_threads=2, feature_dim=128, provider="cpu",
        max_total_len=args.max_total_len, max_new_tokens=8, hotwords="", debug=True)
    rng = np.random.default_rng(7)
    audio = (rng.standard_normal(SR * 3) * 0.02).astype(np.float32)

    for n in (8, 16, 32, 64, 128, 160, 192, 224, 256, 384):
        wl = words(n)
        print(f"###PROBE n={n} chars={sum(len(w) for w in wl)}", flush=True)
        st = rec.create_stream()
        st.accept_waveform(SR, audio)
        st.set_option("hotwords", ",".join(wl))
        t0 = time.time()
        rec.decode_stream(st)
        print(f"###PROBE n={n} decode={time.time()-t0:.2f}s text={st.result.text!r}", flush=True)


if __name__ == "__main__":
    main()
