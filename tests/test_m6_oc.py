# M6 opencode_client 单测（CI 无 node/GPU；REST 用 httpx.MockTransport，事件用 T-M6-2 抓包 fixture）
import asyncio
import json
from pathlib import Path

import httpx
import pytest

from opencode_client.client import OpencodeClient
from opencode_client.events import EventHub
from opencode_client.rest import OcRest
from opencode_client.serve import NO_WINDOW, ServeProcess, isolated_env, parse_ready
from opencode_client.sse import SseParser
from opencode_client.types import (OcConfig, OcLink, OcPermission, OcText, OcTool,
    OcTurnDone)

FIX = Path(__file__).parent / "fixtures"
WS = str(Path("D:/work/voice-code/tools/oc2-home/ws").resolve())
CAP_SID = "ses_f2939f195ffepa7juE7fBcMwAL"


def ev(type_, **data):
    return {"id": "evt_x", "type": type_, "data": data}


def rest_of(handler):
    return OcRest("http://s", "pw", httpx.AsyncClient(
        base_url="http://s", transport=httpx.MockTransport(handler),
        auth=("opencode", "pw")))


def make_hub(handler=None, own=()):
    got = []
    hub = EventHub(rest_of(handler or (lambda r: httpx.Response(200, json={}))),
                   WS, got.append)
    hub.own.update(own)
    return hub, got


# ---------- sse.py ----------
def test_sse_single_data_frame():
    assert SseParser().feed(b'data: {"type":"a"}\n\n') == [{"type": "a"}]


def test_sse_comment_heartbeat_ignored():
    assert SseParser().feed(b": heartbeat\n\ndata: {\"type\":\"b\"}\n\n") == [{"type": "b"}]


def test_sse_split_across_chunks():
    p = SseParser()
    assert p.feed(b'data: {"ty') == []
    assert p.feed(b'pe":"c"}\n') == []
    assert p.feed(b"\n") == [{"type": "c"}]


def test_sse_bad_json_skipped():
    assert SseParser().feed(b'data: {oops}\n\ndata: {"type":"d"}\n\n') == [{"type": "d"}]


def test_sse_multiline_data_one_frame():
    out = SseParser().feed(b'data: {"type":"e"}\ndata: {"type":"f"}\n\n')
    assert [o["type"] for o in out] == ["e", "f"]


def test_sse_flush_without_trailing_blank():
    p = SseParser()
    p.feed(b'data: {"type":"g"}\n')
    assert [o["type"] for o in p.flush()] == ["g"]


# ---------- events.py: translate ----------
def test_translate_delta_and_ended():
    hub, _ = make_hub(own={"s1"})
    got = [hub.translate(ev("session.text.delta", sessionID="s1", delta="你好")),
           hub.translate(ev("session.text.ended", sessionID="s1", text="你好世界"))]
    assert got == [OcText("s1", "你好", False), OcText("s1", "你好世界", True)]


def test_translate_permission():
    hub, _ = make_hub(own={"s1"})
    out = hub.translate(ev("permission.asked", sessionID="s1", id="per_1",
                           action="shell", message="run?"))
    assert out == OcPermission("s1", "per_1", "shell", "run?")


def test_translate_filters_other_session():
    hub, _ = make_hub(own={"s1"})
    assert hub.translate(ev("session.text.delta", sessionID="s2", delta="x")) is None


def test_translate_filters_wrong_location():
    hub, _ = make_hub(own={"s1"})
    e = ev("session.text.delta", sessionID="s1", delta="x")
    e["location"] = {"directory": "C:/elsewhere"}
    assert hub.translate(e) is None


def test_translate_same_dir_different_slash_style():
    hub, _ = make_hub(own={"s1"})
    e = ev("session.text.delta", sessionID="s1", delta="x")
    e["location"] = {"directory": WS.replace("\\", "/")}
    assert hub.translate(e) is not None


def test_translate_sessionless_and_cost():
    hub, got = make_hub()
    out = hub.translate(ev("server.connected"))
    hub.translate(ev("session.usage.updated", sessionID="s1", cost=0.25))
    assert isinstance(out, OcLink) and out.state == "connected"
    assert hub._cost["s1"] == 0.25


def test_translate_unknown_ignored():
    hub, _ = make_hub(own={"s1"})
    assert hub.translate(ev("session.reasoning.delta", sessionID="s1", delta="..")) is None
    assert hub.translate({"type": "plugin.updated", "data": {}}) is None


