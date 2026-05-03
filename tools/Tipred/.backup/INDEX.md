# INDEX.md
# `.backup` 文件索引

创建日期：2026-04-22
最后更新：2026-04-22

## 目录结构树

```
.backup/
├── mvff_model.pkl
├── predict_output.txt
├── queries.fasta
├── execution_log.txt
└── INDEX.md
```

## 文件详细索引（按路径）

| 路径 | 类型 | 功能描述 | 简要内容 / 备注 |
|------|------|----------|----------------|
| `mvff_model.pkl` | 模型 | TIPred-MVFF 训练后的模型 | 由 TIPredictorMVFF 训练保存，用于 CLI 加载（当前加载失败：scripts 模块路径问题）。 |
| `predict_output.txt` | 日志 | 训练与预测摘要 | 记录训练集/测试集规模、特征维度、预测概率。 |
| `queries.fasta` | 输入 | CLI 预测输入 | 两条肽序列：YGGFL 与 RRRRR。 |
| `execution_log.txt` | 日志 | 关键命令输出 | uv sync、演示模式、训练/预测错误与成功输出。 |
| `INDEX.md` | 文档 | 备份索引 | 记录 .backup 内容与用途。 |
