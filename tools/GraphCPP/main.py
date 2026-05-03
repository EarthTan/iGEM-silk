"""
main.py - GraphCPP 微服务启动器
"""

import os
import uvicorn


def main():
    port = int(os.environ.get("PORT", "8009"))

    print(f"""
╔══════════════════════════════════════════════════════╗
║  GraphCPP 微服务                                     ║
║  图神经网络细胞穿膜肽预测 (GraphSAGE)                 ║
║                                                      ║
║  端口: {port}                                        ║
║  API 文档: http://localhost:{port}/docs              ║
╚══════════════════════════════════════════════════════╝
    """)

    from service import app

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        reload=False
    )


if __name__ == "__main__":
    main()