def test_execution_resolves_future():
    async def run():
        def h(req):
            return httpx.Response(200, json={"items": [
                {"type": "assistant",
                 "content": [{"type": "text", "text": "收到"}]}]})
        hub, _ = make_hub(h, own={"s1"})
        fut = asyncio.get_running_loop().create_future()
        hub.pending["s1"] = fut
        hub.translate(ev("session.execution.succeeded", sessionID="s1"))
        done = await asyncio.wait_for(fut, 2)
        assert done == OcTurnDone("s1", "succeeded", "收到", None, 0.0)
        assert hub.pending == {}
    asyncio.run(run())


def test_execution_error_from_messages():
    async def run():
        def h(req):
            return httpx.Response(200, json={"items": [
                {"type": "assistant", "content": [],
                 "error": {"message": "provider down"}}]})
        hub, _ = make_hub(h, own={"s1"})
        fut = asyncio.get_running_loop().create_future()
        hub.pending["s1"] = fut
        hub.translate(ev("session.execution.failed", sessionID="s1"))
        done = await asyncio.wait_for(fut, 2)
        assert done.error == "provider down" and done.outcome == "failed"
    asyncio.run(run())


def test_resync_completes_turn_after_drop():
    async def run():
        def h(req):
            return httpx.Response(200, json={"items": [
                {"type": "idle", "outcome": "succeeded"}]})
        hub, got = make_hub(h, own={"s1"})
        fut = asyncio.get_running_loop().create_future()
        hub.pending["s1"] = fut
        await hub._resync()
        assert (await fut).outcome == "succeeded"
    asyncio.run(run())


def test_fixture_frames_replay():
    text = (FIX / "m6_v2016_frames_turn1.jsonl").read_text(encoding="utf-8")
    p = SseParser()
    frames = p.feed(text.encode("utf-8")) + p.flush()
    assert frames, "fixture 应至少解出一帧"
    hub, got = make_hub(own={CAP_SID})
    n_delta = sum(1 for f in frames if f.get("type") == "session.text.delta")
    assert n_delta > 0
    texts = [t for t in (hub.translate(f) for f in frames)
             if isinstance(t, OcText)]
    assert len(texts) >= n_delta and all(t.session_id == CAP_SID for t in texts)


# ---------- M6.1: tool 事件关联 ----------
def test_tool_started_then_called_resolves_name():
    hub, _ = make_hub(own={"s1"})
    a = hub.translate(ev("session.tool.input.started", sessionID="s1",
                         id="tc_1", name="voice-end"))
    b = hub.translate(ev("session.tool.called", sessionID="s1",
                         id="tc_1", input={"reason": "bye"}, executed=False))
    assert a == OcTool("s1", "tc_1", "voice-end", "started")
    assert b == OcTool("s1", "tc_1", "voice-end", "called", {"reason": "bye"})


def test_tool_called_unknown_id_blank_name():
    hub, _ = make_hub(own={"s1"})
    b = hub.translate(ev("session.tool.called", sessionID="s1", id="tc_9",
                         input={}, executed=False))
    assert b.name == "" and b.phase == "called"


def test_tool_map_pruned_on_finish():
    async def run():
        hub, _ = make_hub(lambda r: httpx.Response(200, json={"items": []}), own={"s1"})
        hub.translate(ev("session.tool.input.started", sessionID="s1", id="tc_1", name="voice-end"))
        fut = asyncio.get_running_loop().create_future()
        hub.pending["s1"] = fut
        hub.translate(ev("session.execution.succeeded", sessionID="s1"))
        await asyncio.wait_for(fut, 2)
        assert hub._toolnames == {}
    asyncio.run(run())


def test_tool_events_respect_session_filter():
    hub, _ = make_hub(own={"s1"})
    assert hub.translate(ev("session.tool.input.started", sessionID="s2",
                            id="t", name="x")) is None


# ---------- rest.py ----------
def test_rest_paths_auth_and_returns():
    async def run():
        cap = []
        def h(req):
            cap.append(req)
            return httpx.Response(200, json={"data": {"id": "ses_1"},
                                             "interrupted": True,
                                             "version": "2.0.16"})
        r = rest_of(h)
        assert await r.session_create("t", "D:/w") == "ses_1"
        assert cap[-1].method == "POST" and cap[-1].url.path == "/api/session"
        assert cap[0].headers["Authorization"].startswith("Basic ")
        await r.prompt("s1", "hi")
        assert json.loads(cap[-1].content)["text"] == "hi"
        assert await r.interrupt("s1") is True
        await r.reply_permission("s1", "per_1", "once")
        assert json.loads(cap[-1].content)["decision"] == "once"
        await r.aclose()
    asyncio.run(run())


