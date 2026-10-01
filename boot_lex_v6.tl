# boot_lex.tl v6 —— set1 原地写版（根治宿主 O(n²) cat 累积）
# 语义与 v5 完全一致：输出 toks/sym/sym_len 逐字节相同；仅把累积策略
# 从"cat 整体复制"改为"预分配 range 数组 + set1 原地写 + 指针"。
# 输入：src 字节 tensor；输出：[cls, val, pos, ...]
# cls: 0=标识符/关键字 1=数字 2=符号 3=EOF

let src = ext_in(0)
# = "let a=1\n"（占位，由 _inject_src_tensor 注入真实源码）

let n = len(src)
let i = 0
# 预分配（值会被覆盖）：out=token 三元组槽，sym=名字字节池，
# sym_off/sym_len=符号表偏移与长度，buf=标识符读取缓冲
let out = range(300000)
let out_n = 0
let sym = range(200000)
let sym_n = 0
let sym_off = range(5000)
let sym_len = range(5000)
let sym_cnt = 0
let buf = range(256)

# ---- 发射一个 token 三元组（原地写） ----
def emit_tok(a, b, c) {
    global out
    global out_n
    let out = set1(out, mul(out_n, 3), a)
    let out = set1(out, add(mul(out_n, 3), 1), b)
    let out = set1(out, add(mul(out_n, 3), 2), c)
    let out_n = add(out_n, 1)
    return 0
}

# ---- 固定符号表（31 个） ----
def add_fixed(buf) {
    global sym
    global sym_len
    global sym_off
    global sym_cnt
    global sym_n
    let sym_off = set1(sym_off, sym_cnt, sym_n)
    let sym = set1(sym, sym_n, 0)
    let k = 0
    while lt(k, len(buf)) {
        let sym = set1(sym, add(sym_n, k), get(buf, k))
        let k = add(k, 1)
    }
    let sym_len = set1(sym_len, sym_cnt, len(buf))
    let sym_n = add(sym_n, len(buf))
    let sym_cnt = add(sym_cnt, 1)
    return 0
}
let _f1 = add_fixed(tensor([116,101,110,115,111,114]))   # tensor -> 9
let _f2 = add_fixed(tensor([114,97,110,103,101]))         # range -> 10
let _f3 = add_fixed(tensor([101,113]))                    # eq -> 11
let _f4 = add_fixed(tensor([103,101]))                    # ge -> 12
let _f5 = add_fixed(tensor([108,101]))                    # le -> 13
let _f6 = add_fixed(tensor([108,116]))                    # lt -> 14
let _f7 = add_fixed(tensor([97,100,100]))                 # add -> 15
let _f8 = add_fixed(tensor([115,117,98]))                 # sub -> 16
let _f9 = add_fixed(tensor([109,117,108]))                # mul -> 17
let _f10 = add_fixed(tensor([99,97,116]))                  # cat -> 18
let _f11 = add_fixed(tensor([109,107]))                    # mk -> 19
let _f12 = add_fixed(tensor([103,101,116]))                # get -> 20
let _f13 = add_fixed(tensor([108,101,110]))                # len -> 21
let _f14 = add_fixed(tensor([101,109,112,116,121]))        # empty -> 22
let _f15 = add_fixed(tensor([115,101,116,49]))             # set1 -> 23
let _f16 = add_fixed(tensor([103,101,116,50]))             # get2 -> 24
let _f17 = add_fixed(tensor([112,97,99,107,51,50]))        # pack32 -> 25
let _f18 = add_fixed(tensor([112,97,99,107,54,52]))        # pack64 -> 26
let _f19 = add_fixed(tensor([98,121,116,101]))             # byte -> 27
let _f20 = add_fixed(tensor([98,97,110,100]))              # band -> 28
let _f21 = add_fixed(tensor([98,111,114]))                 # bor -> 29
let _f22 = add_fixed(tensor([98,120,111,114]))             # bxor -> 30
let _f23 = add_fixed(tensor([98,115,104,108]))             # bshl -> 31
let _f24 = add_fixed(tensor([98,115,104,114]))             # bshr -> 32
let _f25 = add_fixed(tensor([117,112,100,97,116,101]))     # update -> 36
let _f26 = add_fixed(tensor([100,105,118]))                    # div -> 37
let _f27 = add_fixed(tensor([109,111,100]))                    # mod -> 38
let _f28 = add_fixed(tensor([101,120,116,95,105,110]))          # ext_in -> 39
let _f29 = add_fixed(tensor([100,98,108,54,52]))          # dbl64 -> 40
  add_fixed(tensor([103,116]))                    # gt -> 41
  add_fixed(tensor([97,112,112]))                  # app -> 42

