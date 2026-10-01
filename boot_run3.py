# -*- coding: utf-8 -*-
"""v0.16 验证：表驱动发射器（换表即换内核）——relu / add 双内核
1) 均与 tl_emit 逐字节一致
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
SIG = {
    "relu": (None, _P, _P, _I),
    "add":  (None, _P, _P, _P, _I),
}
KERNELS = [("relu", "boot_enc.tl", "relu"),
           ("add", "boot_enc_add.tl", "add")]

print("=" * 60)
print("v0.16 验证：tl 表驱动通用发射器（换表即换内核）")
print("=" * 60)

all_ok = True
for name, src_file, ref_kind in KERNELS:
    src = io.open(src_file, encoding="utf-8").read()
    ast = tl.Parser(tl.lex(src)).parse()
    eng = tl.Engine()
    eng.run(ast, quiet=True)
    tl_bytes = bytes(int(b) & 0xFF for b in eng.vars["code"].value)
    ref = bytes(_gen_single_loop(ref_kind))
    ok_b = tl_bytes == ref
    print("[%s] tl 表驱动产出 %d 字节 | 与 tl_emit 逐字节一致: %s"
          % (name, len(tl_bytes), ok_b))
    if not ok_b:
        all_ok = False
        for i, (a, b) in enumerate(zip(tl_bytes, ref)):
            if a != b:
                print("  首个差异 @%d: tl=%02X ref=%02X" % (i, a, b))
                break
        continue
    mk = load_mc(tl_bytes, SIG[name])
    random.seed(20260926)
    ok_x = True
    for trial in range(6):
        n = random.randint(1, 513)
        a = [random.uniform(-5, 5) for _ in range(n)]
        if name == "relu":
            expected = [v if v > 0 else 0.0 for v in a]
            ab = Buf.from_list(a)
            ob = Buf.from_list([0.0] * n)
            mk.fn(ab.arr, ob.arr, n)
        else:
            b = [random.uniform(-5, 5) for _ in range(n)]
            expected = [x + y for x, y in zip(a, b)]
            ab = Buf.from_list(a)
            bb = Buf.from_list(b)
            ob = Buf.from_list([0.0] * n)
            mk.fn(ab.arr, bb.arr, ob.arr, n)
        if ob.to_list() != expected:
            ok_x = False
            print("  %s trial %d 不一致！" % (name, trial))
            break
    print("[%s] 装载执行 == 纯 Python 语义: %s（6 轮随机形状）" % (name, ok_x))
    all_ok = all_ok and ok_x
    n = 1 << 20
    ab = Buf.from_list([random.uniform(-5, 5) for _ in range(n)])
    if name == "relu":
        ob = Buf.from_list([0.0] * n)
        t0 = time.perf_counter(); mk.fn(ab.arr, ob.arr, n); t1 = time.perf_counter()
    else:
        bb = Buf.from_list([random.uniform(-5, 5) for _ in range(n)])
        ob = Buf.from_list([0.0] * n)
        t0 = time.perf_counter(); mk.fn(ab.arr, bb.arr, ob.arr, n); t1 = time.perf_counter()
    print("[%s] n=%d: %.2f ms" % (name, n, (t1 - t0) * 1000))
    mk.free()

print("=" * 60)
print("结论: %s" % ("换表即换内核：tl 表驱动发射器通用性验证通过" if all_ok else "失败"))
