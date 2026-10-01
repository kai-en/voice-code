# M13 回音门 UT: KwsHit 到达即锚定(monotonic fake clock), end_ts 落窗的 ASR 句(含同音)整段丢弃。
# 设计: docs/0927工作/kws-gated-llm-interrupt-req.md §3 + deepthink M13-echo 方案(纯时间戳, fail-open)。
import asyncio

from asr.pipeline import AsrText
from kws.kws_wake import KwsHit
from opencode_client import OcPermission
from orchestrator import PERM, RUNNING

from test_m5_orch import build, drive, finish


def _sent(text, end_ts):
    return AsrText(text, 0, 0.5, end_ts=end_ts)


def test_thinking_echo_homophone_dropped():
    """思考期 KWS 打断→COLLECT; 同音回音句(小马小马)按时间戳丢, 不入 buf 不刷 deadline。"""
    async def _run():
        orch, asr, tts, oc, now = build()
        fut = asyncio.get_running_loop().create_future()
        oc.send_fut = fut
        task = await drive(orch, [KwsHit("x", 0), AsrText("长任务", 0, 0.5)])
        try:
            orch.collect_deadline = now[0]
            await orch.tick(); await asyncio.sleep(0.02)
            assert orch.state == RUNNING
            orch.post(KwsHit("小码小码", 0)); await asyncio.sleep(0.02)      # wake_mono=1000.0
            assert orch.state == "COLLECT"
            orch.post(_sent("小马小马", now[0] - 0.18)); await asyncio.sleep(0.02)
            assert orch.buf == "" and orch.echo_drops == 1
            assert orch.collect_deadline == 0.0                              # 未当指令刷新
            orch.post(_sent("帮我开单", now[0] + 3.0)); await asyncio.sleep(0.02)
            assert orch.buf == "帮我开单" and orch.echo_drops == 1           # 真指令不误杀
        finally:
            fut.cancel()
            await finish(task, orch)
    asyncio.run(_run())


def test_echo_window_boundaries():
    """Δ 四边界(back=1.2 覆盖 KWS 检测延迟 L≈0.5~0.9s): -1.21 留 / -1.19 杀 / +0.09 杀 / +0.11 留。"""
    async def _run():
        orch, asr, tts, oc, now = build()
        task = await drive(orch, [KwsHit("x", 0)])                           # IDLE 唤醒, 锚=1000.0
        try:
            for ets in (998.79, 998.81, 1000.09, 1000.11):                   # -1.21 / -1.19 / +0.09 / +0.11
                orch.post(_sent("小马小马", ets)); await asyncio.sleep(0.02)
            assert orch.echo_drops == 2 and orch.buf == "小马小马" * 2        # 边界外两句照常入 buf
        finally:
            await finish(task, orch)
    asyncio.run(_run())


def test_merged_short_command_sacrificed():
    """已拍板取舍(宁漏勿杀的镜像面): 连读"小码小码停"单段且指令短→Δ 落窗整段杀, 指令丢失。
    主播免唤醒重说"停"即自愈; 钉住该行为, 防止将来被当 bug"顺手修"成猜文本。"""
    async def _run():
        orch, asr, tts, oc, now = build()
        task = await drive(orch, [KwsHit("x", 0)])
        try:
            orch.post(_sent("小码小码停", now[0] + 0.05)); await asyncio.sleep(0.02)
            assert orch.buf == "" and orch.echo_drops == 1
            orch.post(_sent("停", now[0] + 2.0)); await asyncio.sleep(0.02)   # 重说(独立段)救回
            assert orch.buf == "停"
        finally:
            await finish(task, orch)
    asyncio.run(_run())


