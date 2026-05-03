"""
main.py - AnOxPePred 微服务启动器

Usage:
    python main.py                    # 启动服务（默认端口 8001）
    PORT=8002 python main.py          # 指定端口启动

Port 端口分配（参考 services/orchestrator/registry.py）：
    8001: anoxpepred
"""

import os
import uvicorn


def main():
    port = int(os.environ.get("PORT", "8001"))

    print(f"""
╔══════════════════════════════════════════════════════╗
║  AnOxPePred 微服务                                   ║
║  抗氧化肽预测工具 (CNN 深度学习模型)                 ║
║                                                      ║
║  端口: {port}                                        ║
║  API 文档: http://localhost:{port}/docs              ║
╚══════════════════════════════════════════════════════╝
    """)

    # 导入 app 对象（不是字符串），这样可以正常工作
    from service import app

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        reload=False
    )


if __name__ == "__main__":
    main()