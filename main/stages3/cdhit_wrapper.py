"""
CD-HIT 命令行封装。

提供:
- CD-HIT 命令构建与执行
- .clstr 聚类结果解析
- 聚类统计（簇数、代表序列比例、簇大小分布）
"""

from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path
from typing import Any


def run_cdhit(
    input_fasta: str,
    output_fasta: str,
    identity: float = 0.95,
    word_size: int = 5,
    threads: int = 32,
    memory_limit: int = 0,
) -> dict[str, Any]:
    """
    运行 CD-HIT 聚类。

    参数
    ----
    input_fasta: 输入 FASTA 文件路径
    output_fasta: 输出 FASTA 文件路径（代表序列）
    identity: 序列相似度阈值（-c），默认 0.95
    word_size: word 长度（-n），默认 5
    threads: 线程数（-T），默认 32
    memory_limit: 内存限制 MB（-M），0 = 不限制

    返回
    ----
    {
        "success": True/False,
        "command": "cd-hit ...",
        "returncode": 0,
        "stdout": "...",
        "stderr": "...",
        "elapsed": 123.4,
        "output_fasta": "...",
        "output_clstr": "...",
    }
    """
    clstr_file = output_fasta + ".clstr"
    cmd = [
        "cd-hit",
        "-i", input_fasta,
        "-o", output_fasta,
        "-c", str(identity),
        "-n", str(word_size),
        "-T", str(threads),
        "-M", str(memory_limit),
        "-d", "0",   # 不截断描述
    ]

    start = time.monotonic()
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )
    elapsed = time.monotonic() - start

    return {
        "success": result.returncode == 0,
        "command": " ".join(cmd),
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "elapsed": elapsed,
        "output_fasta": output_fasta,
        "output_clstr": clstr_file,
    }


def parse_clstr(clstr_path: str) -> dict[str, Any]:
    """
    解析 CD-HIT .clstr 文件，返回聚类统计。

    返回
    ----
    {
        "total_clusters": 1234,
        "total_sequences": 100000,
        "cluster_sizes": [105, 3, 1, ...],   # 每个簇的序列数
        "representatives": 1234,              # 代表序列数
        "reduction_ratio": 0.01234,           # 缩减率 (rep / total)
        "size_distribution": {                # 簇大小分布
            "1": 800,      # 单序列簇数量
            "2": 150,      # 2 条序列的簇数量
            "3-10": 200,
            "11-100": 50,
            "101+": 10,
        },
        "singleton_ratio": 0.65,  # 单序列簇占比
    }
    """
    cluster_sizes: list[int] = []
    current_size = 0

    with open(clstr_path) as f:
        for line in f:
            line = line.strip()
            if line.startswith(">"):
                # 新簇开始，记录上一个簇的大小
                if current_size > 0:
                    cluster_sizes.append(current_size)
                current_size = 0
            else:
                current_size += 1
    if current_size > 0:
        cluster_sizes.append(current_size)

    total_clusters = len(cluster_sizes)
    total_sequences = sum(cluster_sizes)
    representatives = total_clusters  # CD-HIT 每个簇输出一条代表序列
    reduction_ratio = representatives / total_sequences if total_sequences > 0 else 0

    # 簇大小分布
    dist: dict[str, int] = {"1": 0, "2": 0, "3-10": 0, "11-100": 0, "101+": 0}
    for s in cluster_sizes:
        if s == 1:
            dist["1"] += 1
        elif s == 2:
            dist["2"] += 1
        elif s <= 10:
            dist["3-10"] += 1
        elif s <= 100:
            dist["11-100"] += 1
        else:
            dist["101+"] += 1

    singleton_ratio = dist["1"] / total_clusters if total_clusters > 0 else 0

    return {
        "total_clusters": total_clusters,
        "total_sequences": total_sequences,
        "cluster_sizes": cluster_sizes,
        "representatives": representatives,
        "reduction_ratio": round(reduction_ratio, 6),
        "size_distribution": dist,
        "singleton_ratio": round(singleton_ratio, 4),
    }


def run_cdhit_parameter_test(
    input_fasta: str,
    identities: list[float] = None,
) -> list[dict[str, Any]]:
    """
    对不同 -c 参数运行 CD-HIT，返回对比结果。

    用于确定短肽聚类的最佳参数。
    """
    if identities is None:
        identities = [0.90, 0.95, 0.98, 1.00]

    base = Path(input_fasta)
    results: list[dict[str, Any]] = []

    for cid in identities:
        out = base.parent / f"{base.stem}_cdhit_c{cid:.2f}.fasta"
        print(f"\n--- CD-HIT -c {cid:.2f} ---")
        run_result = run_cdhit(
            input_fasta=str(base),
            output_fasta=str(out),
            identity=cid,
        )
        if run_result["success"]:
            stats = parse_clstr(run_result["output_clstr"])
            run_result["stats"] = stats
            print(f"  簇数: {stats['total_clusters']:,}")
            print(f"  代表序列: {stats['representatives']:,} ({stats['reduction_ratio']*100:.1f}%)")
            print(f"  单序列簇: {stats['singleton_ratio']*100:.1f}%")
            print(f"  耗时: {run_result['elapsed']:.1f}s")
        else:
            run_result["stats"] = None
            print(f"  [失败] returncode={run_result['returncode']}")
            print(f"  stderr: {run_result['stderr']}")
        results.append(run_result)

    return results
