# INDEX.md
# `.backup` 文件索引

创建日期：2026-04-22
最后更新：2026-04-22

## 目录结构树

```
.backup/
├── INDEX.md
├── predictions.csv
├── user_dataset_empty.csv
├── user_dataset_esm2_t6_8M_UR50D_unified_320_dimension.csv
├── user_dataset_invalid_dim.csv
├── user_dataset_single.csv
└── verification_logs.txt
```

## 文件详细索引（按路径）

| 路径 | 类型 | 功能描述 | 简要内容 / 备注 |
|------|------|----------|----------------|
| `INDEX.md` | 文档 | 备份索引 | 记录 `.backup` 内文件清单与用途。 |
| `verification_logs.txt` | 日志 | 验证命令与关键输出 | 包含 uv 初始化、依赖安装、模型与LFS检查、预测与异常测试输出。 |
| `user_dataset_esm2_t6_8M_UR50D_unified_320_dimension.csv` | 数据 | 预测用最小输入样例 | 2 条样本、320 维嵌入，用于成功预测路径。 |
| `predictions.csv` | 数据 | 预测输出样例 | 模型输出标签（示例为 1,1）。 |
| `user_dataset_empty.csv` | 数据 | 异常输入样例 | 空样本 CSV（仅表头），用于空输入错误验证。 |
| `user_dataset_invalid_dim.csv` | 数据 | 异常输入样例 | 319 维嵌入，触发维度不匹配错误。 |
| `user_dataset_single.csv` | 数据 | 边界输入样例 | 单条 320 维样本，用于单样本预测验证。 |

## 重要说明
- 以上文件均为验证所生成/整理的最小复现实例。
- 预测逻辑基于 pLM4CPPs-main 模型文件 `models/ESM2-320/best_model_320.h5`。
