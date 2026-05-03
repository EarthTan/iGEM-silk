---
name: hemopi2
description: 当用户需要预测多肽的溶血性（hemolytic activity）、评估毒性风险、设计低溶血突变体时触发此技能。用于抗菌肽安全性筛选、虚拟筛选、毒性预测等场景。
version: "1.3"
last_updated: "2026-04-11"
---

# HemoPI2 溶血性预测工具

> ⚠️ **时效性声明**：本 Skill 基于 2026-04-11 的实际测试结果编写。工具版本或依赖更新后，请验证以下信息是否仍然有效。

---

## 版本与时效信息

| 属性 | 值 |
|------|-----|
| **Skill 制作日期** | 2026-04-11 |
| **测试的 hemopi2 版本** | 1.3 (pip install) |
| **测试的 Python 版本** | 3.12.12 |
| **测试的 torch 版本** | 2.11.0 |
| **官方最新版本** | 需访问 https://pypi.org/project/hemopi2/ 确认 |

> 📝 **建议**：使用前请检查 pip show hemopi2 确认版本，如有差异请在 `.memory/` 中记录变更。

---

## Build 日志（.memory/ 记录模板）

> 每次构建或验证此 Skill 时，请在 `.memory/` 中简要记录：
> - 测试日期
> - 安装的具体版本
> - 哪些功能实际测试过
> - 发现的 bug 或异常

**模板：**
```markdown
# HemoPI2 Build Log

## YYYY-MM-DD
- hemopi2 版本: X.X
- Python 版本: X.X
- 测试的功能: job=1, job=2, ...
- 发现的问题: ...
- 备注: ...
```

## What It Is

**HemoPI2** 是由 IIITD Raghava 团队开发的**肽溶血性预测工具**，可对多肽进行：

1. **分类预测**：判断序列是"溶血（Hemolytic）"还是"非溶血（Non-Hemolytic）"
2. **HC50 回归预测**：预测 50% 溶血所需浓度（μM），数值越低毒性越强

### 核心价值
- 在研发抗菌肽时，提前评估其对哺乳动物红细胞的破坏风险
- 大规模候选肽的虚拟筛选与风险分级
- 指导低溶血突变体的设计与优化

---

## When to Use

- **场景 1**：拿到一条候选肽，想快速判断溶血风险 → 用 `job=1`
- **场景 2**：有一条长肽，想知道哪一段最危险 → 用 `job=2`（蛋白扫描）
- **场景 3**：想验证某个位置换成特定氨基酸的效果 → 用 `job=3`（单点突变）
- **场景 4**：想知道某个位置换成什么氨基酸最好 → 用 `job=4`（全突变扫描）
- **场景 5**：想检查序列是否包含已知的溶血/非溶血特征模体 → 用 `job=5`（模体扫描）
- **场景 6**：不只想知道分类，还想知道毒性强度（HC50 值）→ 用**回归模式**

---

## Methodology (How It Works)

### 工具架构

```
输入：FASTA 格式肽序列（或每行一条序列）
   ↓
┌─────────────────────────────────────┐
│           HemoPI2                    │
├─────────────────────────────────────┤
│  分类模式 (hemopi2_classification)   │
│  ├── Model 1: Random Forest (RF)    │
│  ├── Model 2: Hybrid1 (RF+MERCI)    │
│  ├── Model 3: ESM2-t6 (深度学习)     │
│  └── Model 4: Hybrid2 (ESM+MERCI)   │
├─────────────────────────────────────┤
│  回归模式 (hemopi2_regression)       │
│  └── HC50 浓度预测                   │
└─────────────────────────────────────┘
   ↓
输出：CSV 文件（分类/回归结果）
```

### Job 类型 Methodology

| Job | 名称 | 本质 | 类比 |
|-----|------|------|------|
| `1` | 常规预测 | 整条序列直接输出结论 | 体检报告：直接告诉你有没有病 |
| `2` | 蛋白扫描 | 滑动窗口切段分析 | CT扫描：逐层查看哪一节有肿瘤 |
| `3` | 单点突变设计 | 指定位点换指定氨基酸 | 定点手术：切除并替换某一处 |
| `4` | 全突变扫描 | 指定位点换全部20种氨基酸 | 批量培育：同一位置种20种种子看效果 |
| `5` | 模体扫描 | 匹配已知的危险/安全指纹 | 指纹比对：查有没有犯罪前科 |

