# MLCPP 2.0 完整使用指南

## 概述
MLCPP 2.0 (Machine Learning-based Cell Penetrating Peptide Predictor) 是一个基于机器学习的细胞穿透肽（CPP）预测工具。它集成了多种机器学习算法，提供准确的CPP预测功能，支持在线API调用和离线本地预测两种模式。

## 安装与配置

### 系统要求
- Python 3.6 或更高版本
- 基础依赖：requests, pandas, numpy
- 可选依赖：matplotlib, seaborn（可视化），biopython（FASTA处理）

### 安装步骤
```bash
# 1. 安装核心依赖
pip install requests pandas numpy

# 2. 安装可选依赖（推荐）
pip install matplotlib seaborn biopython

# 3. 验证安装
python -c "from tools.mlcpp_integration import MLCPPIntegration; print('MLCPP导入成功')"
```

### 配置选项
```python
from tools.mlcpp_integration import MLCPPIntegration

# 基本配置
mlcpp = MLCPPIntegration(
    mode="auto",               # 运行模式：auto, online, offline, simulation
    confidence_threshold=0.5,  # 置信度阈值
    verbose=True,              # 详细输出
    timeout=30,                # 请求超时时间（秒）
    cache_results=True         # 缓存结果
)

# 离线模式需要指定模型路径
mlcpp_offline = MLCPPIntegration(
    mode="offline",
    model_path="./mlcpp_models",  # 模型文件目录
    download_if_missing=True      # 如果缺失则自动下载
)
```

## 核心功能详解

### 1. 单序列预测
预测单个肽序列是否为细胞穿透肽。

```python
from tools.mlcpp_integration import MLCPPIntegration, PredictionResult

mlcpp = MLCPPIntegration()

# 预测单个序列
sequence = "RKKRRQRRR"  # TAT肽，经典CPP
result = mlcpp.predict_single(sequence)

# 结果分析
print(f"序列: {result.sequence}")
print(f"预测: {result.prediction}")  # "CPP" 或 "Non-CPP"
print(f"是否为CPP: {result.is_cpp}")  # True 或 False
print(f"置信度: {result.confidence:.3f}")  # 0-1之间的值
print(f"概率: {result.probability:.3f}")   # 属于CPP的概率
print(f"特征向量: {result.features[:5]}...")  # 前5个特征值
print(f"模型类型: {result.model_type}")      # 使用的模型
print(f"预测时间: {result.prediction_time:.3f}秒")
```

### 2. 批量预测
批量预测多个肽序列，支持列表、字典或文件输入。

```python
# 列表输入
sequences = ["RKKRRQRRR", "ACDEFGHIK", "GRKKRRQRRRPPQ"]
results = mlcpp.predict_batch(sequences)

# 字典输入（带ID）
sequences_dict = {
    "TAT": "RKKRRQRRR",
    "Random": "ACDEFGHIK",
    "Penetratin": "GRKKRRQRRRPPQ"
}
results = mlcpp.predict_batch(sequences_dict)

# 文件输入（FASTA格式）
results = mlcpp.predict_from_fasta("peptides.fasta")

# 文件输入（CSV格式）
results = mlcpp.predict_from_csv("peptides.csv", sequence_column="Sequence")
```

### 3. 双模式运行
MLCPP支持两种运行模式，可根据网络条件和需求选择。

#### 在线模式 (Online)
通过API调用远程服务器进行预测。

**优点**：
- 无需下载模型文件
- 总是使用最新模型
- 计算在服务器端完成

**缺点**：
- 需要网络连接
- 可能有速率限制
- 数据隐私考虑

```python
mlcpp_online = MLCPPIntegration(mode="online")
```

#### 离线模式 (Offline)
在本地运行预测，需要下载模型文件。

**优点**：
- 无需网络连接
- 数据完全本地处理
- 无速率限制

**缺点**：
- 需要下载模型文件（100-500MB）
- 模型更新需要手动下载

