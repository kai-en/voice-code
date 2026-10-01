# M5 编排器核心：IDLE/COLLECT/RUNNING/PERM 四态，单 asyncio.Queue 串行 dispatch。
# 全双工（用户拍板）：唤醒后 VAD 恒开；3s 静默成轮；退出仅 voice-end。
# RUNNING 打断分级（0927 需求 docs/0927工作/kws-gated-llm-interrupt-req.md）：
#   回答期(本回合已出声) ASR 出句=打断；思考期(未出声) ASR 一律无视，仅 KWS 命中可打断 LLM。
# 第1轮优化：TurnDone 经 _await_turn 桥回队列；每事件/转移一行结构化日志。
# 播报期自听（回采）不设软件防护——硬件 AEC 麦已在场，频发先查硬件链路（AGENTS.md「播报期自听」）。
from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from kws.kws_wake import KwsConfig                            # 只借激活词文件路径（分派仍按类名字符串）

from . import textproc

IDLE, COLLECT, RUNNING, PERM = "IDLE", "COLLECT", "RUNNING", "PERM"
STOP = object()
_SENDING = object()           # 占位护栏：send 的 REST 在飞、Future 还没到手
# M13 回音过滤窗: Δ=AsrText.end_ts−wake_mono 落窗=唤醒词同段回音(转写成同音也杀, 与文本无关), 整段丢。
# 锚是 dispatch 时刻, 落后词声学终点 L=唤醒全链延迟(kws-design §: 160ms批+320ms chunk-16+trailing
# blanks+dispatch ≈0.5~0.9s, 重载再漂)→纯回音 Δ≈−L 恒为负; back=1.2 覆盖 L 上界(0928 评审 F1, 原 0.6 会漏杀)。
# fwd 只 0.10: 独立指令段必有 ≥0.6s 静默间隔, Δ≥+0.65 出窗; 连读短令落窗属"宁漏勿杀"已拍板的牺牲。
ECHO_BACK_S, ECHO_FWD_S = 1.20, 0.10


@dataclass(frozen=True)
class TextIn:
    """M11 控制台注入：一次 post 同时表达"已唤醒 + 带文本"，不念 ack、不经回采去重（设计 §3.3）。"""

    text: str
    src: str = "console"


@dataclass(frozen=True)
class HotwordsSet:
    """M14 控制台手动注入（{t:"hotwords", words:[...]}，注入唯一出口仍是 orch.post，设计 §4）。"""

    words: tuple


@dataclass
class OrchConfig:
    collect_silence_s: float = 3.0      # 断句后静默 3s 成轮（不论长度）
    collect_confirm_s: float = 0.5      # 成轮窗额外余量：给 VAD 起头 min_speech(0.25s) 时间成熟，收窄"第二句刚开口"盲区(0930)
    collect_defer_cap_s: float = 10.0   # audio_pending 推迟提交的上限(防卡死保险:回声漏 AEC 持续触发 VAD 时强提交)
    perm_timeout_s: float = 15.0        # 权限问句无应答→reject
    ack_text: str = "在呢。"
    bye_text: str = "好，先退下了。"
    perm_prompt: str = "需要授权：{action}。说允许或拒绝。"
    error_text: str = "任务出错了。"


def _brief(ev) -> str:
    cls = type(ev).__name__
    if cls == "AsrText":
        return f'"{ev.text[:24]}"'
    if cls == "TextIn":
        return f'"{ev.text[:24]}" src={ev.src}'
    if cls == "OcText":
        return f'{"end" if ev.final else "delta"} "{ev.text[:16]}"'
    if cls == "OcTurnDone":
        return f"outcome={ev.outcome} len={len(ev.text)}"
    if cls == "OcTool":
        return f"{ev.name}/{ev.phase}"
    if cls == "OcPermission":
        return f"{ev.action}"
    if cls == "KwsHit":
        return ev.keyword + ("/repeat" if ev.repeat else "")
    if cls == "OcLink":
        return f"{ev.state} {ev.detail}".strip()[:60]
    if cls == "HotwordsSet":
        return ",".join(ev.words)[:24]
    return ""