---

## Operations

### 环境准备

```bash
# 1. 进入项目目录
cd /path/to/HemoPI2

# 2. 激活虚拟环境
source .venv/bin/activate

# 3. 检查 Python 版本是否为 3.12
python --version  # 应显示 Python 3.12.x

# 4. 重要：如果 hemopi2 包尚未修复兼容性，执行以下修复
#    （修复将 os.system('python3') 改为 os.system(f'{sys.executable}')）
.venv/bin/python -c "
import sys
for script in ['hemopi2_classification.py', 'hemopi2_regression.py']:
    path = f'.venv/lib/python3.12/site-packages/hemopi2/python_scripts/{script}'
    with open(path, 'r') as f:
        content = f.read()
    if 'import sys' not in content:
        content = content.replace('import os', 'import os\nimport sys')
    content = content.replace(\"os.system(f'python3 \", \"os.system(f'{sys.executable} \")
    with open(path, 'w') as f:
        f.write(content)
    print(f'{script} 已修复')
"

# 5. 检查安装是否成功
hemopi2_classification -h
hemopi2_regression -h
```

### 命令速查表

#### 分类模式（hemopi2_classification）

```bash
# 基础用法
hemopi2_classification -i input.fasta -o result.csv -j 1 -m 1 -wd workdir

# 参数说明
# -i, --input     : 输入 FASTA 文件
# -o, --output    : 输出 CSV 文件（默认 outfile.csv）
# -j, --job       : 任务类型 1-5（见上方 Methodology）
# -m, --model     : 模型选择 1-4
#                   1 = Random Forest（默认，快）
#                   2 = Hybrid1（RF+MERCI，较准）
#                   3 = ESM2-t6（深度学习，准）
#                   4 = Hybrid2（ESM+MERCI，推荐但有bug）
# -t, --threshold : 阈值 0-1（默认 RF/Hybrid1=0.46, ESM/Hybrid2=0.55）
# -wd, --working  : 工作目录（必须提供，脚本在此读写临时文件）
```

#### 回归模式（hemopi2_regression）

```bash
# 基础用法
hemopi2_regression -i input.fasta -o hc50_result.csv -j 1 -wd workdir

# 参数说明
# -j, --job: 1=常规预测, 2=蛋白扫描
```

#### 各 Job 专项参数

```bash
# job=3（单点突变）需要额外参数
hemopi2_classification -i input.fasta -o result.csv -j 3 -m 1 -p 5 -r A -wd workdir
# -p, --Position : 突变位置（1-indexed，从1开始数）
# -r, --Residues : 突变后的氨基酸（如 A, G, K 等单字母）

# job=4（全突变扫描）只需指定位置，会自动尝试全部20种
hemopi2_classification -i input.fasta -o result.csv -j 4 -m 1 -p 5 -wd workdir

# job=2（蛋白扫描）可调整窗口长度
hemopi2_classification -i input.fasta -o result.csv -j 2 -m 1 -w 10 -wd workdir
# -w, --winleng : 窗口长度 8-20（默认8）
```

---

## Inputs and Outputs

### 输入格式

**FASTA 格式（推荐）**：
```fasta
>Peptide1
KFLKKIAKVI
>Peptide2
GLFDIVKKVG
```

**简单格式（每行一条）**：
```
KFLKKIAKVI
GLFDIVKKVG
```

### 输出格式

#### 分类输出（job=1）
```csv
SeqID,Sequence,ML Score,Prediction
Peptide1,KFLKKIAKVI,0.100,Non-Hemolytic
Peptide2,GLFDIVKKVG,0.235,Non-Hemolytic
Peptide3,LLGDFFRKSKEKIGKEFKRIVQRIKDFLRNLVPRTES,0.815,Hemolytic
```
- `ML Score`：溶血风险得分（0-1），越高越危险
- `Prediction`：Hemolytic（溶血）/ Non-Hemolytic（非溶血）

#### 回归输出（HC50）
```csv
SeqID,Sequence,HC50(μM),Prediction
Peptide1,KFLKKIAKVI,177.647,Non-Hemolytic
Peptide3,LLGDFFRKSKEKIGKEFKRIVQRIKDFLRNLVPRTES,18.949,Hemolytic
```
- `HC50(μM)`：50% 溶血所需浓度，数值越低毒性越强

