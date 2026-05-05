Set shell = CreateObject("WScript.Shell")
shell.CurrentDirectory = "F:\okra_assistant"
shell.Run """F:\okra_assistant\frontend\src-tauri\target\release\okra-workbench.exe""", 0, False
