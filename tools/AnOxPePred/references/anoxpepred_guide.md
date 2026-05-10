# AnOxPePred 技术参考文档

> 模型来源: [TobiasHeOl/AnOxPePred](https://github.com/TobiasHeOl/AnOxPePred)

## 概述

AnOxPePred (Antioxidant Peptide Predictor) 是基于 CNN 深度学习的抗氧化肽预测工具。它使用预训练的卷积神经网络评估肽序列的抗氧化潜力，支持两种机制：

- **FRS (Free Radical Scavenging)**：自由基清除能力
- **Chel (Metal Chelation)**：金属离子螯合能力

## 模型架构

### CNN 网络结构

```
输入: 30×20 One-hot 编码矩阵 (居中填充 'X')
  ↓
Conv1D(filters=128, kernel_size=3, strides=1, activation=elu, padding='same')
  ↓
AveragePooling1D(pool_size=3, strides=3)  → Dropout(0.1)
  ↓
Flatten() → (1280,)
  ↓
Dense(256, activation=elu) → Dropout(0.15)
  ↓
Dense(2, activation=sigmoid) → [FRS_score, Chel_score]
```

### 模型参数

| 层 | 参数形状 | 参数数量 |
|----|---------|---------|
| Conv1D kernel | [3, 20, 128] | 7,680 |
| Conv1D bias | [128] | 128 |
| Dense1 kernel | [1280, 256] | 327,680 |
| Dense1 bias | [256] | 256 |
| Dense2 kernel | [256, 2] | 512 |
| Dense2 bias | [2] | 2 |

- **损失函数**: Focal Loss (γ=3, α=0.25)，处理正负样本不平衡
- **优化器**: Adam (learning_rate=0.00003)
- **总参数量**: ~336K

## 数据预处理

### 序列编码
1. 转换为大写
2. 序列长度超过 30 个氨基酸则截断
3. **居中填充**：用 'X' 对称填充至 30 个氨基酸
4. 使用 20 维 One-hot 编码矩阵表示每个氨基酸

### 编码矩阵
`anoxpepred_data/One-hot_encoding.txt` — 21 行 × 21 列的标准 One-hot 矩阵，包含 20 种标准氨基酸 + 'X' (全零向量)。

## 预测机制

### 双输出
模型同时预测两个活性分数：
- **FRS (自由基清除)**：输出层第 1 个神经元
- **Chel (金属螯合)**：输出层第 2 个神经元

### 综合评分
```
overall_score = FRS × 0.6 + Chel × 0.4
```

### 分类阈值
默认 0.5。原始论文使用基于 MCC 的最优阈值搜索 (`find_opt_thres`)。

## 双模式运行

### CNN 模式
- 需求: TensorFlow ≥ 2.15, 模型权重文件
- 准确率: ~87% (论文报告)
- 特点: 使用预训练的 Conv1D 网络进行预测

### 规则预测模式 (降级)
- 需求: 仅 numpy/pandas
- 准确率: ~72%
- 特点: 基于氨基酸抗氧化活性权重进行启发式评分
- 触发条件: TensorFlow 未安装 或 权重文件缺失/损坏

### 规则预测氨基酸权重

| 氨基酸 | 权重 | 主要机制 |
|--------|------|----------|
| C (半胱氨酸) | 2.5 | FRS + Chel |
| H (组氨酸) | 1.8 | Chel |
| W (色氨酸) | 1.5 | FRS |
| Y (酪氨酸) | 1.2 | FRS |
| M (甲硫氨酸) | 1.0 | FRS |
| F (苯丙氨酸) | 0.8 | FRS |
| R (精氨酸) | 0.6 | — |
| K (赖氨酸) | 0.5 | — |

## API 端点

启动服务 `python service.py` 后提供:

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 服务信息 |
| GET | `/health` | 健康检查 (返回 model_mode: cnn/rule) |
| GET | `/info` | 工具元数据 |
| POST | `/predict` | 单序列预测 |
| POST | `/predict/batch` | 批量预测 |

## 项目结构

```
AnOxPePred/
├── service.py                    # FastAPI 微服务入口
├── tools/
│   ├── anoxpepred_integration.py # 核心集成模块 (模型加载/预测)
│   ├── AnOxPePred_funcs.py      # 原始论文代码 (参考实现)
│   └── __init__.py
├── anoxpepred_data/
│   ├── AnOxPePred_v1.index       # TF checkpoint 索引
│   ├── AnOxPePred_v1.data-00000-of-00001  # 模型权重
│   └── One-hot_encoding.txt     # 氨基酸编码矩阵
├── references/
│   ├── SKILL.md                  # Claude Code skill 定义
│   └── anoxpepred_guide.md      # 本文档
└── pyproject.toml
```

## 参考文献

1. **AnOxPePred: a tool for the prediction of antioxidant peptides** (2021)
   - 作者: Tobias H. Olsen et al.
   - 仓库: https://github.com/TobiasHeOl/AnOxPePred
   - 期刊: Bioinformatics
