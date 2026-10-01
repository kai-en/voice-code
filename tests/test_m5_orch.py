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
    assert strip_wake("小码小码，帮我开单") == "帮我开单"        # 全词+逗号一起剥(0928 正则优先级回归)
    assert strip_wake("小码，停") == "停"                        # 半词也剥(keywords.txt "小码小码"→自动派生)
    assert strip_wake("小码小码小码小码 停一下") == "停一下"      # 连喊两遍只剥 ≤2 次
    assert strip_wake("帮我看看小码小码") == "帮我看看小码小码"   # 句中不剥, 只管前缀
    assert strip_wake("小马小马，帮我开单") == "小马小马，帮我开单"  # 同音剥不动(R2 已知: 交给 M13 回音门/LLM 错字规则)


def test_strip_wake_custom_keyword(tmp_path, monkeypatch):
    import orchestrator.core as core
    f = tmp_path / "keywords.txt"
    f.write_text("d x iǎo à i :1.5 @小爱小爱\n", encoding="utf-8")
    monkeypatch.setattr(core, "KwsConfig", lambda: type("C", (), {"keywords_file": f})())
    monkeypatch.setattr(core, "_WAKE_RE_CACHE", {})
    assert core.strip_wake("小爱小爱，帮我开灯") == "帮我开灯"
    assert core.strip_wake("小爱，开灯") == "开灯"                    # 半词派生
    assert core.strip_wake("小码小码，开灯") == "小码小码，开灯"       # 自定义后不再认"小码"


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
        self.hotwords = []
        self.pending = False              # audio_pending 可控开关(提交闸用例)
    def set_active(self, on):
        self.active = on
    def audio_pending(self):
        return self.pending
    def set_hotwords(self, words):
        from asr.pipeline import normalize_hotwords
        csv = normalize_hotwords(list(words) if isinstance(words, (list, tuple)) else words)
        if csv is not None:
            self.hotwords.append(csv)
        return csv


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


def test_collect_commit_deferred_while_audio_pending():
    """3s 到期但 audio_pending(在说/在解码)→推迟提交；两句合并一次发(防第二句落进 R3 被吞)。"""
    async def _run():
        orch, asr, tts, oc, now = build()
        fut = asyncio.get_running_loop().create_future()
        oc.send_fut = fut
        task = await drive(orch, [KwsHit("小码", 0), AsrText("第一句", 0, 0.5)])
        try:
            asr.pending = True                       # 第二句还在说: VAD/解码器持有在飞样本
            orch.collect_deadline = now[0]           # 模拟第一句的 3s 静默到期
            await orch.tick(); await asyncio.sleep(0.02)
            assert orch.state == COLLECT and oc.sent == []
            assert orch.collect_deadline == now[0] + 0.5     # 0.5s 后重试
            orch.post(AsrText("第二句", 0, 0.5)); await asyncio.sleep(0.02)   # 迟到句入 buf 重锚
            assert orch.collect_deadline == now[0] + 3.5     # 静默窗含 0.5s 起头确认余量
            assert orch._defer_logged is False             # 重锚 → 推迟 episode 重新计
            asr.pending = False
            orch.collect_deadline = now[0]
            await orch.tick(); await asyncio.sleep(0.02)
            assert oc.sent == [("ses_1", "第一句第二句")]
            assert orch.state == RUNNING
        finally:
            fut.cancel()
            await finish(task, orch)
    asyncio.run(_run())


