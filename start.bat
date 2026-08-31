@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

echo ========================================
echo   Smart Test Platform - Start All
echo ========================================
echo.

:: Navigate to project directory
set "ROOT=%~dp0"
cd /d "%ROOT%"

:: --- Step 1: Stop any existing instances ---
echo [1/4] Cleaning up old processes...
for %%p in (5011 5012 5013) do (
    for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":%%p " ^| findstr "LISTENING"') do (
        taskkill /PID %%a /F /T >nul 2>&1
    )
)
:: Also kill by window title
taskkill /FI "WINDOWTITLE eq LangGraph-5011*" /F /T >nul 2>&1
taskkill /FI "WINDOWTITLE eq FastAPI-5012*" /F /T >nul 2>&1
taskkill /FI "WINDOWTITLE eq NextJS-5013*" /F /T >nul 2>&1
echo   Waiting for ports to release...
ping -n 4 127.0.0.1 >nul 2>&1

:: --- Step 2: Start LangGraph API Server (port 5011) ---
echo [2/4] Starting LangGraph API Server (port 5011)...
start "LangGraph-5011" /min "%ROOT%.venv\Scripts\python.exe" start_server.py
set "READY=0"
for /l %%i in (1,1,45) do (
    if "!READY!"=="0" (
        ping -n 2 127.0.0.1 >nul 2>&1
        netstat -ano 2>nul | findstr ":5011 " | findstr "LISTENING" >nul 2>&1
        if !errorlevel! equ 0 (
            set "READY=1"
            echo   [OK] LangGraph API running on port 5011
        )
    )
)
if "!READY!"=="0" echo   [!!] LangGraph API failed to start

:: --- Step 3: Start FastAPI Server (port 5012) ---
echo [3/4] Starting FastAPI Server (port 5012)...
start "FastAPI-5012" /min "%ROOT%.venv\Scripts\python.exe" -m uvicorn src.app.fastapi_app:app --host 0.0.0.0 --port 5012
set "READY=0"
for /l %%i in (1,1,15) do (
    if "!READY!"=="0" (
        ping -n 2 127.0.0.1 >nul 2>&1
        netstat -ano 2>nul | findstr ":5012 " | findstr "LISTENING" >nul 2>&1
        if !errorlevel! equ 0 (
            set "READY=1"
            echo   [OK] FastAPI running on port 5012
        )
    )
)
if "!READY!"=="0" echo   [!!] FastAPI failed to start

:: --- Step 4: Start Next.js Frontend (port 5013) ---
echo [4/4] Starting Next.js Frontend (port 5013)...
cd /d "%ROOT%webui"
start "NextJS-5013" /min cmd /c "npm run dev"
cd /d "%ROOT%"
set "READY=0"
for /l %%i in (1,1,20) do (
    if "!READY!"=="0" (
        ping -n 2 127.0.0.1 >nul 2>&1
        netstat -ano 2>nul | findstr ":5013 " | findstr "LISTENING" >nul 2>&1
        if !errorlevel! equ 0 (
            set "READY=1"
            echo   [OK] Next.js running on port 5013
        )
    )
)
if "!READY!"=="0" echo   [!!] Next.js failed to start

echo.
echo ========================================
echo   All services started!
echo   LangGraph API:  http://localhost:5011
echo   FastAPI:        http://localhost:5012
echo   Frontend:       http://localhost:5013
echo ========================================
echo.
echo   NOTE: Set FastAPI URL to http://localhost:5012
echo         in browser Config dialog.
echo.
