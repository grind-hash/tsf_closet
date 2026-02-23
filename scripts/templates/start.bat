@echo off
chcp 65001 >nul 2>&1
setlocal EnableDelayedExpansion

REM ============================================
REM   TSF Closet - Launcher
REM ============================================

REM Set current directory to script location
cd /d "%~dp0"

REM Default values
set "PORT=8000"
set "LOG_LEVEL=INFO"

REM ============================================
REM   Load config file
REM ============================================

if exist "config.env" (
    for /f "usebackq tokens=1,* delims==" %%A in ("config.env") do (
        set "line=%%A"
        if not "!line:~0,1!"=="#" (
            if not "%%A"=="" (
                set "%%A=%%B"
            )
        )
    )
)

REM ============================================
REM   Banner
REM ============================================

echo.
echo ============================================
echo   TSF Closet
echo ============================================
echo.

REM ============================================
REM   Environment checks (goto style to avoid UTF-8 parse issues)
REM ============================================

REM Check Python embeddable
if not exist "python_embeded\python.exe" goto :err_python

REM Check backend
if not exist "backend\gateway\app.py" goto :err_backend

REM Check frontend
if not exist "backend\static\index.html" goto :err_frontend

REM Check VC++ Redistributable (MSVCP140.dll)
where msvcp140.dll >nul 2>&1
if errorlevel 1 goto :err_vcredist

REM ============================================
REM   Port conflict detection
REM ============================================

set "PORT_IN_USE=0"
for /f "tokens=*" %%a in ('netstat -ano 2^>nul ^| find "LISTENING" ^| find ":%PORT%"') do (
    set "PORT_IN_USE=1"
)
if "!PORT_IN_USE!"=="1" goto :err_port

REM ============================================
REM   Database migration
REM ============================================

if not exist "backend\data" mkdir "backend\data"

REM Run alembic upgrade head every launch (handles both first-run and updates)
echo データベースマイグレーションを確認中...
cd /d "%~dp0backend"
if exist "migrations\versions" (
    "%~dp0python_embeded\python.exe" -m alembic upgrade head 2>nul
    if errorlevel 1 (
        echo   警告: マイグレーションでエラーが発生しましたが、起動を続行します。
    ) else (
        echo   データベースは最新です。
    )
)
cd /d "%~dp0"
echo.

REM ============================================
REM   Start server
REM ============================================

echo サーバーをポート %PORT% で起動中...
echo.

REM Set environment variables
set "ENV_FILE=%~dp0config.env"

REM Launch server in background
cd /d "%~dp0backend"
start "" /b "%~dp0python_embeded\python.exe" -m uvicorn gateway.app:app --host 127.0.0.1 --port %PORT% --log-level %LOG_LEVEL%
cd /d "%~dp0"

REM ============================================
REM   Health check wait loop
REM ============================================

echo サーバーの起動を待機中...

set "HEALTH_OK=0"
for /L %%i in (1,1,30) do (
    if !HEALTH_OK!==0 (
        timeout /t 1 /nobreak >nul 2>&1
        "%~dp0python_embeded\python.exe" -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:%PORT%/health')" >nul 2>&1
        if !ERRORLEVEL!==0 (
            set "HEALTH_OK=1"
        )
    )
)

if "!HEALTH_OK!"=="0" goto :health_warn
goto :health_ok

:health_warn
echo.
echo ============================================
echo   TSF Closet - 警告
echo ============================================
echo.
echo   警告: サーバーが30秒以内に応答しませんでした。
echo          起動に時間がかかっている可能性があります。
echo          ブラウザで http://127.0.0.1:%PORT% にアクセスしてみてください。
echo.
goto :running

:health_ok
echo.
echo ============================================
echo   起動完了！
echo   ブラウザで http://127.0.0.1:%PORT% を開きます
echo.
echo   終了するには:
echo   - このウィンドウを閉じる
echo   - または Ctrl+C を押す
echo ============================================
echo.

REM Open browser
start "" "http://127.0.0.1:%PORT%"
goto :running

REM ============================================
REM   Server running - wait loop
REM ============================================

:running
echo サーバー実行中... 終了するにはこのウィンドウを閉じるか Ctrl+C を押してください。
echo.

:wait_loop
timeout /t 2 /nobreak >nul 2>&1
set "STILL_RUNNING=0"
for /f "tokens=*" %%a in ('netstat -ano 2^>nul ^| find "LISTENING" ^| find ":%PORT%"') do (
    set "STILL_RUNNING=1"
)
if "!STILL_RUNNING!"=="1" goto :wait_loop

echo.
echo サーバーが停止しました。
goto :cleanup

REM ============================================
REM   Error handlers (outside main flow)
REM ============================================

:err_python
echo ============================================
echo   TSF Closet - エラー
echo ============================================
echo.
echo   エラー: Python実行環境が見つかりません。
echo          python_embeded\python.exe を確認してください。
echo.
pause
exit /b 1

:err_backend
echo ============================================
echo   TSF Closet - エラー
echo ============================================
echo.
echo   エラー: バックエンドが見つかりません。
echo          backend\gateway\app.py を確認してください。
echo.
pause
exit /b 1

:err_frontend
echo ============================================
echo   TSF Closet - エラー
echo ============================================
echo.
echo   エラー: フロントエンドが見つかりません。
echo          backend\static\index.html を確認してください。
echo.
pause
exit /b 1

:err_port
echo ============================================
echo   TSF Closet - エラー
echo ============================================
echo.
echo   エラー: ポート %PORT% は既に使用中です。
echo          他のアプリケーションを終了するか、
echo          config.env で PORT を変更してください。
echo.
pause
exit /b 1

:err_vcredist
echo ============================================
echo   TSF Closet - エラー
echo ============================================
echo.
echo   エラー: Microsoft Visual C++ 再頒布可能パッケージが
echo          インストールされていません。
echo.
echo   以下のURLからダウンロードしてインストールしてください:
echo   https://aka.ms/vs/17/release/vc_redist.x64.exe
echo.
echo   インストール後、もう一度 start.bat を実行してください。
echo.
pause
exit /b 1

REM ============================================
REM   Cleanup
REM ============================================

:cleanup
taskkill /f /im python.exe /fi "WINDOWTITLE eq TSF*" >nul 2>&1
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| find "LISTENING" ^| find ":%PORT%"') do (
    taskkill /f /pid %%a >nul 2>&1
)

echo.
echo 終了しました。
pause
