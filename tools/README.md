# 微服务

微服务大致分为三类：

- fasta评分服务 (fasta_service)：输入fasta，输出针对肽的评分结果
- 3D结构生成 (3d_service)：输入fasta，输出三维结构模型（PDB）
- PDB评分服务 (pdb_service)：输入PDB文件（和其他信息），输入评分结果

### 端口分配表

| 服务 | 类型 | 端口 |
|------|------|------|
| AnOxPePred | fasta_service | 8001 |
| BepiPred-3.0 | fasta_service | 8002 |
| ToxinPred3 | fasta_service | 8003 |
| HemoPI2 | fasta_service | 8004 |
| MHCflurry | fasta_service | 8005 |
| pLM4CPPs | fasta_service | 8006 |
| TIPred | fasta_service | 8007 |
| AlgPred2 | fasta_service | 8008 |
| GraphCPP | fasta_service | 8009 |
| MLCPP | fasta_service | 8010 |
