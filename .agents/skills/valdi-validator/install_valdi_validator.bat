@echo off
setlocal
set "SKILL_ROOT=%~dp0"
for %%I in ("%SKILL_ROOT%..\..\..") do set "PROJECT_ROOT=%%~fI"
for %%I in ("%PROJECT_ROOT%\.agents\skills\valdi-validator") do set "EXPECTED_ROOT=%%~fI\"
if /I not "%SKILL_ROOT%"=="%EXPECTED_ROOT%" (
  echo Valdi installer must run from PROJECT\.agents\skills\valdi-validator\
  exit /b 1
)
if not exist "%PROJECT_ROOT%\.claude\skills\valdi-validator" mkdir "%PROJECT_ROOT%\.claude\skills\valdi-validator"
copy /Y "%SKILL_ROOT%adapters\claude\CLAUDE_SKILL.md" "%PROJECT_ROOT%\.claude\skills\valdi-validator\SKILL.md" >nul
if not exist "%PROJECT_ROOT%\.cursor\skills\valdi-validator" mkdir "%PROJECT_ROOT%\.cursor\skills\valdi-validator"
copy /Y "%SKILL_ROOT%SKILL.md" "%PROJECT_ROOT%\.cursor\skills\valdi-validator\SKILL.md" >nul
echo Valdi installed for Claude + Codex + Cursor.
exit /b 0