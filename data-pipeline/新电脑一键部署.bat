@echo off
chcp 65001 >nul 2>&1
title 足球数据管道 - 一键部署工具

:: ═══════════════════════════════════════════════════════════
::  足球数据管道 v2.0 - 新电脑全自动部署脚本（懒人零操作版）
::  作者: WorkBuddy AI Assistant
::  用途: 双击一下就完事，连Key都不用输
:: ═══════════════════════════════════════════════════════════

echo.
echo ╔══════════════════════════════════════════════════╗
echo ║     足球数据管道 v2.0 - 一键部署向导            ║
echo ║     懒人专属版 | 全自动 | 零输入 | 零配置        ║
echo ╚══════════════════════════════════════════════════╝
echo.

:: ─────────────────────────────────────────────
:: Step 1: 检测 Python 环境
:: ─────────────────────────────────────────────
echo [1/6] 检测 Python 环境...

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo   [!] 未检测到 Python！
    echo.
    echo   请先安装 Python:
    echo     1. 打开 https://www.python.org/downloads/
    echo     2. 下载最新版（建议 3.10+）
    echo     3. 安装时勾选 "Add Python to PATH"
    echo     4. 安装完成后重新运行此脚本
    echo.
    pause
    exit /b 1
)

for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo   [OK] Python %PYVER% 已安装

:: ─────────────────────────────────────────────
:: Step 2: 定位 data-pipeline 目录
:: ─────────────────────────────────────────────
echo.
echo [2/6] 定位 data-pipeline 目录...

set "PIPELINE_DIR="
set "BASE_DIRS=D:\1\Claw D:\Claw E:\1\Claw E:\Claw C:\1\Claw C:\Claw"

:: 方法1: 环境变量
if defined DATA_PIPELINE_PATH (
    if exist "%DATA_PIPELINE_PATH%\main.py" (
        set "PIPELINE_DIR=%DATA_PIPELINE_PATH%"
        goto :found_dir
    )
)

:: 方法2: 遍历常见路径
for %%d in (%BASE_DIRS%) do (
    if exist "%%d\data-pipeline\main.py" (
        set "PIPELINE_DIR=%%d\data-pipeline"
        goto :found_dir
    )
)

:: 方法3: 当前目录
if exist "%cd%\data-pipeline\main.py" (
    set "PIPELINE_DIR=%cd%\data-pipeline"
    goto :found_dir
)

:: 方法4: 让用户选择
echo   [!] 未找到 data-pipeline 目录！
echo.
echo   Syncthing 可能还没同步完成，请检查：
echo     1. Syncthing 是否正在同步 D:\1\Claw\ 目录？
echo     2. 新电脑上该目录路径是什么？
echo.
set /p CUSTOM_PATH="   请输入 data-pipeline 的完整路径（或回车退出）: "
if "%CUSTOM_PATH%"=="" exit /b 1
if not exist "%CUSTOM_PATH%\main.py" (
    echo   [!] 该路径下未找到 main.py！
    pause
    exit /b 1
)
set "PIPELINE_DIR=%CUSTOM_PATH%"

:found_dir
echo   [OK] 找到目录: %PIPELINE_DIR%

:: ─────────────────────────────────────────────
:: Step 3: 创建 .env 配置文件（全自动！Key已内置）
:: ─────────────────────────────────────────────
echo.
echo [3/6] 配置 API 密钥（全自动，无需输入）...

if exist "%PIPELINE_DIR%\.env" (
    echo   [SKIP] .env 文件已存在，跳过创建
    goto :step4
)

:: 🔥🔥🔥 懒人专属：API Key 直接写入，零操作！
(
    echo # ============================================
    echo # 足球数据管道 v2.0 - API 配置
    echo # 由一键部署脚本自动生成（懒人版 - Key已内置）
    echo # ============================================
    echo.
    echo # The Odds API (赔率数据 - 22家bookmaker)
    ODDS_API_KEY=4909eb41f669995d8abe6ab08395d411
    echo.
    echo # Football-data.org (积分/赛程/历史数据)
    FOOTBALL_DATA_TOKEN=70301e87854d4fe0b98b0eabe925f589
) > "%PIPELINE_DIR%\.env"

echo   [OK] .env 配置文件已创建（API Key已自动填入）

