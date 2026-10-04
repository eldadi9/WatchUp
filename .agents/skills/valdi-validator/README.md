# valdi-validator / ולדי (מבקר)

Portable quality & validation skill for Claude, Codex, and Cursor.

## Role
Policy gate + quality diff review + ponytail (when needed) + focused debug.

## Efficiency (locked)
- Default intensity: **LITE**
- Short Hebrew-first report, then brief technical
- Cap findings; no token-heavy deep scans unless STANDARD/DEEP

## Install
1. Copy this folder to `<project>/.agents/skills/valdi-validator/`
2. Run `install_valdi_validator.bat` from that folder
   - or copy `adapters/claude/CLAUDE_SKILL.md` → `<project>/.claude/skills/valdi-validator/SKILL.md`
   - and mirror `SKILL.md` → `<project>/.cursor/skills/valdi-validator/SKILL.md`