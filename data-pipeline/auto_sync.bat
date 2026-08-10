@echo off
cd /d D:\1\Claw

:: 设置 HOME 变量以便 git 找到 .git-credentials
set HOME=%USERPROFILE%

:: 如果有未暂存的更改，添加
git add -A 2>nul

:: 检查是否有待提交的更改
git diff --cached --quiet 2>nul
if %errorlevel% neq 0 (
    for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set dt=%%I
    set msg=auto-sync: %dt:~0,4%-%dt:~4,2%-%dt:~6,2% %dt:~8,2%:%dt:~10,2%
    git commit -m "!msg!" >nul 2>&1
    git push origin master 2>&1
)
