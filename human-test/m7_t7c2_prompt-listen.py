"""M7 T7c2 prompt_wav 母音色试听(先听后决定, 不做 TTS)。 设计: tts-design.md §音色锁定
前置: 耳机/音箱皆可; 候选已就位 (models/voice_candidates/voxcpm2_demo + kws test_wavs)。
步骤: 逐段播放 → 每段听完输入 采用/不采用(+备注, 如"温柔女声可商用?") → 汇总打印。
通过标准: [T7c2-1] 选出 1 段最接近"温柔中文女声+旁白解说风"的素材;
          [T7c2-2] 注意: voxcpm2_demo 系官方 demo(为模型合成语音, 非原始真人录音),
          kws zh_* 为真人演讲/新闻切片(授权不明)。采用哪段需权衡 AI音/授权两风险。
选完后再把胜出素材接进 m7_t7c_promptwav-listen.py 做克隆合成验证。
"""
import datetime as dt
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
CANDS = [
    ("C1", ROOT / "models/voice_candidates/voxcpm2_demo/prompt1.wav",
     "官方demo·助手女声·6.5s·24k", "你好像有不少问题想问我呢，别心急，我们还有很多很多时间。"),
    ("C2", ROOT / "models/voice_candidates/voxcpm2_demo/prompt2.wav",
     "官方demo·戏剧女声·4.0s·16k", "臣妾要告发熹贵妃私通，会乱后宫，罪不容诛。"),
    ("C3", ROOT / "models/voice_candidates/voxcpm2_demo/vd_scene_latenight.wav",
     "官方demo·深夜电台·10.6s·48k", "夜深了，如果你还醒着，不妨听我讲一个关于远方的故事。没有什么比雨声和一个好故事，更适合这样的夜晚了。"),
    ("C4", ROOT / "models/voice_candidates/voxcpm2_demo/vd_short_girl.wav",
     "官方demo·小女孩·6.7s·48k", "妈妈，妈妈，你快来看，我画了一只大恐龙，它会喷火的。"),
    ("C5", ROOT / "models/voice_candidates/voxcpm2_demo/vd_acoustic_soprano.wav",
     "官方demo·女高音吟诗·11.0s·48k", "春江潮水连海平，海上明月共潮生。滟滟随波千万里，何处春江无月明。"),
    ("C6", ROOT / "models/voice_candidates/voxcpm2_demo/zh_cn.wav",
     "官方demo·科技广播·12.0s·48k", "各位听众朋友，大家好，欢迎收听今天的科技前沿节目。今天我们要聊的话题是人工智能语音合成技术的最新进展。"),
    ("C7", ROOT / "models/sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20/test_wavs/zh_0.wav",
     "kws包·真人演讲·5.6s·16k", "对我做了介绍啊。那么我想说的是呢，大家如果对我的研究感兴趣呢。"),
    ("C8", ROOT / "models/sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20/test_wavs/zh_1.wav",
     "kws包·真人演讲·5.2s·16k", "重点呢，想谈三个问题。首先呢，就是这一轮全球金融动荡的表现。"),
    ("C9", ROOT / "models/sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20/test_wavs/zh_3.wav",
     "kws包·新闻切片·8.0s·16k", "文森特·卡索是全球知名的法国性格派演员。"),
    ("C10", ROOT / "models/sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20/test_wavs/zh_4.wav",
     "kws包·新闻切片·4.6s·16k", "蒋友伯被拍到带着女儿出游。"),
    ("C11", ROOT / "models/sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20/test_wavs/zh_5.wav",
     "kws包·新闻切片·4.2s·16k", "周望军就落实，控物价。"),
    ("C12", ROOT / "models/sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20/test_wavs/zh_6.wav",
     "kws包·新闻切片·3.5s·16k", "朱立伦在上市见面会上表示。"),
]


def main():
    import sounddevice as sd
    verdicts = []
    print("[T7c2] 试听 12 段中文候选 (C2/C3 温柔电台风建议重点听)。重听输入 'r'。\n")
    for tag, path, desc, text in CANDS:
        x, sr = sf.read(str(path), dtype="float32")
        if x.ndim > 1:
            x = x.mean(axis=1)
        while True:
            print(f"[{tag}] {desc}\n      文本: {text}")
            sd.play(np.clip(x, -1.0, 1.0), sr)
            sd.wait()
            v = input("      判定(采用/不采用/备注, r=重听): ").strip()
            if v.lower() != "r":
                verdicts.append((tag, desc.split("·")[1] if "·" in desc else "", v or "不采用"))
                break
    print("\n[汇总]")
    for t, d, v in verdicts:
        print(f"  {t} {d}: {v}")
    res = ROOT / "human-test" / f"RESULTS-{dt.date.today().isoformat()}.md"
    header = "# human-test 结果记录\n\n| 时间 | 用例 | 结果 | 数据/备注 |\n| ---- | ---- | ---- | ---- |\n"
    if not res.exists():
        res.write_text(header, encoding="utf-8")
    pick = input("最终选用编号(如 C3, 无则回车): ").strip()
    with res.open("a", encoding="utf-8") as fh:
        fh.write(f"| {dt.datetime.now():%H:%M} | M7 T7c2 母音色试听 | 选用={pick or '无'} | "
                 + "; ".join(f"{t}:{v}" for t, _, v in verdicts) + " |\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
