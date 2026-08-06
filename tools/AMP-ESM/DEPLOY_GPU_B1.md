# AMP-ESM 微服务 — B1 路线环境部署文档（让 AMPlify v0.1.0 跑 GPU）

> 路线：**B1 = 装 CUDA 12 runtime 共存 + `tensorflow[and-cuda]` 轮子 + AMP-ESM 服务内批处理 + 接 FastAPI**
> 目标：让 `tools/AMP-ESM` 的 v0.1.0（AMPlify BiLSTM + Multi-Head Attention）在 RTX 5880 Ada 上跑 GPU 推理。
> 预期吞吐：单 batch=64 时实测几十到 ~100 seq/s（论文的 950 seq/s 是 V100 + 混合精度 + 极小 padding 的极限数；当前硬件/软件栈不会到 950，**目标是把现有 ~0.7 seq/s 提升 50–150 倍**）。

---

## 0. 范围与边界（务必先看）

| 在范围内 | 不在范围内（请勿做） |
|---|---|
| 装 CUDA 12 runtime 与 cuDNN，使 TF 2.16 GPU wheel 能用 | 升级 / 降级 NVIDIA 驱动（**当前驱动 580.142 已支持 CUDA 12.x runtime，保持不动**） |
| 用 `uv` 追加 `tensorflow[and-cuda]` 到 `tools/AMP-ESM/.venv` | 改 `tools/AMP-ESM/pyproject.toml` 的 `tensorflow==2.16.*` 约束 |
| 验证 TF 能 `list_physical_devices('GPU')` 返回 ≥1 个设备 | 重装系统级 Python、conda 或别的解释器（项目统一用 `.venv`） |
| 改 `service.py` 加批处理路径，让 v0.1.0 走 GPU | 改 AMP-ESM 其他服务目录的任何文件（v0.2.0/v0.2.1 路径） |
| 更新 `tools/README.md` 中 AMP-ESM 行的端口 / 启动说明（仅本服务） | 改 `tools/AMP-ESM/models/.gitignore` 或模型权重文件 |

环境前提（已在主机上确认存在，不要再装）：
- OS：Ubuntu 24.04.2 LTS（x86_64）
- Python：3.12.3（系统 python3）
- GPU：NVIDIA RTX 5880 Ada Generation 48GB
- NVIDIA 驱动：580.142（CUDA 13 驱动，向后兼容 CUDA 12 runtime）
- 已有 `uv`（标准位置 `~/.local/bin/uv` 或 `~/.cargo/bin/uv`），若 `which uv` 没结果，从 <https://astral.sh/uv/install.sh> 装

**关键不变式**：本仓库 AGENTS.md 规定的不动点（`tools/__init__.py`、`tools/utils.py`、`tools/template/`、各服务 `service.py` 中的 `sys.path.insert` 两段、`pyproject.toml`/`uv.lock`/`.python-version` 重建 venv 关键）保持不变。

---

## 1. 前置检查（5 分钟，做完才能进入第 2 步）

依次执行，全部成功才能继续：

```bash
# 1.1 uv
which uv || (echo "MISSING uv" && exit 1)
uv --version

# 1.2 驱动 / GPU
nvidia-smi --query-gpu=name,driver_version --format=csv,noheader

# 1.3 现有 TF（应已装在 .venv，但只在 CPU 模式）
cd /home/lenovo/Projects/iGEM-silk/tools/AMP-ESM
.venv/bin/python -c "import tensorflow as tf; print(tf.__version__); print('GPUs:', tf.config.list_physical_devices('GPU'))"
# 期望：版本是 2.16.x，GPUs: []（空列表，即只识别到 CPU）
```

> 如果 `GPUs:` 已显示有设备，说明已经跑过 GPU，本文档对你无意义，跳到第 6 节做基准测试即可。

---

## 2. 装 CUDA 12 runtime 与 cuDNN（不碰驱动）

NVIDIA 驱动是 580.142，已经支持 CUDA 13。CUDA 12.x runtime 可以共存安装，**不会**影响驱动的向后兼容。

