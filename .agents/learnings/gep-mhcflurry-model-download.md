---
title: MHCflurry 模型下载失败处理
type: gep
created: 2026-05-17
status: verified
---

## 问题

MHCflurry 在 Docker build 时模型下载失败，运行时 `Class1AffinityPredictor.load()` 报错：
```
RuntimeError: Missing MHCflurry downloadable file: /app/tools/MHCflurry/models/models_class1_pan/models.combined
```

## 原因

1. **Dockerfile 缺少 `--release` 参数**：设置了 `MHCFLURRY_DOWNLOADS_DIR` 自定义路径后，`mhcflurry-downloads fetch` 必须加 `--release 2.2.0`，否则报 "No release defined"
2. **`|| exit 0` 吞掉错误**：Dockerfile 用 `|| exit 0` 让 build 不报错，但模型实际上没下载
3. **GitHub 在国内不可达**：模型 URL `https://github.com/openvax/mhcflurry/releases/download/pre-2.0/models_class1_pan.selected.20200610.tar.bz2` 在国内直接连接超时

## 修复方法

### 方法 1：通过 ghproxy 下载（推荐，国内网络适用）

```bash
# 从 ghproxy 镜像下载模型 (156MB)
curl -L -o /tmp/mhcflurry_models.tar.bz2 \
  "https://ghproxy.net/https://github.com/openvax/mhcflurry/releases/download/pre-2.0/models_class1_pan.selected.20200610.tar.bz2"

# 解压
mkdir -p /tmp/mhcflurry_models
cd /tmp/mhcflurry_models
tar xjf /tmp/mhcflurry_models.tar.bz2

# 容器内目录结构
# /app/tools/MHCflurry/models/models_class1_pan/
#   ├── models.combined/       ← 权重文件在此目录
#   ├── additional_alleles.txt
#   └── ...

# 复制到容器
docker cp /tmp/mhcflurry_models/. mhcflurry:/app/tools/MHCflurry/models/models_class1_pan/
```

### 方法 2：Dockerfile 用 COPY

```dockerfile
# 替代 RUN mhcflurry-downloads fetch，因为网络限制
COPY models/ /app/tools/MHCflurry/models/
```

注意本地需要有完整的 `models/` 目录结构。

### 方法 3：在线下载（有 GitHub 访问时）

```dockerfile
RUN mkdir -p /app/tools/MHCflurry/models && \
    MHCFLURRY_DOWNLOADS_DIR=/app/tools/MHCflurry/models \
    mhcflurry-downloads fetch models_class1_pan --release 2.2.0
```

## 验证

```bash
# 检查健康状态
curl http://127.0.0.1:8005/health
# 应返回: model_loaded=true, alleles=14883

# 测试预测
curl -X POST http://127.0.0.1:8005/predict/batch \
  -H "Content-Type: application/json" \
  -d '{"sequences": [{"sequence": "ACGTKLMN", "peptide_id": "test001"}]}'
```

## 参考

- MHCflurry 版本: 2.2.1
- 模型文件: `models_class1_pan.selected.20200610.tar.bz2` (156MB)
- 模型路径: `/app/tools/MHCflurry/models/models_class1_pan/models.combined/`
- 等位基因数: 14,883
