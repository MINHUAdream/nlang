# boot_gen.tl —— tl 语言自写代码生成器 v0.3（标量 + 1D tensor 运行时）
# 与 gen_ref.py v0.22 1:1 对应：变量槽 rbp-8*id、临时槽 rbp-8*(1000+2*深度+j)
# 支持：let/print/for/while/if/break/def/return + NumLit/VarRef + add/sub/mul
#        + eq/ge/le/lt + range(常数) + 用户函数（纯 jmp 协议）
#        + tensor 字面量 + mk/get(动态下标)/len/cat/empty
# 类型标记：gen_expr 返回 0='f' 标量 / 1='p' tensor 指针
# 数据区：[常数池][OUT][HEAP 槽][globals 槽][tensor 静态区][预留堆]；fixup kind 0=c 1=o 2=l 3=h 4=b 5=t 6=g

let print_seq = 0

global code consts
global consts_n
global fixups labels
global fixups_n labels_n
global label_seq loop_exits
global loop_exits_n
global loop_depth ast
global blks funcs
global funcs_n
global cur_params tensors
global tensor_idx var_types
global var_types_n
global global_ids global_ids_n
def mk_zeros(n) {
    return alloc(n)
}

let code = empty()
let consts = mk_zeros(65536)    # 预分配：常数表
let consts_n = 0
let fixups = mk_zeros(196608)   # 预分配 3*65536：rel32 记录（len,kind,target）
let fixups_n = 0
let labels = mk_zeros(131072)   # 预分配 2*65536：标签记录（lid,off）
let labels_n = 0
let label_seq = 0
let loop_exits = mk_zeros(65536)
let loop_exits_n = 0
let loop_depth = 0
let ast = ext_in(0)
let blks = ext_in(1)
let funcs = mk_zeros(20480)     # 预分配 5*4096：函数记录（id,body,lab,n,p_start）
let funcs_n = 0
let cur_params = empty()
let tensors = empty()      # 字面量内容平铺 [len, e0...]
let tensor_idx = 0         # gen_expr 当前字面量索引
let var_types = mk_zeros(131072)  # 预分配 2*65536：变量类型
let var_types_n = 0
let global_ids = mk_zeros(4096)   # 全局变量 id（数据区固定槽）
let global_ids_n = 0

# ---------- 字节工具 ----------
def emit1(b) {
    let code = app(code, mk(b))
    return 0
}

def emit_bytes(bs) {
    let i = 0
    while lt(i, len(bs)) {
        let code = app(code, mk(get(bs, i)))
        let i = add(i, 1)
    }
    return 0
}

def emit_d32(v) {
    let code = app(code, pack32(v))
    return 0
}

def emit_rel32(kind, target) {
    let fixups = set1(fixups, fixups_n, len(code))
    let fixups_n = add(fixups_n, 1)
    let fixups = set1(fixups, fixups_n, kind)
    let fixups_n = add(fixups_n, 1)
    let fixups = set1(fixups, fixups_n, target)
    let fixups_n = add(fixups_n, 1)
    let _r = emit_d32(0)
    return 0
}

def new_label() {
    let label_seq = add(label_seq, 1)
    return label_seq
}

def label_at(lid) {
    let labels = set1(labels, labels_n, lid)
    let labels_n = add(labels_n, 1)
    let labels = set1(labels, labels_n, len(code))
    let labels_n = add(labels_n, 1)
    return 0
}

def find_label(lid) {
    let i = 0
    while lt(i, labels_n) {
        if eq(get(labels, i), lid) {
            return get(labels, add(i, 1))
        }
        let i = add(i, 2)
    }
    return 0
}

def const_id(v) {
    let i = 0
    while lt(i, consts_n) {
        if eq(get(consts, i), v) {
            return i
        }
        let i = add(i, 1)
    }
    let consts = set1(consts, consts_n, v)
    let consts_n = add(consts_n, 1)
    return sub(consts_n, 1)
}

# ---------- 指令模板：帧与基础 ----------
def push_rbp() { let _r = emit1(0x55)
    return 0
}
def mov_rbp_rsp() { let _r = emit_bytes(tensor([0x48, 0x89, 0xE5]))
    return 0
}
def sub_rsp_imm() {
    let i = 0
    while lt(i, 8) {
        let _r = emit_bytes(tensor([0x48, 0x81, 0xEC, 0x00, 0x10, 0x00, 0x00]))
        let _r2 = emit_bytes(tensor([0x48, 0xC7, 0x04, 0x24, 0x00, 0x00, 0x00, 0x00]))
        let i = add(i, 1)
    }
    return 0
}
def leave_() { let _r = emit1(0xC9)
    return 0
}
def ret_() { let _r = emit1(0xC3)
    return 0
}
def push_rax() { let _r = emit1(0x50)
    return 0
}
def pop_rax() { let _r = emit1(0x58)
    return 0
}
def jmp_rax() { let _r = emit_bytes(tensor([0xFF, 0xE0]))
    return 0
}
def lea_rax_rip(lid) {
    let _r = emit_bytes(tensor([0x48, 0x8D, 0x05]))
    let _r2 = emit_rel32(2, lid)
    return 0
}
def lea_rax_rip_kind(kind, target) {
    let _r = emit_bytes(tensor([0x48, 0x8D, 0x05]))
    let _r2 = emit_rel32(kind, target)
    return 0
}
def add_rsp_imm(v) {
    let _r = emit_bytes(tensor([0x48, 0x81, 0xC4]))
    let _r2 = emit_d32(v)
    return 0
}
def pxor_xmm0() { let _r = emit_bytes(tensor([0x66, 0x0F, 0xEF, 0xC0]))
    return 0
}

# ---------- 指令模板：标量 ----------
def movsd_xmm0_rip(cid) {
    let _r = emit_bytes(tensor([0xF2, 0x0F, 0x10, 0x05]))
    let _r2 = emit_rel32(0, cid)
    return 0
}
def movsd_xmm0_rip_out() {
    let _r = emit_bytes(tensor([0xF2, 0x0F, 0x10, 0x05]))
    let _r2 = emit_rel32(1, 0)
    return 0
}
def movsd_xmm0_rbp(disp) {
    let _r = emit_bytes(tensor([0xF2, 0x0F, 0x10, 0x85]))
    let _r2 = emit_d32(disp)
    return 0
}
def movsd_xmm1_rbp(disp) {
    let _r = emit_bytes(tensor([0xF2, 0x0F, 0x10, 0x8D]))
    let _r2 = emit_d32(disp)
    return 0
}
def movsd_rbp_xmm0(disp) {
    let _r = emit_bytes(tensor([0xF2, 0x0F, 0x11, 0x85]))
    let _r2 = emit_d32(disp)
    return 0
}
def movsd_out_xmm0() {
    let _r = emit_bytes(tensor([0xF2, 0x0F, 0x11, 0x05]))
    let _r2 = emit_rel32(1, 0)
    return 0
}
def addsd_() { let _r = emit_bytes(tensor([0xF2, 0x0F, 0x58, 0xC1]))
    return 0
}
def subsd_() { let _r = emit_bytes(tensor([0xF2, 0x0F, 0x5C, 0xC1]))
    return 0
}
def mulsd_() { let _r = emit_bytes(tensor([0xF2, 0x0F, 0x59, 0xC1]))
    return 0
}
def ucomisd_() { let _r = emit_bytes(tensor([0x66, 0x0F, 0x2E, 0xC1]))
    return 0
}
def mov_r64_imm(r, v) {
    let _r = emit1(0x48)
    let _r2 = emit1(0xB8)
    let code = app(code, pack64(v))
    return 0
}
def mov_rax_rbp(disp) {
    let _r = emit_bytes(tensor([0x48, 0x8B, 0x85]))
    let _r2 = emit_d32(disp)
    return 0
}
def mov_rbp_rax(disp) {
    let _r = emit_bytes(tensor([0x48, 0x89, 0x85]))
    let _r2 = emit_d32(disp)
    return 0
}
def cvtsi2sd_xmm0_rax() {
    let _r = emit_bytes(tensor([0xF2, 0x48, 0x0F, 0x2A, 0xC0]))
    return 0
}
def inc_rax() { let _r = emit_bytes(tensor([0x48, 0xFF, 0xC0]))
    return 0
}
def cmp_rax_mem(disp) {
    let _r = emit_bytes(tensor([0x48, 0x3B, 0x85]))
    let _r2 = emit_d32(disp)
    return 0
}
def jcc_(cc, lid) {
    let _r = emit1(0x0F)
    let _r2 = emit1(bor(0x80, cc))
    let _r3 = emit_rel32(2, lid)
    return 0
}
def jmp_(lid) {
    let _r = emit1(0xE9)
    let _r2 = emit_rel32(2, lid)
    return 0
}

