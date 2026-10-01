# v0.15 自举第一环：tl 语言发射 x86-64 relu 内核
# 目标：与 tl_emit._gen_single_loop('relu') 逐字节一致（70 字节）
# ABI: relu(x, out, n): rcx=x rdx=out r8=n
# 偏移基准与 tl_emit.Enc.patch 相同：rel32 = target - (pos + insn_len)
# 全部字节与偏移均在 tl 语言内计算：Python 只做装载（load_mc）与执行。

let P_push = tensor([0x56, 0x57, 0x41, 0x53])   # push rsi; push rdi; push r11
let P_mov1 = tensor([0x48, 0x89, 0xCE])          # mov rsi, rcx
let P_mov2 = tensor([0x48, 0x89, 0xD7])          # mov rdi, rdx
let P_mov3 = tensor([0x4D, 0x89, 0xC3])          # mov r11, r8
let P_xor  = tensor([0x33, 0xC9])                # xor ecx, ecx
let P_ld   = tensor([0xF2, 0x0F, 0x10, 0x04, 0xCE])  # movsd xmm0, [rsi+rcx*8]  [L]
let P_px1  = tensor([0x66, 0x0F, 0xEF, 0xC9])    # pxor xmm1, xmm1
let P_uc   = tensor([0x66, 0x0F, 0x2E, 0xC1])    # ucomisd xmm0, xmm1
let P_jbe  = tensor([0x0F, 0x86])                # jbe rel32（6 字节）
let P_st   = tensor([0xF2, 0x0F, 0x11, 0x04, 0xCF])  # movsd [rdi+rcx*8], xmm0
let P_jmp  = tensor([0xE9])                      # jmp rel32（5 字节）
let P_px0  = tensor([0x66, 0x0F, 0xEF, 0xC0])    # pxor xmm0, xmm0  [Lz]
let P_inc  = tensor([0x48, 0xFF, 0xC1])          # inc rcx  [Lnext]
let P_cmp  = tensor([0x4C, 0x39, 0xD9])          # cmp rcx, r11
let P_jl   = tensor([0x0F, 0x8C])                # jl rel32（6 字节）
let P_pop  = tensor([0x41, 0x5B, 0x5F, 0x5E, 0xC3])  # pop r11; pop rdi; pop rsi; ret

# ---- 头部固定指令（pos 0..27）----
let head = cat(cat(cat(cat(cat(cat(cat(P_push, P_mov1), P_mov2), P_mov3), P_xor), P_ld), P_px1), P_uc)

# ---- jbe 偏移：44 - (pos_jbe + 6) = 10 ----
let pjbe = len(head)
let rel_jbe = sub(tensor([44]), add(pjbe, 6))
let jbe_r = pack32(get(rel_jbe, 0))
let seg_jbe = cat(P_jbe, jbe_r)

# ---- jmp 偏移：53 - (pos_jmp + 5) = 9 ----
let h2 = cat(cat(head, seg_jbe), P_st)
let pjmp = len(h2)
let rel_jmp = sub(tensor([53]), add(pjmp, 5))
let jmp_r = pack32(get(rel_jmp, 0))
let h3 = cat(cat(cat(cat(h2, P_jmp), jmp_r), P_px0), P_st)

# ---- jl 偏移：15 - (pos_jl + 6) = -50 ----
let h4 = cat(cat(h3, P_inc), P_cmp)
let pjl = len(h4)
let rel_jl = sub(tensor([15]), add(pjl, 6))
let jl_r = pack32(get(rel_jl, 0))
let seg_jl = cat(P_jl, jl_r)

# ---- 完整内核 ----
let code = cat(cat(h4, seg_jl), P_pop)
print(code)
