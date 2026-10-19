> English translation of [how-to-use-Alphafolw.md](how-to-use-Alphafolw.md). The Chinese original is kept unchanged as the source of truth.

OK, let me explain the complete local deployment + FastAPI microservice plan in one go.

------

## 1. First, Understand the Hardware Bar

AlphaFlow is built on OpenFold (a PyTorch reimplementation of AlphaFold) and **depends heavily on CUDA 11**; this is the biggest pitfall.

| Requirement | Spec                                           |
| ------ | ---------------------------------------------- |
| GPU    | NVIDIA, ≥ 16 GB GPU memory recommended (A100/V100/RTX3090+) |
| CUDA   | **Must be 11.x** (not 12.x — compilation will fail) |
| Python | **3.9** (not 3.10/3.11)                        |
| Memory | ≥ 32 GB RAM (MSA processing is very memory hungry) |

If there is no qualifying GPU locally, **using the ESMFlow version is strongly recommended** (provided in the same repository); it does not need MSA, it is faster, and it is good enough for your exploratory predictions.

------

## 2. Which Model Weights to Choose

The official release provides 6 model categories; given your project's needs:

| Model                                 | Use case                           | Recommendation                 |
| ------------------------------------ | ---------------------------------- | ---------------------- |
| AlphaFlow-PDB distilled              | No MD data; quickly predict experimental conformational diversity | ⭐⭐⭐ for getting started             |
| **AlphaFlow-MD distilled**           | Simulate the conformational distribution at physiological temperature, 300K | ⭐⭐⭐⭐ **recommended for you**    |
| AlphaFlow-MD+Templates 12l-distilled | Use when a known structure exists; 2.5x faster | ⭐⭐⭐⭐⭐ best when a reference structure exists |
| ESMFlow-MD distilled                 | No GPU with CUDA 11 / quick validation | ⭐⭐⭐ alternative               |

What you are doing is assessing the dynamic exposure of fusion proteins under physiological conditions, so **AlphaFlow-MD distilled** is the best fit.

------

## 3. Environment Setup

```bash
# 1. Create an isolated environment (Python 3.9 is mandatory)
conda create -n alphaflow python=3.9
conda activate alphaflow

# 2. Install CUDA 11 (if the system CUDA version is wrong)
conda install nvidia/label/cuda-11.8.0::cuda
conda install nvidia/label/cuda-11.8.0::cuda-cudart-dev
conda install nvidia/label/cuda-11.8.0::libcusparse-dev
conda install nvidia/label/cuda-11.8.0::libcusolver-dev
conda install nvidia/label/cuda-11.8.0::libcublas-dev
ln -s $CONDA_PREFIX/lib/libcudart_static.a $CONDA_PREFIX/lib/libcudart.a

# 3. Install dependencies
pip install numpy==1.21.2 pandas==1.5.3
pip install torch==1.12.1+cu113 -f https://download.pytorch.org/whl/torch_stable.html
pip install biopython==1.79 dm-tree==0.1.6 modelcif==0.7 ml-collections==0.1.0 scipy==1.7.1 absl-py einops
pip install pytorch_lightning==2.0.4 fair-esm mdtraj==1.9.9 wandb

# 4. Install OpenFold (the most time-consuming step; compiles CUDA kernels)
CUDA_HOME=$CONDA_PREFIX pip install 'openfold @ git+https://github.com/aqlaboratory/openfold.git@103d037'

# 5. Clone AlphaFlow
git clone https://github.com/bjing2016/alphaflow.git
cd alphaflow

# 6. Download the model weights
mkdir weights
wget -P ./weights https://storage.googleapis.com/alphaflow/params/alphaflow_md_distilled_202402.pt
```

------

## 4. Original CLI Usage (the Basis for the Microservice Wrapper)

The original command to run inference is:

```bash
# You need an MSA first (generate it with the ColabFold server)
python -m scripts.mmseqs_query --split input.csv --outdir ./msa

# Run prediction
python predict.py \
  --mode alphafold \
  --input_csv input.csv \
  --msa_dir ./msa \
  --weights ./weights/alphaflow_md_distilled_202402.pt \
  --samples 50 \               # number of conformations to generate
  --noisy_first --no_diffusion \ # these two flags are required for distilled models
  --outpdb ./output_pdbs
```

