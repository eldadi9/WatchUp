@echo off
REM Starts the WhatsApp MCP bridge (whatsapp-bridge) so Claude's WhatsApp tools work.
REM Keeps a visible console window open with connection logs.

cd /d "C:\Users\Master_PC\Desktop\whatsapp-mcp\whatsapp-bridge"
echo Starting WhatsApp bridge...
go run .
pause
