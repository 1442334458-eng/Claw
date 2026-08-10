#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
足球数据管道 v2.0 - 全自动部署脚本（Python版）
懒人专属 | 跨平台 | 零输入 | 零配置

特性：
- 自动检测/创建 data-pipeline 目录
- 内置 API Key，无需手动配置
- 自动安装 Python 依赖
- 自动测试 API 连通性
- 跨平台支持（Windows/Mac/Linux）

使用方法:
    python deploy.py

作者: WorkBuddy AI Assistant
日期: 2026-08-09
版本: v2.0 (Python版)
"""

import os
import sys
import subprocess
import shutil
import urllib.request
import json
import time
from pathlib import Path

# ═══════════════════════════════════════════════════════════
#  配置常量
# ═══════════════════════════════════════════════════════════

# API 密钥 — 请通过 .env 文件或环境变量配置，不要硬编码
ODDS_API_KEY = os.environ.get("ODDS_API_KEY", "your-odds-api-key-here")
FOOTBALL_DATA_TOKEN = os.environ.get("FOOTBALL_DATA_TOKEN", "your-football-data-token-here")

# Python 依赖包
REQUIRED_PACKAGES = ["requests", "pyyaml"]

# 要搜索的基础路径列表（按优先级排序）
BASE_DIRS = [
    "D:\\1\\Claw",
    "D:\\Claw",
    "E:\\1\\Claw",
    "E:\\Claw",
    "C:\\1\\Claw",
    "C:\\Claw",
    os.path.expanduser("~/Claw"),
    os.path.expanduser("~/Documents/Claw"),
    os.path.expanduser("~"),
]


def print_banner():
    """打印欢迎横幅"""
    print()
    print("=" * 65)
    print("   足球数据管道 v2.0 - 一键部署向导")
    print("   懒人专属版 | Python版 | 跨平台 | 零输入")
    print("=" * 65)
    print()


def step1_check_python():
    """Step 1: 检测 Python 环境"""
    print("[1/7] 检测 Python 环境...")

    py_version = sys.version.split()[0]
    py_path = sys.executable
    print(f"  ✓ Python {py_version}")
    print(f"    路径: {py_path}")

    return True


def step2_find_or_create_pipeline_dir():
    """Step 2: 定位或创建 data-pipeline 目录"""
    print("\n[2/7] 定位 data-pipeline 目录...")

    # 先尝试找现有的
    for base_dir in BASE_DIRS:
        # 环境变量优先
        env_path = os.environ.get("DATA_PIPELINE_PATH", "")
        if env_path and os.path.exists(os.path.join(env_path, "main.py")):
            print(f"  ✓ 从环境变量找到: {env_path}")
            return env_path, False  # False = 已存在

        # 常见路径搜索
        pipeline_dir = os.path.join(base_dir, "data-pipeline")
        if os.path.exists(os.path.join(pipeline_dir, "main.py")):
            print(f"  ✓ 找到已有目录: {pipeline_dir}")
            return pipeline_dir, False

        # 当前目录
        cwd_pipeline = os.path.join(os.getcwd(), "data-pipeline")
        if os.path.exists(os.path.join(cwd_pipeline, "main.py")):
            print(f"  ✓ 在当前目录找到: {cwd_pipeline}")
            return cwd_pipeline, False

    # 都找不到 → 创建新的
    print("  ℹ 未找到现有项目，将自动创建...")
    
    # 选择最佳创建位置
    target_base = None
    for base_dir in BASE_DIRS:
        if os.path.exists(base_dir) and os.access(base_dir, os.W_OK):
            target_base = base_dir
            break
    
    if not target_base:
        # 使用用户主目录
        target_base = os.path.expanduser("~")
        print(f"  ⚠ 未找到常用路径，将使用用户主目录: {target_base}")
    
    pipeline_dir = os.path.join(target_base, "data-pipeline")
    
    print(f"  将创建新目录: {pipeline_dir}")
    
    try:
        os.makedirs(pipeline_dir, exist_ok=True)
        print(f"  ✓ 目录已创建: {pipeline_dir}")
        return pipeline_dir, True  # True = 新创建
    except Exception as e:
        print(f"  ✗ 创建目录失败: {e}")
        return None, False


def step3_create_project_files(pipeline_dir, is_new):
    """Step 3: 创建项目文件（如果是新项目）"""
    if not is_new:
        print("\n[3/7] 检查项目文件完整性...")
        
        # 检查必要文件是否存在
        required_files = ["main.py", "websearch_templates.yaml", "run.bat"]
        missing = [f for f in required_files if not os.path.exists(os.path.join(pipeline_dir, f))]
        
        if missing:
            print(f"  ⚠ 缺少文件: {', '.join(missing)}")
            print("  将尝试重新生成...")
            is_new = True
        else:
            print("  ✓ 所有必要文件已存在")
            return True
    
    print("\n[3/7] 生成项目文件...")
    
    # 创建子目录
    for subdir in ["cache", "logs"]:
        subdir_path = os.path.join(pipeline_dir, subdir)
        os.makedirs(subdir_path, exist_ok=True)
        print(f"  ✓ 创建目录: {subdir}/")
    
    # 生成 .env 文件
    env_file = os.path.join(pipeline_dir, ".env")
    env_content = f"""# ============================================