def test_collect_defer_cap_force_fire():
    """audio_pending 长期为真(如回声漏 AEC) → 推迟满 cap 强提交, COLLECT 不卡死。"""
    async def _run():
        orch, asr, tts, oc, now = build()
        fut = asyncio.get_running_loop().create_future()
        oc.send_fut = fut
        task = await drive(orch, [KwsHit("小码", 0), AsrText("卡住的半句", 0, 0.5)])
        try:
            asr.pending = True
            orch.collect_deadline = now[0]
            await orch.tick(); await asyncio.sleep(0.02)     # 首次推迟, _defer_start=now
            now[0] += 9.0
            orch.collect_deadline = now[0]
            await orch.tick(); await asyncio.sleep(0.02)     # 未到 cap, 继续推迟
            assert oc.sent == []
            now[0] += 1.0                                    # 距首推 10s = cap
            orch.collect_deadline = now[0]
            await orch.tick(); await asyncio.sleep(0.02)
            assert oc.sent == [("ses_1", "卡住的半句")] and orch.state == RUNNING
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
    """解码迟到 5s：deadline 锚在"说完+3s+确认余量"，已过期就立刻成轮，不再白等 3s。"""
    async def _run():
        orch, asr, tts, oc, now = build()
        task = await drive(orch, [KwsHit("x", 0)])
        try:
            orch.post(AsrText("早说完的话", 0, 0.5, end_ts=now[0] - 5.0))
            await asyncio.sleep(0.02)
            assert orch.collect_deadline == now[0] - 1.5
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
            orch.post(AsrText("刚说完", 0, 0.5, end_ts=now[0] + 0.5))   # 句尾离唤醒锚 ≥0.5s, 不落 M13 回音窗
            await asyncio.sleep(0.02)
            assert orch.collect_deadline == now[0] + 4.0     # base(+0.5) + silence(3) + confirm(0.5)
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
            orch.post(OcText("ses_1", "收到。", final=False)); await asyncio.sleep(0.02)   # 出声→回答期
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
        orch.post(OcText("ses_1", "先应一声。", final=False)); await asyncio.sleep(0.02)   # 出声→回答期
        orch.post(AsrText("补充半句", 0, 0.5))
        await asyncio.sleep(0.25)
        assert oc.interrupts == ["ses_1"] and orch.state == COLLECT
        assert orch.buf == "补充半句" and len(oc.sent) == 1
        await tk
        orch.request_stop(); await asyncio.wait_for(task, 2)
    asyncio.run(_run())


def test_blank_sentences_are_not_spoken():
    """delta 里带 \\n\\n 时断句会产出纯换行"句子"：不得进口播、不得计入 spoken_len。"""
    async def _run():
        orch, asr, tts, oc, now = build()
        fut = asyncio.get_running_loop().create_future()
        oc.send_fut = fut
        task = await drive(orch, [KwsHit("x", 0), AsrText("问一句", 0, 0.5)])
        try:
            orch.collect_deadline = now[0]
            await orch.tick(); await asyncio.sleep(0.02)
            for d in ["第一句。\n\n", "第二句！"]:
                orch.post(OcText("ses_1", d, final=False))
                await asyncio.sleep(0.02)
            assert tts.spoken[1:] == ["第一句。", "第二句！"], tts.spoken
            assert orch.spoken_len == 8                      # "第一句。"4 + "第二句！"4, 换行不计
        finally:
            fut.cancel()
            await finish(task, orch)
    asyncio.run(_run())


# ---------- 打断 = 追加重问（_sent 前置；真机 22:27 答非所问的修复） ----------
def test_barge_in_resend_carries_previous_question():
    """X1 在飞时被 X2 打断 → X2 必须发 X1+X2 整轮，而不是只发后半句。"""
    async def _run():
        orch, asr, tts, oc, now = build()
        fut = asyncio.get_running_loop().create_future()
        oc.send_fut = fut
        task = await drive(orch, [KwsHit("x", 0), AsrText("我在打幽魂角斗士", 0, 0.5)])
        try:
            orch.collect_deadline = now[0]
            await orch.tick(); await asyncio.sleep(0.02)                 # X1 发出
            assert orch._sent == "我在打幽魂角斗士"
            orch.post(OcText("ses_1", "收到。", final=False)); await asyncio.sleep(0.02)   # 出声→回答期
            orch.post(AsrText("但是我们也会互相打倒", 0, 0.5))            # barge-in 打断
            await asyncio.sleep(0.02)
            orch.post(OcTurnDone("ses_1", "interrupted", "", None, 0))   # 陈旧终 → 早退, _sent 保留
            await asyncio.sleep(0.02)
            assert orch._sent == "我在打幽魂角斗士"
            orch.collect_deadline = now[0]
            await orch.tick(); await asyncio.sleep(0.02)
            assert oc.sent[-1][1] == "我在打幽魂角斗士\n但是我们也会互相打倒"
            assert len(oc.sent) == 2 and oc.interrupts == ["ses_1"]
        finally:
            fut.cancel()
            await finish(task, orch)
    asyncio.run(_run())


