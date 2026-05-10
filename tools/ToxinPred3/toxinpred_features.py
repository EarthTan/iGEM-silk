#!/usr/bin/env python3
# coding: utf-8
"""
ToxinPred 3.0 Python API 封装

提供便捷的 Python API 用于:
- AAC (氨基酸组成) 特征提取
- DPC (二肽组成) 特征提取
- 毒性预测

基于官方 toxinpred3 包 (https://github.com/raghavagps/toxinpred3)
"""

import os
import re
import tempfile
import shutil
import subprocess
import warnings
from typing import List, Union, Tuple

import numpy as np
import pandas as pd

# 尝试从已安装的 toxinpred3 包导入
try:
    from toxinpred3.python_scripts import toxinpred3 as tp3_core
    _TOXINPRE3_AVAILABLE = True
except ImportError:
    _TOXINPRE3_AVAILABLE = False
    warnings.warn(
        "toxinpred3 包未安装，部分功能可能受限。"
        "请运行: uv pip install toxinpred3"
    )


# 标准氨基酸
AMINO_ACIDS = list("ACDEFGHIKLMNPQRSTVWY")


def read_fasta(file_path: str) -> Tuple[List[str], List[str]]:
    """
    读取 FASTA 格式文件。

    Args:
        file_path: FASTA 文件路径

    Returns:
        (序列名称列表, 序列列表)
    """
    seqid = []
    seq = []

    with open(file_path) as f:
        records = f.read()

    records = records.split('>')[1:]
    for fasta in records:
        array = fasta.split('\n')
        name = array[0].split()[0]
        sequence = re.sub('[^ARNDCQEGHILKMFPSTWYV-]', '', ''.join(array[1:]).upper())
        seqid.append(name)
        seq.append(sequence)

    return seqid, seq


def write_fasta(sequences: Union[List[str], str], names: List[str] = None) -> str:
    """
    将序列写入临时 FASTA 文件。

    Args:
        sequences: 序列列表或单个序列
        names: 可选的序列名称列表

    Returns:
        临时 FASTA 文件路径
    """
    if isinstance(sequences, str):
        sequences = [sequences]

    if names is None:
        names = [f"Seq_{i+1}" for i in range(len(sequences))]

    with tempfile.NamedTemporaryFile(mode='w', suffix='.fa', delete=False) as f:
        for name, seq in zip(names, sequences):
            f.write(f">{name}\n{seq}\n")
        return f.name


def aac_composition(sequences: Union[List[str], str]) -> pd.DataFrame:
    """
    计算氨基酸组成 (AAC)。

    Args:
        sequences: 肽序列列表或单个序列

    Returns:
        DataFrame: 20列 (AAC_A, AAC_C, ... AAC_Y)

    Example:
        >>> aac = aac_composition(["KWKLFKKIGAVLKVL"])
        >>> aac.shape
        (1, 20)
    """
    if isinstance(sequences, str):
        sequences = [sequences]

    df1 = pd.DataFrame(sequences, columns=["Seq"])
    dd = []

    for seq in df1['Seq']:
        cc = []
        for aa in AMINO_ACIDS:
            count = sum(1 for k in seq if k == aa)
            composition = (count / len(seq)) * 100
            cc.append(composition)
        dd.append(cc)

    df2 = pd.DataFrame(dd)
    df2.columns = [f'AAC_{aa}' for aa in AMINO_ACIDS]

    return df2


