# 断句（M5 纯函数）。规则只有三条：① 。？！?!换行 无条件断；② 超 LONG 字遇任意标点断；③ 尾巴整段交 TTS 自己念。
# LONG=40 锚点：VoxCPM 长句易不稳(加速/嗡音/KV OOM)，本机实测 40 字≈9s 音频。设计 docs/0925工作/m5-orchestrator-design.md §2。

_HARD = "。？！?!\r\n"
_PUNCT = _HARD + "，,、；;：…—"        # 不收半角 : 否则 10:53 / a.py 会被腰斩
LONG = 40


def feed(buf, rest=""):
    """流式分句 → (成句列表, 未成句尾巴)。尾巴由调用方存着，下次连着新 delta 一起喂。"""
    out, cur = [], ""
    for ch in rest + buf:
        cur += ch
        if ch in _HARD or (len(cur) > LONG and ch in _PUNCT):
            out.append(cur)
            cur = ""
    return out, cur


def flush(rest):
    """规则3：尾巴不补标点、不再切，整段交给 TTS。"""
    t = rest.strip()
    return [t] if t else []
