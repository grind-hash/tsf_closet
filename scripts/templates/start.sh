#!/usr/bin/env bash
# ============================================
#   TSF Closet - Launcher (Linux)
# ============================================

set -euo pipefail

# Set current directory to script location
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Default values
PORT=8000
LOG_LEVEL="info"

# ============================================
#   Load config file
# ============================================

if [[ -f "config.env" ]]; then
    while IFS='=' read -r key value; do
        # Skip comments and empty lines
        [[ -z "$key" || "$key" == \#* ]] && continue
        # Remove leading/trailing whitespace
        key="$(echo "$key" | xargs)"
        value="$(echo "$value" | xargs)"
        export "$key=$value"
    done < "config.env"
fi

# Re-read PORT and LOG_LEVEL after config load
PORT="${PORT:-8000}"
LOG_LEVEL="${LOG_LEVEL:-info}"

# ============================================
#   Banner
# ============================================

echo ""
echo "============================================"
echo "  TSF Closet (Linux)"
echo "============================================"
echo ""

# ============================================
#   Environment checks
# ============================================

# Check Python standalone
PYTHON_EXE="$SCRIPT_DIR/python_standalone/bin/python3"
if [[ ! -x "$PYTHON_EXE" ]]; then
    # Fallback: try versioned python
    PYTHON_EXE="$(find "$SCRIPT_DIR/python_standalone/bin" -name 'python3*' -not -name '*-config' 2>/dev/null | head -1)"
    if [[ -z "$PYTHON_EXE" || ! -x "$PYTHON_EXE" ]]; then
        echo "============================================"
        echo "  TSF Closet - エラー"
        echo "============================================"
        echo ""
        echo "  エラー: Python実行環境が見つかりません。"
        echo "         python_standalone/bin/python3 を確認してください。"
        echo ""
        exit 1
    fi
fi

# Check backend
if [[ ! -f "backend/gateway/app.py" ]]; then
    echo "============================================"
    echo "  TSF Closet - エラー"
    echo "============================================"
    echo ""
    echo "  エラー: バックエンドが見つかりません。"
    echo "         backend/gateway/app.py を確認してください。"
    echo ""
    exit 1
fi

# Check frontend
if [[ ! -f "backend/static/index.html" ]]; then
    echo "============================================"
    echo "  TSF Closet - エラー"
    echo "============================================"
    echo ""
    echo "  エラー: フロントエンドが見つかりません。"
    echo "         backend/static/index.html を確認してください。"
    echo ""
    exit 1
fi

# ============================================
#   Port conflict detection
# ============================================

if command -v ss &>/dev/null; then
    if ss -tlnp 2>/dev/null | grep -q ":${PORT} "; then
        echo "============================================"
        echo "  TSF Closet - エラー"
        echo "============================================"
        echo ""
        echo "  エラー: ポート ${PORT} は既に使用中です。"
        echo "         他のアプリケーションを終了するか、"
        echo "         config.env で PORT を変更してください。"
        echo ""
        exit 1
    fi
elif command -v lsof &>/dev/null; then
    if lsof -i ":${PORT}" -sTCP:LISTEN &>/dev/null; then
        echo "============================================"
        echo "  TSF Closet - エラー"
        echo "============================================"
        echo ""
        echo "  エラー: ポート ${PORT} は既に使用中です。"
        echo "         他のアプリケーションを終了するか、"
        echo "         config.env で PORT を変更してください。"
        echo ""
        exit 1
    fi
fi

# ============================================
#   Database initialization
# ============================================

mkdir -p "backend/data"

if [[ ! -f "backend/data/database.sqlite" ]]; then
    echo "データベースを初期化中..."
    if [[ -d "backend/migrations/versions" ]]; then
        pushd "backend" > /dev/null
        "$PYTHON_EXE" -m alembic upgrade head 2>/dev/null || true
        popd > /dev/null
    fi
    echo "  データベース初期化完了"
    echo ""
fi

# ============================================
#   Start server
# ============================================

echo "サーバーをポート ${PORT} で起動中..."
echo ""

# Set environment variables
export ENV_FILE="$SCRIPT_DIR/config.env"

# Launch server in background
cd "$SCRIPT_DIR/backend"
"$PYTHON_EXE" -m uvicorn gateway.app:app --host 127.0.0.1 --port "$PORT" --log-level "$LOG_LEVEL" &
SERVER_PID=$!
cd "$SCRIPT_DIR"

# ============================================
#   Health check wait loop
# ============================================

echo "サーバーの起動を待機中..."

HEALTH_OK=0
for i in $(seq 1 30); do
    sleep 1
    if "$PYTHON_EXE" -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:${PORT}/health')" &>/dev/null; then
        HEALTH_OK=1
        break
    fi
done

if [[ "$HEALTH_OK" -eq 0 ]]; then
    echo ""
    echo "============================================"
    echo "  TSF Closet - 警告"
    echo "============================================"
    echo ""
    echo "  警告: サーバーが30秒以内に応答しませんでした。"
    echo "        起動に時間がかかっている可能性があります。"
    echo "        ブラウザで http://127.0.0.1:${PORT} にアクセスしてみてください。"
    echo ""
else
    echo ""
    echo "============================================"
    echo "  起動完了！"
    echo "  ブラウザで http://127.0.0.1:${PORT} を開いてください"
    echo ""
    echo "  終了するには:"
    echo "  - このターミナルで Ctrl+C を押す"
    echo "============================================"
    echo ""

    # Open browser (try xdg-open, then common browsers)
    if command -v xdg-open &>/dev/null; then
        xdg-open "http://127.0.0.1:${PORT}" &>/dev/null &
    elif command -v sensible-browser &>/dev/null; then
        sensible-browser "http://127.0.0.1:${PORT}" &>/dev/null &
    fi
fi

# ============================================
#   Wait for server process
# ============================================

# Trap SIGINT/SIGTERM to clean up
cleanup() {
    echo ""
    echo "サーバーを停止中..."
    if kill -0 "$SERVER_PID" 2>/dev/null; then
        kill "$SERVER_PID" 2>/dev/null
        wait "$SERVER_PID" 2>/dev/null || true
    fi
    echo "終了しました。"
    exit 0
}

trap cleanup SIGINT SIGTERM

echo "サーバー実行中... 終了するには Ctrl+C を押してください。"
echo ""

# Wait for server process to finish
wait "$SERVER_PID" 2>/dev/null || true

echo ""
echo "サーバーが停止しました。"
