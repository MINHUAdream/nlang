# -*- coding: utf-8 -*-
"""v0.15 自举桥：装载 tl 语言发射的机器码字节序列为可执行内核。"""
import ctypes


def load_mc(code_bytes, sig):
    """装载 tl 程序输出的字节（1D 序列，0-255）为可执行内核并返回 ctypes 可调用 fn。

    v0.15 意义：机器码由 tl 程序生成（boot_emit.tl），此处仅充当 loader
    （VirtualAlloc + 类型包装），不参与任何指令编码/偏移计算。
    """
    from tl_emit import MachineKernel
    raw = bytes(int(b) & 0xFF for b in code_bytes)
    mk = MachineKernel(raw, sig)
    return mk
