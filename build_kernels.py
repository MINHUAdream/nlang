# -*- coding: utf-8 -*-
"""用 zig 编译自研 C 内核 kernels.c -> kernels.dll（ctypes 加载，零第三方运行时）。"""
import os
import subprocess
import sys

import ziglang

HERE = os.path.dirname(os.path.abspath(__file__))
zig = os.path.join(os.path.dirname(ziglang.__file__), "zig.exe")
src = os.path.join(HERE, "kernels.c")
out = os.path.join(HERE, "kernels.dll")

# -ffp-contract=off：禁止 FMA 收缩（s += a*b 必须严格逐步舍入，与 Python 逐位一致）
# 数值内核全自研（含 exp）——不依赖 libm，默认 native target 即可
r = subprocess.run([zig, "cc", "-O2", "-ffp-contract=off", "-shared",
                    src, "-o", out],
                   capture_output=True, text=True)
if r.returncode != 0:
    print("编译失败：")
    print(r.stdout)
    print(r.stderr)
    sys.exit(1)
print("kernels.dll 已生成：", out, os.path.getsize(out), "bytes")