def test_sent_cleared_after_settled_turn():
    """正常收场(succeeded)必须清前缀，否则每轮都拖着全部历史。"""
    async def _run():
        orch, asr, tts, oc, now = build()
        fut = asyncio.get_running_loop().create_future()
        oc.send_fut = fut
        task = await drive(orch, [KwsHit("x", 0), AsrText("问题A", 0, 0.5)])
        try:
            orch.collect_deadline = now[0]
            await orch.tick(); await asyncio.sleep(0.02)
            assert orch._sent == "问题A"
            fut.set_result(OcTurnDone("ses_1", "succeeded", "答A。", None, 0))
            await asyncio.sleep(0.05)
            assert orch._sent == ""
            oc.send_fut = None                                           # 换新的未收场 Future
            orch.post(AsrText("问题B", 0, 0.5)); await asyncio.sleep(0.02)
            orch.collect_deadline = now[0]
            await orch.tick(); await asyncio.sleep(0.02)
            assert oc.sent[-1][1] == "问题B" and len(oc.sent) == 2
        finally:
            await finish(task, orch)
    asyncio.run(_run())


def test_topic_change_barge_in_still_prepends():
    """换话题型打断也照拼（B1 本来就在会话历史里, 前置不引入模型看不到的信息）——
    钉住"无条件拼接"这个设计决定, 防将来有人塞 NLU/关键词判断。"""
    async def _run():
        orch, asr, tts, oc, now = build()
        fut = asyncio.get_running_loop().create_future()
        oc.send_fut = fut
        task = await drive(orch, [KwsHit("x", 0), AsrText("长任务", 0, 0.5)])
        try:
            orch.collect_deadline = now[0]
            await orch.tick(); await asyncio.sleep(0.02)
            orch.post(OcText("ses_1", "收到。", final=False)); await asyncio.sleep(0.02)   # 出声→回答期
            orch.post(AsrText("停，换个事", 0, 0.5)); await asyncio.sleep(0.02)
            orch.post(OcTurnDone("ses_1", "interrupted", "", None, 0)); await asyncio.sleep(0.02)
            orch.collect_deadline = now[0]
            await orch.tick(); await asyncio.sleep(0.02)
            assert oc.sent[-1][1] == "长任务\n停，换个事"
        finally:
            fut.cancel()
            await finish(task, orch)
    asyncio.run(_run())


# ---------- 打断门控（0927 需求: docs/0927工作/kws-gated-llm-interrupt-req.md） ----------
def test_thinking_phase_ignores_asr():
    """RUNNING 思考期(未出声)：任意 ASR 出句一律无响应——不打断、不入 buf、状态不动。"""
    async def _run():
        orch, asr, tts, oc, now = build()
        fut = asyncio.get_running_loop().create_future()
        oc.send_fut = fut
        task = await drive(orch, [KwsHit("x", 0), AsrText("长任务", 0, 0.5)])
        try:
            orch.collect_deadline = now[0]
            await orch.tick(); await asyncio.sleep(0.02)
            assert orch.state == RUNNING
            for i in range(3):
                orch.post(AsrText(f"跟观众说话{i}", 0, 0.5)); await asyncio.sleep(0.02)
            assert oc.interrupts == [] and tts.stops == 0
            assert orch.state == RUNNING and orch.buf == "" and len(oc.sent) == 1
        finally:
            fut.cancel()
            await finish(task, orch)
    asyncio.run(_run())


