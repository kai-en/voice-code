"""M6.1 voice-end 插件真机验证: 正例帧链(input.started[voice-end]→called→…→TurnDone) + 反例不误触。
前置: tools/oc2-home/config/opencode/plugins/voice-end.ts 已部署 (源在 config/oc2/plugins/)。
判定: 脚本自动比对帧链并打印 PASS/FAIL; 免费池抖动=正例 3 连败(小模型不调工具)→ 记"有条件可行"。
产物: tests/fixtures/m61_voicend_frames.jsonl (真帧, 可回灌单测)。
"""
import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from opencode_client import OcConfig, OcText, OcTool, OcTurnDone, start_opencode  # noqa: E402

WS = str(ROOT / "tools" / "oc2-home" / "ws")
# 钉住免费池具体模型: 实测不钉 model 时默认模型不调 voice-end, 钉了必调
MODEL = "opencode/space-bunny-free"
POSITIVE = "用一句话跟我道别，然后结束本次会话。"
NEGATIVE = "今天天气怎么样？只需回答一句。"


async def one_round(client, raw_frames, text):
    sid = await client.session_new(f"m61-{int(time.time())}")
    fut = await client.send(sid, text)
    done = await asyncio.wait_for(fut, 150)
    tools = [e for e in raw_frames["events"] if isinstance(e, OcTool)
             and e.session_id == sid]
    said = [e for e in raw_frames["events"] if isinstance(e, OcText)
            and e.session_id == sid and e.final]
    return done, tools, said


async def main():
    ws = Path(WS)
    ws.mkdir(parents=True, exist_ok=True)
    raw_frames = {"events": [], "lines": []}

    cfg = OcConfig(directory=WS, model=MODEL)
    got = raw_frames["events"]

    def on_event(ev):
        got.append(ev)

    c = await start_opencode(cfg, on_event)
    ok_pos = ok_neg = False
    try:
        # 加载证据: 服务端已注册插件 → model 端 tools 含 voice-end(行为验证兜底, 无 plugin 事件面)
        for attempt in (1, 2, 3):
            done, tools, _ = await one_round(c, raw_frames, POSITIVE)
            hit = [t for t in tools if t.name == "voice-end" and t.phase == "called"]
            print(f"[m61] 正例 try{attempt}: outcome={done.outcome} "
                  f"tools={[(t.name, t.phase) for t in tools]} 告别='{done.text[:30]}'")
            if hit and done.outcome == "succeeded":
                ok_pos = True
                break
        done, tools, _ = await one_round(c, raw_frames, NEGATIVE)
        ok_neg = not any(t.name == "voice-end" and t.phase == "called" for t in tools) \
            and done.outcome == "succeeded"
        print(f"[m61] 反例: outcome={done.outcome} tools={[(t.name, t.phase) for t in tools]}")
    finally:
        Path(ROOT / "tests/fixtures/m61_tool_events.jsonl").write_text(
            "\n".join(json.dumps({"type": type(e).__name__, **vars(e)}, ensure_ascii=False)
                      for e in got if isinstance(e, (OcTool, OcTurnDone))),
            encoding="utf-8")
        await c.aclose()
    verdict = "PASS" if (ok_pos and ok_neg) else "FAIL"
    print(f"\n[m61] 正例={'OK' if ok_pos else '3连败'} 反例={'OK' if ok_neg else '误触'} → {verdict}")
    res = ROOT / "human-test" / f"RESULTS-{time.strftime('%Y-%m-%d')}.md"
    with res.open("a", encoding="utf-8") as fh:
        fh.write(f"| {time.strftime('%H:%M')} | M6.1 voice-end 插件帧链 | {verdict} | "
                 f"正例3连试内命中={'Y' if ok_pos else 'N'} 反例不误触={'Y' if ok_neg else 'N'} |\n")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
