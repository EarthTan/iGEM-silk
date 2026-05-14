"""
Round 2：中等评分

在 Top 100,000 条候选肽上运行 3 个追加服务：
  - ToxinPred3（毒性反向，权重 0.15，瓶颈 ~12 seq/s）
  - HemoPI2（溶血反向，权重 0.10，~69 seq/s GPU）
  - MHCflurry（MHC-I 反向，权重 0.05，~210 seq/s GPU）

合并 Round 1 的 AnOxPePred + AlgPred2 分数，用 5 服务权重重算综合分，
取 Top 10,000 进入 Round 3。

用法：
    uv run python -m main.stages2.round02_scoring

输入：
    output/round01_lightweight/final/top100k.csv

输出：
    output/round02_scoring/
    ├── README.md              ← 分布报告 + Top/Bottom 展示
    ├── run.log
    ├── scores/                ← 各服务原始返回（JSON）
    ├── final/
    │   ├── top10k.csv         ← Top 10,000 肽（含综合分 + 安全标记）
    │   ├── all_scored.csv     ← 全部 100K 评分明细
    │   └── danger_list.csv    ← 🔴 高危肽清单
    └── stats.json             ← 程序化统计摘要
"""

from __future__ import annotations

import asyncio
import csv
import json
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

OUTPUT_DIR = PROJECT_ROOT / "output"
STAGE = "round02_scoring"
STAGE_DIR = OUTPUT_DIR / STAGE

from main.client import ServiceClient

LOG_FILE: Path | None = None
MAX_BATCH_SIZE = 1000
CONCURRENT_CHUNKS = 10

# ── Round 2 新增服务 ──
# ToxinPred3 从 Round 1 移到这里（吞吐仅 ~12 seq/s）
NEW_SERVICES = [
    ("toxinpred3",  0.15, True,  "毒性（反向，越低越好）"),
    ("hemopi2",     0.10, True,  "溶血（反向，越低越好）"),
    ("mhcflurry",   0.05, True,  "MHC-I 结合（反向，越低越好）"),
]

# ── 完整 5 服务权重（含 Round 1 已有的）──
ALL_WEIGHTS = {
    "anoxpepred":  0.50,
    "toxinpred3":  0.15,
    "algpred2":    0.10,
    "hemopi2":     0.10,
    "mhcflurry":   0.05,
}
# 所有权重总和 = 0.90，脚本中会按实际存在的分数动态归一化

SAFETY_THRESHOLDS = {
    "toxinpred3": {"caution": 0.60, "danger": 0.80},
    "algpred2":   {"caution": 0.50, "danger": 0.70},
    "hemopi2":    {"caution": 0.70, "danger": 0.85},
}

TOP_N = 10000
ROUND1_INPUT = OUTPUT_DIR / "round01_lightweight" / "final" / "top100k.csv"


# ═══════════════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════════════

