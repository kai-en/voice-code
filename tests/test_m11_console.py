# M11 控制台单测：帧纯函数 + 分派兜底 + 真 serve（426 / WS 双向 / tap 广播）+ TextIn 状态机(A4/A9/A10)。
import asyncio
import json
import urllib.error
import urllib.request

from asr.pipeline import AsrText
from console.server import ConsoleServer
from kws.kws_wake import KwsHit
from opencode_client import OcText, OcTurnDone
from orchestrator import COLLECT, IDLE, PERM, RUNNING, OrchConfig, Orchestrator, TextIn


class Rec:
    def __init__(self, state=IDLE):
        self.state, self.posts = state, []

    def post(self, ev):
        self.posts.append(ev)


def disp(raw, state=IDLE):
    o = Rec(state)
    return ConsoleServer(port=0, orch=o)._dispatch(raw), o


def test_frames_pure():
    from console import frames
    f = frames.ev_frame(TextIn(text="x" * 3000))
    assert f["kind"] == "TextIn" and len(f["d"]["text"]) == 2001          # 截断 + 省略号
    assert frames.encode(frames.speak_frame("句。")) == '{"t": "speak", "text": "句。"}'


def test_dispatch_rules():
    note, o = disp('{"t":"ask","text":"今天天气"}')
    assert note is None and o.posts[0].text == "今天天气"
    note, o = disp("裸文本也算")
    assert note["code"] == "unknown_frame_as_ask" and o.posts[0].text == "裸文本也算"
    note, o = disp('{"t":"whatever","text":"未知帧"}')
    assert note["code"] == "unknown_frame_as_ask" and o.posts[0].text == "未知帧"
    assert disp('{"t":"ping"}')[0] == {"t": "pong"}
    assert disp('{"t":"ask","text":"  "}')[0] == {"t": "err", "code": "empty_text"}
    note, o = disp('{"t":"stop"}')
    assert note is None and o.posts[0].text == ""
    assert disp('{"t":"perm","decision":"once"}')[0]["code"] == "not_in_perm"
    note, o = disp('{"t":"perm","decision":"reject"}', PERM)
    assert note is None and o.posts[0].text == "拒绝"
    assert ConsoleServer(port=0)._dispatch('{"t":"ask","text":"x"}') == {"t": "err", "code": "not_ready"}


def test_serve_426_and_ws_roundtrip():
    async def _run():
        o = Rec()
        c = ConsoleServer(port=0, orch=o)
        port = await c.start(retry_s=0.1)
        try:
            def get():
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5) as r:
                        return r.status, r.read().decode("utf-8", "replace")
                except urllib.error.HTTPError as e:
                    return e.code, e.read().decode("utf-8", "replace")
            code, body = await asyncio.to_thread(get)
            assert code == 426 and "You cannot access a WebSocket server" in body      # A6′
            from websockets.asyncio.client import connect
            async with connect(f"ws://127.0.0.1:{port}/") as ws:
                hello = json.loads(await asyncio.wait_for(ws.recv(), 5))
                assert hello["t"] == "hello" and hello["v"] == 1 and hello["state"] == IDLE
                await ws.send('{"t":"ask","text":"问"}')
                await ws.send('{"t":"ping"}')
                assert json.loads(await asyncio.wait_for(ws.recv(), 5))["t"] == "pong"
                assert o.posts[0].text == "问"
                c.tap("state", RUNNING)
                assert json.loads(await asyncio.wait_for(ws.recv(), 5)) == {"t": "state", "state": "RUNNING"}
        finally:
            await c.stop()
    asyncio.run(_run())


class FakeAsr:
    def __init__(self):
        self.active = None

    def set_active(self, on):
        self.active = on

    def audio_pending(self):
        return False

    def set_hotwords(self, words):
        from asr.pipeline import normalize_hotwords
        return normalize_hotwords(list(words) if isinstance(words, (list, tuple)) else words)


class FakeTts:
    def __init__(self):
        self.spoken, self.stops = [], 0

    def speak(self, t):
        self.spoken.append(t)
        return 1

    def stop(self):
        self.stops += 1


class FakeOc:
    def __init__(self):
        self.sent = []

    async def session_new(self, title=None):
        return "ses_1"

    async def send(self, sid, text):
        self.sent.append((sid, text))
        return asyncio.Future()

    async def interrupt(self, sid, resume=False):
        pass

    async def reply_permission(self, sid, rid, decision):
        pass


