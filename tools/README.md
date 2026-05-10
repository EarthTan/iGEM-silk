# 微服务

微服务大致分为三类：

- fasta评分服务 (fasta_service)：输入fasta，输出针对肽的评分结果
- 3D结构生成 (3d_service)：输入fasta，输出三维结构模型（PDB）
- PDB评分服务 (pdb_service)：输入PDB文件（和其他信息），输入评分结果

### 微服务设计原则

1. **原作优先**。优先使用工具原作者的代码、设计思路、模型和实现方法，做到原汁原味。这代表了项目的学术背景，以及避免AI幻觉和搪塞工作。（不能偷工减料！）
2. **环境兼容。**本项目的主要开发环境是最新版MacOS，但是实际使用的时候有高性能 Ubuntu（RTX5880）可以使用。因此，（仅仅）对于 **可以进行 CUDA 等加速的工具**：配置dockerfile，以方便在有GPU的设备上快速配置合适环境；代码本身做到自动检测系统和环境，在检测到存在可用环境的时候使用GPU加速；而在GPU环境不可用的时候，也能普通运行。
3. **统一接口**。使用统一的接口，和 `main/` 下的核心框架相衔接，保证 `main/` 能够正常调用。
4. **并发与高通量**。尽量做到高性能高速度预测，提高可处理数量级的范围。


### 端口分配表

| 服务 | 类型 | 作用 | 环境 | 端口 |
|------|------|------|------|------|
| AnOxPePred | fasta_service | 基于深度学习模型预测肽序列的抗氧化活性， | GPU加速（可选） | 8001 |
| BepiPred-3.0 | fasta_service | 线性 B 细胞表位预测工具 |  | 8002 |
| ToxinPred3 | fasta_service | 毒性预测工具 |  | 8003 |
| HemoPI2 | fasta_service | 溶血性预测工具 |  | 8004 |
| MHCflurry | fasta_service | MHC I类肽结合亲和力预测工具 |  | 8005 |
| pLM4CPPs | fasta_service | 细胞穿膜肽预测工具 |  | 8006 |
| TIPred | fasta_service | 预测酪氨酸酶抑制肽(TIP)活性 |  | 8007 |
| AlgPred2 | fasta_service | 过敏原性风险预测工具 - 基于随机森林模型的蛋白过敏原性预测 |  | 8008 |
| GraphCPP | fasta_service | 基于图神经网络(GNN)的细胞穿透肽(Cell-Penetrating Peptide, CPP)预测工具 |  | 8009 |
| MLCPP | fasta_service | 细胞穿透肽预测工具 |  | 8010 |
