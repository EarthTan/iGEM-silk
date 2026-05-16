"""
步骤零：数据整合

合并 function_1 / function_2 / function_3 全量抗氧化肽数据，
去重、长度过滤 (3-30 aa)、标准氨基酸清洗。

用法：
    uv run python -m main.stages2.step00_integrate

输出：
    output/step00_integrate/
    ├── README.md              ← 数据统计报告（含分布直方图）
    ├── run.log
    ├── final/cleaned.csv      ← 清洗后的全量抗氧化肽
    └── stats.json             ← 程序化统计摘要（供后续阶段读取）
"""

from __future__ import annotations

import csv
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "output"

sys.path.insert(0, str(PROJECT_ROOT))

STAGE = "step00_integrate"
STAGE_DIR = OUTPUT_DIR / STAGE

LOG_FILE: Path | None = None

# ── 标准氨基酸 ──
STD_AA = re.compile(r"^[ACDEFGHIKLMNPQRSTVWY]+$", re.IGNORECASE)
LEN_MIN = 3
LEN_MAX = 30


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


# ═══════════════════════════════════════════════════════════════════════
# 分布统计（每阶段通用）
# ═══════════════════════════════════════════════════════════════════════

def describe(name: str, values: list[float], bins: list[float] | None = None) -> str:
    """生成统一格式的分布报告。

    - name: 变量名（如 "综合分"、"AnOxPePred"）
    - values: 数值列表
    - bins: 分箱边界，如 [0, 0.1, 0.2, ..., 1.0]。None 则按数据范围自动分 8 箱
    """
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
        f"  分布直方图:",
    ]

    # 自动分箱
    if bins is None:
        vmin = sorted_v[0]
        vmax = sorted_v[-1]
        if vmax - vmin < 0.001:
            lines.append(f"  所有值 ≈ {vmin:.4f}，无分布")
            return "\n".join(lines)
        raw_bins = 8
        bin_width = (vmax - vmin) / raw_bins
        bins = [vmin + bin_width * i for i in range(raw_bins + 1)]

    bar_width = 14  # 字符宽度
    for i in range(len(bins) - 1):
        lo = bins[i]
        hi = bins[i + 1]
        count = sum(1 for v in values if lo <= v < hi)
        pct = count / n * 100
        filled = round(count / n * bar_width) if n > 0 else 0
        bar = "█" * filled + "░" * (bar_width - filled)

        marker = "← 均值" if lo <= mean < hi else ""
        lines.append(f"  {lo:.4f}-{hi:.4f}: {bar}  ({count:,} 条, {pct:.1f}%) {marker}")

    lines.append("")
    return "\n".join(lines)


def histogram_counts(values: list[float], num_bins: int = 8) -> tuple[list[float], list[int]]:
    """将数值分箱，返回 (bin_edges, counts)。"""
    vmin = min(values)
    vmax = max(values)
    if vmax - vmin < 0.001:
        return [vmin, vmax + 0.1], [len(values)]
    bin_width = (vmax - vmin) / num_bins
    edges = [vmin + bin_width * i for i in range(num_bins + 1)]
    counts = []
    for i in range(num_bins):
        lo = edges[i]
        hi = edges[i + 1]
        counts.append(sum(1 for v in values if lo <= v < hi))
    # 确保最大值被包含
    counts[-1] += sum(1 for v in values if v == edges[-1])
    return edges, counts


# ═══════════════════════════════════════════════════════════════════════
# 加载函数
# ═══════════════════════════════════════════════════════════════════════

def load_function_csv(path: Path) -> list[dict]:
    """加载一个 function CSV 文件，返回行字典列表。"""
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    log(f"  加载 {path.name}: {len(rows)} 行")
    return rows


def is_antioxidant(row: dict) -> bool:
    """检查行是否为抗氧化肽。"""
    return row.get("is_antioxidant", "").strip() == "1"


def clean_sequence(seq: str) -> str | None:
    """标准化并验证序列，返回大写标准序列或 None。"""
    s = seq.upper().strip()
    if not STD_AA.match(s):
        return None
    if not (LEN_MIN <= len(s) <= LEN_MAX):
        return None
    return s


# ═══════════════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════════════

