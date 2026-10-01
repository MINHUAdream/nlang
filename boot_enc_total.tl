# v0.19 表驱动发射器 · total（Neumaier 行规约）
# 与 tl_emit._gen_total() 逐字节一致（311 字节）
# ABI: total(x, n, ...): rcx=x rdx=n → xmm0
# op 表扩展：
#   26=movsd_load_xmm_rip(dst,const_id) F2 0F 10 modrm(0,dst,5) rel32(数据段补丁)
#   27=andpd(d,s) 66 0F 54 modrm(3,d,s)
#   28=ucomisd(d,s) 66 0F 2E modrm(3,d,s)
#   29=add_r64_imm(r,imm32) 48 81 C0+r id32
#   30=sub_r64_r64(d,s) 48 29 modrm(3,s,d)
#   31=movsd_load_xmm_sib(dst,base,idx,scale) F2 [rex] 0F 10 modrm(0,dst,4) sib
#   32=movsd_store_xmm_sib(src,base,idx,scale) F2 [rex] 0F 11 modrm(0,src,4) sib
#   33=data64(const_id) 8 字节常量（数据段）
# 表格式：5 列 [op,a,b,c,d]

let prog = tensor([
    [0,6,0,0,0],
    [1,6,1,0,0],
    [1,1,2,0,0],
    [5,0,0,0,0],
    [5,1,1,0,0],
    [2,2,2,0,0],
    [26,7,0,0,0],
    [13,0,0,0,0],
    [31,2,6,2,8],
    [16,3,0,0,0],
    [15,0x58,0xC2,0,0],
    [16,4,3,0,0],
    [27,4,7,0,0],
    [16,5,2,0,0],
    [27,5,7,0,0],
    [28,4,5,0,0],
    [7,3,1,0,0],
    [16,6,2,0,0],
    [15,0x5C,0xF0,0,0],
    [15,0x58,0xF3,0,0],
    [15,0x58,0xCE,0,0],
    [8,2,0,0,0],
    [13,1,0,0,0],
    [16,6,3,0,0],
    [15,0x5C,0xF0,0,0],
    [15,0x58,0xF2,0,0],
    [15,0x58,0xCE,0,0],
    [13,2,0,0,0],
    [9,2,0,0,0],
    [10,2,1,0,0],
    [7,12,0,0,0],
    [15,0x58,0xC1,0,0],
    [11,6,0,0,0],
    [12,0,0,0,0],
    [33,0,0,0,0],
    [33,1,0,0,0],
    [33,2,0,0,0],
    [33,3,0,0,0],
    [33,4,0,0,0],
    [33,5,0,0,0],
    [33,6,0,0,0],
    [33,7,0,0,0],
    [33,8,0,0,0],
    [33,9,0,0,0],
    [33,10,0,0,0],
    [33,11,0,0,0],
    [33,12,0,0,0],
    [33,13,0,0,0],
    [33,14,0,0,0],
    [33,15,0,0,0],
    [33,16,0,0,0],
    [33,17,0,0,0],
    [33,18,0,0,0],
    [33,19,0,0,0],
    [33,20,0,0,0],
    [33,21,0,0,0],
    [33,22,0,0,0],
    [33,23,0,0,0]
])

# 24 个常数（sorted(_DB) 顺序）
let CONST = tensor([0x7FFFFFFFFFFFFFFF, 0x3D2AE7F3E733B81F, 0x3D6AE7F3E733B81F,
                    0x3F56C16C16C16C17, 0x3F81111111111111, 0x3FA5555555555555,
                    0x3FC5555555555555, 0x3FE0000000000000, 0x3FF0000000000000,
                    0x3DA93974A8C07C9D, 0x3DE6124613A86D09, 0x3E21EED8EFF8D898,
                    0x3E5AE64567F544E4, 0x3E927E4FB7789F5C, 0x3EC71DE3A556C734,
                    0x3EFA01A01A01A01A, 0x3F2A01A01A01A01A, 0x3FE0000000000000,
                    0x7FF0000000000000, 0x3FF71547652B82FE, 0x3FE62E42FEFA39EF,
                    0xFFF0000000000000, 0x3FF0000000000000, 0x8000000000000000])

let LEN = tensor([1,3,2,5,5,4,4,6,5,3,3,1,1,0,5,4,4,6,10,5,4,3,4,5,5,5,8,4,4,7,3,5,5,8])

let pos = tensor([0])
let lab = tensor([-1, -1, -1, -1, -1, -1])
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
        if eq(op, 31) {
            if ge(get2(prog, i, 3), 8) { let L = add(L, 1) }
            if ge(get2(prog, i, 2), 8) { let L = add(L, 1) }
        }
        if eq(op, 32) {
            if ge(get2(prog, i, 3), 8) { let L = add(L, 1) }
            if ge(get2(prog, i, 2), 8) { let L = add(L, 1) }
        }
        let pos = cat(pos, mk(add(cur, L)))
    }
}

let code = empty()
let dp = tensor([-1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1,
                 -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1])