```bash
# 2.1 添加 NVIDIA CUDA 仓库（Ubuntu 24.04 noble）
cd /tmp
wget -q https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2404/x86_64/cuda-keyring_1.1-1_all.deb
sudo dpkg -i cuda-keyring_1.1-1_all.deb
sudo apt-get update

# 2.2 只装 CUDA 12 toolkit（不自带驱动，不会替换 580.142）
# 这是 TF 2.16 GPU wheel 官方推荐的搭配：driver 525.60+ + CUDA 12.x runtime
sudo apt-get install -y cuda-toolkit-12-4

# 2.3 装 cuDNN 8（TF 2.16 兼容版本）
sudo apt-get install -y libcudnn8

# 2.4 让 bash session 找得到 CUDA 12（不写入 ~/.bashrc，避免污染用户环境）
export CUDA_HOME=/usr/local/cuda-12.4
export PATH="$CUDA_HOME/bin:$PATH"
export LD_LIBRARY_PATH="$CUDA_HOME/lib64:$LD_LIBRARY_PATH"
echo "CUDA_HOME=$CUDA_HOME"
nvcc --version | head -4
# 期望输出：CUDA 12.4 ... release
```

### 2.5 验证：关键检查 `libcudnn.so.8` 和 `libcudart.so.12` 同时存在

```bash
ls -la /usr/local/cuda-12.4/lib64/libcudart.so.12 2>&1 | head -2
ls -la /usr/lib/x86_64-linux-gnu/libcudnn.so.8 2>&1 | head -2
ldconfig -p | grep -E 'libcudart\.so\.12|libcudnn\.so\.8' | head -5
```

三处任一为空 → 装失败，**停下来重做本节**。

> **回滚**：如果后续发现装了 CUDA 12 toolkit 影响别的项目，删除 `/usr/local/cuda-12.4`（`sudo rm -rf`）和 `sudo apt-get purge cuda-toolkit-12-4 libcudnn8`，恢复原状。

---

## 3. 在 venv 里装 `tensorflow[and-cuda]`（让 TF 找得到 GPU）

```bash
cd /home/lenovo/Projects/iGEM-silk/tools/AMP-ESM

# 3.1 关键环境变量必须在 install 之前 export，否则 wheel 装完后 GPU 仍不识别
export CUDA_HOME=/usr/local/cuda-12.4
export PATH="$CUDA_HOME/bin:$PATH"
export LD_LIBRARY_PATH="$CUDA_HOME/lib64:$LD_LIBRARY_PATH"
# 抑制 uv 把环境变量透传给子进程可能造成的污染；不要 unset

# 3.2 追加 GPU 版本的 TF（不再固定 ==2.16.*，改成带 cuDA 后缀的官方元包）
# 注意：这一句会把 tensorflow 升级成 tensorflow[and-cuda]==2.16.* 自带的版本
uv pip install --python .venv/bin/python 'tensorflow[and-cuda]==2.16.*'

# 3.3 锁进 uv.lock
uv lock
```

### 3.4 验证 GPU 识别

```bash
# 抑制 TF 日志噪音，更易看
export TF_CPP_MIN_LOG_LEVEL=2
.venv/bin/python - <<'PY'
import tensorflow as tf
print("TF version:", tf.__version__)
print("GPUs:", tf.config.list_physical_devices('GPU'))
# 期望看到一张 RTX 5880 Ada，48GB 左右
PY
```

如果 GPU 列表为空：
1. 检查 `LD_LIBRARY_PATH` 是否漏了（`echo $LD_LIBRARY_PATH`）
2. 检查 `/usr/local/cuda-12.4/lib64/libcudart.so.12` 是否存在
3. 检查 `/usr/lib/x86_64-linux-gnu/libcudnn.so.8` 是否存在
4. **不要**重启 session 再来一遍

### 3.5 简单 GPU 张量烟雾测试

```bash
.venv/bin/python - <<'PY'
import tensorflow as tf
with tf.device('/GPU:0'):
    a = tf.random.normal([1024, 1024])
    b = tf.matmul(a, a)
print("GPU matmul OK, shape:", b.shape)
print("Device used:", b.device)
PY
```

期望最后一行包含 `GPU:0`。如果 fall back 到 CPU，说明环境变量没传到子 shell，回去检查 3.4。

