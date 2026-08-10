#!/bin/bash
# 一键同步到 GitHub（同时也拉取远程更新）
# 用法: bash sync.sh

TOKEN=$(cat data-pipeline/.git_token 2>/dev/null)
URL="https://${TOKEN}@github.com/1442334458-eng/Claw.git"

echo ">>> 暂存更改..."
git add -A

echo ">>> 提交..."
git commit -m "sync: $(date '+%Y-%m-%d %H:%M')" 2>/dev/null || echo "   (无新更改)"

echo ">>> 拉取远程更新..."
git -c credential.helper= fetch "$URL" master 2>/dev/null

echo ">>> 推送到 GitHub..."
git -c credential.helper= push "$URL" HEAD:master

echo "=== 同步完成 ==="
