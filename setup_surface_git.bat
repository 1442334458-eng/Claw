@echo off
REM ============================================================
REM  Surface 首次设置（路线 A：真 git + SSH）
REM  前提：1) 已装 Git(git-scm.com)  2) 已把本机 SSH 公钥加到 GitHub
REM  运行后会 clone 3 个技能仓库到本机用户级 skills 目录
REM ============================================================
set SKILLS=%USERPROFILE%\.workbuddy\skills
if not exist "%SKILLS%" mkdir "%SKILLS%"
cd /d "%SKILLS%"

echo Cloning 3 skill repos via SSH ...
git clone git@github.com:1442334458-eng/football-betting-analysis.git football-betting-analysis
git clone git@github.com:1442334458-eng/football-match-analysis.git football-match-analysis__skillhub
git clone git@github.com:1442334458-eng/football-pipeline-v8.git football-pipeline-v8

echo Linking football-sync skill (lives inside betting-analysis repo) ...
if not exist "football-sync" mklink /J football-sync football-betting-analysis\football-sync

echo.
echo [!] 请确认：把本机 SSH 公钥已加到 GitHub；并在本目录创建 .git_token（写入 PAT，备用）
echo     然后重启 WorkBuddy 即可识别技能。日常同步运行 sync_git.bat。
echo.
pause
