# BepiPred-3.0 特征提取函数

本文档提供 BepiPred-3.0 输出结果的特征提取和后处理函数。

## 特征提取函数

```python
import pandas as pd

def extract_epitope_features(csv_path, threshold=0.1512):
    """从 BepiPred 输出提取特征"""
    df = pd.read_csv(csv_path)

    return {
        'max_epitope_score': df['BepiPred-3.0 score'].max(),
        'mean_epitope_score': df['BepiPred-3.0 score'].mean(),
        'epitope_residue_count': (df['BepiPred-3.0 score'] > threshold).sum(),
        'epitope_ratio': (df['BepiPred-3.0 score'] > threshold).mean(),
        'max_linear_score': df['BepiPred-3.0 linear epitope score'].max(),
    }

def calculate_epitope_penalty(csv_path, threshold=0.1512):
    """计算表位惩罚分数（用于融合引擎）"""
    df = pd.read_csv(csv_path)

    high_epitope_ratio = (df['BepiPred-3.0 score'] > threshold).mean()
    max_score = df['BepiPred-3.0 score'].max()

    # 惩罚分数
    penalty = high_epitope_ratio * 0.5 + max_score * 0.5
    return penalty

def epitope_based_filter(csv_path, max_epitope_ratio=0.3, max_score_threshold=0.5):
    """基于表位预测的粗筛"""
    df = pd.read_csv(csv_path)

    epitope_ratio = (df['BepiPred-3.0 score'] > 0.1512).mean()
    max_score = df['BepiPred-3.0 score'].max()

    if epitope_ratio > max_epitope_ratio or max_score > max_score_threshold:
        return False  # 不通过筛选
    return True  # 通过筛选
```

## 使用示例

```python
from pathlib import Path
from bp3_feature_functions import extract_epitope_features, calculate_epitope_penalty, epitope_based_filter

csv_path = Path("output/raw_output.csv")

# 提取特征
features = extract_epitope_features(csv_path)
print(f"Max epitope score: {features['max_epitope_score']}")
print(f"Epitope ratio: {features['epitope_ratio']}")

# 计算惩罚分数
penalty = calculate_epitope_penalty(csv_path)
print(f"Epitope penalty: {penalty}")

# 粗筛判断
passed = epitope_based_filter(csv_path)
print(f"Filter passed: {passed}")
```

## 函数返回值说明

### extract_epitope_features 返回值

| 字段 | 类型 | 说明 |
|------|------|------|
| `max_epitope_score` | float | 所有残基的最大表位分数 |
| `mean_epitope_score` | float | 所有残基的平均表位分数 |
| `epitope_residue_count` | int | 超过阈值的表位残基数量 |
| `epitope_ratio` | float | 表位残基占总残基的比例 |
| `max_linear_score` | float | 最大线性表位分数 |

### calculate_epitope_penalty 返回值

| 字段 | 类型 | 说明 |
|------|------|------|
| `penalty` | float | 惩罚分数，范围 0-1。越高表示免疫原性风险越大 |

### epitope_based_filter 返回值

| 字段 | 类型 | 说明 |
|------|------|------|
| `passed` | bool | True=通过筛选，False=被拒绝 |
