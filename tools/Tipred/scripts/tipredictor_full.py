#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TIPred-MVFF 完整复现实现

基于论文：
- TIPred (BMC Bioinformatics, 2023): Charoenkwan P, et al.
- TIPred-MVFF (Scientific Reports, 2025): Shoombuatong W, et al.

实现内容：
1. 8种特征编码器：AAC, DPC, APAAC, PAAC, CTDC, CTDT, CTDD
2. Stacked Ensemble：KNN + RF + SVM + GB 作为 base models，LR 作为 meta
3. Multi-View Feature Fusion

作者：iGEM 工具探索
日期：2026-04-18
"""

import numpy as np
import pandas as pd
from typing import List, Union, Tuple, Optional
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.svm import SVC
from sklearn.neighbors import KNeighborsClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split, cross_val_predict
from sklearn.metrics import accuracy_score, matthews_corrcoef, roc_auc_score, classification_report
from sklearn.preprocessing import StandardScaler
import pickle
import warnings
warnings.filterwarnings('ignore')


# ============================================================================
# 氨基酸特性分组（用于 CTD 编码）
# ============================================================================

# 极性氨基酸
POLAR = 'SGNTE'
# 中性氨基酸
NEUTRAL = 'CAGP'
# 疏水氨基酸
HYDROPHOBIC = 'AVLIMFWY'
# 带正电荷氨基酸
POSITIVE = 'KRH'
# 带负电荷氨基酸
NEGATIVE = 'DE'

# 疏水性值（Kyte-Doolittle scale）
HYDROPHOBICITY = {
    'A': 1.8, 'R': -4.5, 'N': -3.5, 'D': -3.5, 'C': 2.5,
    'Q': -3.5, 'E': -3.5, 'G': -0.4, 'H': -3.2, 'I': 4.5,
    'L': 3.8, 'K': -3.9, 'M': 1.9, 'F': 2.8, 'P': -1.6,
    'S': -0.8, 'T': -0.7, 'W': -0.9, 'Y': -1.3, 'V': 4.2
}

# 标准化氨基酸列表
AMINO_ACIDS = 'ACDEFGHIKLMNPQRSTVWY'


# ============================================================================
# 特征编码器实现
# ============================================================================

class AAC:
    """氨基酸组成 (Amino Acid Composition) - 20维"""

    name = "AAC"
    dimension = 20

    @staticmethod
    def encode(sequences: List[str]) -> np.ndarray:
        """
        计算20种氨基酸的出现频率

        Returns:
            形状为 (n_sequences, 20) 的特征矩阵
        """
        features = []
        for seq in sequences:
            seq = seq.upper()
            length = len(seq)
            freq = np.zeros(20)
            for i, aa in enumerate(AMINO_ACIDS):
                freq[i] = seq.count(aa) / length if length > 0 else 0
            features.append(freq)
        return np.array(features)


class DPC:
    """二肽组成 (Dipeptide Composition) - 400维"""

    name = "DPC"
    dimension = 400

    @staticmethod
    def encode(sequences: List[str]) -> np.ndarray:
        """
        计算400种二肽组合的出现频率

        Returns:
            形状为 (n_sequences, 400) 的特征矩阵
        """
        dipeptides = [a1 + a2 for a1 in AMINO_ACIDS for a2 in AMINO_ACIDS]
        features = []
        for seq in sequences:
            seq = seq.upper()
            length = len(seq)
            freq = np.zeros(400)
            if length >= 2:
                count = length - 1
                for i in range(count):
                    dp = seq[i:i+2]
                    if dp in dipeptides:
                        idx = dipeptides.index(dp)
                        freq[idx] += 1
                freq /= count
            features.append(freq)
        return np.array(features)


class APAAC:
    """两亲性伪氨基酸组成 (Amphiphilic Pseudo AAC) - 20+λ维"""

    name = "APAAC"
    dimension = 21  # 20 + 1 (lambda默认=20时)

    def __init__(self, lambda_: int = 20):
        self.lambda_ = lambda_

    def encode(self, sequences: List[str]) -> np.ndarray:
        """
        计算两亲性伪氨基酸组成

        Args:
            lambda_: 伪因子数量（默认20）

        Returns:
            形状为 (n_sequences, 20+lambda) 的特征矩阵
        """
        features = []
        for seq in sequences:
            seq = seq.upper()
            length = len(seq)

            # 1. 氨基酸频率（20维）
            aa_freq = np.zeros(20)
            for i, aa in enumerate(AMINO_ACIDS):
                aa_freq[i] = seq.count(aa) / length if length > 0 else 0

            # 2. 两亲性因子（lambda维）
            if length >= 2:
                hydrophobicity_values = [HYDROPHOBICITY.get(aa, 0) for aa in seq]
                h_sum = sum(hydrophobicity_values)

                # 计算两亲性因子
                amphi = np.zeros(self.lambda_)
                for l in range(1, min(self.lambda_ + 1, length)):
                    # 序列的前半和后半的疏水性差异
                    front = hydrophobicity_values[:l]
                    back = hydrophobicity_values[-l:] if len(hydrophobicity_values) >= l else []
                    if front and back:
                        amphi[l-1] = abs(sum(front)/l - sum(back)/len(back))

                # 归一化
                if h_sum != 0:
                    amphi = amphi / abs(h_sum)

                features.append(np.concatenate([aa_freq, amphi]))
            else:
                features.append(np.concatenate([aa_freq, np.zeros(self.lambda_)]))

        return np.array(features)


class PAAC:
    """并行伪氨基酸组成 (Parallel Pseudo AAC) - 20+λ维"""

    name = "PAAC"
    dimension = 21  # 20 + 1

    def __init__(self, lambda_: int = 20):
        self.lambda_ = lambda_

    def encode(self, sequences: List[str]) -> np.ndarray:
        """
        计算并行伪氨基酸组成

        Args:
            lambda_: 伪因子数量（默认20）

        Returns:
            形状为 (n_sequences, 20+lambda) 的特征矩阵
        """
        features = []
        for seq in sequences:
            seq = seq.upper()
            length = len(seq)

            # 1. 氨基酸频率（20维）
            aa_freq = np.zeros(20)
            for i, aa in enumerate(AMINO_ACIDS):
                aa_freq[i] = seq.count(aa) / length if length > 0 else 0

            # 2. 伪因子（lambda维）
            if length >= 2:
                hydrophobicity_values = [HYDROPHOBICITY.get(aa, 0) for aa in seq]

                # 计算序列的疏水性相关因子
                pseudo = np.zeros(self.lambda_)
                for l in range(1, min(self.lambda_ + 1, length)):
                    # 相隔l的两个残基的疏水性相关性
                    corr = 0
                    count = 0
                    for i in range(length - l):
                        corr += hydrophobicity_values[i] * hydrophobicity_values[i + l]
                        count += 1
                    if count > 0:
                        pseudo[l-1] = corr / count

                features.append(np.concatenate([aa_freq, pseudo]))
            else:
                features.append(np.concatenate([aa_freq, np.zeros(self.lambda_)]))

        return np.array(features)


class CTDC:
    """CTD 组成 (Composition) - 13维

    标准 CTDC (Composition-Transition-Distribution, Composition) 描述符
    计算氨基酸各类别的组成比例
    """

    name = "CTDC"
    dimension = 13

    @staticmethod
    def encode(sequences: List[str]) -> np.ndarray:
        """
        计算组成描述符 - 13维

        Groups:
        1. polar (极性): S, G, N, T, E
        2. neutral (中性): C, A, G, P
        3. hydrophobic (疏水): V, L, I, M, F, W, Y
        4. positive (正电): K, R, H
        5. negative (负电): D, E
        6. aromatic (芳香): F, Y, W
        7. small (小): G, A, S, T, C

        Plus 6 additional subgroups:
        - hydrophobic: LVI (脂肪族疏水)
        - polar: ST (羟基)
        - positive: KR (强碱性)
        - negative: DE (酸性)
        - aromatic: FYW (芳香杂环)
        - neutral: AGC

        Returns:
            形状为 (n_sequences, 13) 的特征矩阵
        """
        features = []
        for seq in sequences:
            seq = seq.upper()
            length = len(seq)
            freq = np.zeros(13)

            freq[0] = sum(seq.count(aa) for aa in POLAR) / length if length > 0 else 0
            freq[1] = sum(seq.count(aa) for aa in NEUTRAL) / length if length > 0 else 0
            freq[2] = sum(seq.count(aa) for aa in HYDROPHOBIC) / length if length > 0 else 0
            freq[3] = sum(seq.count(aa) for aa in POSITIVE) / length if length > 0 else 0
            freq[4] = sum(seq.count(aa) for aa in NEGATIVE) / length if length > 0 else 0
            freq[5] = sum(seq.count(aa) for aa in 'FYWH') / length if length > 0 else 0
            freq[6] = sum(seq.count(aa) for aa in 'GASTC') / length if length > 0 else 0
            freq[7] = sum(seq.count(aa) for aa in 'LVI') / length if length > 0 else 0
            freq[8] = sum(seq.count(aa) for aa in 'ST') / length if length > 0 else 0
            freq[9] = sum(seq.count(aa) for aa in 'KR') / length if length > 0 else 0
            freq[10] = sum(seq.count(aa) for aa in 'DE') / length if length > 0 else 0
            freq[11] = sum(seq.count(aa) for aa in 'FYW') / length if length > 0 else 0
            freq[12] = sum(seq.count(aa) for aa in 'AGC') / length if length > 0 else 0

            features.append(freq)
        return np.array(features)


class CTDT:
    """CTD 转换 (Transition) - 13维

    计算相邻残基在不同类别间转换的频率
    """

    name = "CTDT"
    dimension = 13

    @staticmethod
    def encode(sequences: List[str]) -> np.ndarray:
        """计算转换描述符 - 13维"""
        features = []
        group_sets = [
            set(POLAR), set(NEUTRAL), set(HYDROPHOBIC), set(POSITIVE),
            set(NEGATIVE), set('FYWH'), set('GASTC'),
            set('LVI'), set('ST'), set('KR'), set('DE'), set('FYW'), set('AGC')
        ]

        for seq in sequences:
            seq = seq.upper()
            length = len(seq)
            trans = np.zeros(13)

            if length >= 2:
                for g_idx, group_set in enumerate(group_sets):
                    count = 0
                    total = 0
                    for i in range(length - 1):
                        curr_in = seq[i] in group_set
                        next_in = seq[i+1] in group_set
                        if curr_in != next_in:
                            count += 1
                        if curr_in or next_in:
                            total += 1
                    trans[g_idx] = count / total if total > 0 else 0

            features.append(trans)
        return np.array(features)


class CTDD:
    """CTD 分布 (Distribution) - 21维

    计算每组氨基酸在序列中的分布位置
    7组 x 3个位置（首、中、尾）= 21维
    """

    name = "CTDD"
    dimension = 21

    @staticmethod
    def encode(sequences: List[str]) -> np.ndarray:
        """计算分布描述符 - 21维"""
        features = []
        group_sets = [
            set(POLAR), set(NEUTRAL), set(HYDROPHOBIC), set(POSITIVE),
            set(NEGATIVE), set('FYWH'), set('GASTC')
        ]

        for seq in sequences:
            seq = seq.upper()
            length = len(seq)
            dist = np.zeros(21)

            for g_idx, group_set in enumerate(group_sets):
                positions = [i+1 for i, aa in enumerate(seq) if aa in group_set]
                base = g_idx * 3

                if positions:
                    dist[base] = positions[0] / length
                    dist[base + 1] = positions[len(positions) // 2] / length
                    dist[base + 2] = positions[-1] / length

            features.append(dist)
        return np.array(features)


# ============================================================================
# 特征编码器集合
# ============================================================================

class FeatureEncoder:
    """多视图特征编码器集合"""

    def __init__(self):
        self.encoders = {
            'AAC': AAC(),
            'DPC': DPC(),
            'APAAC': APAAC(lambda_=20),
            'PAAC': PAAC(lambda_=20),
            'CTDC': CTDC(),
            'CTDT': CTDT(),
            'CTDD': CTDD()
        }

    def encode_all(self, sequences: List[str]) -> Tuple[np.ndarray, List[str]]:
        """
        使用所有编码器提取特征

        Returns:
            (特征矩阵, 特征名称列表)
        """
        all_features = []
        feature_names = []

        for name, encoder in self.encoders.items():
            features = encoder.encode(sequences)
            all_features.append(features)

            # 生成特征名称
            dim = features.shape[1]
            if name in ['AAC']:
                feature_names.extend([f'{name}_{aa}' for aa in AMINO_ACIDS])
            elif name in ['DPC']:
                dipeptides = [a1 + a2 for a1 in AMINO_ACIDS for a2 in AMINO_ACIDS]
                feature_names.extend([f'{name}_{dp}' for dp in dipeptides])
            elif name in ['APAAC', 'PAAC']:
                feature_names.append(f'{name}_AA')
                feature_names.extend([f'{name}_lamda_{i}' for i in range(1, dim)])
            elif name == 'CTDC':
                feature_names.extend([f'{name}_polar', f'{name}_neutral', f'{name}_hydrophobic',
                                     f'{name}_positive', f'{name}_negative', f'{name}_aromatic',
                                     f'{name}_small', f'{name}_LVI', f'{name}_ST',
                                     f'{name}_KR', f'{name}_DE', f'{name}_FYW', f'{name}_AGC'])
            elif name == 'CTDT':
                feature_names.extend([f'{name}_polar', f'{name}_neutral', f'{name}_hydrophobic',
                                     f'{name}_positive', f'{name}_negative', f'{name}_aromatic',
                                     f'{name}_small', f'{name}_LVI', f'{name}_ST',
                                     f'{name}_KR', f'{name}_DE', f'{name}_FYW', f'{name}_AGC'])
            elif name == 'CTDD':
                group_names = ['polar', 'neutral', 'hydrophobic', 'positive', 'negative', 'aromatic', 'small']
                for i in range(7):
                    feature_names.extend([f'{name}_{group_names[i]}_first',
                                         f'{name}_{group_names[i]}_middle',
                                         f'{name}_{group_names[i]}_last'])
            else:
                feature_names.extend([f'{name}_{i}' for i in range(dim)])

        # 拼接所有特征
        combined = np.hstack(all_features)
        return combined, feature_names

    def get_feature_dimension(self) -> int:
        """获取总特征维度"""
        return sum(enc.dimension for enc in self.encoders.values())


# ============================================================================
# Stacked Ensemble 模型
# ============================================================================

class StackedEnsembleTIP:
    """
    Stacked Ensemble for TIP Prediction

    Base Models: KNN, RandomForest, SVM, GradientBoosting
    Meta Model: LogisticRegression
    """

    def __init__(self, random_state: int = 42):
        self.random_state = random_state

        # Base models
        self.base_models = {
            'knn': KNeighborsClassifier(n_neighbors=5),
            'rf': RandomForestClassifier(n_estimators=100, max_depth=10, random_state=random_state),
            'svm': SVC(kernel='rbf', probability=True, random_state=random_state),
            'gb': GradientBoostingClassifier(n_estimators=100, max_depth=5, random_state=random_state)
        }

        # Meta model
        self.meta_model = LogisticRegression(random_state=random_state, max_iter=1000)

        self.scaler = StandardScaler()
        self.is_trained = False
        self.feature_names = []

    def fit(self, X: np.ndarray, y: np.ndarray) -> dict:
        """
        训练 Stacked Ensemble

        Args:
            X: 特征矩阵 (n_samples, n_features)
            y: 标签 (n_samples,)

        Returns:
            训练结果字典
        """
        # 标准化
        X_scaled = self.scaler.fit_transform(X)

        # 使用交叉验证生成 base model predictions（避免数据泄露）
        n_samples = X_scaled.shape[0]
        meta_features = np.zeros((n_samples, len(self.base_models)))

        for i, (name, model) in enumerate(self.base_models.items()):
            # 交叉验证预测
            meta_features[:, i] = cross_val_predict(
                model, X_scaled, y, cv=5, method='predict_proba'
            )[:, 1]
            # 用全部数据训练最终模型
            model.fit(X_scaled, y)

        # 训练 meta model
        self.meta_model.fit(meta_features, y)
        self.is_trained = True

        # 计算训练集表现
        train_preds = self.meta_model.predict(meta_features)
        train_probs = self.meta_model.predict_proba(meta_features)[:, 1]

        results = {
            'accuracy': accuracy_score(y, train_preds),
            'mcc': matthews_corrcoef(y, train_preds),
            'auc': roc_auc_score(y, train_probs),
            'base_models': list(self.base_models.keys()),
            'n_features': X.shape[1]
        }

        return results

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """
        预测概率

        Args:
            X: 特征矩阵 (n_samples, n_features)

        Returns:
            TIP 概率 (n_samples,)
        """
        if not self.is_trained:
            raise RuntimeError("模型尚未训练")

        X_scaled = self.scaler.transform(X)

        # Base model predictions
        meta_features = np.zeros((X_scaled.shape[0], len(self.base_models)))
        for i, (name, model) in enumerate(self.base_models.items()):
            meta_features[:, i] = model.predict_proba(X_scaled)[:, 1]

        # Meta model prediction
        return self.meta_model.predict_proba(meta_features)[:, 1]

    def predict(self, X: np.ndarray, threshold: float = 0.5) -> np.ndarray:
        """
        预测分类

        Args:
            X: 特征矩阵
            threshold: 分类阈值

        Returns:
            分类标签 (0或1)
        """
        probs = self.predict_proba(X)
        return (probs >= threshold).astype(int)


# ============================================================================
# 完整 TIPred-MVFF 预测器
# ============================================================================

class TIPredictorMVFF:
    """
    TIPred-MVFF 完整实现

    基于多视图特征融合和堆叠集成的酪氨酸酶抑制肽预测器
    """

    def __init__(self, model_type: str = 'stacked'):
        """
        Args:
            model_type: 'stacked' (完整MVFF) 或 'simple' (单模型RF)
        """
        self.model_type = model_type
        self.feature_encoder = FeatureEncoder()

        if model_type == 'stacked':
            self.model = StackedEnsembleTIP()
        else:
            self.model = RandomForestClassifier(n_estimators=100, max_depth=10, random_state=42)

        self.scaler = StandardScaler()
        self.is_trained = False
        self.feature_names = []

    def extract_features(self, sequences: Union[str, List[str]]) -> np.ndarray:
        """
        提取多视图特征

        Args:
            sequences: 肽序列

        Returns:
            特征矩阵
        """
        if isinstance(sequences, str):
            sequences = [sequences]

        features, self.feature_names = self.feature_encoder.encode_all(sequences)
        return features

    def train(self, sequences: List[str], labels: List[int],
              test_size: float = 0.2, random_state: int = 42) -> dict:
        """
        训练模型

        Args:
            sequences: 肽序列列表
            labels: 标签（1=TIP, 0=非TIP）
            test_size: 测试集比例
            random_state: 随机种子

        Returns:
            训练结果
        """
        # 提取特征
        X = self.extract_features(sequences)
        y = np.array(labels)

        # 处理无效值
        mask = ~np.isnan(X).any(axis=1) & ~np.isinf(X).any(axis=1)
        X = X[mask]
        y = y[mask]

        if len(X) < 50:
            raise ValueError(f"有效样本数 ({len(X)}) 过少，至少需要50个样本")

        # 划分数据
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=random_state, stratify=y
        )

        # 标准化
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)

        if self.model_type == 'stacked':
            # Stacked Ensemble
            results = self.model.fit(X_train, y_train)
            y_pred = self.model.predict(X_test)
            y_prob = self.model.predict_proba(X_test)

            results.update({
                'test_accuracy': accuracy_score(y_test, y_pred),
                'test_mcc': matthews_corrcoef(y_test, y_pred),
                'test_auc': roc_auc_score(y_test, y_prob),
                'train_size': len(X_train),
                'test_size': len(X_test),
                'feature_dim': X.shape[1]
            })
        else:
            # 单模型
            self.model.fit(X_train_scaled, y_train)
            y_pred = self.model.predict(X_test_scaled)
            y_prob = self.model.predict_proba(X_test_scaled)[:, 1]

            results = {
                'accuracy': accuracy_score(y_test, y_pred),
                'mcc': matthews_corrcoef(y_test, y_pred),
                'auc': roc_auc_score(y_test, y_prob),
                'train_size': len(X_train),
                'test_size': len(X_test),
                'feature_dim': X.shape[1]
            }

        self.is_trained = True
        return results

    def predict(self, sequences: Union[str, List[str]]) -> np.ndarray:
        """
        预测 TIP 活性概率

        Args:
            sequences: 肽序列

        Returns:
            TIP 概率数组
        """
        if not self.is_trained:
            raise RuntimeError("模型尚未训练，请先调用 train() 方法")

        if isinstance(sequences, str):
            sequences = [sequences]

        X = self.extract_features(sequences)
        X_scaled = self.scaler.transform(X)

        if self.model_type == 'stacked':
            return self.model.predict_proba(X)
        else:
            return self.model.predict_proba(X_scaled)[:, 1]

    def predict_class(self, sequences: Union[str, List[str]],
                     threshold: float = 0.5) -> List[int]:
        """预测分类"""
        probs = self.predict(sequences)
        return [1 if p >= threshold else 0 for p in probs]

    def save(self, path: str):
        """保存模型"""
        with open(path, 'wb') as f:
            pickle.dump(self, f)
        print(f"模型已保存到：{path}")

    @staticmethod
    def load(path: str) -> 'TIPredictorMVFF':
        """加载模型"""
        with open(path, 'rb') as f:
            return pickle.load(f)


# ============================================================================
# 工具函数
# ============================================================================

def load_fasta(path: str) -> List[Tuple[str, str]]:
    """读取 FASTA 文件"""
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


# ============================================================================
# 命令行接口
# ============================================================================

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='TIPred-MVFF - 完整复现实现')
    parser.add_argument('--input', '-i', type=str, help='输入文件（FASTA 或 CSV）')
    parser.add_argument('--output', '-o', type=str, help='输出文件路径')
    parser.add_argument('--train', action='store_true', help='训练模式')
    parser.add_argument('--labels', type=str, help='训练标签文件')
    parser.add_argument('--model', '-m', type=str, help='模型文件路径')
    parser.add_argument('--save-model', type=str, help='保存训练后的模型')
    parser.add_argument('--type', type=str, default='stacked',
                        choices=['stacked', 'simple'],
                        help='模型类型：stacked(完整MVFF) 或 simple(单模型RF)')

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
        predictor = TIPredictorMVFF(model_type=args.type)
        results = predictor.train(sequences, labels)

        print("\n=== 训练结果 ===")
        print(f"模型类型：{args.type}")
        print(f"训练集大小：{results['train_size']}")
        print(f"测试集大小：{results['test_size']}")
        print(f"特征维度：{results['feature_dim']}")
        print(f"测试集准确率：{results.get('test_accuracy', results['accuracy']):.4f}")
        print(f"测试集 MCC：{results.get('test_mcc', results.get('mcc', 0)):.4f}")
        print(f"测试集 AUC：{results.get('test_auc', results.get('auc', 0)):.4f}")

        if args.save_model:
            predictor.save(args.save_model)

    elif args.model and args.input:
        # 预测模式
        predictor = TIPredictorMVFF.load(args.model)

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
        print("=== TIPred-MVFF 演示模式 ===\n")

        demo_seqs = ['YGGFL', 'GHK', 'PAL', 'ACDEFGHIK', 'LMNPQRSTVWY']

        predictor = TIPredictorMVFF(model_type='stacked')
        features, feature_names = predictor.feature_encoder.encode_all(demo_seqs)

        print(f"示例序列：{demo_seqs}")
        print(f"特征维度：{features.shape}")
        print(f"\n可用编码器：")
        for name, enc in predictor.feature_encoder.encoders.items():
            print(f"  - {name}: {enc.dimension} 维")

        print(f"\n=== 使用说明 ===")
        print("1. 训练：python tipredictor_full.py --train --input sequences.fasta --labels labels.csv --save-model model.pkl --type stacked")
        print("2. 预测：python tipredictor_full.py --model model.pkl --input queries.fasta --output results.csv")