#### 蛋白扫描输出（job=2）
```csv
SeqID,Pattern ID,Start,End,Sequence,ML Score,Prediction
Peptide3,Pattern_1,1,10,LLGDFFRKSK,0.270,Non-Hemolytic
Peptide3,Pattern_2,2,11,LGDFFRKSKE,0.270,Non-Hemolytic
...
```
显示序列各窗口的得分，可定位风险最高区段

#### 突变设计输出（job=3）
```csv
SeqID,Original Sequence,ML Score,Prediction,Mutant Sequence,Position,ML Score,Prediction
Peptide1,KFLKKIAKVI,0.1,Non-Hemolytic,AFLKKIAKVI,1,0.12,Non-Hemolytic
```
原始序列与突变后序列的对比

#### 全突变扫描输出（job=4）
```csv
SeqID,Mutant_ID,Sequences,ML Score,Prediction
Peptide1,Original_Seq1,KFLKKIAKVI,0.100,Non-Hemolytic
Peptide1,Mutant_K1A,AFLKKIAKVI,0.120,Non-Hemolytic
Peptide1,Mutant_K1C,CFLKKIAKVI,0.270,Non-Hemolytic
...
```
该位置全部 20 种氨基酸替换后的预测

#### 模体扫描输出（job=5）
```csv
SeqID,Positive Hits,Negative Hits,Prediction
Peptide1,0,1,Non-Haemolytic
Peptide2,0,1,Non-Haemolytic
```
- `Positive Hits`：匹配到的溶血相关模体数
- `Negative Hits`：匹配到的非溶血相关模体数

---

## Examples

### 示例 1：快速判断一条肽的溶血风险

```bash
# 使用 RF 模型预测
hemopi2_classification -i test.fasta -o result.csv -j 1 -m 1 -wd workdir

# 查看结果
cat workdir/result.csv
```

### 示例 2：定位长肽中最危险的区段

```bash
# 对 30 氨基酸的肽进行窗口扫描（窗口=10）
hemopi2_classification -i long_peptide.fasta -o scan.csv -j 2 -m 1 -w 10 -wd workdir

# 分析结果：找到最高分的窗口
# 高分窗口（>0.5）就是最危险的区段
```

### 示例 3：验证第 5 位换成丙氨酸是否能降低溶血性

```bash
# 单点突变测试
hemopi2_classification -i test.fasta -o mutant.csv -j 3 -m 1 -p 5 -r A -wd workdir

# 比较原始得分和突变后得分
```

### 示例 4：系统寻找第 1 位的最佳替换

```bash
# 全突变扫描（自动尝试全部20种）
hemopi2_classification -i test.fasta -o all_mutants.csv -j 4 -m 1 -p 1 -wd workdir

# 在结果中找 ML Score 最低的突变体
```

### 示例 5：预测 HC50 毒性浓度

```bash
# 回归模式
hemopi2_regression -i test.fasta -o hc50.csv -j 1 -wd workdir

# HC50 < 50 μM 通常表示高毒性
# HC50 > 100 μM 通常表示低毒性
```

### 示例 6：批量预测多条肽（适合虚拟筛选）

```bash
# 准备 FASTA 文件（多条序列）
cat > peptides.fasta << 'EOF'
>候选1
KFLKKIAKVI
>候选2
GLFDIVKKVG
>候选3
LLGDFFRKSKEKIGKEFKRIVQRIKDFLRNLVPRTES
EOF

# 批量预测
hemopi2_classification -i peptides.fasta -o screening.csv -j 1 -m 1 -t 0.46 -wd workdir

# 用更高阈值做粗筛（只保留低风险）
hemopi2_classification -i peptides.fasta -o safe.csv -j 1 -m 1 -t 0.7 -wd workdir
```

---

## Limits and Boundaries

### 已知限制

1. **序列长度限制**：超过 40 个氨基酸的序列会被截断（前 40 位）
2. **Hybrid2 bug**：Model 4 在某些情况下有 MERCI 文件路径 bug（缺少 `/`）
3. **Python 版本**：需要 Python 3.11 或 3.12（不支持 3.13+）
4. **不支持的氨基酸**：序列中包含 B, J, O, U, X, Z 会报错

### ⚠️ hemopi2 包兼容性修复

