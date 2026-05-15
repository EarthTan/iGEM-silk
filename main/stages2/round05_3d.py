"""
Round 5：3D 结构预测 — ESMFold + OmegaFold

对 Round 4 的 90 个 construct 同时运行 ESMFold 和 OmegaFold，
每个 construct 一个独立文件夹：

    constructs/con_XXXX/
    ├── con_XXXX_esmfold.pdb       ← ESMFold PDB
    ├── con_XXXX_omegafold.pdb     ← OmegaFold PDB
    ├── metadata.json               ← 原始数据库信息 + construct 详情
    └── scores.json                 ← 全流水线评分 + pLDDT

用法：
    1. 启动结构预测服务（当前终端）：
       cd tools/ESMFold   && nohup .venv/bin/python service.py --port 8203 &
       cd tools/OmegaFold && nohup .venv/bin/python service.py --port 8204 &

    2. 运行本脚本：
       uv run python -m main.stages2.round05_3d

输入：
    output/round04_enumerate/final/round5_input.json   ← 90 个 construct
    output/round04_enumerate/final/top90.fasta          ← 序列
    output/round03_heavy/final/all_scored.csv           ← 7 服务评分
    data/function_2.csv                                 ← 原始数据库元数据

输出：
    output/round05_3d/
    ├── constructs/con_XXXX/   ← 90 个独立文件夹
    ├── final/                 ← 汇总
    ├── checkpoint.json        ← 崩溃恢复
    ├── README.md
    └── run.log
"""

from __future__ import annotations

import asyncio
import csv
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

OUTPUT_DIR = PROJECT_ROOT / "output"
STAGE = "round05_3d"
STAGE_DIR = OUTPUT_DIR / STAGE
CONSTRUCTS_DIR = STAGE_DIR / "constructs"
FINAL_DIR = STAGE_DIR / "final"
PDB_DIR = STAGE_DIR / "pdb"  # flat copy for easy access

from main.client import ServiceClient
from main.config import service_url

LOG_FILE: Path | None = None

# ── 并发控制 ──
CONCURRENCY = 2                # 同时处理几个 construct（每个 construct 并发 ESMFold+OmegaFold）
ESMFOLD_TIMEOUT = 7200         # ESMFold 单任务超时（2h）
OMEGAFOLD_TIMEOUT = 14400      # OmegaFold 单任务超时（4h）
OMEGAFOLD_CONCURRENCY = 1      # OmegaFold 全局并发数（服务端会阻塞事件循环，不能并发）
POLL_INTERVAL = 30.0           # 轮询间隔
CHECKPOINT_INTERVAL = 3        # 每 N 个 construct 保存一次检查点
SERVICE_START_TIMEOUT = 120    # 等待服务启动（秒）
HEALTH_CHECK_INTERVAL = 5      # 健康检查间隔（秒）

# ── 服务端口 ──
ESMFOLD_PORT = 8203
OMEGAFOLD_PORT = 8204

# ── 要停掉的 GPU 服务（释放显存） ──
GPU_SERVICES_TO_STOP = {
    "bepipred3":  {"port": 8002, "group": "score"},
    "temstapro":  {"port": 8010, "group": "score"},
}

# 其他非 GPU 服务也可以停掉，但不是必需的
OTHER_SERVICES_TO_STOP = {
    "anoxpepred":  {"port": 8001, "group": "score"},
    "toxinpred3":  {"port": 8003, "group": "filter"},
    "hemopi2":     {"port": 8004, "group": "filter"},
    "mhcflurry":   {"port": 8005, "group": "score"},
    "plm4cpps":    {"port": 8006, "group": "score"},
    "tipred":      {"port": 8007, "group": "score"},
    "algpred2":    {"port": 8008, "group": "filter"},
    "graphcpp":    {"port": 8009, "group": "score"},
    "sodope":      {"port": 8012, "group": "score"},
}


# ═══════════════════════════════════════════════════════════════════════
# 日志
# ═══════════════════════════════════════════════════════════════════════

def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    if LOG_FILE:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")


# ═══════════════════════════════════════════════════════════════════════
# 服务管理
# ═══════════════════════════════════════════════════════════════════════