Input CSV format:

```csv
name,seqres
silk_fusion_A,MGAGAGRGGYGGLGSQGAGRGGLGGQGAGAAAAAAAAGGAGQGGYGGLGSQGAGRGGLGGQ
silk_fusion_B,MGAGAGRGGYGGLGSQGAGRGGLGGQGAGAAAAAAAAGGAGQGGYGGLGSQGAGRGGLGGQHHHKKK
```

------

## 5. FastAPI Microservice Code

The overall architecture is: receive sequences over HTTP → write a temporary CSV + MSA → call predict.py → return a zip package of PDBs.

```python
# alphaflow_service.py

import os, uuid, shutil, subprocess, zipfile
from pathlib import Path
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional

app = FastAPI(title="AlphaFlow Conformational Ensemble Service")

# ---- Configuration ----
WEIGHTS_PATH = "./weights/alphaflow_md_distilled_202402.pt"
ALPHAFLOW_DIR = "./alphaflow"          # the git clone directory
WORK_DIR = Path("/tmp/alphaflow_jobs") # temporary directory for each job
WORK_DIR.mkdir(exist_ok=True)

# ---- Request/response models ----
class PredictRequest(BaseModel):
    sequences: List[dict]   # [{"name": "silk_A", "seqres": "MGAGA..."}]
    n_samples: int = 50     # number of conformations to generate; 20-100 recommended
    mode: str = "alphafold" # "alphafold" or "esmfold"

class JobStatus(BaseModel):
    job_id: str
    status: str             # pending / running / done / failed
    message: Optional[str] = None

# ---- In-memory job status ----
jobs: dict[str, dict] = {}

# ---- Main logic ----

def run_prediction(job_id: str, request: PredictRequest):
    job_dir = WORK_DIR / job_id
    jobs[job_id]["status"] = "running"
    
    try:
        # 1. Write the input CSV
        import pandas as pd
        df = pd.DataFrame(request.sequences)
        csv_path = job_dir / "input.csv"
        df.to_csv(csv_path, index=False)
        
        msa_dir = job_dir / "msa"
        out_dir = job_dir / "output_pdbs"
        out_dir.mkdir()
        
        # 2. Generate the MSA (only needed in AlphaFlow mode)
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
        
        # 3. Run AlphaFlow / ESMFlow inference
        cmd = [
            "python", "predict.py",
            "--mode", request.mode,
            "--input_csv", str(csv_path),
            "--weights", WEIGHTS_PATH,
            "--samples", str(request.n_samples),
            "--noisy_first", "--no_diffusion",  # required for distilled models
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
        
        # 4. Package the PDB outputs
        zip_path = job_dir / "ensemble.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            for pdb_file in out_dir.glob("**/*.pdb"):
                zf.write(pdb_file, pdb_file.name)
        
        jobs[job_id]["status"] = "done"
        jobs[job_id]["zip_path"] = str(zip_path)
        
    except Exception as e:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["message"] = str(e)


# ---- API endpoints ----

@app.post("/predict", response_model=JobStatus)
async def submit_job(request: PredictRequest, background_tasks: BackgroundTasks):
    """Submit a conformation prediction job; runs asynchronously"""
    job_id = str(uuid.uuid4())[:8]
    job_dir = WORK_DIR / job_id
    job_dir.mkdir()
    
    jobs[job_id] = {"status": "pending", "zip_path": None, "message": None}
    background_tasks.add_task(run_prediction, job_id, request)
    
    return JobStatus(job_id=job_id, status="pending")


@app.get("/status/{job_id}", response_model=JobStatus)
async def get_status(job_id: str):
    """Query the job status"""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    job = jobs[job_id]
    return JobStatus(job_id=job_id, status=job["status"], message=job.get("message"))


@app.get("/download/{job_id}")
async def download_results(job_id: str):
    """Download the zip package of the PDB conformational ensemble"""
    if job_id not in jobs or jobs[job_id]["status"] != "done":
        raise HTTPException(status_code=400, detail="Job not done or not found")
    zip_path = jobs[job_id]["zip_path"]
    return FileResponse(zip_path, media_type="application/zip",
                        filename=f"ensemble_{job_id}.zip")


@app.delete("/cleanup/{job_id}")
async def cleanup(job_id: str):
    """Delete temporary files"""
    job_dir = WORK_DIR / job_id
    if job_dir.exists():
        shutil.rmtree(job_dir)
    jobs.pop(job_id, None)
    return {"message": "cleaned up"}


# ---- Startup ----
# uvicorn alphaflow_service:app --host 0.0.0.0 --port 8001 --workers 1
```