_DENY = ("拒绝", "不行", "不要", "不准", "不可以", "取消", "驳回", "别")
_ALLOW = ("允许", "同意", "可以", "好的", "行吧", "放行", "没问题", "ok", "OK")
# 剥唤醒前缀用 keywords.txt 的**实际**激活词（自定义"小爱"后不再只认死"小码"）；
# 仍只认正字——同音转写剥不动（R2 已知项：KWS 音素级听得见，文本级不猜同音，误剥更伤）。
_WAKE_RE_CACHE = {}


def _wake_res():
    key = str(KwsConfig().keywords_file)
    if key not in _WAKE_RE_CACHE:
        words = []
        try:
            for line in Path(key).read_text(encoding="utf-8").splitlines():
                w = line.rsplit("@", 1)[1].strip() if "@" in line else ""   # 格式: tokens :分 @显示名
                if len(w) >= 2:
                    words.append(w)
                    h = len(w) // 2
                    if len(w) % 2 == 0 and w[:h] == w[h:]:
                        words.append(w[:h])                   # "小码小码"→半词"小码"也剥
        except OSError:
            pass
        words = list(dict.fromkeys(words))
        if not words:
            _WAKE_RE_CACHE[key] = None                        # 文件缺席/无 @显示名 → 不剥(不再有死词兜底)
        else:
            alt = "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True))
            _WAKE_RE_CACHE[key] = re.compile(rf"^(?:(?:{alt})[，,、\s]*){{1,2}}")
    return _WAKE_RE_CACHE[key]


def strip_wake(text):
    pat = _wake_res()
    return pat.sub("", text.strip(), count=1).strip() if pat else text.strip()


def match_permission(text):
    """拒绝词优先（防"不行"误判成"行"）；无匹配返回 None。"""
    t = text.strip()
    if any(k in t for k in _DENY):
        return "reject"
    if any(k in t for k in _ALLOW):
        return "once"
    return None


