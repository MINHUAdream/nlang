# -*- coding: utf-8 -*-
"""v0.16 自举验证：表驱动发射器（boot_enc.tl）产出 relu 机器码
1) 与 tl_emit 逐字节一致
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
RELU_SIG = (None, _P, _P, _I)

print("=" * 60)
print("v0.16 验证：tl 表驱动通用发射器（boot_enc.tl）")
print("=" * 60)

# 免检执行（Parser + Engine，不经形状检查）
src = io.open("boot_enc.tl", encoding="utf-8").read()
ast = tl.Parser(tl.lex(src)).parse()
eng = tl.Engine()
eng.run(ast, quiet=True)
tl_code = eng.vars["code"].value
tl_bytes = bytes(int(b) & 0xFF for b in tl_code)
print("[1] tl 表驱动发射器产出 %d 字节" % len(tl_bytes))

ref = bytes(_gen_single_loop("relu"))
ok_bytes = tl_bytes == ref
print("[2] 与 tl_emit._gen_single_loop('relu') 逐字节一致: %s" % ok_bytes)
if not ok_bytes:
    for i, (a, b) in enumerate(zip(tl_bytes, ref)):
        if a != b:
            print("  首个差异 @%d: tl=%02X ref=%02X" % (i, a, b))
            break
    print("  tl :", " ".join("%02X" % b for b in tl_bytes))
    print("  ref:", " ".join("%02X" % b for b in ref))
else:
    print("  字节: %s" % " ".join("%02X" % b for b in tl_bytes))

mk = load_mc(tl_bytes, RELU_SIG)
random.seed(20260926)
all_ok = True
for trial in range(6):
    n = random.randint(1, 513)
    x = [random.uniform(-5, 5) for _ in range(n)]
    expected = [v if v > 0 else 0.0 for v in x]
    xb = Buf.from_list(x)
    ob = Buf.from_list([0.0] * n)
    mk.fn(xb.arr, ob.arr, n)
    if ob.to_list() != expected:
        all_ok = False
        print("  trial %d 不一致！" % trial)
        break
print("[3] 装载执行 relu == 纯 Python 语义: %s（6 轮随机形状）" % all_ok)

n = 1 << 20
xb = Buf.from_list([random.uniform(-5, 5) for _ in range(n)])
ob = Buf.from_list([0.0] * n)
t0 = time.perf_counter()
mk.fn(xb.arr, ob.arr, n)
t1 = time.perf_counter()
print("[4] n=%d: %.2f ms" % (n, (t1 - t0) * 1000))
mk.free()

print("=" * 60)
print("结论: %s" % ("表驱动发射器打通：tl 语言内两遍编码生成机器码" if (ok_bytes and all_ok) else "失败"))