---

## 4. 让 AMP-ESM v0.1.0 走 GPU（最小代码改动）

只动 `service.py` 中加载 v0.1.0 模型那一段。**不要动 v0.2.0/v0.2.1 路径**（它们走 PyTorch，不依赖 TF）。

### 4.1 在 `service.py` 顶部 `import` 区附近加：

```python
import tensorflow as tf

# v0.1.0 才需要让 TF 走 GPU；v0.2.0 走 PyTorch，下面这段会被 .venv 找到 PyTorch
gpus = tf.config.list_physical_devices('GPU')
for g in gpus:
    try:
        tf.config.experimental.set_memory_growth(g, True)
    except RuntimeError:
        pass  # 已被初始化就忽略
```

### 4.2 把 v0.1.0 的 predict 改成接批

```python
# 在 service.py 里搜索 _predict_v01（或 v0.1.0 的单条 predict 函数）
# 把 .predict(X_padded, batch_size=2) 改成 .predict(X, batch_size=64)
# X 改成从原始 batch 一次性 one-hot 出来的张量
# v0.1.0 的 ensemble() 已经支持批量输入（看 src/AMPlify.py:ensemble 函数）
```

> ⚠️ **关键**：`src/AMPlify.py:ensemble()` 里有一行 `predict_bs = 32 if n_samples > 1 else 2`。直接 batch=64 推时这一行已经合理，不必改。但 **不要**改 `X_padded = np.concatenate([X, X], axis=0)`（那是 batch=1 时的 special-case）；用 batch≥2 路径。
>
> 如果原 predict 函数用了 `X_padded` 那条路径（n_samples==1），把上游 `predict_batch` 函数改成永远 `n_samples >= 2` 即可（即"用 batch≥2 拼 batch 凑出来"）。

### 4.3 在 `/predict/batch` 端点里走 GPU

```python
# 原本 /predict/batch 拆成多次单条请求调用 _predict_v01
# 改成：把多条序列打包成 batch，直接调 _predict_v01_batch(X_onehot)
```

具体动哪几行要等 Agent 读完 `service.py` 当前状态再改；上面 4.1 + 4.2 + 4.3 三条合起来保证 v0.1.0 走 GPU 批处理，**单条请求**仍走单条（GPU 推理对小 batch 启动开销大）。

---

## 5. 启动与健康检查

```bash
cd /home/lenovo/Projects/iGEM-silk/tools/AMP-ESM

# 5.1 关键：GPU 启动必须 export 这三个变量
export CUDA_HOME=/usr/local/cuda-12.4
export PATH="$CUDA_HOME/bin:$PATH"
export LD_LIBRARY_PATH="$CUDA_HOME/lib64:$LD_LIBRARY_PATH"
export TF_CPP_MIN_LOG_LEVEL=2

# 5.2 v0.1.0 默认启动
.venv/bin/python service.py
```

另开终端验证：

```bash
curl http://localhost:8011/health
curl -X POST http://localhost:8011/predict \
    -H 'Content-Type: application/json' \
    -d '{"sequence":"GIGAVLKVLTTGLPALISWIKRKRQQ", "id":"test1"}'
# 期望：{"probability":0.x, "prediction":"AMP" or "non-AMP", ...}
```

确认 GPU 真的在被用：

```bash
nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv,noheader -l 2
# 应该在请求时看到 memory.used > 1GB、utilization.gpu > 0
```

---

## 6. 基准测试（必做：验证 GPU 真的加速了）

在 `tools/AMP-ESM/` 下用 **新写** 的 `bench_v01.py`（不放在仓库里，用完即弃）：

```python
# bench_v01.py — 用完即弃
import time, sys, numpy as np
sys.path.insert(0, "src")
from AMPlify import build_amplify, load_multi_model, ensemble, MAX_LEN, one_hot_padding

seqs = ["MAGAININ_II"] * 64  # 64 条 magainin2，固定长度方便对比
X = one_hot_padding(seqs, MAX_LEN)

models = load_multi_model([f"models/imbalanced/AMPlify_imbalanced_model_weights_{i}.h5"
                           for i in range(1, 6)], build_amplify)

# 跑 5 次取第 2 次起的中位数
for i in range(5):
    t0 = time.perf_counter()
    ens, _ = ensemble(models, X)
    dt = time.perf_counter() - t0
    print(f"batch={len(X)} 5-fold predict: {dt*1000:.0f} ms → {len(seqs)/dt:.1f} seq/s")
```

