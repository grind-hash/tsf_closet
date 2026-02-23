#!/usr/bin/env bash
#
# TSF着せ替えゲーム ポータブル配布パッケージのビルドスクリプト (Ubuntu/Linux)
#
# Python Standalone + ビルド済みReactフロントエンドを同梱した
# ポータブルパッケージを作成します。
#
# Usage:
#   ./scripts/build_portable_linux.sh [OPTIONS]
#
# Options:
#   -v, --version VERSION       パッケージバージョン (デフォルト: "dev")
#   -o, --output-dir DIR        出力ディレクトリ (デフォルト: "./dist")
#   -p, --python-version VER    Pythonバージョン (デフォルト: "3.12.3")
#   -P, --provider PROVIDER     プロバイダー: novelai, selfhost, openrouter (デフォルト: novelai)
#   --no-archive                tar.gzパッケージ作成をスキップ
#   --skip-frontend             フロントエンドビルドをスキップ
#   --skip-python               Python環境構築をスキップ
#   --force                     既存出力を上書き
#   -h, --help                  ヘルプを表示
#
# Examples:
#   ./scripts/build_portable_linux.sh -v "1.0.0" -P novelai
#   ./scripts/build_portable_linux.sh -v "1.0.0" -P selfhost --force

set -euo pipefail

# ============================================
# デフォルト値
# ============================================

VERSION="dev"
OUTPUT_DIR="./dist"
PYTHON_VERSION="3.12.3"
PROVIDER="novelai"
NO_ARCHIVE=false
SKIP_FRONTEND=false
SKIP_PYTHON=false
FORCE=false

# ============================================
# ヘルパー関数
# ============================================

write_header() {
    echo ""
    echo "============================================"
    echo "  $1"
    echo "============================================"
    echo ""
}

write_step() {
    local step=$1
    local total=$2
    local message=$3
    echo "[$step/$total] $message"
}

write_success() {
    echo "      ✓ $1"
}

write_failure() {
    echo ""
    echo "  エラー: $1" >&2
    echo ""
    exit "${2:-1}"
}

format_size() {
    local bytes=$1
    if (( bytes >= 1073741824 )); then
        echo "$(echo "scale=1; $bytes / 1073741824" | bc) GB"
    elif (( bytes >= 1048576 )); then
        echo "$(echo "scale=1; $bytes / 1048576" | bc) MB"
    elif (( bytes >= 1024 )); then
        echo "$(echo "scale=1; $bytes / 1024" | bc) KB"
    else
        echo "$bytes B"
    fi
}

get_dir_size() {
    du -sb "$1" 2>/dev/null | cut -f1
}

# ============================================
# 引数パース
# ============================================

show_help() {
    head -30 "$0" | grep '^#' | sed 's/^# \?//'
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        -v|--version)       VERSION="$2";        shift 2 ;;
        -o|--output-dir)    OUTPUT_DIR="$2";      shift 2 ;;
        -p|--python-version) PYTHON_VERSION="$2"; shift 2 ;;
        -P|--provider)      PROVIDER="$2";        shift 2 ;;
        --no-archive)       NO_ARCHIVE=true;      shift ;;
        --skip-frontend)    SKIP_FRONTEND=true;   shift ;;
        --skip-python)      SKIP_PYTHON=true;     shift ;;
        --force)            FORCE=true;           shift ;;
        -h|--help)          show_help ;;
        *) write_failure "不明なオプション: $1" 1 ;;
    esac
done

# プロバイダー検証
case "$PROVIDER" in
    novelai|selfhost|openrouter) ;;
    *) write_failure "不正なプロバイダー: $PROVIDER (novelai, selfhost, openrouter のいずれかを指定)" 1 ;;
esac

# ============================================
# パス定義
# ============================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
FRONTEND_DIR="$REPO_ROOT/frontend"
BACKEND_DIR="$REPO_ROOT/backend"
TEMPLATES_DIR="$SCRIPT_DIR/templates"

