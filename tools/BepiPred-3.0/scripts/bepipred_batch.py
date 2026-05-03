#!/usr/bin/env python3
"""
BepiPred-3.0 批量预测脚本

功能：
1. 批量处理 FASTA 格式的肽序列
2. 提取表位特征用于机器学习
3. 计算表位惩罚分数

使用方法：
    python bepipred_batch.py -i input.fasta -o output_dir
"""

import argparse
import sys
from pathlib import Path
import pandas as pd

# 添加 BepiPred-3.0 路径
# 脚本位于 scripts/ 目录，BepiPred-3.0 代码位于 repo/
BP3_PATH = Path(__file__).parent.parent / "repo"
if BP3_PATH.exists():
    sys.path.insert(0, str(BP3_PATH))
    from bp3 import bepipred3
else:
    print("警告：未找到 repo/ 目录，请确保 BepiPred-3.0 代码在 repo/ 目录下")
    bepipred3 = None


def run_bepipred(input_fasta: str, output_dir: str, threshold: float = 0.1512, 
                 add_seq_len: bool = False, rolling_window: int = 7):
    """
    运行 BepiPred-3.0 预测
    
    Args:
        input_fasta: 输入 FASTA 文件路径
        output_dir: 输出目录
        threshold: 表位预测阈值（默认 0.1512）
        add_seq_len: 是否添加序列长度特征
        rolling_window: 滑动窗口大小
    
    Returns:
        predictor: BepiPred-3.0 预测器对象
    """
    if bepipred3 is None:
        raise ImportError("BepiPred-3.0 未正确安装")
    
    input_path = Path(input_fasta)
    output_path = Path(output_dir)
    esm_path = output_path / "esm_encodings"
    
    output_path.mkdir(parents=True, exist_ok=True)
    esm_path.mkdir(parents=True, exist_ok=True)
    
    print(f"处理文件: {input_path}")
    print(f"输出目录: {output_path}")
    
    # 创建抗原对象
    antigens = bepipred3.Antigens(input_path, esm_path, add_seq_len=add_seq_len)
    
    # 运行预测
    predictor = bepipred3.BP3EnsemblePredict(
        antigens, 
        rolling_window_size=rolling_window, 
        top_pred_pct=0.2
    )
    predictor.run_bp3_ensemble()
    
    # 输出结果
    predictor.create_csvfile(output_path)
    predictor.bp3_pred_variable_threshold(output_path, var_threshold=threshold)
    
    print(f"预测完成！")
    
    return predictor


def extract_epitope_features(csv_path: str, threshold: float = 0.1512) -> dict:
    """
    从 BepiPred 输出提取特征
    
    Args:
        csv_path: raw_output.csv 文件路径
        threshold: 表位判定阈值
    
    Returns:
        features: 特征字典
    """
    df = pd.read_csv(csv_path)
    
    features = {
        # 基本统计
        'sequence_length': len(df),
        'max_epitope_score': df['BepiPred-3.0 score'].max(),
        'min_epitope_score': df['BepiPred-3.0 score'].min(),
        'mean_epitope_score': df['BepiPred-3.0 score'].mean(),
        'std_epitope_score': df['BepiPred-3.0 score'].std(),
        
        # 表位残基统计
        'epitope_residue_count': (df['BepiPred-3.0 score'] > threshold).sum(),
        'epitope_ratio': (df['BepiPred-3.0 score'] > threshold).mean(),
        
        # 线性表位统计
        'max_linear_score': df['BepiPred-3.0 linear epitope score'].max(),
        'mean_linear_score': df['BepiPred-3.0 linear epitope score'].mean(),
        
        # 高风险残基统计
        'high_risk_count': (df['BepiPred-3.0 score'] > 0.3).sum(),
        'high_risk_ratio': (df['BepiPred-3.0 score'] > 0.3).mean(),
    }
    
    return features


