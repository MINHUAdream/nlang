# tl v0.2 —— 单头 scaled dot-product attention 前向（S=3 序列, D=4 维度）
# 这是 Transformer 的核心算子，用 tl 语言直接表达

# 查询 / 键 / 值（示例数据，便于对照参考实现验证）
let Q = tensor([[0.5, 0.1, 0.2, 0.3], [0.1, 0.4, 0.6, 0.1], [0.3, 0.2, 0.1, 0.5]])   # [3,4]
let K = tensor([[0.2, 0.3, 0.4, 0.1], [0.5, 0.1, 0.2, 0.3], [0.1, 0.6, 0.3, 0.2]])   # [3,4]
let V = tensor([[1.0, 0.0], [0.0, 1.0], [0.5, 0.5]])                                   # [3,2]

# d_k = 4 → sqrt(d_k) = 2，缩放因子
let d = tensor([2.0])

# 注意力分数 = Q·Kᵀ / √d  →  [3,3]
let qk = scale(matmul(Q, transpose(K)), d)

# 注意力权重 = softmax(分数)  →  [3,3]，每行和为 1
let attn = softmax(qk)

# 上下文 = 注意力权重 · V  →  [3,2]
let ctx = matmul(attn, V)

print(attn)
print(ctx)
