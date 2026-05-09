Set shell = CreateObject("WScript.Shell")
shell.CurrentDirectory = "F:\okra_assistant"
shell.Run "powershell.exe -ExecutionPolicy Bypass -File ""F:\okra_assistant\run_desktop_app.ps1""", 0, False
