"""
方差感知权重引擎 (Variance-Aware Weighting Engine)

stages3 的核心创新：先跑分，看分布，再定权。

流程:
  1. 从评分表读取所有有效分数
  2. 计算每个服务的分布统计（均值、标准差、百分位数）
  3. 对标准差做 winsorization（去掉上下 1% 极端值）
  4. 归一化权重: w_i = σ_i_winsorized / Σσ_j_winsorized
  5. 应用权重计算综合得分
  6. 写入 score_distribution + weight_config + 排名表

用法:
    from main.stages3.analytics import compute_variance_weights

    # Stage 2 中，对所有通过者计算权重
    weights = compute_variance_weights(
        db, table="stage2_scores",
        score_columns=["anoxpepred_score", "bepipred3_score", ...],
        stage_name="stage2"
    )
"""

from __future__ import annotations

import json
import math
import time
from datetime import datetime, timezone
from typing import Any

from main.stages3.db import PipelineDB


def winsorized_stddev(values: list[float], tails: float = 0.01) -> float:
    """
    计算 winsorized 标准差。

    将上下 tails（默认 1%）的极端值替换为对应百分位数的值，
    然后计算标准差。这样避免个别离群值扭曲权重分配。

    Args:
        values: 分数列表
        tails: 上下截尾比例（默认 0.01 = 1%）

    Returns:
        winsorized 标准差
    """
    if len(values) < 10:
        # 样本太少时退化为普通标准差
        return statistics_stddev(values)

    n = len(values)
    sorted_vals = sorted(values)
    lower_idx = max(0, int(n * tails))
    upper_idx = min(n - 1, int(n * (1 - tails)) - 1)
    lower_bound = sorted_vals[lower_idx]
    upper_bound = sorted_vals[upper_idx]

    clipped = [max(lower_bound, min(v, upper_bound)) for v in values]
    return statistics_stddev(clipped)


def statistics_stddev(values: list[float]) -> float:
    """计算标准差（总体标准差）。"""
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    return math.sqrt(variance)


def percentile(values: list[float], p: float) -> float:
    """计算百分位数（线性插值）。"""
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    if n == 1:
        return sorted_vals[0]
    k = (p / 100.0) * (n - 1)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_vals[int(k)]
    return sorted_vals[f] * (c - k) + sorted_vals[c] * (k - f)


def compute_distribution(values: list[float]) -> dict[str, float]:
    """
    计算分数向量的完整分布统计。

    Returns:
        {"count": N, "mean": ..., "stddev": ..., "min": ...,
         "p01": ..., "p05": ..., "p25": ..., "p50": ...,
         "p75": ..., "p95": ..., "p99": ..., "max": ...,
         "winsorized_stddev": ...}
    """
    if not values:
        return {}

    sv = sorted(values)
    n = len(sv)
    return {
        "count": n,
        "mean": sum(values) / n,
        "stddev": statistics_stddev(values),
        "min": sv[0],
        "p01": percentile(values, 1),
        "p05": percentile(values, 5),
        "p25": percentile(values, 25),
        "p50": percentile(values, 50),
        "p75": percentile(values, 75),
        "p95": percentile(values, 95),
        "p99": percentile(values, 99),
        "max": sv[-1],
        "winsorized_stddev": winsorized_stddev(values),
    }


