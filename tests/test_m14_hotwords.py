# M14 动态热词 UT：normalize 校验 / worker set_option / orchestrator 分支 / console 入站帧。全 Fake，无模型。
import asyncio

import numpy as np

from asr.pipeline import AsrText, AsrWorker, normalize_hotwords
from console.server import ConsoleServer
from kws.kws_wake import KwsHit
from opencode_client import OcText, OcTool, OcTurnDone
from orchestrator import RUNNING, HotwordsSet, OrchConfig, Orchestrator, TextIn

from test_m5_orch import FakeAsr, FakeOc, FakeTts, build, drive, finish


# ---------- 校验门面（纯函数） ----------
def test_normalize_passes_and_clears():
    assert normalize_hotwords([]) == ""                                  # 空表 = 清空指令
    assert normalize_hotwords(["毒牙祭坛", "拉维"]) == "毒牙祭坛,拉维"
    assert normalize_hotwords(("盘卷蛇岛",)) == "盘卷蛇岛"                 # tuple 亦可


def test_normalize_rejects_garbage():
    assert normalize_hotwords("毒牙祭坛") is None                         # 非 list → 拒(保留旧表)
    assert normalize_hotwords(["带 空格", "带,逗号"]) is None              # 全脏词 → 拒
    assert normalize_hotwords(["词" * 13]) is None                        # 单词超长 → 剔完 → 拒
    assert normalize_hotwords([{"x": 1}]) is None


def test_normalize_truncates_dedup_and_contain():
    many = [f"甲{i:02d}" for i in range(12)]
    assert normalize_hotwords(many).split(",") == many[:8]                # >8 截前 8
    assert normalize_hotwords(["拉维", "拉维", "祖尔加"]) == "拉维,祖尔加"   # 去重
    assert normalize_hotwords(["毒牙", "毒牙祭坛"]) == "毒牙祭坛"           # 互含留长


def test_worker_applies_stream_option_per_segment():
    class S:
        def __init__(self):
            self.options, self.result = {}, type("R", (), {"text": ""})()
        def set_option(self, k, v):
            self.options[k] = v
        def accept_waveform(self, sr, w):
            pass

    class R:
        def __init__(self):
            self.streams = []
        def create_stream(self):
            self.streams.append(S())
            return self.streams[-1]
        def decode_stream(self, s):
            pass

    rec = R()
    w = AsrWorker(rec, None, lambda t: None)
    w._hotwords = "毒牙祭坛,拉维"
    w.decode_segment(np.zeros(1600, dtype=np.float32), 0.0)
    assert rec.streams[0].options["hotwords"] == "毒牙祭坛,拉维"           # decode 前挂到 stream
    w._hotwords = ""
    w.decode_segment(np.zeros(1600, dtype=np.float32), 0.0)
    assert rec.streams[1].options == {}                                   # 空表不调 set_option(回退 config)


# ---------- orchestrator 分支 ----------
def test_set_hotwords_via_oc_tool_does_not_interrupt():
    async def _run():
        orch, asr, tts, oc, now = build()
        fut = asyncio.get_running_loop().create_future()
        oc.send_fut = fut
        seen = []
        orch.tap = lambda k, o: seen.append((k, o))
        task = await drive(orch, [KwsHit("x", 0), AsrText("长任务", 0, 0.5)])
        try:
            orch.collect_deadline = now[0]
            await orch.tick(); await asyncio.sleep(0.02)
            assert orch.state == RUNNING
            orch.post(OcTool("ses_1", "c1", "set-hotwords", "called",
                             {"words": ["毒牙祭坛", "拉维"]}))
            await asyncio.sleep(0.05)
            assert asr.hotwords == ["毒牙祭坛,拉维"]
            assert orch.state == RUNNING and oc.interrupts == [] and tts.stops == 0   # 装填不碰回合
            assert not [o for _, o in seen if type(o).__name__ == "HotwordsApplied"]  # 回执只进 log 不进 ev 流(0927 拍板)
        finally:
            fut.cancel()
            await finish(task, orch)
    asyncio.run(_run())


def test_hotwords_rejected_keeps_previous():
    async def _run():
        orch, asr, tts, oc, now = build()
        task = await drive(orch, [KwsHit("x", 0), TextIn(text="问")])
        try:
            orch.post(HotwordsSet(words=("盘卷蛇岛",)))
            await asyncio.sleep(0.02)
            orch.post(HotwordsSet(words=("带 空格",)))                      # 脏词 → 整表拒, 旧表不动
            await asyncio.sleep(0.02)
            assert asr.hotwords == ["盘卷蛇岛"]
        finally:
            await finish(task, orch)
    asyncio.run(_run())


