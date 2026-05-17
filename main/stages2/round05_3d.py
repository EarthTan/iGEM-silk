"""
Round 5：3D 结构预测 — ESMFold + OmegaFold

对 Round 4 的全部 construct（Top + Bottom）同时运行 ESMFold 和 OmegaFold，
每个 construct 一个独立文件夹。与原脚本的核心差异：
  - 输出到 output2/
  - 使用 common.py 共享工具
  - 移除 stop_other_services()（原脚本杀死非结构服务自身的 bug）
  - 保留 OmegaFold Docker 桥接 IP 检测（已验证有效）
  - 所有 construct（top + bottom）统一处理

用法：
    uv run python -m main.stages2.round05_3d

输入：
    output2/round04_enumerate/final/round5_input.json
    output2/round04_enumerate/final/all_constructs.fasta
    output2/round03_heavy/final/all_scored.csv（可选，肽评分）
    data/function_2.csv（可选，原始元数据）

输出：
    output2/round05_3d/
    ├── constructs/con_XXXX/   ← 每个 construct 独立文件夹
    │   ├── con_XXXX_esmfold.pdb
    │   ├── con_XXXX_omegafold.pdb
    │   ├── scores.json
    │   └── metadata.json
    ├── final/all_results.csv
    ├── final/round6_input.json
    ├── README.md
    └── run.log
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from main.client import ServiceClient
from main.config import service_url
from main.stages2.common import (
    OUTPUT_DIR, log, setup_stage, make_dir, write_json, read_json,
)

STAGE = "round05_3d"
STAGE_DIR = OUTPUT_DIR / STAGE
CONSTRUCTS_DIR = STAGE_DIR / "constructs"
FINAL_DIR = STAGE_DIR / "final"

# ── 并发控制 ──
CONCURRENCY = 2                # 同时处理几个 construct
ESMFOLD_TIMEOUT = 7200         # ESMFold 单任务超时（2h）
OMEGAFOLD_TIMEOUT = 14400      # OmegaFold 单任务超时（4h）
OMEGAFOLD_CONCURRENCY = 1      # OmegaFold 全局并发（服务端阻塞事件循环）
POLL_INTERVAL = 30.0
CHECKPOINT_INTERVAL = 3
CHECKPOINT_PATH = STAGE_DIR / "checkpoint.json"


# ═══════════════════════════════════════════════════════════════════════
# 数据加载
# ═══════════════════════════════════════════════════════════════════════

def load_constructs() -> list[dict[str, Any]]:
    """加载 round5_input.json（含 channel 标签）。"""
    path = OUTPUT_DIR / "round04_enumerate" / "final" / "round5_input.json"
    if not path.exists():
        log(f"  ❌ 找不到输入: {path}")
        return []
    data = read_json(path)
    constructs = data.get("constructs", [])
    log(f"  Construct 列表: {len(constructs)} 条（Top: {data.get('n_top', '?')}, Bottom: {data.get('n_bottom', '?')}）")
    return constructs


def load_sequences() -> dict[str, str]:
    """从 FASTA 加载序列（construct_id → 完整序列）。"""
    seqs: dict[str, str] = {}
    fasta_path = OUTPUT_DIR / "round04_enumerate" / "final" / "all_constructs.fasta"
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


def _parse_float(val) -> float | None:
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _parse_int(val) -> int | None:
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def load_original_metadata() -> dict[str, dict[str, Any]]:
    """加载 function_2.csv，按序列建立查找索引。"""
    meta: dict[str, dict] = {}
    f2_path = PROJECT_ROOT / "data" / "function_2.csv"
    if not f2_path.exists():
        log(f"  ⚠ 找不到 function_2.csv: {f2_path}")
        return meta
    import csv
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
    log(f"  原始数据库 function_2: {len(meta)} 条（按 sequence 索引）")
    return meta


def load_peptide_scores() -> dict[str, dict[str, Any]]:
    """加载 Round 3 全量肽评分。"""
    scores: dict[str, dict] = {}
    path = OUTPUT_DIR / "round03_heavy" / "final" / "all_scored.csv"
    if not path.exists():
        log(f"  ⚠ 找不到 all_scored.csv: {path}")
        return scores
    import csv
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            pid = row.get("peptide_id", "")
            if not pid:
                continue
            scores[pid] = {
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
    log(f"  Round 3 评分: {len(scores)} 条（按 peptide_id 索引）")
    return scores


# ═══════════════════════════════════════════════════════════════════════
# 服务检查（取代原 stop_other_services + ensure_structure_services）
# ═══════════════════════════════════════════════════════════════════════

def _fix_omegafold_docker_network():
    """将 OmegaFold URL 从 Docker 端口映射改为直连容器 IP。"""
    try:
        result = subprocess.run(
            ["docker", "inspect", "omegafold", "--format", "{{json .NetworkSettings.Networks}}"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            networks = json.loads(result.stdout)
            for net_name, net_info in networks.items():
                ip = net_info.get("IPAddress", "")
                if ip:
                    os.environ["OMEGAFOLD_HOST"] = ip
                    log(f"  OmegaFold 容器 IP: {ip}（绕过 docker-proxy）")
                    return
    except Exception as e:
        log(f"  ⚠ OmegaFold 网络检测失败: {e}，继续使用 localhost")


async def ensure_structure_services(client: ServiceClient) -> bool:
    """检查 ESMFold 和 OmegaFold 是否就绪。"""
    log("\n🔍 检查结构预测服务...")
    health = await client.check_health(["esmfold", "omegafold"])
    esm_ok = health.get("esmfold", {}).get("available", False)
    ome_ok = health.get("omegafold", {}).get("available", False)

    if esm_ok:
        log(f"  ESMFold ✅ 已就绪")
    else:
        log(f"  ESMFold ❌ 不可达 — 请启动服务")
    if ome_ok:
        log(f"  OmegaFold ✅ 已就绪")
    else:
        log(f"  OmegaFold ❌ 不可达 — 请启动服务")

    if not esm_ok or not ome_ok:
        log("\n⚠️  请先启动结构预测服务:")
        if not esm_ok:
            log("   ESMFold:   cd tools/ESMFold && nohup .venv/bin/python service.py --port 8203 &")
        if not ome_ok:
            log("   OmegaFold: cd tools/OmegaFold && nohup .venv/bin/python service.py --port 8204 &")
        return False

    _fix_omegafold_docker_network()
    return True


# ═══════════════════════════════════════════════════════════════════════
# 核心：单个 construct 的双服务预测
# ═══════════════════════════════════════════════════════════════════════

async def predict_one(
    client: ServiceClient,
    construct: dict[str, Any],
    sequence: str,
    peptide_info: dict[str, Any] | None,
    original_meta: dict[str, Any] | None,
    omegafold_sem: asyncio.Semaphore | None = None,
) -> dict[str, Any]:
    """对一个 construct 同时运行 ESMFold + OmegaFold，写文件夹。"""
    cid = construct["construct_id"]
    pid = construct["peptide_id"]
    pep_seq = peptide_info.get("sequence", "") if peptide_info else ""

    con_dir = CONSTRUCTS_DIR / cid
    con_dir.mkdir(parents=True, exist_ok=True)

    log(f"  ▶ {cid} | {pid} | {construct.get('position', '?')} | {len(sequence)}aa | {construct.get('channel', '?')}")

    async def timed_predict(service: str, seq: str, cid: str, timeout: float) -> dict:
        t0 = time.time()
        if service == "omegafold" and omegafold_sem is not None:
            async with omegafold_sem:
                result = await client.predict_structure_async(
                    service, seq, peptide_id=cid,
                    poll_interval=POLL_INTERVAL, timeout=timeout,
                )
        else:
            result = await client.predict_structure_async(
                service, seq, peptide_id=cid,
                poll_interval=POLL_INTERVAL, timeout=timeout,
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
        esmfold_task, omegafold_task, return_exceptions=True,
    )
    elapsed = time.time() - t0

    if isinstance(esmfold_result, Exception):
        esmfold_result = {
            "success": False, "peptide_id": cid,
            "error": f"ESMFold exception: {esmfold_result}",
            "confidence": None, "pdb_content": "", "_elapsed": 0,
        }
    if isinstance(omegafold_result, Exception):
        omegafold_result = {
            "success": False, "peptide_id": cid,
            "error": f"OmegaFold exception: {omegafold_result}",
            "confidence": None, "pdb_content": "", "_elapsed": 0,
        }

    # PDB
    esmfold_pdb = esmfold_result.get("pdb_content", "")
    omegafold_pdb = omegafold_result.get("pdb_content", "")
    if esmfold_pdb:
        (con_dir / f"{cid}_esmfold.pdb").write_text(esmfold_pdb)
    if omegafold_pdb:
        (con_dir / f"{cid}_omegafold.pdb").write_text(omegafold_pdb)

    # pLDDT
    esm_plddt = esmfold_result.get("confidence")
    ome_plddt = omegafold_result.get("confidence")
    best_plddt = None
    best_method = None
    for method, plddt in [("esmfold", esm_plddt), ("omegafold", ome_plddt)]:
        if plddt is not None and (best_plddt is None or plddt > best_plddt):
            best_plddt = plddt
            best_method = method

    # scores.json
    scores = {
        "construct_composite": construct.get("composite_score"),
        "peptide_composite": construct.get("peptide_weighted_score"),
        "sodope": construct.get("sodope_score"),
        "temstapro_construct": construct.get("construct_temstapro"),
        "construct_anoxpepred": construct.get("construct_anoxpepred"),
        "construct_bepipred3": construct.get("construct_bepipred3"),
        "anox_change_ratio": construct.get("anox_change_ratio"),
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
    write_json(con_dir / "scores.json", scores)

    # metadata.json
    metadata = {
        "construct_id": cid,
        "channel": construct.get("channel", "top"),
        "peptide_id": pid,
        "peptide_sequence": pep_seq,
        "linker_id": construct.get("linker_id"),
        "position": construct.get("position"),
        "sequence_length": construct.get("length"),
        "construct_sequence": sequence,
        "original_database": original_meta or {},
    }
    write_json(con_dir / "metadata.json", metadata)

    emoji_esm = "✅" if esmfold_result.get("success") else "❌"
    emoji_ome = "✅" if omegafold_result.get("success") else "❌"
    plddt_str_esm = f"pLDDT={esm_plddt:.4f}" if esm_plddt is not None else "pLDDT=N/A"
    plddt_str_ome = f"pLDDT={ome_plddt:.4f}" if ome_plddt is not None else "pLDDT=N/A"
    log(f"  {emoji_esm} ESMFold   {plddt_str_esm}   ({esmfold_result.get('_elapsed', 0):.0f}s)")
    log(f"  {emoji_ome} OmegaFold {plddt_str_ome}   ({omegafold_result.get('_elapsed', 0):.0f}s)")

    return {
        "construct_id": cid,
        "channel": construct.get("channel", "top"),
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

def save_checkpoint(results: list[dict]):
    data = {
        "completed_ids": [r["construct_id"] for r in results],
        "results": results,
        "timestamp": datetime.now().isoformat(),
    }
    CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
    write_json(CHECKPOINT_PATH, data)


def load_checkpoint() -> tuple[set[str], list[dict]]:
    completed_ids: set[str] = set()
    results: list[dict] = []
    if CHECKPOINT_PATH.exists():
        data = read_json(CHECKPOINT_PATH)
        completed_ids = set(data.get("completed_ids", []))
        results = data.get("results", [])
        log(f"📦 恢复检查点: {len(completed_ids)} 个 construct 已完成")
    return completed_ids, results


# ═══════════════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════════════

async def run():
    start_time = time.time()
    setup_stage(STAGE)
    CONSTRUCTS_DIR.mkdir(parents=True, exist_ok=True)
    FINAL_DIR.mkdir(parents=True, exist_ok=True)

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

    # ── 服务检查（不再停用其他服务）──
    client = ServiceClient(timeout=30.0)
    if not await ensure_structure_services(client):
        log("\n❌ 服务未就绪，请先启动 ESMFold 和 OmegaFold")
        await client.close()
        return

    # ── 恢复检查点 ──
    completed_ids, all_results = load_checkpoint()
    pending = [c for c in constructs if c["construct_id"] not in completed_ids]

    if not pending:
        log("✅ 所有 construct 已完成！")
    else:
        log(f"\n⏳ 待预测: {len(pending)}/{n_total} 个 construct")
        est_min = len(pending) // CONCURRENCY * 6
        log(f"   并发: {CONCURRENCY} | 预计: ~{est_min} 分钟")

    # ══════════════════════════════════════════════════════════════════
    # 主循环
    # ══════════════════════════════════════════════════════════════════
    sem = asyncio.Semaphore(CONCURRENCY)
    omegafold_sem = asyncio.Semaphore(OMEGAFOLD_CONCURRENCY)
    results_lock = asyncio.Lock()
    checkpoint_counter = 0

    async def process_one(construct: dict) -> dict | None:
        nonlocal checkpoint_counter
        cid = construct["construct_id"]
        pid = construct["peptide_id"]
        async with sem:
            seq = sequences.get(cid, "")
            if not seq:
                log(f"  ⚠ {cid} 无序列，跳过")
                return None
            pinfo = peptide_scores.get(pid)
            pep_seq = pinfo.get("sequence", "") if pinfo else ""
            ometa = original_metadata.get(pep_seq) if pep_seq else None
            result = await predict_one(client, construct, seq, pinfo, ometa, omegafold_sem)
            async with results_lock:
                all_results.append(result)
                completed_ids.add(cid)
                checkpoint_counter += 1
                if checkpoint_counter % CHECKPOINT_INTERVAL == 0:
                    save_checkpoint(all_results)
                    log(f"  📝 检查点已保存 ({len(completed_ids)}/{n_total})")
            return result

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
        log(f"    pLDDT: min={min(esm_plddts):.4f}, max={max(esm_plddts):.4f}, mean={sum(esm_plddts)/len(esm_plddts):.4f}")
    log(f"  OmegaFold: {n_ome_ok}/{n_total} 成功")
    if ome_plddts:
        log(f"    pLDDT: min={min(ome_plddts):.4f}, max={max(ome_plddts):.4f}, mean={sum(ome_plddts)/len(ome_plddts):.4f}")
    log(f"  双服务均成功: {n_both_ok}/{n_total}")
    log(f"  耗时: {total_elapsed:.0f}s ({total_elapsed/60:.1f}min)")

    # 汇总 CSV
    results_sorted = sorted(all_results, key=lambda r: r.get("best_plddt") or 0, reverse=True)
    for i, r in enumerate(results_sorted, 1):
        r["rank"] = i
    import csv
    csv_path = FINAL_DIR / "all_results.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        if results_sorted:
            writer = csv.DictWriter(f, fieldnames=list(results_sorted[0].keys()))
            writer.writeheader()
            writer.writerows(results_sorted)
    log(f"\n  汇总 CSV: {csv_path}")

    # Top 5
    log(f"\n  Top 5 by pLDDT:")
    for r in results_sorted[:5]:
        log(f"    #{r['rank']:2d} {r['construct_id']:12s} | {r['peptide_id']:12s} | "
            f"ESM={r['esmfold_plddt']:.4f} OME={r['omegafold_plddt']:.4f} "
            f"BEST={r['best_plddt']:.4f} ({r['best_method']})" if r['best_plddt'] else "N/A")

    # Round 6 输入（含 channel）
    round6_input = {
        "source_stage": STAGE,
        "timestamp": datetime.now().isoformat(),
        "n_constructs": n_total,
        "n_esmfold_success": n_esm_ok,
        "n_omegafold_success": n_ome_ok,
        "results": results_sorted,
    }
    write_json(FINAL_DIR / "round6_input.json", round6_input)
    log(f"  Round 6 输入: {FINAL_DIR / 'round6_input.json'}")

    # README
    _write_readme(n_total, n_esm_ok, n_ome_ok, n_both_ok, esm_plddts, ome_plddts, results_sorted, total_elapsed)
    log(f"\n✅ Round 5 完成！耗时: {total_elapsed:.0f}s")


def _write_readme(n_total, n_esm_ok, n_ome_ok, n_both_ok, esm_plddts, ome_plddts, results, elapsed):
    def plddt_stats(values, name):
        if not values:
            return f"**{name}**: 无有效数据"
        mean = sum(values) / len(values)
        sorted_v = sorted(values)
        n = len(sorted_v)
        median = sorted_v[n // 2] if n % 2 else (sorted_v[n // 2 - 1] + sorted_v[n // 2]) / 2
        return f"**{name}** (n={n}): mean={mean:.4f}, median={median:.4f}, min={sorted_v[0]:.4f}, max={sorted_v[-1]:.4f}"

    top5 = results[:5]
    top5_lines = "\n".join(
        f"| {r['rank']} | {r['construct_id']} | {r['peptide_id']} | "
        f"{r['linker_id']} | {r['position']} | "
        f"{r['esmfold_plddt']:.4f} | {r['omegafold_plddt']:.4f} | "
        f"{r['best_plddt']:.4f} ({r['best_method']}) |" for r in top5
    )

    readme = f"""# Round 5：3D 结构预测 — 报告

