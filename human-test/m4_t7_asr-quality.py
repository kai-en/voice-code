"""M4 T7 转写质量人类实测。 设计: docs/0923工作/asr-design.md §8
前置: models/ 就绪; 安静环境; 默认麦或 --device 指定。
步骤: 屏幕逐句出 10 句中文, 每句对麦朗读一次(说完等 1.5s 看结果)。
评分: 每句 0=整句丢失 / 1=关键词错或漏字 / 2=完全正确。总分 ≥16/20 且无 0 分句 → PASS。
通过标准:
  [T7-1] 总分 ≥16；
  [T7-2] 无整句丢失(0 分句)；
  [T7-3] 数字句注意: qwen3 档应出汉字(二十四), sensevoice 档出阿拉伯数字——均算对, 记入备注。
"""
import datetime as dt
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from audio_capture.capture import MicSource  # noqa: E402
from asr.pipeline import AsrConfig, build_recognizer, AsrWorker  # noqa: E402
from asr.vad_sentence import VadConfig, VadSentencer, build_vad  # noqa: E402
from audio_capture.capture import DropOldestQueue  # noqa: E402

SENTENCES = [
    "帮我把英雄的技能连招改成二一三",
    "打开地图看看右上角有没有野怪刷新",
    "上一局我打了二十四分钟，输出排第四",
    "把音量调到百分之三十，弹幕声音关掉",
    "刚才那个操作太秀了，回放一下下路那波",
    "查询今天八点开始的水友赛报名状态",
    "这件装备价格是一千二百五十金币",
    "切到打野路线，先刷红buff再抓中路",
    "把直播标题改成'深夜电竞冲分挑战'",
    "3 号位换人，替补射手上，辅助休息",
]


def main():
    cfg = AsrConfig()
    mic = MicSource(device_name=(sys.argv[1] if len(sys.argv) > 1 else None))
    mic.start()
    print(f"[T7] 设备 {mic.device_name_resolved} | 模型 {cfg.model} | 载模型中...")
    segq = DropOldestQueue(8)
    last = {}

    def on_text(t):
        last["t"] = t
        print(f"  >> 转写: {t.text}   (段长 {t.dur_s}s, RTF {worker.rtf_last:.2f})")

    vad = VadSentencer(build_vad(VadConfig(silero_vad_model=cfg.silero_vad_model)),
                       mic.sinks["vad"], lambda s, st: segq.put((s, st)))
    worker = AsrWorker(build_recognizer(cfg), segq, on_text)
    vad.start(); worker.start()
    scores = []
    try:
        for i, s in enumerate(SENTENCES):
            print(f"\n句 {i+1}/10，请朗读：\n  「{s}」")
            vad.set_active(False); vad.set_active(True)   # 干净起点
            last.pop("t", None)
            t0 = time.time()
            while time.time() - t0 < 20 and "t" not in last:
                time.sleep(0.2)
            if "t" not in last:
                print("  !! 10s 无转写产出（可补读一次，按回车继续）")
                input()
            v = input("  评分 [0=丢句 / 1=有错 / 2=全对，直接回车=2]: ").strip() or "2"
            scores.append(int(v))
    finally:
        worker.stop(); vad.stop(); mic.stop()
    total = sum(scores)
    ok = total >= 16 and 0 not in scores
    print(f"\n[统计] 总分 {total}/20, 0 分句 {scores.count(0)} 个 → {'PASS' if ok else 'FAIL'}")
    verdict = input("确认结果（回车=如上判定，或输入覆盖说明）: ").strip()
    result = verdict or ("PASS" if ok else "FAIL")
    res = ROOT / "human-test" / f"RESULTS-{dt.date.today().isoformat()}.md"
    header = "# human-test 结果记录\n\n| 时间 | 用例 | 结果 | 数据/备注 |\n| ---- | ---- | ---- | ---- |\n"
    if not res.exists():
        res.write_text(header, encoding="utf-8")
    with res.open("a", encoding="utf-8") as fh:
        fh.write(f"| {dt.datetime.now():%H:%M} | M4 T7 转写质量 | {result} | "
                 f"model={cfg.model} 总分={total}/20 scores={scores} rtf_last={worker.rtf_last:.3f} |\n")
    print(f"[记录] 已写入 {res}")
    return 0 if result == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
