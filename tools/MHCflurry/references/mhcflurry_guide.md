# MHCflurry 使用指南

## 概述

MHCflurry 是一个基于深度学习的MHC I类肽结合亲和力预测工具。本指南提供MHCflurry的完整使用说明，包括安装、配置、预测、分析和故障排除。

## 安装和配置

### 系统要求

- Python 3.8 或更高版本
- 至少 2GB 可用内存
- 网络连接（用于下载预训练模型）
- 约 200MB 磁盘空间（用于模型存储）

### 安装步骤

1. **安装MHCflurry**:
   ```bash
   pip install mhcflurry
   ```

2. **安装可选依赖**（用于数据分析和可视化）:
   ```bash
   pip install pandas numpy matplotlib seaborn
   ```

3. **下载预训练模型**:
   ```bash
   python -c "from mhcflurry.downloads import fetch_models; fetch_models()"
   ```

   或者，在代码中首次使用时自动下载。

### 验证安装

```python
from mhcflurry import Class1AffinityPredictor

# 创建预测器实例
predictor = Class1AffinityPredictor.load()

# 测试预测
predictions = predictor.predict(
    peptides=["SIINFEKL"],
    alleles=["HLA-A*02:01"]
)

print(f"安装成功！预测结果: {predictions}")
```

## 核心概念

### 1. 结合亲和力

结合亲和力以纳摩尔（nM）为单位表示，值越低表示结合越强：
- **< 50 nM**: 强结合
- **50-500 nM**: 弱结合
- **> 500 nM**: 非结合

### 2. 百分位排名

百分位排名表示该肽的结合亲和力相对于随机肽的排名：
- **< 0.5%**: 极强结合
- **0.5-2%**: 强结合
- **2-10%**: 中等结合
- **> 10%**: 弱结合

### 3. 结合类别

基于标准阈值自动分类：
- **强结合子**: ≤ 50 nM
- **弱结合子**: 50-500 nM
- **非结合子**: > 500 nM

## API参考

### 主要类

#### Class1AffinityPredictor
主预测器类，提供所有预测功能。

```python
from mhcflurry import Class1AffinityPredictor

# 加载预测器
predictor = Class1AffinityPredictor.load()

# 主要方法
predictions = predictor.predict(peptides, alleles)  # 预测结合亲和力
predictions = predictor.predict_to_dataframe(peptides, alleles)  # 预测到DataFrame
percentile_ranks = predictor.predict_percentile_ranks(peptides, alleles)  # 预测百分位排名
```

#### Class1PresentationPredictor
包含抗原加工预测的增强预测器。

```python
from mhcflurry import Class1PresentationPredictor

predictor = Class1PresentationPredictor.load()
predictions = predictor.predict(peptides, alleles)
```

### 预测结果

预测结果包含以下字段：

| 字段 | 类型 | 描述 |
|------|------|------|
| peptide | str | 肽序列 |
| allele | str | MHC等位基因 |
| prediction | float | 结合亲和力（nM） |
| percentile_rank | float | 百分位排名 |
| prediction_low | float | 预测下限（95%置信区间） |
| prediction_high | float | 预测上限（95%置信区间） |
| presentation_score | float | 呈递评分（仅Class1PresentationPredictor） |
| processing_score | float | 加工评分（仅Class1PresentationPredictor） |

## 使用示例

### 示例1：基本预测

```python
from mhcflurry import Class1AffinityPredictor

# 加载预测器
predictor = Class1AffinityPredictor.load()

# 预测单个肽
peptides = ["SIINFEKL"]
alleles = ["HLA-A*02:01"]

predictions = predictor.predict(peptides, alleles)
print(predictions)
```

### 示例2：批量预测

