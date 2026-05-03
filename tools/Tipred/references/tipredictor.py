#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TIPred 重建实现 - 酪氨酸酶抑制肽预测器

基于 TIPred-MVFF 论文描述重建
由于原始代码未公开，此实现使用 modlamp 进行特征提取，
使用 scikit-learn 实现机器学习模型。

作者：iGEM 工具探索
日期：2024-04-18
"""

import numpy as np
import pandas as pd
from typing import List, Union, Tuple, Optional
from modlamp.descriptors import GlobalDescriptor, PeptideDescriptor
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.svm import SVC
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import cross_val_score, train_test_split
from sklearn.metrics import accuracy_score, matthews_corrcoef, roc_auc_score, classification_report
import pickle
import json


class TIPredictor:
    """
    酪氨酸酶抑制肽（TIP）预测器
    
    基于论文：
    - TIPred (BMC Bioinformatics, 2023)
    - TIPred-MVFF (Scientific Reports, 2025)
    
    特征提取使用 modlamp，模型使用 scikit-learn 实现。
    """
    
    def __init__(self, model_type: str = 'rf'):
        """
        初始化预测器
        
        Args:
            model_type: 模型类型 ('rf'=RandomForest, 'gb'=GradientBoosting, 'svm'=SVC, 'lr'=LogisticRegression)
        """
        self.model_type = model_type
        self.model = None
        self.is_trained = False
        self.feature_dim = 0
        
    def extract_features(self, sequences: Union[str, List[str]]) -> np.ndarray:
        """
        提取肽序列特征
        
        使用 modlamp 的全局描述符，包括：
        - 分子量 (MW)
        - 等电点 (pI)
        - 净电荷
        - 疏水比
        - 不稳定指数
        - 芳香性
        - 脂肪指数
        - Boman 指数
        - 长度
        - 其他理化性质
        
        Args:
            sequences: 单个肽序列或肽序列列表
            
        Returns:
            特征数组 (n_sequences, n_features)
        """
        if isinstance(sequences, str):
            sequences = [sequences]
        
        # 过滤无效序列
        valid_seqs = []
        valid_indices = []
        for i, seq in enumerate(sequences):
            if seq and all(aa in 'ACDEFGHIKLMNPQRSTVWY' for aa in seq.upper()):
                valid_seqs.append(seq.upper())
                valid_indices.append(i)
        
        if not valid_seqs:
            raise ValueError("没有有效的肽序列（只接受标准氨基酸：ACDEFGHIKLMNPQRSTVWY）")
        
        # 使用 modlamp 提取全局描述符
        gd = GlobalDescriptor(valid_seqs)
        gd.calculate_all()
        
        features = np.array(gd.descriptor)
        self.feature_dim = features.shape[1]
        
        # 为无效序列填充 NaN
        if len(valid_seqs) < len(sequences):
            full_features = np.full((len(sequences), self.feature_dim), np.nan)
            full_features[valid_indices] = features
            return full_features
        
        return features
    
    def train(self, sequences: List[str], labels: List[int], 
              test_size: float = 0.2, random_state: int = 42) -> dict:
        """
        训练预测模型
        
        Args:
            sequences: 肽序列列表
            labels: 标签列表（1=TIP, 0=非 TIP）
            test_size: 测试集比例
            random_state: 随机种子
            
        Returns:
            训练结果字典（包含各项性能指标）
        """
        if len(sequences) != len(labels):
            raise ValueError("序列数和标签数必须一致")
        
        # 提取特征
        X = self.extract_features(sequences)
        y = np.array(labels)
        
        # 处理 NaN
        mask = ~np.isnan(X).any(axis=1)
        X = X[mask]
        y = y[mask]
        
        if len(X) < 10:
            raise ValueError(f"有效样本数 ({len(X)}) 过少，无法训练")
        
        # 划分训练/测试集
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=random_state, stratify=y
        )
        
        # 选择模型
        if self.model_type == 'rf':
            self.model = RandomForestClassifier(
                n_estimators=100,
                max_depth=10,
                random_state=random_state,
                class_weight='balanced'
            )
        elif self.model_type == 'gb':
            self.model = GradientBoostingClassifier(
                n_estimators=100,
                max_depth=5,
                random_state=random_state
            )
        elif self.model_type == 'svm':
            self.model = SVC(
                kernel='rbf',
                probability=True,
                class_weight='balanced',
                random_state=random_state
            )
        elif self.model_type == 'lr':
            self.model = LogisticRegression(
                random_state=random_state,
                class_weight='balanced',
                max_iter=1000
            )
        else:
            raise ValueError(f"不支持的模型类型：{self.model_type}")
        
        # 训练
        self.model.fit(X_train, y_train)
        self.is_trained = True
        
        # 评估
        y_pred = self.model.predict(X_test)
        y_prob = self.model.predict_proba(X_test)[:, 1]
        
        results = {
            'accuracy': accuracy_score(y_test, y_pred),
            'mcc': matthews_corrcoef(y_test, y_pred),
            'auc': roc_auc_score(y_test, y_prob),
            'train_size': len(X_train),
            'test_size': len(X_test),
            'feature_dim': self.feature_dim,
            'classification_report': classification_report(y_test, y_pred, output_dict=True)
        }
        
        # 交叉验证
        cv_scores = cross_val_score(self.model, X, y, cv=5, scoring='roc_auc')
        results['cv_auc_mean'] = cv_scores.mean()
        results['cv_auc_std'] = cv_scores.std()
        
        return results
    
    def predict(self, sequences: Union[str, List[str]]) -> np.ndarray:
        """
        预测肽序列的 TIP 活性概率
        
        Args:
            sequences: 单个肽序列或肽序列列表
            
        Returns:
            TIP 概率数组（0-1 之间）
        """
        if not self.is_trained:
            raise RuntimeError("模型尚未训练，请先调用 train() 方法")
        
        if isinstance(sequences, str):
            sequences = [sequences]
        
        X = self.extract_features(sequences)
        
        # 处理 NaN
        mask = ~np.isnan(X).any(axis=1)
        probs = np.zeros(len(sequences))
        
        if mask.any():
            probs[mask] = self.model.predict_proba(X[mask])[:, 1]
        
        return probs
    
    def predict_class(self, sequences: Union[str, List[str]], 
                      threshold: float = 0.5) -> List[int]:
        """
        预测肽序列的 TIP 分类
        
        Args:
            sequences: 单个肽序列或肽序列列表
            threshold: 分类阈值
            
        Returns:
            分类列表（1=TIP, 0=非 TIP）
        """
        probs = self.predict(sequences)
        return [1 if p >= threshold else 0 for p in probs]
    
    def save(self, path: str):
        """保存模型到文件"""
        with open(path, 'wb') as f:
            pickle.dump(self, f)
        print(f"模型已保存到：{path}")
    
    @staticmethod
    def load(path: str) -> 'TIPredictor':
        """从文件加载模型"""
        with open(path, 'rb') as f:
            return pickle.load(f)


def load_fasta(path: str) -> List[Tuple[str, str]]:
    """
    读取 FASTA 文件
    
    Returns:
        [(header, sequence), ...] 列表
    """
    sequences = []
    current_header = None
    current_seq = []
    
    with open(path, 'r') as f:
        for line in f:
            line = line.strip()
            if line.startswith('>'):
                if current_header:
                    sequences.append((current_header, ''.join(current_seq)))
                current_header = line[1:]
                current_seq = []
            else:
                current_seq.append(line)
        
        if current_header:
            sequences.append((current_header, ''.join(current_seq)))
    
    return sequences


def load_csv(path: str) -> pd.DataFrame:
    """读取 CSV 文件"""
    return pd.read_csv(path)


# 命令行接口
if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='TIPred - 酪氨酸酶抑制肽预测器')
    parser.add_argument('--input', '-i', type=str, help='输入文件路径（FASTA 或 CSV）')
    parser.add_argument('--output', '-o', type=str, help='输出文件路径')
    parser.add_argument('--train', action='store_true', help='训练模式')
    parser.add_argument('--labels', type=str, help='训练标签文件（CSV，含 sequence 和 label 列）')
    parser.add_argument('--model', '-m', type=str, help='模型文件路径（用于预测）')
    parser.add_argument('--save-model', type=str, help='保存训练后的模型')
    
    args = parser.parse_args()
    
    if args.train:
        # 训练模式
        if not args.input or not args.labels:
            print("错误：训练模式需要 --input 和 --labels 参数")
            exit(1)
        
        # 加载数据
        if args.input.endswith('.fasta'):
            data = load_fasta(args.input)
            sequences = [seq for _, seq in data]
        else:
            df = load_csv(args.input)
            sequences = df['Sequence'].tolist() if 'Sequence' in df.columns else df['sequence'].tolist()
        
        labels_df = pd.read_csv(args.labels)
        labels = labels_df['label'].tolist() if 'label' in labels_df.columns else labels_df['Label'].tolist()
        
        # 训练
        predictor = TIPredictor()
        results = predictor.train(sequences, labels)
        
        print("\n=== 训练结果 ===")
        print(f"训练集大小：{results['train_size']}")
        print(f"测试集大小：{results['test_size']}")
        print(f"特征维度：{results['feature_dim']}")
        print(f"准确率：{results['accuracy']:.4f}")
        print(f"MCC: {results['mcc']:.4f}")
        print(f"AUC: {results['auc']:.4f}")
        print(f"5 折 CV AUC: {results['cv_auc_mean']:.4f} ± {results['cv_auc_std']:.4f}")
        
        if args.save_model:
            predictor.save(args.save_model)
    
    elif args.model and args.input:
        # 预测模式
        predictor = TIPredictor.load(args.model)
        
        if args.input.endswith('.fasta'):
            data = load_fasta(args.input)
            sequences = [seq for _, seq in data]
            headers = [h for h, _ in data]
        else:
            df = load_csv(args.input)
            sequences = df['Sequence'].tolist() if 'Sequence' in df.columns else df['sequence'].tolist()
            headers = sequences
        
        probs = predictor.predict(sequences)
        
        # 输出结果
        results_df = pd.DataFrame({
            'ID': range(len(sequences)),
            'Sequence': sequences,
            'TIP_Probability': probs,
            'Prediction': ['TIP' if p >= 0.5 else 'non-TIP' for p in probs]
        })
        
        if args.output:
            results_df.to_csv(args.output, index=False)
            print(f"结果已保存到：{args.output}")
        else:
            print(results_df.to_string(index=False))
    
    else:
        # 演示模式
        print("=== TIPred 演示模式 ===\n")
        
        # 示例序列
        demo_seqs = ['YGGFL', 'GHK', 'PAL', 'ACDEFGHIK', 'LMNPQRSTVWY']
        
        # 创建未训练的预测器（仅演示特征提取）
        predictor = TIPredictor()
        features = predictor.extract_features(demo_seqs)
        
        print("示例肽序列特征提取：")
        print(f"序列数：{len(demo_seqs)}")
        print(f"特征维度：{features.shape[1]}")
        print("\n特征矩阵（前 5 行）:")
        print(features[:5])
        
        print("\n=== 使用说明 ===")
        print("1. 训练：python tipredictor.py --train --input sequences.fasta --labels labels.csv --save-model model.pkl")
        print("2. 预测：python tipredictor.py --model model.pkl --input queries.fasta --output results.csv")
