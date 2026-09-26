# M10 进程卫生：单一实例锁（锁内写**真解释器 PID**）+ Job Object 连坐（KILL_ON_JOB_CLOSE）。
# 设计 docs/0926工作/m10-proc-hygiene-textin-design.md §2.1/§2.2。
# 锁由 OS 在进程死亡（含 /F 强杀、崩溃）时释放 → 锁态=真存活证明，不受 PID 复用骗；
# job 句柄自持到进程退出 → 之后 spawn 的一切子进程（opencode serve / wintts powershell / Bun 的孙子）连坐死。
from __future__ import annotations

import ctypes
import datetime as dt
import os
from ctypes import wintypes as wt
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOCK = Path(os.environ.get("VOICECODE_LOCK") or ROOT / "logs" / "voice-code.lock")

_KILL_ON_CLOSE = 0x2000          # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
_EXTENDED_LIMIT_INFO = 9         # 实测：class 2(Basic) 带 0x2000 会被拒 ERROR_INVALID_PARAMETER(87)，必须用 class 9
_ERROR_NOT_SUPPORTED = 5010
_QUERY_LIMITED = 0x1000
_LOCK_AT = 4096                  # 锁位放在元数据之后：Windows 字节锁会让"读整文件"撞 PermissionError，锁在尾部才能边持有边读


class _BasicLimits(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", ctypes.c_uint32),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", ctypes.c_uint32),
        ("Affinity", ctypes.c_size_t),        # winnt.h 里是 ULONG_PTR/DWORD_PTR（x64 上 8 字节），非 ULONG
        ("PriorityClass", ctypes.c_uint32),
        ("SchedulingClass", ctypes.c_uint32),
    ]


class _IoCounters(ctypes.Structure):
    _fields_ = [(n, ctypes.c_uint64) for n in
                ("ReadOperation", "WriteOperation", "OtherOperation",
                 "ReadTransfer", "WriteTransfer", "OtherTransfer")]


class _ExtendedLimits(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _BasicLimits),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


_k32 = None
_job = None                       # 句柄必须活到进程退出（提前 GC = 连坐杀）
_lock_fd = None


def _api():
    global _k32
    if _k32 is None and os.name == "nt":
        k = ctypes.windll.kernel32
        k.CreateJobObjectW.restype = wt.HANDLE
        k.CreateJobObjectW.argtypes = [wt.LPVOID, wt.LPCWSTR]
        k.SetInformationJobObject.restype = wt.BOOL
        k.SetInformationJobObject.argtypes = [wt.HANDLE, ctypes.c_int, wt.LPVOID, wt.DWORD]
        k.AssignProcessToJobObject.restype = wt.BOOL
        k.AssignProcessToJobObject.argtypes = [wt.HANDLE, wt.HANDLE]
        k.GetCurrentProcess.restype = wt.HANDLE
        k.OpenProcess.restype = wt.HANDLE
        k.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
        k.CloseHandle.argtypes = [wt.HANDLE]
        _k32 = k
    return _k32


def attach_job() -> str:
    k = _api()
    if k is None:
        return "SKIP"
    h = k.CreateJobObjectW(None, None)
    if not h:
        return f"FAIL:Create:{ctypes.GetLastError()}"
    info = _ExtendedLimits()
    info.BasicLimitInformation.LimitFlags = _KILL_ON_CLOSE
    if not k.SetInformationJobObject(h, _EXTENDED_LIMIT_INFO, ctypes.byref(info), ctypes.sizeof(info)):
        k.CloseHandle(h)
        return f"FAIL:SetInfo:{ctypes.GetLastError()}"
    if not k.AssignProcessToJobObject(h, k.GetCurrentProcess()):
        err = ctypes.GetLastError()
        k.CloseHandle(h)
        return "UNSUPPORTED" if err == _ERROR_NOT_SUPPORTED else f"FAIL:Assign:{err}"
    globals()["_job"] = h
    return "OK"


def acquire(job: str = "") -> bool:
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(LOCK), os.O_RDWR | os.O_CREAT, 0o666)
    try:
        import msvcrt
        os.lseek(fd, _LOCK_AT, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
    except OSError:
        os.close(fd)
        return False
    globals()["_lock_fd"] = fd
    os.truncate(fd, 0)
    os.lseek(fd, 0, os.SEEK_SET)
    os.write(fd, f"pid={os.getpid()} boot={dt.datetime.now():%Y-%m-%dT%H:%M:%S} job={job}\n".encode())
    return True


def locked() -> bool:
    import msvcrt
    fd = os.open(str(LOCK), os.O_RDWR | os.O_CREAT, 0o666)
    try:
        os.lseek(fd, _LOCK_AT, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
    except OSError:
        os.close(fd)
        return True
    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    os.close(fd)
    return False


def holder() -> dict:
    try:
        parts = LOCK.read_text(encoding="utf-8", errors="replace").split()
    except OSError:
        return {}
    return dict(p.split("=", 1) for p in parts if "=" in p)


def alive(pid: int) -> bool:
    k = _api()
    if k is None or pid <= 0:
        return False
    h = k.OpenProcess(_QUERY_LIMITED, False, int(pid))
    if h:
        k.CloseHandle(h)
        return True
    return False
