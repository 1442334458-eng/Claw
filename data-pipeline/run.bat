@echo off
chcp 65001 >nul
echo ============================================
echo   足球数据聚合器 v1.0 - Windows启动脚本
echo ============================================
echo.

REM 检查Python是否安装
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到Python！请先安装Python 3.8+
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)

REM 检查.env文件是否存在
if not exist ".env" (
    echo [提示] 未找到.env配置文件
    echo 正在从模板创建...
    copy .env.example .env >nul
    echo 请编辑 .env 文件，填入你的API Key后重新运行
    start notepad .env
    pause
    exit /b 0
)

REM 显示菜单
echo 请选择操作:
echo   [1] 分析指定比赛（手动输入）
echo   [2] 从文件读取比赛列表
echo   [3] 快速测试（示例数据）
echo   [4] 查看缓存文件列表
echo   [0] 退出
echo.
set /p choice=输入选项编号:

if "%choice%"=="1" goto manual
if "%choice%"=="2" goto file
if "%choice%"=="3" goto test
if "%choice%"=="4" goto list_cache
if "%choice%"=="0" goto end

:manual
echo.
set /p matches=请输入比赛（格式: 主队 vs 客队, 多场用逗号分隔）:
echo.
python main.py --matches "%matches%"
goto end

:file
echo.
set /p filepath=请输入文件路径（默认: matches_example.txt）:
if "%filepath%=="" set filepath=matches_example.txt
echo.
python main.py --file "%filepath%"
goto end

:test
echo.
echo [*] 使用示例数据运行测试...
python main.py --file matches_example.txt
goto end

:list_cache
echo.
echo [*] 缓存文件列表:
dir /b cache\*.json 2>nul | findstr /c:".json"
if errorlevel 1 echo (空)
goto end

:end
echo.
pause
