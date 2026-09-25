"""M7 T7c 克隆方案多句稳定性验证: 站录 prompt 续写克隆 × 6 句不同文本, 查跨句音色一致性与内容正确性。
设计: docs/0923工作/tts-design.md §音色锁定 + docs/0925工作/tts-voice-lock-plan.md; prompt=voice_candidates/doubao/prompt_doubao.wav, prompt_text 取其 json 的 asr_text。
前置: GPU 空闲; 首次带 prompt 生成有一次性预热(已内置哑句)。
步骤: 1) 每句: 克隆合成 → 落盘 recordings/m7_t7c_s{N}.wav → 播放 → 本地 ASR 核对内容并打印
      2) 每句听完即时判定: 音色是否与前句同一人、有无电音/失控/截断
通过标准: [T7c-1] 6/6 句音色一致且贴合参考人; [T7c-2] 6/6 ASR 内容与目标句一致(容差:语气词);
          [T7c-3] 无 badcase 重试(观察 stderr)、无句内音色漂移。
"""
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from asr.pipeline import AsrConfig, build_recognizer  # noqa: E402
from tts.tts import SR_DEFAULT, TtsConfig, default_model_factory  # noqa: E402

PROMPT_WAV = ROOT / "models" / "voice_candidates" / "doubao" / "prompt_doubao.wav"
PROMPT_TEXT = json.loads((PROMPT_WAV.parent / "prompt_doubao.json")
                         .read_text(encoding="utf-8"))["asr_text"]
OUT_DIR = ROOT / "human-test" / "recordings"
SENTENCES = [
    "你好，我是小码，你的语音助手。",
    "打开地图看看右上角有没有野怪。",
    "把音量调到百分之三十。",
    "刚才那波操作太秀了，五个人全被留下来，直接一波高地。",
    "今天下午八点开始水友赛报名，记得提前组队。",
    "Boss还有百分之三的血，开嗜血，这波一定能过！",
]


def play(samples: np.ndarray, sr: int) -> None:
    import sounddevice as sd
    sd.play(np.clip(samples, -1.0, 1.0), sr)
    sd.wait()


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("[T7c] 加载 ASR + TTS (TTS 含带 prompt 哑句预热, 可能数分钟)...")
    rec = build_recognizer(AsrConfig())
    model = default_model_factory(TtsConfig())
    sr = int(getattr(model.tts_model, "sample_rate", SR_DEFAULT))
    kw = dict(prompt_wav_path=str(PROMPT_WAV), prompt_text=PROMPT_TEXT,
              inference_timesteps=10, retry_badcase_max_times=1)
    model.generate(text="好的。", **kw)
    results = []
    for i, s in enumerate(SENTENCES, 1):
        w = np.asarray(model.generate(text=s, **kw), dtype=np.float32)
        out = OUT_DIR / f"m7_t7c_s{i}.wav"
        sf.write(str(out), w, sr)
        x16 = np.interp(np.linspace(0, len(w) - 1, int(len(w) * 16000 / sr)),
                        np.arange(len(w)), w).astype(np.float32)
        st = rec.create_stream()
        st.accept_waveform(16000, x16)
        rec.decode_stream(st)
        hyp = st.result.text
        print(f"\n[{i}/6] {s}\n      合成 {len(w)/sr:.1f}s → {out.name}"
              f"\n      ASR: {hyp}")
        play(w, sr)
        v = input("      音色一致+内容对 回车=OK, 否则写问题: ").strip()
        results.append((i, s, hyp, round(len(w) / sr, 1), v))
    bad = [r for r in results if r[4]]
    print("\n[通过标准] T7c-1 6/6同一人 / T7c-2 6/6内容对(见上ASR行) / T7c-3 无重试无漂移")
    verdict = input("[人类] 结论(如 PASS 可作基线 / FAIL 哪几句什么问题): ").strip()
    res = ROOT / "human-test" / f"RESULTS-{dt.date.today().isoformat()}.md"
    header = "# human-test 结果记录\n\n| 时间 | 用例 | 结果 | 数据/备注 |\n| ---- | ---- | ---- | ---- |\n"
    if not res.exists():
        res.write_text(header, encoding="utf-8")
    with res.open("a", encoding="utf-8") as fh:
        fh.write(f"| {dt.datetime.now():%H:%M} | M7 T7c 克隆多句稳定性 | {verdict or '(未填)'} | "
                 f"标注问题 {len(bad)} 句: "
                 + "; ".join(f"s{r[0]}={r[4] or 'ok'}" for r in results) + " |\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