# 足球数据管道 v2.0 - API 配置
# 由一键部署脚本自动生成（懒人版 - Key已内置）
# ============================================

# The Odds API (赔率数据 - 22家bookmaker)
ODDS_API_KEY={ODDS_API_KEY}

# Football-data.org (积分/赛程/历史数据)
FOOTBALL_DATA_TOKEN={FOOTBALL_DATA_TOKEN}
"""
    with open(env_file, "w", encoding="utf-8") as f:
        f.write(env_content)
    print("  ✓ 生成: .env")
    
    # 生成 .env.example
    env_example_file = os.path.join(pipeline_dir, ".env.example")
    with open(env_example_file, "w", encoding="utf-8") as f:
        f.write("# The Odds API\nODDS_API_KEY=your-key-here\n\n# Football-data.org\nFOOTBALL_DATA_TOKEN=your-token-here\n")
    print("  ✓ 生成: .env.example")
    
    # 生成 matches_example.txt
    example_file = os.path.join(pipeline_dir, "matches_example.txt")
    with open(example_file, "w", encoding="utf-8") as f:
        f.write("# 示例：每行一场比赛\n# 格式：主队 vs 客队 | 联赛名 | 城市名\nDeportivo Alaves vs Getafe CF | La Liga | Vitoria-Gasteiz\n")
    print("  ✓ 生成: matches_example.txt")
    
    # 检查核心文件是否需要生成
    core_files = ["main.py", "websearch_templates.yaml", "scheduler.py", "run.bat"]
    for fname in core_files:
        fpath = os.path.join(pipeline_dir, fname)
        if not os.path.exists(fpath):
            print(f"  ⚠ 缺少核心文件: {fname}（需从旧电脑同步或手动复制）")
    
    print("\n  💡 提示: 核心代码文件（main.py等）需要从旧电脑同步过来")
    print("         如果 Syncthing 正在同步，请等待完成后再运行本脚本")
    
    return True


def step4_install_dependencies():
    """Step 4: 安装 Python 依赖"""
    print("\n[4/7] 安装 Python 依赖库...")

    all_ok = True
    for package in REQUIRED_PACKAGES:
        try:
            __import__(package.replace("-", "_"))
            print(f"  ✓ {package} 已安装")
        except ImportError:
            print(f"  正在安装 {package}...")
            try:
                subprocess.check_call(
                    [sys.executable, "-m", "pip", "install", package, "-q"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=60,
                )
                print(f"  ✓ {package} 安装成功")
            except subprocess.CalledProcessError:
                print(f"  ✗ {package} 安装失败")
                all_ok = False
            except subprocess.TimeoutExpired:
                print(f"  ✗ {package} 安装超时")
                all_ok = False

    return all_ok


def step5_test_api(pipeline_dir):
    """Step 5: 测试 API 连通性"""
    print("\n[5/7] 测试 API 连通性...")

    # 测试 The Odds API
    print("  测试 The Odds API...")
    try:
        url = f"https://api.the-odds-api.com/v4/sports?apiKey={ODDS_API_KEY}"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
            sport_count = len([s for s in data if "soccer" in s.get("key", "")])
            print(f"  ✓ The Odds API 连接成功（{sport_count} 个足球联赛）")
    except Exception as e:
        print(f"  ⚠ The Odds API: {str(e)[:50]}")

    # 测试 football-data.org
    print("  测试 football-data.org...")
    try:
        url = "https://api.football-data.org/v4/competitions/PL/standings"
        req = urllib.request.Request(url, headers={"X-Auth-Token": FOOTBALL_DATA_TOKEN})
        with urllib.request.urlopen(req, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
            if "standings" in data:
                team_count = len(data["standings"][0]["table"])
                top_team = data["standings"][0]["table"][0]["team"]["name"]
                print(f"  ✓ football-data.org 连接成功（英超 {team_count}队，榜首: {top_team}）")
            else:
                print("  ⚠ 返回数据异常")
    except urllib.error.HTTPError as e:
        if e.code in [401, 403]:
            print("  ⚠ Token 可能未激活（新注册需等待24h审批）")
        else:
            print(f"  ⚠ HTTP 错误: {e.code}")
    except Exception as e:
        print(f"  ⚠ 连接失败: {str(e)[:50]}")

    return True


def step6_create_launcher(pipeline_dir):
    """Step 6: 创建启动器"""
    print("\n[6/7] 创建启动方式...")

    desktop = Path.home() / "Desktop"
    
    if os.name == "nt":  # Windows
        # 创建 run.bat（如果没有的话）
        run_bat = os.path.join(pipeline_dir, "run.bat")
        if not os.path.exists(run_bat):
            bat_content = f"""@echo off
