# GraphCPP 数据集格式

## 数据集位置

```
dataset/
├── train.csv   # 训练集
├── val.csv     # 验证集
└── test.csv    # 测试集
```

## CSV格式

```csv
name,smiles,label
TAT,CC(C)C(NC(=O)...,1
Penetratin,CC(C)C(NC(=O)...,1
Random,CC(C)C(NC(=O)...,0
```

- `name`: 肽名称
- `smiles`: SMILES格式序列
- `label`: 1=CPP, 0=Non-CPP

## 数据来源

训练数据主要来自:
- CPP1708 数据集(1708条肽)
- 经典CPP(TAT, Penetratin等)及其变体
- MLCPP2 独立测试集

## 特征化流程

1. **SMILES → RDKit Mol对象**: `Chem.MolFromSmiles()`
2. **Mol → 图数据**: `MolGraphConvFeaturizer`
3. **图数据 → PyG Data**: `GraphData.to_pyg_graph()`
4. **添加指纹**: 拓扑指纹 `fp_dict['topological'].GetFingerprint(mol)`

## 融合引擎集成

在融合引擎中使用GraphCPP作为递送模块:

```python
# 特征工程
features = {
    'cpp_probability': predict_cpp(sequence)['probability'],
    'net_charge': calculate_charge(sequence),
    'hydrophobicity': calculate_hydrophobicity(sequence),
}

# 输入到六功效模型
efficacy_score = efficacy_model.predict(features)
```

## 粗筛过滤示例

```python
def pre_screen(peptide):
    cpp_score = predict_cpp(peptide)['probability']
    if cpp_score < 0.3:  # 递送潜力过低
        return False
    if calculate_charge(peptide) > +5:  # 电荷极端
        return False
    if calculate_hydrophobicity(peptide) > 0.8:  # 疏水性极端
        return False
    return True

candidates = [p for p in all_candidates if pre_screen(p.sequence)]
```