@echo off
title Drivio 播刻
cd /d "%~dp0"

echo ================================
echo  Drivio 播刻 - 一键启动
echo ================================
echo.

:: 启动 Flask 后端（后台运行）
echo [1/2] 启动 Flask 后端 (port 5002)...
start "Flask" cmd /c "call .venv\Scripts\activate && python start_flask.py"

:: 等 2 秒让 Flask 先启动
timeout /t 2 /nobreak >nul

:: 启动 Vite 前端（后台运行，自动打开浏览器）
echo [2/2] 启动 Vite 前端 (port 3000)...
start "Vite" cmd /c "cd frontend && npx vite --open"

echo.
echo 全部启动完成！
echo Flask: http://localhost:5002
echo Vite:  http://localhost:3000
echo.
echo 关闭窗口即可停止所有服务
echo ================================
pause