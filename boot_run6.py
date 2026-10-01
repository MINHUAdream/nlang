# -*- coding: utf-8 -*-
"""v0.19 验证：表驱动发射器 · total/colsum/transpose（规约 + 转置）
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
import tl_emit
from tl_native import Buf
from tlb_loadmc import load_mc

_P = ctypes.c_void_p
_I = ctypes.c_int
SIG = {
    "total":      (ctypes.c_double, _P, _I),
    "colsum":     (None, _P, _I, _I, _P),
    "transpose":  (None, _P, _I, _I, _P),
}
FILES = {"total": "boot_enc_total.tl", "colsum": "boot_enc_colsum.tl",
         "transpose": "boot_enc_transpose.tl"}

print("=" * 60)
print("v0.19 验证：规约 + 转置 表驱动发射器")
print("=" * 60)

all_ok = True
for name, f in FILES.items():
    src = io.open(f, encoding="utf-8").read()
    ast = tl.Parser(tl.lex(src)).parse()
    eng = tl.Engine()
    eng.run(ast, quiet=True)
    tl_bytes = bytes(int(b) & 0xFF for b in eng.vars["code"].value)
    ref_fn = {"total": tl_emit._gen_total, "colsum": tl_emit._gen_colsum,
              "transpose": tl_emit._gen_transpose}[name]
    ref = ref_fn()
    ok_b = tl_bytes == ref
    print("[%s] tl 表驱动 %d 字节 | 逐字节一致: %s" % (name, len(tl_bytes), ok_b))
    if not ok_b:
        all_ok = False
        for i, (a, b) in enumerate(zip(tl_bytes, ref)):
            if a != b:
                print("  首个差异 @%d: tl=%02X ref=%02X" % (i, a, b))
                break
        continue
    mk = load_mc(tl_bytes, SIG[name])
    random.seed(20260926 + len(name))
    ok_x = True
    for trial in range(6):
        if name == "total":
            n = random.randint(1, 300)
            x = [random.uniform(-5, 5) for _ in range(n)]
            exp = sum(x)
            xb = Buf.from_list(x)
            got = mk.fn(xb.arr, n)
            if got != exp:
                ok_x = False
                print("  total trial %d 不一致!" % trial)
                break
        elif name == "colsum":
            M = random.randint(1, 9); N = random.randint(1, 9)
            g = [random.uniform(-3, 3) for _ in range(M*N)]
            exp = [sum(g[m*N+n] for m in range(M)) for n in range(N)]
            gb = Buf.from_list(g); ob = Buf.from_list([0.0]*N)
            mk.fn(gb.arr, M, N, ob.arr)
            if ob.to_list() != exp:
                ok_x = False
                print("  colsum trial %d 不一致!" % trial)
                break
        else:
            M = random.randint(1, 9); N = random.randint(1, 9)
            a = [random.uniform(-3, 3) for _ in range(M*N)]
            exp = [a[i*N+j] for j in range(N) for i in range(M)]
            ab = Buf.from_list(a); ob = Buf.from_list([0.0]*(M*N))
            mk.fn(ab.arr, M, N, ob.arr)
            if ob.to_list() != exp:
                ok_x = False
                print("  transpose trial %d 不一致!" % trial)
                break
    print("[%s] 执行 == 纯 Python: %s（6 轮随机）" % (name, ok_x))
    all_ok = all_ok and ok_x
    # 性能采样
    if name == "total":
        n = 1 << 20
        xb = Buf.from_list([random.uniform(-5, 5) for _ in range(n)])
        t0 = time.perf_counter(); v = mk.fn(xb.arr, n); t1 = time.perf_counter()
        print("[%s] n=%d: %.2f ms (sum=%.4f)" % (name, n, (t1-t0)*1000, v))
    elif name == "colsum":
        M = 256; N = 256
        gb = Buf.from_list([random.uniform(-3, 3) for _ in range(M*N)])
        ob = Buf.from_list([0.0]*N)
        t0 = time.perf_counter(); mk.fn(gb.arr, M, N, ob.arr); t1 = time.perf_counter()
        print("[%s] %dx%d: %.2f ms" % (name, M, N, (t1-t0)*1000))
    else:
        M = 512; N = 512
        ab = Buf.from_list([random.uniform(-3, 3) for _ in range(M*N)])
        ob = Buf.from_list([0.0]*(M*N))
        t0 = time.perf_counter(); mk.fn(ab.arr, M, N, ob.arr); t1 = time.perf_counter()
        print("[%s] %dx%d: %.2f ms" % (name, M, N, (t1-t0)*1000))
    mk.free()

print("=" * 60)
print("结论: %s" % ("规约 + 转置三内核由 tl 表驱动发射器生成" if all_ok else "失败"))