------

## 6. Usage Example

```python
import requests, time, zipfile, io

BASE = "http://localhost:8001"

# Submit the job
resp = requests.post(f"{BASE}/predict", json={
    "sequences": [
        {"name": "silk_GGX_insert",
         "seqres": "MGAGAGRGGYGGLGSQGAGRGGLGGQGAGAAAAAAAAGGAGQGGY"
                   "HHHKKK"          # inserted functional peptide
                   "GLGSQGAGRGGLGGQ"},
        {"name": "silk_CTD_insert",
         "seqres": "MGAGAGRGGYGGLGSQGAGRGGLGGQGAGAAAAAAAAGGAGQGGY"
                   "GLGSQGAGRGGLGGQ"
                   "HHHKKK"}         # terminal insertion
    ],
    "n_samples": 50,
    "mode": "alphafold"
})
job_id = resp.json()["job_id"]
print(f"Job submitted: {job_id}")

# Poll the status
while True:
    status = requests.get(f"{BASE}/status/{job_id}").json()
    print(f"Status: {status['status']}")
    if status["status"] in ("done", "failed"):
        break
    time.sleep(30)

# Download and extract
if status["status"] == "done":
    r = requests.get(f"{BASE}/download/{job_id}")
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        z.extractall("./ensemble_results")
    print("PDB files saved to ./ensemble_results/")
```

------

## 7. Specific Advice for Your Project

There are two practical questions you need to think through in advance:

**1. ESMFlow or AlphaFlow?**

If configuring the GPU environment is difficult, start with **ESMFlow-MD distilled** — it does not need the MSA generation step; just change `mode` to `esmfold`, and it is twice as fast, which suits rapid iteration over insertion strategies. Once P0 has narrowed things down to 2–3 candidate constructs, use AlphaFlow for a more precise confirmation.

**2. How many conformations should you choose?**

For your use case (computing the distribution of functional peptide SASA):

- Rapid screening stage: `n_samples=20`, about 5–10 minutes per sequence
- Final validation stage: `n_samples=100`, more reliable statistics

50 conformations are enough to compute a meaningful exposure distribution; you don't need to run 250.



Your plan is actually already quite close to "usable research-grade infrastructure", but if the goal is **long-term stable operation + supporting high-frequency calls from your peptide fusion screening pipeline**, this version is still at the "service-ify a single-machine script" stage, and there are still a few key leaps before it is truly production-grade. Below I won't repeat the parts you already wrote well; instead I'll directly do an **architecture-level refinement** for you, focusing on the core question you raised earlier: **can a microservice actually handle continuous, high-volume calls? And how should this system evolve?**

------

# 1. A Conclusion Up Front (No Beating Around the Bush)

**FastAPI ≠ able to withstand high concurrency**

Your current service:

- ✔ can submit jobs asynchronously (BackgroundTasks)
- ❌ cannot execute GPU jobs concurrently
- ❌ cannot queue or schedule
- ❌ cannot isolate resources
- ❌ cannot scale horizontally

Therefore:

> **A microservice by itself cannot solve the high-volume call problem; what actually solves it is "task queue + scheduling system + GPU resource management".**

------

# 2. The Hidden Bottlenecks in Your Current Architecture (Highly Important)

Let's break down your pipeline from a system-design perspective:

