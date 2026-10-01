# -*- coding: utf-8 -*-
"""tl v0.13 —— 自研 x86-64 机器码生成器（tl 编译器的后端）。
kernels.tl（tl 内核源码）→ AST → 本生成器 → 可执行机器码（VirtualAlloc 直接运行）。
零 C / 零 Rust / 零 LLVM：指令编码、寄存器分配、ABI 全部自研。
"""
import ctypes, struct

# ================= x86-64 编码器 =================
class Enc:
    def __init__(self):
        self.code = bytearray()
        self.labels = {}      # name -> offset（记录 label 定义处的当前长度）
        self.fixups = []      # (pos, target_label, insn_len)
        self.rip_fixups = []  # (rel32_pos, data_label)
    def B(self, *bs):
        for b in bs:
            self.code.append(b & 0xFF)
    def D32(self, v):
        self.code += struct.pack("<i", v)
    def Q64(self, v):
        self.code += struct.pack("<q", v)
    def label(self, name):
        self.labels[name] = len(self.code)
    def here(self):
        return len(self.code)

    def _rex(self, w, r, x, b):
        v = 0x40 | (w << 3) | (r << 2) | (x << 1) | b
        if v != 0x40:
            self.B(v)
    def _modrm(self, mod, reg, rm):
        self.B((mod << 6) | ((reg & 7) << 3) | (rm & 7))
    def _sib(self, scale, idx, base):
        sc = {1: 0, 2: 1, 4: 2, 8: 3}[scale]
        self.B((sc << 6) | ((idx & 7) << 3) | (base & 7))

    # ---- 寄存器搬移 / 算术 ----
    def mov_r64_r64(self, dst, src):
        """mov dst, src（48 89：reg=src, rm=dst）"""
        self._rex(1, src >> 3, 0, dst >> 3)
        self.B(0x89); self._modrm(3, src, dst)
    def mov_r64_imm(self, r, imm):
        self._rex(1, 0, 0, r >> 3)
        self.B(0xB8 + (r & 7)); self.Q64(imm)
    def mov_r64_m64(self, dst, base, disp):
        """mov dst, [base+disp]（disp8 或 disp32；SIB 无索引）"""
        self._rex(1, dst >> 3, 0, base >> 3)
        self.B(0x8B)
        if -128 <= disp <= 127 and disp != 0:
            self._modrm(1, dst, 4); self._sib(1, 4, base); self.B(disp & 0xFF)
        else:
            self._modrm(2, dst, 4); self._sib(1, 4, base); self.D32(disp)
    def mov_r64_m64_rsp(self, dst, disp):
        """mov dst, [rsp+disp]（rsp 作 base）"""
        self._rex(1, dst >> 3, 0, 0)
        self.B(0x8B)
        if -128 <= disp <= 127 and disp != 0:
            self._modrm(1, dst, 4); self._sib(1, 4, 4); self.B(disp & 0xFF)
        else:
            self._modrm(2, dst, 4); self._sib(1, 4, 4); self.D32(disp)
    def add_r64_r64(self, d, s):
        """add d, s（03：reg=d, rm=s）"""
        self._rex(1, d >> 3, 0, s >> 3)
        self.B(0x03); self._modrm(3, d, s)
    def imul_r64_r64(self, d, s):
        """imul d, s：0F AF——reg=目标(d), rm=源(s)；imul r64, r/m64"""
        self._rex(1, d >> 3, 0, s >> 3)
        self.B(0x0F, 0xAF); self._modrm(3, d, s)
    def shr_r64_imm(self, r, n):
        """shr r64, imm8（REX.W C1 /5 ib）"""
        self._rex(1, 0, 0, r >> 3)
        self.B(0xC1); self._modrm(3, 5, r); self.B(n)
    def shl_r64_imm(self, r, n):
        self._rex(1, 0, 0, r >> 3)
        self.B(0xC1, 0xE0 + (r & 7), n)
    def inc_r64(self, r):
        self._rex(1, 0, 0, r >> 3)
        self.B(0xFF, 0xC0 + (r & 7))
    def dec_r64(self, r):
        self._rex(1, 0, 0, r >> 3)
        self.B(0xFF, 0xC8 + (r & 7))
    def xor_r32_r32(self, d, s):
        self._rex(0, d >> 3, 0, s >> 3)
        self.B(0x33); self._modrm(3, d, s)
    def cmp_r64_r64(self, a, b):
        """cmp a, b（39：reg=b, rm=a）"""
        self._rex(1, b >> 3, 0, a >> 3)
        self.B(0x39); self._modrm(3, b, a)
    def cmp_r64_imm(self, a, imm):
        """cmp a, imm32（48 81 /7 id32）"""
        self._rex(1, 0, 0, a >> 3)
        self.B(0x81); self._modrm(3, 7, a); self.D32(imm)
    def push_r64(self, r):
        self._rex(0, 0, 0, r >> 3)
        self.B(0x50 + (r & 7))
    def pop_r64(self, r):
        self._rex(0, 0, 0, r >> 3)
        self.B(0x58 + (r & 7))
    def ret(self):
        self.B(0xC3)

    def add_r64_imm(self, r, imm):
        """add r64, imm32（48 81 C0+r）"""
        self._rex(1, 0, 0, r >> 3)
        self.B(0x81, 0xC0 + (r & 7)); self.D32(imm)
    def sub_r64_r64(self, d, s):
        """sub r/m64, r64（48 29：reg=src, rm=dst）"""
        self._rex(1, s >> 3, 0, d >> 3)
        self.B(0x29); self._modrm(3, s, d)
    def sub_r64_imm(self, r, imm):
        self._rex(1, 0, 0, r >> 3)
        self.B(0x81, 0xE8 + (r & 7)); self.D32(imm)

    # ---- v0.14：SSE 算术 / 转换 / 位操作 ----
    def arith_sse(self, opcode, d, s):
        """F2 0F xx：addsd(58)/subsd(5C)/mulsd(59)/divsd(5E)"""
        self._rex(0, d >> 3, 0, s >> 3)
        self.B(0xF2, 0x0F, opcode); self._modrm(3, d, s)
    def divsd(self, d, s): self.arith_sse(0x5E, d, s)
    def addsd(self, d, s): self.arith_sse(0x58, d, s)
    def subsd(self, d, s): self.arith_sse(0x5C, d, s)
    def mulsd(self, d, s): self.arith_sse(0x59, d, s)
    def movsd_xmm_xmm(self, d, s):
        self.B(0xF2)
        self._rex(0, d >> 3, 0, s >> 3)
        self.B(0x0F, 0x10); self._modrm(3, d, s)
    def andpd_xmm_xmm(self, d, s):
        """fabs：andpd xmm_d, xmm_s（66 0F 54）"""
        self.B(0x66)
        self._rex(0, d >> 3, 0, s >> 3)
        self.B(0x0F, 0x54); self._modrm(3, d, s)
    def roundsd(self, d, s, mode):
        """roundsd xmm_d, xmm_s, imm8（SSE4.1：66 0F 3A 0B；mode 1=floor）"""
        self.B(0x66)
        self._rex(0, d >> 3, 0, s >> 3)
        self.B(0x0F, 0x3A, 0x0B); self._modrm(3, d, s); self.B(mode)
    def cvttsd2si_r64(self, r, x):
        """cvttsd2si r64, xmm（截断转整数；F2 0F 2C）"""
        self.B(0xF2)
        self._rex(1, r >> 3, 0, x >> 3)
        self.B(0x0F, 0x2C); self._modrm(3, r, x)
    def cvtsi2sd_xmm(self, x, r):
        """cvtsi2sd xmm, r64（整数转 double；F2 0F 2A）"""
        self.B(0xF2)
        self._rex(1, x >> 3, 0, r >> 3)
        self.B(0x0F, 0x2A); self._modrm(3, x, r)
    def movq_r64_xmm(self, r, x):
        """movq r64, xmm（读位模式；66 0F 7E /r；modrm.reg=xmm、modrm.rm=r64）
        REX.R=xmm 高 3 位、REX.B=r64 高 3 位（_fix16：与 movq_xmm_r64 同向）"""
        self.B(0x66)
        self._rex(1, x >> 3, 0, r >> 3)
        self.B(0x0F, 0x7E); self._modrm(3, x, r)
    def movq_xmm_r64(self, x, r):
        # legacy 前缀（66）必须在 REX 之前 → 66 48 0F 6E
        self.B(0x66)
        self._rex(1, x >> 3, 0, r >> 3)
        self.B(0x0F, 0x6E); self._modrm(3, x, r)

    # ---- v0.14：RIP 相对数据段（常数区）----
    def movsd_load_xmm_rip(self, x, data_label):
        """movsd xmm, [rip+rel]：F2 0F 10 modrm(00, x, 101) + rel32"""
        self.rip_fixups.append((len(self.code), data_label))
        self.B(0xF2)
        self._rex(0, x >> 3, 0, 0)
        self.B(0x0F, 0x10)
        self._modrm(0, x, 5)
        self.D32(0)
    def data64(self, label, bits):
        """数据段常量（64 位位模式）；定义 label 于当前位置"""
        self.labels[label] = len(self.code)
        self.code += struct.pack("<Q", bits)

    # ---- SSE2 ----
    def movsd_load_xmm(self, x, base, idx, scale):
        """movsd xmm, [base+idx*scale]（无 disp；idx 无时传 None）"""
        self.B(0xF2)
        self._rex(0, x >> 3, idx >> 3 if idx is not None else 0, base >> 3)
        self.B(0x0F, 0x10)
        self._modrm(0, x, 4)
        self._sib(scale, 4 if idx is None else idx, base)
    def movsd_load_xmm_disp(self, x, base, disp):
        """movsd xmm, [base+disp]（rax 基址 + 常量偏移场景统一用 SIB 无索引 + disp）"""
        self.B(0xF2)
        self._rex(0, x >> 3, 0, base >> 3)
        self.B(0x0F, 0x10)
        if -128 <= disp <= 127 and disp != 0:
            self._modrm(1, x, 4); self._sib(1, 4, base); self.B(disp & 0xFF)
        else:
            self._modrm(2, x, 4); self._sib(1, 4, base); self.D32(disp)
    def movsd_store_xmm(self, x, base, idx, scale):
        self.B(0xF2)
        self._rex(0, x >> 3, idx >> 3 if idx is not None else 0, base >> 3)
        self.B(0x0F, 0x11)
        self._modrm(0, x, 4)
        self._sib(scale, 4 if idx is None else idx, base)
    def movsd_store_xmm_disp(self, x, base, disp):
        self.B(0xF2)
        self._rex(0, x >> 3, 0, base >> 3)
        self.B(0x0F, 0x11)
        if -128 <= disp <= 127 and disp != 0:
            self._modrm(1, x, 4); self._sib(1, 4, base); self.B(disp & 0xFF)
        else:
            self._modrm(2, x, 4); self._sib(1, 4, base); self.D32(disp)
    def movupd_load_xmm(self, x, base):
        """movupd xmm, [base]（SSE2 未对齐双精度向量加载）"""
        self.B(0x66)
        self._rex(0, x >> 3, 0, base >> 3)
        self.B(0x0F, 0x10); self._modrm(0, x, 4); self._sib(1, 4, base)
    def movupd_store_xmm(self, x, base):
        """movupd [base], xmm（SSE2 未对齐双精度向量存储）"""
        self.B(0x66)
        self._rex(0, x >> 3, 0, base >> 3)
        self.B(0x0F, 0x11); self._modrm(0, x, 4); self._sib(1, 4, base)
    def addpd_xmm_xmm(self, d, s):
        """addpd xmm_d, xmm_s（SSE2 双精度 packed add）"""
        self.B(0x66)
        self._rex(0, d >> 3, 0, s >> 3)
        self.B(0x0F, 0x58); self._modrm(3, d, s)
    def movsd_xmm_xmm(self, d, s):
        self.B(0xF2)
        self._rex(0, d >> 3, 0, s >> 3)
        self.B(0x0F, 0x10); self._modrm(3, d, s)
    def arith_sse(self, opcode, d, s):
        """addsd/mulsd/subsd/divsd：opcode F2 0F xx"""
        self._rex(0, d >> 3, 0, s >> 3)
        self.B(0xF2, 0x0F, opcode); self._modrm(3, d, s)
    def pxor_xmm(self, d, s):
        self.B(0x66)
        self._rex(0, d >> 3, 0, s >> 3)
        self.B(0x0F, 0xEF); self._modrm(3, d, s)
    def movq_xmm_r64(self, x, r):
        # 注意 x86-64 前缀顺序：legacy 前缀（66）必须在 REX 之前 → 66 48 0F 6E
        self.B(0x66)
        self._rex(1, x >> 3, 0, r >> 3)
        self.B(0x0F, 0x6E); self._modrm(3, x, r)
    def ucomisd(self, d, s):
        self.B(0x66)
        self._rex(0, d >> 3, 0, s >> 3)
        self.B(0x0F, 0x2E); self._modrm(3, d, s)

    # ---- 控制流 ----
    def jcc(self, cc, target):
        """0F 8x rel32（6 字节）"""
        self.fixups.append((len(self.code), target, 6))
        self.B(0x0F, 0x80 | cc)
        self.D32(0)
    def jmp(self, target):
        """E9 rel32（5 字节）"""
        self.fixups.append((len(self.code), target, 5))
        self.B(0xE9); self.D32(0)
    def jl(self, t): self.jcc(JL, t)
    def jge(self, t): self.jcc(JGE, t)
    def jle(self, t): self.jcc(JLE, t)
    def jg(self, t): self.jcc(JG, t)
    def je(self, t): self.jcc(JE, t)
    def jbe(self, t): self.jcc(JBE, t)
    def ja(self, t): self.jcc(JA, t)

    def patch(self):
        for pos, target, insn_len in self.fixups:
            t = self.labels[target]
            rel = t - (pos + insn_len)
            field = pos + (2 if insn_len == 6 else 1)  # jcc: rel32 在 pos+2；jmp: 在 pos+1
            self.code[field:field + 4] = struct.pack("<i", rel)
        for pos, dl in self.rip_fixups:
            # movsd_load_xmm_rip 为 8 字节：F2 0F 10 modrm(101) + rel32（字段在 pos+4）
            rel = self.labels[dl] - (pos + 8)
            self.code[pos + 4:pos + 8] = struct.pack("<i", rel)