```python
mlcpp_offline = MLCPPIntegration(
    mode="offline",
    model_path="./mlcpp_models",
    download_if_missing=True  # 自动下载缺失的模型
)
```

#### 自动模式 (Auto)
优先使用离线模式，如果不可用则切换到在线模式。

```python
mlcpp_auto = MLCPPIntegration(mode="auto")
```

### 4. 结果分析与可视化

#### 基本统计分析
```python
import pandas as pd

# 将结果转换为DataFrame
results = mlcpp.predict_batch(sequences)
df = mlcpp.results_to_dataframe(results)

# 基本统计
print(f"总序列数: {len(df)}")
print(f"CPP预测数: {df['is_cpp'].sum()}")
print(f"Non-CPP预测数: {len(df) - df['is_cpp'].sum()}")
print(f"平均置信度: {df['confidence'].mean():.3f}")
print(f"CPP平均概率: {df[df['is_cpp']]['probability'].mean():.3f}")

# 按置信度分组
high_conf = df[df['confidence'] >= 0.8]
medium_conf = df[(df['confidence'] >= 0.6) & (df['confidence'] < 0.8)]
low_conf = df[df['confidence'] < 0.6]

print(f"高置信度(≥0.8): {len(high_conf)} 条序列")
print(f"中置信度(0.6-0.8): {len(medium_conf)} 条序列")
print(f"低置信度(<0.6): {len(low_conf)} 条序列")
```

#### 可视化分析
```python
import matplotlib.pyplot as plt
import seaborn as sns

# 1. 置信度分布直方图
plt.figure(figsize=(10, 6))
plt.hist(df['confidence'], bins=20, edgecolor='black', alpha=0.7)
plt.xlabel('置信度')
plt.ylabel('频率')
plt.title('预测置信度分布')
plt.axvline(x=0.5, color='red', linestyle='--', label='阈值(0.5)')
plt.legend()
plt.tight_layout()
plt.savefig('confidence_distribution.png', dpi=300)
plt.close()

# 2. CPP vs Non-CPP置信度对比
plt.figure(figsize=(10, 6))
sns.boxplot(x='prediction', y='confidence', data=df)
plt.xlabel('预测类别')
plt.ylabel('置信度')
plt.title('CPP vs Non-CPP置信度对比')
plt.tight_layout()
plt.savefig('confidence_by_class.png', dpi=300)
plt.close()

# 3. 序列长度与预测结果关系
df['length'] = df['sequence'].apply(len)
plt.figure(figsize=(10, 6))
sns.scatterplot(x='length', y='confidence', hue='prediction', data=df, alpha=0.6)
plt.xlabel('序列长度')
plt.ylabel('置信度')
plt.title('序列长度与预测置信度关系')
plt.tight_layout()
plt.savefig('length_vs_confidence.png', dpi=300)
plt.close()
```

## API 参考

### MLCPPIntegration 类

#### 构造函数
```python
mlcpp = MLCPPIntegration(
    mode="auto",                    # 运行模式
    confidence_threshold=0.5,       # 置信度阈值
    verbose=False,                  # 详细输出
    timeout=30,                     # 请求超时时间
    cache_results=True,             # 缓存结果
    model_path=None,                # 离线模型路径
    download_if_missing=False,      # 自动下载缺失模型
    api_key=None,                   # API密钥（如果需要）
    base_url="http://mlcpp-api.example.com"  # API基础URL
)
```

#### 主要方法

##### `predict_single(sequence: str, sequence_id: str = None) -> PredictionResult`
预测单个肽序列。

**参数**：
- `sequence`: 肽序列字符串
- `sequence_id`: 可选的序列标识符

**返回**：PredictionResult对象

##### `predict_batch(sequences, **kwargs) -> List[PredictionResult]`
批量预测多个肽序列。

**参数**：
- `sequences`: 序列列表、字典或文件路径
- `**kwargs`: 额外参数（如sequence_column, id_column等）

**返回**：PredictionResult对象列表

##### `predict_from_fasta(fasta_path: str, max_sequences: int = None) -> List[PredictionResult]`
从FASTA文件预测。