def test_merged_speech_survives_and_stripped():
    """连读段(词+指令一段) end_ts 出窗 → 保留, 正字前缀由 strip_wake 剥。"""
    async def _run():
        orch, asr, tts, oc, now = build()
        task = await drive(orch, [KwsHit("x", 0)])
        try:
            orch.post(_sent("小码小码帮我开单", now[0] + 0.8)); await asyncio.sleep(0.02)
            assert orch.buf == "帮我开单" and orch.echo_drops == 0
        finally:
            await finish(task, orch)
    asyncio.run(_run())


def test_zero_end_ts_fail_open():
    """end_ts=0(未知)不杀——既有 20+ 用例的兼容基座。"""
    async def _run():
        orch, asr, tts, oc, now = build()
        task = await drive(orch, [KwsHit("x", 0)])
        try:
            orch.post(AsrText("小马小马", 0, 0.5)); await asyncio.sleep(0.02)  # 不传 end_ts
            assert orch.echo_drops == 0 and orch.buf == "小马小马"
        finally:
            await finish(task, orch)
    asyncio.run(_run())


def test_collect_refire_refreshes_anchor_only():
    """COLLECT 中再喊(>2s 真命中): 状态不变/不念 ack, 但锚刷新→新回音句被杀。"""
    async def _run():
        orch, asr, tts, oc, now = build()
        task = await drive(orch, [KwsHit("x", 0)])
        try:
            orch.post(AsrText("垫底", 0, 0.5, end_ts=now[0] + 2.0)); await asyncio.sleep(0.02)
            now[0] += 5.0
            orch.post(KwsHit("小码小码", 0)); await asyncio.sleep(0.02)      # 刷锚到 1005
            assert orch.state == "COLLECT" and tts.spoken == ["在呢。"] and oc.interrupts == []
            orch.post(_sent("小马小马", now[0] - 0.1)); await asyncio.sleep(0.02)
            assert orch.buf == "垫底" and orch.echo_drops == 1               # 回音杀, 旧 buf 不动
        finally:
            await finish(task, orch)
    asyncio.run(_run())


def test_perm_echo_no_longer_rejects():
    """PERM 期同音回音句曾被 match_permission 判 reject——现在时间戳门先杀, 授权问句不遭殃。"""
    async def _run():
        orch, asr, tts, oc, now = build()
        fut = asyncio.get_running_loop().create_future()
        oc.send_fut = fut
        task = await drive(orch, [KwsHit("x", 0), AsrText("删文件", 0, 0.5)])
        try:
            orch.collect_deadline = now[0]
            await orch.tick(); await asyncio.sleep(0.02)
            orch.post(OcPermission("ses_1", "per_1", "shell", "rm")); await asyncio.sleep(0.02)
            assert orch.state == PERM
            orch.post(_sent("小马小马", now[0] - 0.1)); await asyncio.sleep(0.02)   # 锚=1000 的回音
            assert oc.replies == [] and orch._rid == "per_1" and orch.echo_drops == 1
            orch.post(_sent("允许", now[0] + 2.0)); await asyncio.sleep(0.02)
            assert oc.replies == [("per_1", "once")]                        # 真应答照常走
        finally:
            fut.cancel()
            await finish(task, orch)
    asyncio.run(_run())


def test_repeat_hit_only_refreshes_anchor():
    """cooldown 二喊(repeat=True): 刷锚, 但不念 ack/不打断/不变状态。"""
    async def _run():
        orch, asr, tts, oc, now = build()
        fut = asyncio.get_running_loop().create_future()
        oc.send_fut = fut
        task = await drive(orch, [KwsHit("x", 0), AsrText("长任务", 0, 0.5)])
        try:
            orch.collect_deadline = now[0]
            await orch.tick(); await asyncio.sleep(0.02)
            orch.post(KwsHit("小码小码", 0, repeat=True)); await asyncio.sleep(0.02)
            assert orch.state == RUNNING and tts.stops == 0 and oc.interrupts == []
            assert tts.spoken == ["在呢。"]
        finally:
            fut.cancel()
            await finish(task, orch)
    asyncio.run(_run())
