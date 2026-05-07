# 微服务

微服务大致分为三类：

- fasta评分服务 (fasta_service)：输入fasta，输出针对肽的评分结果
- 3D结构生成 (3d_service)：输入fasta，输出三维结构模型（PDB）
- PDB评分服务 (pdb_service)：输入PDB文件（和其他信息），输入评分结果

### 端口分配表

| 服务 | 类型 | 作用 | 端口 |
|------|------|------|------|
| AnOxPePred | fasta_service | 基于深度学习模型预测肽序列的抗氧化活性， | 8001 |
| BepiPred-3.0 | fasta_service | 线性 B 细胞表位预测工具 | 8002 |
| ToxinPred3 | fasta_service | 毒性预测工具 | 8003 |
| HemoPI2 | fasta_service | 溶血性预测工具 | 8004 |
| MHCflurry | fasta_service | MHC I类肽结合亲和力预测工具 | 8005 |
| pLM4CPPs | fasta_service | 细胞穿膜肽预测工具 | 8006 |
| TIPred | fasta_service | 预测酪氨酸酶抑制肽(TIP)活性 | 8007 |
| AlgPred2 | fasta_service | 过敏原性风险预测工具 - 基于随机森林模型的蛋白过敏原性预测 | 8008 |
| GraphCPP | fasta_service | 基于图神经网络(GNN)的细胞穿透肽(Cell-Penetrating Peptide, CPP)预测工具 | 8009 |
| MLCPP | fasta_service | 细胞穿透肽预测工具 | 8010 |
