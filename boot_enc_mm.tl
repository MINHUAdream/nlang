# v0.18 表驱动发射器 · mm2（三重循环）内核
# 与 tl_emit.gen_mm2() 逐字节一致（153 字节）
# ABI: mm2(a,b,out,M,K,N): rcx=a rdx=b r8=out r9=M [rsp+40]=K [rsp+48]=N
# 寄存器: rsi=a rdi=b rbx=out r12=N r13=M r14=K; rcx=i rdx=j r8=k rax=addr; xmm0=s
# op 表扩展：
#   20=imul(d,s) 48 0F AF modrm(3,d,s)
#   21=add_r64(d,s) 48 03 modrm(3,d,s)
#   22=shl_imm(r,n) 48 C1 E0+r n
#   23=mov_r64_m64_rsp(dst,disp8) rex 8B modrm(1,dst,4) 24 disp
#   24=ld_idx(dst_xmm,base) F2 0F 10 modrm(0,dst,4) sib(1,0,base)
#   25=st_idx(src_xmm,base) F2 0F 11 modrm(0,src,4) sib(1,0,base)

let prog = tensor([
    [0,6,0],[0,7,0],[0,3,0],[0,12,0],[0,13,0],[0,14,0],
    [1,6,1],[1,7,2],[1,3,8],[1,13,9],
    [23,14,88],[23,12,96],
    [2,1,1],
    [13,0,0],
    [2,2,2],
    [13,1,0],
    [5,0,0],
    [2,8,8],
    [13,2,0],
    [1,0,1],[20,0,14],[21,0,8],[22,0,3],[24,1,6],
    [1,0,8],[20,0,12],[21,0,2],[22,0,3],[24,2,7],
    [15,0x59,0xCA],[15,0x58,0xC1],
    [9,8,0],[10,8,14],[7,12,2],
    [1,0,1],[20,0,12],[21,0,2],[22,0,3],[25,0,3],
    [9,2,0],[10,2,12],[7,12,1],
    [9,1,0],[10,1,13],[7,12,0],
    [11,14,0],[11,13,0],[11,12,0],[11,3,0],[11,7,0],[11,6,0],
    [12,0,0]
])

let LEN = tensor([1, 3, 2, 5, 5, 4, 4, 6, 5, 3, 3, 1, 1, 0, 5, 4, 4, 6, 10, 5,
                  4, 3, 4, 5, 5, 5])

let pos = tensor([0])
let lab = tensor([-1, -1, -1])
for i in range(len(prog)) {
    let op = get2(prog, i, 0)
    let a = get2(prog, i, 1)
    let cur = get(pos, sub(len(pos), 1))
    if eq(op, 13) {
        let lab = set1(lab, a, cur)
        let pos = cat(pos, mk(cur))
    } else {
        let L = get(LEN, op)
        if eq(op, 0) {
            if ge(a, 8) { let L = add(L, 1) }
        }
        if eq(op, 11) {
            if ge(a, 8) { let L = add(L, 1) }
        }
        if eq(op, 2) {
            if ge(a, 8) { let L = add(L, 1) }
        }
        let pos = cat(pos, mk(add(cur, L)))
    }
}

