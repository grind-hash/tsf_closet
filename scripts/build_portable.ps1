<#
.SYNOPSIS
    TSF着せ替えゲーム ポータブル配布パッケージのビルドスクリプト

.DESCRIPTION
    Python Embeddable + ビルド済みReactフロントエンドを同梱した
    ポータブルパッケージを作成します。

.PARAMETER Version
    パッケージバージョン (デフォルト: "dev")

.PARAMETER OutputDir
    出力ディレクトリ (デフォルト: "./dist")

.PARAMETER PythonVersion
    Python Embeddableバージョン (デフォルト: "3.12.3")

.PARAMETER NoZip
    ZIPパッケージ作成をスキップ

.PARAMETER SkipFrontend
    フロントエンドビルドをスキップ

.PARAMETER SkipPython
    Python環境構築をスキップ

.PARAMETER Provider
    画像生成プロバイダー。config.base.env と config.{Provider}.env をマージして config.env を生成。
    指定可能: novelai, selfhost, openrouter (デフォルト: novelai)

.PARAMETER Force
    既存出力を上書き

.EXAMPLE
    .\scripts\build_portable.ps1 -Version "1.0.0" -Provider novelai

.EXAMPLE
    .\scripts\build_portable.ps1 -Version "1.0.0" -Provider selfhost
#>

[CmdletBinding()]
param(
    [string]$Version = "dev",
    [string]$OutputDir = "./dist",
    [string]$PythonVersion = "3.12.3",
    [ValidateSet("novelai", "selfhost", "openrouter")]
    [string]$Provider = "novelai",
    [switch]$NoZip,
    [switch]$SkipFrontend,
    [switch]$SkipPython,
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ============================================
# ヘルパー関数
# ============================================

function Write-Header {
    param([string]$Message)
    Write-Host ""
    Write-Host "============================================" -ForegroundColor Cyan
    Write-Host "  $Message" -ForegroundColor Cyan
    Write-Host "============================================" -ForegroundColor Cyan
    Write-Host ""
}

function Write-Step {
    param([int]$Step, [int]$Total, [string]$Message)
    Write-Host "[$Step/$Total] $Message" -ForegroundColor Yellow
}

function Write-Success {
    param([string]$Message)
    Write-Host "      $([char]0x2713) $Message" -ForegroundColor Green
}

function Write-Failure {
    param([string]$Message, [int]$ExitCode = 1)
    Write-Host ""
    Write-Host "  エラー: $Message" -ForegroundColor Red
    Write-Host ""
    exit $ExitCode
}

function Get-DirectorySize {
    param([string]$Path)
    $size = (Get-ChildItem -Path $Path -Recurse -File | Measure-Object -Property Length -Sum).Sum
    return $size
}

function Format-FileSize {
    param([long]$Bytes)
    if ($Bytes -ge 1GB) { return "{0:N1} GB" -f ($Bytes / 1GB) }
    if ($Bytes -ge 1MB) { return "{0:N1} MB" -f ($Bytes / 1MB) }
    if ($Bytes -ge 1KB) { return "{0:N1} KB" -f ($Bytes / 1KB) }
    return "$Bytes B"
}

# ============================================
# パス定義
# ============================================

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$FrontendDir = Join-Path $RepoRoot "frontend"
$BackendDir = Join-Path $RepoRoot "backend"
$TemplatesDir = Join-Path $PSScriptRoot "templates"

$PackageName = "tsf_closet_portable_v${Version}_${Provider}"
$OutputBase = Resolve-Path -Path $OutputDir -ErrorAction SilentlyContinue
if (-not $OutputBase) {
    $OutputBase = Join-Path $RepoRoot $OutputDir
}
$PackageDir = Join-Path $OutputBase $PackageName
$PythonDir = Join-Path $PackageDir "python_embeded"
$PackageBackendDir = Join-Path $PackageDir "backend"
$PackageStaticDir = Join-Path $PackageBackendDir "static"

$TempDir = Join-Path $OutputBase "temp"
$TotalSteps = 6

# ============================================
# メイン処理
# ============================================

Write-Header "TSF着せ替えゲーム ポータブルパッケージビルド"
Write-Host "  バージョン: $Version" -ForegroundColor White
Write-Host "  プロバイダー: $Provider" -ForegroundColor White
Write-Host ""

# 出力先チェック
if (Test-Path $PackageDir) {
    if ($Force) {
        Write-Host "  既存の出力先を削除中: $PackageDir" -ForegroundColor Gray
        Remove-Item -Path $PackageDir -Recurse -Force
    } else {
        Write-Failure "出力先が既に存在します: $PackageDir`n       -Force で上書きしてください。" 5
    }
}

# 出力ディレクトリ作成
New-Item -ItemType Directory -Path $PackageDir -Force | Out-Null

# ============================================
# Step 1: フロントエンドビルド
# ============================================

Write-Step 1 $TotalSteps "フロントエンドをビルド中..."

if ($SkipFrontend) {
    Write-Success "スキップ (-SkipFrontend)"
} else {
    # npm チェック
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        Write-Failure "npmが見つかりません。Node.jsをインストールしてください。" 1
    }

    Push-Location $FrontendDir
    try {
        # npm install
        $npmOutput = & cmd /c "npm install" 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Host $npmOutput -ForegroundColor Gray
            Write-Failure "npm install に失敗しました。" 2
        }

        # vite build (型チェックをスキップしてビルドのみ実行)
        $viteOutput = & cmd /c "npx vite build" 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Host $viteOutput -ForegroundColor Gray
            Write-Failure "フロントエンドのビルドに失敗しました。" 2
        }
        Write-Success "frontend/dist に出力完了"
    }
    finally {
        Pop-Location
    }
}