let rfx_p = empty()
let rfx_c = empty()
for i in range(len(prog)) {
    let op = get2(prog, i, 0)
    let a = get2(prog, i, 1)
    let b = get2(prog, i, 2)
    let c = get2(prog, i, 3)
    let d = get2(prog, i, 4)
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
        let modrm = bor(0xC0, bor(bshl(band(a, 7), 3), band(b, 7)))
        let code = cat(code, cat(cat(mk(0x66), mk(0x0F)), cat(mk(0xEF), mk(modrm))))
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
    if eq(op, 16) {
        let modrm = bor(0xC0, bor(bshl(band(a, 7), 3), band(b, 7)))
        let code = cat(code, cat(cat(cat(mk(0xF2), mk(0x0F)), mk(0x10)), mk(modrm)))
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
    if eq(op, 26) {
        let modrm = bor(bshl(band(a, 7), 3), 5)
        let code = cat(code, cat(cat(mk(0xF2), mk(0x0F)), cat(cat(mk(0x10), mk(modrm)), pack32(0))))
        let rfx_p = cat(rfx_p, mk(sub(len(code), 8)))
        let rfx_c = cat(rfx_c, mk(b))
    }
    if eq(op, 27) {
        let modrm = bor(0xC0, bor(bshl(band(a, 7), 3), band(b, 7)))
        let code = cat(code, cat(cat(mk(0x66), mk(0x0F)), cat(mk(0x54), mk(modrm))))
    }
    if eq(op, 28) {
        let modrm = bor(0xC0, bor(bshl(band(a, 7), 3), band(b, 7)))
        let code = cat(code, cat(cat(mk(0x66), mk(0x0F)), cat(mk(0x2E), mk(modrm))))
    }
    if eq(op, 29) {
        let rex = bor(0x48, bshr(a, 3))
        let code = cat(code, cat(cat(mk(rex), mk(bor(0x81, 0))), cat(mk(bor(0xC0, band(a, 7))), pack32(b))))
    }
    if eq(op, 30) {
        let rex = bor(0x48, bor(bshl(bshr(b, 3), 2), bshr(a, 3)))
        let modrm = bor(0xC0, bor(bshl(band(b, 7), 3), band(a, 7)))
        let code = cat(code, cat(cat(mk(rex), mk(0x29)), mk(modrm)))
    }
    if eq(op, 31) {
        let rex = bor(0x40, bor(bshl(bshr(c, 3), 1), bshr(b, 3)))
        let modrm = bor(bshl(band(a, 7), 3), 4)
        let sc = 0
        if eq(d, 1) { let sc = 0 }
        if eq(d, 2) { let sc = 1 }
        if eq(d, 4) { let sc = 2 }
        if eq(d, 8) { let sc = 3 }
        let sib = bor(bshl(sc, 6), bor(bshl(band(c, 7), 3), band(b, 7)))
        if eq(rex, 0x40) {
            let code = cat(code, cat(cat(mk(0xF2), mk(0x0F)), cat(cat(mk(0x10), mk(modrm)), mk(sib))))
        } else {
            let code = cat(code, cat(cat(cat(mk(0xF2), mk(rex)), mk(0x0F)), cat(cat(mk(0x10), mk(modrm)), mk(sib))))
        }
    }
    if eq(op, 32) {
        let rex = bor(0x40, bor(bshl(bshr(c, 3), 1), bshr(b, 3)))
        let modrm = bor(bshl(band(a, 7), 3), 4)
        let sc = 0
        if eq(d, 1) { let sc = 0 }
        if eq(d, 2) { let sc = 1 }
        if eq(d, 4) { let sc = 2 }
        if eq(d, 8) { let sc = 3 }
        let sib = bor(bshl(sc, 6), bor(bshl(band(c, 7), 3), band(b, 7)))
        if eq(rex, 0x40) {
            let code = cat(code, cat(cat(mk(0xF2), mk(0x0F)), cat(cat(mk(0x11), mk(modrm)), mk(sib))))
        } else {
            let code = cat(code, cat(cat(cat(mk(0xF2), mk(rex)), mk(0x0F)), cat(cat(mk(0x11), mk(modrm)), mk(sib))))
        }
    }
    if eq(op, 33) {
        let dp = set1(dp, a, len(code))
        let code = cat(code, pack64(get(CONST, a)))
    }
}

# 第三遍：RIP 相对补丁（rel = data_pos - (patch_pos + 8)）
for j in range(len(rfx_p)) {
    let pp = get(rfx_p, j)
    let rel = sub(get(dp, get(rfx_c, j)), add(pp, 8))
    let code = set1(code, add(pp, 4), band(rel, 0xFF))
    let code = set1(code, add(pp, 5), band(bshr(rel, 8), 0xFF))
    let code = set1(code, add(pp, 6), band(bshr(rel, 16), 0xFF))
    let code = set1(code, add(pp, 7), band(bshr(rel, 24), 0xFF))
}
print(code)
