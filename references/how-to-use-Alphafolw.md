好，我把完整的本地部署 + FastAPI 微服务方案一次讲清楚。

------

## 一、先理解硬件门槛

AlphaFlow 底层是 OpenFold（AlphaFold 的 PyTorch 复现），**强依赖 CUDA 11**，这是最大的坑。

| 需求   | 要求                                           |
| ------ | ---------------------------------------------- |
| GPU    | NVIDIA，显存建议 ≥ 16 GB（A100/V100/RTX3090+） |
| CUDA   | **必须 11.x**（不是 12.x，会编译失败）         |
| Python | **3.9**（不是 3.10/3.11）                      |
| 内存   | ≥ 32 GB RAM（MSA 处理很吃内存）                |

如果本地没有符合条件的 GPU，**强烈建议用 ESMFlow 版本**（同一个仓库提供），它不需要 MSA，速度更快，对你们的探索性预测够用。

------

## 二、选哪个模型权重

官方提供 6 类模型，结合你们项目需求：

| 模型                                 | 适用场景                           | 推荐度                 |
| ------------------------------------ | ---------------------------------- | ---------------------- |
| AlphaFlow-PDB distilled              | 无 MD 数据，快速预测实验构象多样性 | ⭐⭐⭐ 入门用             |
| **AlphaFlow-MD distilled**           | 模拟 300K 生理温度下的构象分布     | ⭐⭐⭐⭐ **推荐你们用**    |
| AlphaFlow-MD+Templates 12l-distilled | 有已知结构时用，快 2.5x            | ⭐⭐⭐⭐⭐ 有参考结构时最优 |
| ESMFlow-MD distilled                 | 无 GPU CUDA 11 / 快速验证          | ⭐⭐⭐ 备选               |

你们做的是融合蛋白在生理条件下的动态暴露性评估，选 **AlphaFlow-MD distilled** 最对口。

------

## 三、环境安装

```bash
# 1. 创建隔离环境（Python 3.9 强制）
conda create -n alphaflow python=3.9
conda activate alphaflow

# 2. 安装 CUDA 11（如果系统 CUDA 版本不对）
conda install nvidia/label/cuda-11.8.0::cuda
conda install nvidia/label/cuda-11.8.0::cuda-cudart-dev
conda install nvidia/label/cuda-11.8.0::libcusparse-dev
conda install nvidia/label/cuda-11.8.0::libcusolver-dev
conda install nvidia/label/cuda-11.8.0::libcublas-dev
ln -s $CONDA_PREFIX/lib/libcudart_static.a $CONDA_PREFIX/lib/libcudart.a

# 3. 安装依赖
pip install numpy==1.21.2 pandas==1.5.3
pip install torch==1.12.1+cu113 -f https://download.pytorch.org/whl/torch_stable.html
pip install biopython==1.79 dm-tree==0.1.6 modelcif==0.7 ml-collections==0.1.0 scipy==1.7.1 absl-py einops
pip install pytorch_lightning==2.0.4 fair-esm mdtraj==1.9.9 wandb

# 4. 安装 OpenFold（最耗时，需编译 CUDA kernel）
CUDA_HOME=$CONDA_PREFIX pip install 'openfold @ git+https://github.com/aqlaboratory/openfold.git@103d037'

# 5. 克隆 AlphaFlow
git clone https://github.com/bjing2016/alphaflow.git
cd alphaflow

# 6. 下载模型权重
mkdir weights
wget -P ./weights https://storage.googleapis.com/alphaflow/params/alphaflow_md_distilled_202402.pt
```

------

## 四、原始 CLI 用法（微服务封装的基础）

运行推理的原始命令是：

```bash
# 需要先有 MSA（用 ColabFold 服务器生成）
python -m scripts.mmseqs_query --split input.csv --outdir ./msa

# 运行预测
python predict.py \
  --mode alphafold \
  --input_csv input.csv \
  --msa_dir ./msa \
  --weights ./weights/alphaflow_md_distilled_202402.pt \
  --samples 50 \               # 生成构象数量
  --noisy_first --no_diffusion \ # distilled 模型必须加这两个参数
  --outpdb ./output_pdbs
```