def find_processes_by_port(port: int) -> list[int]:
    """通过端口查找进程 PID（ss 或 lsof）"""
    pids = set()
    try:
        result = subprocess.run(
            ["ss", "-tlnp", f"sport = :{port}"],
            capture_output=True, text=True, timeout=10
        )
        for line in result.stdout.splitlines():
            if "pid=" in line:
                for part in line.split(","):
                    part = part.strip()
                    if part.startswith("pid="):
                        try:
                            pids.add(int(part[4:].split("/")[0]))
                        except ValueError:
                            pass
    except Exception:
        pass
    return list(pids)


def find_service_processes() -> list[int]:
    """找到所有本地运行的微服务进程"""
    pids = []
    try:
        result = subprocess.run(
            ["ps", "aux"],
            capture_output=True, text=True, timeout=10
        )
        for line in result.stdout.splitlines():
            if "service.py" in line and ".venv" in line:
                parts = line.split()
                if parts:
                    pids.append(int(parts[1]))
    except Exception:
        pass
    return pids


def kill_processes(port_infos: dict):
    """通过端口或进程名停掉服务"""
    killed = []
    for name, info in port_infos.items():
        pids = find_processes_by_port(info["port"])
        for pid in pids:
            try:
                os.kill(pid, signal.SIGTERM)
                killed.append(f"{name}(PID {pid})")
                log(f"  停用 {name} (PID {pid})")
            except ProcessLookupError:
                pass
            except Exception as e:
                log(f"  ⚠ 停用 {name} 失败: {e}")
    return killed


def stop_other_services():
    """停掉非结构预测服务，释放 GPU 显存

    注意：跳过结构预测服务端口（8203 ESMFold, 8204 OmegaFold）
    """
    STRUCTURE_PORTS = {8203, 8204}
    log("\n🧹 停用非必需服务，释放显存...")

    # 只停非结构预测端口的服务
    for name, info in {**GPU_SERVICES_TO_STOP, **OTHER_SERVICES_TO_STOP}.items():
        port = info["port"]
        if port in STRUCTURE_PORTS:
            continue
        pids = find_processes_by_port(port)
        for pid in pids:
            try:
                os.kill(pid, signal.SIGTERM)
                log(f"  停用 {name}(PID {pid}) port {port}")
            except ProcessLookupError:
                pass
            except Exception as e:
                log(f"  ⚠ 停用 {name} 失败: {e}")

    log("  停用完成")
    log("  等待 5 秒让 GPU 显存释放...")
    time.sleep(5)


async def wait_for_service(url: str, name: str, timeout: float = SERVICE_START_TIMEOUT) -> bool:
    """等待服务健康"""
    import httpx
    t0 = time.time()
    async with httpx.AsyncClient(timeout=10.0) as client:
        while time.time() - t0 < timeout:
            try:
                resp = await client.get(f"{url}/health")
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("model_loaded"):
                        log(f"  {name} ✅ 已就绪")
                        return True
                    else:
                        log(f"  {name} ⏳ 模型加载中...")
                else:
                    log(f"  {name} ⏳ 状态={resp.status_code}")
            except Exception:
                pass
            await asyncio.sleep(HEALTH_CHECK_INTERVAL)
    log(f"  {name} ❌ 超时 {timeout}s")
    return False


async def ensure_structure_services() -> bool:
    """确保 ESMFold 和 OmegaFold 都在运行"""
    log("\n🔍 检查结构预测服务...")

    esmfold_url = service_url("esmfold")
    omegafold_url = service_url("omegafold")

    esmfold_ok = False
    omegafold_ok = False

    # 检查 ESMFold
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.get(f"{esmfold_url}/health")
                if resp.status_code == 200 and resp.json().get("model_loaded"):
                    esmfold_ok = True
                    log(f"  ESMFold ✅ 已在运行")
            except Exception:
                pass
    except ImportError:
        pass

    # 检查 OmegaFold
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.get(f"{omegafold_url}/health")
                if resp.status_code == 200 and resp.json().get("model_loaded"):
                    omegafold_ok = True
                    log(f"  OmegaFold ✅ 已在运行")
            except Exception:
                pass
    except ImportError:
        pass

    if not esmfold_ok or not omegafold_ok:
        log("\n⚠️  结构预测服务未就绪，请先启动：")
        if not esmfold_ok:
            log(f"   ESMFold:   cd tools/ESMFold && nohup .venv/bin/python service.py &")
        if not omegafold_ok:
            log(f"   OmegaFold: cd tools/OmegaFold && nohup .venv/bin/python service.py &")
        return False

    return True