def dpc_composition(sequences: Union[List[str], str], step: int = 1) -> pd.DataFrame:
    """
    计算二肽组成 (DPC)。

    Args:
        sequences: 肽序列列表或单个序列
        step: 步长，默认1表示连续二肽

    Returns:
        DataFrame: 400列 (DPC_AA, DPC_AC, ... DPC_WY)

    Example:
        >>> dpc = dpc_composition(["KWKLFKKIGAVLKVL"])
        >>> dpc.shape
        (1, 400)
    """
    if isinstance(sequences, str):
        sequences = [sequences]

    df1 = pd.DataFrame(sequences, columns=["Seq"])
    dd = []

    for seq in df1['Seq']:
        cc = []
        for aa1 in AMINO_ACIDS:
            for aa2 in AMINO_ACIDS:
                count = 0
                dipeptide = aa1 + aa2
                for m in range(len(seq) - step):
                    if seq[m:m + step + 1:step] == dipeptide:
                        count += 1
                composition = (count / (len(seq) - step)) * 100 if len(seq) > step else 0
                cc.append(composition)
        dd.append(cc)

    df3 = pd.DataFrame(dd)
    df3.columns = [f'DPC{step}_{aa1}{aa2}' for aa1 in AMINO_ACIDS for aa2 in AMINO_ACIDS]

    return df3


def extract_features(sequences: Union[List[str], str]) -> pd.DataFrame:
    """
    提取完整的 AAC + DPC 特征集 (420维)。

    Args:
        sequences: 肽序列列表或单个序列

    Returns:
        DataFrame: 420列 (AAC 20维 + DPC 400维)

    Example:
        >>> features = extract_features(["KWKLFKKIGAVLKVL", "MKPPLNAKLVLKPMWIG"])
        >>> features.shape
        (2, 420)
    """
    if isinstance(sequences, str):
        sequences = [sequences]

    aac = aac_composition(sequences)
    dpc = dpc_composition(sequences)

    return pd.concat([aac, dpc], axis=1)