# ---------- 指令模板：tensor 运行时 ----------
def movq_xmm0_rax() { let _r = emit_bytes(tensor([0x66, 0x48, 0x0F, 0x6E, 0xC0]))
    return 0
}
def cvtsd2si_rcx_xmm0() { let _r = emit_bytes(tensor([0xF2, 0x48, 0x0F, 0x2C, 0xC8]))
    return 0
}
def mov_rax_mem_rax() { let _r = emit_bytes(tensor([0x48, 0x8B, 0x00]))
    return 0
}
def mov_rcx_mem_rax() { let _r = emit_bytes(tensor([0x48, 0x8B, 0x08]))
    return 0
}
def movsd_xmm0_mem_rax() { let _r = emit_bytes(tensor([0xF2, 0x0F, 0x10, 0x00]))
    return 0
}
def movsd_mem_rax_xmm0() { let _r = emit_bytes(tensor([0xF2, 0x0F, 0x11, 0x00]))
    return 0
}
def mov_mem_rax_rcx() { let _r = emit_bytes(tensor([0x48, 0x89, 0x08]))
    return 0
}
def mov_rcx_rbp(disp) {
    let _r = emit_bytes(tensor([0x48, 0x8B, 0x8D]))
    let _r2 = emit_d32(disp)
    return 0
}
def mov_rdx_rbp(disp) {
    let _r = emit_bytes(tensor([0x48, 0x8B, 0x95]))
    let _r2 = emit_d32(disp)
    return 0
}
def mov_r8_mem_rdx() { let _r = emit_bytes(tensor([0x4C, 0x8B, 0x02]))
    return 0
}
def mov_r9_lea_rdx_8() { let _r = emit_bytes(tensor([0x4C, 0x8D, 0x4A, 0x08]))
    return 0
}
def mov_r10_lea_rcx_8() { let _r = emit_bytes(tensor([0x4C, 0x8D, 0x51, 0x08]))
    return 0
}
def mov_r11_mem_r9() { let _r = emit_bytes(tensor([0x4D, 0x8B, 0x19]))
    return 0
}
def mov_mem_r10_r11() { let _r = emit_bytes(tensor([0x4D, 0x89, 0x1A]))
    return 0
}
def add_r9_8() { let _r = emit_bytes(tensor([0x49, 0x83, 0xC1, 0x08]))
    return 0
}
def add_r10_8() { let _r = emit_bytes(tensor([0x49, 0x83, 0xC2, 0x08]))
    return 0
}
def dec_r8() { let _r = emit_bytes(tensor([0x49, 0xFF, 0xC8]))
    return 0
}
def test_r8_r8() { let _r = emit_bytes(tensor([0x4D, 0x85, 0xC0]))
    return 0
}
def mov_qword_rcx_imm0() { let _r = emit_bytes(tensor([0x48, 0xC7, 0x01, 0x00, 0x00, 0x00, 0x00]))
    return 0
}
def mov_qword_rcx_imm1() { let _r = emit_bytes(tensor([0x48, 0xC7, 0x01, 0x01, 0x00, 0x00, 0x00]))
    return 0
}
def movsd_rcx8_xmm0() { let _r = emit_bytes(tensor([0xF2, 0x0F, 0x11, 0x41, 0x08]))
    return 0
}
def mov_mem_rcx_r8() { let _r = emit_bytes(tensor([0x4C, 0x89, 0x01]))
    return 0
}
def mov_rax_mem_rcx() { let _r = emit_bytes(tensor([0x48, 0x8B, 0x01]))
    return 0
}
def mov_mem_rcx_rax() { let _r = emit_bytes(tensor([0x48, 0x89, 0x01]))
    return 0
}
def add_rax_r8() { let _r = emit_bytes(tensor([0x4C, 0x01, 0xC0]))
    return 0
}
def mov_mem_rbx_r10() { let _r = emit_bytes(tensor([0x4C, 0x89, 0x13]))
    return 0
}
def mov_rdx_mem_rax() { let _r = emit_bytes(tensor([0x48, 0x8B, 0x10]))
    return 0
}
def mov_r8_mem_r10() { let _r = emit_bytes(tensor([0x4D, 0x8B, 0x02]))
    return 0
}
def mov_r10_rbp(disp) {
    let _r = emit_bytes(tensor([0x4C, 0x8B, 0x95]))
    let _r2 = emit_d32(disp)
    return 0
}
def mov_r9_lea_rax_rdx8_8() { let _r = emit_bytes(tensor([0x4C, 0x8D, 0x4C, 0xD0, 0x08]))
    return 0
}
def cmp_r9_r10() { let _r = emit_bytes(tensor([0x4F, 0x39, 0xD1]))
    return 0
}
def mov_r11_lea_r10_r8_8() { let _r = emit_bytes(tensor([0x4F, 0x8D, 0x5C, 0xC2, 0x08]))
    return 0
}
def cmp_r11_rcx() { let _r = emit_bytes(tensor([0x49, 0x39, 0xCB]))
    return 0
}
def add_mem_rax_r8() { let _r = emit_bytes(tensor([0x4C, 0x01, 0x00]))
    return 0
}
def mov_mem_rbx_r11() { let _r = emit_bytes(tensor([0x4C, 0x89, 0x1B]))
    return 0
}
def mov_rax_rsi() { let _r = emit_bytes(tensor([0x48, 0x89, 0xF0]))
    return 0
}
def mov_rsi_rcx() { let _r = emit_bytes(tensor([0x48, 0x89, 0xCE]))
    return 0
}
def mov_rcx_rax() { let _r = emit_bytes(tensor([0x48, 0x89, 0xC1]))
    return 0
}
def mov_rbx_rax() { let _r = emit_bytes(tensor([0x48, 0x89, 0xC3]))
    return 0
}
def movq_out_rax() { let _r = emit_bytes(tensor([0x48, 0x89, 0x05]))
    let _r2 = emit_rel32(1, 0)
    return 0
}
def lea_rax_rax_rcx8_8() { let _r = emit_bytes(tensor([0x48, 0x8D, 0x44, 0xC8, 0x08]))
    return 0
}
def mov_rax_rcx() { let _r = emit_bytes(tensor([0x48, 0x89, 0xC8]))
    return 0
}
def mov_mem_rax_rdx() { let _r = emit_bytes(tensor([0x48, 0x89, 0x10]))
    return 0
}
def mov_mem_rbx_rdx() { let _r = emit_bytes(tensor([0x48, 0x89, 0x13]))
    return 0
}
def mov_mem_rcx_rax8() { let _r = emit_bytes(tensor([0x48, 0x89, 0x41, 0x08]))
    return 0
}
def lea_rdx_rcx_8() { let _r = emit_bytes(tensor([0x48, 0x8D, 0x51, 0x08]))
    return 0
}
def lea_rdx_rcx_16() { let _r = emit_bytes(tensor([0x48, 0x8D, 0x51, 0x10]))
    return 0
}
def lea_rdx_rax_rcx8_8() { let _r = emit_bytes(tensor([0x48, 0x8D, 0x54, 0xC8, 0x08]))
    return 0
}
def mov_rax_mem_rdx() { let _r = emit_bytes(tensor([0x48, 0x8B, 0x02]))
    return 0
}

