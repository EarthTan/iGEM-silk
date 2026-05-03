# MHCflurry 结合类别阈值解释

## 概述

本文档详细解释MHCflurry中使用的结合类别阈值，包括阈值定义、生物学意义、应用场景和自定义方法。正确理解这些阈值对于准确解释预测结果至关重要。

## 标准阈值

### 默认阈值

MHCflurry使用以下标准阈值对结合亲和力进行分类：

| 结合类别 | 阈值范围 (nM) | 描述 |
|----------|---------------|------|
| **强结合子** | ≤ 50 nM | 高亲和力结合，可能引发强烈的T细胞反应 |
| **弱结合子** | 50-500 nM | 中等亲和力结合，可能引发较弱的T细胞反应 |
| **非结合子** | > 500 nM | 低亲和力结合，不太可能引发T细胞反应 |

### 阈值生物学基础

这些阈值基于免疫学研究和实验数据：

1. **50 nM阈值**:
   - 基于T细胞激活实验：亲和力低于50 nM的肽通常能有效激活T细胞
   - 免疫优势表位研究：大多数免疫优势表位的亲和力低于50 nM
   - 疫苗设计标准：候选疫苗肽通常要求亲和力低于50 nM

2. **500 nM阈值**:
   - 基于T细胞识别下限：亲和力高于500 nM的肽通常无法有效激活T细胞
   - 阴性对照标准：实验中的阴性对照肽通常亲和力高于500 nM
   - 背景结合水平：非特异性结合的典型阈值

## 阈值详细解释

### 强结合子 (≤ 50 nM)

#### 生物学特征
- **高亲和力结合**: 肽与MHC分子的结合非常稳定
- **有效T细胞激活**: 能够有效激活CD8+ T细胞
- **免疫原性高**: 很可能在体内引发免疫反应
- **表位可能性大**: 很可能是免疫优势表位

#### 应用场景
1. **疫苗设计**: 优先选择强结合子作为疫苗候选
2. **肿瘤新抗原预测**: 强结合子更可能是有效的新抗原
3. **诊断试剂开发**: 强结合子适合作为诊断抗原
4. **免疫学研究**: 强结合子是研究T细胞识别的理想模型

#### 示例
```python
# 强结合子示例
strong_binders = [
    ("SIINFEKL", "HLA-A*02:01", 25.5),    # 25.5 nM
    ("NLVPMVATV", "HLA-A*02:01", 12.3),   # 12.3 nM
    ("GILGFVFTL", "HLA-A*02:01", 8.7),    # 8.7 nM
]
```

### 弱结合子 (50-500 nM)

#### 生物学特征
- **中等亲和力结合**: 肽与MHC分子的结合稳定性中等
- **部分T细胞激活**: 可能激活T细胞，但效率较低
- **免疫原性中等**: 可能在特定条件下引发免疫反应
- **表位可能性中等**: 可能是亚优势表位

#### 应用场景
1. **次级候选筛选**: 当强结合子不足时考虑弱结合子
2. **广度优先策略**: 为了覆盖更多表位，包括弱结合子
3. **研究用途**: 研究亲和力与免疫原性的关系
4. **组合疗法**: 与其他免疫调节剂联合使用

#### 示例
```python
# 弱结合子示例
weak_binders = [
    ("RAKFKQLL", "HLA-A*02:01", 150.2),   # 150.2 nM
    ("CINGVCWTV", "HLA-A*02:01", 320.5),  # 320.5 nM
    ("YVLDHLIVV", "HLA-A*02:01", 480.3),  # 480.3 nM
]
```

### 非结合子 (> 500 nM)

#### 生物学特征
- **低亲和力结合**: 肽与MHC分子的结合不稳定
- **无效T细胞激活**: 通常无法激活T细胞
- **免疫原性低**: 不太可能在体内引发免疫反应
- **非表位**: 很可能是非免疫原性肽

#### 应用场景
1. **阴性对照**: 实验中的阴性对照
2. **特异性验证**: 验证预测工具的特异性
3. **背景评估**: 评估实验背景水平
4. **排除标准**: 从候选列表中排除