def predict_toxicity(
    sequences: Union[List[str], str],
    names: List[str] = None,
    threshold: float = 0.38,
    model: int = 1,
    return_raw: bool = False
) -> pd.DataFrame:
    """
    预测肽序列的毒性。

    注意: 默认使用 model=1 (AAC+DPC)。model=2 (Hybrid+MERCI) 需要 perl 运行时，
    且在实际测试中对已知毒素 (如 KWKLFKKIGAVLKVL) 产生假阴性。

    Args:
        sequences: 肽序列列表或单个序列，或 FASTA 文件路径
        names: 可选的序列名称列表
        threshold: 毒性阈值 (0-1)，默认0.38
        model: 模型选择，1=AAC+DPC (推荐), 2=Hybrid+MERCI (需 perl)
        return_raw: 是否返回完整结果（含 MERCI 分数）

    Returns:
        DataFrame 包含:
        - Name: 序列名称
        - Sequence: 肽序列
        - Length: 序列长度
        - Score: 毒性评分 (0-1)
        - Prediction: "Toxin" 或 "Non-Toxin"

    Example:
        >>> results = predict_toxicity(["KWKLFKKIGAVLKVL", "MKPPLNAKLVLKPMWIG"])
        >>> print(results)
    """
    # 处理输入
    if isinstance(sequences, str) and os.path.isfile(sequences):
        # 如果是文件路径
        input_file = sequences
        seqid, seq = read_fasta(input_file)
    else:
        # 如果是序列列表
        if isinstance(sequences, str):
            sequences = [sequences]
        seq = sequences
        seqid = names if names else [f"Seq_{i+1}" for i in range(len(seq))]

    if not _TOXINPRE3_AVAILABLE:
        raise ImportError(
            "toxinpred3 包未安装，无法进行毒性预测。"
            "请运行: uv pip install toxinpred3"
        )

    # 创建临时目录用于输出
    temp_dir = tempfile.mkdtemp()

    try:
        # 写入输入文件
        input_file = os.path.join(temp_dir, "input.fa")
        with open(input_file, 'w') as f:
            for name, s in zip(seqid, seq):
                f.write(f">{name}\n{s}\n")

        output_file = os.path.join(temp_dir, "output.csv")

        # 获取 toxinpred3 包路径
        import toxinpred3
        # namespace package 没有 __file__，使用 __path__
        tp3_path = list(toxinpred3.__path__)[0]

        # 构建 FASTA 内容
        fasta_records = [f">{name}\n{seq}" for name, seq in zip(seqid, seq)]
        fasta_content = "\n".join(fasta_records)

        # 解析 FASTA 获取序列
        all_records = fasta_content.split('>')[1:]
        parsed_seqid = []
        parsed_seq = []
        for record in all_records:
            lines = record.strip().split('\n')
            name = lines[0].split()[0]
            sequence = re.sub('[^ARNDCQEGHILKMFPSTWYV-]', '', ''.join(lines[1:]).upper())
            parsed_seqid.append(name)
            parsed_seq.append(sequence)

        # 使用内部函数计算特征
        seq = parsed_seq

        if model == 1:
            # Model 1: AAC + DPC based
            tp3_core.aac_comp(seq, os.path.join(temp_dir, 'seq.aac'))
            tp3_core.dpc_comp(seq, os.path.join(temp_dir, 'seq.dpc'))

            # 修复 CSV 文件末尾逗号问题
            for f in ['seq.aac', 'seq.dpc']:
                with open(os.path.join(temp_dir, f), 'r') as file:
                    content = file.read()
                content = content.replace(',\n', '\n')
                with open(os.path.join(temp_dir, f), 'w') as file:
                    file.write(content)

            model_path = os.path.join(tp3_path, 'model', 'toxinpred3.0_model.pkl')
            tp3_core.prediction(
                os.path.join(temp_dir, 'seq.aac'),
                os.path.join(temp_dir, 'seq.dpc'),
                model_path,
                os.path.join(temp_dir, 'seq.pred')
            )
            tp3_core.class_assignment(os.path.join(temp_dir, 'seq.pred'), threshold, os.path.join(temp_dir, 'seq.out'))

            df = pd.read_csv(os.path.join(temp_dir, 'seq.out'))
            df.columns = ['ML Score', 'Prediction']

            results = pd.DataFrame({
                'Name': parsed_seqid,
                'Sequence': parsed_seq,
                'Length': [len(s) for s in parsed_seq],
                'Score': df['ML Score'].values,
                'Prediction': df['Prediction'].values
            })

        else:
            # Model 2: Hybrid (ML + MERCI)
            merci_path = os.path.join(tp3_path, 'merci', 'MERCI_motif_locator.pl')
            motifs_p = os.path.join(tp3_path, 'motifs', 'pos_motif.txt')
            motifs_n = os.path.join(tp3_path, 'motifs', 'neg_motif.txt')
            model_path = os.path.join(tp3_path, 'model', 'toxinpred3.0_model.pkl')

            # 计算 AAC 和 DPC
            tp3_core.aac_comp(seq, os.path.join(temp_dir, 'seq.aac'))
            tp3_core.dpc_comp(seq, os.path.join(temp_dir, 'seq.dpc'))

            # 修复 CSV 文件末尾逗号问题
            for f in ['seq.aac', 'seq.dpc']:
                with open(os.path.join(temp_dir, f), 'r') as file:
                    content = file.read()
                content = content.replace(',\n', '\n')
                with open(os.path.join(temp_dir, f), 'w') as file:
                    file.write(content)

            # ML 预测
            tp3_core.prediction(
                os.path.join(temp_dir, 'seq.aac'),
                os.path.join(temp_dir, 'seq.dpc'),
                model_path,
                os.path.join(temp_dir, 'seq.pred')
            )

            # 创建序列文件供 MERCI 使用
            with open(os.path.join(temp_dir, 'Sequence_1'), 'w') as f:
                for name, s in zip(parsed_seqid, parsed_seq):
                    f.write(f">{name}\n{s}\n")

            # 运行 MERCI
            subprocess.run(
                ['perl', merci_path, '-p', os.path.join(temp_dir, 'Sequence_1'),
                 '-i', motifs_p, '-o', os.path.join(temp_dir, 'merci_p.txt')],
                capture_output=True, check=False
            )
            subprocess.run(
                ['perl', merci_path, '-p', os.path.join(temp_dir, 'Sequence_1'),
                 '-i', motifs_n, '-o', os.path.join(temp_dir, 'merci_n.txt')],
                capture_output=True, check=False
            )

            # 处理 MERCI 结果
            tp3_core.MERCI_Processor_p(os.path.join(temp_dir, 'merci_p.txt'),
                                       os.path.join(temp_dir, 'merci_output_p.csv'), parsed_seqid)
            tp3_core.MERCI_Processor_n(os.path.join(temp_dir, 'merci_n.txt'),
                                       os.path.join(temp_dir, 'merci_output_n.csv'), parsed_seqid)
            tp3_core.Merci_after_processing_p(os.path.join(temp_dir, 'merci_output_p.csv'),
                                              os.path.join(temp_dir, 'merci_hybrid_p.csv'))
            tp3_core.Merci_after_processing_n(os.path.join(temp_dir, 'merci_output_n.csv'),
                                              os.path.join(temp_dir, 'merci_hybrid_n.csv'))
            tp3_core.hybrid(
                os.path.join(temp_dir, 'seq.pred'), parsed_seqid,
                os.path.join(temp_dir, 'merci_hybrid_p.csv'),
                os.path.join(temp_dir, 'merci_hybrid_n.csv'),
                threshold, os.path.join(temp_dir, 'final_output')
            )

            df = pd.read_csv(os.path.join(temp_dir, 'final_output'))

            if return_raw:
                results = pd.DataFrame({
                    'Name': parsed_seqid,
                    'Sequence': parsed_seq,
                    'Length': [len(s) for s in parsed_seq],
                    'ML Score': df['ML Score'].values,
                    'MERCI Score Pos': df['MERCI Score Pos'].values,
                    'MERCI Score Neg': df['MERCI Score Neg'].values,
                    'Hybrid Score': df['Hybrid Score'].values,
                    'Prediction': df['Prediction'].values
                })
            else:
                results = pd.DataFrame({
                    'Name': parsed_seqid,
                    'Sequence': parsed_seq,
                    'Length': [len(s) for s in parsed_seq],
                    'Score': df['Hybrid Score'].values,
                    'Prediction': df['Prediction'].values
                })

        # 修正分数范围
        results.loc[results['Score'] > 1, 'Score'] = 1
        results.loc[results['Score'] < 0, 'Score'] = 0

        return results.reset_index(drop=True)

    finally:
        # 清理临时文件
        shutil.rmtree(temp_dir, ignore_errors=True)