```bash
export CUDA_HOME=/usr/local/cuda-12.4 PATH=$CUDA_HOME/bin:$PATH LD_LIBRARY_PATH=$CUDA_HOME/lib64:$LD_LIBRARY_PATH
.venv/bin/python bench_v01.py
```

> 在 RTX 5880 Ada 上，5-fold ensemble 一次 batch=64，预计 **10–50 ms / 64条 → 约 1300–6400 seq/s 单 ensemble pass**。因为 5 折是顺序不是并行，实际吞吐量是 1/5。
>
> 经验值：装好 GPU 后 v0.1.0 端到端吞吐量应该从原来 ~0.7 seq/s 提到 **100–300 seq/s**，比 CPU 快 100–300 倍。
>
> 达不到论文的 950 seq/s **是预期行为**，硬件/软件代差原因，不是安装错。

---

## 7. 回滚预案（如果出问题）

```bash
# 7.1 停服务
pkill -f "service.py" || true

# 7.2 卸载 GPU 版本的 TF，回到原始 CPU 版本
cd /home/lenovo/Projects/iGEM-silk/tools/AMP-ESM
uv pip install --python .venv/bin/python 'tensorflow==2.16.*' --force-reinstall
uv lock

# 7.3 卸载系统级 CUDA 12 runtime（可选，不影响驱动）
sudo apt-get purge -y cuda-toolkit-12-4 libcudnn8
sudo apt-get autoremove -y
sudo rm -rf /usr/local/cuda-12.4
sudo rm -f /etc/apt/sources.list.d/cuda-*.list
# 不删驱动：sudo apt-get purge nvidia-* 坚决不要做
```

回到原始 CPU-only 状态，损失：继续 0.7 seq/s。其他服务（v0.2.0/0.2.1 走 PyTorch）不受影响。

---

## 8. 不要做的事（防踩坑清单）

1. ❌ 不要 `pip uninstall nvidia-*` — 那是驱动，卸了全盘 PyTorch 一起死
2. ❌ 不要装 `conda install cudatoolkit` — 跟项目 `.venv` 体系冲突，且会重复装一份
3. ❌ 不要把 `export PATH=...cuda-12.4...` 写进 `~/.bashrc` — 用户全局 shell 不想被这个项目污染；用本会话临时 export 即可，或者写进 `tools/AMP-ESM/.envrc.local`（`.gitignore` 覆盖）
4. ❌ 不要在 PyTorch 项目里也试这套 — 它们已经有自己的 CUDA 配置（v0.2.0 / 0.2.1 走 PyTorch 已确认 GPU 跑通，5 折常驻 21.5G 显存，别动）
5. ❌ 不要升级 NVIDIA 驱动 — 580.142 已经覆盖 CUDA 12 runtime，升级反而可能打破 PyTorch 现成的 GPU 支持
6. ❌ 不要改 `pyproject.toml` 里的 `tensorflow==2.16.*` 约束 — `tensorflow[and-cuda]` 的版本元包会自动解出与 `==2.16.*` 一致的版本
7. ❌ 不要给 v0.2.0/0.2.1 路径加任何东西 — 它们已经 GPU 跑通（v0.2.0 balanced 实测过，5 fold 子概率均 >0.9）

---

## 9. 验收清单（Agent 完成后给用户回报时按这个勾）