# ---------- AST 工具 ----------
def blk_idxs(no) {
    let i = 0
    let k = 0
    while lt(k, no) {
        let i = add(i, add(1, get(blks, i)))
        let k = add(k, 1)
    }
    let L = get(blks, i)
    let r = empty()
    let j = 0
    while lt(j, L) {
        let r = app(r, mk(get(blks, add(add(i, 1), j))))
        let j = add(j, 1)
    }
    return r
}

def top_block_no() {
    let i = 0
    let nos = 0
    while lt(i, len(blks)) {
        let nos = add(nos, 1)
        let i = add(i, add(1, get(blks, i)))
    }
    return sub(nos, 1)
}

# ---------- 函数表 ----------
def find_func(fn_id) {
    let i = 0
    while lt(i, funcs_n) {
        if eq(get(funcs, i), fn_id) {
            return get(funcs, add(i, 2))
        }
        let i = add(i, 5)
    }
    return sub(0, 1)
}

def find_func_body(fn_id) {
    let i = 0
    while lt(i, funcs_n) {
        if eq(get(funcs, i), fn_id) {
            return get(funcs, add(i, 1))
        }
        let i = add(i, 5)
    }
    return sub(0, 1)
}

def find_func_np(fn_id) {
    let i = 0
    while lt(i, funcs_n) {
        if eq(get(funcs, i), fn_id) {
            return get(funcs, add(i, 3))
        }
        let i = add(i, 5)
    }
    return 0
}

def find_func_pstart(fn_id) {
    let i = 0
    while lt(i, funcs_n) {
        if eq(get(funcs, i), fn_id) {
            return get(funcs, add(i, 4))
        }
        let i = add(i, 5)
    }
    return 0
}

def find_cur_param(pid) {
    let i = 0
    while lt(i, len(cur_params)) {
        if eq(get(cur_params, i), pid) {
            return get(cur_params, add(i, 1))
        }
        let i = add(i, 2)
    }
    return sub(0, 1)
}

# ---------- 变量类型 ----------
def set_var_type(vid, kind) {
    # 存在则更新，否则追加
    let i = 0
    while lt(i, var_types_n) {
        if eq(get(var_types, i), vid) {
            let var_types = set1(var_types, add(i, 1), kind)
            return 0
        }
        let i = add(i, 2)
    }
    let var_types = set1(var_types, var_types_n, vid)
    let var_types_n = add(var_types_n, 1)
    let var_types = set1(var_types, var_types_n, kind)
    let var_types_n = add(var_types_n, 1)
    return 0
}

def get_var_type(vid) {
    let i = 0
    while lt(i, var_types_n) {
        if eq(get(var_types, i), vid) {
            return get(var_types, add(i, 1))
        }
        let i = add(i, 2)
    }
    return 0
}

def glob_slot(vid) {
    # 返回全局变量在 global_ids 中的下标（-1 表示非全局）
    let gs = -1
    let gi = 0
    while lt(gi, global_ids_n) {
        if eq(get(global_ids, gi), vid) {
            let gs = gi
        }
        let gi = add(gi, 1)
    }
    return gs
}

def expr_kind(idx) {
    let tp = get(ast, idx)
    if eq(tp, 14) {
        return 1
    }
    if eq(tp, 13) {
        let fn = get(ast, add(idx, 1))
        if eq(fn, 22) {
            return 1
        }
        if eq(fn, 21) {
            return 1
        }
        if eq(fn, 25) {
            return 1
        }
        if eq(fn, 39) {
            return 1
        }
        if eq(fn, 26) {
            return 1
        }
    }
    return 0
}

def collect_types(no) {
    let idxs = blk_idxs(no)
    let i = 0
    while lt(i, len(idxs)) {
        let si = get(idxs, i)
        let tp = get(ast, si)
        if eq(tp, 1) {
            let _r = set_var_type(get(ast, add(si, 1)), expr_kind(get(ast, add(si, 2))))
        }
        if eq(tp, 3) {
            let _r = set_var_type(get(ast, add(si, 1)), 0)
            let _r2 = collect_types(get(ast, add(si, 3)))
        }
        if eq(tp, 4) {
            let _r = collect_types(get(ast, add(si, 2)))
            if eq(get(ast, add(si, 3)), 0) {
                let _r2 = 0
            } else {
                let _r2 = collect_types(get(ast, add(si, 3)))
            }
        }
        if eq(tp, 5) {
            let _r = collect_types(get(ast, add(si, 2)))
        }
        let i = add(i, 1)
    }
    return 0
}

