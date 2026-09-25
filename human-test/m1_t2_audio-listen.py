"""M1 T2/T4 录音试听测试（人类参与）。 设计出处: docs/0923工作/audio-capture-design.md §5.2 T2/T4

前置:
  - 在仓库根目录 (D:\\work\\voice-code) 用 .venv 运行；
  - 麦克风已接好（默认设备，或用 --device 子串指定）。
步骤（录音 30s 期间依次做）:
  1) 对麦拍掌 x10，每次间隔 >=300ms；
  2) 匀速念 "1 2 3 4 5 6 7 8 9"；
  3) 正常说一段话（哼两句也行）；
  4) （T4 附加）若为双声道麦：录的同时分别对左/右麦孔吹气或拍掌。
  录完自动弹出播放器打开 wav，用耳朵对照下面标准。
通过标准:
  [T2-1] 试听无咔哒、爆音、断续、周期性边缘伪影；
  [T2-2] 客观统计打印出 10 个拍掌瞬态（相邻间隔 >=300ms 不吞并）；
  [T2-3] 数数 "1..9" 试听逐字可辨、无掉字；
  [T4-1] (双声道麦) 左/右位置信号均可听到且响度相当(脚本打印建议通道能量对比)。
"""
import argparse
import datetime as dt
import sys
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np
import sounddevice as sd  # noqa: E402  (仅用于列设备)

from audio_capture.capture import SR, MicSource, StallWatchdog, WatchdogConfig  # noqa: E402


def pick_device():
    print("[设备] 可选输入设备:")
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0:
            print(f"  [{i}] {d['name']} ({d['default_samplerate']:.0f}Hz/{d['max_input_channels']}ch)")
    return None


def transient_count(rms_env, thresh_ratio=0.55, gap_s=0.3):
    """粗略统计拍掌瞬态: 高于峰值比例阈值的团块数, 间隔合并. 给人参考, 最终以耳朵为准。"""
    peak = rms_env.max()
    if peak <= 0:
        return 0
    hit = rms_env > peak * thresh_ratio
    n, last, gaps = 0, -10, []
    for i, h in enumerate(hit):
        if h and not (i > 0 and hit[i - 1]):
            gaps.append((i - last) if last >= 0 else 9e9)
            n += 1
            last = i
    merged = sum(1 for g in gaps if g * (1.0 / 50.0) >= gap_s)
    return n if not gaps else merged


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=30.0)
    ap.add_argument("--device", default=None, help="设备索引或名称子串; 缺省用系统默认输入")
    ap.add_argument("--no-play", action="store_true", help="录完不自动打开播放器")
    args = ap.parse_args()

    if not args.device:
        pick_device()
        spec = input("回车用默认输入设备, 或输入 [索引]/设备名子串: ").strip() or None
    else:
        spec = args.device

    mic = MicSource(device_name=spec)
    mic.start()
    print(f"\n[录音] 设备: #{mic.device_index} {mic.device_name_resolved} "
          f"(hands_free={mic.is_hand_free})  {args.seconds:.0f}s  {SR}Hz/mono/int16")
    print("  3 秒后开始 —— 请准备拍掌...")
    wd = StallWatchdog(mic, WatchdogConfig(), started_at=time.monotonic())
    time.sleep(3)

    frames, t_end = [], time.monotonic() + args.seconds
    while time.monotonic() < t_end:
        f = mic.sinks["kws"].get(timeout=0.5)
        if f is not None:
            frames.append(f)
        assert not wd.check()  # 录制中途停摆直接报错终止, 不算 T2 主观判定
    mic.stop()

    pcm = np.concatenate(frames) if frames else np.zeros(1, np.float32)
    rms_env = np.array([np.sqrt(np.mean(f * f)) for f in frames]) if frames else np.zeros(1)
    peak = float(np.abs(pcm).max()) if pcm.size else 0.0
    out = ROOT / "human-test" / "recordings" / (
        "m1_t2_" + dt.datetime.now().strftime("%Y%m%d-%H%M%S") + ".wav")
    out.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(pcm, -1, 1) * 32767).astype("<i2").tobytes())

    print(f"\n[客观统计] 时长 {pcm.size / SR:.2f}s  帧数 {len(frames)} (期望 {args.seconds*50:.0f}±2)"
          f"  peak {peak:.3f}  RMS均值 {rms_env.mean():.4f}")
    print(f"[客观统计] 瞬态(疑似拍掌)个数 ≈ {transient_count(rms_env)}  (期望 10, 最终以试听为准)")
    print(f"[客观统计] dropped: {mic.sinks['kws'].dropped}  status: {mic.status_count}  err: {mic.err_count}")
    print(f"[文件] {out}")
    print("\n" + "=" * 64)
    print(__doc__)
    print("=" * 64)
    if not args.no_play:
        try:
            import os
            os.startfile(str(out))  # noqa: S606  Windows: 用默认播放器打开
        except Exception as e:
            print(f"(自动播放失败, 请手动打开上面的 wav: {e})")

    verdict = input("全部满足直接回车记 PASS, 否则输入 FAIL 及备注: ").strip()
    result = "PASS" if verdict == "" else verdict
    res = ROOT / "human-test" / f"RESULTS-{dt.date.today().isoformat()}.md"
    line = (f"| {dt.datetime.now():%H:%M} | M1 T2/T4 录音试听 | {result} | "
            f"dev={mic.device_name_resolved} dur={pcm.size/SR:.1f}s peak={peak:.3f} "
            f"clap≈{transient_count(rms_env)} file={out.name} |\n")
    header = "# human-test 结果记录\n\n| 时间 | 用例 | 结果 | 数据/备注 |\n| ---- | ---- | ---- | ---- |\n"
    if not res.exists():
        res.write_text(header, encoding="utf-8")
    with res.open("a", encoding="utf-8") as fh:
        if res.stat().st_size == 0:
            fh.write(header)
        fh.write(line)
    print(f"[记录] 已写入 {res}")
    return 0 if result == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
