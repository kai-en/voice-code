"""M2 T5 唤醒率人类实测（同时补做 M1 的 T5 真消费者冒烟）。 设计: kws-design.md §9 / audio-capture-design.md §5.2 T5

前置: models/ 与 config/kws/keywords.txt 已就绪（kws-design.md §2/§3）；安静环境+常规游戏外放音量。
步骤:
  1) 运行后对麦呼唤激活词 10 次，每次间隔约 30s（脚本会提示进度）；
  2) 每次命中会"叮"一声（beep）并打印序号；没听到蜂鸣说明本次漏检，可立刻补叫一次(不计入)；
  3) 期间可正常放游戏声音测试误触发：非呼唤时刻出现命中 → 记为误触发。
通过标准:
  [T5-1] 10 次主动呼唤命中 >=9；
  [T5-2] 全程(约 6min)误触发 <=1 次；
  [T5-3] 无崩溃、CPU 无异常飙升（可开着任务管理器看一眼 python 进程）。
"""
import datetime as dt
import sys
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import sounddevice as sd  # noqa: E402

from audio_capture.capture import MicSource  # noqa: E402
from kws.kws_wake import KwsConfig, build_spotter, KwsWorker  # noqa: E402

CALLS = 10
GAP_S = 30


_BEEP = (0.3 * np.sin(2 * np.pi * 880 * np.linspace(
    0, 0.15, int(0.15 * 44100), endpoint=False))).astype(np.float32)


def beep():
    try:
        sd.play(_BEEP, 44100, blocking=True)   # blocking: 等播完且暴露错误
    except Exception:
        import traceback
        traceback.print_exc()


def main():
    mic = MicSource(device_name=(sys.argv[1] if len(sys.argv) > 1 else None))
    mic.start()
    print(f"[M2 T5] 设备: {mic.device_name_resolved}；激活词文件: config/kws/keywords.txt")
    hits = []
    t0 = time.time()

    def on_hit(h):
        if getattr(h, "repeat", False):        # M13 cooldown 二喊只刷回音锚, 不计入唤醒率/误触发
            return
        hits.append(h)
        print(f"  ✔ 命中 #{len(hits)} '{h.keyword}' @+{h.ts - t0:.1f}s")
        beep()

    w = KwsWorker(build_spotter(KwsConfig()), mic.sinks["kws"], on_hit, KwsConfig())
    w.start()
    print(f"开始：{CALLS} 次呼唤 × {GAP_S}s 间隔。Ctrl+C 可提前结束并照常记录。")
    try:
        for i in range(CALLS):
            print(f"[{dt.datetime.now():%H:%M:%S}] 请第 {i+1}/{CALLS} 次呼唤「小码小码」（本窗口命中数={len(hits)}）")
            time.sleep(GAP_S)
    except KeyboardInterrupt:
        print("(提前结束)")
    finally:
        w.stop(); mic.stop()

    print(f"\n[统计] 命中 {len(hits)}/{CALLS}  hit_count={w.hit_count} "
          f"dropped(cooldown/mute)={w.dropped_count} err={w.err_count} mic_cb={mic.cb_count}")
    if not hits:
        print("[警告] 0 命中：先怀疑 token 生成/设备错误，直接记 FAIL 并排查！")
    verdict = input("按标准判定：回车=PASS，或输入 FAIL 及备注: ").strip()
    result = "PASS" if (verdict == "" and len(hits) >= CALLS - 1) else (verdict or f"FAIL hits={len(hits)}/{CALLS}")
    res = ROOT / "human-test" / f"RESULTS-{dt.date.today().isoformat()}.md"
    header = "# human-test 结果记录\n\n| 时间 | 用例 | 结果 | 数据/备注 |\n| ---- | ---- | ---- | ---- |\n"
    if not res.exists():
        res.write_text(header, encoding="utf-8")
    with res.open("a", encoding="utf-8") as fh:
        fh.write(f"| {dt.datetime.now():%H:%M} | M2 T5 唤醒率 | {result} | "
                 f"hits={len(hits)}/{CALLS} dev={mic.device_name_resolved} "
                 f"dropped={w.dropped_count} err={w.err_count} |\n")
    print(f"[记录] 已写入 {res}")
    return 0 if str(result) == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