# ---------- 表达式求值（结果存临时槽 1000+2*depth；返回 0=f 1=p）----------
def gen_expr(idx, depth) {
    let tp = get(ast, idx)
    let a = get(ast, add(idx, 1))
    let b = get(ast, add(idx, 2))
    let t = add(1000, mul(2, depth))
    if eq(tp, 11) {
        let cid = const_id(a)
        let _r = movsd_xmm0_rip(cid)
        let _r2 = movsd_rbp_xmm0(mul(sub(0, 8), t))
        return 0
    }
    if eq(tp, 12) {
        let kp = find_cur_param(a)
        if ge(kp, 0) {
            let _r = movsd_xmm0_rbp(add(16, mul(8, kp)))
            let _r2 = movsd_rbp_xmm0(mul(sub(0, 8), t))
            return 0
        }
        let gslot = glob_slot(a)
        if ge(gslot, 0) {
            # 全局：数据区固定槽（函数内外同一地址）
            let _r = lea_rax_rip_kind(6, gslot)
            let vt = get_var_type(a)
            if eq(vt, 1) {
                let _r2 = mov_rax_mem_rax()
                let _r3 = mov_rbp_rax(mul(sub(0, 8), t))
                return 1
            }
            let _r2 = movsd_xmm0_mem_rax()
            let _r3 = movsd_rbp_xmm0(mul(sub(0, 8), t))
            return 0
        }
        let vt = get_var_type(a)
        if eq(vt, 1) {
            let _r = mov_rax_rbp(mul(sub(0, 8), a))
            let _r2 = mov_rbp_rax(mul(sub(0, 8), t))
            return 1
        }
        let _r = movsd_xmm0_rbp(mul(sub(0, 8), a))
        let _r2 = movsd_rbp_xmm0(mul(sub(0, 8), t))
        return 0
    }
    if eq(tp, 14) {
        let _r = lea_rax_rip_kind(5, tensor_idx)
        let tensor_idx = add(tensor_idx, 1)
        let _r2 = mov_rbp_rax(mul(sub(0, 8), t))
        return 1
    }
    if eq(tp, 13) {
        let fn = a
        let args = blk_idxs(b)
        if eq(fn, 39) {
            # ext_in(k)：k=0 -> ast 指针；k=1 -> blks 指针（输入区 +8*len+8）
            let k = get(ast, add(get(args, 0), 1))
            if eq(k, 0) {
                let _r = mov_rax_rbp(1024)
                let _r2 = mov_rbp_rax(mul(sub(0, 8), t))
                return 1
            }
            let _r = mov_rax_rbp(1024)
            let _r2 = mov_rcx_mem_rax()
            let _r3 = lea_rax_rax_rcx8_8()
            let _r4 = mov_rbp_rax(mul(sub(0, 8), t))
            return 1
        }
        let fl = find_func(fn)
        if ge(fl, 0) {
            let k = sub(len(args), 1)
            while ge(k, 0) {
                let _r = gen_expr(get(args, k), depth)
                let _r2 = mov_rax_rbp(mul(sub(0, 8), add(1000, mul(2, depth))))
                let _r3 = push_rax()
                let k = sub(k, 1)
            }
            let ret_l = new_label()
            let _r4 = lea_rax_rip(ret_l)
            let _r5 = push_rax()
            let _r6 = jmp_(fl)
            let _r7 = label_at(ret_l)
            if ge(len(args), 1) {
                let _r8 = add_rsp_imm(mul(8, len(args)))
            }
            let _r9 = movsd_rbp_xmm0(mul(sub(0, 8), t))
            return 0
        }
        if eq(fn, 22) {
            # mk(v)：堆分配 [1, v]，返回指针
            let ta = add(1000, mul(2, add(depth, 1)))
            let _r = gen_expr(get(args, 0), add(depth, 1))
            let _r2 = lea_rax_rip_kind(3, 0)
            let _r3 = mov_rcx_mem_rax()
            let _r4 = mov_qword_rcx_imm1()
            let _r5 = movsd_xmm0_rbp(mul(sub(0, 8), ta))
            let _r6 = movsd_rcx8_xmm0()
            let _r7 = lea_rdx_rcx_16()
            let _r8 = mov_mem_rax_rdx()
            let _r9 = mov_rax_rcx()
            let _r10 = mov_rbp_rax(mul(sub(0, 8), t))
            return 1
        }
        if eq(fn, 24) {
            # len(t)：读 [t]，转 double
            let ta = add(1000, mul(2, add(depth, 1)))
            let _r = gen_expr(get(args, 0), add(depth, 1))
            let _r2 = mov_rax_rbp(mul(sub(0, 8), ta))
            let _r3 = mov_rax_mem_rax()
            let _r4 = cvtsi2sd_xmm0_rax()
            let _r5 = movsd_rbp_xmm0(mul(sub(0, 8), t))
            return 0
        }
        if eq(fn, 23) {
            # get(t, i)：i 转整数，元素地址 [t + 8*i + 8]
            let ta = add(1000, mul(2, add(depth, 1)))
            let tb = add(1000, mul(2, add(depth, 2)))
            let _r = gen_expr(get(args, 0), add(depth, 1))
            let _r2 = gen_expr(get(args, 1), add(depth, 2))
            let _r3 = mov_rax_rbp(mul(sub(0, 8), ta))
            let _r4 = movsd_xmm0_rbp(mul(sub(0, 8), tb))
            let _r5 = cvtsd2si_rcx_xmm0()
            let _r6 = lea_rdx_rax_rcx8_8()
            let _r7 = mov_rax_mem_rdx()
            let _r8 = movq_xmm0_rax()
            let _r9 = movsd_rbp_xmm0(mul(sub(0, 8), t))
            return 0
        }
        if eq(fn, 25) {
            # empty()：堆分配 [0]
            let _r = lea_rax_rip_kind(3, 0)
            let _r2 = mov_rcx_mem_rax()
            let _r3 = mov_qword_rcx_imm0()
            let _r4 = lea_rdx_rcx_8()
            let _r5 = mov_mem_rax_rdx()
            let _r6 = mov_rax_rcx()
            let _r7 = mov_rbp_rax(mul(sub(0, 8), t))
            return 1
        }
        if eq(fn, 21) {
            # cat(a, b)：复制合并
            let ta = add(1000, mul(2, add(depth, 1)))
            let tb = add(1000, mul(2, add(depth, 2)))
            let _r = gen_expr(get(args, 0), add(depth, 1))
            let _r2 = gen_expr(get(args, 1), add(depth, 2))
            let _r3 = lea_rax_rip_kind(3, 0)
            let _r4 = mov_rbx_rax()
            let _r5 = mov_rcx_mem_rax()
            let _r6 = mov_rsi_rcx()
            # 复制 a
            let _r7 = mov_rdx_rbp(mul(sub(0, 8), ta))
            let _r8 = mov_r8_mem_rdx()
            let _r9 = mov_mem_rcx_r8()
            let _r10 = mov_r9_lea_rdx_8()
            let _r11 = mov_r10_lea_rcx_8()
            let l_a = new_label()
            let _r12 = label_at(l_a)
            let _r13 = test_r8_r8()
            let jz_a = new_label()
            let _r14 = jcc_(4, jz_a)
            let _r15 = mov_r11_mem_r9()
            let _r16 = mov_mem_r10_r11()
            let _r17 = add_r9_8()
            let _r18 = add_r10_8()
            let _r19 = dec_r8()
            let _r20 = jmp_(l_a)
            let _r21 = label_at(jz_a)
            # 复制 b
            let _r22 = mov_rdx_rbp(mul(sub(0, 8), tb))
            let _r23 = mov_r8_mem_rdx()
            let _r24 = mov_rax_mem_rcx()
            let _r25 = add_rax_r8()
            let _r26 = mov_mem_rcx_rax()
            let _r27 = mov_r9_lea_rdx_8()
            let l_b = new_label()
            let _r28 = label_at(l_b)
            let _r29 = test_r8_r8()
            let jz_b = new_label()
            let _r30 = jcc_(4, jz_b)
            let _r31 = mov_r11_mem_r9()
            let _r32 = mov_mem_r10_r11()
            let _r33 = add_r9_8()
            let _r34 = add_r10_8()
            let _r35 = dec_r8()
            let _r36 = jmp_(l_b)
            let _r37 = label_at(jz_b)
            let _r38 = mov_mem_rbx_r10()
            let _r39 = mov_rax_rsi()
            let _r40 = mov_rbp_rax(mul(sub(0, 8), t))
            return 1
        }
        if eq(fn, 42) {
            # app(t, t2)：t2 元素追加到 t。
            # t 块末尾==t2 基址 且 t2 块末尾==堆顶 → 零拷贝（len 相加、堆顶推进）
            let ta = add(1000, mul(2, add(depth, 1)))
            let tb = add(1000, mul(2, add(depth, 2)))
            let _r = gen_expr(get(args, 0), add(depth, 1))
            let _r2 = gen_expr(get(args, 1), add(depth, 2))
            let _r3 = lea_rax_rip_kind(3, 0)
            let _r4 = mov_rbx_rax()
            let _r5 = mov_rcx_mem_rax()
            let _r6 = mov_rax_rbp(mul(sub(0, 8), ta))
            let _r7 = mov_rdx_mem_rax()
            let _r8 = mov_r9_lea_rax_rdx8_8()
            let _r9 = mov_r10_rbp(mul(sub(0, 8), tb))
            let _r10 = mov_r8_mem_r10()
            let l_copy = new_label()
            let _r11 = cmp_r9_r10()
            let _r12 = jcc_(5, l_copy)
            let _r13 = mov_r11_lea_r10_r8_8()
            let _r14 = cmp_r11_rcx()
            let _r15 = jcc_(5, l_copy)
            let _r16 = add_mem_rax_r8()
            let _r17 = mov_mem_rbx_r11()
            let _r18 = mov_rax_rbp(mul(sub(0, 8), ta))
            let _r19 = mov_rbp_rax(mul(sub(0, 8), t))
            let l_done = new_label()
            let _r20 = jmp_(l_done)
            let _r21 = label_at(l_copy)
            let _r22 = mov_rsi_rcx()
            let _r23 = mov_rdx_rbp(mul(sub(0, 8), ta))
            let _r24 = mov_r8_mem_rdx()
            let _r25 = mov_mem_rcx_r8()
            let _r26 = mov_r9_lea_rdx_8()
            let _r27 = mov_r10_lea_rcx_8()
            let l_a = new_label()
            let _r28 = label_at(l_a)
            let _r29 = test_r8_r8()
            let jz_a = new_label()
            let _r30 = jcc_(4, jz_a)
            let _r31 = mov_r11_mem_r9()
            let _r32 = mov_mem_r10_r11()
            let _r33 = add_r9_8()
            let _r34 = add_r10_8()
            let _r35 = dec_r8()
            let _r36 = jmp_(l_a)
            let _r37 = label_at(jz_a)
            let _r38 = mov_rdx_rbp(mul(sub(0, 8), tb))
            let _r39 = mov_r8_mem_rdx()
            let _r40 = mov_rax_mem_rcx()
            let _r41 = add_rax_r8()
            let _r42 = mov_mem_rcx_rax()
            let _r43 = mov_r9_lea_rdx_8()
            let l_b = new_label()
            let _r44 = label_at(l_b)
            let _r45 = test_r8_r8()
            let jz_b = new_label()
            let _r46 = jcc_(4, jz_b)
            let _r47 = mov_r11_mem_r9()
            let _r48 = mov_mem_r10_r11()
            let _r49 = add_r9_8()
            let _r50 = add_r10_8()
            let _r51 = dec_r8()
            let _r52 = jmp_(l_b)
            let _r53 = label_at(jz_b)
            let _r54 = mov_mem_rbx_r10()
            let _r55 = mov_rax_rsi()
            let _r56 = mov_rbp_rax(mul(sub(0, 8), t))
            let _r57 = label_at(l_done)
            return 1
        }
        if eq(fn, 43) {
            # alloc(n)：分配 n 元素全 0 tensor 块（头=[n]，数据全 0），返回指针
            # n 为 double → cvtsd2si 转整数；寄存器：rcx=n rdx=块基址 rbx=heap槽地址
            # r10=数据起点 r8=计数 rax=填充0
            let ta = add(1000, mul(2, add(depth, 1)))
            let _r = gen_expr(get(args, 0), add(depth, 1))
            let _r0 = movsd_xmm0_rbp(mul(sub(0, 8), ta))
            let _r0b = cvtsd2si_rcx_xmm0()
            let _r2 = lea_rax_rip_kind(3, 0)
            let _r3 = mov_rbx_rax()
            let _r4 = mov_rdx_mem_rax()
            let _r5 = emit_bytes(tensor([0x48, 0x89, 0x0A]))
            let _r6 = emit_bytes(tensor([0x4C, 0x8D, 0x52, 0x08]))
            let _r7 = emit_bytes(tensor([0x49, 0x89, 0xC8]))
            let _r8 = emit_bytes(tensor([0x48, 0x31, 0xC0]))
            let l_z = new_label()
            let _r9 = label_at(l_z)
            let _r10 = test_r8_r8()
            let jz_z = new_label()
            let _r11 = jcc_(4, jz_z)
            let _r12 = emit_bytes(tensor([0x49, 0x89, 0xC3]))
            let _r13 = emit_bytes(tensor([0x4D, 0x89, 0x1A]))
            let _r14 = add_r10_8()
            let _r15 = dec_r8()
            let _r16 = jmp_(l_z)
            let _r17 = label_at(jz_z)
            let _r18 = emit_bytes(tensor([0x48, 0x8D, 0x44, 0xCA, 0x08]))
            let _r19 = emit_bytes(tensor([0x48, 0x89, 0x03]))
            let _r20 = emit_bytes(tensor([0x48, 0x89, 0xD0]))
            let _r21 = mov_rbp_rax(mul(sub(0, 8), t))
            return 1
        }
        if eq(fn, 26) {
            # set1(t, i, v)：复制 t → 新数组，[i] = v（值语义）
            let ta = add(1000, mul(2, add(depth, 1)))
            let tb = add(1000, mul(2, add(depth, 2)))
            let tc = add(1000, mul(2, add(depth, 3)))
            let _r = gen_expr(get(args, 0), add(depth, 1))
            let _r2 = gen_expr(get(args, 1), add(depth, 2))
            let _r3 = gen_expr(get(args, 2), add(depth, 3))
            let _r4 = lea_rax_rip_kind(3, 0)
            let _r5 = mov_rbx_rax()
            let _r6 = mov_rcx_mem_rax()
            let _r7 = mov_rsi_rcx()
            let _r8 = mov_rax_rbp(mul(sub(0, 8), ta))
            let _r9 = mov_rax_mem_rax()
            let _r10 = mov_mem_rcx_rax()
            let _r11 = mov_rdx_rbp(mul(sub(0, 8), ta))
            let _r12 = mov_r8_mem_rdx()
            let _r13 = mov_r9_lea_rdx_8()
            let _r14 = mov_r10_lea_rcx_8()
            let l_cp = new_label()
            let _r15 = label_at(l_cp)
            let _r16 = test_r8_r8()
            let jz_cp = new_label()
            let _r17 = jcc_(4, jz_cp)
            let _r18 = mov_r11_mem_r9()
            let _r19 = mov_mem_r10_r11()
            let _r20 = add_r9_8()
            let _r21 = add_r10_8()
            let _r22 = dec_r8()
            let _r23 = jmp_(l_cp)
            let _r24 = label_at(jz_cp)
            let _r25 = mov_rax_rsi()
            let _r26 = movsd_xmm0_rbp(mul(sub(0, 8), tb))
            let _r27 = cvtsd2si_rcx_xmm0()
            let _r28 = lea_rdx_rax_rcx8_8()
            let _r29 = movsd_xmm0_rbp(mul(sub(0, 8), tc))
            let _r30 = emit_bytes(tensor([242, 15, 17, 2]))  # movsd [rdx]))
            let _r31 = mov_mem_rbx_r10()
            let _r32 = mov_rax_rsi()
            let _r33 = mov_rbp_rax(mul(sub(0, 8), t))
            return 1
        }
        if eq(fn, 28) {
            # pack32(v)：拆 4 字节 → 堆数组 [4, b0..b3]
            let ta = add(1000, mul(2, add(depth, 1)))
            let _r = gen_expr(get(args, 0), add(depth, 1))
            let _r2 = movsd_xmm0_rbp(mul(sub(0, 8), ta))
            let _r3 = emit_bytes(tensor([242, 72, 15, 44, 192]))
            let _r4 = emit_bytes(tensor([72, 137, 133, 0, 8, 0, 0]))  # mov [rbp+2048]))
            let _r5 = lea_rax_rip_kind(3, 0)
            let _r5b = mov_rbx_rax()
            let _r6 = mov_rcx_mem_rax()
            let _r7 = emit_bytes(tensor([72, 199, 1, 4, 0, 0, 0]))  # [rcx]))
            let _k0 = 0
            while lt(_k0, 4) {
                let _t = emit_bytes(tensor([72, 139, 133, 0, 8, 0, 0]))  # mov rax, [rbp+2048]))
                if gt(_k0, 0) {
                    let _t2 = emit_bytes(tensor([72, 193, 232]))
                let _t2b = emit1(mul(8, _k0))
                }
                let _t3 = emit_bytes(tensor([72, 129, 224, 255, 0, 0, 0]))
                let _t4 = cvtsi2sd_xmm0_rax()
                let _t5 = emit_bytes(tensor([242, 15, 17, 65]))
                let _t5b = emit1(add(8, mul(8, _k0)))  # movsd [rcx+8+8k], xmm0
                let _k0 = add(_k0, 1)
            }
            let _r8 = emit_bytes(tensor([72, 141, 145]))  # lea rdx, [rcx+disp32]))
            let _r9 = emit_d32(40)
            let _r10 = mov_mem_rbx_rdx()
            let _r11 = mov_rax_rcx()
            let _r12 = mov_rbp_rax(mul(sub(0, 8), t))
            return 1
        }
        if eq(fn, 29) {
            # pack64(v)：拆 8 字节 → 堆数组 [8, b0..b7]
            let ta = add(1000, mul(2, add(depth, 1)))
            let _r = gen_expr(get(args, 0), add(depth, 1))
            let _r2 = movsd_xmm0_rbp(mul(sub(0, 8), ta))
            let _r3 = emit_bytes(tensor([242, 72, 15, 44, 192]))
            let _r4 = emit_bytes(tensor([72, 137, 133, 0, 8, 0, 0]))  # mov [rbp+2048]))
            let _r5 = lea_rax_rip_kind(3, 0)
            let _r5b = mov_rbx_rax()
            let _r6 = mov_rcx_mem_rax()
            let _r7 = emit_bytes(tensor([72, 199, 1, 8, 0, 0, 0]))  # [rcx]))
            let _k0 = 0
            while lt(_k0, 8) {
                let _t = emit_bytes(tensor([72, 139, 133, 0, 8, 0, 0]))  # mov rax, [rbp+2048]))
                if gt(_k0, 0) {
                    let _t2 = emit_bytes(tensor([72, 193, 232]))
                let _t2b = emit1(mul(8, _k0))
                }
                let _t3 = emit_bytes(tensor([72, 129, 224, 255, 0, 0, 0]))
                let _t4 = cvtsi2sd_xmm0_rax()
                let _t5 = emit_bytes(tensor([242, 15, 17, 65]))
                let _t5b = emit1(add(8, mul(8, _k0)))  # movsd [rcx+8+8k], xmm0
                let _k0 = add(_k0, 1)
            }
            let _r8 = emit_bytes(tensor([72, 141, 145]))  # lea rdx, [rcx+disp32]))
            let _r9 = emit_d32(72)
            let _r10 = mov_mem_rbx_rdx()
            let _r11 = mov_rax_rcx()
            let _r12 = mov_rbp_rax(mul(sub(0, 8), t))
            return 1
        }
        if eq(fn, 40) {
            # dbl64(x)：double 位型拆 8 字节 → 堆数组
            let ta = add(1000, mul(2, add(depth, 1)))
            let _r = gen_expr(get(args, 0), add(depth, 1))
            let _r2 = movsd_xmm0_rbp(mul(sub(0, 8), ta))
            let _r3 = emit_bytes(tensor([102, 72, 15, 126, 192]))
            let _r4 = emit_bytes(tensor([72, 137, 133, 0, 8, 0, 0]))  # mov [rbp+2048]))
            let _r5 = lea_rax_rip_kind(3, 0)
            let _r5b = mov_rbx_rax()
            let _r6 = mov_rcx_mem_rax()
            let _r7 = emit_bytes(tensor([72, 199, 1, 8, 0, 0, 0]))  # [rcx]))
            let _k0 = 0
            while lt(_k0, 8) {
                let _t = emit_bytes(tensor([72, 139, 133, 0, 8, 0, 0]))  # mov rax, [rbp+2048]))
                if gt(_k0, 0) {
                    let _t2 = emit_bytes(tensor([72, 193, 232]))
                let _t2b = emit1(mul(8, _k0))
                }
                let _t3 = emit_bytes(tensor([72, 129, 224, 255, 0, 0, 0]))
                let _t4 = cvtsi2sd_xmm0_rax()
                let _t5 = emit_bytes(tensor([242, 15, 17, 65]))
                let _t5b = emit1(add(8, mul(8, _k0)))  # movsd [rcx+8+8k], xmm0
                let _k0 = add(_k0, 1)
            }
            let _r8 = emit_bytes(tensor([72, 141, 145]))  # lea rdx, [rcx+disp32]))
            let _r9 = emit_d32(72)
            let _r10 = mov_mem_rbx_rdx()
            let _r11 = mov_rax_rcx()
            let _r12 = mov_rbp_rax(mul(sub(0, 8), t))
            return 1
        }
        if eq(fn, 31) {
            let ta = add(1000, mul(2, add(depth, 1)))
            let tb = add(1000, mul(2, add(depth, 2)))
            let _r = gen_expr(get(args, 0), add(depth, 1))
            let _r2 = gen_expr(get(args, 1), add(depth, 2))
            let _r3 = movsd_xmm0_rbp(mul(sub(0, 8), ta))
            let _r4 = emit_bytes(tensor([242, 72, 15, 44, 192]))
            let _r5 = movsd_xmm0_rbp(mul(sub(0, 8), tb))
            let _r6 = emit_bytes(tensor([242, 72, 15, 44, 200]))
            let _r7 = emit_bytes(tensor([72, 33, 200]))
            let _r8 = cvtsi2sd_xmm0_rax()
            let _r9 = movsd_rbp_xmm0(mul(sub(0, 8), t))
            return 0
        }
        if eq(fn, 32) {
            let ta = add(1000, mul(2, add(depth, 1)))
            let tb = add(1000, mul(2, add(depth, 2)))
            let _r = gen_expr(get(args, 0), add(depth, 1))
            let _r2 = gen_expr(get(args, 1), add(depth, 2))
            let _r3 = movsd_xmm0_rbp(mul(sub(0, 8), ta))
            let _r4 = emit_bytes(tensor([242, 72, 15, 44, 192]))
            let _r5 = movsd_xmm0_rbp(mul(sub(0, 8), tb))
            let _r6 = emit_bytes(tensor([242, 72, 15, 44, 200]))
            let _r7 = emit_bytes(tensor([72, 9, 200]))
            let _r8 = cvtsi2sd_xmm0_rax()
            let _r9 = movsd_rbp_xmm0(mul(sub(0, 8), t))
            return 0
        }
        if eq(fn, 35) {
            let ta = add(1000, mul(2, add(depth, 1)))
            let tb = add(1000, mul(2, add(depth, 2)))
            let _r = gen_expr(get(args, 0), add(depth, 1))
            let _r2 = gen_expr(get(args, 1), add(depth, 2))
            let _r3 = movsd_xmm0_rbp(mul(sub(0, 8), ta))
            let _r4 = emit_bytes(tensor([242, 72, 15, 44, 192]))
            let _r5 = movsd_xmm0_rbp(mul(sub(0, 8), tb))
            let _r6 = emit_bytes(tensor([242, 72, 15, 44, 200]))
            let _r7 = emit_bytes(tensor([72, 211, 248]))
            let _r8 = cvtsi2sd_xmm0_rax()
            let _r9 = movsd_rbp_xmm0(mul(sub(0, 8), t))
            return 0
        }
        # 原语 add(18)/sub(19)/mul(20)
        let ta = add(1000, mul(2, add(depth, 1)))
        let tb = add(1000, mul(2, add(depth, 2)))
        let _r = gen_expr(get(args, 0), add(depth, 1))
        let _r2 = gen_expr(get(args, 1), add(depth, 2))
        let _r3 = movsd_xmm0_rbp(mul(sub(0, 8), ta))
        let _r4 = movsd_xmm1_rbp(mul(sub(0, 8), tb))
        if eq(fn, 18) {
            let _r5 = addsd_()
        }
        if eq(fn, 19) {
            let _r5 = subsd_()
        }
        if eq(fn, 20) {
            let _r5 = mulsd_()
        }
        let _r6 = movsd_rbp_xmm0(mul(sub(0, 8), t))
        return 0
    }
    return sub(0, 1)
}