PACKAGE_NAME="tsf_closet_portable_v${VERSION}_${PROVIDER}_linux"
OUTPUT_BASE="$(mkdir -p "$OUTPUT_DIR" && cd "$OUTPUT_DIR" && pwd)"
PACKAGE_DIR="$OUTPUT_BASE/$PACKAGE_NAME"
PYTHON_DIR="$PACKAGE_DIR/python_standalone"
PACKAGE_BACKEND_DIR="$PACKAGE_DIR/backend"
PACKAGE_STATIC_DIR="$PACKAGE_BACKEND_DIR/static"

TEMP_DIR="$OUTPUT_BASE/temp"
TOTAL_STEPS=6

# ============================================
# メイン処理
# ============================================

write_header "TSF着せ替えゲーム ポータブルパッケージビルド (Linux)"
echo "  バージョン:   $VERSION"
echo "  プロバイダー: $PROVIDER"
echo "  Python:       $PYTHON_VERSION"
echo ""

# 出力先チェック
if [[ -d "$PACKAGE_DIR" ]]; then
    if [[ "$FORCE" == true ]]; then
        echo "  既存の出力先を削除中: $PACKAGE_DIR"
        rm -rf "$PACKAGE_DIR"
    else
        write_failure "出力先が既に存在します: $PACKAGE_DIR\n       --force で上書きしてください。" 5
    fi
fi

mkdir -p "$PACKAGE_DIR"

# ============================================
# Step 1: フロントエンドビルド
# ============================================

write_step 1 $TOTAL_STEPS "フロントエンドをビルド中..."

if [[ "$SKIP_FRONTEND" == true ]]; then
    write_success "スキップ (--skip-frontend)"
else
    # npm チェック
    if ! command -v npm &>/dev/null; then
        write_failure "npmが見つかりません。Node.jsをインストールしてください。" 1
    fi

    pushd "$FRONTEND_DIR" > /dev/null

    # npm install
    if ! npm install 2>&1; then
        write_failure "npm install に失敗しました。" 2
    fi

    # vite build (型チェックをスキップしてビルドのみ実行)
    if ! npx vite build 2>&1; then
        write_failure "フロントエンドのビルドに失敗しました。" 2
    fi
    write_success "frontend/dist に出力完了"

    popd > /dev/null
fi

# ============================================
# Step 2: Python Standalone ダウンロード
# ============================================

write_step 2 $TOTAL_STEPS "Python Standalone をダウンロード中..."

if [[ "$SKIP_PYTHON" == true ]]; then
    write_success "スキップ (--skip-python)"
