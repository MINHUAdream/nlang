# v0.19 表驱动发射器 · transpose（转置寻址）
# 与 tl_emit._gen_transpose() 逐字节一致（97 字节）
# ABI: transpose(a,M,N,out): rcx=a rdx=M r8=N r9=out → out[j*M+i]=a[i*N+j]

let prog = tensor([
    [0,6,0,0,0],[0,7,0,0,0],[0,12,0,0,0],[0,13,0,0,0],[0,14,0,0,0],
    [1,6,1,0,0],
    [1,7,9,0,0],
    [1,12,2,0,0],
    [1,13,8,0,0],
    [2,14,14,0,0],
    [13,0,0,0,0],
    [2,1,1,0,0],
    [13,1,0,0,0],
    [1,0,14,0,0],
    [20,0,12,0,0],
    [21,0,1,0,0],
    [22,0,3,0,0],
    [1,8,1,0,0],
    [20,8,13,0,0],
    [21,8,14,0,0],
    [22,8,3,0,0],
    [31,0,6,8,1],
    [32,0,7,0,1],
    [9,1,0,0,0],
    [10,1,12,0,0],
    [7,12,1,0,0],
    [9,14,0,0,0],
    [10,14,13,0,0],
    [7,12,0,0,0],
    [11,14,0,0,0],[11,13,0,0,0],[11,12,0,0,0],[11,7,0,0,0],[11,6,0,0,0],
    [12,0,0,0,0]
])

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
}
print(code)
