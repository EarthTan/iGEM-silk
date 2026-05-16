"""
Stage 0: 数据预处理

从两个原始 FASTA（UniProt 102G + MGnify 120G）中提取短肽，
经过长度筛选、标准氨基酸过滤、精确去重后写入 DuckDB。

流程:
  1. 扫描 UniProt FASTA → 3-30aa + 标准 AA → 批量写入 candidates 表
  2. 扫描 MGnify FASTA → 3-30aa + 标准 AA → 批量写入 candidates 表
  3. 生成数据统计报告

用法:
    uv run python -m main.stages3.stage00_preprocess

输出:
    output3/pipeline.db 的 candidates 表
    output3/reports/stage0_report.md (数据统计报告)
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# 确保可以从项目根目录 import
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from main.stages3.db import PipelineDB, DEFAULT_DB_PATH
from main.stages3.fasta_parser import fasta_iter_lines, is_standard_aa, STANDARD_AA_RE

# ────────────────────────────────────────────────────────────────
# 配置
# ────────────────────────────────────────────────────────────────

# 可以从环境变量覆盖
UNIPROT_FASTA = "/home/lenovo/public_databases/uniprot_all_2021_04.fa"
MGY_FASTA = "/home/lenovo/public_databases/mgy_clusters_2022_05.fa"

MIN_LEN = 3
MAX_LEN = 30
BATCH_SIZE = 100_000  # 每批写入 DB 的条数
PROGRESS_INTERVAL = 1_000_000  # 每扫多少条打印一次进度


def parse_uniprot_header(header: str) -> tuple[str, str]:
    """解析 UniProt FASTA header，返回 (source_id, full_header)。

    >sp|P48347-2|14310_ARATH Description OS=... → P48347-2
    >tr|A0A0B4J2V0|A0A0B4J2V0_DROME Description → A0A0B4J2V0
    """
    parts = header.split("|")
    if len(parts) >= 2:
        source_id = parts[1]
    else:
        source_id = header.split()[0].lstrip(">")
    return source_id, header


def parse_mgy_header(header: str) -> tuple[str, str]:
    """解析 MGnify FASTA header，返回 (source_id, full_header)。

    >MGYP000000077819 → MGYP000000077819
    >MGYP000000184299 FL=1 → MGYP000000184299
    """
    source_id = header.split()[0].lstrip(">")
    return source_id, header


def process_fasta(
    fasta_path: str,
    source: str,
    parse_header_fn,
    db: PipelineDB,
    max_sequences: int | None = None,
) -> dict:
    """
    扫描单个 FASTA 文件，提取 3-30aa + 标准 AA 序列写入数据库。

    返回处理统计。
    """
    stats = {
        "source": source,
        "path": fasta_path,
        "total_scanned": 0,
        "length_passed": 0,
        "aa_passed": 0,
        "written": 0,
        "duplicates_skipped": 0,
        "elapsed": 0.0,
    }

    batch: list[dict] = []
    start = time.monotonic()

    for header, seq in fasta_iter_lines(fasta_path):
        stats["total_scanned"] += 1

        # 进度报告
        if stats["total_scanned"] % PROGRESS_INTERVAL == 0:
            elapsed = time.monotonic() - start
            rate = stats["total_scanned"] / elapsed if elapsed > 0 else 0
            in_batch = len(batch)
            print(f"  [{source}] {stats['total_scanned']:,} 条扫描, "
                  f"{stats['written']:,} 条写入 (+{in_batch} 待写), "
                  f"速度 {rate:.0f} 条/秒, 耗时 {elapsed:.0f}s")

        # 长度筛选
        seq_clean = seq.replace("\n", "").replace(" ", "").upper()
        seq_len = len(seq_clean)
        if seq_len < MIN_LEN or seq_len > MAX_LEN:
            continue
        stats["length_passed"] += 1

        # 标准 AA 筛选
        if not STANDARD_AA_RE.match(seq_clean):
            continue
        stats["aa_passed"] += 1

        # 解析 header
        source_id, full_header = parse_header_fn(header)

        batch.append({
            "source": source,
            "source_id": source_id,
            "header": full_header,
            "sequence": seq_clean,
            "length": seq_len,
            "is_standard_aa": True,
        })

        # 批量写入
        if len(batch) >= BATCH_SIZE:
            written = db.insert_candidates(batch)
            stats["written"] += written
            stats["duplicates_skipped"] += len(batch) - written
            batch = []

        if max_sequences and len(batch) >= max_sequences:
            # 抽样模式：收集够了就停
            written = db.insert_candidates(batch)
            stats["written"] += written
            batch = []
            break

    # 最后一批
    if batch:
        written = db.insert_candidates(batch)
        stats["written"] += written
        stats["duplicates_skipped"] += len(batch) - written

    stats["elapsed"] = time.monotonic() - start
    return stats


def generate_report(uniprot_stats: dict, mgy_stats: dict, db: PipelineDB) -> str:
    """生成数据统计报告。"""
    total = db.row_count("candidates")

    # 按来源统计
    conn = db.connect()
    source_counts = conn.execute("""
        SELECT source, COUNT(*), MIN(length), MAX(length), AVG(length)
        FROM candidates GROUP BY source
    """).fetchall()

    # 长度分布
    length_dist = conn.execute("""
        SELECT length, COUNT(*) FROM candidates
        GROUP BY length ORDER BY length
    """).fetchall()

    lines = [
        "# Stage 0 预处理报告",
        "",
        f"> 生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## 概要",
        "",
        f"| 指标 | 值 |",
        f"|------|-----|",
        f"| 候选池总数 | {total:,} |",
        f"| UniProt 扫描 | {uniprot_stats['total_scanned']:,} 条 |",
        f"| UniProt 写入 | {uniprot_stats['written']:,} 条 |",
        f"| MGnify 扫描 | {mgy_stats['total_scanned']:,} 条 |",
        f"| MGnify 写入 | {mgy_stats['written']:,} 条 |",
        f"| 总耗时 | {uniprot_stats['elapsed'] + mgy_stats['elapsed']:.0f}s |",
        f"| 筛选范围 | {MIN_LEN}-{MAX_LEN} aa |",
        "",
        "## 各数据源统计",
        "",
        "| Source | 条目数 | 最小长度 | 最大长度 | 平均长度 |",
        "|--------|--------|---------|---------|---------|",
    ]
    for src, cnt, mn, mx, avg in source_counts:
        lines.append(f"| {src} | {cnt:,} | {mn} | {mx} | {avg:.1f} |")

    lines.extend([
        "",
        "## 长度分布",
        "",
        "| 长度 | 数量 |",
        "|------|------|",
    ])
    for ln, cnt in length_dist:
        bar = "█" * max(1, cnt // max(1, (max(r[1] for r in length_dist) // 40)))
        lines.append(f"| {ln} | {cnt:,} {bar} |")

    lines.extend([
        "",
        "## 预筛选详情",
        "",
        "| 阶段 | 数量 |",
        "|------|------|",
        f"| UniProt 原始序列 | {uniprot_stats['total_scanned']:,} |",
        f"| UniProt 长度通过 (3-30aa) | {uniprot_stats['length_passed']:,} |",
        f"| UniProt AA 通过 | {uniprot_stats['aa_passed']:,} |",
        f"| UniProt 去重后写入 | {uniprot_stats['written']:,} |",
        f"| UniProt 重复跳过 | {uniprot_stats['duplicates_skipped']:,} |",
        f"| MGnify 原始序列 | {mgy_stats['total_scanned']:,} |",
        f"| MGnify 长度通过 (3-30aa) | {mgy_stats['length_passed']:,} |",
        f"| MGnify AA 通过 | {mgy_stats['aa_passed']:,} |",
        f"| MGnify 去重后写入 | {mgy_stats['written']:,} |",
        f"| MGnify 重复跳过 | {mgy_stats['duplicates_skipped']:,} |",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Stage 0: 数据预处理 — 从原始 FASTA 提取短肽到 DuckDB")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH),
                        help=f"DuckDB 路径（默认 {DEFAULT_DB_PATH}）")
    parser.add_argument("--uniprot", default=UNIPROT_FASTA,
                        help="UniProt FASTA 路径")
    parser.add_argument("--mgy", default=MGY_FASTA,
                        help="MGnify FASTA 路径")
    parser.add_argument("--uniprot-only", action="store_true",
                        help="只处理 UniProt")
    parser.add_argument("--mgy-only", action="store_true",
                        help="只处理 MGnify")
    parser.add_argument("--sample", type=int, default=0,
                        help="抽样模式：每个库只处理 N 条（用于测试）")
    args = parser.parse_args()

    max_seq = args.sample if args.sample > 0 else None
    db_path = args.db

    print("=" * 60)
    print("Stage 0: 数据预处理")
    print("=" * 60)

    db = PipelineDB(db_path)
    db.init_schema()

    # 检查断点
    cp = db.get_checkpoint("stage0_uniprot")
    if cp and cp["status"] == "done":
        print("[检查点] UniProt 已完成，跳过")
        uniprot_stats = {"source": "uniprot", "written": 0}
    else:
        print(f"\n[1/2] 处理 UniProt: {args.uniprot}")
        db.set_checkpoint("stage0_uniprot", "scan", "running")
        uniprot_stats = process_fasta(
            args.uniprot, "uniprot", parse_uniprot_header, db, max_seq)
        print(f"  → 写入 {uniprot_stats['written']:,} 条，"
              f"耗时 {uniprot_stats['elapsed']:.0f}s")
        db.set_checkpoint("stage0_uniprot", "scan", "done",
                          total=uniprot_stats["total_scanned"],
                          processed=uniprot_stats["written"])

    if not args.uniprot_only:
        cp = db.get_checkpoint("stage0_mgy")
        if cp and cp["status"] == "done":
            print("[检查点] MGnify 已完成，跳过")
            mgy_stats = {"source": "mgy", "written": 0}
        else:
            print(f"\n[2/2] 处理 MGnify: {args.mgy}")
            db.set_checkpoint("stage0_mgy", "scan", "running")
            mgy_stats = process_fasta(
                args.mgy, "mgy", parse_mgy_header, db, max_seq)
            print(f"  → 写入 {mgy_stats['written']:,} 条，"
                  f"耗时 {mgy_stats['elapsed']:.0f}s")
            db.set_checkpoint("stage0_mgy", "scan", "done",
                              total=mgy_stats["total_scanned"],
                              processed=mgy_stats["written"])
    else:
        mgy_stats = {"source": "mgy", "written": 0, "total_scanned": 0,
                     "length_passed": 0, "aa_passed": 0, "duplicates_skipped": 0,
                     "elapsed": 0}

    # 生成报告
    total = db.row_count("candidates")
    print(f"\n共计写入 {total:,} 条候选肽")

    report = generate_report(uniprot_stats, mgy_stats, db)
    report_path = Path(db_path).parent / "reports" / "stage0_report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report)
    print(f"报告已写入: {report_path}")

    db.set_checkpoint("stage0", "complete", "done",
                      total=total, processed=total)
    print("Stage 0 完成")


if __name__ == "__main__":
    main()