# ---------- 条件（cond 为假时跳 lid）----------
def gen_cond_jcc(cond, lid) {
    let b = get(ast, add(cond, 2))
    let fn = get(ast, add(cond, 1))
    let args = blk_idxs(b)
    let _r = gen_expr(get(args, 0), 0)
    let _r2 = gen_expr(get(args, 1), 1)
    let _r3 = movsd_xmm0_rbp(mul(sub(0, 8), 1000))
    let _r4 = movsd_xmm1_rbp(mul(sub(0, 8), 1002))
    let _r5 = ucomisd_()
    if eq(fn, 14) {
        let _r6 = jcc_(5, lid)
    }
    if eq(fn, 15) {
        let _r6 = jcc_(2, lid)
    }
    if eq(fn, 16) {
        let _r6 = jcc_(7, lid)
    }
    if eq(fn, 17) {
        let _r6 = jcc_(3, lid)
    }
    if eq(fn, 41) {
        let _r6 = jcc_(6, lid)
    }
    return 0
}

# ---------- 语句 ----------
def gen_for(var_id, it_idx, body_blk) {
    let b = get(ast, add(it_idx, 2))
    let args = blk_idxs(b)
    let N = get(ast, add(get(args, 0), 1))
    let l_start = new_label()
    let l_exit = new_label()
    let loop_exits = set1(loop_exits, loop_exits_n, l_exit)
    let loop_exits_n = add(loop_exits_n, 1)
    let loop_depth = add(loop_depth, 1)
    let cnt_slot = add(2000, mul(2, loop_depth))
    let end_slot = add(2000, add(mul(2, loop_depth), 1))
    let _r = mov_r64_imm(0, 0)
    let _r2 = mov_rbp_rax(mul(sub(0, 8), cnt_slot))
    let _r3 = mov_r64_imm(0, N)
    let _r4 = mov_rbp_rax(mul(sub(0, 8), end_slot))
    let _r5 = label_at(l_start)
    let _r6 = mov_rax_rbp(mul(sub(0, 8), cnt_slot))
    let _r7 = cvtsi2sd_xmm0_rax()
    let _r8 = movsd_rbp_xmm0(mul(sub(0, 8), var_id))
    let _r9 = cmp_rax_mem(mul(sub(0, 8), end_slot))
    let _r10 = jcc_(13, l_exit)
    let _r11 = gen_block(body_blk)
    let _r12 = mov_rax_rbp(mul(sub(0, 8), cnt_slot))
    let _r13 = inc_rax()
    let _r14 = mov_rbp_rax(mul(sub(0, 8), cnt_slot))
    let _r15 = jmp_(l_start)
    let _r16 = label_at(l_exit)
    let loop_exits_n = sub(loop_exits_n, 1)
    let loop_depth = sub(loop_depth, 1)
    return 0
}

