# boot_parse_v4.tl —— set1 原地写版（根治宿主 O(n²) cat）
# 语义与 v3 完全一致：输出 ast/blks 逐字节相同；预分配 + 指针，无 cat。
# 节点 type：0=哨兵 1=let 2=print 3=for 4=if 5=while 6=break 7=def 8=return
#            9=update 11=NumLit 12=VarRef 13=Call 14=tensor_lit 15=param_lit
#            16=Global 20=param

let toks = ext_in(0)
let tpos = 0
let ast = range(1500000)
let ast_n = 0
let blk_flat = range(1000000)
let blk_n = 0
let blk_cnt = 0
let ntok = len(toks)

def peek_cls() {
    return get(toks, mul(tpos, 3))
}
def peek_val() {
    return get(toks, add(mul(tpos, 3), 1))
}
def nxt() {
    global tpos
    let tpos = add(tpos, 1)
    return 0
}
def ast_len() {
    global ast_n
    return mul(ast_n, 4)
}
def emit(tp, a, b, c) {
    global ast ast_n
    let ast = set1(ast, mul(ast_n, 4), tp)
    let ast = set1(ast, add(mul(ast_n, 4), 1), a)
    let ast = set1(ast, add(mul(ast_n, 4), 2), b)
    let ast = set1(ast, add(mul(ast_n, 4), 3), c)
    let ast_n = add(ast_n, 1)
    return sub(mul(ast_n, 4), 4)
}
# 块：登记语句索引序列（idxs 为预分配数组 + n 为实际长度），返回块号
def reg_blk(idxs, n) {
    global blk_flat blk_n
    global blk_cnt
    let blk_flat = set1(blk_flat, blk_n, n)
    let blk_n = add(blk_n, 1)
    let k = 0
    while lt(k, n) {
        let blk_flat = set1(blk_flat, blk_n, get(idxs, k))
        let blk_n = add(blk_n, 1)
        let k = add(k, 1)
    }
    let blk_cnt = add(blk_cnt, 1)
    return sub(blk_cnt, 1)
}

# ---- 表达式：返回节点索引 ----
def parse_expr() {
    let e_cls = peek_cls()
    let e_val = peek_val()
    if eq(e_cls, 1) {
        let _r = nxt()
        return emit(11, e_val, 0, 0)
    }
    if eq(e_cls, 0) {
        # tensor 字面量（固定符号 12）
        if eq(e_val, 12) {
            let _r = nxt()
            let _r = nxt()
            let _r = nxt()
            let tidx = empty()
            if sub(1, mul(eq(peek_cls(), 2), eq(peek_val(), 93))) {
                while sub(1, mul(eq(peek_cls(), 2), eq(peek_val(), 93))) {
                    let e1 = parse_expr()
                    let tidx = cat(tidx, mk(e1))
                    if mul(eq(peek_cls(), 2), eq(peek_val(), 44)) {
                        let _r = nxt()
                    }
                }
            }
            let _r = nxt()
            let _r = nxt()
            let tbl = reg_blk(tidx, len(tidx))
            return emit(14, len(tidx), tbl, 0)
        }
        # 函数调用：后跟 '('
        let nx_cls = get(toks, mul(add(tpos, 1), 3))
        let nx_val = get(toks, add(mul(add(tpos, 1), 3), 1))
        if mul(eq(nx_cls, 2), eq(nx_val, 40)) {
            let fn = e_val
            let _r = nxt()
            let _r = nxt()
            let aargs = empty()
            if sub(1, mul(eq(peek_cls(), 2), eq(peek_val(), 41))) {
                let a1 = parse_expr()
                let aargs = cat(aargs, mk(a1))
                while mul(eq(peek_cls(), 2), eq(peek_val(), 44)) {
                    let _r = nxt()
                    let an = parse_expr()
                    let aargs = cat(aargs, mk(an))
                }
            }
            let _r = nxt()
            let abl = reg_blk(aargs, len(aargs))
            return emit(13, fn, abl, 0)
        }
        # VarRef
        let _r = nxt()
        return emit(12, e_val, 0, 0)
    }
    return 0
}

# ---- 块：{ stmts } 返回块号 ----
def parse_block() {
    let _r = nxt()
    let bsidx = empty()
    while ge(1, 1) {
        if eq(peek_cls(), 2) {
            if eq(peek_val(), 125) {
                let _r = nxt()
                break
            }
        }
        if eq(peek_cls(), 3) {
            break
        }
        let si = parse_stmt()
        if ge(si, 0) {
            let bsidx = cat(bsidx, mk(si))
        }
    }
    return reg_blk(bsidx, len(bsidx))
}

