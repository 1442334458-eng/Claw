@echo off
:: GitHub 自动同步脚本 (Batch 版本)
:: Token 从 data-pipeline\.git_token 读取

cd /d D:\1\Claw

:: 读取 token
set TOKEN=
if exist "data-pipeline\.git_token" (
    set /p TOKEN=<"data-pipeline\.git_token"
)

:: 暂存所有更改
git add -A 2>nul

:: 检查是否有待提交的内容
git diff --cached --quiet 2>nul
if %errorlevel% neq 0 (
    for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set dt=%%I
    set msg=auto-sync: %dt:~0,4%-%dt:~4,2%-%dt:~6,2% %dt:~8,2%:%dt:~10,2%
    git commit -m "!msg!" >nul 2>&1
    
    if defined TOKEN (
        git -c credential.helper= push https://%TOKEN%@github.com/1442334458-eng/Claw.git master >nul 2>&1
    ) else (
        git push origin master >nul 2>&1
    )
)
