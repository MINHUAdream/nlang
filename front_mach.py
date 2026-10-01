# -*- coding: utf-8 -*-
"""front_mach.py —— tl 前端机器码执行器：lex_machine.bin + parse_machine.bin
词法/解析完全在 x86-64 真机执行（VirtualAlloc + CreateThread），不经过 Python 宿主解释。
用法：
    fm = FrontMach()
    flat, blks = fm.front("let a = 1\n")          # 全链
    toks = fm.lex(b"let a = 1\n")                 # 词法
    flat, blks = fm.parse(toks)                    # 解析
"""
import io, struct, ctypes, json

_HERE = __file__.rsplit("\\", 1)[0]
k32 = ctypes.windll.kernel32
_VALLOC = k32.VirtualAlloc
_VALLOC.restype = ctypes.c_void_p
_VALLOC.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32, ctypes.c_uint32]
_MEMCPY = ctypes.cdll.msvcrt.memcpy
_MEMCPY.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
_CreateThread = k32.CreateThread
_CreateThread.restype = ctypes.c_void_p
_CreateThread.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p]
_WaitForSingleObject = k32.WaitForSingleObject
_WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
_MEM = 0x3000
_PAGE = 0x40
_HEAP = 0x2000000


def _rd(q):
    return ctypes.c_uint64.from_address(q).value


def _f64(q):
    return struct.unpack("<d", struct.pack("<Q", q))[0]


class _Mach:
    def __init__(self, code, out_addr, csize=_HEAP):
        self.code = bytes(code)
        self.out_addr = out_addr
        self.csize = len(self.code) + csize
        self.addr = _VALLOC(None, self.csize, _MEM, _PAGE)
        _MEMCPY(self.addr, self.code, len(self.code))
        self.in_buf = _VALLOC(None, 0x800000, _MEM, _PAGE)  # 8MB 复用输入区
        self.in_cap = 0x800000

    def run(self, inb):
        if len(inb) <= self.in_cap:
            in_addr = self.in_buf
            _MEMCPY(in_addr, inb, len(inb))
        else:
            in_addr = _VALLOC(None, len(inb) + 0x100000, _MEM, _PAGE)
            _MEMCPY(in_addr, inb, len(inb))
        h = _CreateThread(None, 0, self.addr, in_addr, 0, None)
        _WaitForSingleObject(h, 30000)
        lo, hi = self.addr, self.addr + self.csize
        out = []
        for oi in range(3):
            p = _rd(self.addr + self.out_addr + 8 * oi)
            try:
                if lo <= p < hi:
                    n = _rd(p)
                    cap = min(n, 500000)
                    if p + 8 + 8 * cap <= hi:
                        out.append([int(_f64(_rd(p + 8 + 8 * k))) for k in range(cap)])
                    else:
                        out.append([int(_f64(p))])
                else:
                    out.append([int(_f64(p))])
            except Exception:
                out.append([0])
        return out


class FrontMach:
    _singleton = None

    def __new__(cls, here=None):
        if cls._singleton is None:
            cls._singleton = super().__new__(cls)
            cls._singleton._init(here)
        return cls._singleton

    def _init(self, here=None):
        d = here or _HERE
        meta = json.load(io.open(d + "\\front_machine.json", encoding="utf-8"))
        self.lex_m = _Mach(io.open(d + "\\lex_machine.bin", "rb").read(), meta["lex"]["out_addr"])
        self.parse_m = _Mach(io.open(d + "\\parse_machine.bin", "rb").read(), meta["parse"]["out_addr"])
        self._lex_run = self.lex_m.run
        self._parse_run = self.parse_m.run

    def lex(self, src_bytes):
        """词法：源码字节 -> toks 值列表（[cls,val,pos,...] 扁平）"""
        vals = list(src_bytes)
        inb = struct.pack("<q", len(vals)) + struct.pack("<%dd" % len(vals), *vals)
        return self._lex_run(inb)[0]

    def lex_full(self, src_bytes):
        """词法完整输出：-> (toks, sym 字节池, sym_len 列表)"""
        vals = list(src_bytes)
        inb = struct.pack("<q", len(vals)) + struct.pack("<%dd" % len(vals), *vals)
        r = self._lex_run(inb)
        return r[0], r[1], r[2]

    def lex_names(self, src_bytes):
        """词法 + 符号表：-> (toks, {sym_id: name})。id 规则与 boot_lex 一致。"""
        toks, sym, lens = self.lex_full(src_bytes)
        names = {}
        off = 0
        for k, L in enumerate(lens):
            sid = 12 + k if k < 31 else 200 + k
            names[sid] = bytes(sym[off:off + L]).decode("utf-8")
            off += L
        return toks, names

    def parse(self, toks):
        """解析：toks 值列表 -> (flat, blks)"""
        inb = struct.pack("<q", len(toks)) + struct.pack("<%dd" % len(toks), *toks)
        r = self._parse_run(inb)
        return r[0], r[1]

    def front(self, src_text):
        """全链：tl 源码文本 -> (flat, blks)"""
        return self.parse(self.lex(src_text.encode("utf-8")))