# 条件码（0F 8x）
JL, JGE, JLE, JG = 0x0C, 0x0D, 0x0E, 0x0F
JBE, JA = 0x06, 0x07
JE = 0x04
JE, JNE = 0x04, 0x05

# ================= 内核生成 =================
# Windows x64 ABI：前 4 整数/指针参数 rcx/rdx/r8/r9，第 5+ 在 [rsp+40+8i]；
# 前 4 中的 double 参数在 xmm0-3。
R_RCX, R_RDX, R_R8, R_R9 = 1, 2, 8, 9
X_XMM0, X_XMM1, X_XMM2, X_XMM3 = 0, 1, 2, 3

def _gen_single_loop(kind):
    """逐元素内核：for i<n { out[i] = f(x[i],...) }。
    kind: relu | add | sub | mul | scale | upd | relu_mask | sqg
    内部寄存器：rsi=源1、rdi=out、r11=n、rcx=i、xmm0 值、xmm1 临时、xmm2/3 常数/标量。
    参数布局（Windows x64）：
      relu(x,out,n):         rcx=x rdx=out r8=n
      add/sub/mul(a,b,out,n): rcx=a rdx=b r8=out r9=n
      scale(x,out,n,cv):      rcx=x rdx=out r8=n xmm3=cv
      upd(v,g,out,n,lr):      rcx=v rdx=g r8=out r9=n [rsp+40]=lr
      relu_mask/sqg(x,g,out,n): rcx=x rdx=g r8=out r9=n
    """
    KIND_REG = {
        "relu":      (R_RCX, R_RDX, R_R8),
        "add":       (R_RCX, R_R8, R_R9),
        "sub":       (R_RCX, R_R8, R_R9),
        "mul":       (R_RCX, R_R8, R_R9),
        "scale":     (R_RCX, R_RDX, R_R8),
        "scale_div": (R_RCX, R_RDX, R_R8),
        "upd":       (R_RCX, R_R8, R_R9),
        "relu_mask": (R_RCX, R_R8, R_R9),
        "sqg":       (R_RCX, R_R8, R_R9),
    }
    s1, oreg, nreg = KIND_REG[kind]
    e = Enc()
    e.push_r64(0x6)   # rsi
    e.push_r64(0x7)   # rdi
    e.push_r64(0xB)   # r11
    e.mov_r64_r64(0x6, s1)     # rsi = 源1
    e.mov_r64_r64(0x7, oreg)   # rdi = out
    e.mov_r64_r64(0xB, nreg)   # r11 = n
    e.xor_r32_r32(1, 1)        # rcx = 0 (i)
    e.label("L")
    # 载入 x[i]
    e.movsd_load_xmm(X_XMM0, 0x6, 1, 8)   # xmm0 = [rsi + rcx*8]
    if kind == "relu":
        e.pxor_xmm(X_XMM1, X_XMM1)
        e.ucomisd(X_XMM0, X_XMM1)         # 比较 x, 0
        e.jcc(JBE, "Lz")                   # x<=0 → 0
        e.movsd_store_xmm(X_XMM0, 0x7, 1, 8)
        e.jmp("Lnext")
        e.label("Lz")
        e.pxor_xmm(X_XMM0, X_XMM0)
        e.movsd_store_xmm(X_XMM0, 0x7, 1, 8)
        e.label("Lnext")
    elif kind == "add" or kind == "sub" or kind == "mul":
        e.movsd_load_xmm(X_XMM1, R_RDX, 1, 8)   # xmm1 = [rdx + rcx*8]（arg2 是源2）
        if kind == "add":
            e.arith_sse(0x58, X_XMM0, X_XMM1)   # addsd
        elif kind == "sub":
            e.arith_sse(0x5C, X_XMM0, X_XMM1)   # subsd
        else:
            e.arith_sse(0x59, X_XMM0, X_XMM1)   # mulsd
        e.movsd_store_xmm(X_XMM0, 0x7, 1, 8)
    elif kind == "scale":
        # cv 在 xmm3（第 4 参数 double）
        e.arith_sse(0x59, X_XMM0, X_XMM3)       # mulsd xmm0, xmm3
        e.movsd_store_xmm(X_XMM0, 0x7, 1, 8)
    elif kind == "scale_div":
        # out[i] = x[i] / cv（对齐 kernels.c tl_scale 与 tlb VM 语义）
        e.arith_sse(0x5E, X_XMM0, X_XMM3)       # divsd xmm0, xmm3
        e.movsd_store_xmm(X_XMM0, 0x7, 1, 8)
    elif kind == "upd":
        # out[i] = v[i] - lr*g[i]；lr 在 [rsp+40]（push×3 后 +24 → [rsp+64]）
        e.movsd_xmm_xmm(X_XMM1, X_XMM0)         # xmm1 = v[i]
        e.movsd_load_xmm(X_XMM0, R_RDX, 1, 8)   # xmm0 = g[i]
        e.movsd_load_xmm_disp(X_XMM2, 4, 64)    # xmm2 = lr（[rsp+64]）
        e.arith_sse(0x59, X_XMM0, X_XMM2)       # xmm0 = lr*g[i]
        e.arith_sse(0x5C, X_XMM1, X_XMM0)       # xmm1 = v[i]-lr*g[i]
        e.movsd_store_xmm(X_XMM1, 0x7, 1, 8)
    elif kind == "relu_mask":
        # out[i] = x[i]>0 ? g[i] : 0；x 在 rsi、g 在 rdx（arg2）、out 在 rdi（arg3）
        e.pxor_xmm(X_XMM1, X_XMM1)
        e.ucomisd(X_XMM0, X_XMM1)
        e.jcc(JBE, "Lz")
        e.movsd_load_xmm(X_XMM0, R_RDX, 1, 8)   # xmm0 = g[i]
        e.movsd_store_xmm(X_XMM0, 0x7, 1, 8)
        e.jmp("Lnext")
        e.label("Lz")
        e.pxor_xmm(X_XMM0, X_XMM0)
        e.movsd_store_xmm(X_XMM0, 0x7, 1, 8)
        e.label("Lnext")
    elif kind == "sqg":
        # out[i] = 2.0*x[i]*g[i]；g 在 rdx（arg2）
        e.movsd_load_xmm(X_XMM1, R_RDX, 1, 8)   # xmm1 = g[i]
        e.arith_sse(0x59, X_XMM0, X_XMM1)       # xmm0 = x*g
        e.mov_r64_imm(0, 0x4000000000000000)    # rax = 2.0 位模式
        e.movq_xmm_r64(X_XMM2, 0)
        e.arith_sse(0x59, X_XMM0, X_XMM2)       # xmm0 = 2*x*g
        e.movsd_store_xmm(X_XMM0, 0x7, 1, 8)
    # i++
    e.inc_r64(1)
    e.cmp_r64_r64(1, 0xB)
    e.jl("L")
    e.pop_r64(0xB); e.pop_r64(0x7); e.pop_r64(0x6)
    e.ret()
    e.patch()
    return bytes(e.code)

def gen_mm2():
    """kernel mm2(a, b, out, M, K, N)：朴素三重循环（与 C tl_mm2 同累加契约）。
    ABI: rcx=a rdx=b r8=out r9=M [rsp+40]=K [rsp+48]=N
    寄存器: rsi=a rdi=b rbx=out r12=N r13=M r14=K; rcx=i rdx=j r8=k rax=addr; xmm0=s
    """
    e = Enc()
    e.push_r64(0x6); e.push_r64(0x7); e.push_r64(0x3)   # rsi rdi rbx
    e.push_r64(0xC); e.push_r64(0xD); e.push_r64(0xE)   # r12 r13 r14
    # 读参数（push×6 → 栈参偏移 40+48=88）
    e.mov_r64_r64(0x6, R_RCX)          # rsi = a
    e.mov_r64_r64(0x7, R_RDX)          # rdi = b
    e.mov_r64_r64(0x3, R_R8)           # rbx = out
    e.mov_r64_r64(0xD, R_R9)           # r13 = M
    e.mov_r64_m64_rsp(0xE, 88)         # r14 = K
    e.mov_r64_m64_rsp(0xC, 96)         # r12 = N
    e.xor_r32_r32(1, 1)                # rcx = 0 (i)
    e.label("Li")
    e.xor_r32_r32(2, 2)                # rdx = 0 (j)
    e.label("Lj")
    e.pxor_xmm(X_XMM0, X_XMM0)         # s = 0
    e.xor_r32_r32(8, 8)                # r8 = 0 (k)
    e.label("Lk")
    # a[i*K+k]
    e.mov_r64_r64(0, 1)                # rax = i
    e.imul_r64_r64(0, 0xE)             # rax = i*K
    e.add_r64_r64(0, 8)                # rax = i*K+k
    e.shl_r64_imm(0, 3)                # rax *= 8
    e.movsd_load_xmm(X_XMM1, 0x6, 0, 1)  # xmm1 = a[rax]（SIB: base=rsi idx=rax scale=1）
    # b[k*N+j]
    e.mov_r64_r64(0, 8)                # rax = k
    e.imul_r64_r64(0, 0xC)             # rax = k*N
    e.add_r64_r64(0, 2)                # rax = k*N+j
    e.shl_r64_imm(0, 3)
    e.movsd_load_xmm(X_XMM2, 0x7, 0, 1)  # xmm2 = b[rax]
    e.arith_sse(0x59, X_XMM1, X_XMM2)  # xmm1 = a*b（mulsd xmm1, xmm2）
    e.arith_sse(0x58, X_XMM0, X_XMM1)  # s += a*b（addsd xmm0, xmm1）
    e.inc_r64(8)                       # k++
    e.cmp_r64_r64(8, 0xE)              # k < K
    e.jl("Lk")
    # out[i*N+j] = s
    e.mov_r64_r64(0, 1)
    e.imul_r64_r64(0, 0xC)
    e.add_r64_r64(0, 2)
    e.shl_r64_imm(0, 3)
    e.movsd_store_xmm(X_XMM0, 0x3, 0, 1)  # out[rax] = s
    e.inc_r64(2)                       # j++
    e.cmp_r64_r64(2, 0xC)              # j < N
    e.jl("Lj")
    e.inc_r64(1)                       # i++
    e.cmp_r64_r64(1, 0xD)              # i < M
    e.jl("Li")
    e.pop_r64(0xE); e.pop_r64(0xD); e.pop_r64(0xC)
    e.pop_r64(0x3); e.pop_r64(0x7); e.pop_r64(0x6)
    e.ret()
    e.patch()
    return bytes(e.code)

# ================= 机器码加载 =================
_VALLOC = ctypes.windll.kernel32.VirtualAlloc
_VFREE = ctypes.windll.kernel32.VirtualFree
_VALLOC.restype = ctypes.c_void_p
_VALLOC.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32, ctypes.c_uint32]
_VFREE.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32]
MEM_COMMIT_RESERVE = 0x3000
PAGE_EXECUTE_READWRITE = 0x40
MEM_RELEASE = 0x8000

class MachineKernel:
    """一段自研机器码 + ctypes 调用封装。"""
    __slots__ = ("code", "addr", "fn", "sig")
    def __init__(self, code, sig):
        self.code = code
        self.sig = sig
        n = len(code)
        addr = _VALLOC(None, n, MEM_COMMIT_RESERVE, PAGE_EXECUTE_READWRITE)
        assert addr, "VirtualAlloc 失败"
        ctypes.memmove(addr, code, n)
        self.addr = addr
        self.fn = ctypes.CFUNCTYPE(*sig)(addr)
    def free(self):
        if self.addr:
            _VFREE(self.addr, 0, MEM_RELEASE)
            self.addr = None

# 各内核签名（kernels.tl 参数序 → ctypes）。注意：CFUNCTYPE(*sig) 首元素是 restype！
_P = ctypes.c_void_p
_I = ctypes.c_int
_D = ctypes.c_double
SIG = {
    "relu":      (None, _P, _P, _I),
    "elem2_add": (None, _P, _P, _P, _I),
    "elem2_sub": (None, _P, _P, _P, _I),
    "elem2_mul": (None, _P, _P, _P, _I),
    "scale":     (None, _P, _P, _I, _D),
    "upd":       (None, _P, _P, _P, _I, _D),
    "relu_mask": (None, _P, _P, _P, _I),
    "sqg":       (None, _P, _P, _P, _I),
    "mm2":       (None, _P, _P, _P, _I, _I, _I),
}

def build_kernels(kerns):
    """输入 tl_kern.parse(kernels.tl) 的 AST，返回 {name: MachineKernel}。"""
    out = {}
    for k in kerns:
        code = _GEN[k.name](k)
        out[k.name] = MachineKernel(code, SIG[k.name])
    return out

def _gen_loop(k):
    kind = k.name
    return _gen_single_loop(kind)

_GEN = {
    "relu": lambda k: _gen_single_loop("relu"),
    "elem2_add": lambda k: _gen_single_loop("add"),
    "elem2_sub": lambda k: _gen_single_loop("sub"),
    "elem2_mul": lambda k: _gen_single_loop("mul"),
    "scale": lambda k: _gen_single_loop("scale"),
    "upd": lambda k: _gen_single_loop("upd"),
    "relu_mask": lambda k: _gen_single_loop("relu_mask"),
    "sqg": lambda k: _gen_single_loop("sqg"),
    "mm2": lambda k: gen_mm2(),
}