def batch_predict_from_file(
    input_file: str,
    output_file: str = None,
    threshold: float = 0.38,
    model: int = 2
) -> pd.DataFrame:
    """
    从 FASTA 文件批量预测并保存结果。

    Args:
        input_file: 输入 FASTA 文件路径
        output_file: 可选的输出 CSV 文件路径
        threshold: 毒性阈值 (0-1)，默认0.38
        model: 模型选择，1=AAC+DPC, 2=Hybrid，默认2

    Returns:
        DataFrame: 预测结果

    Example:
        >>> results = batch_predict_from_file("peptides.fa", "predictions.csv")
        >>> print(f"有毒序列: {sum(results['Prediction'] == 'Toxin')}")
    """
    results = predict_toxicity(input_file, threshold=threshold, model=model)

    if output_file:
        results.to_csv(output_file, index=False)

    return results


# 便捷别名
def calculate_toxicity_score(sequence: str, threshold: float = 0.38) -> Tuple[float, str]:
    """
    基于序列组成计算简化毒性评分（使用默认阈值）。

    Args:
        sequence: 肽序列
        threshold: 阈值

    Returns:
        (评分, 预测结果)
    """
    result = predict_toxicity([sequence], threshold=threshold)
    return result['Score'].iloc[0], result['Prediction'].iloc[0]
