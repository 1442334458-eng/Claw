@echo off
REM ============================================================
REM  Claw 主仓库一键同步脚本（拉取最新分析报告与代码）
REM  用法：把本文件放在 Claw 根目录，双击即可
REM  原理：%~dp0 自动定位脚本所在目录（无论 Claw 在 D:\ 还是 C:\）
REM        自动把 remote 修正为 SSH（绕过 github.com:443 被墙）
REM        然后 git pull 拉取主仓库全部内容（含 reports\）
REM ============================================================
cd /d %~dp0

echo [Claw同步] 修正 remote 为 SSH...
git remote set-url origin git@github.com:1442334458-eng/Claw.git

echo [Claw同步] 正在从 GitHub 拉取最新...
git pull
if %errorlevel% neq 0 (
    echo.
    echo [错误] 拉取失败，可能原因：
    echo   1. 未配置 SSH key（github.com 需要公钥）
    echo   2. git 不在 PATH（请安装 Git for Windows 并勾选 Add to PATH）
    echo   3. 当前目录不是 Claw 仓库
    pause
    exit /b 1
)

echo.
echo [完成] 最新报告已同步到 reports\ 目录：
dir reports\*.md /b 2>nul
echo.
pause