def test_rest_409_maps_to_error():
    async def run():
        r = rest_of(lambda req: httpx.Response(409, json={"name": "ConflictError"}))
        with pytest.raises(httpx.HTTPStatusError):
            await r.prompt("s1", "x")
        await r.aclose()
    asyncio.run(run())


def test_rest_assistant_final_text():
    async def run():
        items = {"items": [{"type": "user", "text": "q"},
                           {"type": "assistant",
                            "content": [{"type": "text", "text": "答"},
                                        {"type": "tool"}],
                            "error": {"message": "boom"}}]}
        r = rest_of(lambda req: httpx.Response(200, json=items))
        assert await r.assistant_final_text("s1") == ("答", "boom")
        multi = {"items": [{"type": "assistant", "content": [{"type": "text", "text": "再见"}]},
                           {"type": "assistant", "content": [{"type": "tool"}]}]}
        r2 = rest_of(lambda req: httpx.Response(200, json=multi))
        assert await r2.assistant_final_text("s1") == ("再见", None)
        await r.aclose()
    asyncio.run(run())


def test_rest_final_text_direction_pinned_by_fixture():
    """T4 回归钉：真机 /message 返回"新→旧"，取反方向会拿到上一轮答案。"""
    async def run():
        body = json.loads((FIX / "m6_v2016_msgs_turn2.json").read_text(encoding="utf-8"))
        assert body["data"][0]["type"] == "idle"               # 证明确是新→旧
        r = rest_of(lambda req: httpx.Response(200, json=body))
        text, _ = await r.assistant_final_text("s1")
        assert text.startswith("在数字游戏中") and len(text) == 569   # 本轮正文
        assert text != "收到"                                   # "收到"=上一轮答案，方向错就会拿到它
        assert "We need" not in text                           # 同条消息里的 reasoning part 不得混入
        await r.aclose()
    asyncio.run(run())


# ---------- serve.py ----------
def test_parse_ready():
    assert parse_ready('{"url":"http://127.0.0.1:5555"}') == "http://127.0.0.1:5555"


def test_isolated_env():
    env = isolated_env(OcConfig(home=Path("H")), "pw123")
    assert env["XDG_DATA_HOME"].endswith(str(Path("H") / "data"))
    assert env["XDG_CONFIG_HOME"].endswith(str(Path("H") / "config"))
    assert env["OPENCODE_PASSWORD"] == "pw123"


def test_serve_start_flags_and_stop_stdin(monkeypatch):
    calls = {}

    class FakeStd:
        def close(self):
            calls["closed"] = True

    class FakeRead:
        async def readline(self):
            return b'{"url":"http://127.0.0.1:9"}\n'

    class FakeProc:
        def __init__(self):
            self.pid, self.returncode, self.stdin, self.stdout = 4242, None, FakeStd(), FakeRead()

        def terminate(self):
            calls["terminated"] = True

        async def wait(self):
            self.returncode = 0

    async def fake_exec(*args, **kw):
        calls.update(args=args, kw=kw)
        return FakeProc()
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    async def run():
        s = await ServeProcess.start(OcConfig(directory="D:/w"))
        assert s.url == "http://127.0.0.1:9" and s.pid == 4242
        assert calls["args"][1:] == ("serve", "--stdio")
        assert calls["kw"]["creationflags"] == NO_WINDOW
        await s.stop()
        assert calls.get("closed") and not calls.get("terminated")
    asyncio.run(run())


# ---------- client.py ----------
def make_client(handler=None):
    hub, got = make_hub(handler)
    return OpencodeClient(OcConfig(), hub._rest, hub, None, None), got


def test_client_session_new_registers():
    async def run():
        c, _ = make_client(lambda r: httpx.Response(200, json={"data": {"id": "ses_x"}}))
        assert await c.session_new("t") == "ses_x"
        assert "ses_x" in c._hub.own
    asyncio.run(run())


def test_client_send_serial_guard():
    async def run():
        c, _ = make_client()
        f1 = await c.send("s1", "a")
        with pytest.raises(RuntimeError):
            await c.send("s1", "b")
        c._hub.pending["s1"].set_result(OcTurnDone("s1", "succeeded", "a", None))
        assert (await f1).outcome == "succeeded"
    asyncio.run(run())


def test_client_send_prompt_failure_cleans_pending():
    async def run():
        c, _ = make_client(lambda r: httpx.Response(409, json={}))
        with pytest.raises(httpx.HTTPStatusError):
            await c.send("s1", "a")
        assert c._hub.pending == {}
    asyncio.run(run())