def test_kws_interrupts_thinking_phase_and_collects_next():
    """思考期 KWS 命中→打断并念 ack 确认(10-01 反转 Q1: 静默打断不可辨)；激活词转写剥空不污染 buf；后续句正常采集。"""
    async def _run():
        orch, asr, tts, oc, now = build()
        fut = asyncio.get_running_loop().create_future()
        oc.send_fut = fut
        task = await drive(orch, [KwsHit("x", 0), AsrText("长任务", 0, 0.5)])
        try:
            orch.collect_deadline = now[0]
            await orch.tick(); await asyncio.sleep(0.02)
            orch.post(KwsHit("小码小码", 0)); await asyncio.sleep(0.02)
            assert orch.state == COLLECT and oc.interrupts == ["ses_1"] and tts.stops >= 1
            assert tts.spoken == ["在呢。"]                               # 双停(0.4s)前不出口
            await asyncio.sleep(0.5)
            assert tts.spoken == ["在呢。", "在呢。"]                      # 打断确认后补念 ack
            orch.post(AsrText("小码小码", 0, 0.5)); await asyncio.sleep(0.02)
            assert orch.buf == ""                                         # strip_wake 后为空 → 不入 buf
            orch.post(AsrText("停，换个事", 0, 0.5)); await asyncio.sleep(0.02)
            assert orch.buf == "停，换个事" and orch.collect_deadline == now[0] + 3.5
        finally:
            fut.cancel()
            await finish(task, orch)
    asyncio.run(_run())


def test_kws_hit_in_collect_or_perm_still_noop():
    """会话中(COLLECT/PERM) KWS 再响仍无动作——唤醒只属于 IDLE。"""
    async def _run():
        orch, asr, tts, oc, _ = build()
        task = await drive(orch, [KwsHit("x", 0)])
        try:
            orch.post(AsrText("说一句", 0, 0.5)); await asyncio.sleep(0.02)
            orch.post(KwsHit("小码小码", 0)); await asyncio.sleep(0.02)
            assert orch.state == COLLECT and orch.buf == "说一句"
            assert tts.spoken == ["在呢。"] and oc.interrupts == []
        finally:
            await finish(task, orch)
    asyncio.run(_run())


class BoomOc(FakeOc):
    def __init__(self):
        super().__init__()
        self.boom = True

    async def send(self, sid, text):
        if self.boom:
            self.boom = False
            raise RuntimeError("boom")
        return await super().send(sid, text)


def test_send_failure_does_not_duplicate_prefix():
    """send 失败时前缀已随 text 整体还回 buf → 再试不能变成 B1\\nB1\\nB2。"""
    async def _run():
        orch = Orchestrator(OrchConfig(), clock=lambda: 1000.0)
        oc = BoomOc()
        orch.bind(None, FakeAsr(), FakeTts(), oc)
        task = asyncio.create_task(orch.run())
        orch.post(KwsHit("x", 0)); await asyncio.sleep(0.02)
        orch.post(AsrText("B1", 0, 0.5)); await asyncio.sleep(0.02)
        orch.collect_deadline = 0.0
        await orch.tick(); await asyncio.sleep(0.05)
        assert orch._sent == "" and orch.buf == "B1" and orch.state == COLLECT
        orch.post(AsrText("B2", 0, 0.5)); await asyncio.sleep(0.02)
        orch.collect_deadline = 0.0
        await orch.tick(); await asyncio.sleep(0.05)
        assert oc.sent[-1][1] == "B1B2", oc.sent            # buf 内合并是 += 无分隔(既有语义); 关键是前缀没变成 B1\nB1\nB2
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
            orch.post(OcText("ses_1", "收到。", final=False)); await asyncio.sleep(0.02)   # 出声→回答期
            orch.post(AsrText("停，换个事", 0, 0.5))
            await asyncio.sleep(0.05)
            assert orch.state == COLLECT and oc.interrupts == ["ses_1"]
            assert tts.stops >= 1 and orch.buf == "停，换个事"
            await asyncio.sleep(0.5)
            assert tts.spoken == ["在呢。", "收到。"]   # 主播抢话型打断不补 ack（不抢话头），与 KWS 型区分
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
            orch.post(OcText("ses_1", "收到。", final=False)); await asyncio.sleep(0.02)   # 出声→回答期
            orch.post(AsrText("闭嘴", 0, 0.5)); await asyncio.sleep(0.02)   # barge-in
            orch.post(OcTurnDone("ses_1", "interrupted", "", None, 0))     # 旧回合终
            await asyncio.sleep(0.02)
            orch.buf = "任务二"
            orch.collect_deadline = now[0]
            await orch.tick(); await asyncio.sleep(0.02)
            assert oc.sent[-1][1] == "任务一\n任务二" and len(oc.sent) == 2   # 打断=追加重问：带上前半轮
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
            assert orch._sent == ""                                # 退出/换会话必须清前缀
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