def build():
    orch = Orchestrator(OrchConfig())
    asr, tts, oc = FakeAsr(), FakeTts(), FakeOc()
    orch.bind(None, asr, tts, oc)
    return orch, tts, oc


def test_textin_single_event_no_ack_no_silence():            # A4
    async def _run():
        orch, tts, oc = build()
        task = asyncio.create_task(orch.run())
        orch.post(TextIn(text="直接问一句"))
        await asyncio.sleep(0.05)
        assert oc.sent == [("ses_1", "直接问一句")] and orch.state == RUNNING
        assert tts.spoken == []                               # 不念"在呢。"
        orch.request_stop()
        await asyncio.wait_for(task, 2)
    asyncio.run(_run())


def test_tap_order_event_before_state():                     # A9
    async def _run():
        orch, tts, oc = build()
        seen = []
        orch.tap = lambda k, o: seen.append(k + ":" + (type(o).__name__ if k == "ev" else str(o)))
        task = asyncio.create_task(orch.run())
        orch.post(TextIn(text="问"))
        await asyncio.sleep(0.05)
        orch.post(OcTurnDone("ses_1", "succeeded", "答。", None, 0))
        await asyncio.sleep(0.05)
        assert "ev:OcTurnDone" in seen and "state:COLLECT" in seen
        assert seen == ["ev:TextIn", "state:COLLECT", "state:RUNNING",
                        "ev:OcTurnDone", "speak:答。", "state:COLLECT"]     # A9：ev 先于它引发的 state
        orch.request_stop()
        await asyncio.wait_for(task, 2)
    asyncio.run(_run())


def test_textin_appends_voice_half_sentence():               # A10 / R3
    async def _run():
        orch, tts, oc = build()
        task = asyncio.create_task(orch.run())
        orch.post(KwsHit("小码小码", 0.0))
        orch.post(AsrText("语音半句", 0.0, 1.0))
        await asyncio.sleep(0.02)
        assert orch.state == COLLECT and orch.buf == "语音半句"
        orch.post(TextIn(text="打字追加"))
        await asyncio.sleep(0.05)
        assert oc.sent == [("ses_1", "语音半句\n打字追加")]
        orch.request_stop()
        await asyncio.wait_for(task, 2)
    asyncio.run(_run())


def test_textin_running_barges_in():                         # R1
    async def _run():
        orch, tts, oc = build()
        task = asyncio.create_task(orch.run())
        orch.post(TextIn(text="第一问"))
        await asyncio.sleep(0.02)
        orch.post(TextIn(text="打断重问"))
        await asyncio.sleep(0.05)
        assert tts.stops >= 1 and orch.state == COLLECT
        orch.request_stop()
        await asyncio.wait_for(task, 2)
    asyncio.run(_run())


# ---------- M13 对话流水视图（同一批帧的投影，src/ 零改动） ----------
def test_dialog_render_only_two_party_lines():
    from console.dialog import render
    assert render({"t": "speak", "text": "第一句。\n第二行"}) == "助手：第一句。 第二行"
    assert render({"t": "ev", "kind": "AsrText", "d": {"text": "我说的话"}}) == "你：我说的话"
    assert render({"t": "ev", "kind": "TextIn", "d": {"text": "打字问"}}) == "你：打字问"
    assert render({"t": "ev", "kind": "AsrText", "d": {"text": ""}}) is None      # 空文本(如 stop 帧)不入流水
    assert render({"t": "ev", "kind": "OcTool", "d": {"name": "grep"}}) is None
    assert render({"t": "state", "state": "RUNNING"}) is None      # RUNNING 占位行由 _run 的 30s ticker 画
    assert render({"t": "hello", "v": 1, "port": 8765}) is None
    from console.dialog import think_line
    assert think_line(0.0) == "助手：思考中...(0秒)"
    assert think_line(30.4) == "助手：思考中...(30秒)"
    assert think_line(61.9) == "助手：思考中...(61秒)"
    from console.dialog import _is_running
    assert _is_running({"t": "state", "state": "RUNNING"})
    assert _is_running({"t": "hello", "v": 1, "state": "RUNNING"})
    assert not _is_running({"t": "state", "state": "COLLECT"})
