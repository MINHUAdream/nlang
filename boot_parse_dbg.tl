# boot_parse.tl v3 —— 分块累积版（ast 每 256 节点刷一次，宿主 O(n²) → O(n²/256)）
# 语义与 v2 完全一致：输出 ast/blks 逐字节相同；仅改累积策略。
# 节点 type：0=哨兵 1=let 2=print 3=for 4=if 5=while 6=break 7=def 8=return
#            9=update 11=NumLit 12=VarRef 13=Call 14=tensor_lit 15=param_lit
#            16=Global 20=param

let toks = tensor([0, 0, 0])
let tpos = 0
global ast ast_pending
global ast_pend_n
let ast = empty()
let ast_pending = empty()
let ast_pend_n = 0
let blks = empty()
let blks_pending = empty()
let blks_pend_cnt = 0
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
    return add(len(ast), ast_pend_n)
}
def emit(tp, a, b, c) {
    global ast ast_pending
    global ast_pend_n
    let ast_pending = cat(ast_pending, cat(mk(tp), cat(mk(a), cat(mk(b), mk(c)))))
    let ast_pend_n = add(ast_pend_n, 4)
    if ge(ast_pend_n, 1024) {
        let ast = cat(ast, ast_pending)
        let ast_pending = empty()
        let ast_pend_n = 0
    }
    return sub(ast_len(), 4)
}
# 块：登记语句索引序列，返回块号
def reg_blk(idxs) {
    global blks blks_pending
global blks_pend_cnt blk_cnt
    let blks_pending = cat(blks_pending, cat(mk(len(idxs)), idxs))
    let blks_pend_cnt = add(blks_pend_cnt, 1)
    if ge(blks_pend_cnt, 512) {
        let blks = cat(blks, blks_pending)
        let blks_pending = empty()
        let blks_pend_cnt = 0
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
            let tbl = reg_blk(tidx)
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
            let abl = reg_blk(aargs)
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
    let sidx = empty()
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
            let sidx = cat(sidx, mk(si))
        }
    }
    return reg_blk(sidx)
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
                let _r = nxt()
                let cnt = 1
            }
            if eq(cnt, 1) {
                let n2 = peek_val()
                let _r = nxt()
                let cnt = 2
            }
            if eq(cnt, 2) {
                let _r = nxt()
            }
        }
        return emit(16, cnt, n1, n2)
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
    if eq(si, sub(0, 1)) {
        print(tpos)
        print(peek_cls())
        print(peek_val())
    }
}
let _r = reg_blk(sidx)
# 刷最后未满的 pending
let ast = cat(ast, ast_pending)
let blks = cat(blks, blks_pending)
print(ast)
print(blks)
