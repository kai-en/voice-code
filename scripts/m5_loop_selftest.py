# M5 真后端回合自测: 真 oc2 serve(第二实例) + 注入事件驱动状态机, 复现"死循环"场景并验证已修复。
# 场景: 唤醒→说"道别并结束会话"→(真模型调 voice-end)→回合桥接回收→IDLE。旧代码此处必卡 busy 循环。
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from asr.pipeline import AsrText                      # noqa: E402
from kws.kws_wake import KwsHit                       # noqa: E402
from opencode_client import OcConfig, start_opencode  # noqa: E402
from orchestrator import OrchConfig, Orchestrator    # noqa: E402


class FakeAsr:
    def __init__(self):
        self.active = []
    def set_active(self, on):
        self.active.append(on)
    def set_hotwords(self, words):
        return ""


class FakeTts:
    def __init__(self):
        self.spoken = []
        self.stops = 0
    def speak(self, text):
        self.spoken.append(text)
        return 1
    def stop(self):
        self.stops += 1


async def main() -> int:
    cfg = OrchConfig()
    orch = Orchestrator(cfg)
    asr, tts = FakeAsr(), FakeTts()
    oc = await start_opencode(
        OcConfig(directory=str(ROOT / "tools" / "oc2-home" / "ws"), agent="voice"),
        orch.post)
    orch.bind(None, asr, tts, oc)
    task = asyncio.create_task(orch.run())
    try:
        orch.post(KwsHit("小码小码", 0))
        await asyncio.sleep(0.1)
        assert orch.state == "COLLECT", orch.state
        orch.post(AsrText("用一句话跟我道别，然后结束本次会话。", 0, 1.0))
        await asyncio.sleep(0.1)
        orch.collect_deadline = orch.clock()          # 快进 3s 静默
        t0 = orch.clock()
        while orch.state != "IDLE" and orch.clock() - t0 < 150:
            await orch.tick()
            await asyncio.sleep(0.5)
        busy = [s for s in tts.spoken if s == cfg.busy_text]
        print("\n[selftest] state:", orch.state, "| sid:", orch.sid)
        print("[selftest] spoken:", tts.spoken)
        print("[selftest] busy次数:", len(busy), "| vad开关:", asr.active)
        ok = orch.state == "IDLE" and orch.sid is None and not busy
        print("[selftest]", "PASS" if ok else "FAIL(仍可复现卡死)")
        return 0 if ok else 1
    finally:
        orch.request_stop()
        await asyncio.wait_for(task, 3)
        await oc.aclose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