# ---- 符号表查找/追加：返回 id（9+索引） ----
def lookup(buf, b_len) {
    global sym
    global sym_len
    global sym_off
    global sym_cnt
    global sym_n
    let lk_cnt = sym_cnt
    let lk_i = 0
    let lk_found = 0
    let lk_fid = 0
    while lt(lk_i, lk_cnt) {
        let lk_L = get(sym_len, lk_i)
        if eq(lk_L, b_len) {
            let lk_off = get(sym_off, lk_i)
            let lk_j = 0
            let lk_same = 1
            while lt(lk_j, lk_L) {
                if sub(1, eq(get(sym, add(lk_off, lk_j)), get(buf, lk_j))) {
                    let lk_same = 0
                }
                let lk_j = add(lk_j, 1)
            }
            if eq(lk_same, 1) {
                let lk_found = 1
                if lt(lk_i, 31) {
                    let lk_fid = add(lk_i, 12)
                } else {
                    let lk_fid = add(lk_i, 200)
                }
            }
        }
        let lk_i = add(lk_i, 1)
    }
    if eq(lk_found, 1) {
        return lk_fid
    }
    let sym_off = set1(sym_off, sym_cnt, sym_n)
    let sym = set1(sym, sym_n, 0)
    let k = 0
    while lt(k, b_len) {
        let sym = set1(sym, add(sym_n, k), get(buf, k))
        let k = add(k, 1)
    }
    let sym_len = set1(sym_len, sym_cnt, b_len)
    let sym_n = add(sym_n, b_len)
    let sym_cnt = add(sym_cnt, 1)
    return add(lk_cnt, 200)
}

# ---- 关键字匹配：返回 1-11，非关键字 0 ----
def kw_id(buf, b_len) {
    if eq(b_len, 3) {
        if eq(get(buf, 0), 108) {
            if eq(get(buf, 1), 101) {
                if eq(get(buf, 2), 116) { return 1 }
            }
        }
        if eq(get(buf, 0), 102) {
            if eq(get(buf, 1), 111) {
                if eq(get(buf, 2), 114) { return 2 }
            }
        }
        if eq(get(buf, 0), 100) {
            if eq(get(buf, 1), 101) {
                if eq(get(buf, 2), 102) { return 9 }
            }
        }
        return 0
    }
    if eq(b_len, 2) {
        if eq(get(buf, 0), 105) {
            if eq(get(buf, 1), 110) { return 3 }
            if eq(get(buf, 1), 102) { return 4 }
        }
        return 0
    }
    if eq(b_len, 4) {
        if eq(get(buf, 0), 101) {
            if eq(get(buf, 1), 108) {
                if eq(get(buf, 2), 115) {
                    if eq(get(buf, 3), 101) { return 5 }
                }
            }
        }
        return 0
    }
    if eq(b_len, 6) {
        if eq(get(buf, 0), 114) {
            if eq(get(buf, 1), 101) {
                if eq(get(buf, 2), 116) {
                    if eq(get(buf, 3), 117) {
                        if eq(get(buf, 4), 114) {
                            if eq(get(buf, 5), 110) { return 10 }
                        }
                    }
                }
            }
        }
        if eq(get(buf, 0), 103) {
            if eq(get(buf, 1), 108) {
                if eq(get(buf, 2), 111) {
                    if eq(get(buf, 3), 98) {
                        if eq(get(buf, 4), 97) {
                            if eq(get(buf, 5), 108) { return 11 }
                        }
                    }
                }
            }
        }
        return 0
    }
    if eq(b_len, 5) {
        if eq(get(buf, 0), 112) {
            if eq(get(buf, 1), 114) {
                if eq(get(buf, 2), 105) {
                    if eq(get(buf, 3), 110) {
                        if eq(get(buf, 4), 116) { return 6 }
                    }
                }
            }
        }
        if eq(get(buf, 0), 119) {
            if eq(get(buf, 1), 104) {
                if eq(get(buf, 2), 105) {
                    if eq(get(buf, 3), 108) {
                        if eq(get(buf, 4), 101) { return 7 }
                    }
                }
            }
        }
        if eq(get(buf, 0), 98) {
            if eq(get(buf, 1), 114) {
                if eq(get(buf, 2), 101) {
                    if eq(get(buf, 3), 97) {
                        if eq(get(buf, 4), 107) { return 8 }
                    }
                }
            }
        }
        return 0
    }
    return 0
}