输入 CSV 格式：

```csv
name,seqres
silk_fusion_A,MGAGAGRGGYGGLGSQGAGRGGLGGQGAGAAAAAAAAGGAGQGGYGGLGSQGAGRGGLGGQ
silk_fusion_B,MGAGAGRGGYGGLGSQGAGRGGLGGQGAGAAAAAAAAGGAGQGGYGGLGSQGAGRGGLGGQHHHKKK
```

------

## 五、FastAPI 微服务代码

整体架构是：HTTP 接收序列 → 写临时 CSV + MSA → 调用 predict.py → 返回 PDB zip 包。

```python
# alphaflow_service.py

import os, uuid, shutil, subprocess, zipfile
from pathlib import Path
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional

app = FastAPI(title="AlphaFlow Conformational Ensemble Service")

# ---- 配置 ----
WEIGHTS_PATH = "./weights/alphaflow_md_distilled_202402.pt"
ALPHAFLOW_DIR = "./alphaflow"          # git clone 的目录
WORK_DIR = Path("/tmp/alphaflow_jobs") # 每个 job 的临时目录
WORK_DIR.mkdir(exist_ok=True)

# ---- 请求/响应模型 ----
class PredictRequest(BaseModel):
    sequences: List[dict]   # [{"name": "silk_A", "seqres": "MGAGA..."}]
    n_samples: int = 50     # 生成构象数量，建议 20-100
    mode: str = "alphafold" # "alphafold" 或 "esmfold"

class JobStatus(BaseModel):
    job_id: str
    status: str             # pending / running / done / failed
    message: Optional[str] = None

# ---- 内存中记录 job 状态 ----
jobs: dict[str, dict] = {}

# ---- 主要逻辑 ----

def run_prediction(job_id: str, request: PredictRequest):
    job_dir = WORK_DIR / job_id
    jobs[job_id]["status"] = "running"
    
    try:
        # 1. 写 input CSV
        import pandas as pd
        df = pd.DataFrame(request.sequences)
        csv_path = job_dir / "input.csv"
        df.to_csv(csv_path, index=False)
        
        msa_dir = job_dir / "msa"
        out_dir = job_dir / "output_pdbs"
        out_dir.mkdir()
        
        # 2. 生成 MSA（AlphaFlow 模式才需要）
        if request.mode == "alphafold":
            msa_dir.mkdir()
            result = subprocess.run(
                ["python", "-m", "scripts.mmseqs_query",
                 "--split", str(csv_path),
                 "--outdir", str(msa_dir)],
                cwd=ALPHAFLOW_DIR,
                capture_output=True, text=True, timeout=3600
            )
            if result.returncode != 0:
                raise RuntimeError(f"MSA generation failed:\n{result.stderr}")
        
        # 3. 运行 AlphaFlow / ESMFlow 推理
        cmd = [
            "python", "predict.py",
            "--mode", request.mode,
            "--input_csv", str(csv_path),
            "--weights", WEIGHTS_PATH,
            "--samples", str(request.n_samples),
            "--noisy_first", "--no_diffusion",  # distilled 模型需要
            "--outpdb", str(out_dir)
        ]
        if request.mode == "alphafold":
            cmd += ["--msa_dir", str(msa_dir)]
        
        result = subprocess.run(
            cmd, cwd=ALPHAFLOW_DIR,
            capture_output=True, text=True, timeout=7200
        )
        if result.returncode != 0:
            raise RuntimeError(f"Prediction failed:\n{result.stderr}")
        
        # 4. 打包 PDB 输出
        zip_path = job_dir / "ensemble.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            for pdb_file in out_dir.glob("**/*.pdb"):
                zf.write(pdb_file, pdb_file.name)
        
        jobs[job_id]["status"] = "done"
        jobs[job_id]["zip_path"] = str(zip_path)
        
    except Exception as e:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["message"] = str(e)


# ---- API 端点 ----

@app.post("/predict", response_model=JobStatus)
async def submit_job(request: PredictRequest, background_tasks: BackgroundTasks):
    """提交构象预测任务，异步运行"""
    job_id = str(uuid.uuid4())[:8]
    job_dir = WORK_DIR / job_id
    job_dir.mkdir()
    
    jobs[job_id] = {"status": "pending", "zip_path": None, "message": None}
    background_tasks.add_task(run_prediction, job_id, request)
    
    return JobStatus(job_id=job_id, status="pending")


@app.get("/status/{job_id}", response_model=JobStatus)
async def get_status(job_id: str):
    """查询任务状态"""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    job = jobs[job_id]
    return JobStatus(job_id=job_id, status=job["status"], message=job.get("message"))


@app.get("/download/{job_id}")
async def download_results(job_id: str):
    """下载 PDB 构象集合 zip 包"""
    if job_id not in jobs or jobs[job_id]["status"] != "done":
        raise HTTPException(status_code=400, detail="Job not done or not found")
    zip_path = jobs[job_id]["zip_path"]
    return FileResponse(zip_path, media_type="application/zip",
                        filename=f"ensemble_{job_id}.zip")


@app.delete("/cleanup/{job_id}")
async def cleanup(job_id: str):
    """删除临时文件"""
    job_dir = WORK_DIR / job_id
    if job_dir.exists():
        shutil.rmtree(job_dir)
    jobs.pop(job_id, None)
    return {"message": "cleaned up"}


# ---- 启动 ----
# uvicorn alphaflow_service:app --host 0.0.0.0 --port 8001 --workers 1
```

