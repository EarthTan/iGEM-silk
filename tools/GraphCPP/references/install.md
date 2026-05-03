# GraphCPP 安装指南

## ⚠️ 重要说明：预训练模型，开箱即用

GraphCPP 提供**官方预训练模型**，位于 `model/checkpoints/epoch=22-step=69.ckpt`。

**不需要自己训练模型**。安装依赖后，直接加载模型即可进行预测。

如需重新训练模型（可选）：
```bash
python main.py --dataset dataset  # 完整训练
python cv.py                      # 交叉验证
```

## 环境要求

- Python 3.9+
- CUDA 11.7+(可选，用于GPU加速)
- 内存: 4GB+(批量100条)

## 使用 uv 安装(推荐)

```bash
cd GraphCPP/
uv init --no-readme
source .venv/bin/activate

# 安装核心依赖
uv pip install torch rdkit deepchem lightning streamlit torchvision

# 安装torch-geometric依赖(需要特殊处理)
uv pip install --no-build-isolation torch-scatter torch-sparse
uv pip install torch-geometric
```

## 使用 conda/mamba 安装(备选)

```bash
# GPU版本
mamba env create -f environment.yml
mamba activate graphcpp

# CPU版本
mamba env create -f cpu.yml
mamba activate graphcpp_cpu
```

## 依赖清单

| 包 | 版本要求 | 用途 |
|----|---------|------|
| python | 3.9+ | 运行环境 |
| pytorch | 1.13.1+ | 深度学习框架 |
| pytorch-geometric | 2.3.0+ | 图神经网络 |
| rdkit | 2022.09.5+ | 分子处理 |
| deepchem | 2.7.1+ | 分子特征化 |
| lightning | 2.0.1+ | 训练框架 |
| streamlit | 1.21.0+ | Web UI |
| torchvision | 0.14.1+ | 数据集工具 |

## 验证安装

```bash
source .venv/bin/activate
python -c "import torch; import rdkit; import deepchem; import lightning; import torch_geometric; print('All imports successful!')"
```

## 常见问题

### CUDA内存不足

```python
# 使用CPU版本
model = GraphCPPModule.load_from_checkpoint(
    checkpoint_path="model/checkpoints/epoch=22-step=69.ckpt",
    map_location=torch.device('cpu')
)
```

### 缺少tensorflow/dgl等依赖

这些是可选依赖，不影响核心预测功能:
- tensorflow: 跳过(DeepChem的部分模型需要)
- dgl: 跳过(图神经网络备选后端)
- transformers: 跳过(某些预训练模型需要)