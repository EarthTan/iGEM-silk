"""
FASTA 抽样工具 — 从超大 FASTA 文件中抽取 N 条序列。

用于 CD-HIT 参数测试前的数据准备。从两个 100G+ 的 FASTA 文件中
各自抽取指定数量的序列，写入单独的抽样文件中。

用法:
    uv run python -m main.stages3.sample_fasta \\
        --input /path/to/uniprot_all_2021_04.fa \\
        --output output3/sample_uniprot_100k.fasta \\
        --n 100000

    uv run python -m main.stages3.sample_fasta \\
        --input /path/to/mgy_clusters_2022_05.fa \\
        --output output3/sample_mgy_100k.fasta \\
        --n 100000
"""

from __future__ import annotations

import argparse
import random
import sys


def count_sequences(path: str) -> int:
    """快速统计 FASTA 文件中的序列数（只数 > 行）。"""
    count = 0
    with open(path) as f:
        for line in f:
            if line.startswith(">"):
                count += 1
    return count


def sample_fasta(input_path: str, output_path: str, n: int,
                 seed: int = 42) -> int:
    """
    从 FASTA 文件中随机抽取 n 条序列。

    使用蓄水池抽样（reservoir sampling），无需将整个文件读入内存。
    返回实际抽取的序列数（如果文件序列数不足 n，则全部取出）。
    """
    random.seed(seed)
    reservoir: list[list[str]] = []
    seen = 0

    with open(input_path) as f:
        current_header: str | None = None
        current_seq: list[str] = []

        def flush() -> None:
            """将当前序列加入蓄水池。"""
            nonlocal current_header, current_seq, seen, reservoir
            if current_header is None:
                return
            seq = "".join(current_seq).replace("\n", "").replace(" ", "")
            seen += 1
            if len(reservoir) < n:
                reservoir.append([current_header, seq])
            else:
                j = random.randint(0, seen - 1)
                if j < n:
                    reservoir[j] = [current_header, seq]
            current_header = None
            current_seq = []

        for line in f:
            line = line.rstrip("\n")
            if line.startswith(">"):
                flush()
                current_header = line
            else:
                if current_header is not None:
                    current_seq.append(line)
        flush()  # 最后一条序列

    # 写入输出
    with open(output_path, "w") as out:
        for header, seq in reservoir:
            out.write(f"{header}\n{seq}\n")

    return len(reservoir)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="从超大 FASTA 文件中随机抽样")
    parser.add_argument("--input", required=True,
                        help="输入 FASTA 文件路径")
    parser.add_argument("--output", required=True,
                        help="输出 FASTA 文件路径")
    parser.add_argument("--n", type=int, default=100_000,
                        help="抽取序列数（默认 100000）")
    parser.add_argument("--seed", type=int, default=42,
                        help="随机种子（默认 42）")
    args = parser.parse_args()

    print(f"统计序列数: {args.input}")
    total = count_sequences(args.input)
    print(f"总序列数: {total:,}")

    print(f"抽样 {args.n:,} 条...")
    sampled = sample_fasta(args.input, args.output, args.n, args.seed)
    print(f"抽取完成: {args.output} ({sampled:,} 条)")


if __name__ == "__main__":
    main()
