"""M7 T7c4 豆包 prompt 采集: 豆包朗读目标文案 → 立体声混音回录 → 裁剪/转44.1k → 本地ASR校验。
前置: 用豆包(网页版/桌面版均可)输入下方文案, 让 AI 语音播报; 外放走扬声器(立体声混音才能收到)。
通过标准: [T7c4-1] 成品 8–12s、无截头去尾、无 BGM; [T7c4-2] ASR 校验与文案一致(豆包没改写);
          [T7c4-3] 主观: 语速从容、音色符合预期。注意: AI 音色做 prompt = 二手克隆, 授权自负(用户已知)。
产物: models/voice_candidates/doubao/prompt_doubao.wav + prompt_doubao.json(text 即 prompt_text)。
"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
OUT_DIR = ROOT / "models" / "voice_candidates" / "doubao"
SR = 44100
SCRIPT = "晨光穿过云层落在桌面上，烧水壶滋滋地响，屋子里暖洋洋的。咱们放慢一点节奏，一起听听今天的故事。"


def find_stereo_mix(sd):
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] >= 2 and ("立体声混音" in d["name"] or "Stereo Mix" in d["name"]):
            return i, d["name"], float(d["default_samplerate"])
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] >= 2 and "主声音捕获" in d["name"]:
            return i, d["name"], float(d["default_samplerate"])
    return None


def trim(x, sr, thr=0.01):
    e = np.abs(x) > thr
    if not e.any():
        return x
    a, b = int(np.argmax(e)), len(e) - int(np.argmax(e[::-1]))
    pad = int(0.05 * sr)
    return x[max(0, a - pad):min(len(x), b + pad)]


def main():
    import sounddevice as sd
    print("!! 先把下面文案发给豆包并准备播报(让它逐字念):\n   " + SCRIPT + "\n")
    dev = find_stereo_mix(sd)
    if dev is None:
        print("未找到 立体声混音/主声音捕获 —— 请在声音设置启用立体声混音后重试")
        return 1
    idx, name, dsr = dev
    print(f"[T7c4] 回录设备: [{idx}] {name} @{dsr:.0f}Hz")
    input("豆包就绪后回车 → 录 24s (提示音响后立刻点播报): ")
    print('\a', flush=True)                     # 机箱蜂鸣, 不污染回录
    import time
    time.sleep(0.2)
    raw = sd.rec(int(24 * dsr), samplerate=dsr, channels=2, device=idx)
    sd.wait()
    x = np.asarray(raw).mean(axis=1).astype(np.float32)
    x = np.interp(np.linspace(0, len(x) - 1, int(len(x) * SR / dsr)),
                  np.arange(len(x)), x).astype(np.float32)
    x = trim(x, SR)
    dur = len(x) / SR
    print(f"[T7c4] 有效音频 {dur:.1f}s")
    if not 8.0 <= dur <= 13.0:
        print("  ⚠️ 时长不在 8–13s，请检查播报完整性/裁切，必要时重录")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "prompt_doubao.wav").write_bytes(_pcm16(x))
    print("[T7c4] 本地 ASR 校验中...")
    from asr.pipeline import AsrConfig, build_recognizer
    rec = build_recognizer(AsrConfig())
    st = rec.create_stream()
    st.accept_waveform(16000, np.interp(
        np.linspace(0, len(x) - 1, int(dur * 16000)), np.arange(len(x)), x).astype(np.float32))
    rec.decode_stream(st)
    hyp = st.result.text
    same = sum(1 for c in SCRIPT if c in hyp) / len(SCRIPT)
    print(f"  文案吻合度 {same:.0%}\n  ASR: {hyp}")
    (OUT_DIR / "prompt_doubao.json").write_text(json.dumps(
        {"wav": "prompt_doubao.wav", "dur_s": round(dur, 2), "sr": SR,
         "asr_text": hyp, "match": round(same, 2), "used_text": SCRIPT},
        ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[T7c4] 产物: {OUT_DIR / 'prompt_doubao.wav'}")
    v = input("[人类] 试听+对照通过标准, 回报 PASS/FAIL+备注: ").strip()
    res = ROOT / "human-test" / "RESULTS-2026-09-25.md"
    with res.open("a", encoding="utf-8") as fh:
        import datetime as dt
        fh.write(f"| {dt.datetime.now():%H:%M} | M7 T7c4 豆包prompt采集 | {v or '(未填)'} | "
                 f"dur={dur:.1f}s match={same:.0%} |\n")
    return 0


def _pcm16(x):
    import wave
    import io
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())
    return b.getvalue()


if __name__ == "__main__":
    raise SystemExit(main())
