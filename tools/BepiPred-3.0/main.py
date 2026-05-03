"""
main.py - BepiPred-3.0 微服务启动器

Usage:
    python main.py                    # 启动服务（默认端口 8002）
    PORT=8003 python main.py          # 指定端口

Port 端口分配（参考 services/orchestrator/registry.py）：
    8002: bepipred3

注意：BepiPred-3.0 依赖 ESM-2 模型，首次运行会下载约 2.5GB 的模型权重
"""

import os
import uvicorn


def main():
    port = int(os.environ.get("PORT", "8002"))

    print(f"""
╔══════════════════════════════════════════════════════╗
║  BepiPred-3.0 微服务                                  ║
║  B 细胞表位预测工具（ESM-2 + 深度学习集成）            ║
║                                                      ║
║  端口: {port}                                        ║
║  API 文档: http://localhost:{port}/docs              ║
║                                                      ║
║  ⚠️  首次运行将下载 ESM-2 模型（约 2.5GB）            ║
╚══════════════════════════════════════════════════════╝
    """)

    # 直接导入 app 对象（不是字符串）
    from service import app

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        reload=False
    )


if __name__ == "__main__":
    main()