**问题描述：**
hemopi2 v1.3 包内部使用 `os.system('python3 ...')` 调用系统 Python，而非 venv 的 Python。当系统 Python 版本 ≥ 3.14 时，会因 `csv.writer(delimiter='\n')` 不再被接受而报错。

**症状：**
```
ValueError: bad delimiter value
```

**解决方案：**
需要修复 venv 中的 hemopi2 包，将 `python3` 替换为 `sys.executable`：

```bash
cd HemoPI2

# 修复 hemopi2_classification.py
.venv/bin/python -c "
import sys
script_path = '.venv/lib/python3.12/site-packages/hemopi2/python_scripts/hemopi2_classification.py'
with open(script_path, 'r') as f:
    content = f.read()
if 'import sys' not in content:
    content = content.replace('import os', 'import os\\nimport sys')
content = content.replace(\"os.system(f'python3 \", \"os.system(f'{sys.executable} \")
with open(script_path, 'w') as f:
    f.write(content)
print('hemopi2_classification.py 已修复')
"

# 修复 hemopi2_regression.py
.venv/bin/python -c "
import sys
script_path = '.venv/lib/python3.12/site-packages/hemopi2/python_scripts/hemopi2_regression.py'
with open(script_path, 'r') as f:
    content = f.read()
if 'import sys' not in content:
    content = content.replace('import os', 'import os\\nimport sys')
content = content.replace(\"os.system(f'python3 \", \"os.system(f'{sys.executable} \")
with open(script_path, 'w') as f:
    f.write(content)
print('hemopi2_regression.py 已修复')
"
```

**注意：** 此修复需要在使用 venv 激活后执行。如果重新安装 hemopi2 包，需要重新执行此修复。

### 版本验证命令

```bash
# 查看已安装版本
pip show hemopi2

# 查看 Python 版本
python --version

# 检查 torch 是否安装
python -c "import torch; print(torch.__version__)"

# 验证 hemopi2 包是否已修复（检查 sys.executable 使用）
grep -l "sys.executable" .venv/lib/python3.12/site-packages/hemopi2/python_scripts/*.py
# 如果输出两个脚本名，说明已修复
```

### 不适用场景

- 非肽类分子（只适用于氨基酸序列）
- 未知修饰的肽（化学修饰肽建议用旧版 HemoPI-MOD）
- 哺乳动物以外物种的红细胞（模型基于哺乳动物 RBC 训练）

### 注意事项

- **阈值选择**：默认阈值并非最优，可根据实际数据集调整
  - 保守筛选（尽量保留）：用高阈值如 0.7
  - 宽松筛选（只剔除高风险）：用低阈值如 0.4
- **首次运行**：ESM2 模型首次使用会下载预训练权重，需网络连接
- **工作目录**：必须提供 `-wd` 参数，且路径不应包含特殊字符

---

## 快速参考卡

```
╔════════════════════════════════════════════════════════════╗
║                    HemoPI2 快速参考                         ║
╠════════════════════════════════════════════════════════════╣
║ 分类预测        │ hemopi2_classification -i X -o Y -j 1    ║
║ HC50回归        │ hemopi2_regression -i X -o Y -j 1        ║
║ 定位危险区段    │ -j 2 -w 10                               ║
║ 单点突变设计    │ -j 3 -p 5 -r A                           ║
║ 全突变扫描      │ -j 4 -p 5                                ║
║ 模体扫描        │ -j 5                                     ║
╠════════════════════════════════════════════════════════════╣
║ 模型选择        │ -m 1(RF) 2(Hybrid1) 3(ESM2) 4(Hybrid2)  ║
║ 常用阈值        │ RF: 0.46 / ESM: 0.55                     ║
╚════════════════════════════════════════════════════════════╝
```

---

## 版本更新检查

> 工具发布新版本后，用法或功能可能发生变化。使用前建议检查：

```bash
# 1. 检查 pip 上的最新版本
pip index versions hemopi2

# 2. 查看当前安装版本
pip show hemopi2

# 3. 查看 GitHub 是否有更新
# https://github.com/raghavagps/HemoPI2/releases
```

如版本有更新，请在 `.memory/` 中记录变更内容。

---

## 引用

- 论文：Rathore et al., Commun Biol 8, 176 (2025)
- 官网：https://webs.iiitd.edu.in/raghava/hemopi2/
- GitHub：https://github.com/raghavagps/HemoPI2
- PyPI：https://pypi.org/project/hemopi2/