def test_idle_clears_hotwords():
    async def _run():
        orch, asr, tts, oc, now = build()
        fut = asyncio.get_running_loop().create_future()
        oc.send_fut = fut
        task = await drive(orch, [KwsHit("x", 0), AsrText("再见了", 0, 0.5)])
        try:
            orch.collect_deadline = now[0]
            await orch.tick(); await asyncio.sleep(0.02)
            orch.post(HotwordsSet(words=("毒牙祭坛",)))
            orch.post(OcTool("ses_1", "t1", "voice-end", "called", {}))
            orch.post(OcTurnDone("ses_1", "succeeded", "再见。", None, 0))
            await asyncio.sleep(0.05)
            assert orch.state == "IDLE" and asr.hotwords == ["毒牙祭坛", ""]   # 退会话自动清
        finally:
            fut.cancel()
            await finish(task, orch)
    asyncio.run(_run())


def test_tool_frame_missing_input_keeps_previous():
    async def _run():
        orch, asr, tts, oc, now = build()
        task = await drive(orch, [KwsHit("x", 0), TextIn(text="问")])
        try:
            orch.post(HotwordsSet(words=("盘卷蛇岛",)))
            await asyncio.sleep(0.02)
            orch.post(OcTool("ses_1", "c2", "set-hotwords", "called", None))          # called 帧不带 input
            orch.post(OcTool("ses_1", "c3", "set-hotwords", "called", {"reason": "x"}))  # 缺 words 键
            await asyncio.sleep(0.05)
            assert asr.hotwords == ["盘卷蛇岛"]                                        # 两次都拒, 旧表不动
        finally:
            await finish(task, orch)
    asyncio.run(_run())


def test_hotwords_survive_barge_in():
    """打断只换回合不清词表（§6 保留行）：装填→回答期→barge-in→COLLECT 后词表原样在。"""
    async def _run():
        orch, asr, tts, oc, now = build()
        fut = asyncio.get_running_loop().create_future()
        oc.send_fut = fut
        task = await drive(orch, [KwsHit("x", 0), AsrText("长任务", 0, 0.5)])
        try:
            orch.collect_deadline = now[0]
            await orch.tick(); await asyncio.sleep(0.02)
            orch.post(HotwordsSet(words=("毒牙祭坛",)))
            orch.post(OcText("ses_1", "收到。", final=False)); await asyncio.sleep(0.05)
            orch.post(AsrText("停，换个事", 0, 0.5)); await asyncio.sleep(0.05)
            assert orch.state == "COLLECT" and asr.hotwords == ["毒牙祭坛"]
        finally:
            fut.cancel()
            await finish(task, orch)
    asyncio.run(_run())


def test_sentinel_pure_hotword_echo():
    echo = AsrWorker._pure_hotword_echo
    assert echo("毒牙祭坛，拉维！", "毒牙祭坛,拉维") is True          # 纯词表拼成 → 记数
    assert echo("毒牙祭坛怎么去", "毒牙祭坛,拉维") is False           # 合法问句不误判(仍照常上抛)
    assert echo("，。", "毒牙祭坛") is False                          # 只有标点不算
    assert echo("随便说点什么", "") is False


# ---------- console 入站帧 ----------
def test_console_hotwords_frame_precedes_ask_fallback():
    orch = Orchestrator(OrchConfig())
    srv = ConsoleServer(port=0)
    srv.attach(orch)
    assert srv._dispatch('{"t":"hotwords","words":["毒牙祭坛","拉维"]}') is None
    assert srv._dispatch('{"t":"hotwords","words":[]}') is None             # 显式空表 = 清空
    err = srv._dispatch('{"t":"hotwords"}')                                  # 缺 words → 拒绝
    assert isinstance(err, dict) and err["code"] == "words_required"
    assert srv._dispatch('{"t":"hotwords","words":"毒牙"}')["code"] == "words_required"   # 非 list 同拒
    kinds = [type(e).__name__ for e in orch._pre]
    assert kinds == ["HotwordsSet", "HotwordsSet"]                           # 一条都没漏进 ask 兜底
