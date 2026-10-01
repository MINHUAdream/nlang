# v0.20 表驱动发射器 · softmax（两遍扫描 + exp 多项式 + Neumaier）
# 与 tl_emit._gen_softmax() 逐字节一致
# ABI: softmax(a, rows, cols, out): rcx rdx r8 r9
# op 表扩展（0..45）：
#   34=sub_r64_imm(r,imm32) 48 81 E8+r id32
#   35=movsd_load_xmm_disp(x,base,disp8) F2 [rex] 0F 10 modrm(01,x,4) sib(0,4,base) disp
#   36=movsd_store_xmm_disp(x,base,disp8) F2 [rex] 0F 11 ...
#   40=roundsd(d,s,mode) 66 [rex] 0F 3A 0B modrm(3,d,s) mode
#   41=cvttsd2si(r,x) F2 48.. 0F 2C modrm(3,r,x)
#   42=movabs_imm(r,imm64) 48.. B8+r q64
#   43=cvtsi2sd(x,r) F2 48.. 0F 2A modrm(3,x,r)
#   44=movsd_load_noix(x,base) F2 [rex] 0F 10 modrm(0,x,4) sib(0,4,base)
#   45=movsd_store_noix(x,base) F2 [rex] 0F 11 modrm(0,x,4) sib(0,4,base)
# label: 0=Li 1=Lmax 2=Lmax_done 3=Lmax_next 4=Lexp 5=Lexp_done 6=Ldiv 7=Ldiv_done
#        8=X_done 9=X_ninf 10=X_inf 11=N_0 12=N_nx 13=N_ge
# 寄存器: rsi=6(a) rdi=7(out) rbx=3 r12=12(cols) r13=13(rows) r14=14(r) r15=15(j)
#         rcx=1 rdx=2 r8=8 r11=11(k) rsp=4 rax=0

