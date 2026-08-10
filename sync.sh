#!/bin/bash
# 一键同步到 GitHub（同时也拉取远程更新）
# 用法: bash sync.sh

TOKEN=$(cat data-pipeline/.git_token 2>/dev/null)
URL="https://${TOKEN}@github.com/1442334458-eng/Claw.git"

# 初始化报告变量
COMMITTED_FILES=0
REMOTE_BEHIND=0
PUSH_STATUS="失败"

# 统计本地待提交文件数
LOCAL_UNCOMMITTED=$(git status --porcelain | wc -l)

echo ">>> 暂存更改..."
git add -A

echo ">>> 提交..."
if [ "$LOCAL_UNCOMMITTED" -gt 0 ]; then
    COMMITTED_FILES=$(git diff --cached --name-only | wc -l)
    git commit -m "sync: $(date '+%Y-%m-%d %H:%M')" >/dev/null 2>&1
    echo "   已提交 $COMMITTED_FILES 个文件"
else
    echo "   无新更改"
fi

echo ">>> 拉取远程更新..."
git -c credential.helper= fetch "$URL" master 2>/dev/null
REMOTE_BEHIND=$(git rev-list --count HEAD..FETCH_HEAD 2>/dev/null)
if [ "$REMOTE_BEHIND" -gt 0 ] 2>/dev/null; then
    git -c credential.helper= merge FETCH_HEAD --no-edit 2>/dev/null && echo "   已合并 $REMOTE_BEHIND 个远程提交" || echo "   合并冲突，请手动处理"
else
    echo "   无远程新更新"
fi

echo ">>> 推送到 GitHub..."
if git -c credential.helper= push "$URL" HEAD:master 2>&1 | grep -q "Everything up-to-date\|master -> master"; then
    PUSH_STATUS="成功"
else
    PUSH_STATUS="失败"
fi

# 生成报告
echo ""
echo "════════════════════════════════════════"
echo "        同步报告 - $(date '+%Y-%m-%d %H:%M')"
echo "════════════════════════════════════════"
echo "  本地提交:     $COMMITTED_FILES 个文件"
echo "  远程拉取:     $REMOTE_BEHIND 个提交"
echo "  推送状态:     $PUSH_STATUS"
echo "════════════════════════════════════════"
echo "=== 同步完成 ==="
