# GraphCPP 模型架构详解

## 模型配置

最佳超参数(见 `config.py`):

```python
BEST_PARAMETERS = {
    'act': 'prelu',
    'conv_aggr': 'sum',
    'conv_dropout': 0.05,
    'has_bn': False,
    'has_l2norm': False,
    'layer_fingerprints': 1,
    'fingerprint_type': 'topological',
    'hidden_channels': 128,
    'layer_type': 'sageconv',
    'layers_pre_mp': 1,
    'mp_layers': 2,
    'layers_post_mp': 1,
    'pooling': 'mean',
    'stage_type': 'stack',
    'learning_rate': 0.001,
    'weight_decay': 'cosine'
}
```

## 核心组件

### 1. 分子图特征化

使用 `MolGraphConvFeaturizer`:
- `use_edges=True`: 包含键类型特征
- `use_chirality=True`: 包含手性信息

### 2. 图卷积层

使用 GraphSAGE 卷积层:
- 2层消息传递(`mp_layers=2`)
- 聚合邻居信息更新节点表示

### 3. 特征融合

1. 节点嵌入经过多层图卷积
2. 结合拓扑指纹(通过 `fp_dict` 生成)
3. Mean pooling 得到全局图表示
4. 全连接层输出预测

## 训练目标

- **任务**: 二分类(CPP vs Non-CPP)
- **损失函数**: BCEWithLogitsLoss
- **评估指标**: MCC, AUC, Accuracy, F1

## 性能指标

| 指标 | 值 |
|------|-----|
| Val MCC | 0.6683 |
| Val AUC | 0.9288 |
| Val Accuracy | 0.8310 |
| Test MCC | 0.5787 |
| Test AUC | 0.8459 |

## 模型文件

```
model/
├── checkpoints/
│   └── epoch=22-step=69.ckpt  # 预训练模型
├── hparams.yaml                 # 模型超参数
└── metrics.csv                  # 训练指标
```