------

## 六、使用示例

```python
import requests, time, zipfile, io

BASE = "http://localhost:8001"

# 提交任务
resp = requests.post(f"{BASE}/predict", json={
    "sequences": [
        {"name": "silk_GGX_insert",
         "seqres": "MGAGAGRGGYGGLGSQGAGRGGLGGQGAGAAAAAAAAGGAGQGGY"
                   "HHHKKK"          # 插入的功能肽
                   "GLGSQGAGRGGLGGQ"},
        {"name": "silk_CTD_insert",
         "seqres": "MGAGAGRGGYGGLGSQGAGRGGLGGQGAGAAAAAAAAGGAGQGGY"
                   "GLGSQGAGRGGLGGQ"
                   "HHHKKK"}         # 末端插入
    ],
    "n_samples": 50,
    "mode": "alphafold"
})
job_id = resp.json()["job_id"]
print(f"Job submitted: {job_id}")

# 轮询状态
while True:
    status = requests.get(f"{BASE}/status/{job_id}").json()
    print(f"Status: {status['status']}")
    if status["status"] in ("done", "failed"):
        break
    time.sleep(30)

# 下载并解压
if status["status"] == "done":
    r = requests.get(f"{BASE}/download/{job_id}")
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        z.extractall("./ensemble_results")
    print("PDB files saved to ./ensemble_results/")
```

------

## 七、关于你们项目的具体建议

有两个实际问题需要提前想好：

**1. ESMFlow 还是 AlphaFlow？**

如果 GPU 环境配置困难，先用 **ESMFlow-MD distilled**——它不需要 MSA 生成那步，把 `mode` 改成 `esmfold` 就行，速度快一倍，适合快速迭代筛选插入策略。等到 P0 筛出 2–3 个候选构建体之后，再用 AlphaFlow 做更精确的确认。

**2. 构象数量怎么选？**

对你们的用途（统计功能肽 SASA 分布）：

- 快速筛选阶段：`n_samples=20`，每条序列约 5–10 分钟
- 最终验证阶段：`n_samples=100`，统计结果更可靠

50 个构象就能算出有意义的暴露性分布，不需要跑 250 个。



