# bal3.tl —— 平衡三进制（balanced ternary）库，tl 语言自写
# trit ∈ {-1, 0, 1}；数组低位在前（trit[0] = 3^0 位）
#
# 为什么是平衡三进制（不是 0/1/2 普通三进制）：
#   · 负数直接表示，无符号位（-5 = 1·1 + 1·3 + -1·9）
#   · 舍入对称：1/2 舍入无偏差
#   · 加法表对称：1+1 → 本位-1 进位1（2 = 3-1）
#
# 算法：x = q·3 + r（r ∈ {0,1,2}，floor 语义）
#   r = 2 → 本位 -1，q 进位 +1（2 = 3 - 1）
#   r = 1 → 本位  1
#   r = 0 → 本位  0

# ---- 十进制 → 平衡三进制 trit 数组（低位在前）----
def to_bal3(x) {
    let out = empty()
    while sub(1, eq(x, 0)) {
        let r = mod(x, 3)
        if eq(r, 2) {
            let out = cat(out, mk(sub(0, 1)))
            let x = add(div(x, 3), 1)
        }
        else {
            let out = cat(out, mk(r))
            let x = div(x, 3)
        }
    }
    return out
}

# ---- trit 数组（低位在前）→ 十进制 ----
def from_bal3(t) {
    let n = len(t)
    let i = 0
    let val = 0
    let p = 1
    while lt(i, n) {
        let val = add(val, mul(get(t, i), p))
        let p = mul(p, 3)
        let i = add(i, 1)
    }
    return val
}

# ---- 单个 trit 相加（含进位）：返回 [本位, 进位] ----
def trit_add(a, b, c) {
    let s = add(add(a, b), c)
    if eq(s, 2) {
        return cat(mk(sub(0, 1)), mk(1))
    }
    if eq(s, sub(0, 2)) {
        return cat(mk(1), mk(sub(0, 1)))
    }
    if eq(s, 3) {
        return cat(mk(0), mk(1))
    }
    if eq(s, sub(0, 3)) {
        return cat(mk(0), mk(sub(0, 1)))
    }
    return cat(mk(s), mk(0))
}

# ---- 平衡三进制加法：a + b（trit 数组，低位在前）----
def bal3_add(a, b) {
    let na = len(a)
    let nb = len(b)
    let n = na
    if lt(nb, na) {
        let n = nb
    }
    # 对齐：按较长数组 + 1 位进位空间
    let L = na
    if gt(nb, na) {
        let L = nb
    }
    let i = 0
    let carry = 0
    let out = empty()
    while lt(i, L) {
        let va = 0
        if lt(i, na) {
            let va = get(a, i)
        }
        let vb = 0
        if lt(i, nb) {
            let vb = get(b, i)
        }
        let r = trit_add(va, vb, carry)
        let out = cat(out, mk(get(r, 0)))
        let carry = get(r, 1)
        let i = add(i, 1)
    }
    if sub(1, eq(carry, 0)) {
        let out = cat(out, mk(carry))
    }
    return out
}

# ---- 测试 ----
let t5 = to_bal3(5)
print(from_bal3(t5))
print(t5)
let tn5 = to_bal3(sub(0, 5))
print(from_bal3(tn5))
print(tn5)
let s = bal3_add(t5, tn5)
print(from_bal3(s))
print(s)
let s2 = bal3_add(to_bal3(100), to_bal3(sub(0, 37)))
print(from_bal3(s2))
print(s2)