def _to_ptr(arr):
    return ctypes.cast(ctypes.byref((ctypes.c_double * len(arr))(*arr)),
                       ctypes.c_void_p)

def _buf(n):
    return (ctypes.c_double * n)()

# =====================================================================
# v0.14 —— 机器码内核全集（对齐 kernels.c 16 个导出内核，逐位一致）
# 累加契约：朴素 s+=（mm2v/mm2_back/scaled_mm/affine2v）；Neumaier 补偿
# 求和（total/colsum/softmax/softmax_grad/scaled_mm_t/affine2 系，复刻
# CPython 3.12+ sum()）；自研 tl_exp（floor 分解 + 16 阶 Taylor Horner +
# 位构造 2^k）。全部由 tl 编译器（本生成器）发射，零 C/零 LLVM。
# =====================================================================
JAE, JP = 0x03, 0x0A

# 常数位模式（IEEE754 双精度）
_DB = {}
for _n, _v in [("INV_LN2", 1.4426950408889634), ("LN2", 0.6931471805599453),
               ("HALF", 0.5), ("ONE", 1.0),
               ("INF", float("inf")), ("NEG_INF", float("-inf")),
               ("SIGN", 0x8000000000000000), ("ABS", 0x7FFFFFFFFFFFFFFF)]:
    _bits = _v if _n in ("SIGN", "ABS") else struct.unpack("<Q", struct.pack("<d", _v))[0]
    _DB["DB_" + _n] = _bits
EXP_C = [4.7794773323873853e-14, 7.6471637318198164e-13, 1.1470745597729725e-11,
         1.6059043836821613e-10, 2.08767569878681e-09, 2.505210838544172e-08,
         2.7557319223985888e-07, 2.7557319223985893e-06, 2.4801587301587302e-05,
         0.00019841269841269841, 0.0013888888888888889, 0.0083333333333333332,
         0.041666666666666664, 0.16666666666666666, 0.5, 1.0]
for _i, _c in enumerate(EXP_C):
    _DB["DB_EXP_C%d" % _i] = struct.unpack("<Q", struct.pack("<d", _c))[0]


def _emit_consts(e):
    for _k in sorted(_DB):
        e.data64(_k, _DB[_k])


def _fin(e):
    e.patch()
    return bytes(e.code)


_neu_seq = [0]


def _neumaier(e, p_reg, n_reg, i_reg):
    """neumaier([p_reg], n_reg) → xmm0；与 kernels.c neumaier 逐位一致。
    占用 xmm0-7、i_reg、rax；不碰 p_reg/n_reg 之外的整数寄存器。
    label 带唯一后缀（_fix20：多次调用时 N0/N_ge/N_next 不得互相覆盖）。"""
    _neu_seq[0] += 1
    sf = "_N%d" % _neu_seq[0]
    N0, Nge, Nnext = sf + "_0", sf + "_ge", sf + "_nx"
    e.pxor_xmm(0, 0)
    e.pxor_xmm(1, 1)
    e.xor_r32_r32(i_reg, i_reg)
    e.movsd_load_xmm_rip(7, "DB_ABS")
    e.label(N0)
    e.movsd_load_xmm(2, p_reg, i_reg, 8)
    e.movsd_xmm_xmm(3, 0)
    e.addsd(0, 2)
    e.movsd_xmm_xmm(4, 3)
    e.andpd_xmm_xmm(4, 7)
    e.movsd_xmm_xmm(5, 2)
    e.andpd_xmm_xmm(5, 7)
    e.ucomisd(4, 5)
    e.jcc(JAE, Nge)
    e.movsd_xmm_xmm(6, 2)
    e.subsd(6, 0)
    e.addsd(6, 3)
    e.addsd(1, 6)
    e.jmp(Nnext)
    e.label(Nge)
    e.movsd_xmm_xmm(6, 3)
    e.subsd(6, 0)
    e.addsd(6, 2)
    e.addsd(1, 6)
    e.label(Nnext)
    e.inc_r64(i_reg)
    e.cmp_r64_r64(i_reg, n_reg)
    e.jl(N0)
    e.addsd(0, 1)


def _tl_exp(e, k_reg=0xB):
    """xmm0 in/out；与 kernels.c tl_exp 逐位一致。
    占用 xmm0-5、rax、rbx、k_reg；常数走 RIP 相对。"""
    e.ucomisd(0, 0)
    e.jcc(JP, "X_done")
    e.movsd_load_xmm_rip(4, "DB_INF")
    e.ucomisd(0, 4)
    e.jcc(JE, "X_done")
    e.movsd_load_xmm_rip(4, "DB_NEG_INF")
    e.ucomisd(0, 4)
    e.jcc(JE, "X_ninf")
    e.movsd_xmm_xmm(3, 0)
    e.movsd_load_xmm_rip(1, "DB_INV_LN2")
    e.mulsd(0, 1)
    e.movsd_load_xmm_rip(1, "DB_HALF")
    e.addsd(0, 1)
    e.roundsd(0, 0, 1)
    e.cvttsd2si_r64(0, 0)
    e.mov_r64_r64(k_reg, 0)
    e.mov_r64_imm(0x0, 1023)
    e.cmp_r64_r64(k_reg, 0)
    e.jg("X_inf")
    e.cvtsi2sd_xmm(1, k_reg)
    e.movsd_load_xmm_rip(2, "DB_LN2")
    e.mulsd(1, 2)
    e.movsd_xmm_xmm(0, 3)
    e.subsd(0, 1)
    e.movsd_load_xmm_rip(2, "DB_EXP_C0")
    for _i in range(1, 16):
        e.mulsd(2, 0)
        e.movsd_load_xmm_rip(1, "DB_EXP_C%d" % _i)
        e.addsd(2, 1)
    e.mulsd(2, 0)
    e.movsd_load_xmm_rip(1, "DB_ONE")
    e.addsd(2, 1)
    e.mov_r64_r64(0, k_reg)
    e.add_r64_imm(0, 1023)
    e.shl_r64_imm(0, 52)
    e.movq_xmm_r64(1, 0)
    e.mulsd(2, 1)
    e.movsd_xmm_xmm(0, 2)
    e.jmp("X_done")
    e.label("X_ninf")
    e.pxor_xmm(0, 0)
    e.jmp("X_done")
    e.label("X_inf")
    e.movsd_load_xmm_rip(0, "DB_INF")
    e.label("X_done")


# ---------------- 批 1：无 neumaier/exp 的简单内核 ----------------
def _gen_sq():
    e = Enc()
    e.push_r64(6); e.push_r64(7); e.push_r64(0xB)
    e.mov_r64_r64(6, R_RCX); e.mov_r64_r64(7, R_R8); e.mov_r64_r64(0xB, R_RDX)
    e.xor_r32_r32(1, 1)
    e.label("L")
    e.movsd_load_xmm(0, 6, 1, 8)
    e.mulsd(0, 0)
    e.movsd_store_xmm(0, 7, 1, 8)
    e.inc_r64(1); e.cmp_r64_r64(1, 0xB); e.jl("L")
    e.pop_r64(0xB); e.pop_r64(7); e.pop_r64(6); e.ret()
    return _fin(e)


def _gen_scg():
    # scg(g, n, cv, out)：g=rcx n=rdx cv=xmm2 out=r9（第 4 整数槽）
    e = Enc()
    e.push_r64(6); e.push_r64(7); e.push_r64(0xB)
    e.mov_r64_r64(6, R_RCX); e.mov_r64_r64(7, R_R9); e.mov_r64_r64(0xB, R_RDX)
    e.xor_r32_r32(1, 1)
    e.label("L")
    e.movsd_load_xmm(0, 6, 1, 8)
    e.divsd(0, X_XMM2)
    e.movsd_store_xmm(0, 7, 1, 8)
    e.inc_r64(1); e.cmp_r64_r64(1, 0xB); e.jl("L")
    e.pop_r64(0xB); e.pop_r64(7); e.pop_r64(6); e.ret()
    return _fin(e)


def _gen_mm2v():
    e = Enc()
    e.push_r64(6); e.push_r64(7); e.push_r64(3); e.push_r64(0xC); e.push_r64(0xD); e.push_r64(0xE)
    e.mov_r64_r64(6, R_RCX); e.mov_r64_r64(7, R_R9)
    e.mov_r64_r64(0xC, R_RDX); e.mov_r64_r64(0xD, R_R8)
    e.mov_r64_m64_rsp(0x3, 88)
    e.xor_r32_r32(1, 1)
    e.label("Lm")
    e.pxor_xmm(0, 0)
    e.xor_r32_r32(2, 2)
    e.label("Lk")
    # a[m*K+k]：rax = m*K + k
    e.mov_r64_r64(0, 1)
    e.imul_r64_r64(0, 0xD)
    e.add_r64_r64(0, 2)
    e.shl_r64_imm(0, 3)
    e.movsd_load_xmm(1, 6, 0, 1)       # a[rax]（[rsi+rax]）
    e.movsd_load_xmm(2, 7, 2, 8)       # b[k]
    e.mulsd(1, 2)
    e.addsd(0, 1)
    e.inc_r64(2); e.cmp_r64_r64(2, 0xD); e.jl("Lk")
    e.mov_r64_r64(0, 1)
    e.shl_r64_imm(0, 3)
    e.movsd_store_xmm(0, 3, 0, 1)
    e.inc_r64(1); e.cmp_r64_r64(1, 0xC); e.jl("Lm")
    e.pop_r64(0xE); e.pop_r64(0xD); e.pop_r64(0xC); e.pop_r64(3); e.pop_r64(7); e.pop_r64(6)
    e.ret()
    return _fin(e)


def _gen_transpose():
    e = Enc()
    e.push_r64(6); e.push_r64(7); e.push_r64(0xC); e.push_r64(0xD); e.push_r64(0xE)
    e.mov_r64_r64(6, R_RCX); e.mov_r64_r64(7, R_R9)
    e.mov_r64_r64(0xC, R_RDX); e.mov_r64_r64(0xD, R_R8)
    e.xor_r32_r32(0xE, 0xE)
    e.label("Lj")
    e.xor_r32_r32(1, 1)
    e.label("Li")
    e.mov_r64_r64(0, 0xE)
    e.imul_r64_r64(0, 0xC)
    e.add_r64_r64(0, 1)
    e.shl_r64_imm(0, 3)
    e.mov_r64_r64(8, 1)
    e.imul_r64_r64(8, 0xD)
    e.add_r64_r64(8, 0xE)
    e.shl_r64_imm(8, 3)
    e.movsd_load_xmm(0, 6, 8, 1)
    e.movsd_store_xmm(0, 7, 0, 1)
    e.inc_r64(1); e.cmp_r64_r64(1, 0xC); e.jl("Li")
    e.inc_r64(0xE); e.cmp_r64_r64(0xE, 0xD); e.jl("Lj")
    e.pop_r64(0xE); e.pop_r64(0xD); e.pop_r64(0xC); e.pop_r64(7); e.pop_r64(6)
    e.ret()
    return _fin(e)


# ---------------- 批 2：neumaier / exp 系 ----------------
def _gen_total():
    e = Enc()
    e.push_r64(6)
    e.mov_r64_r64(6, R_RCX)
    e.mov_r64_r64(1, R_RDX)
    _neumaier(e, 0x6, 1, 2)
    e.pop_r64(6); e.ret()
    _emit_consts(e)
    return _fin(e)


def _gen_colsum():
    """colsum(g, M, N, out)：rcx rdx r8 r9；out[n]=neumaier_m g[m*N+n]"""
    e = Enc()
    e.push_r64(6); e.push_r64(7); e.push_r64(3); e.push_r64(0xC); e.push_r64(0xD); e.push_r64(0xE); e.push_r64(0xF)
    e.mov_r64_r64(0xF, R_RCX)            # r15 = g（neumaier 会占用 rsi）
    e.mov_r64_r64(7, R_R9)
    e.mov_r64_r64(0xC, R_RDX); e.mov_r64_r64(0xD, R_R8)
    e.xor_r32_r32(0xE, 0xE)              # r14 = n
    e.label("Ln")
    e.mov_r64_r64(3, 4)                  # rbx = rsp（保存）
    e.mov_r64_r64(6, 0xF)                # 恢复 rsi = g
    e.mov_r64_r64(0, 0xC)                # rax = M
    e.shl_r64_imm(0, 3)
    e.add_r64_imm(0, 16)
    e.sub_r64_r64(4, 0)                  # rsp -= M*8+16
    e.mov_r64_r64(8, 4)                  # r8 = rsp
    e.add_r64_imm(8, 8)                  # r8 = &buf
    e.xor_r32_r32(1, 1)                  # rcx = m
    e.label("Lc")
    e.mov_r64_r64(0, 1)
    e.imul_r64_r64(0, 0xD)
    e.add_r64_r64(0, 0xE)
    e.shl_r64_imm(0, 3)
    e.movsd_load_xmm(0, 6, 0, 1)         # g[m*N+n]
    e.movsd_store_xmm(0, 8, 1, 8)        # buf[m]
    e.inc_r64(1); e.cmp_r64_r64(1, 0xC); e.jl("Lc")
    e.mov_r64_r64(6, 8)                  # rsi = &buf
    e.mov_r64_r64(1, 0xC)                # rcx = M
    _neumaier(e, 0x6, 1, 2)              # xmm0 = sum
    e.movsd_store_xmm(0, 7, 0xE, 8)      # out[n] = [rdi + n*8]
    e.mov_r64_r64(4, 3)                  # rsp = rbx（恢复）
    e.inc_r64(0xE); e.cmp_r64_r64(0xE, 0xD); e.jl("Ln")
    e.pop_r64(0xF); e.pop_r64(0xE); e.pop_r64(0xD); e.pop_r64(0xC); e.pop_r64(3); e.pop_r64(7); e.pop_r64(6)
    e.ret()
    _emit_consts(e)
    return _fin(e)


