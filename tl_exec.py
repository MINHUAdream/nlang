# -*- coding: utf-8 -*-
"""tl_exec.py —— 机器码隔离执行器（子进程模式）。

背景：同一进程内多次 VirtualAlloc+执行 RWX 机器码，Windows 偶发
ACCESS_VIOLATION（疑似 RWX 页监控/懒提交竞争，memmove 或执行时崩）。
解法：每次执行放在独立子进程（helper 模式）中，执行一次后进程退出，
彻底隔离，回归链 100% 稳定。

用法：
  from tl_exec import exec_code
  got = exec_code(code_bytes)                 # 无输入
  got = exec_code(code_bytes, input_bytes)    # CFUNCTYPE(c_double, c_void_p)

helper 模式：`python -X utf8 tl_exec.py <packed>` 从 stdin 读打包数据执行并打印结果。
"""
import sys, struct, subprocess, os, json

HELPER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tl_exec.py")


def _pack(code: bytes, inbuf: bytes) -> bytes:
    h = struct.pack("<qq", len(code), len(inbuf) if inbuf else 0)
    return h + code + (inbuf or b"")


def exec_code(code: bytes, inbuf: bytes = None, timeout: float = 30.0, has_input: bool = None) -> float:
    """独立子进程执行机器码，返回 OUT 值（double）。"""
    if has_input is None:
        has_input = inbuf is not None
    data = _pack(code, inbuf or b"")
    r = subprocess.run(
        [sys.executable, "-X", "utf8", HELPER, "1" if has_input else "0"],
        input=data, capture_output=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError("子进程执行失败 rc=%d stderr=%r" % (r.returncode, r.stderr[:500]))
    out = r.stdout.strip()
    if not out:
        raise RuntimeError("子进程无输出 stderr=%r" % r.stderr[:500])
    return float(out)


def exec_code_arr(code: bytes, inbuf: bytes = None, timeout: float = 60.0, has_input: bool = None):
    """执行机器码并把 OUT 值当作 tensor 指针，dump 出 [len][e0][e1]... 列表。"""
    if has_input is None:
        has_input = inbuf is not None
    data = _pack(code, inbuf or b"")
    r = subprocess.run(
        [sys.executable, "-X", "utf8", HELPER, "1" if has_input else "0", "dump"],
        input=data, capture_output=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError("子进程执行失败 rc=%d stderr=%r" % (r.returncode, r.stderr[:500]))
    out = r.stdout.strip()
    if not out:
        raise RuntimeError("子进程无输出 stderr=%r" % r.stderr[:500])
    return eval(out)


def _install_veh():
    """安装只打印不干预的 VEH。实测：VEH 存在时 RWX 页执行稳定（无 VEH 小程序偶发崩溃）。"""
    import ctypes
    _EXCEPTION_CONTINUE_SEARCH = 0
    def _handler(exception_info):
        try:
            einfo = ctypes.cast(exception_info, ctypes.POINTER(ctypes.c_void_p))
            rec = ctypes.cast(einfo[0], ctypes.POINTER(ctypes.c_uint64))
            import sys as _s
            _s.stderr.write("CRASH-ADDR %#x\n" % rec[3])
            _s.stderr.flush()
        except Exception:
            pass
        return _EXCEPTION_CONTINUE_SEARCH
    global _veh_cb
    _veh_cb = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p)(_handler)
    _AddVectoredExceptionHandler = ctypes.windll.kernel32.AddVectoredExceptionHandler
    _AddVectoredExceptionHandler.argtypes = [ctypes.c_uint32, ctypes.c_void_p]
    _AddVectoredExceptionHandler.restype = ctypes.c_void_p
    _AddVectoredExceptionHandler(1, ctypes.cast(_veh_cb, ctypes.c_void_p))


if __name__ == "__main__":
    _install_veh()
    # helper：stdin 读 [len_code][len_in][code][inbuf]（均为二进制）
    has_input = len(sys.argv) > 1 and sys.argv[1] == "1"
    dump = len(sys.argv) > 2 and sys.argv[2] == "dump"
    raw = sys.stdin.buffer.read()
    if len(raw) < 16:
        sys.exit(2)
    lc, li = struct.unpack("<qq", raw[:16])
    code = raw[16:16 + lc]
    inbuf = raw[16 + lc:16 + lc + li]
    import ctypes
    _VALLOC = ctypes.windll.kernel32.VirtualAlloc
    _VALLOC.restype = ctypes.c_void_p
    _VALLOC.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32, ctypes.c_uint32]
    # RWX 页：代码 + 数据 + bump 堆（大输入如 B_gen 编译自身需 GB 级堆，
    # 因为 cat/mk 无回收累积；0x100000000 = 4GB）
    addr = _VALLOC(None, len(code) + 0x100000000, 0x3000, 0x40)
    if not addr:
        sys.exit(3)
    ctypes.memmove(addr, code, len(code))
    if has_input:
        iaddr = _VALLOC(None, len(inbuf) + 0x1000, 0x3000, 0x40)
        if not iaddr:
            sys.exit(4)
        ctypes.memmove(iaddr, inbuf, len(inbuf))
        sys.stderr.write("DBG codebase=%#x ibase=%#x codelen=%d inblen=%d\n" % (addr, iaddr, len(code), len(inbuf)))
        sys.stderr.flush()
        got = ctypes.CFUNCTYPE(ctypes.c_double, ctypes.c_void_p)(addr)(iaddr)
    else:
        got = ctypes.CFUNCTYPE(ctypes.c_double)(addr)()
    if dump:
        # OUT 值 = tensor 指针（double 位型）→ 读 [len][e0..]
        ptr = struct.unpack("<q", struct.pack("<d", float(got)))[0]
        if ptr:
            n = ctypes.c_uint64.from_address(ptr).value
            elems = []
            for i in range(int(n)):
                elems.append(ctypes.c_uint64.from_address(ptr + 8 + 8 * i).value)
            sys.stdout.write(repr(elems))
        else:
            sys.stdout.write("[]")
    else:
        sys.stdout.write(repr(float(got)))
    sys.stdout.flush()