# ============================================
# Step 2: Python Embeddable ダウンロード
# ============================================

Write-Step 2 $TotalSteps "Python Embeddable をダウンロード中..."

if ($SkipPython) {
    Write-Success "スキップ (-SkipPython)"
} else {
    $PythonMajorMinor = ($PythonVersion -split '\.')[0..1] -join ''
    $PythonZipName = "python-$PythonVersion-embed-amd64.zip"
    $PythonUrl = "https://www.python.org/ftp/python/$PythonVersion/$PythonZipName"
    New-Item -ItemType Directory -Path $TempDir -Force | Out-Null
    $PythonZipPath = Join-Path $TempDir $PythonZipName

    if (-not (Test-Path $PythonZipPath)) {
        try {
            Invoke-WebRequest -Uri $PythonUrl -OutFile $PythonZipPath -UseBasicParsing
        }
        catch {
            Write-Failure "Python Embeddableのダウンロードに失敗しました。URL: $PythonUrl" 3
        }
    }
    Write-Success "$PythonZipName をダウンロード"

    # 展開
    New-Item -ItemType Directory -Path $PythonDir -Force | Out-Null
    Expand-Archive -Path $PythonZipPath -DestinationPath $PythonDir -Force
    Write-Success "python_embeded/ に展開完了"
}

# ============================================
# Step 3: Python環境セットアップ
# ============================================

Write-Step 3 $TotalSteps "Python環境をセットアップ中..."