def _gen_softmax():
    """softmax(a, rows, cols, out)：rcx rdx r8 r9。
    两遍扫描（免 ex 数组）：①max ②sum=Σexp(row[j]-m)（neumaier）③out=exp/sum。
    exp 确定性函数 → 与 C 的 ex 数组路径逐位一致。"""
    e = Enc()
    e.push_r64(6); e.push_r64(7); e.push_r64(3); e.push_r64(0xC); e.push_r64(0xD); e.push_r64(0xE); e.push_r64(0xF)
    e.mov_r64_r64(6, R_RCX); e.mov_r64_r64(7, R_R9)
    e.mov_r64_r64(0xC, R_R8); e.mov_r64_r64(0xD, R_RDX)
    e.sub_r64_imm(4, 32800)              # 32KB ex 缓冲 + m 槽
    e.xor_r32_r32(0xE, 0xE)              # r14 = r
    e.label("Li")
    # rax = &row
    e.mov_r64_r64(0, 0xE)
    e.imul_r64_r64(0, 0xC)
    e.shl_r64_imm(0, 3)
    e.add_r64_r64(0, 6)
    # max：xmm0 = row[0]
    e.movsd_load_xmm(0, 0, None, 1)
    e.xor_r32_r32(0xF, 0xF)              # r15 = j
    e.label("Lmax")
    e.cmp_r64_r64(0xF, 0xC)
    e.jge("Lmax_done")
    e.movsd_load_xmm(1, 0, 0xF, 8)       # row[j]
    e.ucomisd(1, 0)
    e.jcc(JBE, "Lmax_next")
    e.movsd_xmm_xmm(0, 1)
    e.label("Lmax_next")
    e.inc_r64(0xF)
    e.jmp("Lmax")
    e.label("Lmax_done")
    e.movsd_store_xmm_disp(0, 4, 8)      # m → [rsp+8]
    # exp 缓冲：ex[j] = exp(row[j]-m) → [rsp+16+j*8]
    # 注意：_tl_exp 破坏 rax/rbx/r11，因此每轮重算 &row[j]
    e.xor_r32_r32(0xF, 0xF)
    e.label("Lexp")
    e.cmp_r64_r64(0xF, 0xC)
    e.jge("Lexp_done")
    e.mov_r64_r64(0, 0xE)                # rax = r
    e.imul_r64_r64(0, 0xC)               # *cols
    e.add_r64_r64(0, 0xF)                # +j
    e.shl_r64_imm(0, 3)
    e.add_r64_r64(0, 6)                  # +a → &row[j]
    e.movsd_load_xmm(0, 0, None, 1)      # row[j]
    e.movsd_load_xmm_disp(1, 4, 8)
    e.subsd(0, 1)                        # row[j]-m
    _tl_exp(e)                           # xmm0 = exp（破坏 rax/rbx/r11）
    e.mov_r64_r64(8, 0xF)                # r8 = j
    e.shl_r64_imm(8, 3)
    e.add_r64_imm(8, 16)
    e.add_r64_r64(8, 4)                  # r8 = &[rsp+16+j*8]
    e.movsd_store_xmm(0, 8, None, 1)
    e.inc_r64(0xF)
    e.jmp("Lexp")
    e.label("Lexp_done")
    # sum = neumaier([rsp+16], cols)
    e.mov_r64_r64(3, 6)                  # rbx = a（保存）
    e.mov_r64_r64(6, 4)
    e.add_r64_imm(6, 16)                 # rsi = &buf
    e.mov_r64_r64(1, 0xC)                # rcx = cols
    _neumaier(e, 0x6, 1, 2)              # xmm0 = sum
    e.mov_r64_r64(6, 3)                  # 恢复 a
    # out[r*cols+j] = ex[j]/sum
    e.xor_r32_r32(0xF, 0xF)
    e.label("Ldiv")
    e.cmp_r64_r64(0xF, 0xC)
    e.jge("Ldiv_done")
    e.mov_r64_r64(3, 0xF)
    e.shl_r64_imm(3, 3)
    e.add_r64_imm(3, 16)
    e.add_r64_r64(3, 4)                  # rbx = &ex[j]
    e.movsd_load_xmm(1, 3, None, 1)
    e.divsd(1, 0)                        # ex[j]/sum
    e.mov_r64_r64(0, 0xE)
    e.imul_r64_r64(0, 0xC)
    e.add_r64_r64(0, 0xF)
    e.shl_r64_imm(0, 3)
    e.movsd_store_xmm(1, 7, 0, 1)        # out[rax]
    e.inc_r64(0xF)
    e.jmp("Ldiv")
    e.label("Ldiv_done")
    e.inc_r64(0xE)
    e.cmp_r64_r64(0xE, 0xD)
    e.jl("Li")
    e.add_r64_imm(4, 32800)
    e.pop_r64(0xF); e.pop_r64(0xE); e.pop_r64(0xD); e.pop_r64(0xC); e.pop_r64(3); e.pop_r64(7); e.pop_r64(6)
    e.ret()
    _emit_consts(e)
    return _fin(e)


def _gen_softmax_grad():
    """softmax_grad(s, g, rows, cols, out)：rcx rdx r8 r9 [rsp+40]"""
    e = Enc()
    e.push_r64(6); e.push_r64(7); e.push_r64(3); e.push_r64(0xC); e.push_r64(0xD); e.push_r64(0xE); e.push_r64(0xF)
    e.mov_r64_r64(6, R_RCX); e.mov_r64_r64(7, R_RDX)
    e.mov_r64_r64(0xC, R_R8); e.mov_r64_r64(0xD, R_R9)
    e.mov_r64_m64_rsp(0x3, 96)           # rbx = out（push7 后 [rsp+40+56]）
    e.sub_r64_imm(4, 32784)              # prod 缓冲 [rsp+16..]
    e.xor_r32_r32(0xE, 0xE)              # r14 = r
    e.label("Li")
    # prod[j] = s[r*cols+j]*g[r*cols+j]
    e.xor_r32_r32(0xF, 0xF)
    e.label("Lp")
    e.cmp_r64_r64(0xF, 0xD)
    e.jge("Lp_done")
    e.mov_r64_r64(0, 0xE)
    e.imul_r64_r64(0, 0xD)
    e.add_r64_r64(0, 0xF)
    e.shl_r64_imm(0, 3)
    e.movsd_load_xmm(0, 6, 0, 1)         # s[...]
    e.movsd_load_xmm(1, 7, 0, 1)         # g[...]
    e.mulsd(0, 1)
    e.mov_r64_r64(8, 0xF)
    e.shl_r64_imm(8, 3)
    e.add_r64_imm(8, 16)
    e.add_r64_r64(8, 4)
    e.movsd_store_xmm(0, 8, None, 1)
    e.inc_r64(0xF)
    e.jmp("Lp")
    e.label("Lp_done")
    # dot = neumaier(buf, cols)
    e.mov_r64_r64(8, 6)                  # r8 = s（保存；rbx=out 不可覆盖）
    e.mov_r64_r64(6, 4)
    e.add_r64_imm(6, 16)
    e.mov_r64_r64(1, 0xD)
    _neumaier(e, 0x6, 1, 2)              # xmm0 = dot
    e.mov_r64_r64(6, 8)                  # 恢复 s
    # out[j] = s*(g-dot)
    e.xor_r32_r32(0xF, 0xF)
    e.label("Lg")
    e.cmp_r64_r64(0xF, 0xD)
    e.jge("Lg_done")
    e.mov_r64_r64(0, 0xE)
    e.imul_r64_r64(0, 0xD)
    e.add_r64_r64(0, 0xF)
    e.shl_r64_imm(0, 3)
    e.movsd_load_xmm(1, 6, 0, 1)
    e.movsd_load_xmm(2, 7, 0, 1)
    e.subsd(2, 0)                        # g - dot
    e.mulsd(1, 2)
    e.movsd_store_xmm(1, 3, 0, 1)        # out[rax]
    e.inc_r64(0xF)
    e.jmp("Lg")
    e.label("Lg_done")
    e.inc_r64(0xE)
    e.cmp_r64_r64(0xE, 0xC)
    e.jl("Li")
    e.add_r64_imm(4, 32784)
    e.pop_r64(0xF); e.pop_r64(0xE); e.pop_r64(0xD); e.pop_r64(0xC); e.pop_r64(3); e.pop_r64(7); e.pop_r64(6)
    e.ret()
    _emit_consts(e)
    return _fin(e)


# ---------------- 批 3：mm2_back / scaled_mm 系 ----------------
def _gen_mm2_back():
    """mm2_back(g, M, N, b, K, a, ga, gb)：rcx rdx r8 r9 [rsp+40..]
    ga[M,K] = g@B^T（朴素）；gb[K,N] = A^T@g（朴素）
    寄存器：rsi=g rdi=b rbx=a r12=M r13=N r14=K r15=ga/gb"""
    e = Enc()
    e.push_r64(6); e.push_r64(7); e.push_r64(3); e.push_r64(0xC); e.push_r64(0xD); e.push_r64(0xE); e.push_r64(0xF)
    e.mov_r64_r64(6, R_RCX); e.mov_r64_r64(0xC, R_RDX)
    e.mov_r64_r64(0xD, R_R8); e.mov_r64_r64(7, R_R9)
    e.mov_r64_m64_rsp(0xE, 96)       # r14 = K
    e.mov_r64_m64_rsp(3, 104)        # rbx = a
    e.mov_r64_m64_rsp(0xF, 112)      # r15 = ga
    e.xor_r32_r32(0, 0)
    e.label("Lm")
    e.xor_r32_r32(1, 1)
    e.label("Lk")
    e.pxor_xmm(0, 0)
    e.xor_r32_r32(2, 2)
    e.label("Ln")
    e.mov_r64_r64(8, 0)
    e.imul_r64_r64(8, 0xD)
    e.add_r64_r64(8, 2)
    e.shl_r64_imm(8, 3)
    e.movsd_load_xmm(1, 6, 8, 1)     # g[m*N+n]
    e.mov_r64_r64(8, 1)
    e.imul_r64_r64(8, 0xD)
    e.add_r64_r64(8, 2)
    e.shl_r64_imm(8, 3)
    e.movsd_load_xmm(2, 7, 8, 1)     # b[k*N+n]
    e.mulsd(1, 2); e.addsd(0, 1)
    e.inc_r64(2); e.cmp_r64_r64(2, 0xD); e.jl("Ln")
    e.mov_r64_r64(8, 0)
    e.imul_r64_r64(8, 0xE)
    e.add_r64_r64(8, 1)
    e.shl_r64_imm(8, 3)
    e.movsd_store_xmm(0, 0xF, 8, 1)
    e.inc_r64(1); e.cmp_r64_r64(1, 0xE); e.jl("Lk")
    e.inc_r64(0); e.cmp_r64_r64(0, 0xC); e.jl("Lm")
    # gb[K,N] = Σ_m a[m*K+k]*g[m*N+n]
    e.mov_r64_m64_rsp(0xF, 120)
    e.xor_r32_r32(1, 1)
    e.label("Lk2")
    e.xor_r32_r32(2, 2)
    e.label("Ln2")
    e.pxor_xmm(0, 0)
    e.xor_r32_r32(0, 0)
    e.label("Lm2")
    e.mov_r64_r64(8, 0)
    e.imul_r64_r64(8, 0xE)
    e.add_r64_r64(8, 1)
    e.shl_r64_imm(8, 3)
    e.movsd_load_xmm(1, 3, 8, 1)     # a[m*K+k]
    e.mov_r64_r64(8, 0)
    e.imul_r64_r64(8, 0xD)
    e.add_r64_r64(8, 2)
    e.shl_r64_imm(8, 3)
    e.movsd_load_xmm(2, 6, 8, 1)     # g[m*N+n]
    e.mulsd(1, 2); e.addsd(0, 1)
    e.inc_r64(0); e.cmp_r64_r64(0, 0xC); e.jl("Lm2")
    e.mov_r64_r64(8, 1)
    e.imul_r64_r64(8, 0xD)
    e.add_r64_r64(8, 2)
    e.shl_r64_imm(8, 3)
    e.movsd_store_xmm(0, 0xF, 8, 1)
    e.inc_r64(2); e.cmp_r64_r64(2, 0xD); e.jl("Ln2")
    e.inc_r64(1); e.cmp_r64_r64(1, 0xE); e.jl("Lk2")
    e.pop_r64(0xF); e.pop_r64(0xE); e.pop_r64(0xD); e.pop_r64(0xC); e.pop_r64(3); e.pop_r64(7); e.pop_r64(6)
    e.ret()
    return _fin(e)


