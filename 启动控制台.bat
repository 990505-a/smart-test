@echo off
chcp 65001 >nul
cd /d %~dp0
echo [服务控制台] 启动中... 浏览器将自动打开 http://localhost:5010
start "SmartTest-控制台" /min ".venv\Scripts\python.exe" "launcher.py"
timeout /t 2 >nul
start http://localhost:5010