**时间**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**耗时**: {elapsed:.0f} 秒 ({elapsed/60:.1f} 分钟)

## 结果

| 指标 | 值 |
|------|-----|
| 总数 | {n_total} |
| ESMFold 成功 | {n_esm_ok}/{n_total} |
| OmegaFold 成功 | {n_ome_ok}/{n_total} |
| 双服务均成功 | {n_both_ok}/{n_total} |

### pLDDT 分布

{plddt_stats(esm_plddts, "ESMFold")}

{plddt_stats(ome_plddts, "OmegaFold")}

## Top 5 by pLDDT

| 排名 | Construct | 肽 | Linker | 位置 | ESMFold | OmegaFold | 最佳 |
|------|-----------|-----|--------|------|---------|-----------|------|
{top5_lines}

## 输出

```
output2/round05_3d/
├── constructs/con_XXXX/   ← 每个 construct 独立文件夹
│   ├── con_XXXX_esmfold.pdb
│   ├── con_XXXX_omegafold.pdb
│   ├── metadata.json
│   └── scores.json
└── final/
    ├── all_results.csv
    └── round6_input.json
```
"""
    (STAGE_DIR / "README.md").write_text(readme, encoding="utf-8")
    log(f"  报告: {STAGE_DIR / 'README.md'}")


def main():
    asyncio.run(run())


if __name__ == "__main__":
    main()
