# -*- coding: utf-8 -*-
"""gen_ref.py —— boot_gen.tl 的 Python 参考 v0.22（标量 + 1D tensor）。
AST(flat + blks) → x86-64 机器码；与 boot_gen.tl 1:1 对应。

设计：
- 变量槽：rbp - 8*name_id（disp32）；临时槽：rbp - 8*(1000+2*深度+j)
- 常数池：data64 唯一化，RIP 相对引用；OUT：数据区 qword
- tensor 运行时：数据区 [常数池][OUT][HEAP 槽][tensor 静态区][预留堆空间]
  tensor 表示 [u64 len][u64 e0][u64 e1]...；HEAP 槽存堆顶（bump 分配）
- fixup kind：c=常数池 o=OUT l=label h=HEAP槽地址 b=堆空间基址 t=tensor静态区
支持：let/print/for/while/if/break/def/return + NumLit/VarRef + add/sub/mul
       + eq/ge/le/lt + range(常数) + 用户函数（纯 jmp 协议）
       + tensor 字面量 + mk/get(动态下标)/len/cat/empty
"""
import struct

T_LET, T_PRINT, T_FOR, T_IF, T_WHILE, T_BREAK = 1, 2, 3, 4, 5, 6
T_NUM, T_VAR, T_CALL = 11, 12, 13
T_TENSOR = 14
T_DEF, T_RETURN = 7, 8

FIXED = ["tensor", "range", "eq", "ge", "le", "lt", "add", "sub", "mul",
         "cat", "mk", "get", "len", "empty", "set1", "get2", "pack32", "pack64",
         "byte", "band", "bor", "bxor", "bshl", "bshr", "update", "div", "mod",
         "ext_in", "dbl64", "gt", "app", "alloc"]
FID = {n: 12 + k for k, n in enumerate(FIXED)}


