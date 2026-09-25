"""M1 真机冒烟（手动，非 CI）。对应 audio-capture-design.md §5.2 T1/T3/T6 的简化版。

用法:
    python scripts/m1_smoke.py [设备名子串]
无设备子串则用系统默认输入。采集 3s，报告帧率/队列/CPU/停摆报警。
"""
import sys
import threading
import time

sys.path.insert(0, "src")

import sounddevice as sd

from audio_capture.capture import BLOCK, MicSource, StallWatchdog, WatchdogConfig


def main():
    spec = sys.argv[1] if len(sys.argv) > 1 else None
    print("== 输入设备 ==")
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0:
            print(f"  [{i}] {d['name']} ({d['hostapi']}, {d['default_samplerate']:.0f}Hz/{d['max_input_channels']}ch)")

    mic = MicSource(device_name=spec)
    print(f"\n启动采集 device={spec or '<默认>'} ...")
    try:
        mic.start()
    except Exception as e:
        print(f"启动失败: {type(e).__name__}: {e}")
        return 1
    print(f"已打开: #{mic.device_index} {mic.device_name_resolved} (hands_free={mic.is_hand_free})")

    wd = StallWatchdog(mic, WatchdogConfig(), started_at=time.monotonic())
    got = {"kws": 0, "vad": 0}
    stop = threading.Event()

    def drain(name):
        q = mic.sinks[name]
        while not stop.is_set():
            if q.get(timeout=0.05) is not None:
                got[name] += 1

    th = [threading.Thread(target=drain, args=(n,)) for n in ("kws", "vad")]
    for t in th:
        t.start()

    t0 = time.monotonic()
    cpu0 = time.process_time()
    while time.monotonic() - t0 < 3.0:
        time.sleep(0.2)
    dur = time.monotonic() - t0
    stop.set()
    for t in th:
        t.join()
    mic.stop()

    print(f"\n{dur:.2f}s 结果: cb={mic.cb_count} 期望≈{dur*50:.0f} "
          f"kws={got['kws']} vad={got['vad']} status={mic.status_count} err={mic.err_count}")
    print(f"CPU(进程): {(time.process_time()-cpu0)/dur*100:.1f}%  单帧={BLOCK}样本/{BLOCK/16000*1000:.0f}ms")
    r = mic.cb_count / (dur * 50)
    print(f"{'[T1 PASS]' if 0.9 <= r <= 1.15 and mic.err_count == 0 else '[T1 FAIL]'} 帧率比 {r:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
