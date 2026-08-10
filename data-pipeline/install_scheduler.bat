@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion
:: ============================================
::  数据管道定时任务安装器 v1.0
::  Pipeline Scheduler Installer v1.0
::
::  功能：一键创建 Windows 任务计划程序
::        实现三轮渐进式自动数据采集
::
::  使用方法：右键 → 以管理员身份运行
:: ============================================

echo.
echo ══════════════════════════════════════════════════
echo   足球数据管道 - 定时任务安装器 v1.0
echo ══════════════════════════════════════════════════
echo.

:: 检查管理员权限
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo ❌ 错误: 需要管理员权限！
    echo    请右键点击此文件，选择"以管理员身份运行"
    pause
    exit /b 1
)

echo ✅ 管理员权限确认通过
echo.

:: 设置路径（自动获取当前目录）
set "PIPELINE_DIR=%~dp0"
set "PYTHON=python"

:: 检查 Python 是否可用
%PYTHON% --version >nul 2>&1
if %errorLevel% neq 0 (
    echo ❌ 错误: 未找到 Python！
    echo    请确保 Python 已添加到系统 PATH
    pause
    exit /b 1
)

echo ✅ Python 环境就绪
echo.

:: 显示当前配置
echo 📁 数据管道目录: %PIPELINE_DIR%
echo.
echo ┌─────────────────────────────────────────────┐
│  三轮采集策略                                   │
├─────────────────────────────────────────────┤
│  Round 1 (T-12h): 伤停/H2H/PFI 基线数据      │
│  Round 2 (T-6h):  阵容/赔率/天气 动态信号     │
│  Round 3 (T-3h):  新闻/首发/临盘 最终校准     │
└─────────────────────────────────────────────┘
echo.

:: 询问用户配置
set /p MATCHES_INPUT="请输入要监控的比赛 (格式: \"队A vs 队B,队C vs 阱D\"):"
set /p LEAGUE_INPUT="请输入联赛名称 (留空则跳过):"
set /p CITY_INPUT="请输入比赛城市 (留空则跳过):"
set /p KICKOFF_INPUT="请输入开球时间 (格式: 2026-08-21T19:00，留空则默认明天此时):"

:: 如果用户没有输入开球时间，设置为明天此时
if "%KICKOFF_INPUT%"=="" (
    for /f "tokens=1-3 delims=/ " %%a in ('date /t') do set DATE_TOMORROW=%%a-%%b-%%c
    for /f "tokens=1-2 delims=: " %%a in ('time /t') do set TIME_NOW=%%a:%%b
    set "KICKOFF_INPUT=%DATE_TOMORROW%T%TIME_NOW%"
)

echo.
echo ⏰ 计划执行时间（假设开球时间: %KICKOFF_INPUT%）:
echo   Round 1: T-12h （基线数据）
echo   Round 2: T-6h  （动态信号）
echo   Round 3: T-3h  （最终校准）
echo.

:: 创建临时匹配文件
set "MATCHES_FILE=%PIPELINE_DIR%matches_scheduled.txt"
echo %MATCHES_INPUT% > "%MATCHES_FILE%"

:: 删除旧任务（如果存在）
echo 🗑️ 清理旧任务...
schtasks /delete /tn "FootballPipeline-Round1" /f >nul 2>&1
schtasks /delete /tn "FootballPipeline-Round2" /f >nul 2>&1
schtasks /delete /tn "FootballPipeline-Round3" /f >nul 2>&1

echo ✅ 旧任务已清理
echo.

:: 创建三个定时任务
echo 📋 创建定时任务...

:: Round 1: T-12h 基线数据收集
schtasks /create /tn "FootballPipeline-Round1" ^
/tr "\"%PYTHON%\" \"%PIPELINE_DIR%scheduler.py\" --file \"%MATCHES_FILE%\" --league \"%LEAGUE_INPUT%\" --city \"%CITY_INPUT%\" --kickoff \"%KICKOFF_INPUT%T00:00:00\" --round 1" ^
/sc once ^
/st 08:00 ^
/f ^
/rl HIGHEST

if %errorLevel% equ 0 (
    echo   ✅ Round 1 任务已创建 (每天 08:00)
) else (
    echo   ❌ Round 1 任务创建失败
)

timeout /t 2 /nobreak >nul

:: Round 2: T-6h 动态信号跟进
schtasks /create /tn "FootballPipeline-Round2" ^
/tr "\"%PYTHON%\" \"%PIPELINE_DIR%scheduler.py\" --file \"%MATCHES_FILE%\" --league \"%LEAGUE_INPUT%\" --city \"%CITY_INPUT%\" --kickoff \"%KICKOFF_INPUT%T00:00:00\" --round 2" ^
/sc once ^
/st 14:00 ^
/f ^
/rl HIGHEST

if %errorLevel% equ 0 (
    echo   ✅ Round 2 任务已创建 (每天 14:00)
) else (
    echo   ❌ Round 2 任务创建失败
)

timeout /t 2 /nobreak >nul

:: Round 3: T-3h 最终校准
schtasks /create /tn "FootballPipeline-Round3" ^
/tr "\"%PYTHON%\" \"%PIPELINE_DIR%scheduler.py\" --file \"%MATCHES_FILE%\" --league \"%LEAGUE_INPUT%\" --city \"%CITY_INPUT%\" --kickoff \"%KICKOFF_INPUT%T00:00:00\" --round 3" ^
/sc once ^
/st 17:00 ^
/f ^
/rl HIGHEST

if %errorLevel% equ 0 (
    echo   ✅ Round 3 任务已创建 (每天 17:00)
) else (
    echo   ❌ Round 3 任务创建失败
)

echo.
echo ══════════════════════════════════════════════════
echo   ✅ 安装完成！
echo ══════════════════════════════════════════════════
echo.
echo 📋 已创建的定时任务:
echo   ┌──────────────────────────────────────────┐
echo   │ 任务名              │ 执行时间 │ 功能    │
echo   ├─────────────────────┼──────────┼─────────┤
echo   │ FootballPipeline-R1 │ 08:00    │ 基线数据│
echo   │ FootballPipeline-R2 │ 14:00    │ 动态信号│
echo   │ FootballPipeline-R3 │ 17:00    │ 最终校准│
echo   └─────────────────────┴──────────┴─────────┘
echo.
echo 📂 数据输出目录: %PIPELINE_DIR%cache\
echo 📄 日志文件: %PIPELINE_DIR%logs\
echo.
echo 🔧 管理命令:
echo    查看状态: schtasks /query /tn "FootballPipeline-Round1"
echo    手动运行: schtasks /run /tn "FootballPipeline-Round1"
echo    删除任务: schtasks /delete /tn "FootballPipeline-Round1" /f
echo.
echo 💡 提示:
echo    • 首次运行建议手动测试: python scheduler.py --file matches_scheduled.txt
echo    • 如需修改比赛列表，编辑 matches_scheduled.txt 文件
echo    • 日志文件可帮助排查问题
echo.

pause