class Gen:
    def __init__(self):
        self.code = bytearray()
        self.consts = {}
        self.const_ids = []
        self.fixups = []   # (rel32_pos, kind, target)
        self.data_start = 0
        self.labels = {}      # label_id -> 代码偏移
        self.label_seq = [0]
        self.loop_exits = []  # 循环出口 label 栈（break 用）
        self.loop_depth = 0
        self.funcs = {}       # fn_id -> (param_ids, body_blk, label)
        self.cur_params = {}  # param_id -> k（当前函数参数序号）
        self.cur_shadow = set()  # 当前函数内局部遮蔽（let 变量 id）
        self.print_seq = 0    # print 顺序计数（多 OUT 槽索引）
        self.OUT_N = 8        # OUT 槽数（多 print 输出）
        self.tensors = []     # tensor 字面量内容（build 第一遍收集，静态区顺序）
        self.tensor_idx = 0   # gen_expr 当前字面量索引（与收集顺序一致）
        self.var_types = {}   # 变量 id -> 'f'(标量 double) / 'p'(tensor 指针)
        self.global_ids = []  # 全局变量 id（数据区固定槽）

    # ---- 工具 ----
    def B(self, *bs):
        self.code.extend(bs)

    def D32(self, v):
        self.code += struct.pack("<i", v)

    def Q64(self, v):
        self.code += struct.pack("<q", v)

    def emit_rel32(self, kind, target):
        self.fixups.append((len(self.code), kind, target))
        self.D32(0)

    def emit_rel32_7(self, kind, target):
        """mov/lea 类（3 字节前缀 + rel32@+3，RIP 基准 +7）"""
        self.fixups.append((len(self.code), kind, target))
        self.D32(0)

    # ---- 指令模板 ----
    def push_rbp(self): self.B(0x55)
    def mov_rbp_rsp(self): self.B(0x48, 0x89, 0xE5)
    def sub_rsp_imm(self):
        """逐页探针帧分配：2x(sub rsp,0x1000 + mov qword [rsp],0)。帧 8KB。
        Windows 栈 guard 页机制：一次性 sub 0x8000 跳过未提交区，访问帧底崩溃；
        逐页触碰强制依次提交每页（MSVC _chkstk 探针原理）。"""
        for _ in range(8):
            self.B(0x48, 0x81, 0xEC, 0x00, 0x10, 0x00, 0x00)  # sub rsp, 0x1000
            self.B(0x48, 0xC7, 0x04, 0x24, 0x00, 0x00, 0x00, 0x00)  # mov qword [rsp], 0
    def leave(self): self.B(0xC9)
    def ret(self): self.B(0xC3)

    def movsd_xmm0_rip(self, cid):
        """movsd xmm0, [rip+rel32]（常数）"""
        self.B(0xF2, 0x0F, 0x10, 0x05)
        self.emit_rel32('c', cid)

    def movsd_xmm0_rip_out(self):
        """movsd xmm0, [rip+rel32]（OUT 槽）"""
        self.B(0xF2, 0x0F, 0x10, 0x05)
        self.emit_rel32('o', None)

    def movsd_xmm0_rbp(self, disp):
        self.B(0xF2, 0x0F, 0x10, 0x85)
        self.D32(disp)

    def movsd_xmm1_rbp(self, disp):
        self.B(0xF2, 0x0F, 0x10, 0x8D)
        self.D32(disp)

    def movsd_rbp_xmm0(self, disp):
        self.B(0xF2, 0x0F, 0x11, 0x85)
        self.D32(disp)

    def movsd_out_xmm0(self, idx=0):
        self.B(0xF2, 0x0F, 0x11, 0x05)
        self.emit_rel32('o', idx)

    def addsd(self): self.B(0xF2, 0x0F, 0x58, 0xC1)
    def subsd(self): self.B(0xF2, 0x0F, 0x5C, 0xC1)
    def mulsd(self): self.B(0xF2, 0x0F, 0x59, 0xC1)
    def divsd(self): self.B(0xF2, 0x0F, 0x5E, 0xC1)
    def ucomisd(self): self.B(0x66, 0x0F, 0x2E, 0xC1)

    def mov_r64_imm(self, r, v):
        """mov r64, imm64: 48 B8+r imm64"""
        self.B(0x48, 0xB8 + r)
        self.Q64(v)

    def mov_rax_rbp(self, disp):
        """mov rax, [rbp+disp32]: 48 8B 85 disp32"""
        self.B(0x48, 0x8B, 0x85)
        self.D32(disp)

    def mov_rbp_rax(self, disp):
        """mov [rbp+disp32], rax: 48 89 85 disp32"""
        self.B(0x48, 0x89, 0x85)
        self.D32(disp)

    def cvtsi2sd_xmm0_rax(self):
        """cvtsi2sd xmm0, rax: F2 48 0F 2A C0"""
        self.B(0xF2, 0x48, 0x0F, 0x2A, 0xC0)

    def dec_rax(self): self.B(0x48, 0xFF, 0xC8)
    def inc_r64(self, r): self.B(0x48, 0xFF, 0xC0 + r)

    def jcc(self, cc, lid):
        """jcc rel32: 0F 8x rel32"""
        self.B(0x0F, 0x80 + cc)
        self.emit_rel32('l', lid)

    def push_rax(self): self.B(0x50)
    def pop_rax(self): self.B(0x58)
    def jmp_rax(self): self.B(0xFF, 0xE0)

    def mov_rax_rip(self, lid):
        """mov rax,[rip+rel32]（label 地址——返回点）"""
        self.B(0x48, 0x8B, 0x05)
        self.emit_rel32_7('l', lid)

    def lea_rax_rip(self, lid):
        """lea rax,[rip+rel32]（取返回地址）"""
        self.B(0x48, 0x8D, 0x05)
        self.emit_rel32_7('l', lid)

    def call(self, lid):
        self.B(0xE8)
        self.emit_rel32('l', lid)

    def add_rsp_imm(self, v):
        self.B(0x48, 0x81, 0xC4)
        self.D32(v)

    def pxor_xmm0(self): self.B(0x66, 0x0F, 0xEF, 0xC0)
    def pxor_xmm1(self): self.B(0x66, 0x0F, 0xEF, 0xC9)

    # ---- tensor 运行时指令 ----
    def movq_rax_xmm0(self): self.B(0x66, 0x48, 0x0F, 0x7E, 0xC0)   # movq rax, xmm0
    def movq_rdx_xmm0(self): self.B(0x66, 0x48, 0x0F, 0x7E, 0xD0)   # movq rdx, xmm0
    def movq_xmm0_rax(self): self.B(0x66, 0x48, 0x0F, 0x6E, 0xC0)   # movq xmm0, rax
    def cvtsd2si_rcx_xmm0(self): self.B(0xF2, 0x48, 0x0F, 0x2C, 0xC8)  # cvtsd2si rcx, xmm0
    def cvtsd2si_rax_xmm0(self): self.B(0xF2, 0x48, 0x0F, 0x2C, 0xC0)  # cvtsd2si rax, xmm0
    def and_rax_rcx(self): self.B(0x48, 0x21, 0xC8)                   # and rax, rcx
    def or_rax_rcx(self): self.B(0x48, 0x09, 0xC8)                    # or rax, rcx
    def sar_rax_cl(self): self.B(0x48, 0xD3, 0xF8)                    # sar rax, cl
    def shl_rax_cl(self): self.B(0x48, 0xD3, 0xE0)                    # shl rax, cl
    def shr_rax_imm8(self, k): self.B(0x48, 0xC1, 0xE8, k)            # shr rax, k
    def and_rax_imm8(self): self.B(0x48, 0x81, 0xE0, 0xFF, 0x00, 0x00, 0x00)  # and rax, 0x000000FF
    def mov_rax_mem_rax(self): self.B(0x48, 0x8B, 0x00)             # mov rax, [rax]
    def movsd_xmm0_mem_rax(self): self.B(0xF2, 0x0F, 0x10, 0x00)    # movsd xmm0, [rax]
    def movsd_mem_rax_xmm0(self): self.B(0xF2, 0x0F, 0x11, 0x00)    # movsd [rax], xmm0
    def mov_rax_mem_rax_off8(self): self.B(0x48, 0x8B, 0x40, 0x08)  # mov rax, [rax+8]
    def mov_rcx_mem_rax(self): self.B(0x48, 0x8B, 0x08)             # mov rcx, [rax]
    def mov_rdx_mem_rax(self): self.B(0x48, 0x8B, 0x10)             # mov rdx, [rax]
    def mov_rax_mem_rdx(self): self.B(0x48, 0x8B, 0x02)             # mov rax, [rdx]
    def mov_rcx_mem_rax_off8(self): self.B(0x48, 0x8B, 0x48, 0x08)  # mov rcx, [rax+8]
    def lea_rdx_rax_rcx8(self): self.B(0x48, 0x8D, 0x14, 0xC8)      # lea rdx, [rax+8*rcx]
    def lea_rdx_rax_rcx8_8(self): self.B(0x48, 0x8D, 0x54, 0xC8, 0x08)  # lea rdx, [rax+8*rcx+8]
    def movq_out_rax(self, idx=0):
        """mov [rip+OUT], rax —— 64 位写 OUT 槽（输出指针位型）"""
        self.B(0x48, 0x89, 0x05)
        self.emit_rel32('o', idx)
    def lea_rax_rax_rcx8_8(self): self.B(0x48, 0x8D, 0x44, 0xC8, 0x08)  # lea rax,[rax+8*rcx+8]
    def mov_rax_mem_rax(self): self.B(0x48, 0x8B, 0x00)              # mov rax, [rax]
    def mov_rax_rcx(self): self.B(0x48, 0x89, 0xC8)                 # mov rax, rcx
    def mov_rbx_rax(self): self.B(0x48, 0x89, 0xC3)                 # mov rbx, rax
    def mov_rax_rsi(self): self.B(0x48, 0x89, 0xF0)                 # mov rax, rsi
    def mov_rsi_rcx(self): self.B(0x48, 0x89, 0xCE)                 # mov rsi, rcx
    def mov_rcx_rax(self): self.B(0x48, 0x89, 0xC1)                 # mov rcx, rax
    def mov_mem_rax_rcx(self): self.B(0x48, 0x89, 0x08)             # mov [rax], rcx
    def mov_mem_rcx_rax(self): self.B(0x48, 0x89, 0x01)             # mov [rcx], rax
    def mov_mem_rcx_r8(self): self.B(0x4C, 0x89, 0x01)              # mov [rcx], r8
    def mov_mem_rcx_rax8(self): self.B(0x48, 0x89, 0x41, 0x08)      # mov [rcx+8], rax
    def mov_rax_mem_rcx(self): self.B(0x48, 0x8B, 0x01)             # mov rax, [rcx]
    def mov_mem_rbx_r10(self): self.B(0x4C, 0x89, 0x13)             # mov [rbx], r10
    def movsd_rcx8_xmm0(self): self.B(0xF2, 0x0F, 0x11, 0x41, 0x08) # movsd [rcx+8], xmm0
    def inc_rax(self): self.B(0x48, 0xFF, 0xC0)                     # inc rax
    def cmp_rax_mem(self, disp):
        """cmp rax, [rbp+disp32]: 48 3B 85 disp32"""
        self.B(0x48, 0x3B, 0x85)
        self.D32(disp)

    def mov_mem_rax_rdx(self): self.B(0x48, 0x89, 0x10)             # mov [rax], rdx
    def mov_mem_rbx_rdx(self): self.B(0x48, 0x89, 0x13)             # mov [rbx], rdx
    def mov_mem_rax_off8_rax(self): self.B(0x48, 0x89, 0x40, 0x08)  # mov [rax+8], rax
    def mov_rcx_rbp(self, disp):
        """mov rcx, [rbp+disp32]: 48 8B 8D disp32"""
        self.B(0x48, 0x8B, 0x8D)
        self.D32(disp)
    def mov_rdx_rbp(self, disp):
        """mov rdx, [rbp+disp32]: 48 8B 95 disp32"""
        self.B(0x48, 0x8B, 0x95)
        self.D32(disp)
    def mov_r8_mem_rdx(self): self.B(0x4C, 0x8B, 0x02)              # mov r8, [rdx]
    def mov_r8_mem_r10(self): self.B(0x4D, 0x8B, 0x02)              # mov r8, [r10]
    def mov_r8_mem_r10(self): self.B(0x4D, 0x8B, 0x02)              # mov r8, [r10]
    def mov_r10_rbp(self, disp):
        self.B(0x4C, 0x8B, 0x95)   # mov r10, [rbp+disp32]
        self.D32(disp)
    def mov_r9_lea_rdx_8(self): self.B(0x4C, 0x8D, 0x4A, 0x08)      # lea r9, [rdx+8]
    def mov_r10_lea_rcx_8(self): self.B(0x4C, 0x8D, 0x51, 0x08)     # lea r10, [rcx+8]
    def mov_r11_mem_r9(self): self.B(0x4D, 0x8B, 0x19)              # mov r11, [r9]
    def mov_mem_r10_r11(self): self.B(0x4D, 0x89, 0x1A)             # mov [r10], r11
    def mov_r9_lea_rax_rdx8_16(self): self.B(0x4C, 0x8D, 0x4C, 0xD0, 0x08)  # lea r9,[rax+rdx*8+8]（t 块末尾）
    def cmp_r9_r10(self): self.B(0x4D, 0x39, 0xD1)                  # cmp r9, r10（REX.R=1：reg=r10）
    def mov_r11_lea_r10_r8_16(self): self.B(0x4F, 0x8D, 0x5C, 0xC2, 0x08)  # lea r11,[r10+r8*8+8]（t2 块末尾）
    def cmp_r11_rcx(self): self.B(0x49, 0x39, 0xCB)                 # cmp r11, rcx
    def mov_mem_rbx_r11(self): self.B(0x4C, 0x89, 0x1B)             # mov [rbx], r11
    def add_r9_8(self): self.B(0x49, 0x83, 0xC1, 0x08)              # add r9, 8
    def add_r10_8(self): self.B(0x49, 0x83, 0xC2, 0x08)             # add r10, 8
    def dec_r8(self): self.B(0x49, 0xFF, 0xC8)                      # dec r8
    def test_r8_r8(self): self.B(0x4D, 0x85, 0xC0)                  # test r8, r8
    def mov_qword_rcx_imm0(self): self.B(0x48, 0xC7, 0x01, 0x00, 0x00, 0x00, 0x00)  # mov qword [rcx], 0
    def mov_qword_rcx_imm1(self): self.B(0x48, 0xC7, 0x01, 0x01, 0x00, 0x00, 0x00)  # mov qword [rcx], 1
    def lea_rdx_rcx_8(self): self.B(0x48, 0x8D, 0x51, 0x08)         # lea rdx, [rcx+8]
    def lea_rdx_rcx_16(self): self.B(0x48, 0x8D, 0x51, 0x10)        # lea rdx, [rcx+16]
    def add_rax_r8(self): self.B(0x4C, 0x01, 0xC0)                  # add rax, r8
    def lea_rax_rip_kind(self, kind, target):
        """lea rax, [rip+rel32]（数据区引用）"""
        self.B(0x48, 0x8D, 0x05)
        self.emit_rel32(kind, target)

    def jmp(self, lid):
        self.B(0xE9)
        self.emit_rel32('l', lid)

    def new_label(self):
        self.label_seq[0] += 1
        return self.label_seq[0]

    def label(self, lid):
        self.labels[lid] = len(self.code)

    def const_id(self, v):
        if v not in self.consts:
            self.consts[v] = len(self.const_ids)
            self.const_ids.append(v)
        return self.consts[v]

    # ---- AST 工具 ----
    def blk_idxs(self, blks, no):
        i = 0
        for _ in range(no):
            i += 1 + blks[i]
        L = blks[i]
        return blks[i + 1:i + 1 + L]

    def top_block_no(self, blks):
        i = 0
        nos = 0
        while i < len(blks):
            nos += 1
            i += 1 + blks[i]
        return nos - 1

    # ---- 代码生成 ----
    def gen_expr(self, ast, blks, idx, depth):
        tp, a, b, c = ast[idx], ast[idx + 1], ast[idx + 2], ast[idx + 3]
        t = 1000 + 2 * depth
        if tp == T_NUM:
            self.movsd_xmm0_rip(self.const_id(float(a)))
            self.movsd_rbp_xmm0(-8 * t)
            return 'f'
        if tp == T_VAR:
            # 标量：movsd 加载（位型）；tensor：整数加载（指针）
            if a in self.cur_shadow:
                # 函数内局部遮蔽：读局部槽 rbp-8*a（不查全局）
                if self.var_types.get(a, 'f') == 'p':
                    self.mov_rax_rbp(-8 * a)
                    self.mov_rbp_rax(-8 * t)
                    return 'p'
                self.movsd_xmm0_rbp(-8 * a)
                self.movsd_rbp_xmm0(-8 * t)
                return 'f'
            if a in self.cur_params:
                # 参数优先（遮蔽同名全局）：[rbp+16+8k] 位型直通
                self.movsd_xmm0_rbp(16 + 8 * self.cur_params[a])
                self.movsd_rbp_xmm0(-8 * t)
                return 'f'
            if a in self.global_ids:
                # 全局：数据区固定槽（函数内外同一地址）
                self.lea_rax_rip_kind('g', self.global_ids.index(a))
                if self.var_types.get(a, 'f') == 'p':
                    self.mov_rax_mem_rax()          # rax = [槽]（指针值）
                    self.mov_rbp_rax(-8 * t)
                else:
                    self.movsd_xmm0_mem_rax()       # xmm0 = [槽]（标量位型）
                    self.movsd_rbp_xmm0(-8 * t)      # 存 xmm0（此前误存 rax=槽地址！）
                return 'p' if self.var_types.get(a, 'f') == 'p' else 'f'
            if self.var_types.get(a, 'f') == 'p':
                self.mov_rax_rbp(-8 * a)
                self.mov_rbp_rax(-8 * t)
                return 'p'
            self.movsd_xmm0_rbp(-8 * a)
            self.movsd_rbp_xmm0(-8 * t)
            return 'f'
        if tp == T_TENSOR:
            # tensor 字面量：静态区地址（build 已收集内容与顺序）
            self.lea_rax_rip_kind('t', self.tensor_idx)
            self.tensor_idx += 1
            self.mov_rbp_rax(-8 * t)
            return 'p'
        if tp == T_CALL:
            fn = a
            if fn == FID["ext_in"]:
                # ext_in(k)：k=0 -> ast 指针（=输入区基址）；k=1 -> blks 指针（+8*len+8）
                k = int(ast[self.blk_idxs(blks, b)[0] + 1])  # 字面量参数（NumLit 值）
                if k == 0:
                    self.lea_rax_rip_kind('i', None)      # rax = in_slot 地址
                    self.mov_rax_mem_rax()                # rax = 输入指针
                    self.mov_rbp_rax(-8 * t)
                else:
                    self.lea_rax_rip_kind('i', None)
                    self.mov_rax_mem_rax()
                    self.mov_rcx_mem_rax()                # rcx = ast.len
                    self.lea_rax_rax_rcx8_8()             # rax = 输入 + 8*len+8 = blks
                    self.mov_rbp_rax(-8 * t)
                return 'p'
            if fn in self.funcs:
                # 用户函数调用：参数逆序压栈 → jmp → add rsp → 返回值存槽。
                # 参数求值沿用当前 depth（不重置 0）——否则参数内部原语槽(1000+2d+2..)
                # 会覆盖外层表达式已算出的子结果槽，递归/嵌套调用算错值。
                args = self.blk_idxs(blks, b)
                for arg in reversed(args):
                    self.gen_expr(ast, blks, arg, depth)
                    self.mov_rax_rbp(-8 * (1000 + 2 * depth))
                    self.push_rax()
                ret_l = self.new_label()
                self.lea_rax_rip(ret_l)                  # rax = 返回点绝对地址
                self.push_rax()                          # 压返回地址
                self.jmp(self.funcs[fn][2])              # jmp 进函数
                self.label(ret_l)
                if args:
                    self.add_rsp_imm(8 * len(args))      # 清参数
                self.movsd_rbp_xmm0(-8 * t)
                return 'f'   # 本轮：函数返回标量（tensor 返回下轮）
            args = self.blk_idxs(blks, b)
            if fn == FID["mk"]:
                # mk(v)：堆分配 [1, v]，返回指针
                ta = 1000 + 2 * (depth + 1)
                self.gen_expr(ast, blks, args[0], depth + 1)
                self.lea_rax_rip_kind('h', None)      # rax = heap 槽地址
                self.mov_rcx_mem_rax()                # rcx = 堆顶
                self.mov_qword_rcx_imm1()             # [rcx] = 1（len）
                self.movsd_xmm0_rbp(-8 * ta)          # v
                self.B(0xF2, 0x0F, 0x11, 0x41, 0x08)  # movsd [rcx+8], xmm0
                self.lea_rdx_rcx_16()                 # rdx = 新堆顶
                self.mov_mem_rax_rdx()                # heap 槽 = 新堆顶
                self.mov_rax_rcx()                    # 返回旧堆顶
                self.mov_rbp_rax(-8 * t)
                return 'p'
            if fn == FID["len"]:
                # len(t)：读 [t]，转 double
                ta = 1000 + 2 * (depth + 1)
                self.gen_expr(ast, blks, args[0], depth + 1)
                self.mov_rax_rbp(-8 * ta)             # rax = t 指针
                self.mov_rax_mem_rax()                # rax = len
                self.cvtsi2sd_xmm0_rax()
                self.movsd_rbp_xmm0(-8 * t)
                return 'f'
            if fn == FID["get"]:
                # get(t, i)：i 转整数，元素地址 [t + 8*i + 8]
                ta = 1000 + 2 * (depth + 1)
                tb = 1000 + 2 * (depth + 2)
                self.gen_expr(ast, blks, args[0], depth + 1)
                self.gen_expr(ast, blks, args[1], depth + 2)
                self.mov_rax_rbp(-8 * ta)             # rax = t 指针
                self.movsd_xmm0_rbp(-8 * tb)          # i
                self.cvtsd2si_rcx_xmm0()              # rcx = i
                self.lea_rdx_rax_rcx8_8()             # rdx = t + 8*i + 8
                self.mov_rax_mem_rdx()                # rax = 元素（double 位型）
                self.movq_xmm0_rax()                  # movq xmm0, rax（double 位直通 = 值）
                self.movsd_rbp_xmm0(-8 * t)
                return 'f'
            if fn == FID["empty"]:
                # empty()：堆分配 [0]（len=0 合法 tensor）
                self.lea_rax_rip_kind('h', None)
                self.mov_rcx_mem_rax()
                self.mov_qword_rcx_imm0()             # [rcx] = 0
                self.lea_rdx_rcx_8()                  # 新堆顶
                self.mov_mem_rax_rdx()
                self.mov_rax_rcx()
                self.mov_rbp_rax(-8 * t)
                return 'p'
            if fn == FID["cat"]:
                # cat(a, b)：复制合并，返回新 tensor
                ta = 1000 + 2 * (depth + 1)
                tb = 1000 + 2 * (depth + 2)
                self.gen_expr(ast, blks, args[0], depth + 1)
                self.gen_expr(ast, blks, args[1], depth + 2)
                self.lea_rax_rip_kind('h', None)      # rax = heap 槽地址
                self.mov_rbx_rax()                    # rbx = heap 槽地址（mov rbx, rax）
                self.mov_rcx_mem_rax()                # rcx = 堆顶（新 tensor 基址）
                self.mov_rsi_rcx()                    # rsi = 基址（返回用）
                # 复制 a
                self.mov_rdx_rbp(-8 * ta)             # rdx = a 指针
                self.mov_r8_mem_rdx()                 # r8 = a.len
                self.B(0x4C, 0x89, 0x01)              # mov [rcx], r8（len=a.len 暂）
                self.mov_r9_lea_rdx_8()               # r9 = a 元素首
                self.mov_r10_lea_rcx_8()              # r10 = 目标元素首
                l_a = self.new_label()
                self.label(l_a)
                self.test_r8_r8()
                jz_a = self.new_label()
                self.jcc(4, jz_a)                     # jz（r8=0 跳）
                self.mov_r11_mem_r9()
                self.mov_mem_r10_r11()
                self.add_r9_8()
                self.add_r10_8()
                self.dec_r8()
                self.jmp(l_a)
                self.label(jz_a)
                # 复制 b
                self.mov_rdx_rbp(-8 * tb)
                self.mov_r8_mem_rdx()                 # r8 = b.len
                self.B(0x48, 0x8B, 0x01)              # mov rax, [rcx]（a.len）
                self.add_rax_r8()                     # rax = a.len + b.len
                self.B(0x48, 0x89, 0x01)              # mov [rcx], rax（新 len）
                self.mov_r9_lea_rdx_8()
                l_b = self.new_label()
                self.label(l_b)
                self.test_r8_r8()
                jz_b = self.new_label()
                self.jcc(4, jz_b)
                self.mov_r11_mem_r9()
                self.mov_mem_r10_r11()
                self.add_r9_8()
                self.add_r10_8()
                self.dec_r8()
                self.jmp(l_b)
                self.label(jz_b)
                # 推进堆：heap 槽 = r10（目标末尾）；返回基址
                self.B(0x4C, 0x89, 0x13)              # mov [rbx], r10
                self.mov_rax_rsi()
                self.mov_rbp_rax(-8 * t)
                return 'p'
            if fn == FID["app"]:
                # app(t, t2)：t2 元素追加到 t。
                # 若 t 块末尾==t2 基址 且 t2 块末尾==堆顶 → 零拷贝（len 相加、堆顶推进）
                # 否则复制合并（等价 cat(t, t2)）——O(1) 追加，heap 从 O(n²) 变 O(n)
                ta = 1000 + 2 * (depth + 1)
                tb = 1000 + 2 * (depth + 2)
                self.gen_expr(ast, blks, args[0], depth + 1)
                self.gen_expr(ast, blks, args[1], depth + 2)
                self.lea_rax_rip_kind('h', None)      # rax = heap 槽地址
                self.mov_rbx_rax()                    # rbx = heap 槽地址
                self.mov_rcx_mem_rax()                # rcx = 堆顶
                self.mov_rax_rbp(-8 * ta)
                self.mov_rdx_mem_rax()                # rdx = t.len
                self.mov_r9_lea_rax_rdx8_16()         # r9 = t 块末尾 (t+8+8*len)
                self.mov_r10_rbp(-8 * tb)             # r10 = t2 指针
                self.mov_r8_mem_r10()                 # r8 = t2.len
                l_copy = self.new_label()
                self.cmp_r9_r10()                     # t 末尾 == t2 基址?
                self.jcc(5, l_copy)                   # jne 复制
                self.mov_r11_lea_r10_r8_16()          # r11 = t2 块末尾
                self.cmp_r11_rcx()                    # t2 末尾 == 堆顶?
                self.jcc(5, l_copy)                   # jne 复制
                # 零拷贝：t2 元素搬进 t2 头（t 新末尾）；[t] += len2；堆顶 = t2+8
                self.B(0x4C, 0x01, 0x00)              # add qword [rax], r8（[t] += len2）
                self.B(0x49, 0x8B, 0x52, 0x08)        # mov rdx, [r10+8]（t2 元素）
                self.B(0x49, 0x89, 0x12)              # mov [r10], rdx（搬到 t2 头=t 新末尾）
                self.B(0x4D, 0x8D, 0x5A, 0x08)        # lea r11, [r10+8]（t 新末尾）
                self.mov_mem_rbx_r11()                # mov [rbx], r11（堆顶 = t2+8）
                self.mov_rax_rbp(-8 * ta)
                self.mov_rbp_rax(-8 * t)
                l_done = self.new_label()
                self.jmp(l_done)                      # 跳过复制路径
                self.label(l_copy)
                # 复制退路：等价 cat(t, t2)
                self.mov_rsi_rcx()                    # rsi = 基址（返回用）
                self.mov_rdx_rbp(-8 * ta)
                self.mov_r8_mem_rdx()                 # r8 = t.len
                self.B(0x4C, 0x89, 0x01)              # mov [rcx], r8（len 暂）
                self.mov_r9_lea_rdx_8()
                self.mov_r10_lea_rcx_8()
                l_a = self.new_label()
                self.label(l_a)
                self.test_r8_r8()
                jz_a = self.new_label()
                self.jcc(4, jz_a)
                self.mov_r11_mem_r9()
                self.mov_mem_r10_r11()
                self.add_r9_8()
                self.add_r10_8()
                self.dec_r8()
                self.jmp(l_a)
                self.label(jz_a)
                self.mov_rdx_rbp(-8 * tb)
                self.mov_r8_mem_rdx()
                self.B(0x48, 0x8B, 0x01)              # mov rax, [rcx]（t.len）
                self.add_rax_r8()
                self.B(0x48, 0x89, 0x01)              # mov [rcx], rax（新 len）
                self.mov_r9_lea_rdx_8()
                l_b = self.new_label()
                self.label(l_b)
                self.test_r8_r8()
                jz_b = self.new_label()
                self.jcc(4, jz_b)
                self.mov_r11_mem_r9()
                self.mov_mem_r10_r11()
                self.add_r9_8()
                self.add_r10_8()
                self.dec_r8()
                self.jmp(l_b)
                self.label(jz_b)
                self.B(0x4C, 0x89, 0x13)              # mov [rbx], r10
                self.mov_rax_rsi()
                self.mov_rbp_rax(-8 * t)
                self.label(l_done)
                return 'p'
            if fn == FID["alloc"]:
                # alloc(n)：分配 n 元素全 0 tensor 块（头=[n]，数据全 0），返回指针
                # n 为 double → cvtsd2si 转整数；rcx=n rdx=块基址 rbx=heap槽地址
                # r10=数据起点 r8=计数 rax=填充0
                ta = 1000 + 2 * (depth + 1)
                self.gen_expr(ast, blks, args[0], depth + 1)
                self.movsd_xmm0_rbp(-8 * ta)          # xmm0 = n（double）
                self.cvtsd2si_rcx_xmm0()              # rcx = n（整数）
                self.lea_rax_rip_kind('h', None)      # rax = heap 槽地址
                self.mov_rbx_rax()
                self.mov_rdx_mem_rax()                # rdx = 堆顶（块基址）
                self.B(0x48, 0x89, 0x0A)              # mov [rdx], rcx（块头=n）
                self.B(0x4C, 0x8D, 0x52, 0x08)        # lea r10, [rdx+8]（数据起点）
                self.B(0x49, 0x89, 0xC8)              # mov r8, rcx（计数 = n）
                self.B(0x48, 0x31, 0xC0)              # xor rax, rax（填充 0）
                l_z = self.new_label()
                self.label(l_z)
                self.test_r8_r8()                     # n==0?
                jz_z = self.new_label()
                self.jcc(4, jz_z)
                self.B(0x49, 0x89, 0xC3)              # mov r11, rax（填充值）
                self.B(0x4D, 0x89, 0x1A)              # mov [r10], r11（写 0）
                self.add_r10_8()
                self.dec_r8()
                self.jmp(l_z)
                self.label(jz_z)
                self.B(0x48, 0x8D, 0x44, 0xCA, 0x08)  # lea rax, [rdx+rcx*8+8]（新堆顶）
                self.B(0x48, 0x89, 0x03)              # mov [rbx], rax（heap 槽）
                self.B(0x48, 0x89, 0xD0)              # mov rax, rdx（返回块基址）
                self.mov_rbp_rax(-8 * t)
                return 'p'
            if fn == FID["dbl64"]:
                # dbl64(x)：x 的 double 位型拆 8 字节 → 堆数组 [8, b0..b7]
                ta = 1000 + 2 * (depth + 1)
                self.gen_expr(ast, blks, args[0], depth + 1)
                self.movsd_xmm0_rbp(-8 * ta)
                self.B(0x66, 0x48, 0x0F, 0x7E, 0xC0)  # movq rax, xmm0（位直通）
                self.mov_rbp_rax(2048)                # 暂存位型整数
                self.lea_rax_rip_kind('h', None)
                self.mov_rbx_rax()                    # rbx = heap 槽地址（循环后 rax 被覆盖）
                self.mov_rcx_mem_rax()                # rcx = 堆顶
                self.B(0x48, 0xC7, 0x01, 8, 0, 0, 0)  # [rcx] = 8
                for k in range(8):
                    self.mov_rax_rbp(2048)
                    if k:
                        self.shr_rax_imm8(8 * k)
                    self.and_rax_imm8()
                    self.cvtsi2sd_xmm0_rax()
                    self.B(0xF2, 0x0F, 0x11, 0x41, 8 + 8 * k)  # movsd [rcx+8+8k], xmm0
                self.B(0x48, 0x8D, 0x91)              # lea rdx, [rcx+72]
                self.D32(72)
                self.mov_mem_rbx_rdx()
                self.mov_rax_rcx()
                self.mov_rbp_rax(-8 * t)
                return 'p'
            if fn in (FID["pack32"], FID["pack64"]):
                # 堆分配 [N, b0..bN-1]，字节 = (v>>8k)&0xFF，元素存 double 位型
                N = 4 if fn == FID["pack32"] else 8
                ta = 1000 + 2 * (depth + 1)
                self.gen_expr(ast, blks, args[0], depth + 1)
                self.movsd_xmm0_rbp(-8 * ta)
                self.cvtsd2si_rax_xmm0()              # rax = v（整数）
                self.mov_rbp_rax(2048)                # 存 v 到 rbp+2048（专用）
                self.lea_rax_rip_kind('h', None)
                self.mov_rbx_rax()                    # rbx = heap 槽地址（循环后 rax 被覆盖）
                self.mov_rcx_mem_rax()                # rcx = 堆顶
                self.B(0x48, 0xC7, 0x01, N, 0, 0, 0)  # [rcx] = N
                for k in range(N):
                    self.mov_rax_rbp(2048)            # rax = v
                    if k:
                        self.shr_rax_imm8(8 * k)
                    self.and_rax_imm8()               # rax = 字节
                    self.cvtsi2sd_xmm0_rax()
                    self.B(0xF2, 0x0F, 0x11, 0x41, 8 + 8 * k)  # movsd [rcx+8+8k], xmm0
                self.B(0x48, 0x8D, 0x91)              # lea rdx, [rcx+disp32]
                self.D32(8 + 8 * N)
                self.mov_mem_rbx_rdx()                # [rbx] = 新堆顶（rbx 保存 heap 槽地址）
                self.mov_rax_rcx()
                self.mov_rbp_rax(-8 * t)
                return 'p'
            if fn in (FID["band"], FID["bor"], FID["bshr"], FID["bshl"]):
                # 整数位运算（64 位）：输入 double → 整数 → 运算 → double
                ta = 1000 + 2 * (depth + 1)
                tb = 1000 + 2 * (depth + 2)
                self.gen_expr(ast, blks, args[0], depth + 1)
                self.gen_expr(ast, blks, args[1], depth + 2)
                self.movsd_xmm0_rbp(-8 * ta)
                self.cvtsd2si_rax_xmm0()
                self.movsd_xmm0_rbp(-8 * tb)
                self.cvtsd2si_rcx_xmm0()
                if fn == FID["band"]:
                    self.and_rax_rcx()
                elif fn == FID["bor"]:
                    self.or_rax_rcx()
                elif fn == FID["bshr"]:
                    self.sar_rax_cl()                 # 算术右移（匹配 Python >>）
                else:
                    self.shl_rax_cl()
                self.cvtsi2sd_xmm0_rax()
                self.movsd_rbp_xmm0(-8 * t)
                return 'f'
            if fn == FID["set1"]:
                # set1(t, i, v)：原地写 [t+8*i+8] = v，返回 t（O(1)、无堆分配）
                # 所有 set1 调用方均为预分配全局数组（code/consts/fixups/labels/
                # loop_exits/funcs/var_types/global_ids），无别名共享，原地写安全。
                ta = 1000 + 2 * (depth + 1)
                tb = 1000 + 2 * (depth + 2)
                tc = 1000 + 2 * (depth + 3)
                self.gen_expr(ast, blks, args[0], depth + 1)   # t → 槽 ta（指针位型）
                self.gen_expr(ast, blks, args[1], depth + 2)   # i → 槽 tb
                self.gen_expr(ast, blks, args[2], depth + 3)   # v → 槽 tc
                self.mov_rax_rbp(-8 * ta)             # rax = t 基址
                self.movsd_xmm0_rbp(-8 * tb)
                self.cvtsd2si_rcx_xmm0()              # rcx = i
                self.lea_rdx_rax_rcx8_8()             # rdx = t + 8*i + 8
                self.movsd_xmm0_rbp(-8 * tc)
                self.B(0xF2, 0x0F, 0x11, 0x02)        # movsd [rdx], xmm0
                self.mov_rax_rbp(-8 * ta)             # 返回 t 指针
                self.mov_rbp_rax(-8 * t)
                return 'p'
            if fn == FID["range"]:
                # range(n)：堆分配 [n][0,1,...,n-1]（正确语义，O(n) 填充）
                ta = 1000 + 2 * (depth + 1)
                self.gen_expr(ast, blks, args[0], depth + 1)   # n -> 槽 ta
                self.movsd_xmm0_rbp(-8 * ta)
                self.cvtsd2si_rcx_xmm0()                       # rcx = n
                self.lea_rax_rip_kind('h', None)               # rax = heap 槽地址
                self.mov_rdx_mem_rax()                         # rdx = 旧堆顶（t 基址）
                self.B(0x48, 0x89, 0x0A)                       # mov [rdx], rcx（len = n）
                # 新堆顶 = rdx + rcx*8 + 8 -> r11（REX 4C = W+R，无 X/B；4F 会把 index/base 变 r9/r10）
                self.B(0x4C, 0x8D, 0x5C, 0xCA, 0x08)           # lea r11, [rdx+rcx*8+8]
                self.lea_rax_rip_kind('h', None)               # rax = heap 槽地址
                self.B(0x4C, 0x89, 0x18)                       # mov [rax], r11（新堆顶）
                # 填充 data[i] = i：r8 = 计数器, r9 = 目标地址
                self.B(0x4D, 0x31, 0xC0)                       # xor r8, r8
                self.mov_r9_lea_rdx_8()                        # r9 = rdx + 8
                l_loop = self.new_label()
                l_done = self.new_label()
                self.label(l_loop)
                self.B(0x49, 0x39, 0xC8)                       # cmp r8, rcx
                self.jcc(3, l_done)                            # JAE -> done（r8 >= n）
                self.B(0x4D, 0x89, 0x01)                       # mov [r9], r8（data[i] = i）
                self.B(0x49, 0xFF, 0xC0)                       # inc r8（REX.WR 前缀）
                self.add_r9_8()                                # r9 += 8
                self.jmp(l_loop)
                self.label(l_done)
                self.B(0x48, 0x89, 0xD0)                       # mov rax, rdx（rax = t）
                self.mov_rbp_rax(-8 * t)
                return 'p'
            assert fn in (FID["add"], FID["sub"], FID["mul"], FID["div"]), "未知二元 fn=%d" % fn
            # 槽分配：层 d 结果槽 S(d)=1000+2d；二元 a 存 S(d+1)、b 存 S(d+2)
            # 子 a 用 depth+1、子 b 用 depth+2（串行复用，无冲突）
            ta = 1000 + 2 * (depth + 1)
            tb = 1000 + 2 * (depth + 2)
            self.gen_expr(ast, blks, args[0], depth + 1)
            self.gen_expr(ast, blks, args[1], depth + 2)
            self.movsd_xmm0_rbp(-8 * ta)
            self.movsd_xmm1_rbp(-8 * tb)
            if fn == FID["add"]:
                self.addsd()
            elif fn == FID["sub"]:
                self.subsd()
            elif fn == FID["mul"]:
                self.mulsd()
            else:
                self.divsd()
            self.movsd_rbp_xmm0(-8 * t)
            return 'f'
        raise ValueError("gen_expr 不支持 type %d" % tp)

    def _cmp_jcc(self, ast, blks, cond_idx, lid, invert):
        """求值单个 cmp（eq/ge/lt/le/gt a b），原语义：假时跳 lid；
        invert=True 时：真时跳 lid。"""
        tp, a, b, c = ast[cond_idx], ast[cond_idx + 1], ast[cond_idx + 2], ast[cond_idx + 3]
        assert tp == T_CALL and a in (FID["eq"], FID["ge"], FID["lt"], FID["le"], FID["gt"])
        args = self.blk_idxs(blks, b)
        self.gen_expr(ast, blks, args[0], 0)   # → 槽 1000
        self.gen_expr(ast, blks, args[1], 1)   # → 槽 1002
        self.movsd_xmm0_rbp(-8 * 1000)
        self.movsd_xmm1_rbp(-8 * 1002)
        self.ucomisd()
        if a == FID["eq"]:
            cc = 4 if invert else 5      # JE / JNE
        elif a == FID["ge"]:
            cc = 3 if invert else 2      # JAE / JB
        elif a == FID["lt"]:
            cc = 2 if invert else 3      # JB / JAE
        elif a == FID["le"]:
            cc = 6 if invert else 7      # JBE / JA
        else:
            cc = 7 if invert else 6      # JA / JBE
        self.jcc(cc, lid)

    def gen_cond_jcc(self, ast, blks, cond_idx, lid):
        """求值条件，条件为假时跳 lid。
        支持：cmp(a,b)；sub(1, cmp(a,b)) 取反；sub(1, mul(cmp1,cmp2)) 复合取反。"""
        tp, a, b, c = ast[cond_idx], ast[cond_idx + 1], ast[cond_idx + 2], ast[cond_idx + 3]
        invert = False
        if tp == T_CALL and a == FID["sub"]:
            subs = self.blk_idxs(blks, b)
            assert len(subs) == 2, "sub 条件需 2 参数"
            invert = True
            cond_idx = subs[1]
            tp, a, b, c = ast[cond_idx], ast[cond_idx + 1], ast[cond_idx + 2], ast[cond_idx + 3]
        if tp == T_CALL and a == FID["mul"]:
            muls = self.blk_idxs(blks, b)
            if invert:
                # sub(1, mul(...))：条件假（跳 lid）⇔ eq1 && eq2 都真：
                # 任一子条件假 → 跳过 jmp lid；都真 → jmp lid
                l_done = self.new_label()
                for mi in muls:
                    self.gen_cond_jcc(ast, blks, mi, l_done)
                self.jmp(lid)
                self.label(l_done)
            else:
                # 裸 mul(a,b)：循环条件 = a && b；条件假 ⇔ 任一子条件假 → 跳 lid
                # 子条件递归 gen_cond_jcc（支持 sub 取反嵌套）
                for mi in muls:
                    self.gen_cond_jcc(ast, blks, mi, lid)
            return
        if tp == T_CALL and a in (FID["eq"], FID["ge"], FID["lt"], FID["le"], FID["gt"]):
            self._cmp_jcc(ast, blks, cond_idx, lid, invert)
            return
        # 兜底：任意表达式条件——求值到槽 1000，0 假（跳 lid）/非 0 真
        self.gen_expr(ast, blks, cond_idx, 0)
        self.movsd_xmm0_rbp(-8 * 1000)
        self.pxor_xmm1()
        self.ucomisd()
        if invert:
            self.jcc(5, lid)   # JNE：非 0 跳 lid
        else:
            self.jcc(4, lid)   # JE：0 跳 lid
        return

    def gen_block(self, ast, blks, blk_no):
        for si in self.blk_idxs(blks, blk_no):
            self.gen_stmt(ast, blks, si)

    def gen_for(self, ast, blks, var_id, it_idx, body_blk):
        """for var in range(N)：it = Call(range, [NumLit N])。"""
        tp, a, b, c = ast[it_idx], ast[it_idx + 1], ast[it_idx + 2], ast[it_idx + 3]
        assert tp == T_CALL and a == FID["range"]
        args = self.blk_idxs(blks, b)
        assert ast[args[0]] == T_NUM, "range 参数需数字字面量"
        N = ast[args[0] + 1]
        l_start = self.new_label()
        l_exit = self.new_label()
        self.loop_exits.append(l_exit)
        self.loop_depth += 1
        cnt_slot = 2000 + 2 * self.loop_depth
        end_slot = 2000 + 2 * self.loop_depth + 1
        self.mov_r64_imm(0, 0)                 # rax = 0（i 初值）
        self.mov_rbp_rax(-8 * cnt_slot)
        self.mov_r64_imm(0, N)                 # rax = N（终止值）
        self.mov_rbp_rax(-8 * end_slot)        # 终止值存栈槽（嵌套安全）
        self.label(l_start)
        self.mov_rax_rbp(-8 * cnt_slot)
        self.cvtsi2sd_xmm0_rax()
        self.movsd_rbp_xmm0(-8 * var_id)
        self.B(0x48, 0x3B, 0x85)              # cmp rax, [rbp+disp32]
        self.D32(-8 * end_slot)
        self.jcc(0xD, l_exit)                  # jge 退出（i >= N）
        self.gen_block(ast, blks, body_blk)
        self.mov_rax_rbp(-8 * cnt_slot)
        self.inc_r64(0)                         # inc rax
        self.mov_rbp_rax(-8 * cnt_slot)
        self.jmp(l_start)
        self.label(l_exit)
        self.loop_exits.pop()
        self.loop_depth -= 1

    def gen_stmt(self, ast, blks, idx):
        tp, a, b, c = ast[idx], ast[idx + 1], ast[idx + 2], ast[idx + 3]
        if tp == 17:
            # 表达式语句（裸调用）：求值丢弃
            self.gen_expr(ast, blks, a, 0)
            return
        if tp == T_LET:
            k = self.gen_expr(ast, blks, b, 0)
            if a in self.cur_shadow:
                # 函数内局部遮蔽：写局部槽 rbp-8*a（不写全局）
                if k == 'p':
                    self.mov_rbp_rax(-8 * a)
                else:
                    self.movsd_rbp_xmm0(-8 * a)
                return
            if a in self.global_ids:
                self.lea_rax_rip_kind('g', self.global_ids.index(a))
                if k == 'p':
                    self.mov_rcx_rbp(-8 * (1000 + 2 * 0))   # rcx = 临时槽（指针值）
                    self.mov_mem_rax_rcx()      # [槽] = rcx
                else:
                    self.movsd_mem_rax_xmm0()   # movsd [rax], xmm0
            elif k == 'p':
                self.mov_rbp_rax(-8 * a)      # tensor 指针存槽
            else:
                self.movsd_rbp_xmm0(-8 * a)   # 标量 double 存槽
            return
        if tp == T_PRINT:
            out_i = self.print_seq
            self.print_seq += 1
            k = self.gen_expr(ast, blks, a, 0)
            if k == 'p':
                # 输出指针位型：mov rax,[槽]; mov [OUT+idx*8],rax
                self.mov_rax_rbp(-8 * (1000 + 2 * 0))
                self.movq_out_rax(out_i)
            else:
                self.movsd_out_xmm0(out_i)
            return
        if tp == T_FOR:
            self.gen_for(ast, blks, a, b, c)
            return
        if tp == T_WHILE:
            l_start = self.new_label()
            l_exit = self.new_label()
            self.loop_exits.append(l_exit)
            self.label(l_start)
            self.gen_cond_jcc(ast, blks, a, l_exit)
            self.gen_block(ast, blks, b)
            self.jmp(l_start)
            self.label(l_exit)
            self.loop_exits.pop()
            return
        if tp == T_IF:
            l_else = self.new_label()
            l_end = self.new_label()
            self.gen_cond_jcc(ast, blks, a, l_else)
            self.gen_block(ast, blks, b)
            self.jmp(l_end)
            self.label(l_else)
            if c != 0:
                self.gen_block(ast, blks, c)
            self.label(l_end)
            return
        if tp == T_BREAK:
            assert self.loop_exits, "break 在循环外"
            self.jmp(self.loop_exits[-1])
            return
        if tp == T_RETURN:
            self.gen_expr(ast, blks, a, 0)
            self.movsd_xmm0_rbp(-8 * 1000)
            self.leave()
            self.pop_rax()
            self.jmp_rax()   # 统一 jmp 返回：ret 触发 CET 影子栈校验（调用是 jmp，影子栈无条目）
            return
        if tp == T_DEF:
            return   # 函数段由 build 统一生成
        if tp == 16:
            return   # global 声明：槽语义与普通变量一致，无需生成代码
        raise ValueError("gen_stmt 不支持 type %d" % tp)

    def _blk_tree(self, ast, blks, blk_no, seen=None):
        """递归收集块号集合（含嵌套 if/while/for 体）。"""
        if seen is None:
            seen = set()
        if blk_no in seen:
            return seen
        seen.add(blk_no)
        for si in self.blk_idxs(blks, blk_no):
            tp = ast[si]
            if tp == T_FOR:
                self._blk_tree(ast, blks, ast[si + 3], seen)
            elif tp in (T_IF, T_WHILE):
                self._blk_tree(ast, blks, ast[si + 2], seen)
                if tp == T_IF and ast[si + 3]:
                    self._blk_tree(ast, blks, ast[si + 3], seen)
        return seen

    def collect_types(self, ast, blks, blk_no):
        """递归收集 let/for 变量类型：'p'=tensor 指针，'f'=标量。"""
        for si in self.blk_idxs(blks, blk_no):
            tp, a, b, c = ast[si], ast[si + 1], ast[si + 2], ast[si + 3]
            if tp == T_LET:
                self.var_types[a] = self.expr_kind(ast, blks, b)
            elif tp == T_FOR:
                self.var_types[a] = 'f'          # 循环变量是标量
                self.collect_types(ast, blks, c)
            elif tp in (T_IF, T_WHILE):
                self.collect_types(ast, blks, b)
                if tp == T_IF and c:
                    self.collect_types(ast, blks, c)
            # def 体由 build 函数段递归（本轮函数参数标量）

    def expr_kind(self, ast, blks, idx):
        tp = ast[idx]
        if tp == T_TENSOR:
            return 'p'
        if tp == T_CALL and ast[idx + 1] in (FID["mk"], FID["cat"], FID["app"], FID["empty"],
                                             FID["ext_in"], FID["set1"]):
            return 'p'
        return 'f'

    def build(self, ast, blks):
        top = self.top_block_no(blks)
        # 第一遍：收集函数（def 节点 → 参数/body/标签）
        for si in self.blk_idxs(blks, top):
            if ast[si] == T_DEF:
                fn_id = ast[si + 1]
                p_start = ast[si + 2]
                body = ast[si + 3]
                params = []
                j = p_start
                while ast[j] == 20:
                    params.append(ast[j + 1])
                    j += 4
                self.funcs[fn_id] = (params, body, self.new_label())
        # 收集变量类型（递归所有块：let/for/if/while）
        self.var_types = {}
        for blk_no in range(self.top_block_no(blks) + 1):
            self.collect_types(ast, blks, blk_no)
        # 收集全局变量 id（T_GLOBAL=16：cnt, n1, n2）
        gseen = set()
        for blk_no in range(self.top_block_no(blks) + 1):
            for si in self.blk_idxs(blks, blk_no):
                if ast[si] == 16:
                    cnt = ast[si + 1]
                    if cnt >= 1 and ast[si + 2] >= 12 and ast[si + 2] not in gseen:
                        gseen.add(ast[si + 2]); self.global_ids.append(ast[si + 2])
                    if cnt >= 2 and ast[si + 3] >= 12 and ast[si + 3] not in gseen:
                        gseen.add(ast[si + 3]); self.global_ids.append(ast[si + 3])
        # tl 语义：main 块顶层 let 变量自动全局（函数体内可直接引用顶层变量）
        for si in self.blk_idxs(blks, top):
            if ast[si] == T_LET and ast[si + 1] not in gseen:
                gseen.add(ast[si + 1]); self.global_ids.append(ast[si + 1])
        # 收集 tensor 字面量（生成顺序：先 main 流程（top 块非 def 语句），
        # 再函数段按 funcs 顺序；块/表达式递归——与 gen_expr 的 tensor_idx 分配顺序严格一致）
        self.tensors = []
        def collect_expr(e):
            tp = ast[e]
            if tp == T_TENSOR:
                elems = self.blk_idxs(blks, ast[e + 2])
                self.tensors.append([ast[ei + 1] for ei in elems])
            elif tp == T_CALL:
                for arg in self.blk_idxs(blks, ast[e + 2]):
                    collect_expr(arg)
        def collect_stmt(s):
            tp = ast[s]
            if tp == T_LET:
                collect_expr(ast[s + 2])
            elif tp == T_PRINT:
                collect_expr(ast[s + 1])
            elif tp == T_RETURN:
                collect_expr(ast[s + 1])
            elif tp == T_FOR:
                collect_block(ast[s + 3])          # body blk（iter 为 range(N)，无 tensor）
            elif tp == T_WHILE:
                collect_expr(ast[s + 1])          # cond 是表达式节点
                collect_block(ast[s + 2])
            elif tp == T_IF:
                collect_expr(ast[s + 1])          # cond 是表达式节点
                collect_block(ast[s + 2])
                if ast[s + 3]:
                    collect_block(ast[s + 3])
            elif tp == 9:                           # update：expr 在 b 字段
                collect_expr(ast[s + 2])
            elif tp == 17:                          # 表达式语句（裸调用）：expr 在 a 字段
                collect_expr(ast[s + 1])
        def collect_block(blk):
            for si in self.blk_idxs(blks, blk):
                collect_stmt(si)
        for si in self.blk_idxs(blks, top):
            if ast[si] != T_DEF:
                collect_stmt(si)
        for fn_id, (params, body, lab) in self.funcs.items():
            collect_block(body)
        # 函数内局部遮蔽表：函数体内（含嵌套块）let/for 变量（排除函数内 global 声明）
        func_shadows = {}
        for fn_id, (params, body, lab) in self.funcs.items():
            gdecl = set()
            for blk_no in self._blk_tree(ast, blks, body):
                for si in self.blk_idxs(blks, blk_no):
                    if ast[si] == 16:
                        cnt = ast[si + 1]
                        if cnt >= 1 and ast[si + 2] >= 12:
                            gdecl.add(ast[si + 2])
                        if cnt >= 2 and ast[si + 3] >= 12:
                            gdecl.add(ast[si + 3])
            shadow = set()
            for blk_no in self._blk_tree(ast, blks, body):
                for si in self.blk_idxs(blks, blk_no):
                    if ast[si] == T_LET and ast[si + 1] >= 12 and ast[si + 1] not in gdecl:
                        shadow.add(ast[si + 1])
                    elif ast[si] == T_FOR and ast[si + 1] >= 12 and ast[si + 1] not in gdecl:
                        shadow.add(ast[si + 1])
            func_shadows[fn_id] = shadow

        # 第二遍：主流程（跳过 def）
        self.push_rbp()
        self.mov_rbp_rsp()
        self.sub_rsp_imm()
        # 输入保存：rcx = 输入指针（CFUNCTYPE 首参）→ 数据区输入槽（不碰调用者栈）
        self.mov_rax_rcx()
        self.mov_rcx_rax()
        self.lea_rax_rip_kind('i', None)
        self.mov_mem_rax_rcx()
        # heap 初始化：heap 槽 = heap_base（数据区尾）
        self.lea_rax_rip_kind('h', None)      # rax = heap 槽地址
        self.mov_rcx_rax()                    # rcx = heap 槽地址
        self.lea_rax_rip_kind('b', None)      # rax = heap_base
        self.B(0x48, 0x89, 0x01)              # mov [rcx], rax
        for si in self.blk_idxs(blks, top):
            if ast[si] == T_DEF:
                continue
            self.gen_stmt(ast, blks, si)
        self.pxor_xmm0()      # 返回值清零（避免 ctypes 收尾把 xmm0 当指针读；print 值在 OUT 槽）
        self.leave()
        self.ret()
        # 函数段
        self.fn_ranges = {}
        for fn_id, (params, body, lab) in self.funcs.items():
            self.fn_ranges[fn_id] = len(self.code)
            self.label(lab)
            self.push_rbp()
            self.mov_rbp_rsp()
            self.sub_rsp_imm()
            self.cur_params = {pid: k for k, pid in enumerate(params)}
            self.cur_shadow = func_shadows.get(fn_id, set())
            self.gen_block(ast, blks, body)
            self.pxor_xmm0()      # 缺省返回 0
            self.leave()
            self.pop_rax()
            self.jmp_rax()
            self.cur_params = {}
            self.cur_shadow = set()
        self.cur_shadow = set()  # 当前函数内局部遮蔽（let 变量 id）
        # 数据区：[常数池][OUT 槽][HEAP 槽][tensor 静态区]
        self.data_start = len(self.code)
        for v in self.const_ids:
            self.Q64(struct.unpack("<q", struct.pack("<d", v))[0])
        out_pos = len(self.code)
        for _ in range(self.OUT_N):
            self.Q64(0)                       # OUT 槽（多 print 输出）
        out_addr = self.data_start + 8 * len(self.const_ids)
        in_slot_addr = out_addr + 8 * self.OUT_N
        self.Q64(0)                           # 输入槽（main 序言写入 in_addr）
        heap_slot_addr = in_slot_addr + 8
        self.Q64(0)                           # HEAP 槽（运行时写入初值）
        globals_addr = heap_slot_addr + 8
        for _ in self.global_ids:
            self.Q64(0)                       # 全局变量槽（数据区固定地址）
        tensor_addr = globals_addr + 8 * len(self.global_ids)
        for td in self.tensors:
            self.Q64(len(td))
            for e in td:
                # 元素统一存 double 位型（与 mk/cat 一致，get 用 movq 位直通）
                self.Q64(struct.unpack("<q", struct.pack("<d", float(e)))[0])
        tensor_bytes = sum(8 * (len(td) + 1) for td in self.tensors)
        heap_base_addr = tensor_addr + tensor_bytes
        for pos, kind, target in self.fixups:
            if kind == 'i':
                addr = in_slot_addr
            elif kind == 'c':
                addr = self.data_start + 8 * target
            elif kind == 'o':
                addr = out_addr + 8 * (target or 0)
            elif kind == 'l':
                addr = self.labels[target]
            elif kind == 'h':
                addr = heap_slot_addr
            elif kind == 'b':
                addr = heap_base_addr
            elif kind == 'g':
                addr = globals_addr + 8 * target
            elif kind == 't':
                off = 0
                for k in range(target):
                    off += 8 * (len(self.tensors[k]) + 1)
                addr = tensor_addr + off
            else:
                raise ValueError(kind)
            # rel32 统一在 pos，RIP 基准 = 指令尾 = pos+4
            self.code[pos:pos + 4] = struct.pack('<i', addr - (pos + 4))
        return bytes(self.code), self.data_start, out_pos, heap_base_addr