def calculate_epitope_penalty(csv_path: str, threshold: float = 0.1512,
                              ratio_weight: float = 0.4, 
                              max_score_weight: float = 0.3,
                              high_risk_weight: float = 0.3) -> float:
    """
    计算表位惩罚分数
    
    Args:
        csv_path: raw_output.csv 文件路径
        threshold: 表位判定阈值
        ratio_weight: 表位比例权重
        max_score_weight: 最大分数权重
        high_risk_weight: 高风险残基权重
    
    Returns:
        penalty: 惩罚分数（0-1）
    """
    df = pd.read_csv(csv_path)
    
    # 表位残基比例
    epitope_ratio = (df['BepiPred-3.0 score'] > threshold).mean()
    
    # 最大表位分数（归一化到 0-1）
    max_score = df['BepiPred-3.0 score'].max()
    
    # 高风险残基比例
    high_risk_ratio = (df['BepiPred-3.0 score'] > 0.3).mean()
    
    # 综合惩罚分数
    penalty = (epitope_ratio * ratio_weight + 
               max_score * max_score_weight + 
               high_risk_ratio * high_risk_weight)
    
    return penalty


def epitope_filter(csv_path: str, max_epitope_ratio: float = 0.3,
                   max_score_threshold: float = 0.5) -> bool:
    """
    基于表位预测的粗筛
    
    Args:
        csv_path: raw_output.csv 文件路径
        max_epitope_ratio: 最大允许的表位残基比例
        max_score_threshold: 最大允许的表位分数
    
    Returns:
        passed: 是否通过筛选
    """
    df = pd.read_csv(csv_path)
    
    epitope_ratio = (df['BepiPred-3.0 score'] > 0.1512).mean()
    max_score = df['BepiPred-3.0 score'].max()
    
    if epitope_ratio > max_epitope_ratio or max_score > max_score_threshold:
        return False
    
    return True


def batch_extract_features(output_dir: str, output_csv: str = None) -> pd.DataFrame:
    """
    批量提取所有序列的特征
    
    Args:
        output_dir: BepiPred 输出目录
        output_csv: 特征输出 CSV 文件路径（可选）
    
    Returns:
        features_df: 特征 DataFrame
    """
    csv_path = Path(output_dir) / "raw_output.csv"
    df = pd.read_csv(csv_path)
    
    # 按序列分组提取特征
    features_list = []
    for accession in df['Accession'].unique():
        seq_df = df[df['Accession'] == accession]
        
        features = {
            'accession': accession,
            'sequence_length': len(seq_df),
            'max_epitope_score': seq_df['BepiPred-3.0 score'].max(),
            'mean_epitope_score': seq_df['BepiPred-3.0 score'].mean(),
            'epitope_ratio': (seq_df['BepiPred-3.0 score'] > 0.1512).mean(),
            'max_linear_score': seq_df['BepiPred-3.0 linear epitope score'].max(),
            'penalty_score': calculate_epitope_penalty(str(csv_path).replace('raw_output.csv', f'{accession}_temp.csv'))
        }
        
        # 临时保存单序列数据计算惩罚
        temp_csv = Path(output_dir) / f"{accession}_temp.csv"
        seq_df.to_csv(temp_csv, index=False)
        features['penalty_score'] = calculate_epitope_penalty(str(temp_csv))
        temp_csv.unlink()  # 删除临时文件
        
        features_list.append(features)
    
    features_df = pd.DataFrame(features_list)
    
    if output_csv:
        features_df.to_csv(output_csv, index=False)
        print(f"特征已保存到: {output_csv}")
    
    return features_df


def main():
    parser = argparse.ArgumentParser(description="BepiPred-3.0 批量预测脚本")
    parser.add_argument("-i", "--input", required=True, help="输入 FASTA 文件")
    parser.add_argument("-o", "--output", required=True, help="输出目录")
    parser.add_argument("-t", "--threshold", type=float, default=0.1512, 
                        help="表位预测阈值（默认 0.1512）")
    parser.add_argument("--features", action="store_true", 
                        help="提取特征并保存为 CSV")
    
    args = parser.parse_args()
    
    # 运行预测
    run_bepipred(args.input, args.output, args.threshold)
    
    # 提取特征
    if args.features:
        features_csv = Path(args.output) / "epitope_features.csv"
        batch_extract_features(args.output, str(features_csv))


if __name__ == "__main__":
    main()