```text
HTTP Request
   ↓
FastAPI
   ↓
subprocess.run()
   ↓
AlphaFlow (GPU)
```

The problem with this structure is: **it is a synchronous resource-occupancy model disguised as an asynchronous interface**, that is:

### 1. GPU Is the Hard Bottleneck (Not CPU)

- One GPU can basically run only **1 AlphaFlow inference** at a time
- Even if you set `--workers 4`, you only get:
  - 4 processes fighting over 1 GPU
  - Result: OOM / crash / slowdown

👉 So concurrency is not about "can you handle requests" but about "can the GPU queue them".

------

### 2. BackgroundTasks Is a "Fake Queue"

FastAPI's BackgroundTasks:

- no task persistence (gone if the process dies)
- no concurrency control
- no priority
- no retry

👉 In essence it is just:

> **"running blocking code in another thread"**

------

### 3. MSA Is a Hidden Bomb

AlphaFlow mode:

```text
mmseqs_query → network requests + CPU + memory
```

Problems:

- very slow (minutes)
- very unstable (depends on the network)
- very RAM hungry

👉 Once concurrency rises, this step will collapse before the GPU does.

------

# 3. A Truly Scalable Architecture (I Suggest You Upgrade to It Directly)

Your project has actually already entered a very standard pattern:

> **AI inference service (GPU-bound) + bioinformatics preprocessing (CPU-bound)**

So the recommended structure is:

------

## ✅ Recommended Architecture (Production Version)

```text
                ┌──────────────┐
                │   Client     │
                └──────┬───────┘
                       ↓
                ┌──────────────┐
                │   FastAPI    │  ← only handles incoming requests
                └──────┬───────┘
                       ↓
                ┌──────────────┐
                │ Redis Queue  │  ← core: task queuing
                └──────┬───────┘
         ┌─────────────┼─────────────┐
         ↓                           ↓
┌──────────────────┐        ┌────────────────┐
│ CPU Worker       │        │ GPU Worker     │
│ (MSA generation) │        │ (AlphaFlow)    │
└──────────────────┘        └────────────────┘
         ↓                           ↓
                ┌──────────────┐
                │  Storage     │ (PDB / zip)
                └──────────────┘
```

------

## 🔧 Technology Choices (Pragmatic Version)

| Component     | Recommendation                      |
| -------- | ------------------------- |
| API layer   | FastAPI (you already have it)     |
| Queue     | **Redis + Celery / RQ**   |
| GPU scheduling | Single machine: queue-based control; multiple machines: K8s |
| Storage     | Local / S3 / MinIO         |
| State     | Redis / PostgreSQL        |

------

# 4. Key Upgrade Points (Explained One by One)

## 1️⃣ Introduce a Task Queue (This Is the Game Changer)

Replace your current:

```python
background_tasks.add_task(run_prediction, ...)
```

with:

```python
celery_task.delay(...)
```

What this step changes:

| Capability     | Change              |
| -------- | ----------------- |
| Concurrency control | ✅ limits the number of GPU jobs |
| Queuing     | ✅ automatic queuing        |
| Crash recovery | ✅                 |
| retry    | ✅                 |
| Distribution   | ✅                 |

------

## 2️⃣ GPU Workers Must Be "Single-Threaded"

This is a pit many people fall into:

```bash
# wrong
--workers 4

# right
--workers 1
```

Then use:

```text
multiple GPU workers = multiple GPUs
```

👉 Core principle:

> **one GPU = one worker process**

------

## 3️⃣ Separate CPU and GPU (Highly Important)

Currently you have:

```text
MSA + inference → same process
```

It should be split into:

```text
Task A: MSA (CPU)
Task B: AlphaFlow (GPU)
```

This way:

- the CPU can run many tasks concurrently
- the GPU is not blocked

------

## 4️⃣ ESMFlow Is a "Throughput Beast"

You already mentioned this, but let me make the strategic significance explicit:

| Mode        | Characteristics           |
| ----------- | -------------- |
| AlphaFlow   | Accurate, but slow     |
| **ESMFlow** | Fast, no MSA needed |

👉 Recommended pipeline:

```text
Stage 1: ESMFlow (screen 1000 → 20)
Stage 2: AlphaFlow (precise scoring 20 → 3)
```

This directly cuts your compute cost by an order of magnitude.

------

# 5. Can It Handle "Continuous High-Volume Calls"? (A Serious Answer)

### ❌ The Current Version: No

When QPS > 1:

- GPU blocking
- memory blow-up
- lost jobs

------

### ✅ After the Upgrade: Yes, It Can "Scale Linearly"

Throughput model:

```text
total throughput ≈ number of GPUs / time per task
```

For example:

| GPU      | Time per task | Throughput          |
| -------- | ---------- | ------------- |
| 1 × 3090 | 10 min     | 6 tasks/hour  |
| 4 × 3090 | 10 min     | 24 tasks/hour |

👉 That is why:

> **scaling means adding GPUs, not adding FastAPI workers**

------

# 6. An "Engineering-Grade Recommendation" (Highly Important)

Your current system can actually be upgraded into:

> **Peptide Design Compute Backend (an internal compute platform)**

I suggest adding three layers of abstraction:

------

## Layer 1: API (you already have it)

```text
/predict
/status
/download
```

------

## Layer 2: Task System

```text
task_type:
  - msa
  - esmfold
  - alphaflow
```

------

## Layer 3: Pipeline (the core value)

```text
pipeline:
  - fast_screening
  - final_validation
```

------

Then later you can directly do:

```python
POST /run_pipeline
{
  "type": "fast_screening",
  "sequences": [...]
}
```

instead of manually stitching the workflow together.

------

# 7. The "Minimal Upgrade Path" I Recommend (No-Fuss Version)

If you don't want to jump to K8s all at once, the most pragmatic plan is:

### Step 1 (must do)

- Introduce **Redis + RQ**
- Replace BackgroundTasks

------

### Step 2 (strongly recommended)

- Split MSA and inference
- GPU worker limit = 1

------

### Step 3 (explosive effect)

- Add the ESMFlow path
- Implement two-stage screening

------

# A Final Word (Very Important)

You are no longer just "running a model"; you are **designing the prototype of a compute platform**. If you understand the "concurrency problem" as a web-layer problem, you will be stuck forever; but once you switch to the view that "the GPU is the core resource and needs scheduling", the entire system design suddenly becomes clear and scalable.

------

If you like, as a next step I can help you with:

- **a complete code template for Celery + Redis + GPU worker**
- or **a directly deployable docker-compose architecture**

and fill it in to the point where it can go live.



This concern is very real, and it is basically the first psychological hurdle for everyone moving from "research scripts" to "Docker engineering": **you feel that local development has been taken hostage by containerization — debugging gets slower, feedback gets heavier, and you lose flexibility.**

But the reality is exactly the opposite — if designed correctly, Docker not only won't slow you down; it will make **development, debugging, and deployment consistent and let you converge on problems faster**. The key is that your understanding of Docker is still stuck in the "full rebuild and run" mode rather than a "layered development mode".

Let me break it down for you.

------

# 1. Your Current Misconception: Treating Docker as a "Virtual Machine"

Your current concern is essentially:

> every code change → rebuild image → restart container → re-run the GPU pipeline

If you really used it that way, the conclusion is:

> ❌ it would indeed be slow, and quite user-hostile

But that is **incorrect usage**, not the way Docker is designed.

------

# 2. Understanding Docker's Development Model Correctly: A Three-Layer Split

In engineering, Docker is usually used at three layers:

```text
① Base image (CUDA / Python / system libs)
② Dependency layer (pip/uv install)
③ Code layer (the FastAPI / AlphaFlow wrapper you write)
```

The key point is:

> **during development, only touch layer 3; do not rebuild layers 1-2**

------

# 3. The Correct Local Development Approach: Volume Mount (the Core Mechanism)

What you should really use is this:

```bash
docker run \
  --gpus all \
  -v $(pwd):/app \
  -w /app \
  -p 8001:8001 \
  alphaflow-image \
  uvicorn service:app --reload
```

------

## 🔥 What This Mode Means