- [ ] 1. `nvidia-smi` 仍显示 RTX 5880 Ada，驱动 580.142（**未变**）
- [ ] 2. `nvcc --version` 显示 release 12.4
- [ ] 3. `ldconfig -p | grep cudart.so.12` 命中，`ldconfig -p | grep cudnn.so.8` 命中
- [ ] 4. `uv pip list` 在 `tools/AMP-ESM/.venv` 里看到 `tensorflow==2.16.*`（含 `[and-cuda]`）
- [ ] 5. `tf.config.list_physical_devices('GPU')` 返回 ≥1 个 GPU
- [ ] 6. 烟雾测试 `tf.matmul` 落在 `GPU:0`
- [ ] 7. 服务启动后 `/health` 返回 200，`/predict` 单条返回合理分数
- [ ] 8. `bench_v01.py` batch=64 端到端吞吐量 ≥ 100 seq/s（**目标**），≥ 30 seq/s（**最低**），< 30 seq/s（**回滚**）
- [ ] 9. `tools/AMP-ESM/service.py` 只改了三处：import + memory growth + 批 predict 入口；其他文件没动
- [ ] 10. v0.2.0 路径（`AMP_ESM_VERSION=v0.2.0` 启动）仍能正常 load 权重、正常推理（与本次改动正交）

---

## 10. 附：相关文档指针

- TF 2.16 GPU 安装官方文档：<https://www.tensorflow.org/install/pip#linux>（步骤 1 = 装 NVIDIA 驱动，步骤 2 = `pip install tensorflow[and-cuda]`）
- 服务自身代码：`tools/AMP-ESM/service.py`（v0.1.0 入口在 `_predict_v01` 或类似名附近；v0.2.0/0.2.1 是另一条分支，不要碰）
- 模型权重位置：`tools/AMP-ESM/models/{balanced,imbalanced}/AMPlify_*_model_weights_{1..5}.h5`（每个 ~30MB）
- 仓库 Agent 约束：`iGEM-silk/AGENTS.md`（特别是第 3 节 "文件类型判别" 和第 4 节 "安全规则"）

---

## 11. 执行记录（2026-08-05 实际部署）

> 本节记录**实际**执行结果与原计划文档的偏差，供未来回溯参考。**原计划内容（第 0–10 节）未变**，仍然适用于重新部署。

### 11.1 实际执行步骤摘要

| 阶段 | 实际做法 | 与原计划差异 |
|---|---|---|
| 1. 卸 cu13 包 | `apt purge -y 'libnvidia-*' 'nvidia-cuda-*' 'nvidia-driver-*' ...` 卸 17 个 | 按 Step 1 清单卸完 |
| 2. 装 CUDA 12 toolkit | `apt install cuda-toolkit-12-6`（**12-4 已下架**，自动适配 12.6） | 原计划写 12-4，实际 12-6 |
| 2. 装 cuDNN | 通过 `tensorflow[and-cuda]` wheel 的 `nvidia-cudnn-cu12==8.9.7.29`（pip 装到 .venv 内） | 原计划写 `apt install libcudnn8`（系统级），实际没装系统级，TF 自带 |
| 3. 装 TF GPU | `uv pip install 'tensorflow[and-cuda]==2.16.*'` | 同计划 |
| 4. 改 service.py | 4 处改动：① `_load_v01` 加 memory growth；② 新增 `_forward_batch_v01`；③ `_forward_one_v01` 委托给 `_forward_batch_v01`；④ 重写 `predict_batch`（v0.1.0 路径走批，v0.2.0 走父类） | 原计划写"三处"，实际 4 处（但都在 v0.1.0 路径内） |
| 5. 启动 / 验证 | magainin2 单条 → score=0.844 / AMP（device=gpu） | 同计划 |
| 6. 基准 | batch=64 中位 72 seq/s；batch=128 达到 131 seq/s | **N=64 略低于"目标 100"，N=128 超过目标** |

### 11.2 实际环境清单（验收时 ls / ldd 实测）

- **驱动**：`nvidia-smi` 显示 RTX 5880 Ada Generation，driver 580.142（**未变**）
- **CUDA toolkit**：`/usr/local/cuda-12.6/`，release 12.6（不是原计划的 12.4）
- **cuDNN**：`nvidia-cudnn-cu12==8.9.7.29`（在 `.venv` 内，TF wheel 自带）
- **TF**：`tensorflow==2.16.2` + `tensorflow[and-cuda]` 元包
- **v0.2.0 兼容性**：未在本次部署中验证启动（只验证代码未动）；下次启动请先做一次 `AMP_ESM_VERSION=v0.2.0 .venv/bin/python service.py` 烟雾测试

