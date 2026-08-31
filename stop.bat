@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

echo ========================================
echo   Smart Test Platform - Stop All
echo ========================================
echo.

:: Step 1: Kill by port (find ALL PIDs, kill with /T for process tree)
echo [1/2] Killing processes on ports 5011, 5012, 5013...
for %%p in (5011 5012 5013) do (
    set "FOUND=0"
    for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":%%p " ^| findstr "LISTENING"') do (
        set "FOUND=1"
        echo   Killing PID %%a on port %%p ...
        taskkill /PID %%a /F /T >nul 2>&1
    )
    if "!FOUND!"=="0" echo   Port %%p not running
)

:: Step 2: Also kill by window title (covers `start "title"` launched processes)
echo   Killing by window title...
taskkill /FI "WINDOWTITLE eq LangGraph-5011*" /F /T >nul 2>&1
taskkill /FI "WINDOWTITLE eq FastAPI-5012*" /F /T >nul 2>&1
taskkill /FI "WINDOWTITLE eq NextJS-5013*" /F /T >nul 2>&1

:: Step 3: Wait for TCP sockets to fully release
echo [2/2] Waiting for ports to release...
set "ALL_FREE=0"
for /l %%i in (1,1,10) do (
    if "!ALL_FREE!"=="0" (
        ping -n 2 127.0.0.1 >nul 2>&1
        netstat -ano 2>nul | findstr ":5011 .*LISTENING :5012 .*LISTENING :5013 .*LISTENING" >nul 2>&1
        if !errorlevel! neq 0 (
            set "ALL_FREE=1"
            echo   All ports released.
        )
    )
)
if "!ALL_FREE!"=="0" (
    echo   [WARN] Some ports still showing LISTEN state ^(zombie sockets^)
    echo   Waiting 5 more seconds...
    ping -n 6 127.0.0.1 >nul 2>&1
)

echo.
echo All services stopped.