:step4
:: ─────────────────────────────────────────────
:: Step 4: 安装 Python 依赖
:: ─────────────────────────────────────────────
echo.
echo [4/6] 安装 Python 依赖库...

pip install requests pyyaml >nul 2>&1
if %errorlevel% equ 0 (
    echo   [OK] 依赖安装成功（requests, pyyaml）
) else (
    echo   [!] 尝试使用 pip3...
    pip3 install requests pyyaml >nul 2>&1
    if %errorlevel% equ 0 (
        echo   [OK] 依赖安装成功（pip3）
    ) else (
        echo   [!] 依赖安装失败！请手动执行: pip install requests pyyaml
    )
)

:: ─────────────────────────────────────────────
:: Step 5: 测试 API 连通性
:: ─────────────────────────────────────────────
echo.
echo [5/6] 测试 API 连通性...

echo   测试 The Odds API...
python -c "import urllib.request; urllib.request.urlopen('https://api.the-odds-api.com/v4/sports?apiKey=' + open(r'%PIPELINE_DIR%\.env').read().split('ODDS_API_KEY=')[1].split('\n')[0].strip(), timeout=10); print('[OK]')" 2>nul
if %errorlevel% equ 0 (
    echo   [OK] The Odds API 连接成功
) else (
    echo   [WARN] The Odds API 连接失败（可能网络问题，不影响使用）
)

echo   测试 football-data.org...
python -c "import urllib.request; req=urllib.request.Request('https://api.football-data.org/v4/competitions/PL/standings', headers={'X-Auth-Token': open(r'%PIPELINE_DIR%\.env').read().split('FOOTBALL_DATA_TOKEN=')[1].split('\n')[0].strip()}); urllib.request.urlopen(req, timeout=10); print('[OK]')" 2>nul
if %errorlevel% equ 0 (
    echo   [OK] football-data.org 连接成功
) else (
    echo   [WARN] football-data.org 可能需等待24h Token激活
)

:: ─────────────────────────────────────────────
:: Step 6: 创建快捷方式 + 完成报告
:: ─────────────────────────────────────────────
echo.
echo [6/6] 创建桌面快捷方式...

powershell -Command "$ws = New-Object -ComObject WScript.Shell; $sc = $ws.CreateShortcut([Environment]::GetFolderPath('Desktop') + '\足球数据管道.lnk'); $sc.TargetPath = '%PIPELINE_DIR%\run.bat'; $sc.WorkingDirectory = '%PIPELINE_DIR%'; $sc.Description = '足球数据管道 v2.0'; $sc.Save()" 2>nul
if %errorlevel% equ 0 (
    echo   [OK] 桌面快捷方式已创建: "足球数据管道.lnk"
) else (
    echo   [WARN] 快捷方式创建失败（可手动双击 run.bat 启动）
)

:: ─────────────────────────────────────────────
:: 最终报告
:: ─────────────────────────────────────────────
echo.
echo ╔══════════════════════════════════════════════════════╗
echo ║                                                  ║
echo ║          部署完成！系统已就绪                      ║
echo ║                                                  ║
echo ╠══════════════════════════════════════════════════════╣
echo ║                                                  ║
echo ║  数据管道位置:                                    ║
echo ║     %PIPELINE_DIR%                               ║
echo ║                                                  ║
echo ║  启动方式（二选一）:                              ║
echo ║     1. 双击桌面 "足球数据管道" 快捷方式             ║
echo ║     2. 进入目录双击 run.bat                       ║
echo ║                                                  ║
echo ║  自动化任务（WorkBuddy 云端）:                    ║
echo ║     Round 1 基线数据  - 每天 08:00               ║
echo ║     Round 2 动态信号  - 每天 14:00               ║
echo ║     Round 3 最终方案  - 每天 17:00  <- 重点      ║
echo ║                                                  ║
echo ║  你每天只需要做的一件事:                          ║
echo ║     17:00 后查看 WorkBuddy 推送的投注方案         ║
echo ║     -> 复制去投注                                 ║
echo ║     -> 晚上等复盘结果                             ║
echo ║                                                  ║
echo ╚══════════════════════════════════════════════════════╝
echo.
echo   提示:
echo     - 首次使用 football-data.org 可能需等待24h激活
echo     - 如遇问题查看日志: %PIPELINE_DIR%\logs\
echo     - 如需修改 API Key，编辑 %PIPELINE_DIR%\.env
echo.
pause
