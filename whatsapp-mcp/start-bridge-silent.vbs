' Launches start-bridge.bat with no visible window.
' Use this in the Startup folder if you don't want a console window popping up on every boot.
' The bridge still runs in the background - check Task Manager for "go.exe" / "whatsapp-bridge" if you need to confirm.

Set WshShell = CreateObject("WScript.Shell")
WshShell.Run """C:\Users\Master_PC\Desktop\whatsapp-mcp\start-bridge.bat""", 0, False
