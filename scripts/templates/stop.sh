#!/usr/bin/env bash
# ============================================
#   TSF Closet - Stop Script (Linux)
# ============================================

set -euo pipefail

# Set current directory to script location
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Default port
PORT=8000

# Load config to get PORT
if [[ -f "config.env" ]]; then
    while IFS='=' read -r key value; do
        [[ -z "$key" || "$key" == \#* ]] && continue
        key="$(echo "$key" | xargs)"
        value="$(echo "$value" | xargs)"
        case "$key" in
            PORT) PORT="$value" ;;
        esac
    done < "config.env"
fi

echo ""
echo "============================================"
echo "  TSF Closet - 停止"
echo "============================================"
echo ""

# Find and kill process listening on PORT
FOUND=0

if command -v ss &>/dev/null; then
    # Use ss to find PIDs
    PIDS=$(ss -tlnp "( sport = :${PORT} )" 2>/dev/null | grep -oP 'pid=\K[0-9]+' | sort -u)
elif command -v lsof &>/dev/null; then
    # Use lsof to find PIDs
    PIDS=$(lsof -t -i ":${PORT}" -sTCP:LISTEN 2>/dev/null || true)
else
    # Fallback to fuser
    PIDS=$(fuser "${PORT}/tcp" 2>/dev/null || true)
fi

if [[ -n "$PIDS" ]]; then
    for pid in $PIDS; do
        echo "  PID $pid を終了しています..."
        kill "$pid" 2>/dev/null || true
        FOUND=1
    done
fi

if [[ "$FOUND" -eq 0 ]]; then
    echo "  ポート ${PORT} で実行中のサーバーは見つかりませんでした。"
else
    # Wait a moment and verify
    sleep 1
    echo ""
    echo "  サーバーを停止しました。"
fi

echo ""
