# M11 帧编解码（纯函数，无 socket/无 loop 依赖）：事件对象 → 可广播的 JSON 帧。
# 出帧 6 种：hello / state / ev(泛化镜像) / speak / note / err / pong —— 新增事件类零协议改动（设计 §3.2）。
import dataclasses
import json

MAX_TEXT = 2000


def pick(ev):
    if not dataclasses.is_dataclass(ev) or isinstance(ev, type):
        return {}
    out = {}
    for k, v in dataclasses.asdict(ev).items():
        if isinstance(v, str):
            out[k] = v[:MAX_TEXT] + ("…" if len(v) > MAX_TEXT else "")
        elif v is None or isinstance(v, (bool, int, float)):
            out[k] = v
    return out


def ev_frame(ev):
    return {"t": "ev", "kind": type(ev).__name__, "d": pick(ev)}


def state_frame(state):
    return {"t": "state", "state": state}


def speak_frame(text):
    return {"t": "speak", "text": text}


def encode(frame):
    return json.dumps(frame, ensure_ascii=False)
