"""
超大 FASTA 流式读取器。

支持 mmap 内存映射处理 100G+ 文件，提供:
- 逐条序列迭代
- 3-30aa 预筛选
- 标准 AA 过滤
- 并行分块读取
"""

from __future__ import annotations

import mmap
import re
import time
from typing import Iterator

# 20 种标准氨基酸
STANDARD_AA = set("ACDEFGHIKLMNPQRSTVWY")
STANDARD_AA_RE = re.compile(r"^[ACDEFGHIKLMNPQRSTVWY]+$")


def is_standard_aa(seq: str) -> bool:
    """检查序列是否只含 20 种标准氨基酸。"""
    return bool(STANDARD_AA_RE.match(seq.upper()))


def fasta_iter_lines(path: str) -> Iterator[tuple[str, str]]:
    """
    流式读取 FASTA 文件，逐个 yield (header, sequence)。

    内存占用 O(最长单条序列)，适合 100G+ 文件。
    """
    header: str | None = None
    seq_parts: list[str] = []

    with open(path) as f:
        for line in f:
            line = line.rstrip("\n")
            if not line:
                continue
            if line.startswith(">"):
                if header is not None:
                    yield header, "".join(seq_parts)
                header = line
                seq_parts = []
            else:
                seq_parts.append(line)

    if header is not None:
        yield header, "".join(seq_parts)


def fasta_iter_mmap(path: str) -> Iterator[tuple[str, str]]:
    """
    使用 mmap 的 FASTA 迭代器。大文件上可能比逐行读取更快。

    用法同 fasta_iter_lines。
    """
    with open(path, "rb") as f:
        with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
            header: str | None = None
            seq_parts: list[bytearray] = []
            pos = 0
            size = len(mm)

            while pos < size:
                nl = mm.find(b"\n", pos)
                if nl == -1:
                    nl = size
                line = mm[pos:nl].decode("ascii", errors="replace").rstrip("\r")
                pos = nl + 1

                if not line:
                    continue
                if line.startswith(">"):
                    if header is not None:
                        yield header, b"".join(seq_parts).decode("ascii", errors="replace")
                    header = line
                    seq_parts = []
                else:
                    seq_parts.append(line.encode("ascii", errors="replace"))

            if header is not None:
                yield header, b"".join(seq_parts).decode("ascii", errors="replace")


def filter_length(seq: str, min_len: int = 3, max_len: int = 30) -> bool:
    """检查序列长度是否在 [min_len, max_len] 范围内。"""
    return min_len <= len(seq) <= max_len


def extract_short_sequences(
    input_path: str,
    output_path: str | None = None,
    min_len: int = 3,
    max_len: int = 30,
    max_count: int | None = None,
    progress_interval: int = 1_000_000,
) -> list[tuple[str, str]]:
    """
    从 FASTA 文件中提取 3-30aa 的短序列。

    参数
    ----
    input_path: 输入 FASTA 文件路径
    output_path: 可选的输出 FASTA 文件路径
    min_len, max_len: 长度筛选范围
    max_count: 最多提取多少条（用于抽样）
    progress_interval: 每处理多少条打印一次进度

    返回
    ----
    [(header, sequence), ...] 列表
    """
    result: list[tuple[str, str]] = []
    total = 0
    passed = 0
    start = time.monotonic()

    for header, seq in fasta_iter_lines(input_path):
        total += 1
        if total % progress_interval == 0:
            elapsed = time.monotonic() - start
            rate = total / elapsed if elapsed > 0 else 0
            print(f"  [进度] {total:,} 条扫描, {passed:,} 条通过, "
                  f"速度 {rate:.0f} 条/秒, 耗时 {elapsed:.0f}s")

        if filter_length(seq, min_len, max_len) and is_standard_aa(seq):
            result.append((header, seq))
            passed += 1
            if max_count and passed >= max_count:
                break

    elapsed = time.monotonic() - start
    print(f"  [完成] 共扫描 {total:,} 条, {passed:,} 条通过 3-{max_len}aa 筛选, "
          f"耗时 {elapsed:.0f}s")

    if output_path:
        with open(output_path, "w") as f:
            for h, s in result:
                f.write(f"{h}\n{s}\n")
        print(f"  [写入] {output_path} ({len(result):,} 条)")

    return result


def fasta_count_sequences(path: str) -> int:
    """快速统计 FASTA 序列数（只数 > 行）。"""
    count = 0
    with open(path) as f:
        for line in f:
            if line.startswith(">"):
                count += 1
    return count
