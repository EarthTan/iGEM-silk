---
name: BepiPred-3.0
description: 当需要预测肽序列的线性 B 细胞表位、评估免疫原性风险、或在融合肽筛选中作为惩罚项时触发此技能。BepiPred-3.0 基于 ESM-2 蛋白质语言模型，可本地批量运行。
created: 2026-04-17
version: 0.0.12.7
last_updated: 2026-04-25
---

# BepiPred-3.0 线性 B 细胞表位预测工具

## What It Is

BepiPred-3.0 是基于 ESM-2 蛋白质语言模型的线性 B 细胞表位预测工具。它预测蛋白质/肽序列中哪些氨基酸残基可能被抗体识别（即构成 B 细胞表位）。

**核心价值**：为融合引擎提供"免疫原性风险信号"，帮助剔除高免疫原性候选肽。

## When to Use

- **免疫原性风险评估**：评估候选肽序列的表位风险分数
- **融合肽粗筛**：作为惩罚项，剔除高免疫原性序列
- **多肽药物筛选**：过滤潜在的致敏序列
- **批量预测**：一次处理 20/100/1000+ 条候选序列

## Methodology

**输入**：FASTA 格式氨基酸序列
**输出**：
- 每个残基的表位概率分数（0-1）
- 线性表位平滑分数
- 标记表位残基的 FASTA 文件

**核心流程**：
1. 使用 ESM-2 提取序列的蛋白质语言模型表征
2. 通过 ensemble 神经网络分类器预测表位
3. 输出每残基表位概率和平滑分数

## Operations

### 安装

```bash
# 1. 下载 BepiPred-3.0
cd /path/to/BepiPred-3.0
curl -fsSL https://github.com/UberClifford/BepiPred-3.0/archive/refs/heads/main.tar.gz -o repo.tar.gz
tar -xzf repo.tar.gz && mv BepiPred-3.0-main repo

# 2. 创建虚拟环境
cd repo
uv venv .venv --python 3.11
source .venv/bin/activate

# 3. 安装依赖（CPU 版本）
uv pip install torch --index-url https://download.pytorch.org/whl/cpu
uv pip install fair-esm numpy pandas plotly
```

### 命令行使用

```bash
# 激活环境
source .venv/bin/activate

# 运行预测（可变阈值模式）
python bepipred3_CLI.py -i input.fasta -o output_dir -pred vt_pred

# 运行预测（多数投票模式）
python bepipred3_CLI.py -i input.fasta -o output_dir -pred mjv_pred

# 自定义参数
python bepipred3_CLI.py -i input.fasta -o output_dir -pred vt_pred \
    -t 0.2                    # 自定义阈值（默认 0.1512）
    -rolling_window_size 7     # 滚动窗口大小（默认 9）
    -top 0.2                   # Top 20% 表位（默认 0.2）
```

### Python API 使用

```python
import sys
from pathlib import Path

# 添加 BepiPred-3.0 路径
BP3_PATH = "/path/to/BepiPred-3.0/repo"
sys.path.insert(0, BP3_PATH)

from bp3 import bepipred3

# 设置路径
fasta_file = Path("input.fasta")
esm_dir = Path("esm_encodings")
out_dir = Path("output")

# 创建抗原对象并运行预测
antigens = bepipred3.Antigens(fasta_file, esm_dir, add_seq_len=False)
predictor = bepipred3.BP3EnsemblePredict(antigens, rolling_window_size=7, top_pred_pct=0.2)
predictor.run_bp3_ensemble()

# 输出结果
predictor.create_csvfile(out_dir)
predictor.bp3_pred_variable_threshold(out_dir, var_threshold=0.1512)
```

## 输入输出

### 输入格式

```fasta
>PEP_001
MKFLILLFNILCLFPVLAADNHGNPKTHPNPRG
>PEP_002
GILGFVFTLTVPSERGL
```

### 输出文件

| 文件 | 内容 |
|------|------|
| `raw_output.csv` | 每残基的表位分数 |
| `Bcell_epitope_preds.fasta` | 大写=表位残基，小写=非表位 |
| `Bcell_epitope_top_20pct_preds.fasta` | Top 20% 预测 |
| `output_interactive_figures.html` | 交互式可视化 |

### raw_output.csv 示例

```csv
Accession,Residue,BepiPred-3.0 score,BepiPred-3.0 linear epitope score
PEP_001,M,0.148,0.070
PEP_001,K,0.206,0.078
PEP_001,F,0.086,0.083
```

## Examples

### 1. 基本预测流程

```bash
# 准备输入
cat > test.fasta << 'EOF'
>PEP_001
MKFLILLFNILCLFPVLAADNHGNPKTHPNPRG
>PEP_002
GILGFVFTLTVPSERGL
EOF

# 运行预测
python bepipred3_CLI.py -i test.fasta -o results -pred vt_pred

# 查看结果
cat results/raw_output.csv
cat results/Bcell_epitope_preds.fasta
```

### 2. 批量筛选脚本

详见 `references/FEATURE_FUNCTIONS.md`

## 局限性

| 场景 | 限制 |
|------|------|
| **< 5 aa** | 预测不可靠，ESM-2 编码需要足够上下文 |
| **5-10 aa** | 敏感性较低，短肽通常不形成典型表位 |
| **非标准氨基酸** | B, Z, X, U, O 等字符被接受但可能影响准确性 |
| **化学修饰** | 不支持磷酸化、糖基化等修饰信息 |
| **计算资源** | 首次运行需下载约 2.5GB ESM-2 模型权重 |

### 对融合肽的限制

- Linker 区域（GGGGS、EAAAK）通常被正确预测为非表位
- 融合边界可能产生新表位，需特别关注
- 建议对完整融合肽进行预测，而非分别预测各模块

## 参考文献

1. Clifford, J. N., et al. (2022). "BepiPred-3.0: Improved B-cell epitope prediction using protein language models." *Protein Science*, 31(12), e4497.
2. Lin, Z., et al. (2023). "Evolutionary-scale prediction of atomic-level protein structure with a language model." *Science*, 379(6637), 1123-1130.

## References Index

| File | Contents |
|------|----------|
| `references/FEATURE_FUNCTIONS.md` | 特征提取函数（extract_epitope_features、calculate_epitope_penalty、epitope_based_filter） |
| `references/TEST_RESULTS.md` | 详细测试结果和性能数据 |
| `references/FUSION_PEPTIDE_TESTS.md` | 融合肽场景测试 |
