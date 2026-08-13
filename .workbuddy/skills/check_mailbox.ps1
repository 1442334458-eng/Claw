# check_mailbox.ps1
# 在 sync_git.bat 开头调用：检查 GitHub Issue 信箱是否有新留言（xieyu <-> 老二）
$ErrorActionPreference = 'SilentlyContinue'

# token 候选路径（xieyu / Surface 都尽量覆盖）
$TOKEN_CANDIDATES = @(
    'D:\1\Claw\data-pipeline\.git_token',
    'D:\1\Claw\.workbuddy\skills\.git_token',
    "$env:USERPROFILE\data-pipeline\.git_token",
    "$env:USERPROFILE\.workbuddy\data-pipeline\.git_token",
    "$env:USERPROFILE\.workbuddy\skills\.git_token"
)
$STATE_FILE = "$env:USERPROFILE\.workbuddy\skills\.mailbox_state.json"
$REPO = '1442334458-eng/football-betting-analysis'
$ISSUE_NUM = 1

$tokenFile = $null
foreach ($c in $TOKEN_CANDIDATES) { if (Test-Path $c) { $tokenFile = $c; break } }
if (-not $tokenFile) {
    Write-Host '[信箱] 未找到 token，跳过信箱检查（如需检查，请把 GitHub token 放到 data-pipeline\.git_token）。'
    exit 0
}
$token = (Get-Content $tokenFile -Raw).Trim()
if (-not $token) { Write-Host '[信箱] token 为空，跳过。'; exit 0 }

$headers = @{ Authorization = "token $token"; Accept = 'application/vnd.github+json' }
$state = @{ lastCommentId = 0 }
if (Test-Path $STATE_FILE) {
    try { $state = Get-Content $STATE_FILE -Raw | ConvertFrom-Json } catch {}
}

$newMsgs = @()
try {
    # 1) 信箱 Issue #1 的评论（老二的回复）
    $comments = Invoke-RestMethod -Uri "https://api.github.com/repos/$REPO/issues/$ISSUE_NUM/comments" -Headers $headers
    foreach ($c in $comments) {
        if ($c.id -gt $state.lastCommentId) {
            $firstLine = ($c.body -split "`n")[0].Trim()
            if ($firstLine.Length -gt 60) { $firstLine = $firstLine.Substring(0, 60) + '…' }
            $newMsgs += "  - 老二在 Issue #$ISSUE_NUM 回复：$firstLine"
        }
    }
    if ($comments.Count -gt 0) {
        $state.lastCommentId = ($comments | ForEach-Object { $_.id } | Measure-Object -Maximum).Maximum
    }
    # 2) 是否有新开的 Issue
    $issues = Invoke-RestMethod -Uri "https://api.github.com/repos/$REPO/issues?state=open" -Headers $headers
    foreach ($i in $issues) {
        if ($i.number -gt $ISSUE_NUM) { $newMsgs += "  - 新 Issue #$($i.number): $($i.title)" }
    }
} catch {
    Write-Host '[信箱] 检查失败（网络或权限），跳过。'
    exit 0
}

$state | ConvertTo-Json | Set-Content $STATE_FILE

if ($newMsgs.Count -gt 0) {
    Write-Host '【信箱】检测到新留言：'
    $newMsgs | ForEach-Object { Write-Host $_ }
} else {
    Write-Host '【信箱】暂无新留言。'
}