**参数**：
- `fasta_path`: FASTA文件路径
- `max_sequences`: 最大分析序列数

**返回**：PredictionResult对象列表

##### `predict_from_csv(csv_path: str, sequence_column: str = "Sequence", id_column: str = "ID", **kwargs) -> List[PredictionResult]`
从CSV文件预测。

**参数**：
- `csv_path`: CSV文件路径
- `sequence_column`: 序列列名
- `id_column`: ID列名
- `**kwargs`: 传递给pandas.read_csv的额外参数

**返回**：PredictionResult对象列表

##### `results_to_dataframe(results: List[PredictionResult]) -> pd.DataFrame`
将预测结果转换为pandas DataFrame。

**参数**：
- `results`: PredictionResult对象列表

**返回**：包含所有预测结果的DataFrame

##### `export_results(results: List[PredictionResult], output_path: str, format: str = "csv") -> None`
导出预测结果到文件。

**参数**：
- `results`: 预测结果列表
- `output_path`: 输出文件路径
- `format`: 输出格式（csv, excel, json）

##### `check_status() -> Dict[str, Any]`
检查MLCPP服务状态。

**返回**：包含服务状态信息的字典

##### `get_model_info() -> Dict[str, Any]`
获取模型信息。

**返回**：包含模型版本、类型、特征等信息的字典

### PredictionResult 数据类
```python
class PredictionResult:
    sequence: str                    # 原始序列
    sequence_id: str                 # 序列ID
    prediction: str                  # 预测结果 ("CPP" 或 "Non-CPP")
    is_cpp: bool                     # 是否为CPP（布尔值）
    confidence: float                # 置信度 (0-1)
    probability: float               # CPP概率 (0-1)
    features: List[float]            # 特征向量
    model_type: str                  # 使用的模型类型
    prediction_time: float           # 预测时间（秒）
    timestamp: datetime              # 预测时间戳
    metadata: Dict[str, Any]         # 元数据
```

## 使用示例

### 示例1：完整CPP筛选流程
```python
from tools.mlcpp_integration import MLCPPIntegration
import pandas as pd

def cpp_screening_pipeline(sequences, output_dir="cpp_screening"):
    """
    完整的CPP筛选流水线
    """
    import os
    os.makedirs(output_dir, exist_ok=True)
    
    # 初始化MLCPP
    mlcpp = MLCPPIntegration(
        mode="auto",
        confidence_threshold=0.7,  # 使用较高的置信度阈值
        verbose=True
    )
    
    print(f"开始筛选 {len(sequences)} 条候选肽...")
    
    # 批量预测
    results = mlcpp.predict_batch(sequences)
    
    # 转换为DataFrame
    df = mlcpp.results_to_dataframe(results)
    
    # 筛选高置信度CPP
    high_confidence_cpp = df[
        (df['is_cpp'] == True) & 
        (df['confidence'] >= 0.7)
    ].copy()
    
    # 按置信度排序
    high_confidence_cpp = high_confidence_cpp.sort_values('confidence', ascending=False)
    
    # 保存结果
    output_files = []
    
    # 1. 所有预测结果
    all_results_path = os.path.join(output_dir, "all_predictions.csv")
    df.to_csv(all_results_path, index=False)
    output_files.append(all_results_path)
    
    # 2. 高置信度CPP
    if not high_confidence_cpp.empty:
        cpp_results_path = os.path.join(output_dir, "high_confidence_cpp.csv")
        high_confidence_cpp.to_csv(cpp_results_path, index=False)
        output_files.append(cpp_results_path)
        
        # 3. 生成报告
        report_path = os.path.join(output_dir, "screening_report.txt")
        with open(report_path, 'w') as f:
            f.write("=" * 60 + "\n")
            f.write("       细胞穿透肽筛选报告\n")
            f.write("=" * 60 + "\n\n")
            
            f.write(f"筛选时间: {pd.Timestamp.now()}\n")
            f.write(f"候选肽总数: {len(sequences)}\n")
            f.write(f"预测为CPP: {df['is_cpp'].sum()} 条\n")
            f.write(f"高置信度CPP (置信度≥0.7): {len(high_confidence_cpp)} 条\n\n")
            
            f.write("高置信度CPP列表:\n")
            f.write("-" * 60 + "\n")
            for idx, row in high_confidence_cpp.iterrows():
                f.write(f"{row['sequence_id']}: {row['sequence']}\n")
                f.write(f"  置信度: {row['confidence']:.3f}, 概率: {row['probability']:.3f}\n")
            
            f.write("\n" + "=" * 60 + "\n")
        
        output_files.append(report_path)
    
    print(f"\n筛选完成!")
    print(f"  总序列数: {len(sequences)}")
    print(f"  CPP预测数: {df['is_cpp'].sum()}")
    print(f"  高置信度CPP: {len(high_confidence_cpp)}")
    print(f"  结果文件: {output_files}")
    
    return high_confidence_cpp

# 使用示例
candidate_peptides = {
    "TAT": "RKKRRQRRR",
    "Penetratin": "GRKKRRQRRRPPQ",
    "MPG": "KETWWETWWTEWSQPKKKRKV",
    "pVEC": "LLIILRRRIRKQAHAHSK",
    "Transportan": "GWTLNSAGYLLGKINLKALAALAKKIL",
    "Random1": "ACDEFGHIKLMNPQRSTVWY",
    "Random2": "MKWVTFISLLFLFSSAYSR",
    "Random3": "DAHKSEVAHRFKDLGEENFK"
}

high_conf_cpp = cpp_screening_pipeline(candidate_peptides, "screening_results")
```

