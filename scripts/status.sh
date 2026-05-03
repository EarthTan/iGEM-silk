#!/usr/bin/env bash
# ============================================================================
# scripts/status.sh
# ============================================================================
# 检查所有服务状态
#
# 用法：
#   ./scripts/status.sh
# ============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
PID_DIR="$PROJECT_ROOT/.pids"
LOG_DIR="$PROJECT_ROOT/logs"

echo "═══════════════════════════════════════════════════════════"
echo "  iGEM-silk 服务状态"
echo "═══════════════════════════════════════════════════════════"

# 定义所有服务
declare -A PORTS=(
    ["orchestrator"]=8000
    ["anoxpepred"]=8001
    ["bepipred3"]=8002
    ["toxipred3"]=8003
    ["hemopi2"]=8004
    ["mhcflurry"]=8005
    ["plm4cpps"]=8006
    ["tipred"]=8007
    ["algpred2"]=8008
    ["graphcpp"]=8009
    ["mlcpp"]=8010
)

for name in "${!PORTS[@]}"; do
    port="${PORTS[$name]}"
    pid=$(lsof -ti:$port 2>/dev/null || true)

    if [ -n "$pid" ]; then
        # 检查进程是否响应
        if curl -s -o /dev/null -w "%{http_code}" "http://localhost:$port/health" 2>/dev/null | grep -q "200"; then
            echo "✅ $name (端口 $port, PID: $pid) - 运行中"
        else
            echo "⚠️  $name (端口 $port, PID: $pid) - 端口被占用但服务未响应"
        fi
    else
        # 检查 PID 文件
        pidfile="$PID_DIR/${name}.pid"
        if [ -f "$pidfile" ]; then
            pid=$(cat "$pidfile")
            echo "❌ $name (PID: $pid) - 进程已停止但 PID 文件存在"
        else
            echo "⬜ $name (端口 $port) - 未运行"
        fi
    fi
done

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  帮助命令"
echo "═══════════════════════════════════════════════════════════"
echo "  启动所有工具: ./scripts/start_all_tools.sh"
echo "  启动编排器:   ./scripts/start_orchestrator.sh"
echo "  停止所有服务: ./scripts/stop_all.sh"
echo "  查看日志:     tail -f logs/<tool_name>.log"