def _gen_scaled_mm():
    """scaled_mm(a, M, K, b, N, cv, out)：rcx rdx r8 r9 [rsp+40]=N [rsp+48]=cv [rsp+56]=out
    out[m*N+n] = (Σ_k a[m*K+k]*b[k*N+n])/cv（朴素）"""
    e = Enc()
    e.push_r64(6); e.push_r64(7); e.push_r64(3); e.push_r64(0xC); e.push_r64(0xD); e.push_r64(0xE); e.push_r64(0xF)
    e.mov_r64_r64(6, R_RCX); e.mov_r64_r64(0xC, R_RDX)
    e.mov_r64_r64(0xD, R_R8); e.mov_r64_r64(7, R_R9)
    e.mov_r64_m64_rsp(0xE, 96)
    e.movsd_load_xmm_disp(2, 4, 104)
    e.mov_r64_m64_rsp(0xF, 112)
    e.xor_r32_r32(0, 0)
    e.label("Lm")
    e.xor_r32_r32(1, 1)
    e.label("Ln")
    e.pxor_xmm(0, 0)
    e.xor_r32_r32(2, 2)
    e.label("Lk")
    e.mov_r64_r64(8, 0)
    e.imul_r64_r64(8, 0xD)
    e.add_r64_r64(8, 2)
    e.shl_r64_imm(8, 3)
    e.movsd_load_xmm(1, 6, 8, 1)
    e.mov_r64_r64(8, 2)
    e.imul_r64_r64(8, 0xE)
    e.add_r64_r64(8, 1)
    e.shl_r64_imm(8, 3)
    e.movsd_load_xmm(3, 7, 8, 1)
    e.mulsd(1, 3); e.addsd(0, 1)
    e.inc_r64(2); e.cmp_r64_r64(2, 0xD); e.jl("Lk")
    e.divsd(0, 2)
    e.mov_r64_r64(8, 0)
    e.imul_r64_r64(8, 0xE)
    e.add_r64_r64(8, 1)
    e.shl_r64_imm(8, 3)
    e.movsd_store_xmm(0, 0xF, 8, 1)
    e.inc_r64(1); e.cmp_r64_r64(1, 0xE); e.jl("Ln")
    e.inc_r64(0); e.cmp_r64_r64(0, 0xC); e.jl("Lm")
    e.pop_r64(0xF); e.pop_r64(0xE); e.pop_r64(0xD); e.pop_r64(0xC); e.pop_r64(3); e.pop_r64(7); e.pop_r64(6)
    e.ret()
    return _fin(e)


def _gen_scaled_mm_t():
    """scaled_mm_t(a, M, K, b, N, cv, out)：同 scaled_mm 参数
    out[m*N+n] = neumaier_k(a[m*K+k]*b[n*K+k])/cv
    寄存器：r15=a rdi=b r12=M r13=K r14=N rbx=rsp；out 存 xmm8；栈 [rsp]=cv [rsp+8..]=prod"""
    e = Enc()
    e.push_r64(6); e.push_r64(7); e.push_r64(3); e.push_r64(0xC); e.push_r64(0xD); e.push_r64(0xE); e.push_r64(0xF)
    e.mov_r64_r64(0xF, R_RCX)         # r15 = a
    e.mov_r64_r64(0xC, R_RDX)
    e.mov_r64_r64(0xD, R_R8)
    e.mov_r64_r64(7, R_R9)            # rdi = b
    e.mov_r64_m64_rsp(0xE, 96)
    e.movsd_load_xmm_disp(2, 4, 104)  # xmm2 = cv
    e.mov_r64_m64_rsp(1, 112)         # rcx = out
    e.movq_xmm_r64(8, 1)              # xmm8 = out（neumaier 不碰 xmm8+）
    e.mov_r64_r64(3, 4)               # rbx = rsp
    e.mov_r64_r64(0, 0xD)
    e.shl_r64_imm(0, 3)
    e.add_r64_imm(0, 16)
    e.sub_r64_r64(4, 0)               # rsp -= K*8+16
    e.movsd_store_xmm_disp(2, 4, 0)   # [rsp] = cv
    e.xor_r32_r32(8, 8)               # r8 = m（_fix17：勿 mov r8,rax，rax 非 0）
    e.label("Lm")
    e.xor_r32_r32(9, 9)               # r9 = n
    e.label("Ln")
    e.xor_r32_r32(2, 2)               # rdx = k
    e.label("Lk")
    e.mov_r64_r64(0, 8)
    e.imul_r64_r64(0, 0xD)
    e.add_r64_r64(0, 2)
    e.shl_r64_imm(0, 3)
    e.movsd_load_xmm(1, 0xF, 0, 1)
    e.mov_r64_r64(0, 9)
    e.imul_r64_r64(0, 0xD)
    e.add_r64_r64(0, 2)
    e.shl_r64_imm(0, 3)
    e.movsd_load_xmm(2, 7, 0, 1)
    e.mulsd(1, 2)
    e.mov_r64_r64(0, 2)
    e.shl_r64_imm(0, 3)
    e.add_r64_imm(0, 8)
    e.add_r64_r64(0, 4)
    e.movsd_store_xmm(1, 0, None, 1)
    e.inc_r64(2); e.cmp_r64_r64(2, 0xD); e.jl("Lk")
    e.mov_r64_r64(6, 4)
    e.add_r64_imm(6, 8)
    e.mov_r64_r64(1, 0xD)
    _neumaier(e, 0x6, 1, 2)
    e.movsd_load_xmm_disp(3, 4, 0)
    e.divsd(0, 3)
    e.mov_r64_r64(0, 8)
    e.imul_r64_r64(0, 0xE)
    e.add_r64_r64(0, 9)
    e.shl_r64_imm(0, 3)
    e.movq_r64_xmm(1, 8)              # rcx = out
    e.movsd_store_xmm(0, 1, 0, 1)
    e.inc_r64(9); e.cmp_r64_r64(9, 0xE); e.jl("Ln")
    e.inc_r64(8); e.cmp_r64_r64(8, 0xC); e.jl("Lm")
    e.mov_r64_r64(4, 3)
    e.pop_r64(0xF); e.pop_r64(0xE); e.pop_r64(0xD); e.pop_r64(0xC); e.pop_r64(3); e.pop_r64(7); e.pop_r64(6)
    e.ret()
    _emit_consts(e)
    return _fin(e)


def _gen_scaled_mm_back():
    """scaled_mm_back(a, M, K, b, N, g, cv, ga, gb) → double
    rcx=a rdx=M r8=K r9=b [rsp+40]=N [rsp+48]=g [rsp+56]=cv [rsp+64]=ga [rsp+72]=gb
    ga=Σ_n (g/cv)*b（朴素）；gb=Σ_m a*(g/cv)（朴素）；dc=-neumaier(g*p)/(cv*cv)
    寄存器：rsi=g rdi=b rbx=a r12=M r13=K r14=N r15=ga/gb；栈 [rsp]=cv [rsp+8..]=prod_all"""
    e = Enc()
    e.push_r64(6); e.push_r64(7); e.push_r64(3); e.push_r64(0xC); e.push_r64(0xD); e.push_r64(0xE); e.push_r64(0xF)
    e.mov_r64_r64(3, R_RCX)           # rbx = a
    e.mov_r64_r64(0xC, R_RDX)
    e.mov_r64_r64(0xD, R_R8)
    e.mov_r64_r64(7, R_R9)            # rdi = b
    e.mov_r64_m64_rsp(0xE, 96)
    e.mov_r64_m64_rsp(6, 104)         # rsi = g
    e.movsd_load_xmm_disp(3, 4, 112)  # xmm3 = cv
    e.mov_r64_m64_rsp(0xF, 120)       # r15 = ga
    e.movsd_store_xmm_disp(3, 4, 0)   # [rsp] = cv（push 后原栈顶可用）
    e.xor_r32_r32(0, 0)
    e.label("Lm")
    e.xor_r32_r32(1, 1)
    e.label("Lk")
    e.pxor_xmm(0, 0)
    e.xor_r32_r32(2, 2)
    e.label("Ln")
    e.mov_r64_r64(8, 0)
    e.imul_r64_r64(8, 0xE)
    e.add_r64_r64(8, 2)
    e.shl_r64_imm(8, 3)
    e.movsd_load_xmm(1, 6, 8, 1)
    e.divsd(1, 3)
    e.mov_r64_r64(8, 1)
    e.imul_r64_r64(8, 0xE)
    e.add_r64_r64(8, 2)
    e.shl_r64_imm(8, 3)
    e.movsd_load_xmm(2, 7, 8, 1)
    e.mulsd(1, 2); e.addsd(0, 1)
    e.inc_r64(2); e.cmp_r64_r64(2, 0xE); e.jl("Ln")
    e.mov_r64_r64(8, 0)
    e.imul_r64_r64(8, 0xD)
    e.add_r64_r64(8, 1)
    e.shl_r64_imm(8, 3)
    e.movsd_store_xmm(0, 0xF, 8, 1)
    e.inc_r64(1); e.cmp_r64_r64(1, 0xD); e.jl("Lk")
    e.inc_r64(0); e.cmp_r64_r64(0, 0xC); e.jl("Lm")
    # gb[k*N+n] = Σ_m a[m*K+k]*(g[m*N+n]/cv)
    e.mov_r64_m64_rsp(0xF, 128)
    e.xor_r32_r32(1, 1)
    e.label("Lk2")
    e.xor_r32_r32(2, 2)
    e.label("Ln2")
    e.pxor_xmm(0, 0)
    e.xor_r32_r32(0, 0)
    e.label("Lm2")
    e.mov_r64_r64(8, 0)
    e.imul_r64_r64(8, 0xD)
    e.add_r64_r64(8, 1)
    e.shl_r64_imm(8, 3)
    e.movsd_load_xmm(1, 3, 8, 1)
    e.mov_r64_r64(8, 0)
    e.imul_r64_r64(8, 0xE)
    e.add_r64_r64(8, 2)
    e.shl_r64_imm(8, 3)
    e.movsd_load_xmm(2, 6, 8, 1)
    e.divsd(2, 3)
    e.mulsd(1, 2); e.addsd(0, 1)
    e.inc_r64(0); e.cmp_r64_r64(0, 0xC); e.jl("Lm2")
    e.mov_r64_r64(8, 1)
    e.imul_r64_r64(8, 0xE)
    e.add_r64_r64(8, 2)
    e.shl_r64_imm(8, 3)
    e.movsd_store_xmm(0, 0xF, 8, 1)
    e.inc_r64(2); e.cmp_r64_r64(2, 0xE); e.jl("Ln2")
    e.inc_r64(1); e.cmp_r64_r64(1, 0xD); e.jl("Lk2")
    # dc：prod_all[idx] = g[m*N+n]*(Σ_k a[m*K+k]*b[k*N+n])，neumaier → /(cv*cv)，取负
    e.mov_r64_r64(0, 0xC)
    e.imul_r64_r64(0, 0xE)
    e.shl_r64_imm(0, 3)
    e.add_r64_imm(0, 16)
    e.sub_r64_r64(4, 0)               # rsp -= M*N*8+16（rbx=a 不动）
    e.movsd_store_xmm_disp(3, 4, 0)   # [新rsp] = cv
    e.xor_r32_r32(1, 1)               # rcx = idx
    e.xor_r32_r32(0, 0)               # rax = m
    e.label("Ldm")
    e.xor_r32_r32(9, 9)               # r9 = n
    e.label("Ldn")
    e.pxor_xmm(0, 0)
    e.xor_r32_r32(2, 2)               # rdx = k
    e.label("Ldk")
    e.mov_r64_r64(8, 0)
    e.imul_r64_r64(8, 0xD)
    e.add_r64_r64(8, 2)
    e.shl_r64_imm(8, 3)
    e.movsd_load_xmm(1, 3, 8, 1)      # a[m*K+k]
    e.mov_r64_r64(8, 2)
    e.imul_r64_r64(8, 0xE)
    e.add_r64_r64(8, 9)
    e.shl_r64_imm(8, 3)
    e.movsd_load_xmm(2, 7, 8, 1)      # b[k*N+n]
    e.mulsd(1, 2); e.addsd(0, 1)
    e.inc_r64(2); e.cmp_r64_r64(2, 0xD); e.jl("Ldk")
    e.mov_r64_r64(8, 0)
    e.imul_r64_r64(8, 0xE)
    e.add_r64_r64(8, 9)
    e.shl_r64_imm(8, 3)
    e.movsd_load_xmm(1, 6, 8, 1)      # g[m*N+n]
    e.mulsd(1, 0)
    e.mov_r64_r64(8, 1)
    e.shl_r64_imm(8, 3)
    e.add_r64_imm(8, 8)
    e.add_r64_r64(8, 4)
    e.movsd_store_xmm(1, 8, None, 1)
    e.inc_r64(1)
    e.inc_r64(9); e.cmp_r64_r64(9, 0xE); e.jl("Ldn")
    e.inc_r64(0); e.cmp_r64_r64(0, 0xC); e.jl("Ldm")
    e.mov_r64_r64(6, 4)
    e.add_r64_imm(6, 8)
    e.mov_r64_r64(1, 0xC)
    e.imul_r64_r64(1, 0xE)
    _neumaier(e, 0x6, 1, 2)
    e.movsd_load_xmm_disp(3, 4, 0)
    e.mulsd(3, 3)
    e.divsd(0, 3)
    e.movsd_load_xmm_rip(1, "DB_SIGN")
    e.pxor_xmm(0, 1)
    e.mov_r64_r64(0, 0xC)
    e.imul_r64_r64(0, 0xE)
    e.shl_r64_imm(0, 3)
    e.add_r64_imm(0, 16)
    e.add_r64_r64(4, 0)               # rsp 恢复
    e.pop_r64(0xF); e.pop_r64(0xE); e.pop_r64(0xD); e.pop_r64(0xC); e.pop_r64(3); e.pop_r64(7); e.pop_r64(6)
    e.ret()
    _emit_consts(e)
    return _fin(e)


