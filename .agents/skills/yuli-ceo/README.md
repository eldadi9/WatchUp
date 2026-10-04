# yuli-ceo / יולי (מנהלת מטה)

Portable Chief of Staff skill for **Claude Code**, **Codex**, and **Cursor**.
Technical id remains `yuli-ceo`. Eldad is Owner. Yuli "Jordan" is Chief of Staff.

One protocol. Three discovery paths. No project state inside this folder.

## Tool matrix

| Tool | Discovery path | What to install |
|---|---|---|
| **Codex** | `.agents/skills/yuli-ceo/SKILL.md` | Canonical folder + `AGENTS.md` YULI-ROUTING |
| **Cursor** | `.agents/skills/yuli-ceo/SKILL.md` (+ optional `.cursor/skills/yuli-ceo/`) | Same + `AGENTS.md` routing |
| **Claude Code** | `.claude/skills/yuli-ceo/SKILL.md` | Thin adapter → canonical + `CLAUDE.md` YULI-ROUTING |

## Install into a project (Windows)

1. Copy this folder to:
   `<project>/.agents/skills/yuli-ceo/`
2. Run:
   `<project>/.agents/skills/yuli-ceo/install_yuli_ceo.bat`

The installer:

- installs the Claude adapter under `.claude/skills/yuli-ceo/`
- mirrors the skill under `.cursor/skills/yuli-ceo/`
- appends `YULI-ROUTING` markers to `CLAUDE.md` and `AGENTS.md` once

## Manual install

```
# Canonical (Codex + Cursor)
yuli-ceo/  ->  <project>/.agents/skills/yuli-ceo/

# Claude Code adapter
yuli-ceo/adapters/claude/CLAUDE_SKILL.md
  -> <project>/.claude/skills/yuli-ceo/SKILL.md

# Optional Cursor browser mirror
yuli-ceo/SKILL.md
  -> <project>/.cursor/skills/yuli-ceo/SKILL.md
```

## Activate

Hebrew or English: `יולי` / `מנהלת` / `Activate Yuli` / `Yuli status` / `Yuli review`

## Does not include

Andy checkpoints, Uri phase plans, Valdi results, secrets, or JobHunterX-only paths.