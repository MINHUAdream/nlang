# tl v0.3 —— 一个完整的 Transformer encoder block（参数化、可训练）
# 结构：Q/K/V 投影 → 注意力 → 残差 → FFN → 残差 → MSE 损失
# 单样本 [S=3, D=4]，单头（多头见 attention3d.tl）

# 输入 [3,4]
let X = tensor([[1.0, 0.0, 0.5, 0.2], [0.3, 1.0, 0.1, 0.4], [0.2, 0.5, 1.0, 0.3]])

# —— 注意力子层：三个可训练投影 + 缩放点积注意力 ——
let Wq = param([4, 4])
let Wk = param([4, 4])
let Wv = param([4, 4])
let Q = matmul(X, Wq)                                  # [3,4]
let K = matmul(X, Wk)                                  # [3,4]
let V = matmul(X, Wv)                                  # [3,4]
let d = tensor([2.0])                                  # sqrt(D) = sqrt(4)
let scores = scale(matmul(Q, transpose(K)), d)         # [3,3]
let attn = softmax(scores)                             # [3,3] 行和为 1
let ctx = matmul(attn, V)                              # [3,4]
let h = add(ctx, X)                                    # 残差连接 ①

# —— 前馈子层：relu(h·W1 + b1) → 输出 ——
let W1 = param([4, 4])
let b1 = param([4])
let f = add(matmul(relu(h), W1), b1)                   # [3,4]
let out = add(f, h)                                    # 残差连接 ②

# —— 损失：输出逼近输入（自重建目标，block 语义验证用） ——
let target = tensor([[1.0, 0.0, 0.5, 0.2], [0.3, 1.0, 0.1, 0.4], [0.2, 0.5, 1.0, 0.3]])
let loss = mean(square(sub(out, target)))

print(out)
print(loss)