# ---- 读取一个标识符到 buf，返回其长度 ----
def read_ident() {
    global buf
    global i
    global src
    global n
    let b_n = 0
    while lt(i, n) {
        let d = get(src, i)
        let okd = 0
        if mul(ge(d, 97), le(d, 122)) {
            let okd = 1
        }
        else {
            if mul(ge(d, 65), le(d, 90)) {
                let okd = 1
            }
            else {
                if mul(ge(d, 48), le(d, 57)) {
                    let okd = 1
                }
                else {
                    if eq(d, 95) {
                        let okd = 1
                    }
                    else {
                        let okd = 0
                    }
                }
            }
        }
        if eq(okd, 1) {
            let buf = set1(buf, b_n, d)
            let b_n = add(b_n, 1)
            let i = add(i, 1)
        }
        else {
            break
        }
    }
    return b_n
}

# ---- 主循环 ----
while lt(i, n) {
    let c = get(src, i)
    if eq(c, 32) {
        let i = add(i, 1)
    }
    else {
        if eq(c, 9) {
            let i = add(i, 1)
        }
        else {
            if eq(c, 10) {
                let i = add(i, 1)
            }
            else {
                if eq(c, 13) {
                    let i = add(i, 1)
                }
                else {
                    if eq(c, 35) {
                        while mul(lt(i, n), sub(1, eq(get(src, i), 10))) {
                            let i = add(i, 1)
                        }
                    }
                    else {
                        if eq(c, 48) {
                            if mul(lt(add(i, 1), n), eq(get(src, add(i, 1)), 120)) {
                                let i = add(i, 2)
                                let val = 0
                                let pos = sub(i, 2)
                                while lt(i, n) {
                                    let d = get(src, i)
                                    let okd = 0
                                    if mul(ge(d, 48), le(d, 57)) {
                                        let okd = 1
                                    }
                                    else {
                                        if mul(ge(d, 97), le(d, 102)) {
                                            let okd = 1
                                        }
                                        else {
                                            if mul(ge(d, 65), le(d, 70)) {
                                                let okd = 1
                                            }
                                            else {
                                                let okd = 0
                                            }
                                        }
                                    }
                                    if eq(okd, 1) {
                                        let dv = 0
                                        if ge(d, 97) {
                                            let dv = sub(d, 87)
                                        }
                                        else {
                                            if ge(d, 65) {
                                                let dv = sub(d, 55)
                                            }
                                            else {
                                                let dv = sub(d, 48)
                                            }
                                        }
                                        let val = add(mul(val, 16), dv)
                                        let i = add(i, 1)
                                    }
                                    else {
                                        break
                                    }
                                }
                                let _r = emit_tok(1, val, pos)
                            }
                            else {
                                let val = 0
                                let pos = i
                                while mul(ge(get(src, i), 48), le(get(src, i), 57)) {
                                    let val = add(mul(val, 10), sub(get(src, i), 48))
                                    let i = add(i, 1)
                                }
                                if eq(get(src, i), 46) {
                                    if mul(ge(get(src, add(i, 1)), 48), le(get(src, add(i, 1)), 57)) {
                                        let i = add(i, 1)
                                        let scale = 10
                                        while mul(ge(get(src, i), 48), le(get(src, i), 57)) {
                                            let val = add(val, div(sub(get(src, i), 48), scale))
                                            let scale = mul(scale, 10)
                                            let i = add(i, 1)
                                        }
                                    }
                                }
                                let _r = emit_tok(1, val, pos)
                            }
                        }
                        else {
                            if mul(ge(c, 49), le(c, 57)) {
                                let val = 0
                                let pos = i
                                while mul(ge(get(src, i), 48), le(get(src, i), 57)) {
                                    let val = add(mul(val, 10), sub(get(src, i), 48))
                                    let i = add(i, 1)
                                }
                                if eq(get(src, i), 46) {
                                    if mul(ge(get(src, add(i, 1)), 48), le(get(src, add(i, 1)), 57)) {
                                        let i = add(i, 1)
                                        let scale = 10
                                        while mul(ge(get(src, i), 48), le(get(src, i), 57)) {
                                            let val = add(val, div(sub(get(src, i), 48), scale))
                                            let scale = mul(scale, 10)
                                            let i = add(i, 1)
                                        }
                                    }
                                }
                                let _r = emit_tok(1, val, pos)
                            }
                            else {
                                if mul(ge(c, 95), le(c, 122)) {
                                    let pos = i
                                    let b_len = read_ident()
                                    let k = kw_id(buf, b_len)
                                    if eq(k, 0) {
                                        let k = lookup(buf, b_len)
                                    }
                                    let _r = emit_tok(0, k, pos)
                                }
                                else {
                                    if mul(mul(ge(c, 65), le(c, 90)), sub(1, 0)) {
                                        let pos = i
                                        let b_len = read_ident()
                                        let k = kw_id(buf, b_len)
                                        if eq(k, 0) {
                                            let k = lookup(buf, b_len)
                                        }
                                        let _r = emit_tok(0, k, pos)
                                    }
                                    else {
                                        if eq(c, 45) {
                                            if mul(ge(get(src, add(i, 1)), 48), le(get(src, add(i, 1)), 57)) {
                                                let pos = i
                                                let i = add(i, 1)
                                                let val = 0
                                                while mul(ge(get(src, i), 48), le(get(src, i), 57)) {
                                                    let val = add(mul(val, 10), sub(get(src, i), 48))
                                                    let i = add(i, 1)
                                                }
                                                let _r = emit_tok(1, sub(0, val), pos)
                                            }
                                            else {
                                                let _r = emit_tok(2, c, i)
                                                let i = add(i, 1)
                                            }
                                        }
                                        else {
                                            let _r = emit_tok(2, c, i)
                                            let i = add(i, 1)
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

let _r = emit_tok(3, 0, n)

# ---- 压缩输出：out[0, out_n*3) → out_f ----
let out_f = range(mul(out_n, 3))
let k = 0
while lt(k, mul(out_n, 3)) {
    let out_f = set1(out_f, k, get(out, k))
    let k = add(k, 1)
}
let sym_f = range(sym_n)
let k = 0
while lt(k, sym_n) {
    let sym_f = set1(sym_f, k, get(sym, k))
    let k = add(k, 1)
}
let sym_len_f = range(sym_cnt)
let k = 0
while lt(k, sym_cnt) {
    let sym_len_f = set1(sym_len_f, k, get(sym_len, k))
    let k = add(k, 1)
}
print(out_f)
print(sym_f)
print(sym_len_f)