```python
from mhcflurry import Class1AffinityPredictor
import pandas as pd

predictor = Class1AffinityPredictor.load()

# 批量预测多个肽和等位基因
peptides = ["SIINFEKL", "NLVPMVATV", "GILGFVFTL"]
alleles = ["HLA-A*02:01", "HLA-A*01:01"]

# 预测到DataFrame
df = predictor.predict_to_dataframe(peptides, alleles)
print(df)

# 保存结果
df.to_csv("predictions.csv", index=False)
```

### 示例3：使用抗原加工预测

```python
from mhcflurry import Class1PresentationPredictor

predictor = Class1PresentationPredictor.load()

peptides = ["SIINFEKL", "NLVPMVATV"]
alleles = ["HLA-A*02:01"]

# 预测包含加工和呈递评分
predictions = predictor.predict(peptides, alleles)
print(predictions)
```

### 示例4：自定义阈值

```python
from mhcflurry import Class1AffinityPredictor

predictor = Class1AffinityPredictor.load()

# 预测
peptides = ["SIINFEKL", "NLVPMVATV", "GILGFVFTL"]
alleles = ["HLA-A*02:01"]

df = predictor.predict_to_dataframe(peptides, alleles)

# 自定义分类阈值
def classify_affinity(affinity_nM, strong_threshold=50, weak_threshold=500):
    if affinity_nM <= strong_threshold:
        return "strong_binder"
    elif affinity_nM <= weak_threshold:
        return "weak_binder"
    else:
        return "non_binder"

df["binding_class"] = df["prediction"].apply(classify_affinity)
print(df[["peptide", "allele", "prediction", "binding_class"]])
```

## 等位基因支持

### 常见人类HLA等位基因

MHCflurry支持数百种MHC I类等位基因，包括：

#### HLA-A
- HLA-A*02:01 (全球最常见)
- HLA-A*01:01 (欧洲常见)
- HLA-A*03:01 (全球分布)
- HLA-A*11:01 (亚洲常见)
- HLA-A*24:02 (亚洲最常见)

#### HLA-B
- HLA-B*07:02 (全球常见)
- HLA-B*08:01 (欧洲常见)
- HLA-B*15:01 (全球分布)
- HLA-B*35:01 (地中海地区常见)
- HLA-B*40:01 (亚洲常见)

#### HLA-C
- HLA-C*07:02 (全球最常见)
- HLA-C*04:01 (欧洲常见)
- HLA-C*05:01 (中东常见)
- HLA-C*06:02 (亚洲常见)

### 其他物种

#### 小鼠 (H-2)
- H-2-Kb
- H-2-Db
- H-2-Kd
- H-2-Dd
- H-2-Ld

#### 恒河猴 (Mamu)
- Mamu-A1*001
- Mamu-B*001
- Mamu-B*003
- Mamu-B*004

#### 黑猩猩 (Patr)
- Patr-A*0101
- Patr-B*0101

### 获取支持列表

```python
from mhcflurry import Class1AffinityPredictor

predictor = Class1AffinityPredictor.load()
alleles = predictor.supported_alleles

print(f"总共支持 {len(alleles)} 个等位基因")
print("前20个等位基因:")
for i, allele in enumerate(alleles[:20], 1):
    print(f"  {i:2d}. {allele}")
```

## 性能优化

### 1. 批量处理

批量预测比逐个预测更高效：

```python
# 推荐：批量预测
predictions = predictor.predict(peptides, alleles)

# 不推荐：逐个预测
for peptide in peptides:
    prediction = predictor.predict([peptide], alleles)
```

### 2. 减少等位基因数量

预测时间与等位基因数量成正比：

```python
# 高效：使用较少的等位基因
predictions = predictor.predict(peptides, ["HLA-A*02:01", "HLA-B*07:02"])

# 低效：使用大量等位基因
predictions = predictor.predict(peptides, all_alleles[:50])
```

### 3. 使用适当的数据结构

使用列表而不是单个值进行预测：

