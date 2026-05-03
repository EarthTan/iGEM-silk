#!/usr/bin/env python3
"""
疫苗候选肽筛选脚本

本脚本使用MHCflurry预测肽的MHC结合亲和力，筛选强结合子作为疫苗候选。
支持从FASTA文件读取肽序列，批量预测，结果分析和可视化。

使用方法:
    python vaccine_candidate_screening.py --input peptides.fasta --output results.csv
"""

import argparse
import sys
import os
from pathlib import Path
from typing import List, Dict, Any, Tuple
import pandas as pd
import numpy as np

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tools.mhcflurry_integration import MHCflurryIntegration, MHCflurryConfig


def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="使用MHCflurry筛选疫苗候选肽",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
    # 基本使用
    python vaccine_candidate_screening.py --input peptides.fasta --output results.csv
    
    # 指定等位基因
    python vaccine_candidate_screening.py --input peptides.fasta --alleles HLA-A*02:01 HLA-B*07:02
    
    # 使用自定义阈值
    python vaccine_candidate_screening.py --input peptides.fasta --strong-threshold 100 --weak-threshold 1000
    
    # 生成可视化
    python vaccine_candidate_screening.py --input peptides.fasta --visualize
        """
    )
    
    parser.add_argument(
        "--input", "-i",
        type=str,
        required=True,
        help="输入FASTA文件路径"
    )
    
    parser.add_argument(
        "--output", "-o",
        type=str,
        default="vaccine_candidates.csv",
        help="输出文件路径 (默认: vaccine_candidates.csv)"
    )
    
    parser.add_argument(
        "--alleles", "-a",
        nargs="+",
        default=["HLA-A*02:01", "HLA-A*01:01", "HLA-B*07:02", "HLA-C*07:02"],
        help="MHC等位基因列表 (默认: 常见等位基因)"
    )
    
    parser.add_argument(
        "--strong-threshold",
        type=float,
        default=50.0,
        help="强结合阈值 (nM) (默认: 50.0)"
    )
    
    parser.add_argument(
        "--weak-threshold",
        type=float,
        default=500.0,
        help="弱结合阈值 (nM) (默认: 500.0)"
    )
    
    parser.add_argument(
        "--percentile-strong",
        type=float,
        default=0.02,
        help="强结合百分位阈值 (默认: 0.02)"
    )
    
    parser.add_argument(
        "--percentile-weak",
        type=float,
        default=0.10,
        help="弱结合百分位阈值 (默认: 0.10)"
    )
    
    parser.add_argument(
        "--min-length",
        type=int,
        default=8,
        help="最小肽长度 (默认: 8)"
    )
    
    parser.add_argument(
        "--max-length",
        type=int,
        default=15,
        help="最大肽长度 (默认: 15)"
    )
    
    parser.add_argument(
        "--top-n",
        type=int,
        default=50,
        help="输出前N个最佳候选 (默认: 50)"
    )
    
    parser.add_argument(
        "--visualize",
        action="store_true",
        help="生成可视化图表"
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="详细输出模式"
    )
    
    parser.add_argument(
        "--cache",
        action="store_true",
        default=True,
        help="启用预测缓存 (默认: 启用)"
    )
    
    return parser.parse_args()


def load_peptides_from_fasta(fasta_file: str, min_length: int = 8, max_length: int = 15) -> List[Tuple[str, str]]:
    """
    从FASTA文件加载肽序列
    
    Args:
        fasta_file: FASTA文件路径
        min_length: 最小肽长度
        max_length: 最大肽长度
    
    Returns:
        List[Tuple[str, str]]: (序列ID, 肽序列) 列表
    """
    peptides = []
    
    if not os.path.exists(fasta_file):
        raise FileNotFoundError(f"FASTA文件不存在: {fasta_file}")
    
    with open(fasta_file, 'r') as f:
        current_id = None
        current_seq = []
        
        for line in f:
            line = line.strip()
            
            if line.startswith('>'):
                # 保存前一个序列
                if current_id is not None and current_seq:
                    seq = ''.join(current_seq)
                    if min_length <= len(seq) <= max_length:
                        peptides.append((current_id, seq))
                
                # 开始新序列
                current_id = line[1:].split()[0]  # 取第一个单词作为ID
                current_seq = []
            else:
                current_seq.append(line)
        
        # 保存最后一个序列
        if current_id is not None and current_seq:
            seq = ''.join(current_seq)
            if min_length <= len(seq) <= max_length:
                peptides.append((current_id, seq))
    
    return peptides


def initialize_mhcflurry(config_args: Dict[str, Any]) -> MHCflurryIntegration:
    """初始化MHCflurry集成"""
    config = MHCflurryConfig(
        cache_predictions=config_args["cache"],
        prediction_thresholds={
            "strong_binder": config_args["strong_threshold"],
            "weak_binder": config_args["weak_threshold"],
            "non_binder": 10000.0
        }
    )
    
    mhcflurry = MHCflurryIntegration(config=config, verbose=config_args["verbose"])
    
    # 检查安装状态
    status = mhcflurry.check_installation()
    if config_args["verbose"]:
        print(f"MHCflurry版本: {status['version']}")
        print(f"可用等位基因: {status['available_alleles_count']}")
    
    return mhcflurry


def validate_alleles(mhcflurry: MHCflurryIntegration, alleles: List[str]) -> List[str]:
    """验证等位基因是否支持"""
    valid_alleles, invalid_alleles = mhcflurry.validate_alleles(alleles)
    
    if invalid_alleles:
        print(f"警告: 以下等位基因不被支持: {invalid_alleles}")
        print(f"将使用支持的等位基因: {valid_alleles}")
    
    if not valid_alleles:
        raise ValueError("没有有效的等位基因可用")
    
    return valid_alleles


def predict_peptides(mhcflurry: MHCflurryIntegration, peptides: List[Tuple[str, str]], 
                     alleles: List[str], verbose: bool = False) -> pd.DataFrame:
    """预测肽的结合亲和力"""
    # 提取肽序列
    peptide_ids = [pid for pid, _ in peptides]
    peptide_seqs = [seq for _, seq in peptides]
    
    if verbose:
        print(f"开始预测 {len(peptide_seqs)} 个肽与 {len(alleles)} 个等位基因的结合亲和力...")
        print(f"预计预测数量: {len(peptide_seqs) * len(alleles)}")
    
    # 批量预测
    results = mhcflurry.predict_batch(peptide_seqs, alleles)
    
    # 转换为DataFrame
    results_list = []
    for result in results:
        results_list.append({
            "peptide_id": peptide_ids[peptide_seqs.index(result.peptide)] if result.peptide in peptide_seqs else "unknown",
            "peptide": result.peptide,
            "allele": result.allele,
            "affinity_nM": result.affinity_nM,
            "percentile_rank": result.percentile_rank,
            "prediction_score": result.prediction_score,
            "is_strong_binder": result.is_strong_binder,
            "is_weak_binder": result.is_weak_binder,
            "is_non_binder": result.is_non_binder,
            "prediction_class": result.prediction_class,
            "peptide_length": len(result.peptide)
        })
    
    df = pd.DataFrame(results_list)
    
    if verbose:
        print(f"预测完成，共 {len(df)} 个结果")
    
    return df


def analyze_results(df: pd.DataFrame, args) -> Dict[str, Any]:
    """分析预测结果"""
    analysis = {}
    
    # 基本统计
    analysis["total_predictions"] = len(df)
    analysis["unique_peptides"] = df["peptide"].nunique()
    analysis["unique_alleles"] = df["allele"].nunique()
    
    # 结合类别统计
    analysis["strong_binders"] = len(df[df["is_strong_binder"]])
    analysis["weak_binders"] = len(df[df["is_weak_binder"]])
    analysis["non_binders"] = len(df[df["is_non_binder"]])
    
    # 亲和力统计
    analysis["affinity_mean"] = df["affinity_nM"].mean()
    analysis["affinity_median"] = df["affinity_nM"].median()
    analysis["affinity_min"] = df["affinity_nM"].min()
    analysis["affinity_max"] = df["affinity_nM"].max()
    analysis["affinity_std"] = df["affinity_nM"].std()
    
    # 百分位排名统计
    analysis["percentile_mean"] = df["percentile_rank"].mean()
    analysis["percentile_median"] = df["percentile_rank"].median()
    analysis["percentile_min"] = df["percentile_rank"].min()
    analysis["percentile_max"] = df["percentile_rank"].max()
    
    # 按等位基因统计
    allele_stats = df.groupby("allele").agg({
        "affinity_nM": ["count", "mean", "median", "min", "max"],
        "is_strong_binder": "sum",
        "is_weak_binder": "sum",
        "is_non_binder": "sum"
    }).round(2)
    
    analysis["allele_stats"] = allele_stats
    
    # 按肽统计（跨等位基因）
    peptide_stats = df.groupby(["peptide_id", "peptide"]).agg({
        "affinity_nM": ["count", "mean", "median", "min"],
        "is_strong_binder": "sum",
        "is_weak_binder": "sum",
        "percentile_rank": "mean"
    }).round(2)
    
    # 重命名列
    peptide_stats.columns = ["_".join(col).strip() for col in peptide_stats.columns.values]
    peptide_stats = peptide_stats.rename(columns={
        "affinity_nM_count": "allele_count",
        "affinity_nM_mean": "affinity_mean",
        "affinity_nM_median": "affinity_median",
        "affinity_nM_min": "affinity_min",
        "is_strong_binder_sum": "strong_binder_count",
        "is_weak_binder_sum": "weak_binder_count",
        "percentile_rank_mean": "percentile_mean"
    })
    
    # 计算综合评分
    peptide_stats["composite_score"] = (
        0.6 * (1 - peptide_stats["percentile_mean"] / 0.1) +  # 百分位排名贡献 (0-1)
        0.4 * (1 - peptide_stats["affinity_mean"] / 1000)    # 亲和力贡献 (0-1)
    ).clip(0, 1)
    
    analysis["peptide_stats"] = peptide_stats
    
    return analysis


def select_top_candidates(peptide_stats: pd.DataFrame, top_n: int = 50) -> pd.DataFrame:
    """选择前N个最佳候选"""
    # 按综合评分排序
    sorted_candidates = peptide_stats.sort_values("composite_score", ascending=False)
    
    # 选择前N个
    top_candidates = sorted_candidates.head(top_n).copy()
    
    # 添加排名
    top_candidates["rank"] = range(1, len(top_candidates) + 1)
    
    return top_candidates


def save_results(df: pd.DataFrame, analysis: Dict[str, Any], args):
    """保存结果到文件"""
    output_path = Path(args.output)
    
    # 保存所有预测结果
    all_results_path = output_path.parent / f"{output_path.stem}_all_predictions.csv"
    df.to_csv(all_results_path, index=False)
    print(f"所有预测结果已保存到: {all_results_path}")
    
    # 保存肽统计
    peptide_stats = analysis["peptide_stats"]
    peptide_stats_path = output_path.parent / f"{output_path.stem}_peptide_stats.csv"
    peptide_stats.to_csv(peptide_stats_path)
    print(f"肽统计结果已保存到: {peptide_stats_path}")
    
    # 保存前N个候选
    top_candidates = select_top_candidates(peptide_stats, args.top_n)
    top_candidates_path = output_path.parent / f"{output_path.stem}_top_{args.top_n}_candidates.csv"
    top_candidates.to_csv(top_candidates_path)
    print(f"前{args.top_n}个候选已保存到: {top_candidates_path}")
    
    # 保存分析摘要
    summary_path = output_path.parent / f"{output_path.stem}_summary.txt"
    with open(summary_path, 'w') as f:
        f.write("疫苗候选肽筛选结果摘要\n")
        f.write("=" * 50 + "\n\n")
        
        f.write("输入参数:\n")
        f.write(f"  输入文件: {args.input}\n")
        f.write(f"  等位基因: {', '.join(args.alleles)}\n")
        f.write(f"  强结合阈值: {args.strong_threshold} nM\n")
        f.write(f"  弱结合阈值: {args.weak_threshold} nM\n")
        f.write(f"  最小肽长度: {args.min_length}\n")
        f.write(f"  最大肽长度: {args.max_length}\n\n")
        
        f.write("预测统计:\n")
        f.write(f"  总预测数: {analysis['total_predictions']}\n")
        f.write(f"  唯一肽数: {analysis['unique_peptides']}\n")
        f.write(f"  唯一等位基因数: {analysis['unique_alleles']}\n\n")
        
        f.write("结合类别分布:\n")
        f.write(f"  强结合子: {analysis['strong_binders']} ({analysis['strong_binders']/analysis['total_predictions']*100:.1f}%)\n")
        f.write(f"  弱结合子: {analysis['weak_binders']} ({analysis['weak_binders']/analysis['total_predictions']*100:.1f}%)\n")
        f.write(f"  非结合子: {analysis['non_binders']} ({analysis['non_binders']/analysis['total_predictions']*100:.1f}%)\n\n")
        
        f.write("亲和力统计 (nM):\n")
        f.write(f"  平均值: {analysis['affinity_mean']:.2f}\n")
        f.write(f"  中位数: {analysis['affinity_median']:.2f}\n")
        f.write(f"  最小值: {analysis['affinity_min']:.2f}\n")
        f.write(f"  最大值: {analysis['affinity_max']:.2f}\n")
        f.write(f"  标准差: {analysis['affinity_std']:.2f}\n\n")
        
        f.write("百分位排名统计:\n")
        f.write(f"  平均值: {analysis['percentile_mean']:.4f}\n")
        f.write(f"  中位数: {analysis['percentile_median']:.4f}\n")
        f.write(f"  最小值: {analysis['percentile_min']:.4f}\n")
        f.write(f"  最大值: {analysis['percentile_max']:.4f}\n\n")
        
        f.write("前10个候选肽:\n")
        top_10 = select_top_candidates(analysis['peptide_stats'], 10)
        for idx, (_, row) in enumerate(top_10.iterrows(), 1):
            f.write(f"  {idx:2d}. {row.name[1]} (ID: {row.name[0]})\n")
            f.write(f"      综合评分: {row['composite_score']:.3f}, 亲和力均值: {row['affinity_mean']:.1f} nM, 强结合等位基因数: {row['strong_binder_count']}\n")
    
    print(f"分析摘要已保存到: {summary_path}")
    
    # 打印摘要到控制台
    if args.verbose:
        print("\n" + "=" * 50)
        print("筛选结果摘要")
        print("=" * 50)
        print(f"总预测数: {analysis['total_predictions']}")
        print(f"强结合子: {analysis['strong_binders']} ({analysis['strong_binders']/analysis['total_predictions']*100:.1f}%)")
        print(f"平均亲和力: {analysis['affinity_mean']:.2f} nM")
        print(f"前3个候选肽:")
        top_3 = select_top_candidates(analysis['peptide_stats'], 3)
        for idx, (_, row) in enumerate(top_3.iterrows(), 1):
            print(f"  {idx}. {row.name[1]} (评分: {row['composite_score']:.3f}, 亲和力: {row['affinity_mean']:.1f} nM)")


def generate_visualization(df: pd.DataFrame, analysis: Dict[str, Any], args):
    """生成可视化图表"""
    try:
