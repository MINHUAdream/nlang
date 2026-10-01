# -*- coding: utf-8 -*-
"""探针执行器：VEH + 可选 dump（读 OUT 指针数组）——已验证可靠通道"""
import sys, io, struct, ctypes

EXCEPTION_CONTINUE_SEARCH = 0

def _veh_handler(exception_info):
    try:
        einfo = ctypes.cast(exception_info, ctypes.POINTER(ctypes.c_void_p))
        rec = ctypes.cast(einfo[0], ctypes.POINTER(ctypes.c_uint64))
        sys.stderr.write("CRASH-ADDR %#x\n" % rec[3])
        sys.stderr.flush()
    except Exception:
        pass
    return EXCEPTION_CONTINUE_SEARCH

_veh_cb = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p)(_veh_handler)
_AddVectoredExceptionHandler = ctypes.windll.kernel32.AddVectoredExceptionHandler
_AddVectoredExceptionHandler.argtypes = [ctypes.c_uint32, ctypes.c_void_p]
_AddVectoredExceptionHandler.restype = ctypes.c_void_p
_AddVectoredExceptionHandler(1, ctypes.cast(_veh_cb, ctypes.c_void_p))

_VALLOC = ctypes.windll.kernel32.VirtualAlloc
_VALLOC.restype = ctypes.c_void_p
_VALLOC.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32, ctypes.c_uint32]

raw = sys.stdin.buffer.read()
if len(raw) < 16:
    sys.exit(2)
lc, li = struct.unpack("<qq", raw[:16])
code = raw[16:16 + lc]
inbuf = raw[16 + lc:16 + lc + li]
dump = len(sys.argv) > 1 and sys.argv[1] == "dump"

addr = _VALLOC(None, len(code) + 0x100000000, 0x3000, 0x40)
if not addr:
    sys.exit(3)
ctypes.memmove(addr, code, len(code))
if li:
    iaddr = _VALLOC(None, len(inbuf) + 0x1000, 0x3000, 0x40)
    if not iaddr:
        sys.exit(4)
    ctypes.memmove(iaddr, inbuf, len(inbuf))
    got = ctypes.CFUNCTYPE(ctypes.c_double, ctypes.c_void_p)(addr)(iaddr)
else:
    got = ctypes.CFUNCTYPE(ctypes.c_double)(addr)()
if dump:
    ptr = struct.unpack("<q", struct.pack("<d", float(got)))[0]
    if ptr:
        n = ctypes.c_uint64.from_address(ptr).value
        elems = [ctypes.c_uint64.from_address(ptr + 8 + 8 * i).value for i in range(int(n))]
        sys.stdout.write(repr(elems))
    else:
        sys.stdout.write("[]")
else:
    sys.stdout.write(repr(float(got)))
sys.stdout.flush()