def _gen_scaled_mm_t_back():
    """scaled_mm_t_back(a, M, K, b, N, g, cv, ga, gb) → double
    ga[m*K+k] = neumaier_n(g[m*N+n]*b[n*K+k])/cv
    gb[n*K+k] = neumaier_m(g[m*N+n]*a[m*K+k])/cv
    dc = -(Σ_neumaier(g[m*N+n]*p))/(cv*cv)，p 朴素内积
    寄存器：r15=a rdi=b r12=M r13=K r14=N rbx=rsp；g 存 xmm8、ga 存 xmm9、gb 存 xmm10；
    栈 [rsp]=cv [rsp+8..] 缓冲"""
    e = Enc()
    e.push_r64(6); e.push_r64(7); e.push_r64(3); e.push_r64(0xC); e.push_r64(0xD); e.push_r64(0xE); e.push_r64(0xF)
    e.mov_r64_r64(0xF, R_RCX)         # r15 = a
    e.mov_r64_r64(0xC, R_RDX)
    e.mov_r64_r64(0xD, R_R8)
    e.mov_r64_r64(7, R_R9)            # rdi = b
    e.mov_r64_m64_rsp(0xE, 96)
    e.mov_r64_m64_rsp(6, 104)         # rsi = g
    e.movq_xmm_r64(8, 6)              # xmm8 = g
    e.movsd_load_xmm_disp(3, 4, 112)  # xmm3 = cv
    e.mov_r64_m64_rsp(1, 120)         # rcx = ga
    e.movq_xmm_r64(9, 1)              # xmm9 = ga
    e.mov_r64_m64_rsp(1, 128)         # rcx = gb
    e.movq_xmm_r64(10, 1)             # xmm10 = gb
    e.mov_r64_r64(3, 4)               # rbx = rsp
    e.mov_r64_r64(0, 0xC)
    e.imul_r64_r64(0, 0xE)
    e.shl_r64_imm(0, 3)
    e.add_r64_imm(0, 16)
    e.sub_r64_r64(4, 0)               # rsp -= M*N*8+16（缓冲够 N 与 M）
    e.movsd_store_xmm_disp(3, 4, 0)   # [rsp] = cv
    # ga[m*K+k] = neumaier_n(g[m*N+n]*b[n*K+k])/cv
    e.xor_r32_r32(8, 8)               # r8 = m（_fix17b）
    e.label("Lm")
    e.xor_r32_r32(9, 9)               # r9 = k
    e.label("Lk")
    e.movq_r64_xmm(6, 8)              # rsi = g
    e.xor_r32_r32(2, 2)               # rdx = n
    e.label("Ln")
    e.mov_r64_r64(0, 8)
    e.imul_r64_r64(0, 0xE)
    e.add_r64_r64(0, 2)
    e.shl_r64_imm(0, 3)
    e.movsd_load_xmm(1, 6, 0, 1)      # g[m*N+n]
    e.mov_r64_r64(0, 2)
    e.imul_r64_r64(0, 0xD)
    e.add_r64_r64(0, 9)
    e.shl_r64_imm(0, 3)
    e.movsd_load_xmm(2, 7, 0, 1)      # b[n*K+k]（_fix18：n 在前 k 在后）
    e.mulsd(1, 2)
    e.mov_r64_r64(0, 2)
    e.shl_r64_imm(0, 3)
    e.add_r64_imm(0, 8)
    e.add_r64_r64(0, 4)
    e.movsd_store_xmm(1, 0, None, 1)  # prod[n]
    e.inc_r64(2); e.cmp_r64_r64(2, 0xE); e.jl("Ln")
    e.mov_r64_r64(6, 4)
    e.add_r64_imm(6, 8)
    e.mov_r64_r64(1, 0xE)
    _neumaier(e, 0x6, 1, 2)
    e.movsd_load_xmm_disp(3, 4, 0)
    e.divsd(0, 3)
    e.mov_r64_r64(0, 8)
    e.imul_r64_r64(0, 0xD)
    e.add_r64_r64(0, 9)
    e.shl_r64_imm(0, 3)
    e.movq_r64_xmm(1, 9)              # rcx = ga
    e.movsd_store_xmm(0, 1, 0, 1)
    e.inc_r64(9); e.cmp_r64_r64(9, 0xD); e.jl("Lk")
    e.inc_r64(8); e.cmp_r64_r64(8, 0xC); e.jl("Lm")
    # gb[n*K+k] = neumaier_m(g[m*N+n]*a[m*K+k])/cv
    e.xor_r32_r32(9, 9)               # r9 = n
    e.label("Ln2")
    e.xor_r32_r32(2, 2)               # rdx = k
    e.label("Lk2")
    e.movq_r64_xmm(6, 8)              # rsi = g
    e.xor_r32_r32(8, 8)               # r8 = m
    e.label("Lm2")
    e.mov_r64_r64(0, 8)
    e.imul_r64_r64(0, 0xE)
    e.add_r64_r64(0, 9)
    e.shl_r64_imm(0, 3)
    e.movsd_load_xmm(1, 6, 0, 1)      # g[m*N+n]
    e.mov_r64_r64(0, 8)
    e.imul_r64_r64(0, 0xD)
    e.add_r64_r64(0, 2)
    e.shl_r64_imm(0, 3)
    e.movsd_load_xmm(2, 0xF, 0, 1)    # a[m*K+k]
    e.mulsd(1, 2)
    e.mov_r64_r64(0, 8)
    e.shl_r64_imm(0, 3)
    e.add_r64_imm(0, 8)
    e.add_r64_r64(0, 4)
    e.movsd_store_xmm(1, 0, None, 1)  # prod[m]
    e.inc_r64(8); e.cmp_r64_r64(8, 0xC); e.jl("Lm2")
    e.mov_r64_r64(6, 4)
    e.add_r64_imm(6, 8)
    e.mov_r64_r64(1, 0xC)
    _neumaier(e, 0x6, 1, 8)           # _fix19：i_reg=r8（rdx 是 k 循环变量）
    e.movsd_load_xmm_disp(3, 4, 0)
    e.divsd(0, 3)
    e.mov_r64_r64(0, 9)
    e.imul_r64_r64(0, 0xD)
    e.add_r64_r64(0, 2)
    e.shl_r64_imm(0, 3)
    e.movq_r64_xmm(1, 10)             # rcx = gb
    e.movsd_store_xmm(0, 1, 0, 1)
    e.inc_r64(2); e.cmp_r64_r64(2, 0xD); e.jl("Lk2")
    e.inc_r64(9); e.cmp_r64_r64(9, 0xE); e.jl("Ln2")
    # dc：手工 neumaier 对 g[m*N+n]*p（p 朴素内积）
    e.movq_r64_xmm(6, 8)              # rsi = g
    e.pxor_xmm(0, 0); e.pxor_xmm(1, 1)
    e.xor_r32_r32(8, 8)               # r8 = m
    e.label("Ldm")
    e.xor_r32_r32(9, 9)               # r9 = n
    e.label("Ldn")
    e.pxor_xmm(2, 2)
    e.xor_r32_r32(2, 2)               # rdx = k
    e.label("Ldk")
    e.mov_r64_r64(0, 8)
    e.imul_r64_r64(0, 0xD)
    e.add_r64_r64(0, 2)
    e.shl_r64_imm(0, 3)
    e.movsd_load_xmm(3, 0xF, 0, 1)    # a[m*K+k]
    e.mov_r64_r64(0, 9)
    e.imul_r64_r64(0, 0xD)
    e.add_r64_r64(0, 2)
    e.shl_r64_imm(0, 3)
    e.movsd_load_xmm(4, 7, 0, 1)      # b[n*K+k]
    e.mulsd(3, 4)
    e.addsd(2, 3)
    e.inc_r64(2); e.cmp_r64_r64(2, 0xD); e.jl("Ldk")
    e.mov_r64_r64(0, 8)
    e.imul_r64_r64(0, 0xE)
    e.add_r64_r64(0, 9)
    e.shl_r64_imm(0, 3)
    e.movsd_load_xmm(3, 6, 0, 1)      # g[m*N+n]
    e.mulsd(3, 2)
    e.movsd_xmm_xmm(4, 0)             # xmm4 = s 旧
    e.addsd(0, 3)                     # t = s + g*p
    e.movsd_xmm_xmm(5, 4)
    e.movsd_load_xmm_rip(7, "DB_ABS")
    e.andpd_xmm_xmm(5, 7)
    e.movsd_xmm_xmm(6, 3)
    e.andpd_xmm_xmm(6, 7)
    e.ucomisd(5, 6)
    e.jcc(JAE, "Dge")
    e.movsd_xmm_xmm(5, 3)
    e.subsd(5, 0)
    e.addsd(5, 4)
    e.addsd(1, 5)
    e.jmp("Dnext")
    e.label("Dge")
    e.movsd_xmm_xmm(5, 4)
    e.subsd(5, 0)
    e.addsd(5, 3)
    e.addsd(1, 5)
    e.label("Dnext")
    e.inc_r64(9); e.cmp_r64_r64(9, 0xE); e.jl("Ldn")
    e.inc_r64(8); e.cmp_r64_r64(8, 0xC); e.jl("Ldm")
    e.addsd(0, 1)
    e.movsd_load_xmm_disp(3, 4, 0)
    e.mulsd(3, 3)
    e.divsd(0, 3)
    e.movsd_load_xmm_rip(1, "DB_SIGN")
    e.pxor_xmm(0, 1)
    e.mov_r64_r64(4, 3)
    e.pop_r64(0xF); e.pop_r64(0xE); e.pop_r64(0xD); e.pop_r64(0xC); e.pop_r64(3); e.pop_r64(7); e.pop_r64(6)
    e.ret()
    _emit_consts(e)
    return _fin(e)


# ---------------- 批 4：affine 系 ----------------
def _gen_affine2():
    """affine2(a, M, K, b, N, bias, biasn, relu_flag, out)：rcx rdx r8 r9 [rsp+40..]
    out[m*N+n] = relu(neumaier(a[mK+k]*b[kN+n]) + bias)
    寄存器：r15=a rdi=b r12=M r13=K r14=N r10=biasn r11=relu rbx=rsp
    xmm8=bias xmm9=out；栈 [rsp+8..]=prod"""
    e = Enc()
    e.push_r64(6); e.push_r64(7); e.push_r64(3); e.push_r64(0xC); e.push_r64(0xD); e.push_r64(0xE); e.push_r64(0xF)
    e.mov_r64_r64(0xF, R_RCX)
    e.mov_r64_r64(0xC, R_RDX)
    e.mov_r64_r64(0xD, R_R8)
    e.mov_r64_r64(7, R_R9)
    e.mov_r64_m64_rsp(0xE, 96)        # r14 = N
    e.mov_r64_m64_rsp(1, 104)         # rcx = bias
    e.movq_xmm_r64(8, 1)              # xmm8 = bias
    e.mov_r64_m64_rsp(10, 112)        # r10 = biasn
    e.mov_r64_m64_rsp(11, 120)        # r11 = relu_flag
    e.mov_r64_m64_rsp(1, 128)         # rcx = out
    e.movq_xmm_r64(9, 1)              # xmm9 = out
    e.mov_r64_r64(3, 4)               # rbx = rsp
    e.mov_r64_r64(0, 0xD)
    e.shl_r64_imm(0, 3)
    e.add_r64_imm(0, 16)
    e.sub_r64_r64(4, 0)               # rsp -= K*8+16
    e.xor_r32_r32(8, 8)               # r8 = m
    e.label("Lm")
    e.xor_r32_r32(9, 9)               # r9 = n
    e.label("Ln")
    e.xor_r32_r32(2, 2)               # rdx = k
    e.label("Lk")
    e.mov_r64_r64(0, 8)
    e.imul_r64_r64(0, 0xD)
    e.add_r64_r64(0, 2)
    e.shl_r64_imm(0, 3)
    e.movsd_load_xmm(1, 0xF, 0, 1)    # a[m*K+k]
    e.mov_r64_r64(0, 2)
    e.imul_r64_r64(0, 0xE)
    e.add_r64_r64(0, 9)
    e.shl_r64_imm(0, 3)
    e.movsd_load_xmm(2, 7, 0, 1)      # b[k*N+n]
    e.mulsd(1, 2)
    e.mov_r64_r64(0, 2)
    e.shl_r64_imm(0, 3)
    e.add_r64_imm(0, 8)
    e.add_r64_r64(0, 4)
    e.movsd_store_xmm(1, 0, None, 1)  # prod[k]
    e.inc_r64(2); e.cmp_r64_r64(2, 0xD); e.jl("Lk")
    e.mov_r64_r64(6, 4)
    e.add_r64_imm(6, 8)
    e.mov_r64_r64(1, 0xD)
    _neumaier(e, 0x6, 1, 2)           # xmm0 = neumaier(prod, K)
    e.movq_r64_xmm(6, 8)              # rsi = bias
    e.cmp_r64_imm(10, 0)
    e.jle("B0")
    e.mov_r64_r64(0, 9)
    e.shl_r64_imm(0, 3)
    e.movsd_load_xmm(2, 6, 0, 1)      # bias[n]
    e.jmp("Bd")
    e.label("B0")
    e.xor_r32_r32(0, 0)               # _fix21：rax 必须为 0（idx 是寄存器）
    e.movsd_load_xmm(2, 6, 0, 1)      # bias[0]
    e.label("Bd")
    e.addsd(0, 2)
    e.cmp_r64_imm(11, 0)
    e.je("Nr")
    e.pxor_xmm(1, 1)
    e.ucomisd(0, 1)
    e.ja("Nr")                        # _fix25：z>0 保留
    e.pxor_xmm(0, 0)                  # z<=0 → 0
    e.label("Nr")
    e.movq_r64_xmm(1, 9)              # rcx = out
    e.mov_r64_r64(0, 8)
    e.imul_r64_r64(0, 0xE)
    e.add_r64_r64(0, 9)
    e.shl_r64_imm(0, 3)
    e.movsd_store_xmm(0, 1, 0, 1)
    e.inc_r64(9); e.cmp_r64_r64(9, 0xE); e.jl("Ln")
    e.inc_r64(8); e.cmp_r64_r64(8, 0xC); e.jl("Lm")
    e.mov_r64_r64(4, 3)
    e.pop_r64(0xF); e.pop_r64(0xE); e.pop_r64(0xD); e.pop_r64(0xC); e.pop_r64(3); e.pop_r64(7); e.pop_r64(6)
    e.ret()
    _emit_consts(e)
    return _fin(e)


