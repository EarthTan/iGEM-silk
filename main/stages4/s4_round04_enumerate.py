"""
Round 4: Construct 枚举 + 属性评分。

从 Round 3 排名中取 Top N 肽，枚举 3 个融合位置 × 2 种 Linker 的全长 construct，
运行 SoDoPE + TemStaPro 评分。

每轮只排序取百分比，不跨属性加权平均。

用法:
    uv run python -m main.stages4.s4_round04_enumerate
    uv run python -m main.stages4.s4_round04_enumerate --top-n 30000 --top-pct 5
"""

from __future__ import annotations

import asyncio
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

DATA_DIR = PROJECT_ROOT / "data"

from main.client import ServiceClient
from main.data_loader import load_fasta
from main.stages4.s4_db import PipelineDB
from main.stages4.s4_docker_utils import ensure_services
from main.stages4.s4_service_map import get_round_services

# ── Construct 参数 ──
HIS_TAG = "LEHHHHHH"
SELECTED_LINKERS = [
    ("Flex_GGGGSx1", "GGGGS"),
    ("Flex_GGGGSx2", "GGGGSGGGGS"),
]
POSITIONS = ["N", "C", "Both"]


def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


def load_scaffold() -> str:
    """加载丝蛋白骨架序列。"""
    path = DATA_DIR / "silk.fasta"
    records = load_fasta(path)
    if not records:
        raise FileNotFoundError(f"骨架文件不存在: {path}")
    seq = records[0]["sequence"]
    log(f"骨架: {len(seq)} aa ({path.name})")
    return seq


def load_linkers() -> dict[str, str]:
    """加载 Linker 序列。"""
    path = DATA_DIR / "linker.fasta"
    records = load_fasta(path)
    linkers = {r["id"]: r["sequence"] for r in records}
    log(f"Linker: {len(linkers)} 条")
    return linkers


def build_full_sequence(
    scaffold: str, linker_seq: str, peptide_seq: str, position: str
) -> str:
    """组装全长 construct 序列。"""
    if position == "N":
        return f"{peptide_seq}{linker_seq}{scaffold}{HIS_TAG}"
    elif position == "C":
        return f"{scaffold}{linker_seq}{peptide_seq}{HIS_TAG}"
    elif position == "Both":
        return f"{peptide_seq}{linker_seq}{scaffold}{linker_seq}{peptide_seq}{HIS_TAG}"
    else:
        raise ValueError(f"未知位置: {position}")


def enumerate_constructs(
    peptides: list[dict],
    scaffold: str,
    linker_map: dict[str, str],
    channel: str,
) -> list[dict]:
    """枚举 construct。"""
    constructs = []
    n_peptides = len([p for p in peptides if p.get("channel", channel) == channel])
    for p in peptides:
        for pos in POSITIONS:
            for linker_name, linker_seq in SELECTED_LINKERS:
                full_seq = build_full_sequence(
                    scaffold, linker_seq, p["sequence"], pos
                )
                # 找实际的 linker 序列
                actual_linker = linker_seq
                constructs.append({
                    "candidate_id": p["candidate_id"],
                    "linker": linker_name,
                    "linker_seq": actual_linker,
                    "position": pos,
                    "channel": channel,
                    "scaffold_seq": scaffold,
                    "peptide_seq": p["sequence"],
                    "full_sequence": full_seq,
                })
    return constructs


