# GitHub 自动同步脚本
# 路径：D:\1\Claw\data-pipeline\auto_sync.ps1
# Token 存储在同目录 .git_token 文件（已 gitignore）

$repoPath = "D:\1\Claw"
$tokenFile = "$repoPath\data-pipeline\.git_token"
$repoUrl = "https://github.com/1442334458-eng/Claw.git"

Set-Location $repoPath

# 读取 token
$token = ""
if (Test-Path $tokenFile) {
    $token = (Get-Content $tokenFile -Raw).Trim()
}

# 暂存所有更改
git add -A 2>$null

# 检查是否有待提交的内容
$hasChanges = git diff --cached --quiet 2>$null
if ($LASTEXITCODE -ne 0) {
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm"
    $commitMsg = "auto-sync: $timestamp"
    git commit -m $commitMsg 2>&1 | Out-Null
    
    # 用 token URL 推送（绕过 credential helper 问题）
    if ($token) {
        $pushUrl = $repoUrl -replace "https://", "https://${token}@"
        git -c credential.helper= push $pushUrl master 2>&1 | Out-Null
    } else {
        git push origin master 2>&1 | Out-Null
    }
}
