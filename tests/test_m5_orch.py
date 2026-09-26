# M5 orchestrator 单测：纯函数(textproc) + 状态机(Fake 四件套+假时钟)，无真机/无 GPU/无 node。
import asyncio
import time


from asr.pipeline import AsrText
from kws.kws_wake import KwsHit
from opencode_client import OcLink, OcPermission, OcText, OcTool, OcTurnDone
from orchestrator import COLLECT, IDLE, PERM, RUNNING, OrchConfig, Orchestrator
from orchestrator import textproc
from orchestrator.core import match_permission, strip_wake


# ---------- 分句三规则 ----------
def test_feed_hard_breaks_period_question_exclaim_newline():
    got, rest = textproc.feed("真的吗？好！走\n尾巴")
    assert got == ["真的吗？", "好！", "走\n"] and rest == "尾巴"


def test_feed_soft_break_only_over_long():
    assert textproc.feed("这里有个逗号，但整句还不长。")[0] == ["这里有个逗号，但整句还不长。"]
    assert textproc.feed("长" * 39 + "，尾")[0] == []                  # 阈值是 >40，不是 >=
    got, rest = textproc.feed("长" * 40 + "，尾")
    assert got == ["长" * 40 + "，"] and rest == "尾"
    assert textproc.feed("长" * 40 + "一直拖也没有标点")[0] == []        # 无标点不误切


def test_feed_carries_rest_across_deltas():
    deltas = ["尽管来，我这", "脑子专治各种刁钻问题。查", "得到我就给你带",
              "版本的说法，查不到我也直说不瞎编", "。"]                  # 2026-09-26 真机 delta
    got, rest = [], ""
    for d in deltas:
        sents, rest = textproc.feed(d, rest)
        got += sents
    assert got == ["尽管来，我这脑子专治各种刁钻问题。",
                   "查得到我就给你带版本的说法，查不到我也直说不瞎编。"] and rest == ""


def test_flush_returns_tail_untouched():
    assert textproc.feed("。", "") == (["。"], "")                    # 只看标点，不做任何清洗
    assert textproc.flush("没有标点的尾巴") == ["没有标点的尾巴"]        # 不补标点，整段交 TTS
    assert textproc.flush("") == [] and textproc.flush("   ") == []


def test_permission_words():
    assert match_permission("不行") == "reject"             # 拒绝优先于"行"
    assert match_permission("可以，行") == "once"
    assert match_permission("随便") is None


def test_strip_wake():
    assert strip_wake("小码小码，帮我开单") == "帮我开单"


def test_normalize_peak():
    from tts.tts import normalize_peak
    import numpy as np
    quiet = normalize_peak(np.full(100, 0.05, dtype=np.float32))
    assert abs(float(np.max(np.abs(quiet))) - 10 ** (-1 / 20)) < 1e-4   # 放大到 -1dBFS
    near_silence = normalize_peak(np.full(100, 0.0001, dtype=np.float32))
    assert float(np.max(np.abs(near_silence))) < 0.001                  # 近静音不放大
    hot = normalize_peak(np.full(100, 0.99, dtype=np.float32))
    assert float(np.max(np.abs(hot))) < 0.9                             # 过冲句压回


# ---------- 状态机 ----------
class FakeAsr:
    def __init__(self):
        self.active = None
    def set_active(self, on):
        self.active = on


class FakeTts:
    def __init__(self):
        self.spoken, self.stops = [], 0
    def speak(self, t):
        self.spoken.append(t)
        return 1
    def stop(self):
        self.stops += 1


class FakeOc:
    def __init__(self, send_fut=None):
        self.sessions, self.sent, self.interrupts, self.replies = [], [], [], []
        self.send_fut = send_fut
    async def session_new(self, title=None):
        self.sessions.append(title)
        return "ses_1"
    async def send(self, sid, text):
        self.sent.append((sid, text))
        return self.send_fut or asyncio.Future()
    async def interrupt(self, sid, resume=False):
        self.interrupts.append(sid)
        return True
    async def reply_permission(self, sid, rid, decision):
        self.replies.append((rid, decision))


def build(clock=None):
    now = [clock if clock is not None else 1000.0]
    cfg = OrchConfig()
    orch = Orchestrator(cfg, clock=lambda: now[0])
    asr, tts, oc = FakeAsr(), FakeTts(), FakeOc()
    orch.bind(None, asr, tts, oc)
    return orch, asr, tts, oc, now


