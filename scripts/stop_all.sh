#!/usr/bin/env bash
# ============================================================================
# scripts/stop_all.sh
# ============================================================================
# 停止所有工具微服务和 Orchestrator
#
# 用法：
#   ./scripts/stop_all.sh
# ============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
PID_DIR="$PROJECT_ROOT/.pids"

echo "═══════════════════════════════════════════════════════════"
echo "  停止所有服务"
echo "═══════════════════════════════════════════════════════════"

# 停止工具服务
if [ -d "$PID_DIR" ]; then
    for pidfile in "$PID_DIR"/*.pid; do
        if [ -f "$pidfile" ]; then
            name=$(basename "$pidfile" .pid)
            pid=$(cat "$pidfile")

            if kill -0 "$pid" 2>/dev/null; then
                echo "🛑 停止 $name (PID: $pid)..."
                kill "$pid" 2>/dev/null || true
            else
                echo "⏭️  $name 已停止"
            fi

            rm -f "$pidfile"
        fi
    done
fi

# 停止可能运行的 uvicorn 进程（按端口）
for port in 8000 8001 8002 8003 8004 8005 8006 8007 8008 8009 8010; do
    pid=$(lsof -ti:$port 2>/dev/null || true)
    if [ -n "$pid" ]; then
        echo "🛑 停止端口 $port 上的进程 (PID: $pid)..."
        kill $pid 2>/dev/null || true
    fi
done

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  所有服务已停止"
echo "═══════════════════════════════════════════════════════════"