### 示例2：肽优化与突变分析
```python
def analyze_mutations(base_sequence, mutation_sites=None, output_dir="mutation_analysis"):
    """
    分析突变对细胞穿透能力的影响
    """
    import os
    os.makedirs(output_dir, exist_ok=True)
    
    mlcpp = MLCPPIntegration(mode="auto")
    
    # 如果没有指定突变位点，分析所有位置
    if mutation_sites is None:
        mutation_sites = range(len(base_sequence))
    
    # 生成突变体
    mutants = []
    mutant_info = []
    
    standard_aas = "ACDEFGHIKLMNPQRSTVWY"
    
    for pos in mutation_sites:
        original_aa = base_sequence[pos]
        for aa in standard_aas:
            if aa != original_aa:
                mutant_seq = list(base_sequence)
                mutant_seq[pos] = aa
                mutant_seq_str = "".join(mutant_seq)
                
                mutants.append(mutant_seq_str)
                mutant_info.append({
                    'position': pos + 1,  # 1-based位置
                    'original': original_aa,
                    'mutant': aa,
                    'sequence': mutant_seq_str
                })
    
    print(f"基础序列: {base_sequence}")
    print(f"生成 {len(mutants)} 个单点突变体")
    
    # 批量预测
    results = mlcpp.predict_batch(mutants)
    
    # 创建结果DataFrame
    df = pd.DataFrame(mutant_info)
    df['prediction'] = [r.prediction for r in results]
    df['is_cpp'] = [r.is_cpp for r in results]
    df['confidence'] = [r.confidence for r in results]
    df['probability'] = [r.probability for r in results]
    
    # 分析突变影响
    base_result = mlcpp.predict_single(base_sequence)
    
    # 找出改善的突变
    improved_mutants = df[
        (df['is_cpp'] == True) & 
        (df['confidence'] > base_result.confidence)
    ].copy()
    
    improved_mutants = improved_mutants.sort_values('confidence', ascending=False)
    
    # 找出破坏的突变
    disrupted_mutants = df[
        (df['is_cpp'] == False) & 
        (base_result.is_cpp == True)
    ].copy()
    
    # 保存结果
    output_files = []
    
    # 1. 所有突变体结果
    all_mutants_path = os.path.join(output_dir, "all_mutants.csv")
    df.to_csv(all_mutants_path, index=False)
    output_files.append(all_mutants_path)
    
    # 2. 改善的突变体