async def drive(orch, posts, settle=0.02):
    """启动 run 后台任务，按序投递事件并等待消化。"""
    task = asyncio.create_task(orch.run())
    for ev in posts:
        orch.post(ev)
        await asyncio.sleep(settle)
    return task


async def finish(task, orch):
    orch.request_stop()
    await asyncio.wait_for(task, 2)


def test_wake_to_collect():
    async def _run():
        orch, asr, tts, oc, _ = build()
        task = await drive(orch, [KwsHit("小码小码", 0)])
        try:
            assert orch.state == COLLECT and asr.active is True
            assert tts.spoken == ["在呢。"]
        finally:
            await finish(task, orch)
    asyncio.run(_run())

def test_silence_then_send_full_buffer():
    async def _run():
        orch, asr, tts, oc, now = build()
        fut = asyncio.get_running_loop().create_future()
        oc.send_fut = fut
        task = await drive(orch, [
            KwsHit("小码", 0),
            AsrText("帮我看看", 0, 0.5),
            AsrText("目录里有啥", 0, 0.5),
        ])
        try:
            orch.collect_deadline = now[0]          # 模拟 3s 静默到期
            await orch.tick(); await asyncio.sleep(0.02)
            assert oc.sent == [("ses_1", "帮我看看目录里有啥")]
            assert orch.state == RUNNING
            now[0] += 1
            await orch.tick(); await asyncio.sleep(0.02)
            assert len(oc.sent) == 1                # 已发送后不重复触发
        finally:
            fut.cancel()
            await finish(task, orch)
    asyncio.run(_run())

def test_stream_flushes_tail_at_turn_end():
    S1 = "尽管来，我这脑子专治各种刁钻问题。"
    S2 = "查得到我就给你带版本的说法，查不到我也直说不瞎编"      # 尾巴没标点，flush 不补
    FULL = S1 + S2 + "。"
    async def _run():
        orch, asr, tts, oc, _ = build()
        fut = asyncio.get_running_loop().create_future()
        oc.send_fut = fut
        task = await drive(orch, [
            KwsHit("x", 0), AsrText("说一句", 0, 0.5),
        ])
        try:
            orch.collect_deadline = 1000.0
            await orch.tick(); await asyncio.sleep(0.02)
            for d in ["尽管来，我这", "脑子专治各种刁钻问题。查", "得到我就给你带",
                      "版本的说法，查不到我也直说不瞎编"]:
                orch.post(OcText("ses_1", d, final=False))
                await asyncio.sleep(0.02)
            assert tts.spoken[1:] == [S1]                  # 只有带句号的那句能先出口，其余是尾巴
            orch.post(OcText("ses_1", FULL, final=True))        # 全量校准文本不得重播
            orch.post(OcTurnDone("ses_1", "succeeded", FULL, None, 0))
            await asyncio.sleep(0.05)
            assert tts.spoken[1:] == [S1, S2]                   # 尾巴在回合末被 flush 播出
            assert tts.spoken.count(S2) == 1 and orch.state == COLLECT
            assert orch.spoken_len == len(S1) + len(S2)
        finally:
            await finish(task, orch)
    asyncio.run(_run())


# ---------- 3s 锚点 / barge-in 追加 / 先转态再发（2026-09-26 真机丢话复盘） ----------
def test_collect_deadline_anchors_on_speech_end():
    """解码迟到 5s：deadline 锚在"说完+3s"，已过期就立刻成轮，不再白等 3s。"""
    async def _run():
        orch, asr, tts, oc, now = build()
        task = await drive(orch, [KwsHit("x", 0)])
        try:
            orch.post(AsrText("早说完的话", 0, 0.5, end_ts=now[0] - 5.0))
            await asyncio.sleep(0.02)
            assert orch.collect_deadline == now[0] - 2.0
            await orch.tick(); await asyncio.sleep(0.02)
            assert orch.state == RUNNING and oc.sent[-1][1] == "早说完的话"
        finally:
            await finish(task, orch)
    asyncio.run(_run())