#### 示例
```python
# 非结合子示例
non_binders = [
    ("AAAAAAAA", "HLA-A*02:01", 1250.8),  # 1250.8 nM
    ("PPPPPPPP", "HLA-A*02:01", 980.3),   # 980.3 nM
    ("RRRRRRRR", "HLA-A*02:01", 750.6),   # 750.6 nM
]
```

## 百分位排名阈值

除了绝对亲和力阈值，MHCflurry还提供百分位排名，这是另一个重要的分类指标：

### 百分位排名阈值

| 百分位排名 | 分类 | 描述 |
|------------|------|------|
| **< 0.5%** | 极强结合 | 亲和力位于前0.5% |
| **0.5-2%** | 强结合 | 亲和力位于前0.5-2% |
| **2-10%** | 中等结合 | 亲和力位于前2-10% |
| **> 10%** | 弱结合 | 亲和力位于后90% |

### 百分位排名的优势

1. **等位基因标准化**: 考虑了不同等位基因的结合分布差异
2. **相对比较**: 相对于随机肽的排名，更生物学相关
3. **稳定性**: 对实验变异性的鲁棒性更好

### 使用示例

```python
def classify_by_percentile(percentile_rank):
    """根据百分位排名分类"""
    if percentile_rank < 0.005:  # 0.5%
        return "extremely_strong"
    elif percentile_rank < 0.02:  # 2%
        return "strong"
    elif percentile_rank < 0.10:  # 10%
        return "moderate"
    else:
        return "weak"

# 示例数据
samples = [
    ("SIINFEKL", 0.001),   # 0.1%
    ("NLVPMVATV", 0.008),  # 0.8%
    ("GILGFVFTL", 0.015),  # 1.5%
    ("RAKFKQLL", 0.050),   # 5.0%
    ("AAAAAAAA", 0.850),   # 85.0%
]

for peptide, percentile in samples:
    category = classify_by_percentile(percentile)
    print(f"{peptide}: {percentile:.3f} → {category}")
```

## 自定义阈值

### 为什么需要自定义阈值

在某些应用场景中，标准阈值可能不适用：

1. **特定疾病研究**: 某些疾病可能需要更严格或更宽松的阈值
2. **实验条件差异**: 不同的实验体系可能需要调整阈值
3. **保守策略**: 更保守的筛选策略需要更严格的阈值
4. **广度优先策略**: 为了覆盖更多可能性需要更宽松的阈值

### 自定义阈值方法

#### 方法1: 直接使用阈值分类

使用标准的 Class1AffinityPredictor 并在预测后应用自定义阈值：

```python
from mhcflurry import Class1AffinityPredictor

# 加载预测器
predictor = Class1AffinityPredictor.load()

# 预测
df = predictor.predict_to_dataframe(
    peptides=["SIINFEKL", "NLVPMVATV"],
    alleles=["HLA-A*02:01"]
)

# 自定义分类阈值
custom_strong_threshold = 100.0   # 放宽强结合阈值
custom_weak_threshold = 1000.0    # 放宽弱结合阈值

def classify_with_custom_threshold(affinity_nM, strong=50.0, weak=500.0):
    """使用自定义阈值的分类函数"""
    if affinity_nM <= strong:
        return "strong_binder"
    elif affinity_nM <= weak:
        return "weak_binder"
    else:
        return "non_binder"

# 应用自定义阈值
df["custom_class"] = df["prediction"].apply(
    lambda x: classify_with_custom_threshold(x, custom_strong_threshold, custom_weak_threshold)
)
print(df)
```

#### 方法2: 后处理分类

```python
def custom_classify(affinity_nM, thresholds):
    """自定义分类函数"""
    strong_thresh = thresholds.get("strong", 50.0)
    weak_thresh = thresholds.get("weak", 500.0)
    
    if affinity_nM <= strong_thresh:
        return "strong_binder"
    elif affinity_nM <= weak_thresh:
        return "weak_binder"
    else:
        return "non_binder"

# 使用示例
custom_thresholds = {"strong": 100.0, "weak": 1000.0}
affinity = 75.0  # nM
category = custom_classify(affinity, custom_thresholds)
print(f"亲和力 {affinity} nM: {category}")  # 输出: strong_binder
```

