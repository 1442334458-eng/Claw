Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "D:\1\Claw"
WshShell.Run "C:\Users\xieyu\.workbuddy\vendor\PortableGit\bin\bash.exe sync.sh", 1, true
MsgBox "同步完成，按确定关闭。", 0, "GitHub同步"
Set WshShell = Nothing
