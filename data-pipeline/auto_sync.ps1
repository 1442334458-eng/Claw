# GitHub 自动同步脚本
# 路径：D:\1\Claw\data-pipeline\auto_sync.ps1

$repoPath = "D:\1\Claw"
$env:HOME = $env:USERPROFILE

Set-Location $repoPath

# 暂存所有更改
git add -A 2>$null

# 检查是否有待提交的内容
$hasChanges = git diff --cached --quiet 2>$null
if ($LASTEXITCODE -ne 0) {
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm"
    $commitMsg = "auto-sync: $timestamp"
    git commit -m $commitMsg 2>&1 | Out-Null
    git push origin master 2>&1
}