class Orchestrator:
    def __init__(self, cfg: OrchConfig = field(default_factory=OrchConfig),
                 clock=time.monotonic):
        self.cfg, self.clock = cfg, clock
        self.state, self.sid, self.buf = IDLE, None, ""
        self.collect_deadline = self.perm_deadline = 0.0
        self.pending_exit = False
        self._turn_fut = None           # 未回收的回合 Future（串行护栏）
        self._rid = None                # 待答权限 request id
        self.spoken_len = 0             # 本回合已播字数（终稿对账）
        self._spoke_this_turn = False   # 本回合是否已出声：False=思考期(ASR 打断需 KWS)，True=回答期(任意 ASR 可打断)
        self._rest = ""                 # 本回合模型话里还没成句的尾巴（与 self.buf 对称）
        self._sent = ""                 # 已发出但那轮被打断没答完的提问；下次前置 → 打断=追加重问
        self._wake_mono = None          # M13: 最近一次 KwsHit 到达时刻(monotonic, 与 end_ts 同基准)
        self.echo_drops = 0             # M13: 被判为激活词回音而丢弃的句数(观测)
        self._defer_logged = False      # M5 0930: 本提交窗口是否已因 audio_pending 推迟过(日志去重+计 cap)
        self._defer_start = 0.0         # 首次推迟时刻；_defer_logged 为真时有效
        self._q: asyncio.Queue = asyncio.Queue()
        self._loop, self._pre = None, []
        self.kws = self.asr = self.tts = self.oc = None
        self.tap: Optional[Callable[[str, object], None]] = None   # M11 控制台出流，同 loop 线程同步调用

    def bind(self, kws, asr, tts, oc):
        self.kws, self.asr, self.tts, self.oc = kws, asr, tts, oc

    def _tap(self, kind, obj=None):
        if self.tap is None:
            return
        try:
            self.tap(kind, obj)
        except Exception:
            pass

    def post(self, ev):                 # 线程安全唯一入口（模块回调全走这里）
        if self._loop is None:
            self._pre.append(ev)
        else:
            self._loop.call_soon_threadsafe(self._q.put_nowait, ev)

    def request_stop(self):
        self.post(STOP)

    def _log(self, msg):
        print(f"[m5 {time.strftime('%H:%M:%S')}] {self.state} | {msg}", flush=True)

    def _go(self, state):
        if state != self.state:
            self._log(f"{self.state}->{state}")
            self._tap("state", state)
        self.state = state
        self.asr.set_active(state != IDLE)          # 全双工：仅 IDLE 关 VAD
        if state == IDLE:
            self.asr.set_hotwords([])               # M14：退会话必须收走热词窗口（无 TTL，IDLE 即清）
            self._log("hotwords cleared@IDLE")

    def _speak(self, text: str):
        self._log(f"speak: {text[:24]}")
        self._tap("speak", text)
        self.tts.speak(text)

    def _apply_hotwords(self, words):
        csv = self.asr.set_hotwords(words)
        if csv is None:
            self._log(f"hotwords rejected: {str(words)[:60]}")
            return
        self._log(f"hotwords applied: {csv or '(cleared)'}")   # 回执只进 log(用户 0927 拍板)，不进 ev/tap

    async def run(self):
        self._loop = asyncio.get_running_loop()
        for ev in self._pre:
            self._q.put_nowait(ev)
        self._pre.clear()
        while True:
            ev = await self._q.get()
            if ev is STOP:
                return
            self._log(f"<{type(ev).__name__}> {_brief(ev)}".rstrip())
            self._tap("ev", ev)                    # 先镜像事件再处理 → 保证 ev 早于其引发的 state（A9）
            try:
                await self._handle(ev)
            except Exception as e:                   # dispatch 永不崩
                self._log(f"ERR {type(ev).__name__}: {e}")

    async def _handle(self, ev):
        cls = type(ev).__name__
        if cls == "TextIn":                         # M11 控制台注入（单事件原子，绕开 ack/strip_wake/回采去重）
            if self.state == RUNNING:
                self._barge_in(ev.text)             # 打字即打断；同理打字轮可被真人说话打断（R1）
            elif self.state == PERM:
                await self._answer_perm(ev.text)
            elif self.state == COLLECT:
                if not ev.text:
                    return
                self.buf = (self.buf + "\n" + ev.text) if self.buf else ev.text   # 不吞语音半句（R3）
                await self._collect_fire()
            elif self.state == IDLE and ev.text:
                self._go(COLLECT)                   # 打字不念"在呢。"
                self.buf = ev.text
                await self._collect_fire()
            return
        if cls == "KwsHit":
            self._wake_mono = self.clock()         # 一切状态都刷锚(COLLECT/PERM 的 no-op 命中同样要杀回音句)
            if ev.repeat:
                return                             # cooldown 二喊: 只刷锚, 不动状态
            if self.state == IDLE:                   # 会话中(COLLECT/PERM) KWS 再响=无效(用户已在线)
                self._speak(self.cfg.ack_text)
                self._go(COLLECT)
            elif self.state == RUNNING:              # 思考期打断 LLM 的唯一通道(不念 ack, Q1)
                self._barge_in("")
        elif cls == "AsrText":
            if self._is_wake_echo(ev):               # 先于 strip_wake: 杀同音回音与文本无关(log 见原文)
                self.echo_drops += 1
                self._log(f'echo-drop "{ev.text[:16]}" Δ={ev.end_ts - self._wake_mono:+.2f}s')
                return
            if self._wake_mono is not None and ev.end_ts > 0 and -3.0 <= (d := ev.end_ts - self._wake_mono) <= 0.5:
                self._log(f'echo-near "{ev.text[:16]}" Δ={d:+.2f}s')   # F2: 近锚未杀样本留痕, 真机校准窗口靠它
            text = strip_wake(ev.text)
            if self.state == COLLECT and text:
                self.buf += text
                base = ev.end_ts if ev.end_ts > 0 else self.clock()   # 锚在"说完"，不是"解码完"
                self.collect_deadline = base + self.cfg.collect_silence_s + self.cfg.collect_confirm_s
                self._defer_logged, self._defer_start = False, 0.0    # 新一句 → 推迟 episode 重新计
            elif self.state == RUNNING:
                if self._spoke_this_turn:            # 回答期(R4)：主播抢话=不满意, 断
                    self._barge_in(text)
                # 思考期(R3)：主播在对观众说话, oc2 不许插话——不响应不入 buf(tap 已镜像, Q2 可见)
            elif self.state == PERM:
                await self._answer_perm(text)
        elif cls == "OcText" and self.state in (RUNNING, PERM) and not ev.final:
            sents, self._rest = textproc.feed(ev.text, self._rest)   # 尾巴必须带下来：delta 多为逗号结尾的碎片
            sents = [s for s in sents if s.strip()]                  # 纯换行/空白不成句(断句按 \n 硬断的副产物)
            for s in sents:
                self._speak(s)
                self.spoken_len += len(s)
                self._spoke_this_turn = True         # 首次出声 → 本回合进入回答期
        elif cls == "OcPermission" and self.state in (RUNNING, PERM):
            self._rid = ev.request_id
            self.tts.stop()
            self._speak(self.cfg.perm_prompt.format(action=ev.action))
            self._go(PERM)
            self.perm_deadline = self.clock() + self.cfg.perm_timeout_s
        elif cls == "OcTool" and ev.name == "set-hotwords" and ev.phase == "called" \
                and self.state != IDLE:        # 迟到帧 guard: IDLE 后不复活词表（console 手动注入不受此限）
            self._apply_hotwords((ev.tool_input or {}).get("words"))   # M14 SSE 旁观, 与 voice-end 同构
        elif cls == "HotwordsSet":                         # M14 控制台手动注入
            self._apply_hotwords(list(ev.words))
        elif cls == "OcTool" and ev.name == "voice-end" and ev.phase == "called":
            self.pending_exit = True                 # 唯一退出通道(M6.1)
        elif cls == "OcTurnDone":
            await self._end_turn(ev)
        elif cls in ("CaptureDead", "AlertTick") and self.state == IDLE:
            self._speak("音频采集异常，请检查麦克风后重启助手。")

    async def _collect_fire(self):
        if self.state != COLLECT or not self.buf:
            return
        if self._turn_fut is not None:               # 旧回合未收场: M6 同 session 禁并发(client.py:57)，静默等 2s 重试
            self._log("busy: 旧回合未收场，本句暂不发")
            self.collect_deadline = self.clock() + 2.0
            return
        text, self.buf = self.buf, ""
        if self._sent:                                       # 打断=追加重问：把没答完的前半轮带回来
            text = self._sent + "\n" + text
        self.collect_deadline = 0.0
        self.spoken_len, self._rest = 0, ""
        self._spoke_this_turn = False                # 新回合 = 思考期起步
        self._turn_fut = _SENDING                    # await 期间不得再发第二句(M6 同 session 禁并发)
        self._go(RUNNING)                            # 先转态：await 期间新到的句子按"打断"处理，不当继续采集
        try:
            if self.sid is None:                     # 懒建会话
                self.sid = await self.oc.session_new("voice")
            fut = await self.oc.send(self.sid, text)
        except Exception as e:
            self._log(f"send failed: {e}")
            self._turn_fut = None
            self._sent = ""                          # 前缀已随 text 整体还回 buf, 否则下轮变 B1\nB1\nB2
            self.buf = self.buf or text              # 还回缓冲(除非已被新话占住)，回 COLLECT 下轮再试
            self._go(COLLECT)
            return
        self._turn_fut = fut
        self._sent = text                            # 记账：本轮已发出的全文（被打断则下轮前置）
        asyncio.get_running_loop().create_task(self._await_turn(fut))

    async def _await_turn(self, fut):
        """M6 契约: OcTurnDone 只落在 send 的 Future 上 → 桥回 _q。"""
        try:
            ev = await fut
        except Exception as e:
            self._log(f"turn fut err: {e}")
            return
        self.post(ev)

    async def _end_turn(self, ev):
        self._turn_fut = None
        if self.state not in (RUNNING, PERM):
            return                                   # barge-in 后的陈旧终 → 丢弃（_sent 保留，下轮前置）
        self._sent = ""                              # 本轮真收场(succeeded/failed/退出) → 不再前置
        for s in textproc.flush(self._rest):         # 尾巴整段播（必须在下面"零播才兜底"之前，否则双播）
            self._speak(s)
            self.spoken_len += len(s)
        self._rest = ""
        if self.pending_exit:
            self.pending_exit, self.sid = False, None
            if self.spoken_len == 0:                 # 模型道别没播出来才补
                self._speak(ev.text or self.cfg.bye_text)
            self._go(IDLE)
            return
        if ev.outcome != "succeeded":
            self._speak(self.cfg.error_text if ev.outcome == "failed" else "已停止。")
            self._go(COLLECT if self.sid else IDLE)
            return
        if self.spoken_len == 0 and ev.text:         # 断线零播 → 终稿全量兜底
            self._speak(ev.text)
        elif ev.text and abs(len(ev.text) - self.spoken_len) > 8:
            self._log(f"校准差 {self.spoken_len}->{len(ev.text)}（不重播）")
        self._go(COLLECT)                            # 免唤醒连续对话

    def _barge_in(self, text):
        self.tts.stop()
        asyncio.get_running_loop().call_later(0.4, self.tts.stop)   # 双 stop 压尾音(tts.py:74)
        if self.sid:
            t = asyncio.get_running_loop().create_task(self.oc.interrupt(self.sid))
            t.add_done_callback(lambda f: None if f.cancelled() else f.exception())
        self.pending_exit, self._rest = False, ""    # 打断后旧尾巴作废，不续进新轮
        self._go(COLLECT)
        if text:
            self.buf = (self.buf + "\n" + text) if self.buf else text   # 覆盖会吞掉竞态窗口里攒下的半句
            self.collect_deadline = self.clock() + self.cfg.collect_silence_s + self.cfg.collect_confirm_s + self.cfg.collect_confirm_s

    def _is_wake_echo(self, ev) -> bool:
        if self._wake_mono is None or ev.end_ts <= 0:
            return False                             # 无锚/无端点时刻 → fail-open(守 end_ts=0 构造的既有用例)
        return -ECHO_BACK_S <= ev.end_ts - self._wake_mono <= ECHO_FWD_S

    async def _answer_perm(self, text):
        rid, self._rid = self._rid, None
        decision = match_permission(text) or "reject"
        try:
            await self.oc.reply_permission(self.sid, rid, decision)
        except Exception as e:
            self._log(f"reply failed: {e}")
        self._go(RUNNING)

    async def tick(self):                            # main._ticker 以 2Hz 驱动
        now = self.clock()
        if self.state == COLLECT and self.buf and now >= self.collect_deadline:
            pending = self.asr is not None and self.asr.audio_pending()
            overdue = self._defer_logged and now - self._defer_start >= self.cfg.collect_defer_cap_s
            if pending and not overdue:              # 话还在路上(在说/在队/在解码): 别把第二句丢进 R3 吞了
                if not self._defer_logged:
                    self._defer_logged, self._defer_start = True, now
                    self._log("collect defer: audio_pending")
                self.collect_deadline = now + 0.5
                return
            if overdue:                              # 保险: audio_pending 长期为真(回声/常开麦) → 到上限仍强提交
                self._log(f"collect defer cap {self.cfg.collect_defer_cap_s:.0f}s -> force fire")
            self._defer_logged, self._defer_start = False, 0.0
            await self._collect_fire()
        elif self.state == PERM and now >= self.perm_deadline:
            self._log("perm timeout -> reject")
            await self._answer_perm("拒绝")
