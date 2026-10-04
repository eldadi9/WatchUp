# Andy — Session Continuity Agent

Andy lets you drop a session (or switch AI tools — Codex, Claude, Cursor,
ChatGPT) on a project and pick up exactly where you left off, without a
manual HANDOFF and without re-reading the whole conversation.

This folder is the canonical Andy distribution source. Installed projects
receive copies under `.agents/skills/andy/`; project-specific `.ai/andy/`
state is never copied back to this source or between projects.

## Install (Windows, one click)

1. Copy this entire folder into the project:

```
andy/  ->  <project>/.agents/skills/andy/
```

2. Double-click:

```
<project>/.agents/skills/andy/install_andy.bat
```

The installer:

- creates `.claude/skills/andy/` if needed;
- copies `adapters/claude/CLAUDE_SKILL.md` there as `SKILL.md`;
- creates a clean `.ai/andy/current.json`, `sessions/`, and `history/`;
- preserves an existing `current.json` instead of overwriting it.

Restart any AI sessions that were already open, then say `אנדי התחל` or
`Andy start`. The installer creates only an empty `status: new` state; the
start command captures the actual goal, task, restrictions, and worker.

## Manual install

Codex and Cursor discover the core after it is copied to `.agents/skills/andy/`.

Claude Code does not scan `.agents/skills/`. To use the same Andy core with
Claude Code, also copy the included adapter:

```
andy/adapters/claude/CLAUDE_SKILL.md
  -> <project>/.claude/skills/andy/SKILL.md
```

The adapter reads the canonical `.agents/skills/andy/SKILL.md`. Codex, Cursor,
and Claude therefore use one protocol and one shared `.ai/andy/current.json`.
Linked Git worktrees of the same repository also share that canonical state;
different repositories keep separate JSON files.
Automatic checkpoints are mandatory and silent. Andy displays state only for
an explicit Status command or a brief confirmation after explicit Save.
As a fallback heartbeat, Andy also checkpoints after at most three completed
user/assistant exchanges, even if no workspace change was detected. That
checkpoint captures a compact conversation delta so a new session can resume
without rereading the old chat.
To initialize the state manually, run:

```
python .agents/skills/andy/scripts/andy_state.py init <project-root>
```

## Start

In the project, say:

```
אנדי התחל
```
(or: `Andy start`)

This creates `<project>/.ai/andy/` if the installer has not already created
it, then activates the workstream and records the initial checkpoint.

## Resume

New session, same or different tool, same project folder:

```
אנדי
```
(or: `Andy`)

## Commands

| Hebrew | English |
|---|---|
| אנדי התחל | Andy start |
| אנדי | Andy (continue) |
| אנדי מצב | Andy status |
| אנדי שמור | Andy save |
| אנדי החלף | Andy switch |
| אנדי עצור | Andy pause |
| אנדי סגור | Andy close |

## State location

`.ai/andy/` inside each project — local to that project, never shared or
copied across projects. Keep `.agents/skills/andy/` and the Claude adapter:
`.ai/andy/` stores data but cannot implement saving or restoration by itself.
See `SKILL.md` for the full protocol.