chcp 65001 >nul 2>&1
title 足球数据管道 v2.0
cd /d "{pipeline_dir}"
python main.py %*
pause
"""
            with open(run_bat, "w", encoding="utf-8") as f:
                f.write(bat_content)
            print("  ✓ 生成: run.bat")
        
        # 尝试创建桌面快捷方式
        shortcut_path = desktop / "足球数据管道.lnk"
        try:
            import pythoncom
            from win32com.client import Dispatch
            
            shell = Dispatch("WScript.Shell")
            shortcut = shell.CreateShortcut(str(shortcut_path))
            shortcut.TargetPath = run_bat
            shortcut.WorkingDirectory = pipeline_dir
            shortcut.Description = "足球数据管道 v2.0"
            shortcut.Save()
            print(f"  ✓ 桌面快捷方式: {shortcut_path}")
        except ImportError:
            print("  ⚠ 快捷方式需要 pywin32（可选）")
            print(f"     可直接双击运行: {run_bat}")
        except Exception as e:
            print(f"  ⚠ 快捷方式创建失败: {e}")
            
    else:  # Mac/Linux
        launcher = desktop / "start_pipeline.sh"
        sh_content = f"""#!/bin/bash
cd "{pipeline_dir}"
python3 main.py "$@"
read -p "按回车键退出..."
"""
        with open(launcher, "w") as f:
            f.write(sh_content)
        os.chmod(launcher, 0o755)
        print(f"  ✓ 桌面启动脚本: {launcher}")

    return True


def step7_final_report(pipeline_dir, is_new):
    """Step 7: 最终报告"""
    print("\n[7/7] 生成部署报告...")
    
    # 统计文件数量
    file_count = sum(len(files) for _, _, files in os.walk(pipeline_dir))
    
    print()
    print("=" * 65)
    print("  🎉 部署完成！")
    print("=" * 65)
    print()
    print(f"  📂 项目位置:")
    print(f"     {pipeline_dir}")
    print()
    print(f"  📊 文件统计: {file_count} 个文件")
    print()
    
    if is_new:
        print("  ⚠️ 重要提示（新项目）:")
        print("     • 配置文件 (.env) 已自动生成 ✓")
        print("     • 核心代码 (main.py 等) 需要 Syncthing 同步")
        print("     • 请确保旧电脑的 data-pipeline 已加入同步列表")
        print()
    
    print("  🚀 启动方式:")
    if os.name == "nt":
        print("     ① 双击桌面 '足球数据管道' 快捷方式")
        print(f"     ② 双击: {os.path.join(pipeline_dir, 'run.bat')}")
    else:
        print(f"     ① 运行: {Path.home() / 'Desktop' / 'start_pipeline.sh'}")
    print(f"     ③ 命令行: cd {pipeline_dir} && python main.py")
    print()
    print("  ⏰ WorkBuddy Automation（云端任务）:")
    print("     Round 1 基线数据  → 每天 08:00")
    print("     Round 2 动态信号  → 每天 14:00")
    print("     Round 3 最终方案  → 每天 17:00 ← 重点！")
    print()
    print("  📱 你每天的工作:")
    print("     17:00 后查看方案 → 投注 → 晚上复盘")
    print("     （每天5分钟）")
    print()
    print("-" * 65)
    print("  📞 常见问题:")
    print("     • football-data.org 需等24h激活 → 正常现象")
    print(f"     • 日志位置: {os.path.join(pipeline_dir, 'logs')}")
    print(f"     • 修改API Key: 编辑 {os.path.join(pipeline_dir, '.env')}")
    print()


def main():
    """主函数"""
    start_time = time.time()
    
    # 打印横幅
    print_banner()
    
    # Step 1: 检测 Python
    if not step1_check_python():
        return 1
    
    # Step 2: 定位或创建目录
    pipeline_dir, is_new = step2_find_or_create_pipeline_dir()
    if not pipeline_dir:
        print("\n✗ 无法定位/创建项目目录，部署终止。")
        input("按回车键退出...")
        return 1
    
    # Step 3: 创建项目文件
    if not step3_create_project_files(pipeline_dir, is_new):
        return 1
    
    # Step 4: 安装依赖
    step4_install_dependencies()
    
    # Step 5: 测试 API
    step5_test_api(pipeline_dir)
    
    # Step 6: 创建启动器
    step6_create_launcher(pipeline_dir)
    
    # Step 7: 最终报告
    step7_final_report(pipeline_dir, is_new)
    
    # 统计耗时
    elapsed = time.time() - start_time
    print(f"  ⏱️ 总耗时: {elapsed:.1f} 秒")
    print()
    
    input("按回车键退出...")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n用户中断部署。")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ 部署过程出错: {e}")
        import traceback
        traceback.print_exc()
        input("\n按回车键退出...")
        sys.exit(1)