else
    # python-build-standalone のリリースから取得
    # https://github.com/indygreg/python-build-standalone
    PYTHON_MAJOR_MINOR="${PYTHON_VERSION%.*}"  # e.g. 3.12

    # detect architecture
    ARCH="$(uname -m)"
    case "$ARCH" in
        x86_64)  PBS_ARCH="x86_64-unknown-linux-gnu" ;;
        aarch64) PBS_ARCH="aarch64-unknown-linux-gnu" ;;
        *) write_failure "未対応アーキテクチャ: $ARCH" 3 ;;
    esac

    # Release tag format: 20240415 (date-based)
    # We use the install-only variant for smaller size
    PBS_FILENAME="cpython-${PYTHON_VERSION}+20240415-${PBS_ARCH}-install_only_stripped.tar.gz"
    PBS_URL="https://github.com/indygreg/python-build-standalone/releases/download/20240415/${PBS_FILENAME}"

    # Fallback: try install_only (non-stripped) if stripped not available
    PBS_FILENAME_FALLBACK="cpython-${PYTHON_VERSION}+20240415-${PBS_ARCH}-install_only.tar.gz"
    PBS_URL_FALLBACK="https://github.com/indygreg/python-build-standalone/releases/download/20240415/${PBS_FILENAME_FALLBACK}"

    mkdir -p "$TEMP_DIR"
    PYTHON_ARCHIVE="$TEMP_DIR/$PBS_FILENAME"

    if [[ ! -f "$PYTHON_ARCHIVE" ]]; then
        echo "  ダウンロード中: $PBS_URL"
        if ! curl -fSL -o "$PYTHON_ARCHIVE" "$PBS_URL" 2>/dev/null; then
            echo "  stripped版が見つかりません。install_only版を試行中..."
            PBS_FILENAME="$PBS_FILENAME_FALLBACK"
            PYTHON_ARCHIVE="$TEMP_DIR/$PBS_FILENAME"
            PBS_URL="$PBS_URL_FALLBACK"
            if ! curl -fSL -o "$PYTHON_ARCHIVE" "$PBS_URL" 2>/dev/null; then
                write_failure "Python Standaloneのダウンロードに失敗しました。\n  URL: $PBS_URL\n  手動でダウンロードし $TEMP_DIR に配置してください。" 3
            fi
        fi
    fi
    write_success "$PBS_FILENAME をダウンロード"

    # 展開 (tar.gz -> python/ directory)
    mkdir -p "$PYTHON_DIR"
    tar -xzf "$PYTHON_ARCHIVE" -C "$PYTHON_DIR" --strip-components=1
    write_success "python_standalone/ に展開完了"
fi

# ============================================
# Step 3: Python環境セットアップ
# ============================================

write_step 3 $TOTAL_STEPS "Python環境をセットアップ中..."

if [[ "$SKIP_PYTHON" == true ]]; then
    write_success "スキップ (--skip-python)"
else
    PYTHON_EXE="$PYTHON_DIR/bin/python3"

    if [[ ! -x "$PYTHON_EXE" ]]; then
        # python3.12 等の名前になっている場合のフォールバック
        PYTHON_EXE="$(find "$PYTHON_DIR/bin" -name 'python3*' -not -name '*-config' | head -1)"
        if [[ -z "$PYTHON_EXE" || ! -x "$PYTHON_EXE" ]]; then
            write_failure "Python実行ファイルが見つかりません: $PYTHON_DIR/bin/" 4
        fi
    fi

    # pip が同梱されていない場合 ensurepip or get-pip.py
    if ! "$PYTHON_EXE" -m pip --version &>/dev/null; then
        echo "  pip をインストール中..."
        if ! "$PYTHON_EXE" -m ensurepip --upgrade 2>/dev/null; then
            GET_PIP_PATH="$TEMP_DIR/get-pip.py"
            if [[ ! -f "$GET_PIP_PATH" ]]; then
                curl -fSL -o "$GET_PIP_PATH" "https://bootstrap.pypa.io/get-pip.py" || \
                    write_failure "get-pip.py のダウンロードに失敗しました。" 4
            fi
            "$PYTHON_EXE" "$GET_PIP_PATH" --no-warn-script-location || \
                write_failure "pip のインストールに失敗しました。" 4
        fi
    fi
    write_success "pip を確認/インストール"

    # requirements.txt を生成
    REQUIREMENTS_PATH="$BACKEND_DIR/requirements.txt"
    pushd "$REPO_ROOT" > /dev/null
    if command -v uv &>/dev/null; then
        uv pip compile "$BACKEND_DIR/pyproject.toml" -o "$REQUIREMENTS_PATH" || \
            write_failure "requirements.txt の生成に失敗しました。" 4
    else
        echo "  警告: uv が見つかりません。既存の requirements.txt を使用します。"
        if [[ ! -f "$REQUIREMENTS_PATH" ]]; then
            write_failure "requirements.txt が見つかりません。uv をインストールしてください。" 4
        fi
    fi
    popd > /dev/null

    # 依存ライブラリインストール
    "$PYTHON_EXE" -m pip install -r "$REQUIREMENTS_PATH" --no-warn-script-location 2>&1 || \
        write_failure "依存ライブラリのインストールに失敗しました。" 4

    PACKAGE_COUNT=$("$PYTHON_EXE" -m pip list --format=columns 2>/dev/null | tail -n +3 | wc -l)
    write_success "依存ライブラリをインストール ($PACKAGE_COUNT パッケージ)"
