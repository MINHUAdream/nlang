# v0.16 表驱动通用发射器（tl 语言内完成两遍编码）
# 目标：与 tl_emit._gen_single_loop('relu') 逐字节一致（70 字节）
# 指令表 prog：每行 [op, a, b]
#   op: 0=push(reg) 1=mov(dst,src) 2=xor32 3=movsd_ld 4=movsd_st
#       5=pxor(x,y) 6=ucomisd 7=jcc8(cc,label) 8=jmp(label) 9=inc(reg)
#       10=cmp(a,b) 11=pop(reg) 12=ret 13=label(id)
# 注意：jcc 的 a=条件码、b=目标 label；xor 的 a=b=目标寄存器
# 第一遍：按长度表累加位置 + 记录 label 位置
# 第二遍：逐条编码（rel32 = label - (cur + insn_len)，与 tl_emit 同基准）

let prog = tensor([
    [0, 6, 0], [0, 7, 0], [0, 11, 0],
    [1, 6, 1], [1, 7, 2], [1, 11, 8],
    [2, 1, 1],
    [13, 0, 0],
    [3, 0, 0],
    [5, 1, 1],
    [6, 0, 0],
    [7, 6, 1],
    [4, 0, 0],
    [8, 2, 0],
    [13, 1, 0],
    [5, 0, 0],
    [4, 0, 0],
    [13, 2, 0],
    [9, 1, 0],
    [10, 1, 11],
    [7, 12, 0],
    [11, 11, 0], [11, 7, 0], [11, 6, 0],
    [12, 0, 0]
])

# 长度表（op 0..13；push/pop 高寄存器 +1）
let LEN = tensor([1, 3, 2, 5, 5, 4, 4, 6, 5, 3, 3, 1, 1, 0])

# ---- 第一遍：位置表 pos + label 表 lab ----
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