if ($SkipPython) {
    Write-Success "スキップ (-SkipPython)"
} else {
    $PythonMajorMinor = ($PythonVersion -split '\.')[0..1] -join ''

    # python312._pth を編集して import site を有効化
    $PthFile = Join-Path $PythonDir "python${PythonMajorMinor}._pth"
    if (Test-Path $PthFile) {
        $pthContent = Get-Content $PthFile -Raw
        # "#import site" のコメントを外す
        $pthContent = $pthContent -replace '#\s*import site', 'import site'
        # Lib\site-packages を追加 (なければ)
        if ($pthContent -notmatch 'Lib\\site-packages') {
            $pthContent = $pthContent.TrimEnd() + "`nLib\site-packages`n"
        }
        Set-Content -Path $PthFile -Value $pthContent -NoNewline
    }
    Write-Success "_pth ファイルを更新 (import site 有効化)"

    # get-pip.py をダウンロード・実行
    $GetPipUrl = "https://bootstrap.pypa.io/get-pip.py"
    $GetPipPath = Join-Path $TempDir "get-pip.py"
    if (-not (Test-Path $GetPipPath)) {
        try {
            Invoke-WebRequest -Uri $GetPipUrl -OutFile $GetPipPath -UseBasicParsing
        }
        catch {
            Write-Failure "get-pip.py のダウンロードに失敗しました。" 4
        }
    }

    $PythonExe = Join-Path $PythonDir "python.exe"
    $pipOutput = & $PythonExe $GetPipPath --no-warn-script-location 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host $pipOutput -ForegroundColor Gray
        Write-Failure "pip のインストールに失敗しました。" 4
    }
    Write-Success "pip をインストール"

    # requirements.txt を生成
    $RequirementsPath = Join-Path $BackendDir "requirements.txt"
    Push-Location $RepoRoot
    try {
        $uvOutput = & uv pip compile "$BackendDir/pyproject.toml" -o $RequirementsPath 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Host $uvOutput -ForegroundColor Gray
            Write-Failure "requirements.txt の生成に失敗しました。" 4
        }
    }
    finally {
        Pop-Location
    }

    # 依存ライブラリインストール
    $installOutput = & $PythonExe -m pip install -r $RequirementsPath --no-warn-script-location 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host $installOutput -ForegroundColor Gray
        Write-Failure "依存ライブラリのインストールに失敗しました。" 4
    }

    $PackageCount = (& $PythonExe -m pip list --format=columns 2>$null | Select-Object -Skip 2 | Measure-Object).Count
    Write-Success "依存ライブラリをインストール ($PackageCount パッケージ)"
}

# ============================================
# Step 4: バックエンドコピー
# ============================================

Write-Step 4 $TotalSteps "バックエンドをコピー中..."

# gateway/ をコピー
$GatewaySrc = Join-Path $BackendDir "gateway"
$GatewayDst = Join-Path $PackageBackendDir "gateway"
Copy-Item -Path $GatewaySrc -Destination $GatewayDst -Recurse -Force
# __pycache__ を削除
Get-ChildItem -Path $GatewayDst -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
Write-Success "gateway/ をコピー"

# workflows/ をコピー
$WorkflowsSrc = Join-Path $BackendDir "workflows"
if (Test-Path $WorkflowsSrc) {
    $WorkflowsDst = Join-Path $PackageBackendDir "workflows"
    Copy-Item -Path $WorkflowsSrc -Destination $WorkflowsDst -Recurse -Force
    Write-Success "workflows/ をコピー"
}

# images/ をコピー
$ImagesSrc = Join-Path $BackendDir "images"
if (Test-Path $ImagesSrc) {
    $ImagesDst = Join-Path $PackageBackendDir "images"
    Copy-Item -Path $ImagesSrc -Destination $ImagesDst -Recurse -Force
    Write-Success "images/ をコピー"
}

# migrations/ をコピー
$MigrationsSrc = Join-Path $BackendDir "migrations"
if (Test-Path $MigrationsSrc) {
    $MigrationsDst = Join-Path $PackageBackendDir "migrations"
    Copy-Item -Path $MigrationsSrc -Destination $MigrationsDst -Recurse -Force
    # __pycache__ を削除
    Get-ChildItem -Path $MigrationsDst -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
    Write-Success "migrations/ をコピー"
}

# alembic.ini をコピー
$AlembicIniSrc = Join-Path $BackendDir "alembic.ini"
if (Test-Path $AlembicIniSrc) {
    Copy-Item -Path $AlembicIniSrc -Destination $PackageBackendDir -Force
    Write-Success "alembic.ini をコピー"
}

# data/ ディレクトリ作成（空）
$DataDir = Join-Path $PackageBackendDir "data"
New-Item -ItemType Directory -Path $DataDir -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $DataDir "history_images") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $DataDir "history_masks") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $DataDir "preset_masks") -Force | Out-Null
Write-Success "data/ ディレクトリを作成"

