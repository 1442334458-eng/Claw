@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
REM ============================================================
REM  足球技能 真 git 双向同步  (commit -> pull -> push)
REM  通道: SSH (github.com:22)，密钥见 ~/.ssh/id_ed25519_claw
REM  首次需在 GitHub 加入本机公钥；Surface 同理
REM ============================================================
set GIT_HOME=%USERPROFILE%\.workbuddy\vendor\PortableGit
if not exist "%GIT_HOME%\cmd\git.exe" (
    echo [错误] 找不到 git：%GIT_HOME%\cmd\git.exe，请确认 WorkBuddy 已安装。
    pause
    exit /b 1
)
set "PATH=%GIT_HOME%\cmd;%GIT_HOME%\bin;%PATH%"

set SKILLS=%USERPROFILE%\.workbuddy\skills
set LOG=%USERPROFILE%\.workbuddy\skills\sync_git_last.log

echo [信箱] 检查 GitHub 留言...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0check_mailbox.ps1"
echo.

echo 足球技能同步开始  %date% %time% > "%LOG%"
echo 日志文件：%LOG%
echo.

set FAIL=0

for %%D in (football-betting-analysis football-match-analysis__skillhub football-pipeline-v8) do (
    echo.
    echo ==================== %%D ====================
    echo ========== %%D ========== >> "%LOG%"
    pushd "%SKILLS%\%%D"

    git add -A

    git -c user.email=claw@local -c user.name=claw diff --cached --quiet >nul 2>&1
    if errorlevel 1 (
        git -c user.email=claw@local -c user.name=claw commit -q -m "sync %date% %time%" >> "%LOG%" 2>&1
        if errorlevel 1 (
            echo [提交] 失败
            set /a FAIL+=1
        ) else (
            echo [提交] 已提交本地改动
        )
    ) else (
        echo [提交] 无改动
    )

    git pull origin main >> "%LOG%" 2>&1
    if errorlevel 1 (
        echo [拉取] 失败
        set /a FAIL+=1
    ) else (
        echo [拉取] 成功
    )

    git push origin main >> "%LOG%" 2>&1
    if errorlevel 1 (
        echo [推送] 失败
        set /a FAIL+=1
    ) else (
        echo [推送] 成功
    )

    popd
)

echo.
echo ========== 同步报告 ==========
if %FAIL%==0 (
    echo 结果：3 个仓库全部同步成功
) else (
    echo 结果：%FAIL% 个步骤失败
    echo 日志文件：%LOG%
)
echo ===============================
pause
