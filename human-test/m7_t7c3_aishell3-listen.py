"""M7 T7c3 AISHELL-3 母音色试听: 16 段真人女声(Apache-2.0, 44.1kHz 原生)逐段听, 选 C1'。
前置: 素材已在 models/voice_candidates/aishell3/ (本目录不入库, 见 overall-goals 开源边界)。
步骤: 逐段播放(文本为官方转写=未来 prompt_text) → 每段输入 采用/不采用+备注 → 汇总选最终编号。
通过标准: [T7c3-1] 嗓音偏柔、无播音腔硬感; [T7c3-2] 无齿音/爆音/截断;
          [T7c3-3] 选定后其单句 ≥5s 且转写逐字准确(官方表已保证, 可抽查)。
"""
import datetime as dt
import json
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "models" / "voice_candidates" / "aishell3"


def main():
    import sounddevice as sd
    picks = json.loads((DIR / "_picks.json").read_text(encoding="utf-8"))
    rows = [(sp, f, t, tag) for sp, f, t, tag in picks]
    rows.sort(key=lambda r: (r[3], r[1]))
    verdicts = []
    print(f"[T7c3] 试听 {len(rows)} 段 AISHELL-3 女声 (C=26-40岁 D=41+, 北/南口音)。\n")
    for n, (sp, f, t, tag) in enumerate(rows, 1):
        x, sr = sf.read(str(DIR / f), dtype="float32")
        if x.ndim > 1:
            x = x.mean(axis=1)
        while True:
            print(f"[{n:02d}|{tag}|{f}] {len(x)/sr:.1f}s\n      prompt_text: {t}")
            sd.play(np.clip(x, -1.0, 1.0), sr)
            sd.wait()
            v = input("      判定(采用/不采用/备注, r=重听): ").strip()
            if v.lower() != "r":
                verdicts.append((n, sp, f, v or "不采用"))
                break
    print("\n[汇总]")
    for n, sp, f, v in verdicts:
        print(f"  {n:02d} {sp}/{f}: {v}")
    pick = input("最终选用编号(如 07, 无则回车): ").strip()
    res = ROOT / "human-test" / f"RESULTS-{dt.date.today().isoformat()}.md"
    header = "# human-test 结果记录\n\n| 时间 | 用例 | 结果 | 数据/备注 |\n| ---- | ---- | ---- | ---- |\n"
    if not res.exists():
        res.write_text(header, encoding="utf-8")
    chosen = next((f"{sp}/{f}" for n, sp, f, v in verdicts if n == int(pick or -1)), "无")
    with res.open("a", encoding="utf-8") as fh:
        fh.write(f"| {dt.datetime.now():%H:%M} | M7 T7c3 AISHELL3试听 | 选用={chosen} | "
                 + "; ".join(f"{n:02d}:{v}" for n, _, _, v in verdicts) + " |\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