def _gen_affine2v():
    """affine2v(a, M, K, b, bias, biasn, relu_flag, out)：rcx rdx r8 r9 [rsp+40..]
    out[m] = relu(朴素Σ a[mK+k]*b[k] + bias)
    寄存器：r15=a rdi=b r12=M r13=K r10=biasn r11=relu；xmm8=bias xmm9=out"""
    e = Enc()
    e.push_r64(6); e.push_r64(7); e.push_r64(3); e.push_r64(0xC); e.push_r64(0xD); e.push_r64(0xE); e.push_r64(0xF)
    e.mov_r64_r64(0xF, R_RCX)
    e.mov_r64_r64(0xC, R_RDX)
    e.mov_r64_r64(0xD, R_R8)
    e.mov_r64_r64(7, R_R9)
    e.mov_r64_m64_rsp(1, 96)          # rcx = bias
    e.movq_xmm_r64(8, 1)
    e.mov_r64_m64_rsp(10, 104)        # r10 = biasn
    e.mov_r64_m64_rsp(11, 112)        # r11 = relu_flag
    e.mov_r64_m64_rsp(1, 120)         # rcx = out
    e.movq_xmm_r64(9, 1)
    e.xor_r32_r32(8, 8)               # r8 = m
    e.label("Lm")
    e.pxor_xmm(0, 0)
    e.xor_r32_r32(2, 2)               # rdx = k
    e.label("Lk")
    e.mov_r64_r64(0, 8)
    e.imul_r64_r64(0, 0xD)
    e.add_r64_r64(0, 2)
    e.shl_r64_imm(0, 3)
    e.movsd_load_xmm(1, 0xF, 0, 1)    # a[m*K+k]
    e.mov_r64_r64(0, 2)
    e.shl_r64_imm(0, 3)
    e.movsd_load_xmm(2, 7, 0, 1)      # b[k]
    e.mulsd(1, 2); e.addsd(0, 1)
    e.inc_r64(2); e.cmp_r64_r64(2, 0xD); e.jl("Lk")
    e.movq_r64_xmm(6, 8)              # rsi = bias
    e.cmp_r64_imm(10, 1)
    e.jle("B0")
    e.mov_r64_r64(0, 8)
    e.shl_r64_imm(0, 3)
    e.movsd_load_xmm(2, 6, 0, 1)      # bias[m]
    e.jmp("Bd")
    e.label("B0")
    e.xor_r32_r32(0, 0)               # _fix21：rax 必须为 0（idx 是寄存器）
    e.movsd_load_xmm(2, 6, 0, 1)      # bias[0]
    e.label("Bd")
    e.addsd(0, 2)
    e.cmp_r64_imm(11, 0)
    e.je("Nr")
    e.pxor_xmm(1, 1)
    e.ucomisd(0, 1)
    e.ja("Nr")                        # _fix25：z>0 保留
    e.pxor_xmm(0, 0)                  # z<=0 → 0
    e.label("Nr")
    e.movq_r64_xmm(1, 9)              # rcx = out
    e.mov_r64_r64(0, 8)
    e.shl_r64_imm(0, 3)
    e.movsd_store_xmm(0, 1, 0, 1)
    e.inc_r64(8); e.cmp_r64_r64(8, 0xC); e.jl("Lm")
    e.pop_r64(0xF); e.pop_r64(0xE); e.pop_r64(0xD); e.pop_r64(0xC); e.pop_r64(3); e.pop_r64(7); e.pop_r64(6)
    e.ret()
    _emit_consts(e)
    return _fin(e)


def _gen_affine2v_back():
    """affine2v_back(a, M, K, b, g, bias, biasn, relu_flag, ga, gb, gb_bias)
    rcx rdx r8 r9 [rsp+40..]：g=104 bias=112 biasn=120 relu=128 ga=136 gb=144 gb_bias=152
    z/g2 缓冲 [rsp+8+m*8]（M 个）；sub = M*8+16
    寄存器：r15=a rdi=b r12=M r13=K r10=biasn r11=relu rbx=rsp
    xmm8=g xmm9=bias xmm10=ga xmm11=gb xmm12=gb_bias"""
    e = Enc()
    e.push_r64(6); e.push_r64(7); e.push_r64(3); e.push_r64(0xC); e.push_r64(0xD); e.push_r64(0xE); e.push_r64(0xF)
    e.mov_r64_r64(0xF, R_RCX)
    e.mov_r64_r64(0xC, R_RDX)
    e.mov_r64_r64(0xD, R_R8)
    e.mov_r64_r64(7, R_R9)
    e.mov_r64_m64_rsp(1, 96)          # rcx = g
    e.movq_xmm_r64(8, 1)
    e.mov_r64_m64_rsp(1, 104)         # rcx = bias
    e.movq_xmm_r64(9, 1)
    e.mov_r64_m64_rsp(10, 112)        # r10 = biasn
    e.mov_r64_m64_rsp(11, 120)        # r11 = relu_flag
    e.mov_r64_m64_rsp(1, 128)         # rcx = ga
    e.movq_xmm_r64(10, 1)
    e.mov_r64_m64_rsp(1, 136)         # rcx = gb
    e.movq_xmm_r64(11, 1)
    e.mov_r64_m64_rsp(1, 144)         # rcx = gb_bias
    e.movq_xmm_r64(12, 1)
    e.mov_r64_r64(3, 4)               # rbx = rsp
    e.mov_r64_r64(0, 0xC)
    e.shl_r64_imm(0, 3)               # rax = M*8
    e.movq_xmm_r64(13, 0)             # xmm13 = M*8（_fix24：prod 独立区基准）
    e.mov_r64_r64(2, 0)               # rdx = M*8
    e.mov_r64_r64(0, 0xC)
    e.shl_r64_imm(0, 3)
    e.add_r64_r64(0, 2)               # rax = 2*M*8
    e.add_r64_imm(0, 16)
    e.sub_r64_r64(4, 0)               # rsp -= 2*M*8+16
    # z[m] = 朴素Σ + bias → [rsp+8+m*8]
    e.xor_r32_r32(8, 8)               # r8 = m
    e.label("Lm")
    e.pxor_xmm(0, 0)
    e.xor_r32_r32(2, 2)               # rdx = k
    e.label("Lk")
    e.mov_r64_r64(0, 8)
    e.imul_r64_r64(0, 0xD)
    e.add_r64_r64(0, 2)
    e.shl_r64_imm(0, 3)
    e.movsd_load_xmm(1, 0xF, 0, 1)
    e.mov_r64_r64(0, 2)
    e.shl_r64_imm(0, 3)
    e.movsd_load_xmm(2, 7, 0, 1)
    e.mulsd(1, 2); e.addsd(0, 1)
    e.inc_r64(2); e.cmp_r64_r64(2, 0xD); e.jl("Lk")
    e.movq_r64_xmm(6, 9)              # rsi = bias
    e.cmp_r64_imm(10, 1)
    e.jle("B0")
    e.mov_r64_r64(0, 8)
    e.shl_r64_imm(0, 3)
    e.movsd_load_xmm(2, 6, 0, 1)      # bias[m]
    e.jmp("Bd")
    e.label("B0")
    e.xor_r32_r32(0, 0)               # _fix21：rax 必须为 0（idx 是寄存器）
    e.movsd_load_xmm(2, 6, 0, 1)      # bias[0]
    e.label("Bd")
    e.addsd(0, 2)
    e.mov_r64_r64(0, 8)
    e.shl_r64_imm(0, 3)
    e.add_r64_imm(0, 8)
    e.add_r64_r64(0, 4)
    e.movsd_store_xmm(0, 0, None, 1)  # z[m]
    e.inc_r64(8); e.cmp_r64_r64(8, 0xC); e.jl("Lm")
    # g2[m] = relu && !(z>0) ? 0 : g[m] → 覆盖 z[m]
    e.movq_r64_xmm(6, 8)              # rsi = g
    e.xor_r32_r32(8, 8)               # r8 = m
    e.label("Lg")
    e.mov_r64_r64(0, 8)
    e.shl_r64_imm(0, 3)
    e.add_r64_imm(0, 8)
    e.add_r64_r64(0, 4)
    e.movsd_load_xmm(1, 0, None, 1)   # z[m]
    e.mov_r64_r64(0, 8)
    e.shl_r64_imm(0, 3)
    e.movsd_load_xmm(2, 6, 0, 1)      # g[m]
    e.cmp_r64_imm(11, 0)
    e.je("Gok")
    e.pxor_xmm(3, 3)
    e.ucomisd(1, 3)
    e.ja("Gok")                       # z>0 → g2=g
    e.pxor_xmm(2, 2)                  # z<=0 → g2=0
    e.label("Gok")
    e.mov_r64_r64(0, 8)
    e.shl_r64_imm(0, 3)
    e.add_r64_imm(0, 8)
    e.add_r64_r64(0, 4)
    e.movsd_store_xmm(2, 0, None, 1)  # g2[m]
    e.inc_r64(8); e.cmp_r64_r64(8, 0xC); e.jl("Lg")
    # ga[m*K+k] = g2[m]*b[k]
    e.movq_r64_xmm(1, 10)             # rcx = ga
    e.xor_r32_r32(8, 8)               # r8 = m
    e.label("Lam")
    e.xor_r32_r32(2, 2)               # rdx = k
    e.label("Lak")
    e.mov_r64_r64(0, 8)
    e.shl_r64_imm(0, 3)
    e.add_r64_imm(0, 8)
    e.add_r64_r64(0, 4)
    e.movsd_load_xmm(1, 0, None, 1)   # g2[m]
    e.mov_r64_r64(0, 2)
    e.shl_r64_imm(0, 3)
    e.movsd_load_xmm(2, 7, 0, 1)      # b[k]
    e.mulsd(1, 2)
    e.mov_r64_r64(0, 8)
    e.imul_r64_r64(0, 0xD)
    e.add_r64_r64(0, 2)
    e.shl_r64_imm(0, 3)
    e.movsd_store_xmm(1, 1, 0, 1)     # ga[m*K+k]
    e.inc_r64(2); e.cmp_r64_r64(2, 0xD); e.jl("Lak")
    e.inc_r64(8); e.cmp_r64_r64(8, 0xC); e.jl("Lam")
    # gb[k] = neumaier(a[mK+k]*g2[m] over m)
    e.movq_r64_xmm(1, 11)             # rcx = gb
    e.xor_r32_r32(2, 2)               # rdx = k
    e.label("Lbk")
    e.xor_r32_r32(8, 8)               # r8 = m
    e.label("Lbm")
    e.mov_r64_r64(0, 8)
    e.imul_r64_r64(0, 0xD)
    e.add_r64_r64(0, 2)
    e.shl_r64_imm(0, 3)
    e.movsd_load_xmm(1, 0xF, 0, 1)    # a[m*K+k]
    e.mov_r64_r64(0, 8)
    e.shl_r64_imm(0, 3)
    e.add_r64_imm(0, 8)
    e.add_r64_r64(0, 4)
    e.movsd_load_xmm(2, 0, None, 1)   # g2[m]
    e.mulsd(1, 2)
    e.mov_r64_r64(0, 8)
    e.shl_r64_imm(0, 3)
    e.movq_r64_xmm(6, 13)             # rsi = M*8
    e.add_r64_r64(0, 6)
    e.add_r64_imm(0, 8)
    e.add_r64_r64(0, 4)
    e.movsd_store_xmm(1, 0, None, 1)  # prod[m] → [rsp+8+M*8+m*8]（_fix24）
    e.inc_r64(8); e.cmp_r64_r64(8, 0xC); e.jl("Lbm")
    e.movq_r64_xmm(6, 13)             # rsi = M*8
    e.add_r64_r64(6, 4)               # rsi = rsp + M*8
    e.add_r64_imm(6, 8)               # rsi = rsp + M*8 + 8（p = prod）
    e.mov_r64_r64(1, 0xC)
    _neumaier(e, 0x6, 1, 8)           # i_reg=r8（m 循环已结束）
    e.mov_r64_r64(0, 2)
    e.shl_r64_imm(0, 3)
    e.movq_r64_xmm(1, 11)             # rcx = gb
    e.movsd_store_xmm(0, 1, 0, 1)     # gb[k]
    e.inc_r64(2); e.cmp_r64_r64(2, 0xD); e.jl("Lbk")
    # gb_bias：biasn>1 → gb_bias[m]=g2[m]；否则 gb_bias[0]=朴素Σg2
    e.movq_r64_xmm(1, 12)             # rcx = gb_bias
    e.cmp_r64_imm(10, 1)
    e.jle("Bs")
    e.xor_r32_r32(8, 8)               # r8 = m
    e.label("Lbm2")
    e.mov_r64_r64(0, 8)
    e.shl_r64_imm(0, 3)
    e.add_r64_imm(0, 8)
    e.add_r64_r64(0, 4)
    e.movsd_load_xmm(2, 0, None, 1)   # g2[m]
    e.mov_r64_r64(0, 8)
    e.shl_r64_imm(0, 3)
    e.movsd_store_xmm(2, 1, 0, 1)     # gb_bias[m]
    e.inc_r64(8); e.cmp_r64_r64(8, 0xC); e.jl("Lbm2")
    e.jmp("Bd2")
    e.label("Bs")
    e.pxor_xmm(0, 0)
    e.xor_r32_r32(8, 8)
    e.label("Lbs")
    e.mov_r64_r64(0, 8)
    e.shl_r64_imm(0, 3)
    e.add_r64_imm(0, 8)
    e.add_r64_r64(0, 4)
    e.movsd_load_xmm(2, 0, None, 1)
    e.addsd(0, 2)
    e.inc_r64(8); e.cmp_r64_r64(8, 0xC); e.jl("Lbs")
    e.movsd_store_xmm_disp(0, 1, 0)   # gb_bias[0]（_fix22：rax 残留循环值）
    e.label("Bd2")
    e.mov_r64_r64(4, 3)
    e.pop_r64(0xF); e.pop_r64(0xE); e.pop_r64(0xD); e.pop_r64(0xC); e.pop_r64(3); e.pop_r64(7); e.pop_r64(6)
    e.ret()
    _emit_consts(e)
    return _fin(e)


