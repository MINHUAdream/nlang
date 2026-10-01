# -*- coding: utf-8 -*-
"""v0.20 验证：softmax 表驱动发射器
1) tl 表驱动 1035 字节 vs _gen_softmax 逐字节一致
2) 装载执行 == 纯 Python 语义（复刻 _tl_exp 位构造 + Neumaier）逐位一致
3) 性能采样
"""
import io
import os
import math
import random
import struct
import time
import ctypes

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)

import tl
import tl_emit
from tl_native import Buf
from tlb_loadmc import load_mc

# ---- exp 逐位参考（复刻 _tl_exp：floor 分解 + 16 阶 Horner + 位构造 2^k）----
_INV_LN2 = 1.4426950408889634
_LN2 = 0.6931471805599453
_EXP_C = [4.7794773323873853e-14, 7.6471637318198164e-13, 1.1470745597729725e-11,
          1.6059043836821613e-10, 2.08767569878681e-09, 2.505210838544172e-08,
          2.7557319223985888e-07, 2.7557319223985893e-06, 2.4801587301587302e-05,
          0.00019841269841269841, 0.0013888888888888889, 0.0083333333333333332,
          0.041666666666666664, 0.16666666666666666, 0.5, 1.0]
_INF = float("inf")


def exp_py(x):
    if x != x:
        return x
    if x == _INF:
        return _INF
    if x == -_INF:
        return 0.0
    x3 = x
    x = x * _INV_LN2 + 0.5
    k = math.floor(x)                      # roundsd floor
    # cvttsd2si 溢出模拟：超出 int64 → INT64_MIN（Intel INDEFINITE）
    if not (-2**63 <= k <= 2**63 - 1):
        k = -2**63
    if k > 1023:
        return _INF
    t = x3 - float(k) * _LN2
    acc = _EXP_C[0]
    for i in range(1, 16):
        acc = acc * t + _EXP_C[i]
    acc = acc * t + 1.0
    bits = ((k + 1023) << 52) & 0xFFFFFFFFFFFFFFFF   # 位构造 2^k（shl rax,52 低 64 位）
    two_k = struct.unpack("<d", struct.pack("<Q", bits))[0]
    return acc * two_k


def softmax_py(a):
    rows, cols = len(a), len(a[0])
    out = []
    for r in range(rows):
        m = max(a[r])
        ex = [exp_py(v - m) for v in a[r]]
        s = sum(ex)                        # Neumaier == Python sum
        out.append([v / s for v in ex])
    return out


print("=" * 60)
print("v0.20 验证：softmax 表驱动发射器（_tl_exp 内联 + Neumaier 内联）")
print("=" * 60)

# 1) 逐字节
src = io.open("boot_enc_softmax.tl", encoding="utf-8").read()
ast = tl.Parser(tl.lex(src)).parse()
eng = tl.Engine()
eng.run(ast, quiet=True)
tl_bytes = bytes(int(b) & 0xFF for b in eng.vars["code"].value)
ref = tl_emit._gen_softmax()
ok_b = tl_bytes == ref
print("[softmax] tl 表驱动 %d 字节 | 与 _gen_softmax 逐字节一致: %s" % (len(tl_bytes), ok_b))
if not ok_b:
    for i, (a, b) in enumerate(zip(tl_bytes, ref)):
        if a != b:
            print("  首个差异 @%d: tl=%02X ref=%02X" % (i, a, b))
            break
    raise SystemExit(1)

# 2) 装载执行 == 纯 Python 逐位
mk = load_mc(tl_bytes, (None, ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_void_p))
random.seed(20260925)
ok_x = True
for trial in range(8):
    R = random.randint(1, 6)
    C = random.randint(1, 8)
    # 混合数值：常规、偏大/偏负、nan、inf（不超 int64 截断域）
    a = []
    for _ in range(R * C):
        r = random.random()
        if r < 0.7:
            a.append(random.uniform(-10, 10))
        elif r < 0.85:
            a.append(random.uniform(-300, 300))
        elif r < 0.93:
            a.append(float("nan") if random.random() < 0.5 else float("inf"))
        else:
            a.append(float("-inf") if random.random() < 0.5 else random.uniform(-700, 700))
    am = [a[i * C:(i + 1) * C] for i in range(R)]
    exp = softmax_py(am)
    ab = Buf.from_list(a)
    ob = Buf.from_list([0.0] * (R * C))
    mk.fn(ab.arr, R, C, ob.arr)
    got = [ob.to_list()[i * C:(i + 1) * C] for i in range(R)]
    def same(a, b):
        return a == b or (a != a and b != b)

    if not all(same(got[r][c], exp[r][c]) for r in range(R) for c in range(C)):
        ok_x = False
        print("  trial %d 不一致! R=%d C=%d 输入=%s" % (trial, R, C, a))
        for r in range(R):
            for c in range(C):
                g, e = got[r][c], exp[r][c]
                if not same(g, e):
                    print("    [%d][%d] got=%r exp=%r" % (r, c, g, e))
        break
print("[softmax] 装载执行 == 纯 Python 逐位: %s（8 轮随机，含 NaN/inf/大数）" % ok_x)

# 3) 性能
R, C = 256, 256
a = [random.uniform(-5, 5) for _ in range(R * C)]
ab = Buf.from_list(a)
ob = Buf.from_list([0.0] * (R * C))
t0 = time.perf_counter()
mk.fn(ab.arr, R, C, ob.arr)
t1 = time.perf_counter()
print("[softmax] 256x256: %.3f ms" % ((t1 - t0) * 1000))
mk.free()

print("=" * 60)
print("结论: %s" % ("softmax 内核由 tl 表驱动发射器生成，逐字节一致 + 执行一致" if (ok_b and ok_x) else "失败"))
