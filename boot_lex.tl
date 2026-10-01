# boot_lex.tl v5 —— tl 语言写的词法分析器（符号表版）
# 输入：src 字节 tensor；输出：[cls, val, pos, ...]
# cls: 0=标识符/关键字 1=数字 2=符号 3=EOF
# val: 关键字{let:1 for:2 in:3 if:4 else:5 print:6 while:7 break:8}
#      固定符号{9=tensor 10=range 11=eq 12=ge 13=le 14=lt 15=add 16=sub 17=mul
#               18=cat 19=mk 20=get 21=len 22=empty 23=set1 24=get2 25=pack32 26=pack64
#               27=byte 28=band 29=bor 30=bxor 31=bshl 32=bshr 33=update}
#      其他 ID 从 34 动态分配
# 符号表：sym=名字字节拼接，sym_len=各名字长度；id = 索引 + 9

let src = tensor([108,101,116,32,97,61,49,10,35,32,99,111,109,109,101,110,116,10,102,111,114,32,105,32,105,110,32,114,97,110,103,101,40,54,52,41,32,123,10,32,32,108,101,116,32,98,61,116,101,110,115,111,114,40,91,48,120,52,48,44,48,120,52,57,93,41,10,32,32,105,102,32,101,113,40,105,44,48,41,32,123,32,112,114,105,110,116,40,98,41,32,125,32,101,108,115,101,32,123,32,98,114,101,97,107,32,125,10,125,10])
# = "let a=1\n# comment\nfor i in range(64) {\n  let b=tensor([0x40,0x49])\n  if eq(i,0) { print(b) } else { break }\n}\n"

let n = len(src)
let i = 0
let out = empty()
let sym = empty()
let sym_len = empty()
let sym_off = empty()

# ---- 固定符号表（25 个） ----
def add_fixed(buf) {
    global sym sym_len sym_off
    let sym_off = cat(sym_off, mk(len(sym)))
    let sym = cat(sym, buf)
    let sym_len = cat(sym_len, mk(len(buf)))
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
def lookup(buf) {
    global sym sym_len sym_off
    let lk_cnt = len(sym_len)
    let lk_i = 0
    let lk_found = 0
    let lk_fid = 0
    while lt(lk_i, lk_cnt) {
        let lk_L = get(sym_len, lk_i)
        if eq(lk_L, len(buf)) {
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
    let sym_off = cat(sym_off, mk(len(sym)))
    let sym = cat(sym, buf)
    let sym_len = cat(sym_len, mk(len(buf)))
    return add(lk_cnt, 200)
}

# ---- 关键字匹配：返回 1-8，非关键字 0 ----
def kw_id(buf) {
    if eq(len(buf), 3) {
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
    if eq(len(buf), 2) {
        if eq(get(buf, 0), 105) {
            if eq(get(buf, 1), 110) { return 3 }
            if eq(get(buf, 1), 102) { return 4 }
        }
        return 0
    }
    if eq(len(buf), 4) {
        if eq(get(buf, 0), 101) {
            if eq(get(buf, 1), 108) {
                if eq(get(buf, 2), 115) {
                    if eq(get(buf, 3), 101) { return 5 }
                }
            }
        }
        return 0
    }
    if eq(len(buf), 6) {
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
    if eq(len(buf), 5) {
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
                                let out = cat(out, cat(mk(1), cat(mk(val), mk(pos))))
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
                                let out = cat(out, cat(mk(1), cat(mk(val), mk(pos))))
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
                                let out = cat(out, cat(mk(1), cat(mk(val), mk(pos))))
                            }
                            else {
                                if mul(ge(c, 95), le(c, 122)) {
                                    let pos = i
                                    let buf = empty()
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
                                            let buf = cat(buf, mk(d))
                                            let i = add(i, 1)
                                        }
                                        else {
                                            break
                                        }
                                    }
                                    let k = kw_id(buf)
                                    if eq(k, 0) {
                                        let k = lookup(buf)
                                    }
                                    let out = cat(out, cat(mk(0), cat(mk(k), mk(pos))))
                                }
                                else {
                                    if mul(mul(ge(c, 65), le(c, 90)), sub(1, 0)) {
                                        let pos = i
                                        let buf = empty()
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
                                                let buf = cat(buf, mk(d))
                                                let i = add(i, 1)
                                            }
                                            else {
                                                break
                                            }
                                        }
                                        let k = kw_id(buf)
                                        if eq(k, 0) {
                                            let k = lookup(buf)
                                        }
                                        let out = cat(out, cat(mk(0), cat(mk(k), mk(pos))))
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
                                                let out = cat(out, cat(mk(1), cat(mk(sub(0, val)), mk(pos))))
                                            }
                                            else {
                                                let out = cat(out, cat(mk(2), cat(mk(c), mk(i))))
                                                let i = add(i, 1)
                                            }
                                        }
                                        else {
                                            let out = cat(out, cat(mk(2), cat(mk(c), mk(i))))
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

let out = cat(out, cat(mk(3), cat(mk(0), mk(n))))
print(out)
print(sym)
print(sym_len)
