# tl v0.1 demo —— 一个 3→2→1 的两层小网络（正向 + 自动微分）
# 语法要点：张量字面量 tensor([...])、可训练参数 param([...])、
#          算子 matmul/add/relu/sum 均为前缀函数形式

# 输入向量（形状 [3]）
let x = tensor([1.0, 2.0, 3.0])

# 第一层：权重 [2,3] + 偏置 [2]，ReLU 激活
let W1 = param([2, 3])
let b1 = param([2])
let h1 = add(matmul(W1, x), b1)
let a1 = relu(h1)

# 第二层：权重 [1,2] + 偏置 [1]，输出标量
let W2 = param([1, 2])
let b2 = param([1])
let y = add(matmul(W2, a1), b2)

# 标量损失（全元素求和）
let loss = sum(y)

print(x)
print(W1)
print(h1)
print(a1)
print(y)
print(loss)