let code = empty()
for i in range(len(prog)) {
    let op = get2(prog, i, 0)
    let a = get2(prog, i, 1)
    let b = get2(prog, i, 2)
    let cur = get(pos, i)
    let lid = -1
    if eq(op, 7) { let lid = b }
    if eq(op, 8) { let lid = a }
    if eq(op, 13) { let lid = a }
    if eq(op, 0) {
        if ge(a, 8) {
            let code = cat(code, cat(mk(0x41), mk(bor(0x50, band(a, 7)))))
        } else {
            let code = cat(code, mk(bor(0x50, a)))
        }
    }
    if eq(op, 1) {
        let rex = bor(0x48, bor(bshl(bshr(b, 3), 2), bshr(a, 3)))
        let modrm = bor(0xC0, bor(bshl(band(b, 7), 3), band(a, 7)))
        let code = cat(code, cat(cat(mk(rex), mk(0x89)), mk(modrm)))
    }
    if eq(op, 2) {
        let modrm = bor(0xC0, bor(bshl(band(a, 7), 3), band(a, 7)))
        let rex = bor(0x40, bor(bshl(bshr(a, 3), 2), bshr(a, 3)))
        if eq(rex, 0x40) {
            let code = cat(code, cat(mk(0x33), mk(modrm)))
        } else {
            let code = cat(code, cat(cat(mk(rex), mk(0x33)), mk(modrm)))
        }
    }
    if eq(op, 5) {
        let modrm = bor(0xC0, bor(bshl(band(b, 7), 3), band(a, 7)))
        let code = cat(code, cat(cat(mk(0x66), mk(0x0F)), cat(mk(0xEF), mk(modrm))))
    }
    if eq(op, 7) {
        let rel = sub(get(lab, lid), add(cur, 6))
        let code = cat(code, cat(cat(mk(0x0F), mk(bor(0x80, a))), pack32(rel)))
    }
    if eq(op, 9) {
        let rex = bor(0x48, bshr(a, 3))
        let code = cat(code, cat(cat(mk(rex), mk(0xFF)), mk(bor(0xC0, band(a, 7)))))
    }
    if eq(op, 10) {
        let rex = bor(0x48, bor(bshl(bshr(b, 3), 2), bshr(a, 3)))
        let modrm = bor(0xC0, bor(bshl(band(b, 7), 3), band(a, 7)))
        let code = cat(code, cat(cat(mk(rex), mk(0x39)), mk(modrm)))
    }
    if eq(op, 11) {
        if ge(a, 8) {
            let code = cat(code, cat(mk(0x41), mk(bor(0x58, band(a, 7)))))
        } else {
            let code = cat(code, mk(bor(0x58, a)))
        }
    }
    if eq(op, 12) {
        let code = cat(code, mk(0xC3))
    }
    if eq(op, 15) {
        let code = cat(code, cat(cat(mk(0xF2), mk(0x0F)), cat(mk(a), mk(b))))
    }
    if eq(op, 20) {
        let rex = bor(0x48, bor(bshl(bshr(a, 3), 2), bshr(b, 3)))
        let modrm = bor(0xC0, bor(bshl(band(a, 7), 3), band(b, 7)))
        let code = cat(code, cat(cat(cat(mk(rex), mk(0x0F)), mk(0xAF)), mk(modrm)))
    }
    if eq(op, 21) {
        let rex = bor(0x48, bor(bshl(bshr(a, 3), 2), bshr(b, 3)))
        let modrm = bor(0xC0, bor(bshl(band(a, 7), 3), band(b, 7)))
        let code = cat(code, cat(cat(mk(rex), mk(0x03)), mk(modrm)))
    }
    if eq(op, 22) {
        let rex = bor(0x48, bshr(a, 3))
        let code = cat(code, cat(cat(cat(mk(rex), mk(0xC1)), mk(bor(0xE0, band(a, 7)))), mk(b)))
    }
    if eq(op, 23) {
        let rex = bor(0x48, bshl(bshr(a, 3), 2))
        let modrm = bor(0x40, bor(bshl(band(a, 7), 3), 4))
        let code = cat(code, cat(cat(cat(mk(rex), mk(0x8B)), cat(mk(modrm), mk(0x24))), mk(b)))
    }
    if eq(op, 24) {
        let modrm = bor(bshl(band(a, 7), 3), 4)
        let sib = bor(bshl(bshr(b, 3), 6), band(b, 7))
        let code = cat(code, cat(cat(mk(0xF2), mk(0x0F)), cat(cat(mk(0x10), mk(modrm)), mk(sib))))
    }
    if eq(op, 25) {
        let modrm = bor(bshl(band(a, 7), 3), 4)
        let sib = bor(bshl(bshr(b, 3), 6), band(b, 7))
        let code = cat(code, cat(cat(mk(0xF2), mk(0x0F)), cat(cat(mk(0x11), mk(modrm)), mk(sib))))
    }
}
print(code)
