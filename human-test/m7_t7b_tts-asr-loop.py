"""M7/M4 联合人类实测 T7b: TTS 外放 → 麦回录 → ASR 转写 → CER。 设计: tts-design.md §6
一测三验: M7 音质(耳朵) + M4 转写质量(已知文本对照) + 外放回录链路(为 barge-in/自激摸底)。
前置: **必须用音箱外放**(拔耳机!)让麦能录到 TTS 声音; models/voxcpm1.5 与 qwen3-asr 就绪。
步骤: 逐句 TTS 播放 → 自动回录窗口收 ASR 文本 → 打印 CER → 你确认"听到的=说的这句"(回车)/否则写备注。
通过标准: [T7b-1] 每句可听懂且与目标句一致; [T7b-2] 平均 CER ≤ 5%; [T7b-3] 无漏句(6/6 出文本)。
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
from tts.tts import SpeakFinish, TtsConfig as TTSCfg, start_tts  # noqa: E402

SENTENCES = [
    "你好，我是语音助手测试。",
    "打开地图看看右上角有没有野怪。",
    "把音量调到百分之三十。",
    "刚才那波操作太秀了，回放一下。",
    "今天下午八点开始水友赛报名。",
    "第三局换替补射手上场，辅助休息。",
]


def cer(ref: str, hyp: str) -> float:
    ref, hyp = ref.strip(), hyp.strip()
    if not ref:
        return 1.0
    d = [[0] * (len(hyp) + 1) for _ in range(len(ref) + 1)]
    for i in range(len(ref) + 1):
        d[i][0] = i
    for j in range(len(hyp) + 1):
        d[0][j] = j
    for i in range(1, len(ref) + 1):
        for j in range(1, len(hyp) + 1):
            d[i][j] = min(d[i-1][j] + 1, d[i][j-1] + 1,
                          d[i-1][j-1] + (ref[i-1] != hyp[j-1]))
    return d[len(ref)][len(hyp)] / len(ref)


def main():
    print("!! 确认: 正在使用【音箱外放】而非耳机? (回车继续)")
    input()
    mic = MicSource()
    mic.start()
    print(f"[T7b] 麦: {mic.device_name_resolved} | 加载 ASR + TTS (TTS 预热最长 420s)...")
    segq = DropOldestQueue(8)
    texts = []
    vad = VadSentencer(build_vad(VadConfig()), mic.sinks["vad"],
                       lambda s, st: segq.put((s, st)))
    asr = AsrWorker(build_recognizer(AsrConfig()), segq, lambda t: texts.append(t))
    asr.start(); vad.start()
    tts = start_tts(TTSCfg())
    assert tts.ready.wait(420), "TTS 预热超时"
    results = []
    try:
        for i, s in enumerate(SENTENCES):
            texts.clear()
            done = []
            n = tts.speak(s)
            t0 = time.monotonic()
            while time.monotonic() - t0 < 60 and len(done) < n:
                time.sleep(0.05)
            vad.set_active(True)             # 回录窗口
            t0 = time.monotonic()
            while not texts and time.monotonic() - t0 < 15:
                time.sleep(0.2)
            hyp = texts[0].text if texts else "(无输出)"
            c = cer(s, hyp)
            results.append((s, hyp, c))
            print(f"\n[{i+1}/6] 目标: {s}\n      转写: {hyp}\n      CER: {c:.1%}")
            v = input("      听到且一致回车=OK, 否则输入备注: ").strip()
            if v:
                results[-1] = (s, hyp, -1.0)
    finally:
        asr.stop(); vad.stop(); tts.shutdown(); mic.stop()
    avg = sum(r[2] for r in results if r[2] >= 0) / max(len(results), 1)
    ok = len(results) == 6 and all(r[2] >= 0 for r in results) and avg <= 0.05
    print(f"\n[统计] {len(results)}/6 句 | 平均 CER {avg:.1%} | "
          f"{'PASS' if ok else 'FAIL'}")
    res = ROOT / "human-test" / f"RESULTS-{dt.date.today().isoformat()}.md"
    header = "# human-test 结果记录\n\n| 时间 | 用例 | 结果 | 数据/备注 |\n| ---- | ---- | ---- | ---- |\n"
    if not res.exists():
        res.write_text(header, encoding="utf-8")
    verdict = input("确认结果 (回车=如上判定 或输入覆盖): ").strip()
    with res.open("a", encoding="utf-8") as fh:
        fh.write(f"| {dt.datetime.now():%H:%M} | M7/M4 T7b TTS回录闭环 | "
                 f"{verdict or ('PASS' if ok else 'FAIL')} | avgCER={avg:.1%} "
                 f"sent={len(results)}/6 |\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
