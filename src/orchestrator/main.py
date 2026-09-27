# M5 装配与回收(设计§3)：mic→orch→tts(预热最慢先行)→asr→kws→oc→ready→run+ticker；
# 回收：console.stop → tts.stop → oc.aclose(stdin 关→超时 terminate 自记录 PID) → asr/kws/mic/tts。
# M10/M11 接入：起先 attach_job+acquire 锁(拒绝双开) → 早绑控制台端口(TTS 预热前就要暴露端口冲突)。
import asyncio, contextlib, os, signal, sys
from pathlib import Path

from asr.pipeline import AsrConfig, start_asr
from audio_capture.capture import MicSource, StallWatchdog, device_line
from console import ConsoleServer
from console.server import BindError
from kws.kws_wake import KwsConfig, start_kws
from lifecycle import procguard
from opencode_client import OcConfig, start_opencode
from orchestrator import OrchConfig, Orchestrator
from tts.tts import TtsConfig, start_tts


async def amain() -> int:
    print(f"[m5] starting pid={os.getpid()} cwd={Path.cwd()}", flush=True)
    job = procguard.attach_job()
    if not procguard.acquire(job):
        print(f"[m10] FATAL: 已有实例持锁 {procguard.holder()} → 拒绝双开", file=sys.stderr, flush=True)
        return 3
    print(f"[m10] lock=pid={os.getpid()} job={job}", flush=True)
    if job != "OK":
        print(f"[m10] job={job} → 连坐保证不成立，杀父可能留子（设计 §2.2 边界2）", file=sys.stderr, flush=True)
    console = ConsoleServer()
    try:
        await console.start()
    except BindError as e:
        print(f"[m11] FATAL: {e}", file=sys.stderr, flush=True)
        return 4
    loop = asyncio.get_running_loop()
    orch = Orchestrator(OrchConfig())
    mic = MicSource()
    mic.start()
    print(f"[m1] {device_line(mic)}", flush=True)
    tts = start_tts(TtsConfig(
        backend=os.environ.get("VOICECODE_TTS_BACKEND", "wintts"),
        vox_gain=float(os.environ.get("VOICECODE_VOX_GAIN", "0.5"))), orch.post)   # 无参默认 winTTS（秒级合成）；voxcpm 需显式设环境变量
    asr = start_asr(AsrConfig(), mic, orch.post)
    asr.start()
    kws = start_kws(KwsConfig(), mic, orch.post)
    ws = str(Path(__file__).resolve().parents[2] / "tools" / "oc2-home" / "ws")
    oc = await start_opencode(OcConfig(directory=ws, agent="voice"), orch.post)
    orch.bind(kws, asr, tts, oc)
    console.attach(orch)
    orch.tap = console.tap
    wd = StallWatchdog(mic)
    rc = 0
    if not await loop.run_in_executor(None, lambda: tts.ready.wait(300)):
        print("[m5] FATAL: TTS 预热失败", file=sys.stderr, flush=True)
        rc = 2
    else:
        for sig in (signal.SIGINT, signal.SIGTERM):
            with contextlib.suppress(NotImplementedError):
                loop.add_signal_handler(sig, orch.request_stop)
        print(f"[m5] started: 说「小码小码」唤醒（Ctrl-C 退出）；打字走 ws://127.0.0.1:{console.bound}",
              flush=True)
        run = asyncio.create_task(orch.run())
        tick = asyncio.create_task(_ticker(orch, wd))
        try:
            await run
        finally:
            tick.cancel()
    await _cleanup(orch, oc, asr, kws, mic, tts, console)
    return rc


async def _ticker(orch, wd):
    loop = asyncio.get_running_loop()
    while True:
        await asyncio.sleep(0.5)
        await orch.tick()
        [orch.post(a) for a in wd.check(loop.time())]


async def _cleanup(orch, oc, asr, kws, mic, tts, console=None):
    orch.request_stop()
    if console is not None:
        await console.stop()
    tts.stop()
    with contextlib.suppress(Exception):
        await oc.aclose()
    asr.stop(); kws.stop(); mic.stop(); tts.shutdown()