你的这套方案，其实已经相当接近“可用的研究级基础设施”了，但如果目标是**长期稳定运行 + 支撑你们 peptide fusion screening pipeline 的高频调用**，现在这个版本还停留在「单机脚本服务化」，距离真正的 production-grade 还有几步关键跃迁。下面我不会重复你已经写得很好的部分，而是直接帮你做一层**架构级 refinement**，重点回答你前面那个核心问题：**微服务到底能不能解决连续大量调用？以及应该怎么进化这一套系统。**

------

# 一、先给你一个结论（不绕弯）

**FastAPI ≠ 能抗高并发**

你现在这个服务：

- ✔ 能异步提交任务（BackgroundTasks）
- ❌ 不能并发执行 GPU 任务
- ❌ 不能排队调度
- ❌ 不能资源隔离
- ❌ 不能横向扩展

因此：

> **微服务本身不能解决大量调用问题，真正解决问题的是「任务队列 + 调度系统 + GPU资源管理」。**

------

# 二、你当前架构的隐性瓶颈（非常关键）

我们用系统设计的视角，把你的 pipeline 拆一下：

```text
HTTP Request
   ↓
FastAPI
   ↓
subprocess.run()
   ↓
AlphaFlow (GPU)
```

这个结构的问题在于：**它是同步资源占用模型伪装成异步接口**，也就是说：

### 1. GPU 是硬瓶颈（不是 CPU）

- 一张 GPU 同时基本只能跑 **1 个 AlphaFlow 推理**
- 即使你开 `--workers 4`，也只是：
  - 4 个进程抢 1 张 GPU
  - 结果：OOM / crash / slowdown

👉 所以并发不是“能不能处理请求”，而是“GPU能不能排队”。

------

### 2. BackgroundTasks 是“假队列”

FastAPI 的 BackgroundTasks：

- 没有任务持久化（进程挂了就没了）
- 没有并发控制
- 没有优先级
- 没有 retry

👉 本质上只是：

> **“把阻塞代码放到另一个线程跑”**

------

### 3. MSA 是隐藏炸弹

AlphaFlow 模式：

```text
mmseqs_query → 网络请求 + CPU + 内存
```

问题：

- 很慢（分钟级）
- 很不稳定（网络依赖）
- 很吃 RAM

👉 如果并发上来，这一步会比 GPU 更先崩。

------

# 三、真正可扩展的架构（建议你直接升级）

你这个项目，其实已经进入一个很标准的模式：

> **AI推理服务（GPU-bound）+ 生物信息学预处理（CPU-bound）**

所以推荐结构如下：

------

## ✅ 推荐架构（Production Version）

```text
                ┌──────────────┐
                │   Client     │
                └──────┬───────┘
                       ↓
                ┌──────────────┐
                │   FastAPI    │  ← 只负责接请求
                └──────┬───────┘
                       ↓
                ┌──────────────┐
                │ Redis Queue  │  ← 核心：任务排队
                └──────┬───────┘
         ┌─────────────┼─────────────┐
         ↓                           ↓
┌────────────────┐        ┌────────────────┐
│ CPU Worker     │        │ GPU Worker     │
│ (MSA生成)      │        │ (AlphaFlow)    │
└────────────────┘        └────────────────┘
         ↓                           ↓
                ┌──────────────┐
                │  Storage     │ (PDB / zip)
                └──────────────┘
```

------

## 🔧 技术选型建议（务实版）

| 组件     | 推荐                      |
| -------- | ------------------------- |
| API 层   | FastAPI（你已经有了）     |
| 队列     | **Redis + Celery / RQ**   |
| GPU 调度 | 单机：队列控制；多机：K8s |
| 存储     | 本地 / S3 / MinIO         |
| 状态     | Redis / PostgreSQL        |

------

# 四、关键升级点（逐条说透）

## 1️⃣ 引入任务队列（这是质变）

把你现在的：

