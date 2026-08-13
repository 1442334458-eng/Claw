@echo off
chcp 65001 >nul
cd /d C:\Users\xieyu\.workbuddy\skills
set PY=C:\Users\xieyu\.workbuddy\binaries\python\versions\3.13.12\python.exe
set LOG=C:\Users\xieyu\Desktop\sync-skills-log.txt
echo [%date% %time%] start sync > "%LOG%"
"%PY%" -u git-sync.py pull >> "%LOG%" 2>&1
echo [pull exit=%errorlevel%] >> "%LOG%"
"%PY%" -u git-sync.py push >> "%LOG%" 2>&1
echo [push exit=%errorlevel%] >> "%LOG%"
echo [%date% %time%] end sync >> "%LOG%"
echo.
echo Done. See sync-skills-log.txt on Desktop for details.
echo Press any key to close...
pause
