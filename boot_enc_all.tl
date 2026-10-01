# v0.17 表驱动通用发射器 · 全 single_loop 内核（9 kind 顺序发射）
# 与 tl_emit._gen_single_loop(kind) 逐字节一致
# 输出 all = 每段 [pack32(len) + code] 顺序拼接
# op 表：
#   0=push(reg) 1=mov(dst,src) 2=xor32(reg) 3=ld0(dst_xmm) 4=st(src_xmm)
#   5=pxor(x,y) 6=ucomisd 7=jcc8(cc,label) 8=jmp(label) 9=inc(reg) 10=cmp(a,b)
#   11=pop(reg) 12=ret 13=label(id) 14=ld2(dst_xmm) 15=arith(opcode,modrm)
#   16=movsd_xmm(d,s) 17=load_disp(xmm,disp8) 18=movabs(reg,const_id) 19=movq_xmm_r64(xmm,r)

let CONST = tensor([0x4000000000000000])
let LEN = tensor([1, 3, 2, 5, 5, 4, 4, 6, 5, 3, 3, 1, 1, 0, 5, 4, 4, 6, 10, 5])
let KINDS = 9
let all = empty()

for k in range(KINDS) {
    let prog = empty()
    if eq(k, 0) {
        # relu: rsi=rcx rdi=rdx r11=r8
        let prog = tensor([
            [0,6,0],[0,7,0],[0,11,0],
            [1,6,1],[1,7,2],[1,11,8],
            [2,1,1],
            [13,0,0],
            [3,0,0],[5,1,1],[6,0,0],[7,6,1],[4,0,0],[8,2,0],
            [13,1,0],[5,0,0],[4,0,0],
            [13,2,0],
            [9,1,0],[10,1,11],[7,12,0],
            [11,11,0],[11,7,0],[11,6,0],[12,0,0]
        ])
    }
    if eq(k, 1) {
        # add: rsi=rcx rdi=r8 r11=r9
        let prog = tensor([
            [0,6,0],[0,7,0],[0,11,0],
            [1,6,1],[1,7,8],[1,11,9],
            [2,1,1],
            [13,0,0],
            [3,0,0],[14,1,0],[15,0x58,0xC1],[4,0,0],
            [9,1,0],[10,1,11],[7,12,0],
            [11,11,0],[11,7,0],[11,6,0],[12,0,0]
        ])
    }
    if eq(k, 2) {
        # sub
        let prog = tensor([
            [0,6,0],[0,7,0],[0,11,0],
            [1,6,1],[1,7,8],[1,11,9],
            [2,1,1],
            [13,0,0],
            [3,0,0],[14,1,0],[15,0x5C,0xC1],[4,0,0],
            [9,1,0],[10,1,11],[7,12,0],
            [11,11,0],[11,7,0],[11,6,0],[12,0,0]
        ])
    }
    if eq(k, 3) {
        # mul
        let prog = tensor([
            [0,6,0],[0,7,0],[0,11,0],
            [1,6,1],[1,7,8],[1,11,9],
            [2,1,1],
            [13,0,0],
            [3,0,0],[14,1,0],[15,0x59,0xC1],[4,0,0],
            [9,1,0],[10,1,11],[7,12,0],
            [11,11,0],[11,7,0],[11,6,0],[12,0,0]
        ])
    }
    if eq(k, 4) {
        # scale: rsi=rcx rdi=rdx r11=r8；cv 在 xmm3
        let prog = tensor([
            [0,6,0],[0,7,0],[0,11,0],
            [1,6,1],[1,7,2],[1,11,8],
            [2,1,1],
            [13,0,0],
            [3,0,0],[15,0x59,0xC3],[4,0,0],
            [9,1,0],[10,1,11],[7,12,0],
            [11,11,0],[11,7,0],[11,6,0],[12,0,0]
        ])
    }
    if eq(k, 5) {
        # scale_div: out=x/cv（xmm3）
        let prog = tensor([
            [0,6,0],[0,7,0],[0,11,0],
            [1,6,1],[1,7,2],[1,11,8],
            [2,1,1],
            [13,0,0],
            [3,0,0],[15,0x5E,0xC3],[4,0,0],
            [9,1,0],[10,1,11],[7,12,0],
            [11,11,0],[11,7,0],[11,6,0],[12,0,0]
        ])
    }
    if eq(k, 6) {
        # upd: rsi=rcx( v ) rdi=r8( out ) r11=r9( n )；g 在 rdx；lr [rsp+64]
        let prog = tensor([
            [0,6,0],[0,7,0],[0,11,0],
            [1,6,1],[1,7,8],[1,11,9],
            [2,1,1],
            [13,0,0],
            [3,0,0],[16,1,0],[14,0,0],[17,2,64],
            [15,0x59,0xC2],[15,0x5C,0xC8],[4,1,0],
            [9,1,0],[10,1,11],[7,12,0],
            [11,11,0],[11,7,0],[11,6,0],[12,0,0]
        ])
    }
    if eq(k, 7) {
        # relu_mask: rsi=rcx( x ) rdi=r8( out ) r11=r9( n )；g 在 rdx
        let prog = tensor([
            [0,6,0],[0,7,0],[0,11,0],
            [1,6,1],[1,7,8],[1,11,9],
            [2,1,1],
            [13,0,0],
            [3,0,0],[5,1,1],[6,0,0],[7,6,1],[14,0,0],[4,0,0],[8,2,0],
            [13,1,0],[5,0,0],[4,0,0],
            [13,2,0],
            [9,1,0],[10,1,11],[7,12,0],
            [11,11,0],[11,7,0],[11,6,0],[12,0,0]
        ])
    }
    if eq(k, 8) {
        # sqg: out = 2*x*g；x 在 rsi=rcx、g 在 rdx、out=rdi=r8
        let prog = tensor([
            [0,6,0],[0,7,0],[0,11,0],
            [1,6,1],[1,7,8],[1,11,9],
            [2,1,1],
            [13,0,0],
            [3,0,0],[14,1,0],[15,0x59,0xC1],
            [18,0,0],[19,2,0],[15,0x59,0xC2],[4,0,0],
            [9,1,0],[10,1,11],[7,12,0],
            [11,11,0],[11,7,0],[11,6,0],[12,0,0]
        ])
    }

    # ---- 第一遍：位置表 + label 表（label id = k*100 + a，防冲突）----
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
            let pos = cat(pos, mk(add(cur, L)))
        }
    }

    # ---- 第二遍：编码 ----
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
            let code = cat(code, cat(mk(0x33), mk(modrm)))
        }
        if eq(op, 3) {
            let m = bor(0x04, bshl(band(a, 7), 3))
            let code = cat(code, cat(cat(mk(0xF2), mk(0x0F)), cat(cat(mk(0x10), mk(m)), mk(0xCE))))
        }
        if eq(op, 4) {
            let m = bor(0x04, bshl(band(a, 7), 3))
            let code = cat(code, cat(cat(mk(0xF2), mk(0x0F)), cat(cat(mk(0x11), mk(m)), mk(0xCF))))
        }
        if eq(op, 5) {
            let modrm = bor(0xC0, bor(bshl(band(b, 7), 3), band(a, 7)))
            let code = cat(code, cat(cat(mk(0x66), mk(0x0F)), cat(mk(0xEF), mk(modrm))))
        }
        if eq(op, 6) {
            let code = cat(code, tensor([0x66, 0x0F, 0x2E, 0xC1]))
        }
        if eq(op, 7) {
            let rel = sub(get(lab, lid), add(cur, 6))
            let code = cat(code, cat(cat(mk(0x0F), mk(bor(0x80, a))), pack32(rel)))
        }
        if eq(op, 8) {
            let rel = sub(get(lab, lid), add(cur, 5))
            let code = cat(code, cat(mk(0xE9), pack32(rel)))
        }
        if eq(op, 9) {
            let code = cat(code, cat(cat(mk(0x48), mk(0xFF)), mk(bor(0xC0, band(a, 7)))))
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
        if eq(op, 14) {
            let m = bor(0x04, bshl(band(a, 7), 3))
            let code = cat(code, cat(cat(mk(0xF2), mk(0x0F)), cat(cat(mk(0x10), mk(m)), mk(0xCA))))
        }
        if eq(op, 15) {
            let code = cat(code, cat(cat(mk(0xF2), mk(0x0F)), cat(mk(a), mk(b))))
        }
        if eq(op, 16) {
            let modrm = bor(0xC0, bor(bshl(band(a, 7), 3), band(b, 7)))
            let code = cat(code, cat(cat(cat(mk(0xF2), mk(0x0F)), mk(0x10)), mk(modrm)))
        }
        if eq(op, 17) {
            let modrm = bor(0x40, bor(bshl(band(a, 7), 3), 4))
            let code = cat(code, cat(cat(cat(mk(0xF2), mk(0x0F)), cat(mk(0x10), mk(modrm))), cat(mk(0x24), mk(b))))
        }
        if eq(op, 18) {
            let imm = get(CONST, b)
            let rex = bor(0x48, bshr(a, 3))
            let code = cat(code, cat(cat(mk(rex), mk(bor(0xB8, band(a, 7)))), pack64(imm)))
        }
        if eq(op, 19) {
            let rex = bor(0x48, bor(bshl(bshr(a, 3), 2), bshr(b, 3)))
            let modrm = bor(0xC0, bor(bshl(band(a, 7), 3), band(b, 7)))
            let code = cat(code, cat(cat(cat(mk(0x66), mk(rex)), mk(0x0F)), cat(mk(0x6E), mk(modrm))))
        }
    }
    let all = cat(all, cat(pack32(len(code)), code))
}
print(all)
