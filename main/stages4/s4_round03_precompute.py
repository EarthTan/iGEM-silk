"""
Round 3 预打分脚本 — 利用 Round 2 运行中的 GPU 空闲提前为 deep scoring 打分。

无需等 Round 2 完成，直接从 round1_channels 读取候选列表，
逐服务顺序打分（避免 GPU 显存竞争），写入 round3_scores 表。

写入幂等：insert_round3_scores() 使用 ON CONFLICT DO UPDATE，
多轮写入不同服务的分数不会互相覆盖。

用法:
    # 全量预打分（默认 5 个服务）
    uv run python -m main.stages4.s4_round03_precompute

    # 指定服务子集（断点续跑或部分重打）
    uv run python -m main.stages4.s4_round03_precompute \\
        --services sodope,plm4cpps

    # 恢复模式：跳过已完成的服务
    uv run python -m main.stages4.s4_round03_precompute \\
        --services sodope,bepipred3,temstapro --resume

    # 查看 checkpoint 状态
    uv run python -m main.stages4.s4_round03_precompute --status
"""

from __future__ import annotations

import asyncio
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from main.client import ServiceClient
from main.stages4.s4_db import PipelineDB

# ── 服务顺序（CPU 先出结果，GPU 由轻到重避免显存竞争） ──
SERVICE_ORDER = ["sodope", "plm4cpps", "graphcpp", "bepipred3", "temstapro"]

# ── 参数（与 s4_round03_deep_scoring.py 保持一致） ──
BATCH_SIZE = 1_000
CONCURRENCY = 5
TIMEOUT = 300.0
CHECKPOINT_PREFIX = "round3_precompute"
PROGRESS_INTERVAL = 10  # 每 N 批报告一次


def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def print_status(db: PipelineDB):
    """打印各服务预打分 checkpoint 状态。"""
    log("预打分状态:")
    for svc in SERVICE_ORDER:
        cp = db.get_checkpoint(f"{CHECKPOINT_PREFIX}_{svc}")
        if cp:
            log(f"  {svc}: {cp['status']} (processed={cp['processed_items']:,})")
        else:
            log(f"  {svc}: 未开始")
    scored = db.get_last_processed_id("round3_scores")
    log(f"round3_scores 总计: {scored:,} 条")


async def run(
    services_subset: list[str] | None = None,
    resume: bool = False,
):
    db = PipelineDB()
    db.connect()
    db.init_schema()

    # ── 1. 读取 channel candidates（不依赖 Round 2） ──
    top = db.get_channel_candidates("top")
    bottom = db.get_channel_candidates("bottom")
    all_candidates = top + bottom
    total = len(all_candidates)
    log(f"从 round1_channels 读取: {total:,} 条 (top={len(top):,}, bottom={len(bottom):,})")

    if not all_candidates:
        log("❌ 无候选，请先运行 Round 1")
        return

    # ── 2. 确定要打分的服务列表 ──
    services = services_subset or list(SERVICE_ORDER)

    # ── 3. 逐服务顺序打分 ──
    for svc in services:
        if svc not in SERVICE_ORDER:
            log(f"⚠️ 跳过未知服务: {svc} (有效: {SERVICE_ORDER})")
            continue

        # 检查 checkpoint（断点续跑）
        cp = db.get_checkpoint(f"{CHECKPOINT_PREFIX}_{svc}")
        if resume and cp and cp["status"] == "done":
            log(f"  {svc}: ✅ 已跳过（上次已完成 {cp['processed_items']:,} 条）")
            continue

        log(f"\n▶ 开始 {svc} 预打分 ({total:,} 条)...")
        svc_start = time.time()
        db.set_checkpoint(CHECKPOINT_PREFIX, svc, "running",
                          total=total, processed=0)

        client = ServiceClient(timeout=TIMEOUT)
        sem = asyncio.Semaphore(CONCURRENCY)
        chunks = [all_candidates[i:i + BATCH_SIZE]
                  for i in range(0, total, BATCH_SIZE)]

        async def score_chunk(chunk: list[dict]) -> list[dict]:
            async with sem:
                items = [
                    {"peptide_id": str(c["candidate_id"]), "sequence": c["sequence"]}
                    for c in chunk
                ]
                result = await client.predict_batch(svc, items)
                if result.get("success") and result.get("results"):
                    return result["results"]
                return [{"peptide_id": item["peptide_id"], "score": None}
                        for item in items]

        # ── 分批打分 + 写入 ──
        for chunk_idx, chunk in enumerate(chunks):
            results = await score_chunk(chunk)

            # 构建 round3_scores record（只设当前服务的分数，其他留 NULL）
            records = []
            for c in chunk:
                cid_str = str(c["candidate_id"])
                record: dict = {"candidate_id": c["candidate_id"]}
                # 当前服务的分数
                matching = [r for r in results if r["peptide_id"] == cid_str]
                score = matching[0].get("score") if matching else None
                record[f"{svc}_score"] = score
                record[f"{svc}_success"] = score is not None
                # 其他服务字段留 NULL
                for other in SERVICE_ORDER:
                    if other == svc:
                        continue
                    record[f"{other}_score"] = None
                    record[f"{other}_success"] = False
                records.append(record)

            db.insert_round3_scores(records)
            db.set_checkpoint(CHECKPOINT_PREFIX, svc, "running",
                              total=total, processed=(chunk_idx + 1) * BATCH_SIZE)

            # 进度报告
            if (chunk_idx + 1) % PROGRESS_INTERVAL == 0 or chunk_idx == len(chunks) - 1:
                processed = min((chunk_idx + 1) * BATCH_SIZE, total)
                pct = processed / total * 100
                elapsed = time.time() - svc_start
                rate = processed / elapsed if elapsed > 0 else 0
                log(f"  {svc}: {processed:,}/{total:,} ({pct:.1f}%) | "
                    f"{rate:.0f} seq/s | {elapsed:.0f}s")

        await client.close()

        # 完成
        db.set_checkpoint(CHECKPOINT_PREFIX, svc, "done",
                          total=total, processed=total)
        svc_elapsed = time.time() - svc_start
        log(f"  {svc}: ✅ 完成 ({svc_elapsed:.0f}s)")

    # ── 4. 汇总 ──
    log("\n" + "=" * 55)
    log("  预打分汇总:")
    for svc in SERVICE_ORDER:
        cp = db.get_checkpoint(f"{CHECKPOINT_PREFIX}_{svc}")
        status = "✅" if cp and cp["status"] == "done" else "⏳"
        processed = f"{cp['processed_items']:,}" if cp else "0"
        log(f"  {status} {svc}: {processed}")
    scored = db.get_last_processed_id("round3_scores")
    log(f"  round3_scores 总计: {scored:,} 条")
    log("=" * 55)

    db.close()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Round 3 预打分（GPU 空闲时提前计算）")
    parser.add_argument("--services", type=str, default=None,
                        help="服务列表，逗号分隔 (default: 全部)")
    parser.add_argument("--resume", action="store_true",
                        help="恢复模式：跳过已完成的服务")
    parser.add_argument("--status", action="store_true",
                        help="仅显示预打分状态")
    args = parser.parse_args()

    # 快速状态查询（不启动 asyncio）
    if args.status:
        db = PipelineDB()
        db.connect()
        print_status(db)
        db.close()
        return

    services = args.services.split(",") if args.services else None

    log(f"Round 3 预打分")
    log(f"服务顺序: {services or SERVICE_ORDER}")
    log(f"恢复模式: {'开' if args.resume else '关'}")

    asyncio.run(run(services, resume=args.resume))


if __name__ == "__main__":
    main()
