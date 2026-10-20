> **English** | [中文](how_to_use_esm.zh.md)

You can use ESM directly as a Python library, or you can use the command-line tools that ship with it (such as `esm-fold` and `esm-extract`). The core dependencies are PyTorch and a suitable Python/CUDA environment.

Below I cover two parts: environment requirements + common usage patterns.

------

## Environment and Dependencies

## Base Environment

- You must install **PyTorch** first and then install ESM; all models in this repository are built on PyTorch.
- A **Linux** or WSL/server environment is recommended, ideally with a GPU (large models and structure prediction are very GPU-memory hungry).

## Python Version Requirements

- For the regular ESM/ESM-2 language models: an ordinary PyTorch environment is enough; Python 3.8/3.9/3.10 usually all work (subject to the PyTorch version you install).
- **ESMFold (the structure prediction model)**: the official instructions require starting from an environment with **Python ≤ 3.9** and PyTorch already installed.

## Installation

1. Install PyTorch (pick the command for your machine's CUDA version at https://pytorch.org).
2. Install ESM:

```
bash
# Stable release
pip install fair-esm

# Or install directly from the GitHub main branch ("latest")
pip install git+https://github.com/facebookresearch/esm.git
```

1. To use **ESMFold** for structure prediction, you need to install the additional OpenFold-related dependencies, and the machine must have `nvcc` (the CUDA compiler):

```
bash
pip install "fair-esm[esmfold]"
pip install 'dllogger @ git+https://github.com/NVIDIA/dllogger.git'
pip install 'openfold @ git+https://github.com/aqlaboratory/openfold.git@4b41059694619831a7db195b7e0988fc4ff3a307'
```

- If the OpenFold installation fails, the official guidance is to check whether `nvcc` for the corresponding CUDA version is installed, and whether PyTorch is a **CUDA-enabled** build.
- You can also use the ready-made `conda` environment file: `conda env create -f environment.yml` (the repository provides an `esmfold` environment).

------

## Using ESM Models in Python

## 1. Load an ESM-2 Language Model and Extract Embeddings

The most common usage is to load an ESM-2 model and extract per-token or per-sequence embeddings for protein sequences, for downstream tasks (structure prediction, function prediction, variant effect modeling, etc.).

```
python
import torch
import esm

# Load an ESM-2 model (example: 33 layers, 650M parameters)
model, alphabet = esm.pretrained.esm2_t33_650M_UR50D()
batch_converter = alphabet.get_batch_converter()
model.eval()  # disable dropout so results are reproducible

# Prepare sequence data: (name, sequence)
data = [
    ("protein1", "MKTVRQERLKSIVRILERSKEPVSGAQLAEELSVSRQVIVQDIAYLRSLGYNIVATPRGYVLAGG"),
    ("protein2", "KALTARQQEVFDLIRDHISQTGMPPTRAEIAQRLGFRSPNAAEEHLKALARKGVIEIVSGASRGIRLLQEE"),
]

batch_labels, batch_strs, batch_tokens = batch_converter(data)
batch_lens = (batch_tokens != alphabet.padding_idx).sum(1)

with torch.no_grad():
    results = model(batch_tokens, repr_layers=[33], return_contacts=True)
token_representations = results["representations"][33]

# Compute the mean embedding for each sequence (per-sequence representation)
sequence_representations = []
for i, tokens_len in enumerate(batch_lens):
    seq_repr = token_representations[i, 1:tokens_len - 1].mean(0)
    sequence_representations.append(seq_repr)
```

This code shows:

- how to load a pretrained ESM-2 model;
- how to convert string sequences into tensors;
- how to get the representation of each amino acid as well as the mean representation of the whole sequence.

------

## Using ESMFold for Structure Prediction

After installing `fair-esm[esmfold]` and the OpenFold dependencies, you can predict a PDB directly in Python:

```
python
import torch
import esm

model = esm.pretrained.esmfold_v1()
model = model.eval().cuda()  # recommend moving it to the GPU

sequence = "MKTVRQERLKSIVRILERSKEPVSGAQLAEELSVSRQVIVQDIAYLRSLGYNIVATPRGYVLAGG"

with torch.no_grad():
    pdb_str = model.infer_pdb(sequence)

with open("result.pdb", "w") as f:
    f.write(pdb_str)
```

- This directly produces a PDB string that can be written to `result.pdb`.
- You can analyze it further with Biotite or PyMOL. Biotite example (to read pLDDT):

```
python
import biotite.structure.io as bsio
struct = bsio.load_structure("result.pdb", extra_fields=["b_factor"])
print(struct.b_factor.mean())  # mean pLDDT
```

------

## Using the Command-Line Tools (No Code Needed)

After installing the package, the repository ships two commonly used CLIs:

## 1. `esm-fold`: Batch Structure Prediction

```
bash
esm-fold -i input.fasta -o output_dir \
  --max-tokens-per-batch 4096 \
  --chunk-size 128 \
  --cpu-offload
```

- `-i`: input FASTA file.
- `-o`: output directory for PDB files.
- `--chunk-size` / `--max-tokens-per-batch`: reduce memory usage on long sequences or GPUs with less memory.
- `--cpu-offload`: move some parameters to CPU memory to reduce GPU memory pressure.

## 2. `esm-extract`: Batch Embedding Extraction from FASTA

```
bash
esm-extract esm2_t33_650M_UR50D some_proteins.fasta some_proteins_emb_esm2 \
  --repr_layers 0 32 33 --include mean per_tok
```

- The inputs are the model name + FASTA file; the output directory gets one `.pt` file per sequence, which can be loaded with `torch.load()`.
- `--repr_layers`: select the layers to save; `--include` decides what to save, such as the mean embedding and the per-token embedding.

------

## Other Routes (Lower-Effort Options)

If you just want to try things out quickly, you don't necessarily have to build the environment yourself:

- **HuggingFace Transformers**: you can call ESM and ESMFold directly through `AutoModel`/`AutoTokenizer`; HuggingFace has simplified the dependencies and provides a unified API.

- **ColabFold with integrated ESMFold**: can be run directly in Google Colab, suitable when you have no local GPU or don't want to configure the environment.

- **ESM Atlas API**: you can `curl` a sequence to the official API and get a PDB back directly, for example:

  ```
  bash
  curl -X POST --data "YOUR_PROTEIN_SEQUENCE" \
    https://api.esmatlas.com/foldSequence/v1/pdb/
  ```

------

If you can tell me more about your use case (for example, "I only want structure prediction", "I mainly do variant scoring", "I want to extract embeddings to train downstream models"), I can write a more targeted minimal example script and recommend an environment setup for you.
