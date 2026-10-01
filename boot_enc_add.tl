# v0.16 表驱动通用发射器 · add 内核版（换表即换内核）
# 与 tl_emit._gen_single_loop('add') 逐字节一致（51 字节）
# op 表扩展：14=movsd_ld2(xmm1=[rdx+rcx*8]) 15=arith(F2 0F op modrm)
# ABI: add(a, b, out, n): rcx=a rdx=b r8=out r9=n

let prog = tensor([
    [0, 6, 0], [0, 7, 0], [0, 11, 0],
    [1, 6, 1], [1, 7, 8], [1, 11, 9],
    [2, 1, 1],
    [13, 0, 0],
    [3, 0, 0],
    [14, 0, 0],
    [15, 0x58, 0],
    [4, 0, 0],
    [9, 1, 0],
    [10, 1, 11],
    [7, 12, 0],
    [11, 11, 0], [11, 7, 0], [11, 6, 0],
    [12, 0, 0]
])

let LEN = tensor([1, 3, 2, 5, 5, 4, 4, 6, 5, 3, 3, 1, 1, 0, 5, 4])

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

let code = empty()
for i in range(len(prog)) {
    let op = get2(prog, i, 0)
    let a = get2(prog, i, 1)
    let b = get2(prog, i, 2)
    let cur = get(pos, i)
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
        let code = cat(code, tensor([0xF2, 0x0F, 0x10, 0x04, 0xCE]))
    }
    if eq(op, 14) {
        let code = cat(code, tensor([0xF2, 0x0F, 0x10, 0x0C, 0xCA]))
    }
    if eq(op, 15) {
        let code = cat(code, cat(cat(mk(0xF2), mk(0x0F)), cat(mk(a), mk(0xC1))))
    }
    if eq(op, 4) {
        let code = cat(code, tensor([0xF2, 0x0F, 0x11, 0x04, 0xCF]))
    }
    if eq(op, 5) {
        let modrm = bor(0xC0, bor(bshl(band(b, 7), 3), band(a, 7)))
        let code = cat(code, cat(cat(mk(0x66), mk(0x0F)), cat(mk(0xEF), mk(modrm))))
    }
    if eq(op, 6) {
        let code = cat(code, tensor([0x66, 0x0F, 0x2E, 0xC1]))
    }
    if eq(op, 7) {
        let rel = sub(get(lab, b), add(cur, 6))
        let code = cat(code, cat(cat(mk(0x0F), mk(bor(0x80, a))), pack32(rel)))
    }
    if eq(op, 8) {
        let rel = sub(get(lab, a), add(cur, 5))
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
}
print(code)