def test_collect_deadline_still_waits_when_fresh():
    async def _run():
        orch, asr, tts, oc, now = build()
        task = await drive(orch, [KwsHit("x", 0)])
        try:
            orch.post(AsrText("刚说完", 0, 0.5, end_ts=now[0]))
            await asyncio.sleep(0.02)
            assert orch.collect_deadline == now[0] + 3.0
            await orch.tick(); await asyncio.sleep(0.02)
            assert orch.state == COLLECT and not oc.sent
        finally:
            await finish(task, orch)
    asyncio.run(_run())


def test_barge_in_appends_pending_half_sentence():
    """barge-in 不得覆盖 buf 里竞态攒下的半句（真机丢过"它的那个叫什么？这个。"）。"""
    async def _run():
        orch, asr, tts, oc, now = build()
        fut = asyncio.get_running_loop().create_future()
        oc.send_fut = fut
        task = await drive(orch, [KwsHit("x", 0), AsrText("第一问", 0, 0.5)])
        try:
            orch.collect_deadline = now[0]
            await orch.tick(); await asyncio.sleep(0.02)
            assert orch.state == RUNNING
            orch.buf = "竞态里攒下的半句"
            orch.post(AsrText("新指令", 0, 0.5)); await asyncio.sleep(0.05)
            assert orch.buf == "竞态里攒下的半句\n新指令"
        finally:
            fut.cancel()
            await finish(task, orch)
    asyncio.run(_run())


class SlowOc(FakeOc):
    def __init__(self):
        super().__init__()
        self.entered = asyncio.Event()

    async def send(self, sid, text):
        self.entered.set()
        self.sent.append((sid, text))
        await asyncio.sleep(0.2)                      # 模拟 REST 在飞
        return self.send_fut or asyncio.Future()


def test_running_state_set_before_send_returns():
    """先转态再 await：否则 await 期间到达的 AsrText 被当"继续采集"而不是"打断"。"""
    async def _run():
        orch = Orchestrator(OrchConfig(), clock=lambda: 1000.0)
        oc = SlowOc()
        orch.bind(None, FakeAsr(), FakeTts(), oc)
        task = asyncio.create_task(orch.run())
        orch.post(KwsHit("x", 0)); await asyncio.sleep(0.02)
        orch.post(AsrText("说一句", 0, 0.5)); await asyncio.sleep(0.02)
        orch.collect_deadline = 0.0                   # 假时钟不动, 手动判定"已静默满 3s"
        tk = asyncio.create_task(orch.tick())
        await oc.entered.wait(); await asyncio.sleep(0.02)
        assert orch.state == RUNNING                  # send 还没返回就已 RUNNING
        orch.post(AsrText("补充半句", 0, 0.5))
        await asyncio.sleep(0.25)
        assert oc.interrupts == ["ses_1"] and orch.state == COLLECT
        assert orch.buf == "补充半句" and len(oc.sent) == 1
        await tk
        orch.request_stop(); await asyncio.wait_for(task, 2)
    asyncio.run(_run())


def test_barge_in_stops_and_recollects():
    async def _run():
        orch, asr, tts, oc, now = build()
        fut = asyncio.get_running_loop().create_future()
        oc.send_fut = fut
        task = await drive(orch, [KwsHit("x", 0), AsrText("长任务", 0, 0.5)])
        try:
            orch.collect_deadline = now[0]
            await orch.tick(); await asyncio.sleep(0.02)
            assert orch.state == RUNNING
            orch.post(AsrText("停，换个事", 0, 0.5))
            await asyncio.sleep(0.05)
            assert orch.state == COLLECT and oc.interrupts == ["ses_1"]
            assert tts.stops >= 1 and orch.buf == "停，换个事"
        finally:
            fut.cancel()
            await finish(task, orch)
    asyncio.run(_run())

def test_turn_busy_guard_no_double_send():
    async def _run():
        orch, asr, tts, oc, now = build()
        task = await drive(orch, [KwsHit("x", 0), AsrText("任务一", 0, 0.5)])
        try:
            orch.collect_deadline = now[0]
            await orch.tick(); await asyncio.sleep(0.02)
            assert orch.state == RUNNING            # send_fut 未完成
            orch.post(AsrText("闭嘴", 0, 0.5)); await asyncio.sleep(0.02)   # barge-in
            orch.post(OcTurnDone("ses_1", "interrupted", "", None, 0))     # 旧回合终
            await asyncio.sleep(0.02)
            orch.buf = "任务二"
            orch.collect_deadline = now[0]
            await orch.tick(); await asyncio.sleep(0.02)
            assert oc.sent[-1][1] == "任务二" and len(oc.sent) == 2
        finally:
            await finish(task, orch)
    asyncio.run(_run())

