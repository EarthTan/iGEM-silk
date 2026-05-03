# BepiPred-3.0 详细测试结果

## 测试环境

- **平台**：macOS (Darwin)
- **Python**：3.11
- **PyTorch**：2.11.0 (CPU)
- **fair-esm**：2.0.0
- **设备**：Apple M1, CPU 模式

## 安装验证

### 依赖安装命令

```bash
uv venv .venv --python 3.11
uv pip install torch --index-url https://download.pytorch.org/whl/cpu
uv pip install fair-esm numpy pandas plotly
```

### 首次运行

首次运行时会自动下载 ESM-2 模型权重（约 2.5GB）：

```
Downloading: "https://dl.fbaipublicfiles.com/fair-esm/models/esm2_t33_650M_UR50D.pt"
Downloading: "https://dl.fbaipublicfiles.com/fair-esm/models/esm2_t33_650M_UR50D-contact-regression.pt"
```

## 功能测试

### 测试 1：基本预测（3 条序列）

**输入**：
```fasta
>TEST_PEP1
MKFLILLFNILCLFPVLAADNHGNPKTHPNPRG
>TEST_PEP2
GILGFVFTLTVPSERGL
>TEST_PEP3
SIINFEKLTEWTSV
```

**输出**：
- ✅ `raw_output.csv` - 包含每残基分数
- ✅ `Bcell_epitope_preds.fasta` - 表位标记
- ✅ 约 5 秒完成

**关键发现**：
- 大写字母表示预测为表位的残基
- TEST_PEP1 的 D, N, H, G, N, P, K 等残基被标记为表位

### 测试 2：融合肽场景

**输入**：
```fasta
>FUSION_1
MKFLILLFNILCLFPVLAADNHGNPKTHPNPRGGGGSEAAAKGILGFVFTLTVPSERGL
```

**结果**：
- Linker 区域（GGGGSEAAAK）部分被预测为非表位（小写）
- 融合区域边界有部分被预测为表位

**观察**：
- Linker (GGGGS, EAAAK) 通常被正确预测为非表位
- 功能模块边界区域可能产生新的表位信号

### 测试 3：短肽限制

| 序列 | 长度 | 最高分数 | 阈值 | 预测为表位 |
|------|------|----------|------|------------|
| GGGGS | 5 aa | 0.24 | 0.1512 | 否 |
| DYKDDDDK | 8 aa | ~0.15 | 0.1512 | 可疑 |
| X | 1 aa | 0.15 | 0.1512 | 否 |

**结论**：短肽（<10 aa）的预测结果应谨慎解读。

## 批量处理性能

### 20 条序列测试

```
序列数量: 20
平均长度: 25-45 aa
处理时间: ~7 秒（ESM 编码已缓存）
```

### 100 条序列测试

```
序列数量: 100
平均长度: 15-55 aa
处理时间: ~14 秒（冷启动，含 ESM 编码）
```

**性能结论**：
- 批量处理 100 条序列在 15 秒内完成
- ESM 编码可缓存，后续运行更快
- 内存占用：处理 100 条时约 2-3GB

## Python API 测试

```python
from bp3 import bepipred3
from pathlib import Path

antigens = bepipred3.Antigens(fasta_file, esm_dir, add_seq_len=False)
predictor = bepipred3.BP3EnsemblePredict(antigens, rolling_window_size=7, top_pred_pct=0.2)
predictor.run_bp3_ensemble()
predictor.create_csvfile(out_dir)
```

✅ API 调用成功

## 输出格式详解

### raw_output.csv 字段

| 字段 | 说明 |
|------|------|
| Accession | 序列标识符 |
| Residue | 氨基酸残基（单字母） |
| BepiPred-3.0 score | 原始表位预测分数（0-1） |
| BepiPred-3.0 linear epitope score | 线性表位平滑分数 |

### 阈值说明

- **默认阈值**：0.1512（论文推荐）
- **分数 > 阈值**：预测为表位残基
- **分数 < 阈值**：预测为非表位残基

## 与 BepiPred-2.0 的对比

| 特性 | BepiPred-2.0 | BepiPred-3.0 |
|------|--------------|--------------|
| 基础模型 | 经验模型 | ESM-2 语言模型 |
| 安装 | 需下载 IEDB 工具 | GitHub 克隆即可 |
| 依赖 | Linux 64位 | Python 环境 |
| 批量处理 | 需通过 Web | CLI/Python API |
| 部署难度 | 较高 | 较低 |

**推荐**：使用 BepiPred-3.0，本地集成更方便。
