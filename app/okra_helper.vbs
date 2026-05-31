Set shell = CreateObject("WScript.Shell")
scriptDir = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
projectDir = CreateObject("Scripting.FileSystemObject").GetParentFolderName(scriptDir)
shell.CurrentDirectory = projectDir
shell.Run "powershell.exe -ExecutionPolicy Bypass -File """ & projectDir & "\run_desktop_app.ps1""", 0, False