# ═══════════════════════════════════════════════════════════════════════
# 数据加载
# ═══════════════════════════════════════════════════════════════════════

def load_original_metadata() -> dict[str, dict[str, Any]]:
    """加载 function_2.csv，按序列建立查找索引"""
    meta = {}
    f2_path = PROJECT_ROOT / "data" / "function_2.csv"
    if not f2_path.exists():
        log(f"  ⚠ 找不到 function_2.csv: {f2_path}")
        return meta

    with open(f2_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            seq = row.get("sequence", "").strip()
            if seq:
                meta[seq] = {
                    "is_antimicrobial": _parse_int(row.get("is_antimicrobial")),
                    "is_antioxidant": _parse_int(row.get("is_antioxidant")),
                    "is_antiglycation": _parse_int(row.get("is_antiglycation")),
                    "is_collagen_stimulating": _parse_int(row.get("is_collagen_stimulating")),
                    "is_cell_penetrating": _parse_int(row.get("is_cell_penetrating")),
                    "source_name": row.get("source_name", ""),
                    "source_species": row.get("source_species", ""),
                    "source_protein": row.get("source_protein", ""),
                    "database_id": _parse_int(row.get("database_id")),
                    "database_name": row.get("database_name", ""),
                    "refs_journal": row.get("refs_journal", ""),
                    "refs_title": row.get("refs_title", ""),
                    "doi": row.get("doi", ""),
                    "additional_info": row.get("additional_info", ""),
                    "source_files": row.get("source_files", ""),
                }
    log(f"  原始数据库 function_2: {len(meta)} 条 (按 sequence 索引)")
    return meta


def _parse_int(val) -> int | None:
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def load_peptide_scores() -> dict[str, dict[str, Any]]:
    """加载 all_scored.csv（Round 3 全量评分），按 peptide_id 索引"""
    scores = {}
    path = OUTPUT_DIR / "round03_heavy" / "final" / "all_scored.csv"
    if not path.exists():
        log(f"  ⚠ 找不到 all_scored.csv: {path}")
        return scores

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            pid = row.get("peptide_id", "")
            if not pid:
                continue
            entry = {
                "sequence": row.get("sequence", ""),
                "length": _parse_int(row.get("length")),
                "source": row.get("source", ""),
                "anoxpepred": _parse_float(row.get("anoxpepred")),
                "toxinpred3": _parse_float(row.get("toxinpred3")),
                "algpred2": _parse_float(row.get("algpred2")),
                "hemopi2": _parse_float(row.get("hemopi2")),
                "mhcflurry": _parse_float(row.get("mhcflurry")),
                "bepipred3": _parse_float(row.get("bepipred3")),
                "temstapro": _parse_float(row.get("temstapro")),
                "weighted_score": _parse_float(row.get("weighted_score")),
                "safety_flag": row.get("safety_flag", ""),
            }
            scores[pid] = entry
    log(f"  Round 3 评分: {len(scores)} 条 (按 peptide_id 索引)")
    return scores


def _parse_float(val) -> float | None:
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def load_constructs() -> list[dict[str, Any]]:
    """加载 round5_input.json"""
    path = OUTPUT_DIR / "round04_enumerate" / "final" / "round5_input.json"
    if not path.exists():
        log(f"  ❌ 找不到输入: {path}")
        return []
    with open(path) as f:
        data = json.load(f)
    constructs = data.get("constructs", [])
    log(f"  Construct 列表: {len(constructs)} 条")
    return constructs


def load_sequences() -> dict[str, str]:
    """从 FASTA 加载序列（construct_id → 完整序列）"""
    seqs = {}
    fasta_path = OUTPUT_DIR / "round04_enumerate" / "final" / "top90.fasta"
    if not fasta_path.exists():
        log(f"  ⚠ 找不到 FASTA: {fasta_path}")
        return seqs
    current_id = None
    current_seq: list[str] = []
    with open(fasta_path) as f:
        for line in f:
            line = line.strip()
            if line.startswith(">"):
                if current_id and current_seq:
                    seqs[current_id] = "".join(current_seq)
                current_id = line[1:].split(" | ")[0]
                current_seq = []
            else:
                current_seq.append(line)
        if current_id and current_seq:
            seqs[current_id] = "".join(current_seq)
    log(f"  FASTA 序列: {len(seqs)} 条")
    return seqs


# ═══════════════════════════════════════════════════════════════════════
# 核心：运行单个 construct 的双服务预测
# ═══════════════════════════════════════════════════════════════════════

async def predict_one(
    client: ServiceClient,
    construct: dict[str, Any],
    sequence: str,
    peptide_info: dict[str, Any] | None,
    original_meta: dict[str, Any] | None,
    omegafold_sem: asyncio.Semaphore | None = None,
) -> dict[str, Any]:
    """对一个 construct 同时运行 ESMFold + OmegaFold，写文件夹"""
    cid = construct["construct_id"]
    pid = construct["peptide_id"]
    pep_seq = peptide_info.get("sequence", "") if peptide_info else ""

    # 创建 construct 目录
    con_dir = CONSTRUCTS_DIR / cid
    con_dir.mkdir(parents=True, exist_ok=True)

    # ── 并发运行 ESMFold + OmegaFold ──
    log(f"  ▶ {cid} | {pid} | {construct['position']} | {len(sequence)}aa")

    async def timed_predict(service: str, seq: str, cid: str, timeout: float) -> dict:
        t0 = time.time()
        if service == "omegafold" and omegafold_sem is not None:
            async with omegafold_sem:
                result = await client.predict_structure_async(
                    service, seq,
                    peptide_id=cid,
                    poll_interval=POLL_INTERVAL,
                    timeout=timeout,
                )
        else:
            result = await client.predict_structure_async(
                service, seq,
                peptide_id=cid,
                poll_interval=POLL_INTERVAL,
                timeout=timeout,
            )
        result["_elapsed"] = time.time() - t0
        return result

    esmfold_task = asyncio.create_task(
        timed_predict("esmfold", sequence, cid, ESMFOLD_TIMEOUT)
    )
    omegafold_task = asyncio.create_task(
        timed_predict("omegafold", sequence, cid, OMEGAFOLD_TIMEOUT)
    )

    t0 = time.time()
    esmfold_result, omegafold_result = await asyncio.gather(
        esmfold_task, omegafold_task,
        return_exceptions=True,
    )
    elapsed = time.time() - t0

    # 处理异常
    if isinstance(esmfold_result, Exception):
        esmfold_result = {
            "success": False,
            "peptide_id": cid,
            "error": f"ESMFold exception: {esmfold_result}",
            "confidence": None,
            "pdb_content": "",
            "_elapsed": 0,
        }
    if isinstance(omegafold_result, Exception):
        omegafold_result = {
            "success": False,
            "peptide_id": cid,
            "error": f"OmegaFold exception: {omegafold_result}",
            "confidence": None,
            "pdb_content": "",
            "_elapsed": 0,
        }

    # ── 写入 PDB ──
    esmfold_pdb = esmfold_result.get("pdb_content", "")
    omegafold_pdb = omegafold_result.get("pdb_content", "")

    if esmfold_pdb:
        with open(con_dir / f"{cid}_esmfold.pdb", "w") as f:
            f.write(esmfold_pdb)
    if omegafold_pdb:
        with open(con_dir / f"{cid}_omegafold.pdb", "w") as f:
            f.write(omegafold_pdb)

    # ── 构建 scores.json ──
    esm_plddt = esmfold_result.get("confidence")
    ome_plddt = omegafold_result.get("confidence")

    # 确定最佳 pLDDT
    best_plddt = None
    best_method = None
    for method, plddt in [("esmfold", esm_plddt), ("omegafold", ome_plddt)]:
        if plddt is not None and (best_plddt is None or plddt > best_plddt):
            best_plddt = plddt
            best_method = method

    scores = {
        "construct_composite": construct.get("composite_score"),
        "peptide_composite": construct.get("peptide_score"),
        "sodope": construct.get("sodope_score"),
        "temstapro_construct": construct.get("temstapro_score"),
        "round3_services": {
            "anoxpepred": peptide_info.get("anoxpepred") if peptide_info else None,
            "toxinpred3": peptide_info.get("toxinpred3") if peptide_info else None,
            "algpred2": peptide_info.get("algpred2") if peptide_info else None,
            "hemopi2": peptide_info.get("hemopi2") if peptide_info else None,
            "mhcflurry": peptide_info.get("mhcflurry") if peptide_info else None,
            "bepipred3": peptide_info.get("bepipred3") if peptide_info else None,
            "temstapro": peptide_info.get("temstapro") if peptide_info else None,
        },
        "safety_flag": peptide_info.get("safety_flag") if peptide_info else None,
        "structure": {
            "esmfold": {
                "success": esmfold_result.get("success", False),
                "plddt": round(esm_plddt, 4) if esm_plddt is not None else None,
                "elapsed": round(esmfold_result.get("_elapsed", 0), 1),
                "error": esmfold_result.get("error") if not esmfold_result.get("success") else None,
                "pdb_file": f"{cid}_esmfold.pdb" if esmfold_pdb else None,
            },
            "omegafold": {
                "success": omegafold_result.get("success", False),
                "plddt": round(ome_plddt, 4) if ome_plddt is not None else None,
                "elapsed": round(omegafold_result.get("_elapsed", 0), 1),
                "error": omegafold_result.get("error") if not omegafold_result.get("success") else None,
                "pdb_file": f"{cid}_omegafold.pdb" if omegafold_pdb else None,
            },
            "best_plddt": round(best_plddt, 4) if best_plddt is not None else None,
            "best_method": best_method,
            "total_elapsed": round(elapsed, 1),
        },
    }

    with open(con_dir / "scores.json", "w", encoding="utf-8") as f:
        json.dump(scores, f, ensure_ascii=False, indent=2)

    # ── 构建 metadata.json ──
    metadata = {
        "construct_id": cid,
        "peptide_id": pid,
        "peptide_sequence": pep_seq,
        "linker_id": construct.get("linker_id"),
        "linker_sequence": construct.get("linker_sequence", ""),
        "position": construct.get("position"),
        "sequence_length": construct.get("length"),
        "construct_sequence": sequence,
        "original_database": original_meta or {},
    }

    with open(con_dir / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    # ── 日志 ──
    emoji_esm = "✅" if esmfold_result.get("success") else "❌"
    emoji_ome = "✅" if omegafold_result.get("success") else "❌"
    plddt_str_esm = f"pLDDT={esm_plddt:.4f}" if esm_plddt is not None else "pLDDT=N/A"
    plddt_str_ome = f"pLDDT={ome_plddt:.4f}" if ome_plddt is not None else "pLDDT=N/A"
    log(f"  {emoji_esm} ESMFold   {plddt_str_esm}   ({esmfold_result.get('_elapsed', 0):.0f}s)")
    log(f"  {emoji_ome} OmegaFold {plddt_str_ome}   ({omegafold_result.get('_elapsed', 0):.0f}s)")

    return {
        "construct_id": cid,
        "peptide_id": pid,
        "position": construct.get("position"),
        "linker_id": construct.get("linker_id"),
        "esmfold_success": esmfold_result.get("success", False),
        "esmfold_plddt": round(esm_plddt, 4) if esm_plddt is not None else None,
        "omegafold_success": omegafold_result.get("success", False),
        "omegafold_plddt": round(ome_plddt, 4) if ome_plddt is not None else None,
        "best_plddt": round(best_plddt, 4) if best_plddt is not None else None,
        "best_method": best_method,
        "total_elapsed": round(elapsed, 1),
    }


# ═══════════════════════════════════════════════════════════════════════
# 检查点
# ═══════════════════════════════════════════════════════════════════════

CHECKPOINT_PATH = STAGE_DIR / "checkpoint.json"


def save_checkpoint(results: list[dict]):
    data = {
        "completed_ids": [r["construct_id"] for r in results],
        "results": results,
        "timestamp": datetime.now().isoformat(),
    }
    CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CHECKPOINT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_checkpoint() -> tuple[set[str], list[dict]]:
    completed_ids: set[str] = set()
    results: list[dict] = []
    if CHECKPOINT_PATH.exists():
        with open(CHECKPOINT_PATH) as f:
            data = json.load(f)
        completed_ids = set(data.get("completed_ids", []))
        results = data.get("results", [])
        log(f"📦 恢复检查点: {len(completed_ids)} 个 construct 已完成")
    return completed_ids, results


# ═══════════════════════════════════════════════════════════════════════
# Docker 网络辅助
# ═══════════════════════════════════════════════════════════════════════

def _fix_omegafold_docker_network():
    """将 OmegaFold URL 从 Docker 端口映射改为直连容器 IP，避免 docker-proxy 间歇性故障"""
    try:
        import subprocess
        import json as _json
        result = subprocess.run(
            ["docker", "inspect", "omegafold", "--format", "{{json .NetworkSettings.Networks}}"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            networks = _json.loads(result.stdout)
            for net_name, net_info in networks.items():
                ip = net_info.get("IPAddress", "")
                if ip:
                    os.environ["OMEGAFOLD_HOST"] = ip
                    log(f"  OmegaFold 容器 IP: {ip} (绕过 docker-proxy)")
                    return
    except Exception as e:
        log(f"  ⚠ OmegaFold 网络检测失败: {e}，继续使用 localhost")


# ═══════════════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════════════

async def run():
    global LOG_FILE
    start_time = time.time()

    STAGE_DIR.mkdir(parents=True, exist_ok=True)
    CONSTRUCTS_DIR.mkdir(parents=True, exist_ok=True)
    FINAL_DIR.mkdir(parents=True, exist_ok=True)
    LOG_FILE = STAGE_DIR / "run.log"

    log("=" * 60)
    log("Round 5：3D 结构预测 — ESMFold + OmegaFold")
    log("=" * 60)

    # ── 加载数据 ──
    log("\n📂 加载数据...")
    constructs = load_constructs()
    if not constructs:
        return

    sequences = load_sequences()
    peptide_scores = load_peptide_scores()
    original_metadata = load_original_metadata()

    n_total = len(constructs)
    log(f"\n总计: {n_total} 个 construct")

    # ── 停掉无关服务 ──
    stop_other_services()

    # ── 检查结构预测服务 ──
    if not await ensure_structure_services():
        log("\n❌ 服务未就绪，请先启动 ESMFold 和 OmegaFold")
        return

    # ── 检测 OmegaFold Docker 容器 IP，绕过 docker-proxy ──
    _fix_omegafold_docker_network()

    # ── 恢复检查点 ──
    completed_ids, all_results = load_checkpoint()

    # ── 过滤未完成的 construct ──
    pending = [c for c in constructs if c["construct_id"] not in completed_ids]
    if not pending:
        log("✅ 所有 construct 已完成！")
    else:
        log(f"\n⏳ 待预测: {len(pending)}/{n_total} 个 construct")
        log(f"   并发: {CONCURRENCY} (每个 construct 同时跑 ESMFold + OmegaFold)")
        log(f"   预计: ~{len(pending) // CONCURRENCY * 6} 分钟")

    # ══════════════════════════════════════════════════════════════════
    # 主循环：并发运行 ESMFold + OmegaFold
    # ══════════════════════════════════════════════════════════════════

    client = ServiceClient(timeout=30.0)
    sem = asyncio.Semaphore(CONCURRENCY)
    omegafold_sem = asyncio.Semaphore(OMEGAFOLD_CONCURRENCY)
    results_lock = asyncio.Lock()
    checkpoint_counter = 0

    async def process_one(construct: dict) -> dict | None:
        nonlocal checkpoint_counter
        cid = construct["construct_id"]
        pid = construct["peptide_id"]

        async with sem:
            # 获取序列
            seq = sequences.get(cid, "")
            if not seq:
                log(f"  ⚠ {cid} 无序列，跳过")
                return None

            # 获取肽评分
            pinfo = peptide_scores.get(pid)

            # 获取原始数据库信息（通过序列匹配）
            pep_seq = pinfo.get("sequence", "") if pinfo else ""
            ometa = original_metadata.get(pep_seq) if pep_seq else None

            # 运行双服务预测
            result = await predict_one(client, construct, seq, pinfo, ometa, omegafold_sem)

            async with results_lock:
                all_results.append(result)
                completed_ids.add(cid)
                checkpoint_counter += 1

                if checkpoint_counter % CHECKPOINT_INTERVAL == 0:
                    save_checkpoint(all_results)
                    log(f"  📝 检查点已保存 ({len(completed_ids)}/{n_total})")

            return result

    # 启动所有 construct 的处理
    async def safe_process_one(c: dict) -> dict | None:
        try:
            return await process_one(c)
        except Exception as e:
            log(f"  ❌ {c.get('construct_id', '???')} 异常: {e}")
            import traceback
            log(f"     {traceback.format_exc()}")
            return None

    tasks = [safe_process_one(c) for c in pending]
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
        save_checkpoint(all_results)
        log(f"  📝 最终检查点已保存 ({len(completed_ids)}/{n_total})")

    await client.close()
    total_elapsed = time.time() - start_time

    # ══════════════════════════════════════════════════════════════════
    # 汇总
    # ══════════════════════════════════════════════════════════════════
    log("\n" + "=" * 60)
    log("📊 Round 5 汇总")

    n_esm_ok = sum(1 for r in all_results if r["esmfold_success"])
    n_ome_ok = sum(1 for r in all_results if r["omegafold_success"])
    n_both_ok = sum(1 for r in all_results if r["esmfold_success"] and r["omegafold_success"])

    esm_plddts = [r["esmfold_plddt"] for r in all_results if r["esmfold_plddt"] is not None]
    ome_plddts = [r["omegafold_plddt"] for r in all_results if r["omegafold_plddt"] is not None]

    log(f"  ESMFold:   {n_esm_ok}/{n_total} 成功")
    if esm_plddts:
        log(f"    pLDDT: min={min(esm_plddts):.4f}, max={max(esm_plddts):.4f}, "
            f"mean={sum(esm_plddts)/len(esm_plddts):.4f}")

    log(f"  OmegaFold: {n_ome_ok}/{n_total} 成功")
    if ome_plddts:
        log(f"    pLDDT: min={min(ome_plddts):.4f}, max={max(ome_plddts):.4f}, "
            f"mean={sum(ome_plddts)/len(ome_plddts):.4f}")

    log(f"  双服务均成功: {n_both_ok}/{n_total}")
    log(f"  耗时: {total_elapsed:.0f}s ({total_elapsed/60:.1f}min)")

    # 保存汇总 CSV
    results_sorted = sorted(all_results, key=lambda r: r.get("best_plddt") or 0, reverse=True)
    for i, r in enumerate(results_sorted, 1):
        r["rank"] = i

    csv_path = FINAL_DIR / "all_results.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        if results_sorted:
            writer = csv.DictWriter(f, fieldnames=results_sorted[0].keys())
            writer.writeheader()
            writer.writerows(results_sorted)
    log(f"\n  汇总 CSV: {csv_path}")

    # Top 5
    log(f"\n  Top 5 by pLDDT:")
    for r in results_sorted[:5]:
        log(f"    #{r['rank']:2d} {r['construct_id']:12s} | {r['peptide_id']:12s} | "
            f"ESM={r['esmfold_plddt']:.4f} OME={r['omegafold_plddt']:.4f} "
            f"BEST={r['best_plddt']:.4f} ({r['best_method']})" if r['best_plddt'] else "N/A")

    # 写入 round6_input.json
    round6_input = {
        "source_stage": STAGE,
        "timestamp": datetime.now().isoformat(),
        "n_constructs": n_total,
        "n_esmfold_success": n_esm_ok,
        "n_omegafold_success": n_ome_ok,
        "results": results_sorted,
    }
    with open(FINAL_DIR / "round6_input.json", "w", encoding="utf-8") as f:
        json.dump(round6_input, f, ensure_ascii=False, indent=2)
    log(f"  Round 6 输入: {FINAL_DIR / 'round6_input.json'}")

    # 写入 README
    write_readme(n_total, n_esm_ok, n_ome_ok, n_both_ok,
                 esm_plddts, ome_plddts, results_sorted, total_elapsed)

    log(f"\n✅ Round 5 完成！耗时: {total_elapsed:.0f}s")
    log(f"   Construct 文件: {CONSTRUCTS_DIR}")
    log(f"   汇总 CSV: {csv_path}")


def write_readme(
    n_total: int,
    n_esm_ok: int,
    n_ome_ok: int,
    n_both_ok: int,
    esm_plddts: list[float],
    ome_plddts: list[float],
    results: list[dict],
    elapsed: float,
):
    esm_stats = _plddt_stats(esm_plddts, "ESMFold")
    ome_stats = _plddt_stats(ome_plddts, "OmegaFold")

    top5_lines = "\n".join(
        f"| {r['rank']} | {r['construct_id']} | {r['peptide_id']} | "
        f"{r['linker_id']} | {r['position']} | "
        f"{r['esmfold_plddt']:.4f} | {r['omegafold_plddt']:.4f} | "
        f"{r['best_plddt']:.4f} ({r['best_method']}) |"
        for r in results[:5]
    )

    readme = f"""# Round 5：3D 结构预测 — 报告

**时间**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**耗时**: {elapsed:.0f} 秒 ({elapsed/60:.1f} 分钟)

## 方法

每个 construct 同时运行 **ESMFold** 和 **OmegaFold**，分别保存 PDB 文件。

| 服务 | 模型 | 单条耗时 |
|------|------|----------|
| ESMFold | ESM-2 3B | ~2 min |
| OmegaFold | Protein LM + GeoTransformer | ~6 min |

## 结果

| 指标 | 值 |
|------|-----|
| 总数 | {n_total} |
| ESMFold 成功 | {n_esm_ok}/{n_total} |
| OmegaFold 成功 | {n_ome_ok}/{n_total} |
| 双服务均成功 | {n_both_ok}/{n_total} |

### pLDDT 分布

{esm_stats}

{ome_stats}

## Top 5 by pLDDT

| 排名 | Construct | 肽 | Linker | 位置 | ESMFold | OmegaFold | 最佳 |
|------|-----------|-----|--------|------|---------|-----------|------|
{top5_lines}

## 输出结构

```
output/round05_3d/
├── constructs/
│   ├── con_0001/          ← 每个 construct 一个文件夹
│   │   ├── con_0001_esmfold.pdb
│   │   ├── con_0001_omegafold.pdb
│   │   ├── metadata.json   ← 原始数据库信息
│   │   └── scores.json     ← 全流水线评分 + pLDDT
│   ├── con_0002/
│   └── ...
├── pdb/                    ← PDB 扁平汇总
├── final/
│   ├── all_results.csv
│   └── round6_input.json
└── checkpoint.json
```

## 下一步

Round 6：PDB 评估 — SASA + Aggrescan3D + SoDoPE 综评
"""
    readme_path = STAGE_DIR / "README.md"
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(readme)
    log(f"  报告: {readme_path}")


def _plddt_stats(values: list[float], name: str) -> str:
    if not values:
        return f"**{name}**: 无有效数据"
    mean = sum(values) / len(values)
    sorted_v = sorted(values)
    n = len(sorted_v)
    median = sorted_v[n // 2] if n % 2 else (sorted_v[n // 2 - 1] + sorted_v[n // 2]) / 2
    return (
        f"**{name}** (n={n}): "
        f"mean={mean:.4f}, median={median:.4f}, "
        f"min={sorted_v[0]:.4f}, max={sorted_v[-1]:.4f}"
    )


# ═══════════════════════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════════════════════

def main():
    asyncio.run(run())


if __name__ == "__main__":
    main()
