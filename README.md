本项目还未启用docker

# 前端服务启动指南







# 后端服务启动指南

### 启动工具微服务
开发中

### 启动主服务

开发模式（自动重载）
```bash
uvicorn services.api.main:app --reload --port 8000
```

生产模式
```bash
uvicorn services.api.main:app --host 0.0.0.0 --port 8000 --workers 4
```

## 验证

应用启动后访问：

- **API 文档** → http://localhost:8000/docs
- **根路由** → http://localhost:8000/
- **健康检查** → http://localhost:8000/health
- **工具列表** → http://localhost:8000/tools