async def run(top_n: int, info: dict | None = None):
    start_time = time.time()

    # ── 1. 连接数据库 ──
    db = PipelineDB()
    conn = db.connect()
    db.init_schema()

    # ── 2. 从 Round 3 排名取 Top N ──
    log(f"从 round3_ranking 取 Top {top_n:,}...")
    ranking_rows = conn.execute(f"""
        SELECT r.candidate_id, r.composite_score, r.rank, ch.channel
        FROM round3_ranking r
        JOIN round1_channels ch ON ch.candidate_id = r.candidate_id
        ORDER BY r.rank
        LIMIT ?
    """, [top_n]).fetchall()

    if not ranking_rows:
        log("❌ Round 3 排名为空，请先运行 Round 3")
        return

    candidate_ids = [r[0] for r in ranking_rows]
    log(f"  Top {len(candidate_ids)} 候选")

    # 获取序列
    seq_rows = conn.execute(f"""
        SELECT candidate_id, sequence FROM candidates
        WHERE candidate_id IN ({','.join(str(c) for c in candidate_ids)})
    """).fetchall()
    seq_map = {int(r[0]): r[1] for r in seq_rows}

    # ── 3. 加载骨架和 Linker ──
    log("\n加载序列数据...")
    scaffold = load_scaffold()
    linker_map = load_linkers()

    # ── 4. 枚举 construct ──
    log("\n枚举 construct...")
    peptides = []
    for cid, score, rank, channel in ranking_rows:
        seq = seq_map.get(cid)
        if seq:
            peptides.append({
                "candidate_id": cid,
                "sequence": seq,
                "composite_score": score,
                "rank": rank,
                "channel": channel,
            })

    # 按通道分别枚举
    top_peptides = [p for p in peptides if p.get("channel") == "top"]
    bottom_peptides = [p for p in peptides if p.get("channel") == "bottom"]

    all_constructs = []
    all_constructs.extend(enumerate_constructs(top_peptides, scaffold, linker_map, "top"))
    if bottom_peptides:
        all_constructs.extend(enumerate_constructs(bottom_peptides, scaffold, linker_map, "bottom"))

    log(f"  枚举完成: {len(all_constructs):,} constructs")
    log(f"    Top: {len(top_peptides)} peptides × {len(POSITIONS)} pos × {len(SELECTED_LINKERS)} linker = {len(top_peptides) * len(POSITIONS) * len(SELECTED_LINKERS)}")
    if bottom_peptides:
        log(f"    Bottom: {len(bottom_peptides)} peptides × {len(POSITIONS)} pos × {len(SELECTED_LINKERS)} linker = {len(bottom_peptides) * len(POSITIONS) * len(SELECTED_LINKERS)}")

    # ── 5. 写入 constructs 表 ──
    log("\n写入 constructs 表...")
    construct_ids = db.insert_constructs(all_constructs)
    for i, cid in enumerate(construct_ids):
        all_constructs[i]["construct_id"] = cid
    log(f"  写入完成: {len(construct_ids)} 条")

    # ── 6. 运行 SoDoPE + TemStaPro ──
    if info:
        unavailable = [s for s, h in info.items() if not h.get("available")]
        if unavailable:
            log(f"❌ 服务不可用: {unavailable}")
            return

    log("评分 construct...")
    client = ServiceClient(timeout=300.0)
    concurrency = asyncio.Semaphore(10)
    batch_size = 100

    chunks = [all_constructs[i:i + batch_size] for i in range(0, len(all_constructs), batch_size)]

    async def score_constructs(chunk: list[dict], svc: str) -> list[dict]:
        async with concurrency:
            items = [
                {"peptide_id": str(c["construct_id"]), "sequence": c["full_sequence"]}
                for c in chunk
            ]
            result = await client.predict_batch(svc, items)
            if result.get("success") and result.get("results"):
                return result["results"]
            return [{"peptide_id": item["peptide_id"], "score": None} for item in items]

    async def score_service(svc: str, chunk_size: int) -> dict[str, float]:
        c = [all_constructs[i:i + chunk_size] for i in range(0, len(all_constructs), chunk_size)]
        tasks = [score_constructs(chunk, svc) for chunk in c]
        results = await asyncio.gather(*tasks)
        flat: dict[str, float] = {}
        for batch_res in results:
            for r in batch_res:
                flat[r["peptide_id"]] = r.get("score")
        return flat

    sodope_map, temsta_map = await asyncio.gather(
        score_service("sodope", batch_size),
        score_service("temstapro", batch_size),
    )

    score_records = []
    for c in all_constructs:
        cid = c["construct_id"]
        score_records.append({
            "construct_id": cid,
            "sodope_score": sodope_map.get(str(cid)),
            "sodope_success": sodope_map.get(str(cid)) is not None,
            "temstapro_score": temsta_map.get(str(cid)),
            "temstapro_success": temsta_map.get(str(cid)) is not None,
        })

    db.insert_construct_scores(score_records)
    await client.close()
    log(f"  Construct 评分完成: {len(score_records)} 条")

    total_elapsed = time.time() - start_time
    db.set_checkpoint("round4", "enumerate", "done",
                      total=len(all_constructs), processed=len(all_constructs))

    log(f"\n{'='*55}")
    log(f"  Round 4 完成!")
    log(f"  Constructs: {len(all_constructs):>10,}")
    log(f"  总耗时:     {total_elapsed:>8.0f}s")
    log(f"{'='*55}")

    db.close()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Round 4: Construct 枚举")
    parser.add_argument("--top-n", type=int, default=30000,
                        help="从 Round 3 取多少肽用于枚举 (default: 30000)")
    args = parser.parse_args()

    log(f"Round 4: Construct 枚举 + 属性评分")

    info = get_round_services("round4")
    log(f"依赖服务: {', '.join(info['services'])}")
    health = ensure_services(info["services"], info["profiles"], timeout=180.0)

    asyncio.run(run(args.top_n, info=health))


if __name__ == "__main__":
    main()