fi

# ============================================
# Step 4: バックエンドコピー
# ============================================

write_step 4 $TOTAL_STEPS "バックエンドをコピー中..."

# gateway/ をコピー
mkdir -p "$PACKAGE_BACKEND_DIR"
cp -r "$BACKEND_DIR/gateway" "$PACKAGE_BACKEND_DIR/"
# __pycache__ を削除
find "$PACKAGE_BACKEND_DIR/gateway" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
write_success "gateway/ をコピー"

# workflows/ をコピー
if [[ -d "$BACKEND_DIR/workflows" ]]; then
    cp -r "$BACKEND_DIR/workflows" "$PACKAGE_BACKEND_DIR/"
    write_success "workflows/ をコピー"
fi

# images/ をコピー
if [[ -d "$BACKEND_DIR/images" ]]; then
    cp -r "$BACKEND_DIR/images" "$PACKAGE_BACKEND_DIR/"
    write_success "images/ をコピー"
fi

# migrations/ をコピー
if [[ -d "$BACKEND_DIR/migrations" ]]; then
    cp -r "$BACKEND_DIR/migrations" "$PACKAGE_BACKEND_DIR/"
    find "$PACKAGE_BACKEND_DIR/migrations" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    write_success "migrations/ をコピー"
fi

# alembic.ini をコピー
if [[ -f "$BACKEND_DIR/alembic.ini" ]]; then
    cp "$BACKEND_DIR/alembic.ini" "$PACKAGE_BACKEND_DIR/"
    write_success "alembic.ini をコピー"
fi

# data/ ディレクトリ作成 (空)
mkdir -p "$PACKAGE_BACKEND_DIR/data/history_images"
mkdir -p "$PACKAGE_BACKEND_DIR/data/history_masks"
mkdir -p "$PACKAGE_BACKEND_DIR/data/preset_masks"
write_success "data/ ディレクトリを作成"

# ============================================
# Step 5: フロントエンド配置
# ============================================

write_step 5 $TOTAL_STEPS "フロントエンドを配置中..."

FRONTEND_DIST_DIR="$FRONTEND_DIR/dist"
if [[ ! -d "$FRONTEND_DIST_DIR" ]]; then
    if [[ "$SKIP_FRONTEND" == true ]]; then
        echo "      ! フロントエンドビルド出力が見つかりません (スキップ中のため無視)"
    else
        write_failure "フロントエンドのビルド出力が見つかりません: $FRONTEND_DIST_DIR" 2
    fi
else
    mkdir -p "$PACKAGE_STATIC_DIR"
    cp -r "$FRONTEND_DIST_DIR/"* "$PACKAGE_STATIC_DIR/"
    write_success "static/ に配置完了"
fi

# ============================================
# Step 6: 設定ファイル生成
# ============================================

write_step 6 $TOTAL_STEPS "設定ファイルを生成中..."

# config.env: base + provider をマージして生成
CONFIG_BASE_PATH="$TEMPLATES_DIR/config.base.env"
CONFIG_PROVIDER_PATH="$TEMPLATES_DIR/config.${PROVIDER}.env"
CONFIG_OUTPUT_PATH="$PACKAGE_DIR/config.env"

if [[ ! -f "$CONFIG_PROVIDER_PATH" ]]; then
    write_failure "プロバイダー設定ファイルが見つかりません: config.${PROVIDER}.env" 1
fi

{
    cat "$CONFIG_BASE_PATH"
    echo ""
    cat "$CONFIG_PROVIDER_PATH"
} > "$CONFIG_OUTPUT_PATH"
write_success "config.env を生成 (base + $PROVIDER)"

