"""M7 真机冒烟: 加载 VoxCPM1.5 并开口说话。设计: tts-design.md §6
用法: python scripts/m7_tts_say.py [任意中文文本]
"""
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tts.tts import SpeakFinish, Interrupted, TtsConfig, start_tts  # noqa: E402


def main():
    text = sys.argv[1] if len(sys.argv) > 1 else \
        "你好，我是语音助手。显存常驻测试，成功。现在是第二句，用来验证分句流水。"
    done = []

    def on_ev(ev):
        if isinstance(ev, SpeakFinish):
            done.append(ev)
            print(f"  ✔ [{ev.text[:20]}...] 合成 {ev.synth_s}s 播放 {ev.play_s}s")
        elif isinstance(ev, Interrupted):
            print("  被打断:", ev.text)

    t0 = time.monotonic()
    e = start_tts(TtsConfig(), on_event=on_ev)
    print("[load+warm] 首次含 torch.compile ~150s ...")
    if not e.ready.wait(420):
        print("预热超时"); return 1
    print(f"[ready] {time.monotonic()-t0:.0f}s")

    t1 = time.monotonic()
    n = e.speak(text)
    while len(done) < n and time.monotonic() - t1 < 120:
        time.sleep(0.1)
    print(f"[speak] {n} 句, 端到端 {time.monotonic()-t1:.1f}s, stats={e.stats()}")
    import subprocess
    print(subprocess.run(["nvidia-smi", "--query-gpu=memory.used",
                          "--format=csv,noheader"], capture_output=True,
                          text=True).stdout.strip(), "(含桌面其他占用)")
    e.shutdown()
    return 0 if len(done) == n else 1


if __name__ == "__main__":
    raise SystemExit(main())
