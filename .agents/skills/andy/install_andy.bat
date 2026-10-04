@echo off
setlocal

set "SKILL_ROOT=%~dp0"
for %%I in ("%SKILL_ROOT%..\..\..") do set "PROJECT_ROOT=%%~fI"
for %%I in ("%PROJECT_ROOT%\.agents\skills\andy") do set "EXPECTED_ROOT=%%~fI\"

if /I not "%SKILL_ROOT%"=="%EXPECTED_ROOT%" (
  echo Andy installer must run from PROJECT\.agents\skills\andy\
  echo Current location: %SKILL_ROOT%
  goto :failed
)

if not exist "%SKILL_ROOT%SKILL.md" (
  echo Missing Andy core: %SKILL_ROOT%SKILL.md
  goto :failed
)

if not exist "%SKILL_ROOT%adapters\claude\CLAUDE_SKILL.md" (
  echo Missing Claude adapter template.
  goto :failed
)

if not exist "%PROJECT_ROOT%\.claude\skills\andy" (
  mkdir "%PROJECT_ROOT%\.claude\skills\andy"
  if errorlevel 1 goto :failed
)

copy /Y "%SKILL_ROOT%adapters\claude\CLAUDE_SKILL.md" "%PROJECT_ROOT%\.claude\skills\andy\SKILL.md" >nul
if errorlevel 1 goto :failed
echo Claude adapter: ready

rem Claude always loads PROJECT\CLAUDE.md. Add a small routing marker once so
rem natural-language Andy commands, including Hebrew equivalents, activate the
rem adapter instead of being treated as a generic chat request.
set "CLAUDE_ROUTING_FILE=%PROJECT_ROOT%\CLAUDE.md"
findstr /C:"ANDY-ROUTING" "%CLAUDE_ROUTING_FILE%" >nul 2>&1
if errorlevel 1 (
  (
    echo.
    echo ^<!-- ANDY-ROUTING --^>
    echo ## Andy session continuity
    echo When the user invokes Andy session continuity, including an equivalent Hebrew command,
    echo read .claude/skills/andy/SKILL.md and follow its canonical protocol.
    echo Use .ai/andy/current.json only within this project as the session state.
  ) >> "%CLAUDE_ROUTING_FILE%"
)
echo Claude command routing: ready

set "AGENTS_ROUTING_FILE=%PROJECT_ROOT%\AGENTS.md"
findstr /C:"ANDY-AUTOSAVE" "%AGENTS_ROUTING_FILE%" >nul 2>&1
if errorlevel 1 (
  (
    echo.
    echo ^<!-- ANDY-AUTOSAVE --^>
    echo ## Andy active-workstream checkpoint gate
    echo When .ai/andy/current.json has an active, paused, or blocked workstream, read .agents/skills/andy/SKILL.md before finishing any turn with any state or workspace change.
    echo Save silently before risky or long actions, after every state or workspace change, before returning control with unsaved work, and after at most three exchanges. The three-exchange save captures a compact conversation delta. Use fresh updated_at for guarded writes. Never print automatic-save details; display state only for explicit Andy status or Andy save.
  ) >> "%AGENTS_ROUTING_FILE%"
)
echo Codex/Cursor auto-save routing: ready

findstr /C:"ANDY-AUTOSAVE" "%CLAUDE_ROUTING_FILE%" >nul 2>&1
if errorlevel 1 (
  (
    echo.
    echo ^<!-- ANDY-AUTOSAVE --^>
    echo ## Andy active-workstream checkpoint gate
    echo When .ai/andy/current.json has an active, paused, or blocked workstream, read .claude/skills/andy/SKILL.md before finishing any turn with any state or workspace change.
    echo Save silently before risky or long actions, after every state or workspace change, before returning control with unsaved work, and after at most three exchanges. The three-exchange save captures a compact conversation delta. Use fresh updated_at for guarded writes. Never print automatic-save details; display state only for explicit Andy status or Andy save.
  ) >> "%CLAUDE_ROUTING_FILE%"
)
echo Claude auto-save routing: ready
where py >nul 2>&1
if not errorlevel 1 (
  py -3 "%SKILL_ROOT%scripts\andy_state.py" init "%PROJECT_ROOT%"
  if errorlevel 1 goto :failed
  goto :success
)

where python >nul 2>&1
if not errorlevel 1 (
  python "%SKILL_ROOT%scripts\andy_state.py" init "%PROJECT_ROOT%"
  if errorlevel 1 goto :failed
  goto :success
)

echo Python 3 was not found. Claude adapter was installed, but Andy state was not initialized.
echo Install Python 3, then run this file again.
goto :failed

:success
echo.
echo Andy installation complete.
echo Project: %PROJECT_ROOT%
echo Restart any open AI session, then say: Andy start
set "EXIT_CODE=0"
goto :finish

:failed
echo.
echo Andy installation did not complete.
set "EXIT_CODE=1"

:finish
if /I not "%~1"=="--no-pause" pause
exit /b %EXIT_CODE%
