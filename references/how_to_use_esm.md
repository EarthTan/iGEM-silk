可以直接把 ESM 当作一个 Python 库来用，也可以用它自带的命令行工具（如 `esm-fold`、`esm-extract`），核心依赖是 PyTorch 和合适的 Python/CUDA 环境。

下面分两部分说：环境要求 + 常见使用方式。

------

## 环境与依赖

## 基础环境

- 必须先安装 **PyTorch**，再安装 ESM，本仓库所有模型都基于 PyTorch。
- 建议使用 **Linux** 或 WSL/服务器环境，有 GPU 更合适（大模型和结构预测非常吃显存）。

## Python 版本要求

- 一般的 ESM/ESM‑2 语言模型：普通 PyTorch 环境即可，Python 3.8/3.9/3.10 通常都能用（以你安装的 PyTorch 版本为准）。
- **ESMFold（结构预测模型）**：官方要求从一个 **Python ≤ 3.9** 且已安装 PyTorch 的环境开始。

## 安装方式

1. 安装 PyTorch（根据你机器的 CUDA 版本，在 https://pytorch.org 选择命令）。
2. 安装 ESM：

```
bash
# 稳定版
pip install fair-esm

# 或直接从 GitHub 主分支安装（“最新版”）
pip install git+https://github.com/facebookresearch/esm.git
```

1. 如果要用 **ESMFold** 做结构预测，需要额外安装 OpenFold 相关依赖，并要求本机有 `nvcc`（CUDA 编译器）：

```
bash
pip install "fair-esm[esmfold]"
pip install 'dllogger @ git+https://github.com/NVIDIA/dllogger.git'
pip install 'openfold @ git+https://github.com/aqlaboratory/openfold.git@4b41059694619831a7db195b7e0988fc4ff3a307'
```

- 若 OpenFold 安装失败，官方建议检查是否安装了 CUDA 对应的 `nvcc`，以及 PyTorch 是否是 **支持 CUDA** 的版本。
- 也可以用现成的 `conda` 环境文件：`conda env create -f environment.yml`（仓库里提供了 `esmfold` 环境）。

------

## 在 Python 中使用 ESM 模型

## 1. 加载 ESM‑2 语言模型并抽取嵌入

最常见的用法是加载 ESM‑2 模型，对蛋白序列抽取 per‑token 或 per‑sequence embedding，用于下游任务（结构预测、功能预测、变体效应建模等）。

```
python
import torch
import esm

# 加载 ESM-2 模型（示例：33 层、650M 参数）
model, alphabet = esm.pretrained.esm2_t33_650M_UR50D()
batch_converter = alphabet.get_batch_converter()
model.eval()  # 关闭 dropout，结果可复现

# 准备序列数据：(name, sequence)
data = [
    ("protein1", "MKTVRQERLKSIVRILERSKEPVSGAQLAEELSVSRQVIVQDIAYLRSLGYNIVATPRGYVLAGG"),
    ("protein2", "KALTARQQEVFDLIRDHISQTGMPPTRAEIAQRLGFRSPNAAEEHLKALARKGVIEIVSGASRGIRLLQEE"),
]

batch_labels, batch_strs, batch_tokens = batch_converter(data)
batch_lens = (batch_tokens != alphabet.padding_idx).sum(1)

with torch.no_grad():
    results = model(batch_tokens, repr_layers=[33], return_contacts=True)
token_representations = results["representations"][33]

# 求每条序列的平均 embedding（per-sequence 表征）
sequence_representations = []
for i, tokens_len in enumerate(batch_lens):
    seq_repr = token_representations[i, 1:tokens_len - 1].mean(0)
    sequence_representations.append(seq_repr)
```

这段代码展示了：

- 如何加载预训练 ESM‑2 模型；
- 如何把字符串形式的序列转成张量；
- 如何得到每个氨基酸的表示，以及整条序列的平均表示。

------

## 使用 ESMFold 做结构预测

在安装了 `fair-esm[esmfold]` 和 OpenFold 依赖后，可以在 Python 中直接预测 pdb：

```
python
import torch
import esm

model = esm.pretrained.esmfold_v1()
model = model.eval().cuda()  # 建议放到 GPU 上

sequence = "MKTVRQERLKSIVRILERSKEPVSGAQLAEELSVSRQVIVQDIAYLRSLGYNIVATPRGYVLAGG"

with torch.no_grad():
    pdb_str = model.infer_pdb(sequence)

with open("result.pdb", "w") as f:
    f.write(pdb_str)
```

- 这会直接生成一个 PDB 字符串，可写入 `result.pdb`。
- 你可以用 Biotite 或 PyMOL 进一步分析，Biotite 示例（用于取 pLDDT）：

```
python
import biotite.structure.io as bsio
struct = bsio.load_structure("result.pdb", extra_fields=["b_factor"])
print(struct.b_factor.mean())  # 平均 pLDDT
```

------

## 使用命令行工具（无需自己写代码）

安装包后，仓库自带两个常用 CLI：

## 1. `esm-fold`：批量结构预测

```
bash
esm-fold -i input.fasta -o output_dir \
  --max-tokens-per-batch 4096 \
  --chunk-size 128 \
  --cpu-offload
```

- `-i`：输入 FASTA 文件。
- `-o`：输出 PDB 文件目录。
- `--chunk-size` / `--max-tokens-per-batch`：在长序列或显存较小的 GPU 上减小内存占用。
- `--cpu-offload`：将部分参数放到 CPU 内存，减少 GPU 显存压力。

## 2. `esm-extract`：从 FASTA 批量抽取嵌入

```
bash
esm-extract esm2_t33_650M_UR50D some_proteins.fasta some_proteins_emb_esm2 \
  --repr_layers 0 32 33 --include mean per_tok
```

- 输入是模型名称 + FASTA 文件，输出目录中每个序列生成一个 `.pt` 文件，可用 `torch.load()` 读入。
- `--repr_layers`：选择要保存的层；`--include` 决定保存 mean embedding、per‑token embedding 等。

------

## 其他使用途径（更“省事”的方案）

如果你只是想快速试一下，不一定要自己搭环境：

- **HuggingFace Transformers**：可以直接通过 `AutoModel`/`AutoTokenizer` 调用 ESM 和 ESMFold，HuggingFace 对依赖做了简化，并提供统一 API。

- **ColabFold 集成 ESMFold**：可以在 Google Colab 里直接运行，适合没有本地 GPU 或懒得配环境的情况。

- **ESM Atlas API**：可以用 `curl` 把序列发到官方 API，直接返回 PDB，例如：

  ```
  bash
  curl -X POST --data "YOUR_PROTEIN_SEQUENCE" \
    https://api.esmatlas.com/foldSequence/v1/pdb/
  ```

------

如果你能补充一下你的使用场景（比如“只想做结构预测”“主要做变体打分”“想抽 embedding 训练下游模型”），我可以帮你写一个更针对性的最小示例脚本和推荐环境配置。