def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    if LOG_FILE:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def make_dir(name: str) -> Path:
    d = STAGE_DIR / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_json(path: Path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def describe(name: str, values: list[float]) -> str:
    n = len(values)
    if n == 0:
        return f"{name}: 无有效数据"
    sorted_v = sorted(values)
    mean = sum(sorted_v) / n
    median = sorted_v[n // 2] if n % 2 == 1 else (sorted_v[n // 2 - 1] + sorted_v[n // 2]) / 2
    variance = sum((x - mean) ** 2 for x in sorted_v) / n
    std = variance ** 0.5
    p5 = sorted_v[int(n * 0.05)]
    p25 = sorted_v[int(n * 0.25)]
    p75 = sorted_v[int(n * 0.75)]
    p95 = sorted_v[int(n * 0.95)]
    lines = [
        f"{name} 分布 (n={n}):",
        f"  均值:   {mean:.4f}",
        f"  中位数: {median:.4f}",
        f"  标准差: {std:.4f}",
        f"  最小值: {sorted_v[0]:.4f}",
        f"  最大值: {sorted_v[-1]:.4f}",
        f"  P5: {p5:.4f}  |  P25: {p25:.4f}  |  P75: {p75:.4f}  |  P95: {p95:.4f}",
        "",
        "  分布直方图:",
    ]
    vmin = sorted_v[0]
    vmax = sorted_v[-1]
    if vmax - vmin < 0.001:
        lines.append(f"  所有值 ≈ {vmin:.4f}，无分布")
        return "\n".join(lines)
    raw_bins = 8
    bin_width = (vmax - vmin) / raw_bins
    bins = [vmin + bin_width * i for i in range(raw_bins + 1)]
    for i in range(len(bins) - 1):
        lo = bins[i]
        hi = bins[i + 1]
        count = sum(1 for v in values if lo <= v < hi)
        pct = count / n * 100
        filled = round(count / n * 14)
        bar = "█" * filled + "░" * (14 - filled)
        marker = "  ← 均值" if lo <= mean < hi else ""
        lines.append(f"  {lo:.4f}-{hi:.4f}: {bar}  ({count:,} 条, {pct:.1f}%){marker}")
    lines.append("")
    return "\n".join(lines)


def calc_safety_flag(peptide: dict) -> str:
    flags = []
    for svc_name, cfg in SAFETY_THRESHOLDS.items():
        score = peptide.get(svc_name)
        if score is None:
            continue
        if score >= cfg["danger"]:
            flags.append(f"{svc_name}:danger({score:.3f})")
        elif score >= cfg["caution"]:
            flags.append(f"{svc_name}:caution({score:.3f})")
    return ";".join(flags) if flags else "safe"


# ═══════════════════════════════════════════════════════════════════════
# 并发批处理
# ═══════════════════════════════════════════════════════════════════════

async def process_service(
    client: ServiceClient,
    service_name: str,
    chunks: list[list[dict]],
) -> dict[str, dict]:
    sem = asyncio.Semaphore(CONCURRENT_CHUNKS)
    all_results: dict[str, dict] = {}
    errors = 0
    total = sum(len(c) for c in chunks)

    async def process_chunk(chunk: list[dict]) -> None:
        nonlocal errors
        async with sem:
            result = await client.predict_batch(service_name, chunk)
            if result.get("success") and result.get("results"):
                for r in result["results"]:
                    pid = r.get("peptide_id", "unknown")
                    all_results[pid] = {
                        "score": r.get("score"),
                        "label": r.get("label", ""),
                    }
            else:
                errors += 1
                for item in chunk:
                    pid = item.get("peptide_id", "unknown")
                    all_results[pid] = {"score": None, "label": "SERVICE_ERROR"}

    tasks = [process_chunk(chunk) for chunk in chunks]
    batch_size = 50
    for i in range(0, len(tasks), batch_size):
        batch = tasks[i:i + batch_size]
        await asyncio.gather(*batch)
        progress = min((i + batch_size) * MAX_BATCH_SIZE, total)
        log(f"  {service_name}: {progress:,}/{total:,} ({progress/total*100:.0f}%) | errors={errors}")

    log(f"  ✅ {service_name}: {total:,} 完成, {errors} 批次错误")
    return all_results


# ═══════════════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════════════

async def run():
    global LOG_FILE
    start_time = time.time()

    STAGE_DIR.mkdir(parents=True, exist_ok=True)
    LOG_FILE = STAGE_DIR / "run.log"
    log("=" * 60)
    log("Round 2：中等评分 — ToxinPred3 + HemoPI2 + MHCflurry")
    log("=" * 60)

    # ── 加载 Round 1 Top 100K ──
    if not ROUND1_INPUT.exists():
        log(f"输入不存在: {ROUND1_INPUT}")
        log("请先运行: uv run python -m main.stages2.round01_lightweight")
        return

    peptides: list[dict] = []
    with open(ROUND1_INPUT, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # 转换数值字段
            row["anoxpepred"] = float(row["anoxpepred"]) if row.get("anoxpepred") else None
            row["algpred2"] = float(row["algpred2"]) if row.get("algpred2") else None
            row["weighted_score"] = float(row["weighted_score"]) if row.get("weighted_score") else None
            row["length"] = int(row["length"])
            peptides.append(row)

    total = len(peptides)
    log(f"\n输入: {total:,} 条 (Round 1 Top 100K)")

    # ── 分块 ──
    chunks: list[list[dict]] = []
    for i in range(0, total, MAX_BATCH_SIZE):
        chunk = peptides[i:i + MAX_BATCH_SIZE]
        chunks.append([{"sequence": p["sequence"], "peptide_id": p["peptide_id"]} for p in chunk])
    log(f"分块: {len(chunks)} 批 (≤{MAX_BATCH_SIZE}/批)")

    # ── 客户端 ──
    client = ServiceClient(timeout=300.0)

    # ══════════════════════════════════════════════════════════════════
    # 并发调用 3 个新服务
    # ══════════════════════════════════════════════════════════════════
    svc_names = [s[0] for s in NEW_SERVICES]
    log(f"\n新服务: {', '.join(svc_names)} ({len(chunks)} 批, 并发 {CONCURRENT_CHUNKS})")
    log("注意: ToxinPred3 吞吐仅 ~12 seq/s，100K 条预计 ~2.3 小时")

    async def run_one(svc_name: str, weight: float, reverse: bool, desc: str):
        log(f"\n{svc_name} ({desc})")
        t0 = time.time()
        results = await process_service(client, svc_name, chunks)
        elapsed = time.time() - t0
        n_valid = sum(1 for v in results.values() if v["score"] is not None)
        rate = n_valid / elapsed if elapsed > 0 else 0
        log(f"  {svc_name}: {elapsed:.0f}s, {n_valid}/{len(results)} 有效 ({rate:.0f} seq/s)")
        return svc_name, results, weight, reverse

    tasks = [run_one(svc, w, r, d) for svc, w, r, d in NEW_SERVICES]
    completed = await asyncio.gather(*tasks)
    new_results: dict[str, dict[str, dict]] = {svc: res for svc, res, _, _ in completed}

    await client.close()

    # ── 保存原始返回 ──
    scores_dir = make_dir("scores")
    for svc_name in new_results:
        write_json(scores_dir / f"{svc_name}_results.json", new_results[svc_name])

    # ══════════════════════════════════════════════════════════════════
    # 合并分数，用 5 服务权重重算综合分
    # ══════════════════════════════════════════════════════════════════
    log(f"\n合并分数 & 重算综合分...")

    all_services = list(ALL_WEIGHTS.keys())  # 5 服务
    scored_peptides: list[dict] = []
    for pep in peptides:
        pid = pep["peptide_id"]
        row = {
            "peptide_id": pid,
            "sequence": pep["sequence"],
            "length": pep["length"],
            "source": pep["source"],
        }

        # 保留 Round 1 分数
        row["anoxpepred"] = pep.get("anoxpepred")
        row["algpred2"] = pep.get("algpred2")

        weighted_sum = 0.0
        total_weight = 0.0
        missing_svc = []

        for svc_name in all_services:
            weight = ALL_WEIGHTS[svc_name]
            reverse = svc_name in ("toxinpred3", "algpred2", "hemopi2", "mhcflurry")

            # 取分数：新服务从 new_results，旧服务从 pep
            if svc_name in new_results:
                svc_data = new_results[svc_name].get(pid, {})
                raw_score = svc_data.get("score")
                row[svc_name] = raw_score
            elif svc_name in pep and pep[svc_name] is not None:
                raw_score = pep[svc_name]
                # row[svc_name] 已设
            else:
                raw_score = None

            if raw_score is None:
                if svc_name not in row or row[svc_name] is None:
                    missing_svc.append(svc_name)
                continue

            normalized = max(0.0, min(1.0, raw_score))
            row[f"{svc_name}_raw_norm"] = round(normalized, 4)
            if reverse:
                normalized = 1.0 - normalized
            weighted_sum += normalized * weight
            total_weight += weight

        if missing_svc:
            row["missing_services"] = ";".join(missing_svc)

        row["weighted_score"] = round(weighted_sum / total_weight, 4) if total_weight > 0 else None
        row["safety_flag"] = calc_safety_flag(row)
        scored_peptides.append(row)

    n_valid = sum(1 for p in scored_peptides if p["weighted_score"] is not None)
    log(f"  完成: {n_valid:,}/{len(scored_peptides):,} 有效评分")

    # ── 排序 + 输出 ──
    log(f"\n排序...")
    scored_peptides.sort(key=lambda x: (x["weighted_score"] or 0), reverse=True)

    final_dir = make_dir("final")
    fieldnames = ["peptide_id", "sequence", "length", "source",
                  "anoxpepred", "toxinpred3", "algpred2", "hemopi2", "mhcflurry",
                  "weighted_score", "safety_flag"]

    # 全部
    all_path = final_dir / "all_scored.csv"
    with open(all_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(scored_peptides)

    # Top N
    n_top = min(TOP_N, len(scored_peptides))
    top_peptides = scored_peptides[:n_top]
    top_path = final_dir / "top10k.csv"
    with open(top_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(top_peptides)
    log(f"Top {n_top:,}: {top_path}")

    # 高危
    danger_list = [p for p in scored_peptides if "danger" in p.get("safety_flag", "")]
    danger_path = final_dir / "danger_list.csv"
    with open(danger_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(danger_list)
    log(f"高危清单: {danger_path} ({len(danger_list)} 条)")

    # ══════════════════════════════════════════════════════════════════
    # 统计报告
    # ══════════════════════════════════════════════════════════════════
    total_elapsed = time.time() - start_time
    valid_scores = [p["weighted_score"] for p in scored_peptides if p["weighted_score"] is not None]

    all_reports = [describe("综合分", valid_scores)]
    for svc_name in all_services:
        vals = [p[svc_name] for p in scored_peptides if p.get(svc_name) is not None]
        if vals:
            all_reports.append(describe(svc_name, vals))
    full_distro = "\n".join(all_reports)

    n_safe = sum(1 for p in scored_peptides if p.get("safety_flag") == "safe")
    n_caution = sum(1 for p in scored_peptides if "caution" in p.get("safety_flag", ""))
    n_danger = len(danger_list)
    n_missing = sum(1 for p in scored_peptides if p.get("missing_services"))

    # Top 10
    top10_lines = [f"| {p['peptide_id']} | {p['sequence'][:25]:25s} | {p['length']} | {p['weighted_score']:.4f} | {p.get('safety_flag','safe')} |"
                   for p in scored_peptides[:10]]
    # Bottom 10
    bottom_valid = [p for p in scored_peptides if p["weighted_score"] is not None]
    bottom10_lines = [f"| {p['peptide_id']} | {p['sequence'][:25]:25s} | {p['length']} | {p['weighted_score']:.4f} | {p.get('safety_flag','safe')} |"
                      for p in reversed(bottom_valid[-10:])]

    # 统计
    stats = {
        "stage": STAGE,
        "timestamp": datetime.now().isoformat(),
        "elapsed_sec": round(total_elapsed, 1),
        "input": total,
        "new_services": {s[0]: {"weight": s[1], "reverse": s[2], "desc": s[3]} for s in NEW_SERVICES},
        "all_weights": ALL_WEIGHTS,
        "scoring": {"n_valid": len(valid_scores),
                     "mean": round(sum(valid_scores)/len(valid_scores), 4) if valid_scores else None,
                     "top_n": n_top},
        "safety": {"safe": n_safe, "caution": n_caution, "danger": n_danger, "missing": n_missing},
    }
    write_json(STAGE_DIR / "stats.json", stats)

    # ── README ──
    readme = f"""# Round 2：中等评分 — 报告

**时间**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**耗时**: {total_elapsed:.0f} 秒
**输入**: {total:,} 条肽（Round 1 Top 100K）

## 评分服务（5 服务）

| 服务 | 权重 | 方向 | 有效 |
|------|------|------|------|
| AnOxPePred | 0.50 | 正向 | {sum(1 for p in scored_peptides if p.get('anoxpepred') is not None):,} |
| ToxinPred3 | 0.15 | 反向 | {sum(1 for p in scored_peptides if p.get('toxinpred3') is not None):,} |
| AlgPred2 | 0.10 | 反向 | {sum(1 for p in scored_peptides if p.get('algpred2') is not None):,} |
| HemoPI2 | 0.10 | 反向 | {sum(1 for p in scored_peptides if p.get('hemopi2') is not None):,} |
| MHCflurry | 0.05 | 反向 | {sum(1 for p in scored_peptides if p.get('mhcflurry') is not None):,} |

## 综合分分布

```
{full_distro}
```

## 安全标记

| 级别 | 数量 | 占比 |
|------|------|------|
| 正常 | {n_safe:,} | {n_safe/max(len(scored_peptides),1)*100:.1f}% |
| 注意 | {n_caution:,} | {n_caution/max(len(scored_peptides),1)*100:.1f}% |
| 高危 | {n_danger:,} | {n_danger/max(len(scored_peptides),1)*100:.1f}% |
| 数据缺失 | {n_missing:,} | {n_missing/max(len(scored_peptides),1)*100:.1f}% |

## Top 10

| ID | 序列 | 长度 | 综合分 | 安全 |
|----|------|------|--------|------|
{chr(10).join(top10_lines)}

## Bottom 10

| ID | 序列 | 长度 | 综合分 | 安全 |
|----|------|------|--------|------|
{chr(10).join(bottom10_lines)}

## 输出

- `final/top10k.csv` — Top {n_top:,} 条 → Round 3
- `final/all_scored.csv` — 全部 {len(scored_peptides):,} 条
- `final/danger_list.csv` — 高危 {len(danger_list)} 条
"""
    readme_path = STAGE_DIR / "README.md"
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(readme)
    log(f"\n报告: {readme_path}")
    log(f"\n{'='*60}")
    log(f"Round 2 汇总")
    log(f"  输入: {total:,} 条 | Top: {n_top:,}")
    if valid_scores:
        log(f"  综合分: mean={sum(valid_scores)/len(valid_scores):.4f}, max={max(valid_scores):.4f}")
    log(f"  安全: {n_safe:,} / {n_caution:,} / {n_danger:,}")
    log(f"  耗时: {total_elapsed:.0f}s")
    log(f"{'='*60}")


def main():
    asyncio.run(run())


if __name__ == "__main__":
    main()