#### 方法3: 基于百分位排名的阈值

```python
def classify_by_percentile_custom(percentile_rank, thresholds):
    """基于百分位排名的自定义分类"""
    extremely_strong = thresholds.get("extremely_strong", 0.005)  # 0.5%
    strong = thresholds.get("strong", 0.02)  # 2%
    moderate = thresholds.get("moderate", 0.10)  # 10%
    
    if percentile_rank < extremely_strong:
        return "extremely_strong"
    elif percentile_rank < strong:
        return "strong"
    elif percentile_rank < moderate:
        return "moderate"
    else:
        return "weak"

# 使用示例
custom_percentile_thresholds = {
    "extremely_strong": 0.01,  # 1%
    "strong": 0.05,            # 5%
    "moderate": 0.20           # 20%
}

percentile = 0.03  # 3%
category = classify_by_percentile_custom(percentile, custom_percentile_thresholds)
print(f"百分位排名 {percentile:.3f}: {category}")  # 输出: strong
```

### 应用场景特定的阈值建议

#### 疫苗设计
```python
vaccine_thresholds = {
    "strong_binder": 50.0,     # 严格标准，确保高免疫原性
    "weak_binder": 200.0,      # 中等标准，考虑次级候选
    "percentile_strong": 0.01, # 前1%
    "percentile_weak": 0.05    # 前5%
}
```

#### 肿瘤新抗原预测
```python
neoantigen_thresholds = {
    "strong_binder": 100.0,    # 稍宽松，考虑突变特异性
    "weak_binder": 500.0,      # 标准
    "percentile_strong": 0.02, # 前2%
    "percentile_weak": 0.10    # 前10%
}
```

#### 诊断试剂开发
```python
diagnostic_thresholds = {
    "strong_binder": 20.0,     # 非常严格，确保高特异性
    "weak_binder": 100.0,      # 严格
    "percentile_strong": 0.005, # 前0.5%
    "percentile_weak": 0.02    # 前2%
}
```

#### 基础研究
```python
research_thresholds = {
    "strong_binder": 500.0,    # 宽松，包括更多样本
    "weak_binder": 5000.0,     # 非常宽松
    "percentile_strong": 0.10, # 前10%
    "percentile_weak": 0.50    # 前50%
}
```

## 阈值验证

### 实验验证方法

1. **ELISA结合实验**: 直接测量肽-MHC结合亲和力
2. **T细胞激活实验**: 测量肽诱导的T细胞反应
3. **MHC多聚体染色**: 检测肽特异性T细胞
4. **免疫动物实验**: 评估肽的体内免疫原性

### 验证数据集

使用已知的免疫原性肽数据集验证阈值：

```python
def validate_thresholds(validation_data, thresholds):
    """验证阈值在已知数据集上的性能"""
    true_positives = 0
    false_positives = 0
    true_negatives = 0
    false_negatives = 0
    
    for peptide, affinity, is_immunogenic in validation_data:
        # 使用阈值分类
        if affinity <= thresholds["strong_binder"]:
            predicted_immunogenic = True
        else:
            predicted_immunogenic = False
        
        # 统计
        if is_immunogenic and predicted_immunogenic:
            true_positives += 1
        elif not is_immunogenic and predicted_immunogenic:
            false_positives += 1
        elif not is_immunogenic and not predicted_immunogenic:
            true_negatives += 1
        elif is_immunogenic and not predicted_immunogenic:
            false_negatives += 1
    
    # 计算性能指标
    sensitivity = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) > 0 else 0
    specificity = true_negatives / (true_negatives + false_positives) if (true_negatives + false_positives) > 0 else 0
    accuracy = (true_positives + true_negatives) / len(validation_data)
    
    return {
        "sensitivity": sensitivity,
        "specificity": specificity,
        "accuracy": accuracy,
        "true_positives": true_positives,
        "false_positives": false_positives,
        "true_negatives": true_negatives,
        "false_negatives": false_negatives
    }
```

