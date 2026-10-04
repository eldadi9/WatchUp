@echo off
setlocal

set "SKILL_ROOT=%~dp0"
for %%I in ("%SKILL_ROOT%..\..\..") do set "PROJECT_ROOT=%%~fI"
for %%I in ("%PROJECT_ROOT%\.agents\skills\yuli-ceo") do set "EXPECTED_ROOT=%%~fI\"

if /I not "%SKILL_ROOT%"=="%EXPECTED_ROOT%" (
  echo Yuli Chief of Staff installer must run from PROJECT\.agents\skills\yuli-ceo\
  echo Current location: %SKILL_ROOT%
  echo.
  echo First copy EG-SKIILS\...\yuli-ceo to PROJECT\.agents\skills\yuli-ceo\
  goto :failed
)

if not exist "%SKILL_ROOT%SKILL.md" (
  echo Missing Yuli core: %SKILL_ROOT%SKILL.md
  goto :failed
)

if not exist "%SKILL_ROOT%adapters\claude\CLAUDE_SKILL.md" (
  echo Missing Claude adapter template.
  goto :failed
)

rem --- Claude Code ---
if not exist "%PROJECT_ROOT%\.claude\skills\yuli-ceo" mkdir "%PROJECT_ROOT%\.claude\skills\yuli-ceo"
copy /Y "%SKILL_ROOT%adapters\claude\CLAUDE_SKILL.md" "%PROJECT_ROOT%\.claude\skills\yuli-ceo\SKILL.md" >nul
if errorlevel 1 goto :failed
echo Claude adapter: ready

rem --- Cursor optional mirror ---
if not exist "%PROJECT_ROOT%\.cursor\skills\yuli-ceo" mkdir "%PROJECT_ROOT%\.cursor\skills\yuli-ceo"
copy /Y "%SKILL_ROOT%SKILL.md" "%PROJECT_ROOT%\.cursor\skills\yuli-ceo\SKILL.md" >nul
if errorlevel 1 goto :failed
echo Cursor skill mirror: ready

rem --- Claude routing ---
set "CLAUDE_ROUTING_FILE=%PROJECT_ROOT%\CLAUDE.md"
findstr /C:"YULI-ROUTING" "%CLAUDE_ROUTING_FILE%" >nul 2>&1
if errorlevel 1 (
  (
    echo.
    echo ^<!-- YULI-ROUTING --^>
    echo ## Yuli Chief of Staff / מנהלת מטה
    echo When the user invokes Yuli, מנהלת, or Activate Yuli — including Hebrew equivalents —
    echo read .claude/skills/yuli-ceo/SKILL.md and follow the canonical protocol at
    echo .agents/skills/yuli-ceo/SKILL.md. Enforce code review before commit-approval requests,
    echo and BLOCK On-Demand / push / deploy / deletes without explicit owner approval.
  ) >> "%CLAUDE_ROUTING_FILE%"
)
echo Claude command routing: ready

rem --- Codex / Cursor AGENTS.md routing ---
set "AGENTS_ROUTING_FILE=%PROJECT_ROOT%\AGENTS.md"
findstr /C:"YULI-ROUTING" "%AGENTS_ROUTING_FILE%" >nul 2>&1
if errorlevel 1 (
  (
    echo.
    echo ^<!-- YULI-ROUTING --^>
    echo ## Yuli Chief of Staff / מנהלת מטה
    echo When the user invokes Yuli, מנהלת, or Activate Yuli, read .agents/skills/yuli-ceo/SKILL.md
    echo and follow it. Review diffs before asking the owner to approve commits. BLOCK On-Demand,
    echo push, deploy, and deletes without explicit owner approval. Coordinate Andy / Uri / Valdi
    echo when those skills exist in this project.
  ) >> "%AGENTS_ROUTING_FILE%"
)
echo Codex/Cursor AGENTS routing: ready

echo.
echo Yuli Chief of Staff installed for Claude + Codex + Cursor. Technical id remains yuli-ceo.
echo Canonical: %SKILL_ROOT%SKILL.md
exit /b 0

:failed
echo Install failed.
exit /b 1