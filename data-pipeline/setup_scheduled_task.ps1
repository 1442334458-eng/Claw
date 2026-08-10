# 创建 Windows 计划任务：每30分钟自动同步 GitHub
$taskName = "Claw GitHub Auto Sync"
$scriptPath = "D:\1\Claw\data-pipeline\auto_sync.ps1"

# 先删除旧任务（如果存在）
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

# 创建触发器：每30分钟
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 30) -RepetitionDuration ([TimeSpan]::MaxValue)

# 创建动作
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-WindowStyle Hidden -NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`""

# 用当前用户创建任务
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive

# 注册任务
Register-ScheduledTask -TaskName $taskName -Trigger $trigger -Action $action -Principal $principal -Description "Auto commit and push Claw project to GitHub every 30 minutes" -ErrorAction Stop

Write-Host "Task '$taskName' created successfully."
Write-Host "Trigger: Every 30 minutes"
Write-Host "Script: $scriptPath"