```python
background_tasks.add_task(run_prediction, ...)
```

替换成：

```python
celery_task.delay(...)
```

这一步带来的变化是：

| 能力     | 变化              |
| -------- | ----------------- |
| 并发控制 | ✅ 限制 GPU 任务数 |
| 排队     | ✅ 自动排队        |
| 崩溃恢复 | ✅                 |
| retry    | ✅                 |
| 分布式   | ✅                 |

------

## 2️⃣ GPU Worker 必须“单线程”

这是很多人会踩的坑：

```bash
# 错误
--workers 4

# 正确
--workers 1
```

然后用：

```text
多个 GPU Worker = 多张 GPU
```

👉 核心原则：

> **一张 GPU = 一个 worker 进程**

------

## 3️⃣ CPU / GPU 分离（非常关键）

你现在是：

```text
MSA + 推理 → 同一个进程
```

应该拆成：

```text
Task A: MSA (CPU)
Task B: AlphaFlow (GPU)
```

这样：

- CPU 可以并发跑很多
- GPU 不被阻塞

------

## 4️⃣ ESMFlow 是“吞吐量神器”

你已经提到这一点，但我帮你明确战略意义：

| 模式        | 特点           |
| ----------- | -------------- |
| AlphaFlow   | 准确，但慢     |
| **ESMFlow** | 快，不需要 MSA |

👉 推荐 pipeline：

```text
Stage 1: ESMFlow（筛选 1000 条 → 20 条）
Stage 2: AlphaFlow（精算 20 条 → 3 条）
```

这会直接把你的计算成本降一个数量级。

------

# 五、能不能扛“连续大量调用”？（严肃回答）

### ❌ 现在这个版本：不能

当 QPS > 1：

- GPU 阻塞
- 内存爆
- 任务丢失

------

### ✅ 升级后：可以“线性扩展”

吞吐量模型：

```text
总吞吐 ≈ GPU数量 / 单任务耗时
```

举例：

| GPU      | 单任务时间 | 吞吐          |
| -------- | ---------- | ------------- |
| 1 × 3090 | 10 min     | 6 tasks/hour  |
| 4 × 3090 | 10 min     | 24 tasks/hour |

👉 这就是为什么：

> **扩展靠加 GPU，不是加 FastAPI worker**

------

# 六、给你一个“工程级建议”（很关键）

你现在这个系统，其实已经可以升级成：

> **Peptide Design Compute Backend（内部算力平台）**

建议你加三层抽象：

------

## Layer 1：API（你已有）

```text
/predict
/status
/download
```

------

## Layer 2：任务系统

```text
task_type:
  - msa
  - esmfold
  - alphaflow
```

------

## Layer 3：Pipeline（核心价值）

```text
pipeline:
  - fast_screening
  - final_validation
```

------

这样你以后可以直接：

```python
POST /run_pipeline
{
  "type": "fast_screening",
  "sequences": [...]
}
```

而不是手动拼流程。

------

# 七、我给你的“最小升级路径”（不折腾版）

如果你不想一下子上 K8s，最务实方案是：

### Step 1（必须做）

- 引入 **Redis + RQ**
- 把 BackgroundTasks 替换掉

------

### Step 2（强烈建议）

- 拆 MSA 和推理
- GPU worker 限制 = 1

------

### Step 3（效果爆炸）

- 加 ESMFlow 路径
- 做两阶段筛选

------

# 最后一句（很重要）

你现在已经不只是“在跑一个模型”，而是在**设计一个计算平台的雏形**；如果你把“并发问题”理解为 web 层问题，那永远会卡住，但一旦你切换到“GPU 是核心资源，需要调度”的视角，整个系统设计就会一下子变得清晰而且可扩展。

------

如果你愿意，我可以下一步帮你把：

- **Celery + Redis + GPU worker 的完整代码模板**
- 或者 **一个可直接部署的 docker-compose 架构**

直接给你补齐到可以上线的程度。



