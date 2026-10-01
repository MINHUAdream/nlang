# -*- coding: utf-8 -*-
"""v0.18 验证：表驱动发射器（boot_enc_mm.tl）产出 mm2 三重循环内核
1) 与 tl_emit.gen_mm2() 逐字节一致（153 字节）
2) 装载执行与纯 Python 矩阵乘法逐位一致
"""
import io
import os
import random
import time
import ctypes

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)

import tl
from tl_emit import gen_mm2
from tl_native import Buf
from tlb_loadmc import load_mc

_P = ctypes.c_void_p
_I = ctypes.c_int
MM2_SIG = (None, _P, _P, _P, _I, _I, _I)

print("=" * 60)
print("v0.18 验证：tl 表驱动发射器 · mm2（三重循环）")
print("=" * 60)

src = io.open("boot_enc_mm.tl", encoding="utf-8").read()
ast = tl.Parser(tl.lex(src)).parse()
eng = tl.Engine()
eng.run(ast, quiet=True)
tl_bytes = bytes(int(b) & 0xFF for b in eng.vars["code"].value)

ref = gen_mm2()
ok_b = tl_bytes == ref
print("[1] tl 表驱动产出 %d 字节 | 与 gen_mm2() 逐字节一致: %s" % (len(tl_bytes), ok_b))
if not ok_b:
    for i, (a, b) in enumerate(zip(tl_bytes, ref)):
        if a != b:
            print("  首个差异 @%d: tl=%02X ref=%02X" % (i, a, b))
            break
    print("  tl :", " ".join("%02X" % b for b in tl_bytes))
    print("  ref:", " ".join("%02X" % b for b in ref))
else:
    print("  字节: %s" % " ".join("%02X" % b for b in tl_bytes))

mk = load_mc(tl_bytes, MM2_SIG)
random.seed(20260926)
all_ok = True
for trial in range(6):
    M = random.randint(1, 9); K = random.randint(1, 9); N = random.randint(1, 9)
    a = [random.uniform(-3, 3) for _ in range(M*K)]
    b = [random.uniform(-3, 3) for _ in range(K*N)]
    # 纯 Python 语义（与 kernels.c tl_mm2 同累加契约）
    exp = []
    for i in range(M):
        for j in range(N):
            s = 0.0
            for k in range(K):
                s += a[i*K+k] * b[k*N+j]
            exp.append(s)
    ab = Buf.from_list(a); bb = Buf.from_list(b); ob = Buf.from_list([0.0]*(M*N))
    mk.fn(ab.arr, bb.arr, ob.arr, M, K, N)
    if ob.to_list() != exp:
        all_ok = False
        print("  trial %d (%dx%dx%d) 不一致！" % (trial, M, K, N))
        break
print("[2] 装载执行 == 纯 Python mm: %s（6 轮随机形状）" % all_ok)

# 性能：256x256x10（v0.14 基准 120.6ms vs C 225.3ms）
M = K = N = 256
a = [random.uniform(-1, 1) for _ in range(M*K)]
b = [random.uniform(-1, 1) for _ in range(K*N)]
ab = Buf.from_list(a); bb = Buf.from_list(b); ob = Buf.from_list([0.0]*(M*N))
t0 = time.perf_counter(); mk.fn(ab.arr, bb.arr, ob.arr, M, K, N); t1 = time.perf_counter()
print("[3] mm2 %dx%dx%d: %.1f ms（v0.14 基准: 120.6ms vs C 225.3ms）" % (M, K, N, (t1-t0)*1000))
mk.free()

print("=" * 60)
print("结论: %s" % ("mm2 三重循环内核由 tl 表驱动发射器生成" if (ok_b and all_ok) else "失败"))