def slice_keep(xs, n) {
    let r = empty()
    let i = 0
    while lt(i, n) {
        let r = app(r, mk(get(xs, i)))
        let i = add(i, 1)
    }
    return r
}

def gen_block(no) {
    let idxs = blk_idxs(no)
    let i = 0
    while lt(i, len(idxs)) {
        let _r = gen_stmt(get(idxs, i))
        let i = add(i, 1)
    }
    return 0
}

def gen_stmt(idx) {
    let tp = get(ast, idx)
    let a = get(ast, add(idx, 1))
    let b = get(ast, add(idx, 2))
    let c = get(ast, add(idx, 3))
    if eq(tp, 1) {
        let gslot = glob_slot(a)
        if ge(gslot, 0) {
            # 全局：写数据区固定槽
            let k = gen_expr(b, 0)
            let _r = lea_rax_rip_kind(6, gslot)
            if eq(k, 1) {
                let _r2 = mov_rcx_rbp(mul(sub(0, 8), 1000))
                let _r3 = mov_mem_rax_rcx()
            } else {
                let _r2 = movsd_mem_rax_xmm0()
            }
            return 0
        }
        let k = gen_expr(b, 0)
        if eq(k, 1) {
            let _r = mov_rbp_rax(mul(sub(0, 8), a))
        } else {
            let _r = movsd_rbp_xmm0(mul(sub(0, 8), a))
        }
        return 0
    }
    if eq(tp, 2) {
        let k = gen_expr(a, 0)
        if eq(k, 1) {
            let _r = mov_rax_rbp(mul(sub(0, 8), 1000))
            let _r2 = movq_out_rax()
        } else {
            let _r = movsd_out_xmm0()
        }
        return 0
    }
    if eq(tp, 3) {
        let _r = gen_for(a, b, c)
        return 0
    }
    if eq(tp, 5) {
        let l_start = new_label()
        let l_exit = new_label()
        let loop_exits = set1(loop_exits, loop_exits_n, l_exit)
        let loop_exits_n = add(loop_exits_n, 1)
        let _r = label_at(l_start)
        let _r2 = gen_cond_jcc(a, l_exit)
        let _r3 = gen_block(b)
        let _r4 = jmp_(l_start)
        let _r5 = label_at(l_exit)
        let loop_exits_n = sub(loop_exits_n, 1)
        return 0
    }
    if eq(tp, 4) {
        let l_else = new_label()
        let l_end = new_label()
        let _r = gen_cond_jcc(a, l_else)
        let _r2 = gen_block(b)
        let _r3 = jmp_(l_end)
        let _r4 = label_at(l_else)
        if eq(c, 0) {
            let _r5 = 0
        } else {
            let _r5 = gen_block(c)
        }
        let _r6 = label_at(l_end)
        return 0
    }
    if eq(tp, 6) {
        let _r = jmp_(get(loop_exits, sub(loop_exits_n, 1)))
        return 0
    }
    if eq(tp, 8) {
        let _r = gen_expr(a, 0)
        let _r2 = movsd_xmm0_rbp(mul(sub(0, 8), 1000))
        let _r3 = leave_()
        let _r4 = pop_rax()
        let _r5 = jmp_rax()
        return 0
    }
    if eq(tp, 7) {
        return 0
    }
    if eq(tp, 16) {
        return 0
    }
    return sub(0, 1)
}

