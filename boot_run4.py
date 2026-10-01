# -*- coding: utf-8 -*-
"""v0.17 验证：表驱动通用发射器（boot_enc_all.tl）覆盖全部 9 个 single_loop 内核
1) 每段与 tl_emit._gen_single_loop(kind) 逐字节一致
2) 装载执行与纯 Python 语义逐位一致
"""
import io
import os
import random
import time
import ctypes

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)

import tl
from tl_emit import _gen_single_loop
from tl_native import Buf
from tlb_loadmc import load_mc

_P = ctypes.c_void_p
_I = ctypes.c_int
_D = ctypes.c_double
SIG = {
    "relu":       (None, _P, _P, _I),
    "add":        (None, _P, _P, _P, _I),
    "sub":        (None, _P, _P, _P, _I),
    "mul":        (None, _P, _P, _P, _I),
    "scale":      (None, _P, _P, _I, _D),
    "scale_div":  (None, _P, _P, _I, _D),
    "upd":        (None, _P, _P, _P, _I, _D),
    "relu_mask":  (None, _P, _P, _P, _I),
    "sqg":        (None, _P, _P, _P, _I),
}
KINDS = list(SIG)

print("=" * 60)
print("v0.17 验证：tl 表驱动发射器 · 全 9 内核")
print("=" * 60)

# 免检执行 boot_enc_all.tl
src = io.open("boot_enc_all.tl", encoding="utf-8").read()
ast = tl.Parser(tl.lex(src)).parse()
eng = tl.Engine()
eng.run(ast, quiet=True)
blob = [int(b) & 0xFF for b in eng.vars["all"].value]

# 解析：每段 [len32 LE][code]
segs = []
off = 0
for k in range(9):
    ln = (blob[off] | (blob[off+1] << 8) | (blob[off+2] << 16) | (blob[off+3] << 24))
    segs.append(bytes(blob[off+4:off+4+ln]))
    off += 4 + ln
print("[0] 解析出 %d 段，总字节 %d" % (len(segs), off))

all_ok = True
for k, kind in enumerate(KINDS):
    tl_bytes = segs[k]
    ref = bytes(_gen_single_loop(kind))
    ok_b = tl_bytes == ref
    print("[%s] tl 表驱动 %d 字节 | 逐字节一致: %s"
          % (kind, len(tl_bytes), ok_b))
    if not ok_b:
        all_ok = False
        for i, (a, b) in enumerate(zip(tl_bytes, ref)):
            if a != b:
                print("  首个差异 @%d: tl=%02X ref=%02X" % (i, a, b))
                break
        print("  tl :", " ".join("%02X" % b for b in tl_bytes))
        print("  ref:", " ".join("%02X" % b for b in ref))
        continue
    # 执行验证
    mk = load_mc(tl_bytes, SIG[kind])
    random.seed(20260926 + k)
    ok_x = True
    for trial in range(6):
        n = random.randint(1, 257)
        a = [random.uniform(-5, 5) for _ in range(n)]
        if kind == "relu":
            exp = [v if v > 0 else 0.0 for v in a]
            ab = Buf.from_list(a); ob = Buf.from_list([0.0]*n)
            mk.fn(ab.arr, ob.arr, n)
        elif kind in ("add", "sub", "mul"):
            b = [random.uniform(-5, 5) for _ in range(n)]
            exp = [{"add": lambda x, y: x+y, "sub": lambda x, y: x-y,
                    "mul": lambda x, y: x*y}[kind](x, y) for x, y in zip(a, b)]
            ab = Buf.from_list(a); bb = Buf.from_list(b); ob = Buf.from_list([0.0]*n)
            mk.fn(ab.arr, bb.arr, ob.arr, n)
        elif kind in ("scale", "scale_div"):
            cv = random.uniform(0.5, 3.0)
            exp = [v*cv if kind == "scale" else v/cv for v in a]
            ab = Buf.from_list(a); ob = Buf.from_list([0.0]*n)
            mk.fn(ab.arr, ob.arr, n, cv)
        elif kind == "upd":
            g = [random.uniform(-5, 5) for _ in range(n)]
            lr = random.uniform(0.001, 0.1)
            exp = [v - lr*g_i for v, g_i in zip(a, g)]
            ab = Buf.from_list(a); gb = Buf.from_list(g); ob = Buf.from_list([0.0]*n)
            mk.fn(ab.arr, gb.arr, ob.arr, n, lr)
        elif kind == "relu_mask":
            g = [random.uniform(-5, 5) for _ in range(n)]
            exp = [g_i if v > 0 else 0.0 for v, g_i in zip(a, g)]
            ab = Buf.from_list(a); gb = Buf.from_list(g); ob = Buf.from_list([0.0]*n)
            mk.fn(ab.arr, gb.arr, ob.arr, n)
        elif kind == "sqg":
            g = [random.uniform(-5, 5) for _ in range(n)]
            exp = [2.0*x*g_i for x, g_i in zip(a, g)]
            ab = Buf.from_list(a); gb = Buf.from_list(g); ob = Buf.from_list([0.0]*n)
            mk.fn(ab.arr, gb.arr, ob.arr, n)
        if ob.to_list() != exp:
            ok_x = False
            print("  %s trial %d 不一致！" % (kind, trial))
            break
    print("[%s] 执行 == 纯 Python: %s（6 轮随机）" % (kind, ok_x))
    all_ok = all_ok and ok_x
    # 性能采样
    n = 1 << 20
    ab = Buf.from_list([random.uniform(-5, 5) for _ in range(n)])
    if kind == "relu":
        ob = Buf.from_list([0.0]*n)
        t0 = time.perf_counter(); mk.fn(ab.arr, ob.arr, n); t1 = time.perf_counter()
    elif kind in ("add", "sub", "mul"):
        bb = Buf.from_list([random.uniform(-5, 5) for _ in range(n)])
        ob = Buf.from_list([0.0]*n)
        t0 = time.perf_counter(); mk.fn(ab.arr, bb.arr, ob.arr, n); t1 = time.perf_counter()
    elif kind in ("scale", "scale_div"):
        ob = Buf.from_list([0.0]*n)
        t0 = time.perf_counter(); mk.fn(ab.arr, ob.arr, n, 2.0); t1 = time.perf_counter()
    elif kind == "upd":
        gb = Buf.from_list([random.uniform(-5, 5) for _ in range(n)])
        ob = Buf.from_list([0.0]*n)
        t0 = time.perf_counter(); mk.fn(ab.arr, gb.arr, ob.arr, n, 0.01); t1 = time.perf_counter()
    else:
        gb = Buf.from_list([random.uniform(-5, 5) for _ in range(n)])
        ob = Buf.from_list([0.0]*n)
        t0 = time.perf_counter(); mk.fn(ab.arr, gb.arr, ob.arr, n); t1 = time.perf_counter()
    print("[%s] n=%d: %.2f ms" % (kind, n, (t1-t0)*1000))
    mk.free()

print("=" * 60)
print("结论: %s" % ("全 9 内核由 tl 表驱动发射器生成，逐字节一致 + 执行一致" if all_ok else "失败"))
