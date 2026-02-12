@echo off
echo ============================================
echo 初始化 Weekly Metrics 数据
echo ============================================
echo.

cd /d %~dp0

where python >nul 2>&1
if errorlevel 1 (
    echo 错误: 找不到 python 命令
    echo 请确保 Python 已添加到系统 PATH
    pause
    exit /b 1
)

echo 开始初始化...
python migrations\004_init_weekly_metrics.py

echo.
echo 完成！
pause