# ---------- 主流程 ----------
let top = top_block_no()
let idxs = blk_idxs(top)
# 第一遍：收集函数
let i = 0
while lt(i, len(idxs)) {
    let si = get(idxs, i)
    if eq(get(ast, si), 7) {
        let fn_id = get(ast, add(si, 1))
        let p_start = get(ast, add(si, 2))
        let body = get(ast, add(si, 3))
        let lab = new_label()
        let n = 0
        let j = p_start
        while eq(get(ast, j), 20) {
            let n = add(n, 1)
            let j = add(j, 4)
        }
        let funcs = set1(funcs, funcs_n, fn_id)
        let funcs_n = add(funcs_n, 1)
        let funcs = set1(funcs, funcs_n, body)
        let funcs_n = add(funcs_n, 1)
        let funcs = set1(funcs, funcs_n, lab)
        let funcs_n = add(funcs_n, 1)
        let funcs = set1(funcs, funcs_n, n)
        let funcs_n = add(funcs_n, 1)
        let funcs = set1(funcs, funcs_n, p_start)
        let funcs_n = add(funcs_n, 1)
    }
    let i = add(i, 1)
}
# 收集变量类型（递归所有块）
let bi = 0
while lt(bi, add(top, 1)) {
    let _r = collect_types(bi)
    let bi = add(bi, 1)
}
# 收集全局变量 id（T_GLOBAL=16：cnt, n1, n2）
let gi3 = 0
while lt(gi3, len(ast)) {
    if eq(get(ast, gi3), 16) {
        let cnt3 = get(ast, add(gi3, 1))
        if ge(cnt3, 1) {
            let gv = get(ast, add(gi3, 2))
            if ge(gv, 12) {
                if eq(glob_slot(gv), -1) {
                    let global_ids = set1(global_ids, global_ids_n, gv)
                    let global_ids_n = add(global_ids_n, 1)
                }
            }
        }
        if ge(cnt3, 2) {
            let gv2 = get(ast, add(gi3, 3))
            if ge(gv2, 12) {
                if eq(glob_slot(gv2), -1) {
                    let global_ids = set1(global_ids, global_ids_n, gv2)
                    let global_ids_n = add(global_ids_n, 1)
                }
            }
        }
    }
    let gi3 = add(gi3, 4)
}
# 收集 tensor 字面量（生成顺序：先 main 流程（top 块非 def 语句），
# 再函数段按 funcs 顺序；块/表达式递归——与 gen_expr 的 tensor_idx 分配顺序严格一致）
def collect_expr(e) {
    let tp = get(ast, e)
    if eq(tp, 14) {
        let elems = blk_idxs(get(ast, add(e, 2)))
        let tensors = app(tensors, mk(len(elems)))
        let ej = 0
        while lt(ej, len(elems)) {
            let tensors = app(tensors, mk(get(ast, add(get(elems, ej), 1))))
            let ej = add(ej, 1)
        }
        return 0
    }
    if eq(tp, 13) {
        let args = blk_idxs(get(ast, add(e, 2)))
        let aj = 0
        while lt(aj, len(args)) {
            let _r = collect_expr(get(args, aj))
            let aj = add(aj, 1)
        }
    }
    return 0
}
def collect_stmt(s) {
    let tp = get(ast, s)
    if eq(tp, 1) {
        let _r = collect_expr(get(ast, add(s, 2)))
    }
    if eq(tp, 2) {
        let _r = collect_expr(get(ast, add(s, 1)))
    }
    if eq(tp, 8) {
        let _r = collect_expr(get(ast, add(s, 1)))
    }
    if eq(tp, 3) {
        let _r = collect_block(get(ast, add(s, 3)))
    }
    if eq(tp, 5) {
        let _r = collect_expr(get(ast, add(s, 1)))
        let _r2 = collect_block(get(ast, add(s, 2)))
    }
    if eq(tp, 4) {
        let _r = collect_expr(get(ast, add(s, 1)))
        let _r2 = collect_block(get(ast, add(s, 2)))
        if lt(0, get(ast, add(s, 3))) {
            let _r3 = collect_block(get(ast, add(s, 3)))
        }
    }
    if eq(tp, 9) {
        let _r = collect_expr(get(ast, add(s, 2)))
    }
    return 0
}
def collect_block(blk) {
    let sts = blk_idxs(blk)
    let si2 = 0
    while lt(si2, len(sts)) {
        let _r = collect_stmt(get(sts, si2))
        let si2 = add(si2, 1)
    }
    return 0
}
# main 流程（top 块非 def 语句，按块顺序）
let sts0 = blk_idxs(top)
let si0 = 0
while lt(si0, len(sts0)) {
    let s0 = get(sts0, si0)
    if eq(get(ast, s0), 7) {
        let _sk = 0
    } else {
        let _r = collect_stmt(s0)
    }
    let si0 = add(si0, 1)
}
# 函数段（funcs 顺序）
let fi2 = 0
while lt(fi2, funcs_n) {
    let _r = collect_block(get(funcs, add(fi2, 1)))
    let fi2 = add(fi2, 5)
}
# 第二遍：main 流程（跳过 def）
let _r = push_rbp()
let _r2 = mov_rbp_rsp()
let _r3 = sub_rsp_imm()
# 输入保存：rcx = 输入指针 → [rbp+1024]
let _r3b = mov_rax_rcx()
let _r3c = mov_rbp_rax(1024)
# heap 初始化：heap 槽 = heap_base（数据区尾）
let _r4 = lea_rax_rip_kind(3, 0)
let _r5 = mov_rcx_rax()
let _r6 = lea_rax_rip_kind(4, 0)
let _r7 = emit_bytes(tensor([0x48, 0x89, 0x01]))
let i2 = 0
while lt(i2, len(idxs)) {
    let si = get(idxs, i2)
    if eq(get(ast, si), 7) {
        let i2 = add(i2, 1)
    } else {
        let _r8 = gen_stmt(si)
        let i2 = add(i2, 1)
    }
}
let _r9 = movsd_xmm0_rip_out()
let _r10 = leave_()
let _r11 = ret_()
# 函数段
let fi = 0
while lt(fi, funcs_n) {
    let fbody = get(funcs, add(fi, 1))
    let flab = get(funcs, add(fi, 2))
    let fnp = get(funcs, add(fi, 3))
    let fpst = get(funcs, add(fi, 4))
    let _r = label_at(flab)
    let _r2 = push_rbp()
    let _r3 = mov_rbp_rsp()
    let _r4 = sub_rsp_imm()
    let cur_params = empty()
    let j = fpst
    let k = 0
    while lt(k, fnp) {
        let cur_params = app(cur_params, mk(get(ast, add(j, 1))))
        let cur_params = app(cur_params, mk(k))
        let j = add(j, 4)
        let k = add(k, 1)
    }
    let _r5 = gen_block(fbody)
    let _r6 = pxor_xmm0()
    let _r7 = leave_()
    let _r8 = pop_rax()
    let _r9 = jmp_rax()
    let fi = add(fi, 5)
}