```python
# 正确：使用列表
peptides = ["SIINFEKL", "NLVPMVATV"]
alleles = ["HLA-A*02:01"]

# 错误：使用单个值（需要额外处理）
peptide = "SIINFEKL"
allele = "HLA-A*02:01"
```

### 4. 内存管理

对于大规模预测，分批处理：

```python
def predict_in_batches(peptides, alleles, batch_size=1000):
    results = []
    for i in range(0, len(peptides), batch_size):
        batch = peptides[i:i+batch_size]
        batch_results = predictor.predict(batch, alleles)
        results.extend(batch_results)
    return results

# 大规模预测
large_peptide_list = [...]  # 10000个肽
results = predict_in_batches(large_peptide_list, ["HLA-A*02:01"])
```

## 结果分析

### 统计摘要

```python
import pandas as pd
import numpy as np

def analyze_predictions(df):
    """分析预测结果"""
    summary = {
        "total_predictions": len(df),
        "strong_binders": len(df[df["prediction"] <= 50]),
        "weak_binders": len(df[(df["prediction"] > 50) & (df["prediction"] <= 500)]),
        "non_binders": len(df[df["prediction"] > 500]),
        "mean_affinity": df["prediction"].mean(),
        "median_affinity": df["prediction"].median(),
        "min_affinity": df["prediction"].min(),
        "max_affinity": df["prediction"].max(),
        "std_affinity": df["prediction"].std(),
    }
    
    # 按等位基因分组统计
    allele_stats = df.groupby("allele")["prediction"].agg([
        "count", "mean", "median", "min", "max", "std"
    ]).round(2)
    
    return summary, allele_stats

# 使用示例
df = predictor.predict_to_dataframe(peptides, alleles)
summary, allele_stats = analyze_predictions(df)

print("统计摘要:")
for key, value in summary.items():
    print(f"  {key}: {value}")

print("\n等位基因统计:")
print(allele_stats)
```

### 可视化

```python
import matplotlib.pyplot as plt
import seaborn as sns

def visualize_predictions(df, output_path=None):
    """可视化预测结果"""
    fig, axes = plt.subplots(2, 2, figsize=(12, 10))
    
    # 1. 结合亲和力分布
    axes[0, 0].hist(df["prediction"], bins=50, edgecolor='black', alpha=0.7)
    axes[0, 0].axvline(x=50, color='red', linestyle='--', label='强结合阈值')
    axes[0, 0].axvline(x=500, color='orange', linestyle='--', label='弱结合阈值')
    axes[0, 0].set_xlabel("结合亲和力 (nM)")
    axes[0, 0].set_ylabel("频数")
    axes[0, 0].set_title("结合亲和力分布")
    axes[0, 0].legend()
    axes[0, 0].set_xscale('log')
    
    # 2. 结合类别饼图
    binding_classes = []
    for affinity in df["prediction"]:
        if affinity <= 50:
            binding_classes.append("强结合子")
        elif affinity <= 500:
            binding_classes.append("弱结合子")
        else:
            binding_classes.append("非结合子")
    
    class_counts = pd.Series(binding_classes).value_counts()
    axes[0, 1].pie(class_counts.values, labels=class_counts.index, autopct='%1.1f%%')
    axes[0, 1].set_title("结合类别分布")
    
    # 3. 等位基因箱线图
    if len(df["allele"].unique()) > 1:
        sns.boxplot(data=df, x="allele", y="prediction", ax=axes[1, 0])
        axes[1, 0].set_yscale('log')
        axes[1, 0].set_xlabel("等位基因")
        axes[1, 0].set_ylabel("结合亲和力 (nM)")
        axes[1, 0].set_title("等位基因比较")
        axes[1, 0].tick_params(axis='x', rotation=45)
    
    # 4. 肽长度散点图
    df["peptide_length"] = df["peptide"].apply(len)
    axes[1, 1].scatter(df["peptide_length"], df["prediction"], alpha=0.6)
    axes[1, 1].set_xlabel("肽长度")
    axes[1, 1].set_ylabel("结合亲和力 (nM)")
    axes[1, 1].set_title("肽长度与结合亲和力关系")
    axes[1, 1].set_yscale('log')
    
    plt.tight_layout()
    
    if output_path:
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        print(f"可视化已保存到: {output_path}")
    
    plt.show()

# 使用示例
visualize_predictions(df, "mhcflurry_visualization.png")
```

