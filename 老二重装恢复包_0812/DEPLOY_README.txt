========================================
老二重装恢复包 v1.0（2026-08-12）
========================================

【这是什么】
老二电脑卸载重装 WorkBuddy 后，用本包一键恢复足球分析全套技能。
GitHub 云端三仓库数据完好，执行 pull 即可全部恢复。

【本包包含】
  1. git-sync.py   —— 同步工具（push/pull/status 三命令）
  2. .git_token    —— GitHub 访问令牌（机密！勿外传勿发邮件）
  3. .mcp.json     —— MCP 服务配置（jc-mcp 竞彩接口）
  4. 本说明文件

【部署步骤】（在老二电脑上操作）
  第 1 步  把本 zip 解压，将 git-sync.py 和 .git_token 复制到：
           C:\Users\<你的用户名>\.workbuddy\skills\
           （skills 目录不存在就手动创建）

  第 2 步  打开 Git Bash，执行：
           python3 "$(cygpath -m "$HOME")/.workbuddy/skills/git-sync.py" pull
           看到三个仓库 "Pull 完成" 即成功
           （会同时还原 football-sync 技能和球队画像档案库）

  第 3 步  验证：
           ls ~/.workbuddy/skills/
           应看到 football-betting-analysis、football-match-analysis__skillhub、
           football-pipeline-v8 三个目录

  第 4 步  【重要】MCP 配置：如果老二电脑的用户名不是 xieyu，
           请把 .mcp.json 复制到  C:\Users\<你的用户名>\.workbuddy\.mcp.json
           （注意是 skills 的上一级目录）

【完成后怎么用】
  - 在老二对话框直接说「帮我分析 XX 比赛」→ 自动加载技能走完整流程
  - 想让老二拉取本机最新数据，直接说「pull」或「同步一下」
  - 让老二分析完推送，它自己会执行 push（铁律，无需你操心）

【pull 和 push 本来就是分开的】
  不用再混淆：
  - git-sync.py pull  = 拉取云端最新数据（分析前用）
  - git-sync.py push  = 推送本地改动到云端（分析后/复盘后用）
  - 两个是独立命令，永不自动一起跑
========================================
