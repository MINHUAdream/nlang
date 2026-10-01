# tl v0.3 —— 多头 scaled dot-product attention（H=2 头, S=3, Dh=2）
# 3D 张量语义：[H, S, Dh] 每头独立做 attention；softmax 沿最后一维
# 单头公式：scores = Q·Kᵀ / √Dh → attn = softmax(scores) → ctx = attn·V

let Q = tensor([[[0.5, 0.1], [0.2, 0.3], [0.1, 0.4]], [[0.3, 0.2], [0.4, 0.1], [0.2, 0.5]]])   # [2,3,2]
let K = tensor([[[0.1, 0.2], [0.3, 0.4], [0.2, 0.1]], [[0.4, 0.3], [0.1, 0.2], [0.3, 0.1]]])   # [2,3,2]
let V = tensor([[[1.0, 0.0], [0.0, 1.0], [0.5, 0.5]], [[0.0, 1.0], [1.0, 0.0], [0.5, 0.5]]])   # [2,3,2]

let d = tensor([1.4142135623730951])   # sqrt(Dh) = sqrt(2)

# 每头分数 [2,3,3]：batch matmul + 沿最后两维转置
let qk = scale(matmul(Q, transpose(K)), d)

# 每头注意力权重 [2,3,3]：沿最后一维 softmax（行和为 1）
let attn = softmax(qk)

# 每头上下文 [2,3,2]：batch matmul
let ctx = matmul(attn, V)

print(attn)
print(ctx)