### 阈值优化

使用网格搜索优化阈值：

```python
import numpy as np

def optimize_thresholds(validation_data):
    """优化结合类别阈值"""
    best_accuracy = 0
    best_thresholds = {"strong": 50.0, "weak": 500.0}
    
    # 网格搜索
    strong_candidates = np.arange(10, 200, 10)  # 10-200 nM
    weak_candidates = np.arange(100, 1000, 50)  # 100-1000 nM
    
    for strong_thresh in strong_candidates:
        for weak_thresh in weak_candidates:
            if weak_thresh <= strong_thresh:
                continue  # 弱阈值必须大于强阈值
            
            thresholds = {"strong": strong_thresh, "weak": weak_thresh}
            performance = validate_thresholds(validation_data, thresholds)
            
            if performance["accuracy"] > best_accuracy:
                best_accuracy = performance["accuracy"]
                best_thresholds = thresholds
    
    return best_thresholds, best_accuracy
```

## 阈值选择指南

### 选择标准阈值的场景

1. **标准免疫学研究**: 使用默认阈值（50/500 nM）
2. **与文献比较**: 使用领域标准阈值以确保可比性
3. **初步筛选**: 使用保守阈值减少假阳性
4. **教学目的**: 使用标准阈值便于理解

### 选择自定义阈值的场景

1. **特定疾病研究**: 根据疾病特性调整阈值
2. **实验验证**: 根据实验体系优化阈值
3. **高通量筛选**: 使用宽松阈值增加候选数量
4. **精准医疗**: 根据患者特征个性化阈值

### 阈值选择决策树

```
开始
  ↓
是否需要与已有研究比较？
  ├─ 是 → 使用文献中的标准阈值
  └─ 否 → 是否有实验验证数据？
        ├─ 是 → 基于验证数据优化阈值
        └─ 否 → 应用场景是什么？
              ├─ 疫苗设计 → 使用严格阈值（≤50 nM）
              ├─ 肿瘤新抗原 → 使用中等阈值（≤100 nM）
              ├─ 诊断开发 → 使用非常严格阈值（≤20 nM）
              └─ 基础研究 → 使用宽松阈值（≤500 nM）
```

## 常见问题

### Q1: 为什么使用50 nM作为强结合阈值？

**A**: 50 nM阈值基于大量实验数据：
- T细胞激活实验显示，亲和力低于50 nM的肽能有效激活T细胞
- 免疫优势表位通常具有低于50 nM的亲和力
- 疫苗设计标准通常要求候选肽亲和力低于50 nM
- 这个阈值在灵敏度和特异性之间提供了良好的平衡

### Q2: 百分位排名和绝对亲和力哪个更重要？

**A**: 两者都重要，但用途不同：
- **绝对亲和力**: 适用于跨等位基因比较和绝对阈值应用
- **百分位排名**: 适用于等位基因内比较和相对评估
- **建议**: 同时考虑两者，优先使用百分位排名进行等位基因标准化比较

### Q3: 如何为特定应用选择阈值？

**A**: 遵循以下步骤：
1. 明确应用目标（疫苗设计、诊断开发等）
2. 查阅相关文献了解领域标准
3. 如果有实验数据，基于数据优化阈值
4. 考虑假阳性和假阴性的代价
5. 从保守阈值开始，根据需要调整

### Q4: 阈值是否适用于所有等位基因？

**A**: 标准阈值（50/500 nM）是基于常见等位基因（如HLA-A*02:01）建立的。对于罕见等位基因：
- 绝对阈值可能不完全适用
- 建议使用百分位排名进行标准化
- 如有条件，基于等位基因特异性数据调整阈值

### Q5: 如何验证阈值的有效性？

**A**: 使用以下方法：
1. 收集已知免疫原性肽的实验数据
2. 计算阈值在这些数据上的性能指标
3. 比较不同阈值的性能
4. 选择在灵敏度和特异性之间平衡最好的阈值
5. 在独立数据集上验证

## 总结

MHCflurry的结合类别阈值是基于免疫学研究和实验数据建立的实用工具。正确理解和使用这些阈值对于准确