def compute_variance_weights(
    db: PipelineDB,
    table: str,
    score_columns: list[str],
    stage_name: str,
    id_column: str = "candidate_id",
    excluded_prefixes: tuple[str, ...] = ("toxinpred3", "hemopi2"),
) -> dict[str, Any]:
    """
    核心函数：根据分数分布计算方差感知权重。

    Args:
        db: PipelineDB 实例
        table: 评分表名 (如 "stage2_scores")
        score_columns: 参与权重计算的分数列名
        stage_name: 阶段名 (如 "stage2", "final")
        id_column: 主键列名
        excluded_prefixes: 不参与权重计算的列前缀（硬过滤条件）

    Returns:
        {
            "weights": {"anoxpepred_score": 0.35, ...},
            "distribution": {"anoxpepred_score": {...}, ...},
            "total_candidates": 12345,
            "formula": "winsorized_stddev_normalized",
        }

    Raises:
        ValueError: 如果所有列的标准差都为 0
    """
    conn = db.connect()

    # 筛选参与权重计算的列
    weight_columns = [
        c for c in score_columns
        if not any(c.startswith(prefix) for prefix in excluded_prefixes)
        and c.endswith("_score")  # 只处理 score 列，跳过 _success 等
    ]

    if not weight_columns:
        raise ValueError("没有可用的评分列用于权重计算")

    # 1. 从数据库读取所有分数
    total_candidates = 0
    distributions: dict[str, dict] = {}
    raw_values: dict[str, list[float]] = {}

    for col in weight_columns:
        rows = conn.execute(f"""
            SELECT {col} FROM {table}
            WHERE {col} IS NOT NULL
        """).fetchall()
        values = [float(r[0]) for r in rows if r[0] is not None]
        if not values:
            print(f"  [analytics] {col}: 无有效数据，跳过")
            continue
        raw_values[col] = values
        total_candidates = max(total_candidates, len(values))
        distributions[col] = compute_distribution(values)

    if not raw_values:
        raise ValueError("所有评分列均无有效数据")

    # 2. 计算 winsorized 标准差，归一化为权重
    stddevs = {
        col: distributions[col].get("winsorized_stddev", 0)
        for col in raw_values
    }

    total_std = sum(stddevs.values())
    if total_std == 0:
        raise ValueError("所有服务标准差均为 0，无法计算差异化权重")

    weights = {
        col: std / total_std
        for col, std in stddevs.items()
    }

    # 3. 写入 score_distribution 表
    for col in raw_values:
        dist = distributions[col]
        conn.execute("""
            INSERT INTO score_distribution
                (stage_name, service_name, count, mean, stddev,
                 min, p01, p05, p25, p50, p75, p95, p99, max,
                 winsorized_stddev, computed_weight)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            stage_name, col, dist["count"], dist["mean"], dist["stddev"],
            dist["min"], dist["p01"], dist["p05"], dist["p25"],
            dist["p50"], dist["p75"], dist["p95"], dist["p99"],
            dist["max"], dist["winsorized_stddev"],
            weights.get(col, 0.0),
        ])

    # 4. 写入 weight_config 表（可审计）
    conn.execute("""
        INSERT INTO weight_config
            (stage_name, total_candidates, weight_formula,
             weights, distribution_snapshot)
        VALUES (?, ?, ?, ?, ?)
    """, [
        stage_name, total_candidates, "winsorized_stddev_normalized",
        json.dumps(weights),
        json.dumps({col: distributions[col] for col in raw_values}, default=str),
    ])

    # 5. 打印报告
    print(f"\n  [analytics] === {stage_name} 方差感知权重 ===")
    print(f"  [analytics] 参与候选: {total_candidates:,}")
    print(f"  [analytics] 权重公式: winsorized_stddev_normalized")
    for col in sorted(weights, key=weights.get, reverse=True):
        w = weights[col]
        sd = stddevs[col]
        bar = "█" * max(1, int(w * 100))
        print(f"  [analytics]   {col}: {w:.4f} (σ={sd:.4f}) {bar}")
    print(f"  [analytics] 权重和: {sum(weights.values()):.4f}")

    return {
        "weights": weights,
        "distribution": distributions,
        "total_candidates": total_candidates,
        "formula": "winsorized_stddev_normalized",
    }


def apply_weights_and_rank(
    db: PipelineDB,
    table: str,
    score_columns: list[str],
    weights: dict[str, float],
    stage_name: str,
    rank_table: str | None = None,
    id_column: str = "candidate_id",
    top_n: int | None = None,
) -> list[dict[str, Any]]:
    """
    应用权重计算综合得分并排名。

    Args:
        db: PipelineDB 实例
        table: 评分表名
        score_columns: 所有分数列名（含不参与权重的列）
        weights: {col_name: weight} — 由 compute_variance_weights 返回
        stage_name: 阶段名（用于记录）
        rank_table: 可选，排名写入目标表
        id_column: 主键列名
        top_n: 可选，只返回 Top N

    Returns:
        [(candidate_id, composite_score, rank), ...]
    """
    conn = db.connect()

    # 构建加权求和表达式
    weight_exprs = []
    for col, w in weights.items():
        if w > 0 and col in score_columns:
            # 归一化到 [0,1] 区间后加权
            weight_exprs.append(f"COALESCE({col}, 0) * {w}")

    if not weight_exprs:
        raise ValueError("没有有效的加权表达式")

    composite_expr = " + ".join(weight_exprs)

    limit_clause = f"LIMIT {top_n}" if top_n else ""

    rows = conn.execute(f"""
        SELECT {id_column}, {composite_expr} AS composite_score
        FROM {table}
        WHERE {' AND '.join(f'{c} IS NOT NULL' for c in weights if weights[c] > 0)}
        ORDER BY composite_score DESC
        {limit_clause}
    """).fetchall()

    results = []
    for rank, (cid, score) in enumerate(rows, start=1):
        score_val = float(score) if score is not None else 0.0
        results.append({
            id_column: int(cid),
            "composite_score": round(score_val, 6),
            "rank": rank,
        })

    # 写入排名表
    if rank_table:
        conn.execute(f"DELETE FROM {rank_table} WHERE 1=1")
        conn.executemany(f"""
            INSERT INTO {rank_table} ({id_column}, composite_score, rank)
            VALUES (?, ?, ?)
        """, [
            (r[id_column], r["composite_score"], r["rank"])
            for r in results
        ])

    print(f"  [analytics] {stage_name} 排名: {len(results):,} 候选")
    if results:
        print(f"  [analytics]   第 1 名: ID={results[0][id_column]}, "
              f"score={results[0]['composite_score']:.4f}")
        print(f"  [analytics]   第 {len(results)} 名: ID={results[-1][id_column]}, "
              f"score={results[-1]['composite_score']:.4f}")

    return results