def test_voice_end_only_exit_channel():
    async def _run():
        orch, asr, tts, oc, _ = build()
        fut = asyncio.get_running_loop().create_future()
        oc.send_fut = fut
        task = await drive(orch, [KwsHit("x", 0), AsrText("再见了", 0, 0.5)])
        try:
            orch.collect_deadline = 1000.0
            await orch.tick(); await asyncio.sleep(0.02)
            orch.post(OcText("ses_1", "再见，祝顺利。", final=False))
            orch.post(OcTool("ses_1", "t1", "voice-end", "called", {}))
            orch.post(OcTurnDone("ses_1", "succeeded", "再见，祝顺利。", None, 0))
            await asyncio.sleep(0.02)
            assert orch.state == IDLE and orch.sid is None and asr.active is False
            assert tts.spoken == ["在呢。", "再见，祝顺利。"]   # 不补 bye（模型已道别）
        finally:
            await finish(task, orch)
    asyncio.run(_run())

def test_permission_flow():
    async def _run():
        orch, asr, tts, oc, now = build()
        fut = asyncio.get_running_loop().create_future()
        oc.send_fut = fut
        task = await drive(orch, [KwsHit("x", 0), AsrText("删文件", 0, 0.5)])
        try:
            orch.collect_deadline = now[0]
            await orch.tick(); await asyncio.sleep(0.02)
            orch.post(OcPermission("ses_1", "per_9", "shell", "rm -rf"))
            await asyncio.sleep(0.02)
            assert orch.state == PERM and "需要授权：shell" in tts.spoken[-1]
            orch.post(AsrText("允许", 0, 0.3))
            await asyncio.sleep(0.02)
            assert oc.replies == [("per_9", "once")] and orch.state == RUNNING
            orch.post(OcPermission("ses_1", "per_10", "edit", "x"))
            await asyncio.sleep(0.02)
            orch.perm_deadline = now[0] - 1
            await orch.tick(); await asyncio.sleep(0.02)
            assert oc.replies[-1] == ("per_10", "reject")   # 超时自动 reject
        finally:
            fut.cancel()
            await finish(task, orch)
    asyncio.run(_run())

def test_failed_turn_and_alerts():
    async def _run():
        orch, asr, tts, oc, _ = build()
        fut = asyncio.get_running_loop().create_future()
        oc.send_fut = fut
        task = await drive(orch, [KwsHit("x", 0), AsrText("做事", 0, 0.5)])
        try:
            orch.collect_deadline = 1000.0
            await orch.tick(); await asyncio.sleep(0.02)
            orch.post(OcTurnDone("ses_1", "failed", "", "provider down", 0))
            await asyncio.sleep(0.02)
            assert tts.spoken[-1] == "任务出错了。" and orch.state == COLLECT
            orch.post(OcLink("reconnecting", "boom"))      # 仅日志，不改状态
            await asyncio.sleep(0.02)
            assert orch.state == COLLECT
        finally:
            fut.cancel()
            await finish(task, orch)
    asyncio.run(_run())



# ---------- 第1轮优化回归 ----------
def test_turn_fut_bridge_posts_end():
    """回归: send 的 Future 完成必须自动回灌队列(死循环根因), 不再依赖手工 post。"""
    async def _run():
        orch, asr, tts, oc, now = build()
        fut = asyncio.get_running_loop().create_future()
        oc.send_fut = fut
        task = await drive(orch, [KwsHit("x", 0), AsrText("说一句", 0, 0.5)])
        try:
            orch.collect_deadline = now[0]          # post 已消化, 再拨表
            await orch.tick(); await asyncio.sleep(0.02)
            assert orch.state == RUNNING
            fut.set_result(OcTurnDone("ses_1", "succeeded", "好。", None, 0))
            await asyncio.sleep(0.05)
            assert orch.state == COLLECT and orch._turn_fut is None   # 桥接生效
        finally:
            await finish(task, orch)
    asyncio.run(_run())