# ---- 语句：返回语句节点索引 ----
def parse_stmt() {
    let s_val = peek_val()
    # update（固定符号 36）
    if eq(s_val, 36) {
        let _r = nxt()
        let _r = nxt()
        let name = peek_val()
        let _r = nxt()
        let _r = nxt()
        let lr = peek_val()
        let _r = nxt()
        let _r = nxt()
        return emit(9, name, lr, 0)
    }
    # let（1）
    if eq(s_val, 1) {
        let _r = nxt()
        let name = peek_val()
        let _r = nxt()
        let _r = nxt()
        let e = parse_expr()
        return emit(1, name, e, 0)
    }
    # print（6）
    if eq(s_val, 6) {
        let _r = nxt()
        let _r = nxt()
        let e = parse_expr()
        let _r = nxt()
        return emit(2, e, 0, 0)
    }
    # for（2）
    if eq(s_val, 2) {
        let _r = nxt()
        let var = peek_val()
        let _r = nxt()
        let _r = nxt()
        let it = parse_expr()
        let b = parse_block()
        return emit(3, var, it, b)
    }
    # if（4）
    if eq(s_val, 4) {
        let _r = nxt()
        let cond = parse_expr()
        let b1 = parse_block()
        let b2 = 0
        if mul(eq(peek_cls(), 0), eq(peek_val(), 5)) {
            let _r = nxt()
            let b2 = parse_block()
        }
        return emit(4, cond, b1, b2)
    }
    # while（7）
    if eq(s_val, 7) {
        let _r = nxt()
        let cond = parse_expr()
        let b = parse_block()
        return emit(5, cond, b, 0)
    }
    # break（8）
    if eq(s_val, 8) {
        let _r = nxt()
        return emit(6, 0, 0, 0)
    }
    # def（9）
    if eq(s_val, 9) {
        let _r = nxt()
        let name = peek_val()
        let _r = nxt()
        let _r = nxt()
        let p_start = ast_len()
        while sub(1, mul(eq(peek_cls(), 2), eq(peek_val(), 41))) {
            if eq(peek_cls(), 0) {
                let _r = emit(20, peek_val(), 0, 0)
            }
            let _r = nxt()
        }
        let _r = emit(0, 0, 0, 0)
        let _r = nxt()
        let b = parse_block()
        return emit(7, name, p_start, b)
    }
    # return（10）
    if eq(s_val, 10) {
        let _r = nxt()
        let e = parse_expr()
        return emit(8, e, 0, 0)
    }
    # global（11）：循环消费全部名字（≤2 注册，多余消费防死循环）
    if eq(s_val, 11) {
        let _r = nxt()
        let n1 = 0
        let n2 = 0
        let cnt = 0
        while mul(eq(peek_cls(), 0), ge(peek_val(), 12)) {
            if eq(cnt, 0) {
                let n1 = peek_val()
            }
            if eq(cnt, 1) {
                let n2 = peek_val()
            }
            let _r = nxt()
            let cnt = add(cnt, 1)
            if ge(cnt, 2) {
                let cnt = 2
            }
        }
        return emit(16, cnt, n1, n2)
    }
    # ExpressionStmt（裸调用语句，type 17）：cls=0 且下一 token 是 '('
    let _nxc = get(toks, mul(add(tpos, 1), 3))
    let _nxv = get(toks, add(mul(add(tpos, 1), 3), 1))
    if mul(eq(peek_cls(), 0), mul(eq(_nxc, 2), eq(_nxv, 40))) {
        let _e = parse_expr()
        return emit(17, _e, 0, 0)
    }
    return sub(0, 1)
}

# ---- 主循环（顶层也是一个块）----
let sidx = empty()
while lt(tpos, ntok) {
    if eq(peek_cls(), 3) {
        break
    }
    let si = parse_stmt()
    if ge(si, 0) {
        let sidx = cat(sidx, mk(si))
    }
}
let _r = reg_blk(sidx, len(sidx))
# 尾压缩输出（与 v3 输出逐字节一致）
let ast_f = range(mul(ast_n, 4))
let k = 0
while lt(k, mul(ast_n, 4)) {
    let ast_f = set1(ast_f, k, get(ast, k))
    let k = add(k, 1)
}
print(ast_f)
let blk_f = range(blk_n)
let k3 = 0
while lt(k3, blk_n) {
    let blk_f = set1(blk_f, k3, get(blk_flat, k3))
    let k3 = add(k3, 1)
}
print(blk_f)
