# -*- coding: utf-8 -*-
"""v0.12 构建 bench_c.exe（zig cc，-ffp-contract=off）。"""
import os, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ziglang

z = os.path.join(os.path.dirname(ziglang.__file__), "zig.exe")
d = os.path.dirname(os.path.abspath(__file__))
cmd = [z, "cc", "-O2", "-ffp-contract=off",
       os.path.join(d, "bench_c.c"),
       "-o", os.path.join(d, "bench_c.exe")]
print(" ".join(cmd))
r = subprocess.run(cmd, capture_output=True, text=True)
print(r.stdout[-3000:] if len(r.stdout) > 3000 else r.stdout)
print(r.stderr[-3000:] if len(r.stderr) > 3000 else r.stderr)
print("exit", r.returncode)
