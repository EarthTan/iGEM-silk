"""
Round 5: 3D 结构预测 — OmegaFold。

从 constructs 表读取所有 construct 序列，运行 OmegaFold 3D 预测。
OmegaFold 阻塞事件循环，只能串行推理（Semaphore=1）。

用法:
    uv run python -m main.stages4.s4_round05_3d
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

import httpx

from main.client import ServiceClient
from main.config import service_url
from main.stages4.s4_db import PipelineDB
from main.stages4.s4_docker_utils import ensure_services
from main.stages4.s4_service_map import get_round_services

OUTPUT4 = PROJECT_ROOT / "output4"
PDB_DIR = OUTPUT4 / "pdb"
PDB_DIR.mkdir(parents=True, exist_ok=True)

# ── 并发控制 ──
CONCURRENCY = 1
PREDICT_TIMEOUT = 14400
POLL_INTERVAL = 30.0
PROGRESS_INTERVAL = 5


def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


async def predict_omegafold(
    client: httpx.AsyncClient,
    sequence: str,
    construct_id: int,
    sem: asyncio.Semaphore,
) -> dict:
    """调用 OmegaFold 预测单个 construct 的 3D 结构。"""
    async with sem:
        url = f"{service_url('omegafold')}/predict/batch"
        payload = {
            "sequences": [{"peptide_id": f"con_{construct_id:04d}", "sequence": sequence}],
        }
        try:
            resp = await client.post(url, json=payload, timeout=PREDICT_TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                # OmegaFold 返回 {success: true, results: [{pdb_content, confidence, details}]}
                results = data.get("results", [])
                if results:
                    r = results[0]
                    return {
                        "construct_id": construct_id,
                        "success": True,
                        "pdb": r.get("pdb_content", ""),
                        "confidence": r.get("confidence"),
                        "error": None,
                    }
                return {
                    "construct_id": construct_id, "success": False,
                    "pdb": "", "confidence": None,
                    "error": "Empty results",
                }
            else:
                return {
                    "construct_id": construct_id,
                    "success": False,
                    "pdb": "", "confidence": None,
                    "error": f"HTTP {resp.status_code}: {resp.text[:200]}",
                }
        except Exception as e:
            return {
                "construct_id": construct_id,
                "success": False,
                "pdb": "", "confidence": None,
                "error": str(e),
            }


async def run(sample: int = 0):
    start_time = time.time()

    # ── 1. 连接数据库 ──
    db = PipelineDB()
    conn = db.connect()
    db.init_schema()

    # ── 2. 从 constructs 表读取 ──
    limit_clause = f"LIMIT {sample}" if sample else ""
    rows = conn.execute(f"""
        SELECT c.construct_id, c.full_sequence, c.channel
        FROM constructs c
        ORDER BY c.construct_id
        {limit_clause}
    """).fetchall()

    if not rows:
        log("❌ constructs 表为空，请先运行 Round 4")
        return

    all_constructs = [
        {"construct_id": int(r[0]), "sequence": r[1], "channel": r[2]}
        for r in rows
    ]
    log(f"待预测: {len(all_constructs)} constructs")

    # ── 3. 检查已完成 ──
    done = db.row_count("structure_results")
    if done > 0:
        log(f"已完成: {done}，跳过已完成的任务")
        remaining = [c for c in all_constructs
                     if not conn.execute(
                         "SELECT 1 FROM structure_results WHERE construct_id=?",
                         [c["construct_id"]]
                     ).fetchone()]
        log(f"待预测: {len(remaining)} constructs")
        all_constructs = remaining

    if not all_constructs:
        log("✅ 所有 construct 已完成 3D 预测")
        return

    # ── 4. 确保 Docker 服务就绪（已在 main() 中检查） ──
    log("✅ OmegaFold 就绪 (已在 main 中验证)")

    # ── 5. 预测循环 ──
    sem = asyncio.Semaphore(CONCURRENCY)
    async with httpx.AsyncClient(timeout=PREDICT_TIMEOUT) as client:
        for idx, c in enumerate(all_constructs):
            cid = c["construct_id"]
            seq = c["sequence"]

            log(f"[{idx + 1}/{len(all_constructs)}] con_{cid:04d} ({len(seq)} aa) ...")

            result = await predict_omegafold(client, seq, cid, sem)

            if result["success"] and result["pdb"]:
                # 保存 PDB
                construct_dir = PDB_DIR / f"con_{cid:04d}"
                construct_dir.mkdir(parents=True, exist_ok=True)
                pdb_path = construct_dir / "omegafold.pdb"
                with open(pdb_path, "w") as f:
                    f.write(result["pdb"])

                # 提取 pLDDT（直接从 confidence 字段，或从 details.mean_plddt）
                plddt_val = result.get("confidence")

                db.write_structure_result(
                    construct_id=cid,
                    service="omegafold",
                    pdb_path=str(pdb_path),
                    plddt=plddt_val,
                )

                plddt_str = f"{plddt_val:.4f}" if plddt_val is not None else "N/A"
                log(f"  ✅ pLDDT={plddt_str}, PDB={pdb_path}")
            else:
                log(f"  ❌ 失败: {result['error'][:100]}")
                db.write_structure_result(
                    construct_id=cid,
                    service="omegafold",
                    pdb_path="",
                    plddt=None,
                )

            # 进度报告
            if (idx + 1) % PROGRESS_INTERVAL == 0:
                elapsed = time.time() - start_time
                done_count = db.row_count("structure_results")
                log(f"  进度: {done_count}/{len(all_constructs)} | 耗时: {elapsed:.0f}s")

    total_elapsed = time.time() - start_time
    success = db.row_count("structure_results")
    log(f"\n{'='*55}")
    log(f"  Round 5 完成!")
    log(f"  完成: {success}/{len(all_constructs)}")
    log(f"  总耗时: {total_elapsed:.0f}s ({total_elapsed/60:.1f} min)")
    log(f"{'='*55}")

    db.close()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Round 5: 3D 结构预测")
    parser.add_argument("--sample", type=int, default=0,
                        help="采样模式：只处理前 N 个 construct (default: 全量)")
    args = parser.parse_args()

    log("Round 5: 3D 结构预测 — OmegaFold")

    info = get_round_services("round5")
    log(f"依赖服务: {', '.join(info['services'])}")
    health = ensure_services(info["services"], info["profiles"], timeout=300.0)
    unavailable = [s for s, h in health.items() if not h["available"]]
    if unavailable:
        log(f"❌ OmegaFold 不可用: {unavailable}")
        sys.exit(1)

    asyncio.run(run(sample=args.sample))


if __name__ == "__main__":
    main()
