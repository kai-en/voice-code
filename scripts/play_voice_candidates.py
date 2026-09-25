# -*- coding: utf-8 -*-
"""连播中文母音候选（同步播放版）"""
import glob
import os
import sys

import numpy as np
import sounddevice as sd
import torch
import torchaudio

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.stdout.reconfigure(encoding="utf-8")

SR = 44100
files = [f for f in sorted(glob.glob("models/voice_candidates/zh_*.aac"))
         if os.path.basename(f) != "zh_35.aac"]
print(f"found {len(files)} candidates", flush=True)

for i, f in enumerate(files, 1):
    wav, rate = torchaudio.load(f)
    if wav.shape[0] > 1:
        wav = wav.mean(0, keepdim=True)
    x = wav.squeeze(0)
    if rate != SR:
        x = torchaudio.functional.resample(x, rate, SR)
    x = x.numpy().astype(np.float32)
    peak = float(np.abs(x).max())
    if peak < 1e-4:
        print(f"[{i}] {os.path.basename(f)} 静音/解码失败! peak={peak}", flush=True)
        continue
    x = x / peak * 0.7
    print(f"[{i}/{len(files)}] {os.path.basename(f)}  {len(x)/SR:.1f}s peak={peak:.2f}  ▶", flush=True)
    sd.play(x, SR)
    sd.wait()                       # 同步: 播完才返回
    print("    done", flush=True)
    import time
    time.sleep(1.0)
print("ALL DONE", flush=True)
