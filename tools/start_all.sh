#!/bin/bash
# ============================================================================
# 一键启动所有 9 个微服务
# ============================================================================
#
# 用法:
#   ./tools/start_all.sh              # 启动所有服务
#   ./tools/start_all.sh stop         # 停止所有服务
#   ./tools/start_all.sh status       # 查看服务状态
#
# 服务列表:
#   AnOxPePred   8001  抗氧化肽预测 (CNN)
#   BepiPred-3.0 8002  B细胞表位预测 (ESM-2)
#   ToxinPred3   8003  肽毒性预测 (Extra Trees)
#   HemoPI2      8004  肽溶血性预测 (ESM-2)
#   MHCflurry    8005  MHC-I结合亲和力 (深度学习)
#   pLM4CPPs     8006  细胞穿透肽预测 (ESM-2 + CNN)
#   Tipred       8007  酪氨酸酶抑制肽预测 (Stacked Ensemble)
#   AlgPred2     8008  过敏原性预测 (Random Forest)
#   GraphCPP     8009  细胞穿透肽预测 (GraphSAGE GNN)
#   TemStaPro    8010  蛋白质热稳定性预测 (ProtT5-XL + MLP)
#   AlphaFold3   8201  3D结构预测 (Docker, GPU必需)
#   PEP-FOLD4    8202  肽从头结构预测 (Docker, CPU)
#   SASA         8101  溶剂可及表面积分析 (FreeSASA)
#
# 日志输出: tools/logs/<name>.log
# PID 文件: tools/logs/<name>.pid
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOGS_DIR="$SCRIPT_DIR/logs"

# 所有服务名（迭代顺序）
SERVICE_NAMES="anoxpepred bepipred3 toxinpred3 hemopi2 mhcflurry plm4cpps tipred algpred2 graphcpp temstapro alphafold3 pepfold4 sasa"

# ── 根据服务名查目录名 ──
dir_of() {
    case "$1" in
        anoxpepred)  echo "AnOxPePred"   ;;
        bepipred3)   echo "BepiPred-3.0" ;;
        toxinpred3)  echo "ToxinPred3"   ;;
        hemopi2)     echo "HemoPI2"      ;;
        mhcflurry)   echo "MHCflurry"    ;;
        plm4cpps)    echo "pLM4CPPs"     ;;
        tipred)      echo "Tipred"       ;;
        algpred2)    echo "algpred2"     ;;
        graphcpp)    echo "GraphCPP"     ;;
        temstapro)   echo "TemStaPro"    ;;
        alphafold3)  echo "AlphaFold3"   ;;
        pepfold4)    echo "PEP-FOLD4"    ;;
        sasa)        echo "SASA"         ;;
    esac
}

# ── 根据服务名查端口 ──
port_of() {
    case "$1" in
        anoxpepred)  echo "8001" ;;
        bepipred3)   echo "8002" ;;
        toxinpred3)  echo "8003" ;;
        hemopi2)     echo "8004" ;;
        mhcflurry)   echo "8005" ;;
        plm4cpps)    echo "8006" ;;
        tipred)      echo "8007" ;;
        algpred2)    echo "8008" ;;
        graphcpp)    echo "8009" ;;
        temstapro)   echo "8010" ;;
        alphafold3)  echo "8201" ;;
        pepfold4)    echo "8202" ;;
        sasa)        echo "8101" ;;
    esac
}

# ────────────────────────────────────────────────────────────
# 启动单个服务
# ────────────────────────────────────────────────────────────
start_one() {
    local name=$1
    local dir=$(dir_of "$name")
    local port=$(port_of "$name")
    local service_dir="$SCRIPT_DIR/$dir"
    local log_file="$LOGS_DIR/${name}.log"
    local pid_file="$LOGS_DIR/${name}.pid"

    if [ ! -d "$service_dir" ]; then
        echo "[ERROR] $name: 目录不存在 $service_dir"
        return 1
    fi

    # 检查是否已在运行
    if [ -f "$pid_file" ]; then
        local old_pid=$(cat "$pid_file")
        if kill -0 "$old_pid" 2>/dev/null; then
            echo "[WARN]  $name (port $port) 已在运行 (PID $old_pid)，跳过。"
            return 0
        fi
    fi

    # 检查 venv
    local python_bin="$service_dir/.venv/bin/python"
    if [ ! -f "$python_bin" ]; then
        echo "[ERROR] $name: 未找到虚拟环境 $python_bin"
        return 1
    fi

    mkdir -p "$LOGS_DIR"

    # 后台启动
    (
        cd "$service_dir"
        PORT=$port nohup "$python_bin" service.py > "$log_file" 2>&1 &
        echo $! > "$pid_file"
    )

    echo "[INFO]  $name 已启动 (port $port, PID $(cat "$pid_file"))"
}

# ────────────────────────────────────────────────────────────
# 停止单个服务
# ────────────────────────────────────────────────────────────
stop_one() {
    local name=$1
    local pid_file="$LOGS_DIR/${name}.pid"

    if [ ! -f "$pid_file" ]; then
        echo "[WARN]  $name: 未找到 PID 文件，跳过。"
        return 0
    fi

    local pid=$(cat "$pid_file")
    if kill -0 "$pid" 2>/dev/null; then
        kill "$pid" 2>/dev/null
        sleep 0.5
        if kill -0 "$pid" 2>/dev/null; then
            kill -9 "$pid" 2>/dev/null
        fi
        echo "[INFO]  $name (PID $pid) 已停止"
    else
        echo "[WARN]  $name: PID $pid 已不存在，清理。"
    fi
    rm -f "$pid_file"
}

# ────────────────────────────────────────────────────────────
# 检查单个服务状态
# ────────────────────────────────────────────────────────────
status_one() {
    local name=$1
    local port=$(port_of "$name")
    local pid_file="$LOGS_DIR/${name}.pid"

    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if kill -0 "$pid" 2>/dev/null; then
            local health=$(curl -s -o /dev/null -w "%{http_code}" --max-time 3 "http://127.0.0.1:$port/health" 2>/dev/null || echo "000")
            local label="healthy"
            local marker="OK"
            [ "$health" != "200" ] && marker="--" && label="running (HTTP $health)"
            printf "  [%s] %-12s port %s  PID %s  %s\n" "$marker" "$name" "$port" "$pid" "$label"
            return
        fi
    fi
    printf "  [--] %-12s port %s  stopped\n" "$name" "$port"
}

# ────────────────────────────────────────────────────────────
# 主逻辑
# ────────────────────────────────────────────────────────────
case "${1:-start}" in
    start)
        echo ""
        echo "  启动全部 iGEM-silk 微服务 …"
        echo "  ──────────────────────────────────"
        echo ""

        for name in $SERVICE_NAMES; do
            start_one "$name"
        done

        echo ""
        echo "  完成。查看状态: ./tools/start_all.sh status"
        echo "  查看日志 : tail -f tools/logs/<name>.log"
        echo "  停止服务 : ./tools/start_all.sh stop"
        echo ""
        ;;

    stop)
        echo ""
        echo "  停止全部微服务 …"
        echo ""

        for name in $SERVICE_NAMES; do
            stop_one "$name"
        done

        echo ""
        echo "  所有服务已停止。"
        echo ""
        ;;

    status)
        echo ""
        echo "  微服务状态："
        echo "  ──────────────────────────────────"
        for name in $SERVICE_NAMES; do
            status_one "$name"
        done
        echo ""
        ;;

    *)
        echo "用法: $0 {start|stop|status}"
        exit 1
        ;;
esac