# start.sh
START_SH_TEMPLATE="$TEMPLATES_DIR/start.sh"
if [[ -f "$START_SH_TEMPLATE" ]]; then
    cp "$START_SH_TEMPLATE" "$PACKAGE_DIR/"
    chmod +x "$PACKAGE_DIR/start.sh"
    write_success "start.sh を生成"
fi

# stop.sh
STOP_SH_TEMPLATE="$TEMPLATES_DIR/stop.sh"
if [[ -f "$STOP_SH_TEMPLATE" ]]; then
    cp "$STOP_SH_TEMPLATE" "$PACKAGE_DIR/"
    chmod +x "$PACKAGE_DIR/stop.sh"
    write_success "stop.sh を生成"
fi

# README files (Linux versions → renamed for end users)
README_TEMPLATE="$TEMPLATES_DIR/README_linux.txt"
if [[ -f "$README_TEMPLATE" ]]; then
    cp "$README_TEMPLATE" "$PACKAGE_DIR/README.txt"
    write_success "README.txt を生成"
fi

README_UPDATE_TEMPLATE="$TEMPLATES_DIR/README_linux_update.txt"
if [[ -f "$README_UPDATE_TEMPLATE" ]]; then
    cp "$README_UPDATE_TEMPLATE" "$PACKAGE_DIR/README_update.txt"
    write_success "README_update.txt を生成"
fi

README_EN_TEMPLATE="$TEMPLATES_DIR/README_linux_en.txt"
if [[ -f "$README_EN_TEMPLATE" ]]; then
    cp "$README_EN_TEMPLATE" "$PACKAGE_DIR/README_en.txt"
    write_success "README_en.txt を生成"
fi

README_EN_UPDATE_TEMPLATE="$TEMPLATES_DIR/README_linux_en_update.txt"
if [[ -f "$README_EN_UPDATE_TEMPLATE" ]]; then
    cp "$README_EN_UPDATE_TEMPLATE" "$PACKAGE_DIR/README_en_update.txt"
    write_success "README_en_update.txt を生成"
fi

# LICENSE
LICENSE_TEMPLATE="$TEMPLATES_DIR/LICENSE"
if [[ -f "$LICENSE_TEMPLATE" ]]; then
    cp "$LICENSE_TEMPLATE" "$PACKAGE_DIR/"
    write_success "LICENSE を生成"
fi

# ============================================
# tar.gz パッケージ作成
# ============================================

if [[ "$NO_ARCHIVE" != true ]]; then
    echo ""
    echo "tar.gz パッケージを作成中..."
    ARCHIVE_PATH="$OUTPUT_BASE/${PACKAGE_NAME}.tar.gz"
    if [[ -f "$ARCHIVE_PATH" ]]; then
        rm -f "$ARCHIVE_PATH"
    fi
    tar -czf "$ARCHIVE_PATH" -C "$OUTPUT_BASE" "$PACKAGE_NAME"
    ARCHIVE_SIZE=$(stat -c%s "$ARCHIVE_PATH" 2>/dev/null || stat -f%z "$ARCHIVE_PATH" 2>/dev/null || echo 0)
    write_success "tar.gz パッケージを作成: $ARCHIVE_PATH"
fi

# ============================================
# 完了
# ============================================

PACKAGE_SIZE=$(get_dir_size "$PACKAGE_DIR")
FORMATTED_SIZE=$(format_size "$PACKAGE_SIZE")

write_header "ビルド完了！"
echo "  出力先:       $PACKAGE_DIR"
echo "  サイズ:       $FORMATTED_SIZE"
if [[ "$NO_ARCHIVE" != true ]]; then
    ARCHIVE_FORMATTED=$(format_size "$ARCHIVE_SIZE")
    echo "  アーカイブ:   $ARCHIVE_PATH ($ARCHIVE_FORMATTED)"
fi
echo ""