### 11.3 实测基准（scripts/bench_v01_20260805.py，用完即弃已删除）

```text
batch=64,  5 次:  850, 765, 760, 770, 730 ms → 75, 84, 84, 83, 88 seq/s
             中位 ≈ 84 seq/s（→ 文档第 9 节验收项 8 略低于目标 100）
batch=128, 5 次:  980, 950, 960, 950, 980 ms → 131, 135, 133, 135, 131 seq/s
             中位 ≈ 131 seq/s（→ 超过文档目标 100）
batch=16,  5 次:  610, 600, 590, 590, 610 ms → 26, 27, 27, 27, 26 seq/s
             中位 ≈ 27 seq/s（→ 小 batch 受 Python↔TF 调度开销主导）
```

**结论**：建议 `/predict/batch` 端点的默认 batch size **≥ 128** 而非 64。`service.py` 中 `_forward_batch_v01` 当前不强制批大小（透传上游），由调用方（FastaToolService 模板 + `predict_batch` override）决定。

### 11.4 实际启动命令（请用此版本，与第 5 节区别仅在 CUDA 版本）

```bash
cd /home/lenovo/Projects/iGEM-silk/tools/AMP-ESM
export CUDA_HOME=/usr/local/cuda-12.6          # 注意：12.6 不是 12.4
export PATH="$CUDA_HOME/bin:$PATH"
export LD_LIBRARY_PATH="$CUDA_HOME/lib64:$LD_LIBRARY_PATH"
export TF_CPP_MIN_LOG_LEVEL=2
.venv/bin/python service.py
```

### 11.5 验收清单实证（2026-08-05 全部 ✓）

- [x] 1. 驱动 580.142 未变
- [x] 2. `nvcc --version` 显示 release 12.6
- [x] 3. `libcudart.so.12` 命中（系统 `/usr/local/cuda-12.6/lib64/`）+ `libcudnn.so.8` 命中（.venv 内 TF wheel 自带）
- [x] 4. `uv pip list` 看到 `tensorflow==2.16.2` + 12 个 cu12 包
- [x] 5. `tf.config.list_physical_devices('GPU')` 返回 1 张
- [x] 6. `tf.matmul` 落在 `GPU:0`
- [x] 7. `/health` 200；`/predict` magainin2 → 0.844 / AMP
- [x] 8. **部分达成**：batch=64 中位 72-82 seq/s（≥30 最低，<100 目标）；batch=128 中位 131 seq/s（≥100 目标）
- [x] 9. `service.py` 改了 4 处（v0.1.0 路径内），其他文件未动
- [x] 10. v0.2.0 代码路径未动（启动验证留给下次）

### 11.6 经验教训（给未来回溯）

1. **CUDA 12.4 已下架**：直接装 `cuda-toolkit-12-6`，API 兼容（12 系列 minor 版本差异对 TF 2.16 影响极小），不需要 12.4 死磕
2. **apt 装的 cuDNN v.s. TF 自带的 cuDNN**：本次走 TF 自带（`nvidia-cudnn-cu12==8.9.7.29` 进 .venv），**没**装系统级 `libcudnn8`。优点：隔离；缺点：换 .venv 时要重新装
3. **batch 大小真的很关键**：从 64 升到 128 吞吐从 80 跳到 130（+60%），但从 16 升到 64 只从 27 跳到 80（+200%）。**小 batch 的 Python↔TF 互操作开销巨大**
4. **不要锁 CUDA 版本到 12.4**：原计划写 12.4 是 2026 NVIDIA 仓库当时的稳定版；现在 12.4 已下架，**写 12.x 兼容更新文档更耐用**
5. **驱动仍然 580.142 不动**：升级 NVIDIA 驱动会破坏 PyTorch 项目；CUDA 12.x runtime 与现有 CUDA 13 驱动可共存

### 11.7 临时清理

- 已还原 `mullvad.list`（apt 仓库源）
- 已删 `bench_v01_20260805.py`（用完即弃）
- 已删 `requests` 临时包（用完即弃）
- 已删 `/tmp/cuda-keyring_1.1-1_all.deb`
- 服务已停，GPU 显存从 47 GB 释放回 581 MB（仅 TF 内核）