## 故障排除

### 常见问题

#### Q1: MHCflurry安装失败
**错误**: `pip install mhcflurry` 失败
**解决方案**:
```bash
# 升级pip
pip install --upgrade pip

# 使用清华镜像
pip install mhcflurry -i https://pypi.tuna.tsinghua.edu.cn/simple

# 或使用conda
conda install -c bioconda mhcflurry
```

#### Q2: 模型下载失败
**错误**: 首次使用时模型下载失败
**解决方案**:
```bash
# 手动下载
python -c "from mhcflurry.downloads import fetch_models; fetch_models()"

# 或指定镜像
python -c "from mhcflurry.downloads import fetch_models; fetch_models(mirror='https://github.com')"
```

#### Q3: 预测速度慢
**问题**: 预测大量数据时速度慢
**解决方案**:
1. 使用批量预测而非单个预测
2. 减少同时预测的等位基因数量
3. 使用更强大的硬件
4. 考虑使用GPU加速（如果可用）

#### Q4: 内存不足
**问题**: 预测大量数据时内存不足
**解决方案**:
1. 减少批量大小
2. 分批处理数据
3. 增加系统内存
4. 使用流式处理

#### Q5: 等位基因不支持
**错误**: `ValueError: 不支持的等位基因`
**解决方案**:
```python
# 检查支持的等位基因
alleles = predictor.supported_alleles
print(f"支持的等位基因: {alleles}")

# 使用支持的等位基因
if "HLA-A*02:01" in alleles:
    predictions = predictor.predict(peptides, ["HLA-A*02:01"])
```

### 错误处理示例

```python
from mhcflurry import Class1AffinityPredictor

try:
    # 尝试加载预测器
    predictor = Class1AffinityPredictor.load()
    
    # 尝试预测
    predictions = predictor.predict(["SIINFEKL"], ["HLA-A*02:01"])
    
except ImportError as e:
    print(f"导入错误: {e}")
    print("请确保已安装MHCflurry: pip install mhcflurry")
    
except ValueError as e:
    print(f"值错误: {e}")
    print("请检查肽序列或等位基因格式")
    
except RuntimeError as e:
    print(f"运行时错误: {e}")
    print("请检查模型文件是否存在")
    
except Exception as e:
    print(f"未知错误: {e}")
    print("请查看MHCflurry文档或报告问题")
```

## 高级用法

### 自定义模型

```python
from mhcflurry import Class1AffinityPredictor

# 从自定义路径加载模型
predictor = Class1AffinityPredictor.load("/path/to/custom/models")

# 或训练自定义模型
# predictor.train(training_data, ...)
```

### 集成到工作流

```python
def vaccine_candidate_pipeline(fasta_file, alleles, output_dir):
    """疫苗候选肽筛选流水线"""
    import os
    from Bio import SeqIO
    
    # 1. 从FASTA读取肽序列
    peptides = []
    for record in SeqIO.parse(fasta_file, "fasta"):
        peptides.append(str(record.seq))
    
    # 2. 初始化预测器
    predictor = Class1AffinityPredictor.load()
    
    # 3. 批量预测
    df = predictor.predict_to_dataframe(peptides, alleles)
    
    # 4. 筛选强结合子
    strong_binders = df[df["prediction"] <= 50].copy()
    
    # 5. 按亲和力排序
    strong_binders = strong_binders.sort_values("prediction")
    
    # 6. 保存结果
    os.makedirs(output_dir, exist