def run():
    global LOG_FILE
    start_time = time.time()

    # ── 创建输出目录 ──
    STAGE_DIR.mkdir(parents=True, exist_ok=True)
    LOG_FILE = STAGE_DIR / "run.log"
    log("=" * 60)
    log("步骤零：数据整合")
    log("=" * 60)

    # ══════════════════════════════════════════════════════════════════
    # 1. 加载数据
    # ══════════════════════════════════════════════════════════════════
    log("\n📦 加载原始数据...")

    f1_path = DATA_DIR / "function_1.csv"
    f2_path = DATA_DIR / "function_2.csv"
    f3_path = DATA_DIR / "function_3.csv"

    if not f1_path.exists():
        log(f"❌ 找不到 {f1_path}")
        return
    if not f2_path.exists():
        log(f"❌ 找不到 {f2_path}")
        return

    raw1 = load_function_csv(f1_path)
    raw2 = load_function_csv(f2_path)
    raw3 = load_function_csv(f3_path) if f3_path.exists() else []

    # ══════════════════════════════════════════════════════════════════
    # 2. 筛选抗氧化肽
    # ══════════════════════════════════════════════════════════════════
    log("\n🔍 筛选抗氧化肽 (is_antioxidant=1)...")
    aox1 = [r for r in raw1 if is_antioxidant(r)]
    aox2 = [r for r in raw2 if is_antioxidant(r)]
    aox3 = [r for r in raw3 if is_antioxidant(r)]
    log(f"  function_1: {len(raw1)} → {len(aox1)} 抗氧化")
    log(f"  function_2: {len(raw2)} → {len(aox2)} 抗氧化")
    log(f"  function_3: {len(raw3)} → {len(aox3)} 抗氧化")

    total_aox = len(aox1) + len(aox2) + len(aox3)
    log(f"  抗氧化合计: {total_aox:,} 条")

    # ══════════════════════════════════════════════════════════════════
    # 3. 合并、清洗、去重
    # ══════════════════════════════════════════════════════════════════
    log("\n🧹 清洗 & 去重...")

    length_stats: dict[str, int] = {"too_short": 0, "too_long": 0, "valid": 0}
    non_std_count = 0

    seen_sequences: set[str] = set()
    cleaned: list[dict] = []

    for source, rows in [("function_1", aox1), ("function_2", aox2), ("function_3", aox3)]:
        for row in rows:
            seq = clean_sequence(row["sequence"])
            if seq is None:
                raw_seq = row["sequence"].upper().strip()
                if not STD_AA.match(raw_seq):
                    non_std_count += 1
                elif len(raw_seq) < LEN_MIN:
                    length_stats["too_short"] += 1
                elif len(raw_seq) > LEN_MAX:
                    length_stats["too_long"] += 1
                continue

            length_stats["valid"] += 1

            if seq not in seen_sequences:
                seen_sequences.add(seq)
                cleaned.append({
                    "peptide_id": "",  # 稍后分配
                    "sequence": seq,
                    "length": len(seq),
                    "source": source,
                })

    log(f"  非标准氨基酸: {non_std_count}")
    log(f"  过短 (<{LEN_MIN}aa): {length_stats['too_short']}")
    log(f"  过长 (>{LEN_MAX}aa): {length_stats['too_long']}")
    log(f"  合法序列: {length_stats['valid']:,}")
    log(f"  去重后: {len(cleaned):,}")

    # 分配 peptide_id
    for i, c in enumerate(cleaned):
        c["peptide_id"] = f"pep_{i:06d}"

    # ══════════════════════════════════════════════════════════════════
    # 4. 长度分布统计
    # ══════════════════════════════════════════════════════════════════
    log("\n📊 长度分布:")
    lengths = [c["length"] for c in cleaned]
    edges, counts = histogram_counts(lengths, num_bins=8)
    len_report = describe("肽长度", lengths)
    for line in len_report.split("\n"):
        log(line)

    # ══════════════════════════════════════════════════════════════════
    # 5. 输出
    # ══════════════════════════════════════════════════════════════════
    final_dir = make_dir("final")
    csv_path = final_dir / "cleaned.csv"

    fieldnames = ["peptide_id", "sequence", "length", "source"]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(cleaned)
    log(f"\n✅ 已写入: {csv_path} ({len(cleaned):,} 条)")

    # 统计摘要
    elapsed = time.time() - start_time
    stats = {
        "stage": STAGE,
        "timestamp": datetime.now().isoformat(),
        "elapsed_sec": round(elapsed, 1),
        "input": {
            "function_1": len(raw1),
            "function_2": len(raw2),
            "function_3": len(raw3),
        },
        "filtering": {
            "total_antioxidant": total_aox,
            "non_standard_aa": non_std_count,
            f"too_short_<{LEN_MIN}aa": length_stats["too_short"],
            f"too_long_>{LEN_MAX}aa": length_stats["too_long"],
            "valid_sequences": length_stats["valid"],
            "after_dedup": len(cleaned),
        },
        "output": {
            "path": str(csv_path),
            "n_peptides": len(cleaned),
            "length_range": [min(lengths), max(lengths)],
            "length_mean": round(sum(lengths) / len(lengths), 2) if lengths else 0,
        },
    }
    write_json(STAGE_DIR / "stats.json", stats)

    # ══════════════════════════════════════════════════════════════════
    # 6. README
    # ══════════════════════════════════════════════════════════════════
    len_distro_lines = describe("肽长度", lengths)

    readme = f"""# 步骤零：数据整合 — 报告

**时间**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**耗时**: {elapsed:.1f} 秒

## 数据源

| 文件 | 总行数 | 抗氧化子集 |
|------|--------|-----------|
| function_1.csv | {len(raw1):,} | {len(aox1):,} |
| function_2.csv | {len(raw2):,} | {len(aox2):,} |
| function_3.csv | {len(raw3):,} | {len(aox3):,} |

## 清洗流程

```
原始抗氧化合计: {total_aox:,}
  ├─ 非标准氨基酸:    {non_std_count} 条
  ├─ 过短 (<{LEN_MIN}aa):   {length_stats['too_short']} 条
  ├─ 过长 (>{LEN_MAX}aa):   {length_stats['too_long']} 条
  ├─ 合法序列:        {length_stats['valid']:,} 条
  └─ 去重后:          {len(cleaned):,} 条
```

## 长度分布

```
{len_distro_lines}
```

## 输出

- `final/cleaned.csv` — {len(cleaned):,} 条抗氧化肽（含 peptide_id、sequence、length、source）

## 下一步

Round 1（轻量评分），输入: `{csv_path}`
"""

    readme_path = STAGE_DIR / "README.md"
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(readme)
    log(f"报告已写入: {readme_path}")
    log(f"\n✅ 步骤零完成！耗时: {elapsed:.1f}s")
    log(f"  输出: {len(cleaned):,} 条抗氧化肽 → Round 1")


def main():
    run()


if __name__ == "__main__":
    main()