let prog = tensor([
    [0,6,0,0,0],
    [0,7,0,0,0],
    [0,3,0,0,0],
    [0,12,0,0,0],
    [0,13,0,0,0],
    [0,14,0,0,0],
    [0,15,0,0,0],
    [1,6,1,0,0],
    [1,7,9,0,0],
    [1,12,8,0,0],
    [1,13,2,0,0],
    [34,4,32800,0,0],
    [2,14,14,0,0],
    [13,0,0,0,0],
    [1,0,14,0,0],
    [20,0,12,0,0],
    [22,0,3,0,0],
    [21,0,6,0,0],
    [44,0,0,0,0],
    [2,15,15,0,0],
    [13,1,0,0,0],
    [10,15,12,0,0],
    [7,13,2,0,0],
    [31,1,0,15,8],
    [28,1,0,0,0],
    [7,6,3,0,0],
    [16,0,1,0,0],
    [13,3,0,0,0],
    [9,15,0,0,0],
    [8,1,0,0,0],
    [13,2,0,0,0],
    [36,0,4,8,0],
    [2,15,15,0,0],
    [13,4,0,0,0],
    [10,15,12,0,0],
    [7,13,5,0,0],
    [1,0,14,0,0],
    [20,0,12,0,0],
    [21,0,15,0,0],
    [22,0,3,0,0],
    [21,0,6,0,0],
    [44,0,0,0,0],
    [35,1,4,8,0],
    [15,0x5C,0xC1,0,0],
    [28,0,0,0,0],
    [7,10,8,0,0],
    [26,4,18,0,0],
    [28,0,4,0,0],
    [7,4,8,0,0],
    [26,4,21,0,0],
    [28,0,4,0,0],
    [7,4,9,0,0],
    [16,3,0,0,0],
    [26,1,19,0,0],
    [15,0x59,0xC1,0,0],
    [26,1,17,0,0],
    [15,0x58,0xC1,0,0],
    [40,0,0,1,0],
    [41,0,0,0,0],
    [1,11,0,0,0],
    [42,0,1023,0,0],
    [10,11,0,0,0],
    [7,15,10,0,0],
    [43,1,11,0,0],
    [26,2,20,0,0],
    [15,0x59,0xCA,0,0],
    [16,0,3,0,0],
    [15,0x5C,0xC1,0,0],
    [26,2,1,0,0],
    [15,0x59,0xD0,0,0],
    [26,1,2,0,0],
    [15,0x58,0xD1,0,0],
    [15,0x59,0xD0,0,0],
    [26,1,9,0,0],
    [15,0x58,0xD1,0,0],
    [15,0x59,0xD0,0,0],
    [26,1,10,0,0],
    [15,0x58,0xD1,0,0],
    [15,0x59,0xD0,0,0],
    [26,1,11,0,0],
    [15,0x58,0xD1,0,0],
    [15,0x59,0xD0,0,0],
    [26,1,12,0,0],
    [15,0x58,0xD1,0,0],
    [15,0x59,0xD0,0,0],
    [26,1,13,0,0],
    [15,0x58,0xD1,0,0],
    [15,0x59,0xD0,0,0],
    [26,1,14,0,0],
    [15,0x58,0xD1,0,0],
    [15,0x59,0xD0,0,0],
    [26,1,15,0,0],
    [15,0x58,0xD1,0,0],
    [15,0x59,0xD0,0,0],
    [26,1,16,0,0],
    [15,0x58,0xD1,0,0],
    [15,0x59,0xD0,0,0],
    [26,1,3,0,0],
    [15,0x58,0xD1,0,0],
    [15,0x59,0xD0,0,0],
    [26,1,4,0,0],
    [15,0x58,0xD1,0,0],
    [15,0x59,0xD0,0,0],
    [26,1,5,0,0],
    [15,0x58,0xD1,0,0],
    [15,0x59,0xD0,0,0],
    [26,1,6,0,0],
    [15,0x58,0xD1,0,0],
    [15,0x59,0xD0,0,0],
    [26,1,7,0,0],
    [15,0x58,0xD1,0,0],
    [15,0x59,0xD0,0,0],
    [26,1,8,0,0],
    [15,0x58,0xD1,0,0],
    [15,0x59,0xD0,0,0],
    [26,1,22,0,0],
    [15,0x58,0xD1,0,0],
    [1,0,11,0,0],
    [29,0,1023,0,0],
    [22,0,52,0,0],
    [19,1,0,0,0],
    [15,0x59,0xD1,0,0],
    [16,0,2,0,0],
    [8,8,0,0,0],
    [13,9,0,0,0],
    [5,0,0,0,0],
    [8,8,0,0,0],
    [13,10,0,0,0],
    [26,0,18,0,0],
    [13,8,0,0,0],
    [1,8,15,0,0],
    [22,8,3,0,0],
    [29,8,16,0,0],
    [21,8,4,0,0],
    [45,0,8,0,0],
    [9,15,0,0,0],
    [8,4,0,0,0],
    [13,5,0,0,0],
    [1,3,6,0,0],
    [1,6,4,0,0],
    [29,6,16,0,0],
    [1,1,12,0,0],
    [5,0,0,0,0],
    [5,1,1,0,0],
    [2,2,2,0,0],
    [26,7,0,0,0],
    [13,11,0,0,0],
    [31,2,6,2,8],
    [16,3,0,0,0],
    [15,0x58,0xC2,0,0],
    [16,4,3,0,0],
    [27,4,7,0,0],
    [16,5,2,0,0],
    [27,5,7,0,0],
    [28,4,5,0,0],
    [7,3,13,0,0],
    [16,6,2,0,0],
    [15,0x5C,0xF0,0,0],
    [15,0x58,0xF3,0,0],
    [15,0x58,0xCE,0,0],
    [8,12,0,0,0],
    [13,13,0,0,0],
    [16,6,3,0,0],
    [15,0x5C,0xF0,0,0],
    [15,0x58,0xF2,0,0],
    [15,0x58,0xCE,0,0],
    [13,12,0,0,0],
    [9,2,0,0,0],
    [10,2,1,0,0],
    [7,12,11,0,0],
    [15,0x58,0xC1,0,0],
    [1,6,3,0,0],
    [2,15,15,0,0],
    [13,6,0,0,0],
    [10,15,12,0,0],
    [7,13,7,0,0],
    [1,3,15,0,0],
    [22,3,3,0,0],
    [29,3,16,0,0],
    [21,3,4,0,0],
    [44,1,3,0,0],
    [15,0x5E,0xC8,0,0],
    [1,0,14,0,0],
    [20,0,12,0,0],
    [21,0,15,0,0],
    [22,0,3,0,0],
    [32,1,7,0,1],
    [9,15,0,0,0],
    [8,6,0,0,0],
    [13,7,0,0,0],
    [9,14,0,0,0],
    [10,14,13,0,0],
    [7,12,0,0,0],
    [29,4,32800,0,0],
    [11,15,0,0,0],
    [11,14,0,0,0],
    [11,13,0,0,0],
    [11,12,0,0,0],
    [11,3,0,0,0],
    [11,7,0,0,0],
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

let LEN = tensor([1,3,2,5,5,4,4,6,5,3,3,1,1,0,5,4,4,4,10,5,4,3,4,5,5,5,8,4,4,7,3,5,5,8,7,6,6,0,0,0,6,5,10,5,5,5])

let pos = tensor([0])
let lab = tensor([-1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1, -1])
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
        if eq(op, 35) {
            if ge(a, 8) { let L = add(L, 1) }
            if ge(get2(prog, i, 2), 8) { let L = add(L, 1) }
        }
        if eq(op, 36) {
            if ge(a, 8) { let L = add(L, 1) }
            if ge(get2(prog, i, 2), 8) { let L = add(L, 1) }
        }
        if eq(op, 40) {
            if ge(a, 8) { let L = add(L, 1) }
            if ge(get2(prog, i, 2), 8) { let L = add(L, 1) }
        }
        if eq(op, 44) {
            if ge(get2(prog, i, 2), 8) { let L = add(L, 1) }
        }
        if eq(op, 45) {
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
    let PROBE = tensor([0, 0, 0, 0])
    if eq(i, 31) { let PROBE = set1(PROBE, 0, get2(prog, i, 1)) }
    if eq(i, 31) { let PROBE = set1(PROBE, 1, get2(prog, i, 0)) }
    if eq(i, 31) { let PROBE = set1(PROBE, 2, add(get2(prog, i, 2), 100)) }
    if eq(i, 31) { let PROBE = set1(PROBE, 3, add(get2(prog, i, 3), 200)) }
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
    if eq(op, 19) {
        let rex = bor(0x48, bor(bshl(bshr(a, 3), 2), bshr(b, 3)))
        let modrm = bor(0xC0, bor(bshl(band(a, 7), 3), band(b, 7)))
        let code = cat(code, cat(cat(cat(cat(mk(0x66), mk(rex)), mk(0x0F)), mk(0x6E)), mk(modrm)))
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
    if eq(op, 34) {
        let rex = bor(0x48, bshr(a, 3))
        let code = cat(code, cat(cat(cat(mk(rex), mk(0x81)), mk(bor(0xE8, band(a, 7)))), pack32(b)))
    }

    if eq(op, 35) {
        let rex = bor(bshl(bshr(a, 3), 2), bshr(b, 3))
        let modrm = bor(0x40, bor(bshl(band(a, 7), 3), 4))
        let sib = bor(0x20, band(b, 7))
        if eq(rex, 0) {
            let code = cat(code, cat(cat(cat(mk(0xF2), mk(0x0F)), cat(cat(mk(0x10), mk(modrm)), mk(sib))), mk(c)))
        } else {
            let code = cat(code, cat(cat(cat(cat(mk(0xF2), mk(rex)), mk(0x0F)), cat(cat(mk(0x10), mk(modrm)), mk(sib))), mk(c)))
        }
    }

    if eq(op, 36) {
        let rex = bor(bshl(bshr(a, 3), 2), bshr(b, 3))
        let modrm = bor(0x40, bor(bshl(band(a, 7), 3), 4))
        let sib = bor(0x20, band(b, 7))
        if eq(rex, 0) {
            let code = cat(code, cat(cat(cat(mk(0xF2), mk(0x0F)), cat(cat(mk(0x11), mk(modrm)), mk(sib))), mk(c)))
        } else {
            let code = cat(code, cat(cat(cat(cat(mk(0xF2), mk(rex)), mk(0x0F)), cat(cat(mk(0x11), mk(modrm)), mk(sib))), mk(c)))
        }
    }

    if eq(op, 40) {
        let rex = bor(bshl(bshr(a, 3), 2), bshr(b, 3))
        let modrm = bor(0xC0, bor(bshl(band(a, 7), 3), band(b, 7)))
        if eq(rex, 0) {
            let code = cat(code, cat(cat(cat(mk(0x66), mk(0x0F)), cat(cat(mk(0x3A), mk(0x0B)), mk(modrm))), mk(c)))
        } else {
            let code = cat(code, cat(cat(cat(cat(mk(0x66), mk(rex)), mk(0x0F)), cat(cat(mk(0x3A), mk(0x0B)), mk(modrm))), mk(c)))
        }
    }

    if eq(op, 41) {
        let rex = bor(0x48, bor(bshl(bshr(a, 3), 2), bshr(b, 3)))
        let modrm = bor(0xC0, bor(bshl(band(a, 7), 3), band(b, 7)))
        let code = cat(code, cat(cat(cat(mk(0xF2), mk(rex)), mk(0x0F)), cat(mk(0x2C), mk(modrm))))
    }

    if eq(op, 42) {
        let rex = bor(0x48, bshr(a, 3))
        let code = cat(code, cat(cat(mk(rex), mk(bor(0xB8, band(a, 7)))), pack64(b)))
    }

    if eq(op, 43) {
        let rex = bor(0x48, bor(bshl(bshr(a, 3), 2), bshr(b, 3)))
        let modrm = bor(0xC0, bor(bshl(band(a, 7), 3), band(b, 7)))
        let code = cat(code, cat(cat(cat(mk(0xF2), mk(rex)), mk(0x0F)), cat(mk(0x2A), mk(modrm))))
    }

    if eq(op, 44) {
        let rex = bor(0x40, bor(bshl(bshr(a, 3), 2), bshr(b, 3)))
        let modrm = bor(bshl(band(a, 7), 3), 4)
        let sib = bor(0x20, band(b, 7))
        if eq(rex, 0x40) {
            let code = cat(code, cat(cat(mk(0xF2), mk(0x0F)), cat(cat(mk(0x10), mk(modrm)), mk(sib))))
        } else {
            let code = cat(code, cat(cat(cat(mk(0xF2), mk(rex)), mk(0x0F)), cat(cat(mk(0x10), mk(modrm)), mk(sib))))
        }
    }

    if eq(op, 45) {
        let rex = bor(0x40, bor(bshl(bshr(a, 3), 2), bshr(b, 3)))
        let modrm = bor(bshl(band(a, 7), 3), 4)
        let sib = bor(0x20, band(b, 7))
        if eq(rex, 0x40) {
            let code = cat(code, cat(cat(mk(0xF2), mk(0x0F)), cat(cat(mk(0x11), mk(modrm)), mk(sib))))
        } else {
            let code = cat(code, cat(cat(cat(mk(0xF2), mk(rex)), mk(0x0F)), cat(cat(mk(0x11), mk(modrm)), mk(sib))))
        }
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
