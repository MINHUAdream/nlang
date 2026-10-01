# v0.15 自举第二内核：tl 语言发射 x86-64 add 内核（single_loop add）
# 目标：与 tl_emit._gen_single_loop('add') 逐字节一致（51 字节）
# ABI: add(a, b, out, n): rcx=a rdx=b r8=out r9=n
# rel32 = target - (pos + insn_len)，与 tl_emit.Enc.patch 相同。

let P_push = tensor([0x56, 0x57, 0x41, 0x53])   # push rsi; push rdi; push r11
let P_mov1 = tensor([0x48, 0x89, 0xCE])          # mov rsi, rcx
let P_mov2 = tensor([0x4C, 0x89, 0xC7])          # mov rdi, r8
let P_mov3 = tensor([0x4D, 0x89, 0xCB])          # mov r11, r9
let P_xor  = tensor([0x33, 0xC9])                # xor ecx, ecx
let P_ld0  = tensor([0xF2, 0x0F, 0x10, 0x04, 0xCE])  # xmm0 = [rsi+rcx*8]
let P_ld1  = tensor([0xF2, 0x0F, 0x10, 0x0C, 0xCA])  # xmm1 = [rdx+rcx*8]
let P_add  = tensor([0xF2, 0x0F, 0x58, 0xC1])    # addsd xmm0, xmm1
let P_st   = tensor([0xF2, 0x0F, 0x11, 0x04, 0xCF])  # [rdi+rcx*8] = xmm0
let P_inc  = tensor([0x48, 0xFF, 0xC1])          # inc rcx
let P_cmp  = tensor([0x4C, 0x39, 0xD9])          # cmp rcx, r11
let P_jl   = tensor([0x0F, 0x8C])                # jl rel32
let P_pop  = tensor([0x41, 0x5B, 0x5F, 0x5E, 0xC3])

let head = cat(cat(cat(cat(cat(cat(P_push, P_mov1), P_mov2), P_mov3), P_xor), P_ld0), P_ld1)
let h1 = cat(cat(cat(head, P_add), P_st), P_inc)
let h2 = cat(h1, P_cmp)
let pjl = len(h2)
let rel_jl = sub(tensor([15]), add(pjl, 6))
let jl_r = pack32(get(rel_jl, 0))
let code = cat(cat(h2, P_jl), cat(jl_r, P_pop))
print(code)
