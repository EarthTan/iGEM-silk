"""
main.py
=======
MLCPP 服务启动入口。
"""

import os
import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8010"))
    print(f"Starting MLCPP service on port {port}...")
    uvicorn.run("service:app", host="0.0.0.0", port=port, reload=False)