def _gen_affine2_back():
    """affine2_back(a, M, K, b, N, g, bias, biasn, relu_flag, ga, gb, gb_bias)
    rcx rdx r8 r9 [rsp+40..]：N=96 g=104 bias=112 biasn=120 relu=128 ga=136 gb=144 gb_bias=152
    z/g2 缓冲 [rsp+8+i*8]（M*N 个）；col/prod 区 [rsp+8+MN*8..]
    sub = (M*N + M + K)*8 + 16
    寄存器：r15=a rdi=b r12=M r13=K r14=N r10=biasn r11=relu rbx=rsp
    xmm8=g xmm9=bias xmm10=ga xmm11=gb xmm12=gb_bias xmm13=MN*8+8"""
    e = Enc()
    e.push_r64(6); e.push_r64(7); e.push_r64(3); e.push_r64(0xC); e.push_r64(0xD); e.push_r64(0xE); e.push_r64(0xF)
    e.mov_r64_r64(0xF, R_RCX)
    e.mov_r64_r64(0xC, R_RDX)
    e.mov_r64_r64(0xD, R_R8)
    e.mov_r64_r64(7, R_R9)
    e.mov_r64_m64_rsp(0xE, 96)        # r14 = N
    e.mov_r64_m64_rsp(1, 104)         # rcx = g
    e.movq_xmm_r64(8, 1)
    e.mov_r64_m64_rsp(1, 112)         # rcx = bias
    e.movq_xmm_r64(9, 1)
    e.mov_r64_m64_rsp(10, 120)        # r10 = biasn
    e.mov_r64_m64_rsp(11, 128)        # r11 = relu_flag
    e.mov_r64_m64_rsp(1, 136)         # rcx = ga
    e.movq_xmm_r64(10, 1)
    e.mov_r64_m64_rsp(1, 144)         # rcx = gb
    e.movq_xmm_r64(11, 1)
    e.mov_r64_m64_rsp(1, 152)         # rcx = gb_bias
    e.movq_xmm_r64(12, 1)
    # xmm13 = MN*8+8
    e.mov_r64_r64(0, 0xC)
    e.imul_r64_r64(0, 0xE)
    e.shl_r64_imm(0, 3)
    e.add_r64_imm(0, 8)
    e.movq_xmm_r64(13, 0)
    e.mov_r64_r64(3, 4)               # rbx = rsp
    # sub = (M*N + M + K)*8 + 16
    e.mov_r64_r64(0, 0xC)
    e.imul_r64_r64(0, 0xE)
    e.add_r64_r64(0, 0xC)
    e.add_r64_r64(0, 0xD)
    e.shl_r64_imm(0, 3)
    e.add_r64_imm(0, 16)
    e.sub_r64_r64(4, 0)
    # z[m*N+n] = neumaier(prod) + bias → [rsp+8+(m*N+n)*8]
    e.xor_r32_r32(8, 8)               # r8 = m
    e.label("Lm")
    e.xor_r32_r32(9, 9)               # r9 = n
    e.label("Ln")
    e.xor_r32_r32(2, 2)               # rdx = k
    e.label("Lk")
    e.mov_r64_r64(0, 8)
    e.imul_r64_r64(0, 0xD)
    e.add_r64_r64(0, 2)
    e.shl_r64_imm(0, 3)
    e.movsd_load_xmm(1, 0xF, 0, 1)    # a[m*K+k]
    e.mov_r64_r64(0, 2)
    e.imul_r64_r64(0, 0xE)
    e.add_r64_r64(0, 9)
    e.shl_r64_imm(0, 3)
    e.movsd_load_xmm(2, 7, 0, 1)      # b[k*N+n]
    e.mulsd(1, 2)
    # prod[k] → [rsp + k*8 + (MN*8+8)]
    e.mov_r64_r64(0, 2)
    e.shl_r64_imm(0, 3)
    e.movq_r64_xmm(6, 13)             # rsi = MN*8+8
    e.add_r64_r64(0, 6)
    e.add_r64_r64(0, 4)
    e.movsd_store_xmm(1, 0, None, 1)
    e.inc_r64(2); e.cmp_r64_r64(2, 0xD); e.jl("Lk")
    # neumaier(prod, K)：p = rsp + (MN*8+8)
    e.movq_r64_xmm(6, 13)
    e.add_r64_r64(6, 4)
    e.mov_r64_r64(1, 0xD)
    _neumaier(e, 0x6, 1, 0)           # i_reg=rax
    e.movq_r64_xmm(6, 9)              # rsi = bias
    e.cmp_r64_imm(10, 0)
    e.jle("B0")
    e.mov_r64_r64(0, 9)
    e.shl_r64_imm(0, 3)
    e.movsd_load_xmm(2, 6, 0, 1)      # bias[n]
    e.jmp("Bd")
    e.label("B0")
    e.xor_r32_r32(0, 0)
    e.movsd_load_xmm(2, 6, 0, 1)
    e.label("Bd")
    e.addsd(0, 2)
    # z[m*N+n] → [rsp+8+(m*N+n)*8]
    e.mov_r64_r64(0, 8)
    e.imul_r64_r64(0, 0xE)
    e.add_r64_r64(0, 9)
    e.shl_r64_imm(0, 3)
    e.add_r64_imm(0, 8)
    e.add_r64_r64(0, 4)
    e.movsd_store_xmm(0, 0, None, 1)
    e.inc_r64(9); e.cmp_r64_r64(9, 0xE); e.jl("Ln")
    e.inc_r64(8); e.cmp_r64_r64(8, 0xC); e.jl("Lm")
    # g2[i] = relu && !(z>0) ? 0 : g[i] → 覆盖 z 缓冲
    e.movq_r64_xmm(6, 8)              # rsi = g
    e.mov_r64_r64(0, 0xC)             # rax = M*N（_fix23：g2 循环界）
    e.imul_r64_r64(0, 0xE)
    e.mov_r64_r64(2, 0)               # rdx = M*N（_fix23b：r10 仍是 biasn，勿覆盖）
    e.xor_r32_r32(8, 8)               # r8 = i
    e.label("Lg")
    e.mov_r64_r64(0, 8)
    e.shl_r64_imm(0, 3)
    e.add_r64_imm(0, 8)
    e.add_r64_r64(0, 4)
    e.movsd_load_xmm(1, 0, None, 1)   # z[i]
    e.mov_r64_r64(0, 8)
    e.shl_r64_imm(0, 3)
    e.movsd_load_xmm(2, 6, 0, 1)      # g[i]
    e.cmp_r64_imm(11, 0)
    e.je("Gok")
    e.pxor_xmm(3, 3)
    e.ucomisd(1, 3)
    e.ja("Gok")
    e.pxor_xmm(2, 2)
    e.label("Gok")
    e.mov_r64_r64(0, 8)
    e.shl_r64_imm(0, 3)
    e.add_r64_imm(0, 8)
    e.add_r64_r64(0, 4)
    e.movsd_store_xmm(2, 0, None, 1)  # g2[i]
    e.inc_r64(8); e.cmp_r64_r64(8, 2); e.jl("Lg")    # _fix23b：界 M*N（rdx）
    # ga[m*K+k] = Σ_n g2[m*N+n]*b[k*N+n]（朴素）
    e.movq_r64_xmm(1, 10)             # rcx = ga
    e.xor_r32_r32(8, 8)               # r8 = m
    e.label("Lam")
    e.xor_r32_r32(2, 2)               # rdx = k
    e.label("Lak")
    e.pxor_xmm(0, 0)
    e.xor_r32_r32(9, 9)               # r9 = n
    e.label("Lan")
    e.mov_r64_r64(0, 8)
    e.imul_r64_r64(0, 0xE)
    e.add_r64_r64(0, 9)
    e.shl_r64_imm(0, 3)
    e.add_r64_imm(0, 8)
    e.add_r64_r64(0, 4)
    e.movsd_load_xmm(1, 0, None, 1)   # g2[m*N+n]
    e.mov_r64_r64(0, 2)
    e.imul_r64_r64(0, 0xE)
    e.add_r64_r64(0, 9)
    e.shl_r64_imm(0, 3)
    e.movsd_load_xmm(2, 7, 0, 1)      # b[k*N+n]
    e.mulsd(1, 2); e.addsd(0, 1)
    e.inc_r64(9); e.cmp_r64_r64(9, 0xE); e.jl("Lan")
    e.mov_r64_r64(0, 8)
    e.imul_r64_r64(0, 0xD)
    e.add_r64_r64(0, 2)
    e.shl_r64_imm(0, 3)
    e.movsd_store_xmm(0, 1, 0, 1)     # ga[m*K+k]
    e.inc_r64(2); e.cmp_r64_r64(2, 0xD); e.jl("Lak")
    e.inc_r64(8); e.cmp_r64_r64(8, 0xC); e.jl("Lam")
    # gb[k*N+n] = Σ_m a[m*K+k]*g2[m*N+n]（朴素）
    e.movq_r64_xmm(1, 11)             # rcx = gb
    e.xor_r32_r32(2, 2)               # rdx = k
    e.label("Lbk")
    e.xor_r32_r32(9, 9)               # r9 = n
    e.label("Lbn")
    e.pxor_xmm(0, 0)
    e.xor_r32_r32(8, 8)               # r8 = m
    e.label("Lbm")
    e.mov_r64_r64(0, 8)
    e.imul_r64_r64(0, 0xD)
    e.add_r64_r64(0, 2)
    e.shl_r64_imm(0, 3)
    e.movsd_load_xmm(1, 0xF, 0, 1)    # a[m*K+k]
    e.mov_r64_r64(0, 8)
    e.imul_r64_r64(0, 0xE)
    e.add_r64_r64(0, 9)
    e.shl_r64_imm(0, 3)
    e.add_r64_imm(0, 8)
    e.add_r64_r64(0, 4)
    e.movsd_load_xmm(2, 0, None, 1)   # g2[m*N+n]
    e.mulsd(1, 2); e.addsd(0, 1)
    e.inc_r64(8); e.cmp_r64_r64(8, 0xC); e.jl("Lbm")
    e.mov_r64_r64(0, 2)
    e.imul_r64_r64(0, 0xE)
    e.add_r64_r64(0, 9)
    e.shl_r64_imm(0, 3)
    e.movsd_store_xmm(0, 1, 0, 1)     # gb[k*N+n]
    e.inc_r64(9); e.cmp_r64_r64(9, 0xE); e.jl("Lbn")
    e.inc_r64(2); e.cmp_r64_r64(2, 0xD); e.jl("Lbk")
    # gb_bias：biasn>0 → 每列 neumaier；否则 neumaier(g2 全)
    e.movq_r64_xmm(1, 12)             # rcx = gb_bias
    e.cmp_r64_imm(10, 0)
    e.jle("Ball")
    e.xor_r32_r32(9, 9)               # r9 = n
    e.label("Lbn2")
    e.xor_r32_r32(8, 8)               # r8 = m
    e.label("Lbm2")
    e.mov_r64_r64(0, 8)
    e.imul_r64_r64(0, 0xE)
    e.add_r64_r64(0, 9)
    e.shl_r64_imm(0, 3)
    e.add_r64_imm(0, 8)
    e.add_r64_r64(0, 4)
    e.movsd_load_xmm(2, 0, None, 1)   # g2[m*N+n]
    # col[m] → [rsp + m*8 + (MN*8+8)]
    e.mov_r64_r64(0, 8)
    e.shl_r64_imm(0, 3)
    e.movq_r64_xmm(6, 13)
    e.add_r64_r64(0, 6)
    e.add_r64_r64(0, 4)
    e.movsd_store_xmm(2, 0, None, 1)
    e.inc_r64(8); e.cmp_r64_r64(8, 0xC); e.jl("Lbm2")
    # neumaier(col, M)：p = rsp + (MN*8+8)
    e.movq_r64_xmm(6, 13)
    e.add_r64_r64(6, 4)
    e.mov_r64_r64(1, 0xC)
    _neumaier(e, 0x6, 1, 8)           # i_reg=r8
    e.mov_r64_r64(0, 9)
    e.shl_r64_imm(0, 3)
    e.movq_r64_xmm(1, 12)
    e.movsd_store_xmm(0, 1, 0, 1)     # gb_bias[n]
    e.inc_r64(9); e.cmp_r64_r64(9, 0xE); e.jl("Lbn2")
    e.jmp("Bdone")
    e.label("Ball")
    # neumaier(g2, M*N)：p = rsp+8
    e.mov_r64_r64(6, 4)
    e.add_r64_imm(6, 8)
    e.mov_r64_r64(0, 0xC)
    e.imul_r64_r64(0, 0xE)
    e.mov_r64_r64(1, 0)
    _neumaier(e, 0x6, 1, 0)
    e.movq_r64_xmm(1, 12)
    e.movsd_store_xmm_disp(0, 1, 0)   # gb_bias[0]（_fix22）
    e.label("Bdone")
    e.mov_r64_r64(4, 3)
    e.pop_r64(0xF); e.pop_r64(0xE); e.pop_r64(0xD); e.pop_r64(0xC); e.pop_r64(3); e.pop_r64(7); e.pop_r64(6)
    e.ret()
    _emit_consts(e)
    return _fin(e)
