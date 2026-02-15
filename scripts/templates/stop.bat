@echo off
chcp 65001 >nul 2>&1
setlocal EnableDelayedExpansion

REM ============================================
REM   TSF Closet - Stop Script
REM ============================================

REM Set current directory to script location
cd /d "%~dp0"

REM Default port
set "PORT=8000"

REM Load config to get PORT
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

echo.
echo ============================================
echo   TSF Closet - 停止
echo ============================================
echo.

REM Find and kill process listening on PORT
set "FOUND=0"
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| find "LISTENING" ^| find ":%PORT%"') do (
    set "FOUND=1"
    echo   PID %%a を終了しています...
    taskkill /f /pid %%a >nul 2>&1
)

if "!FOUND!"=="0" (
    echo   ポート %PORT% で実行中のサーバーは見つかりませんでした。
) else (
    echo.
    echo   サーバーを停止しました。
)

echo.
pause
