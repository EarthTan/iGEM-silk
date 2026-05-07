---
name: graphcpp
description: 当用户需要使用图神经网络预测细胞穿透肽(CPP)时触发此技能。支持本地批量预测、特征导出，可作为融合引擎中递送模块的信号来源。
created: 2026-04-18
version: 1.0.0
last_updated: 2026-04-18
---

# GraphCPP

## What It Is

GraphCPP 是一个基于图神经网络(GNN)的细胞穿透肽(Cell-Penetrating Peptide, CPP)预测工具。使用 GraphSAGE 卷积层将肽序列转换为分子图表示，实现 SOTA 级别的 CPP 预测性能(MCC 0.5787, AUC 0.8459)。

**模型来源**: ⚠️ **预训练模型，可直接加载使用，无需训练**

GraphCPP 仓库在 `model/checkpoints/` 目录下提供了官方预训练模型 (`epoch=22-step=69.ckpt`)。该模型已经过训练和验证，**开箱即用**。

如需重新训练，仓库也提供了完整训练代码，但通常不需要这样做。

**解决的问题**: 预测给定肽序列是否具有细胞穿透能力

**在融合引擎中的角色**:
- 递送/透皮相关的序列层 proxy
- 六功效模型的特征输入
- 粗筛与融合引擎的信号来源

## When to Use

- 需要预测候选肽的细胞穿透能力时
- 需要批量筛选大量肽序列的 CPP 潜力时
- 需要将 CPP 概率作为下游模型的输入特征时
- 需要在融合前剔除递送潜力过低的序列时

## Methodology

### 核心原理

1. **分子图表示**: 将肽序列转换为 RDKit 分子图(原子=节点, 化学键=边)
2. **图特征化**: 使用 MolGraphConvFeaturizer 提取节点和边的特征
3. **图神经网络**: 使用 GraphSAGE 卷积层进行消息传递和特征学习
4. **分类输出**: Sigmoid 激活后的二分类概率(阈值 0.5)

### 特征融合

- 图卷积层输出的节点嵌入
- 拓扑指纹(topological fingerprint)
- 图池化(mean pooling)得到的全局表示
- 全连接层输出最终预测

## Operations

### 环境安装

```bash
cd GraphCPP/
uv init --no-readme
source .venv/bin/activate

# 安装核心依赖
uv pip install torch rdkit deepchem lightning streamlit torchvision
uv pip install --no-build-isolation torch-scatter torch-sparse
uv pip install torch-geometric
```

### 预测单个序列

```python
import torch
import yaml
from rdkit import Chem
from graphcpp.lightning import GraphCPPModule
from graphcpp.dataset import _featurize_mol
from graphcpp.fp_generators import fp_dict

# 加载模型
with open('model/hparams.yaml', 'r') as f:
    hparams = yaml.safe_load(f)
model = GraphCPPModule.load_from_checkpoint(
    checkpoint_path="model/checkpoints/epoch=22-step=69.ckpt",
    map_location=torch.device('cpu')
)
model.eval()
model.freeze()

# 预测函数
def predict_cpp(fasta_seq):
    mol = Chem.MolFromFASTA(fasta_seq)
    if mol is None:
        return None
    data = _featurize_mol(mol)
    fp = fp_dict[hparams['fingerprint_type']].GetFingerprint(mol)
    data.fp = torch.tensor([fp], dtype=torch.float32)
    
    with torch.no_grad():
        prediction = model(data)[0]
        probability = torch.sigmoid(prediction).item()
        is_cpp = probability >= 0.5
    return {'probability': probability, 'is_cpp': is_cpp}

# 示例
result = predict_cpp("GRKKRRQRRRPPQ")  # TAT肽
print(f"CPP概率: {result['probability']:.4f}")
```

### 批量预测脚本

```python
import pandas as pd
from rdkit import Chem
import torch
import yaml
from graphcpp.lightning import GraphCPPModule
from graphcpp.dataset import _featurize_mol
from graphcpp.fp_generators import fp_dict

# 加载模型
with open('model/hparams.yaml', 'r') as f:
    hparams = yaml.safe_load(f)
model = GraphCPPModule.load_from_checkpoint(
    checkpoint_path="model/checkpoints/epoch=22-step=69.ckpt",
    map_location=torch.device('cpu')
)
model.eval()
model.freeze()

def predict_batch(fasta_list):
    results = []
    for seq in fasta_list:
        mol = Chem.MolFromFASTA(seq)
        if mol is None:
            results.append({'sequence': seq, 'probability': None, 'is_cpp': None})
            continue
        data = _featurize_mol(mol)
        fp = fp_dict[hparams['fingerprint_type']].GetFingerprint(mol)
        data.fp = torch.tensor([fp], dtype=torch.float32)
        
        with torch.no_grad():
            prediction = model(data)[0]
            probability = torch.sigmoid(prediction).item()
            is_cpp = probability >= 0.5
        results.append({'sequence': seq, 'probability': probability, 'is_cpp': is_cpp})
    return results

# 读取FASTA文件
df = pd.read_csv("candidates.csv")  # 需要 name, sequence 列
predictions = predict_batch(df['sequence'].tolist())
df['cpp_probability'] = [p['probability'] for p in predictions]
df['cpp_prediction'] = ['Yes' if p['is_cpp'] else 'No' for p in predictions]
df.to_csv("cpp_predictions.csv", index=False)
```

### 启动 Web UI

```bash
cd GraphCPP/
source .venv/bin/activate
streamlit run dashboard.py
# 浏览器访问 http://localhost:8501
```

## Inputs and Outputs

### 输入格式

**FASTA格式(推荐)**
```
>Peptide1
GRKKRRQRRRPPQ
>Peptide2
RQIKIWFQNRRMKWKK
```

**SMILES格式(CSV)**
```csv
name,smiles
TAT,CC(C)C(NC(=O)...
```

### 输出格式

| 字段 | 类型 | 说明 |
|------|------|------|
| Name | string | 肽名称 |
| Probability | float (0-1) | CPP概率分数 |
| Cell-Penetrating | Yes/No | 二分类预测 |

## Examples

**例1: 经典CPP预测**
```python
predict_cpp("GRKKRRQRRRPPQ")  # TAT肽 -> CPP概率 > 0.9
predict_cpp("RQIKIWFQNRRMKWKK")  # Penetratin -> CPP概率 > 0.9
```

**例2: 非CPP识别**
```python
predict_cpp("ACDEFGHIKLMNPQRSTVY")  # 随机序列 -> CPP概率 < 0.3
```

## Limitations

1. **序列长度**: 最佳范围 5-40 个氨基酸，>100aa 精度下降
2. **融合肽**: 针对单链CPP训练，对"功效肽+linker+CPP"融合结构未优化
3. **非天然氨基酸**: 依赖RDKit的MolFromFASTA，默认只支持20种标准氨基酸
4. **特征导出**: 当前版本主要输出分类结果，中间层特征需修改代码提取

## References Index

| File | Contents |
|------|----------|
| `references/install.md` | 详细安装说明和依赖版本 |
| `references/model-details.md` | 模型架构和训练细节 |
| `references/dataset.md` | 数据集格式和处理流程 |