# 数据区：[常数池][OUT 槽][HEAP 槽][tensor 静态区]
let data_start = len(code)
let ci = 0
while lt(ci, consts_n) {
    let code = app(code, dbl64(get(consts, ci)))
    let ci = add(ci, 1)
}
let out_pos = len(code)
let code = app(code, dbl64(0))
let out_addr = add(data_start, mul(8, consts_n))
let heap_slot_addr = add(out_addr, 8)
let code = app(code, dbl64(0))
let globals_addr = add(heap_slot_addr, 8)
let gsi2 = 0
while lt(gsi2, global_ids_n) {
    let code = app(code, dbl64(0))
    let gsi2 = add(gsi2, 1)
}
let tensor_addr = add(globals_addr, mul(8, global_ids_n))
let ti = 0
while lt(ti, len(tensors)) {
    let tlen = get(tensors, ti)
    let code = app(code, pack64(tlen))
    let ej2 = 0
    while lt(ej2, tlen) {
        let code = app(code, dbl64(get(tensors, add(ti, add(ej2, 1)))))
        let ej2 = add(ej2, 1)
    }
    let ti = add(ti, add(tlen, 1))
}
# tensor 静态区字节数（用于 't' 偏移与 heap_base）
let tb = 0
let ti2 = 0
while lt(ti2, len(tensors)) {
    let tb = add(tb, mul(8, add(get(tensors, ti2), 1)))
    let ti2 = add(ti2, add(get(tensors, ti2), 1))
}
let heap_base_addr = add(tensor_addr, tb)

# patch fixups：kind 0=c 1=o 2=l 3=h 4=b 5=t
let f = 0
while lt(f, fixups_n) {
    let pos = get(fixups, f)
    let kind = get(fixups, add(f, 1))
    let target = get(fixups, add(f, 2))
    let addr = 0
    if eq(kind, 0) {
        let addr = add(data_start, mul(8, target))
    }
    if eq(kind, 1) {
        let addr = out_addr
    }
    if eq(kind, 2) {
        let addr = find_label(target)
    }
    if eq(kind, 3) {
        let addr = heap_slot_addr
    }
    if eq(kind, 4) {
        let addr = heap_base_addr
    }
    if eq(kind, 5) {
        # 't'：第 target 个字面量静态区偏移（tensors 平铺，用计数 n 与 target 比较）
        let off = 0
        let tk = 0
        let n = 0
        while lt(n, target) {
            let off = add(off, mul(8, add(get(tensors, tk), 1)))
            let tk = add(tk, add(get(tensors, tk), 1))
            let n = add(n, 1)
        }
        let addr = add(tensor_addr, off)
    }
    if eq(kind, 6) {
        # 'g'：第 target 个全局变量槽
        let addr = add(globals_addr, mul(8, target))
    }
    # disp 计算：rel = addr - IP。多数 rel32 指令前缀 3 字节（lea 48 8D 05、mov 48 8B 05、jcc 0F 8X、jmp E9），
    # disp 字段位置 pos 满足执行时 RIP = pos+4，故 rel = addr-(pos+4)。
    # movsd xmm0,[rip+disp]（F2 0F 10 05）与 movsd [rip+disp],xmm0（F2 0F 11 05）前缀 4 字节：
    # 执行时 RIP = pos+3，须特判 ip = pos+3。tl 无 and/or 算子，用 mul(eq) 实现。
    let ok = band(ge(pos, 4), 1)
    let b0 = mul(get(code, sub(pos, 4)), ok)
    let b1 = mul(get(code, sub(pos, 3)), ok)
    let b2 = mul(get(code, sub(pos, 2)), ok)
    let b3 = mul(get(code, sub(pos, 1)), ok)
    let is_m = mul(mul(eq(b0, 242), eq(b1, 15)), mul(add(eq(b2, 16), eq(b2, 17)), eq(b3, 5)))
    let ip = sub(add(pos, 4), is_m)
    let rel = sub(addr, ip)
    let code = set1(code, pos, band(rel, 255))
    let code = set1(code, add(pos, 1), band(bshr(rel, 8), 255))
    let code = set1(code, add(pos, 2), band(bshr(rel, 16), 255))
    let code = set1(code, add(pos, 3), band(bshr(rel, 24), 255))
    let f = add(f, 3)
}
print(code)