# ============================================
# Step 5: フロントエンド配置
# ============================================

Write-Step 5 $TotalSteps "フロントエンドを配置中..."

$FrontendDistDir = Join-Path $FrontendDir "dist"
if (-not (Test-Path $FrontendDistDir)) {
    if ($SkipFrontend) {
        Write-Host "      ! フロントエンドビルド出力が見つかりません (スキップ中のため無視)" -ForegroundColor Yellow
    } else {
        Write-Failure "フロントエンドのビルド出力が見つかりません: $FrontendDistDir" 2
    }
} else {
    New-Item -ItemType Directory -Path $PackageStaticDir -Force | Out-Null
    Copy-Item -Path "$FrontendDistDir\*" -Destination $PackageStaticDir -Recurse -Force
    Write-Success "static/ に配置完了"
}

# ============================================
# Step 6: 設定ファイル生成
# ============================================

Write-Step 6 $TotalSteps "設定ファイルを生成中..."

# config.env: base + provider をマージして生成
$ConfigBasePath = Join-Path $TemplatesDir "config.base.env"
$ConfigProviderPath = Join-Path $TemplatesDir "config.$Provider.env"
$ConfigOutputPath = Join-Path $PackageDir "config.env"

$configContent = @()
if (Test-Path $ConfigBasePath) {
    $configContent += Get-Content $ConfigBasePath -Encoding UTF8
}
if (Test-Path $ConfigProviderPath) {
    $configContent += ""  # 空行で区切り
    $configContent += Get-Content $ConfigProviderPath -Encoding UTF8
} else {
    Write-Failure "プロバイダー設定ファイルが見つかりません: config.$Provider.env" 1
}
$configContent | Set-Content -Path $ConfigOutputPath -Encoding UTF8
Write-Success "config.env を生成 (base + $Provider)"

# start.bat
$StartBatTemplate = Join-Path $TemplatesDir "start.bat"
if (Test-Path $StartBatTemplate) {
    Copy-Item -Path $StartBatTemplate -Destination $PackageDir -Force
    Write-Success "start.bat を生成"
}

# stop.bat
$StopBatTemplate = Join-Path $TemplatesDir "stop.bat"
if (Test-Path $StopBatTemplate) {
    Copy-Item -Path $StopBatTemplate -Destination $PackageDir -Force
    Write-Success "stop.bat を生成"
}

# README.txt
$ReadmeTemplate = Join-Path $TemplatesDir "README.txt"
if (Test-Path $ReadmeTemplate) {
    Copy-Item -Path $ReadmeTemplate -Destination $PackageDir -Force
    Write-Success "README.txt を生成"
}

# LICENSE
$LicenseTemplate = Join-Path $TemplatesDir "LICENSE"
if (Test-Path $LicenseTemplate) {
    Copy-Item -Path $LicenseTemplate -Destination $PackageDir -Force
    Write-Success "LICENSE を生成"
}

# ============================================
# ZIP パッケージ作成
# ============================================

if (-not $NoZip) {
    Write-Host ""
    Write-Host "ZIPパッケージを作成中..." -ForegroundColor Yellow
    $ZipPath = Join-Path $OutputBase "$PackageName.zip"
    if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force }
    Compress-Archive -Path $PackageDir -DestinationPath $ZipPath -CompressionLevel Optimal
    Write-Success "ZIPパッケージを作成: $ZipPath"
}

# ============================================
# 完了
# ============================================

$PackageSize = Get-DirectorySize -Path $PackageDir
$FormattedSize = Format-FileSize -Bytes $PackageSize

Write-Header "ビルド完了！"
Write-Host "  出力先:     $PackageDir" -ForegroundColor White
Write-Host "  サイズ:     $FormattedSize" -ForegroundColor White
if (-not $NoZip) {
    $ZipSize = (Get-Item $ZipPath).Length
    Write-Host "  ZIPファイル: $ZipPath ($(Format-FileSize -Bytes $ZipSize))" -ForegroundColor White
}
Write-Host ""