### ✔ Code Is "Live-Mapped"

You edit:

```python
service.py
```

It takes effect in the container immediately; no rebuild needed.

------

### ✔ Docker Only Handles the "Environment"

CUDA / torch / openfold:

- unchanged
- not reinstalled
- not recompiled

------

### ✔ You Are Debugging the "Runtime State", Not the "Build State"

This is the key difference.

------

# 4. The "Slowness" You Worry About Actually Comes from These Three Misuses

## ❌ Misuse 1: Rebuilding the Image Every Time

```bash
docker build .
docker run ...
```

👉 This is for production deployment, not development

------

## ❌ Misuse 2: COPYing Code into the Image

```dockerfile
COPY . /app
```

👉 This forces a rebuild on every code change

------

## ❌ Misuse 3: No Volume Mount

Without:

```bash
-v $(pwd):/app
```

👉 development loses its point

------

# 5. The Correct Development Flow (This Is How You Should Use It)

## 🧠 Standard Workflow (Industry-Grade)

### Step 1: First Build (Slow, but Only Once)

```bash
docker build -t alphaflow .
```

------

### Step 2: Development Phase (Fast)

```bash
docker run \
  --gpus all \
  -v $(pwd):/app \
  -w /app \
  -p 8001:8001 \
  alphaflow \
  uvicorn service:app --reload
```

------

### Step 3: You Modify the Code

You only need to:

- save the Python file
- let FastAPI auto-reload

👉 **no need to restart Docker**

------

# 6. Performance Comparison (The Real Situation)

| Operation     | Local conda | Docker development mode |
| -------- | --------- | -------------- |
| Code change   | Instant      | Instant           |
| Dependency change   | May reinstall  | uv sync        |
| CUDA environment | Easy to break    | Stable           |
| Startup speed | Fast        | 1-3 second difference     |
| GPU runs  | Unstable    | Stable           |

👉 Conclusion:

> What is slow is not Docker development, but the "incorrect usage pattern"

------

# 7. A Key Mindset Shift (Very Important)

Your current thinking is:

> "I want to debug Python locally"

But the correct mindset Docker brings is:

> **"I am debugging a system that is fully consistent with production"**

This brings a very important benefit:

------

## ✔ You Will No Longer Run Into:

- works locally, blows up on the server
- CUDA mismatch
- torch ABI crash
- openfold compilation problems

------

# 8. So How Do uv and Docker Work Together Most Comfortably?

Your ideal combination is actually:

```text
Docker = environment + GPU + system libs
uv     = Python dependency manager
```

The development flow becomes:

```bash
# change Python dependencies
uv add fastapi

# change code
vim service.py

# no need to rebuild the container
```

------

# 9. When Do You Actually Need to Rebuild Docker?

Only three cases:

## 1️⃣ CUDA / system dependencies changed

```bash
apt-get install xxx
```

------

## 2️⃣ Changes in the torch / openfold compilation layer

------

## 3️⃣ You upgrade the base image

```dockerfile
FROM nvidia/cuda:12.x
```

------

👉 No other case needs a rebuild

------

# 10. The Conclusion for You (Very Clear)

The thing you worry about most can be summed up in one sentence:

> ❗ Whether Docker is slow depends on whether you treat it as a "build tool" rather than a "runtime environment"

------

# 11. If You Want to Optimize Further (A Good Fit for Your Project)

Your AlphaFlow + peptide screening system can actually be upgraded one more step:

## 🚀 Recommended Next Steps:

- docker + hot reload
- containerize the GPU worker
- Redis task queue
- multi-container parallel inference

In the end it becomes:

> **a local cloud-computing system resembling "AlphaFold-as-a-Service"**

------

If you like, as a next step I can design directly for you:

### 👉 "The Complete Docker + uv + GPU + FastAPI Development Template Best Suited to Your Project"

Including:

- Dockerfile (CUDA optimized)
- docker-compose (with Redis + worker)
- uv integration best practice
- a scheme for controlling a single GPU worker
- a local debug / production-consistent architecture

Once this is done, you are basically at the level of "being able to provide compute services externally".

