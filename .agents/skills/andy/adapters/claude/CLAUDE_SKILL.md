---
name: andy
description: >-
  Use when the user says אנדי or Andy, with start, continue, status, save,
  switch, pause, close, or the equivalent Hebrew command. Also use for session
  continuity and resuming work from another AI tool in the same project.
---

# Andy adapter for Claude Code

Read `.agents/skills/andy/SKILL.md` from the current project root and follow
that canonical protocol for the user's Andy command. Use its script and schema.
Store state only in the current project's `.ai/andy/`; never create a separate
Claude-specific state. Linked Git worktrees of the same repository share the
canonical state selected by `andy_state.py`; always pass the active worktree
root to the helper.

If the canonical skill is missing, report the expected path and stop instead
of creating a different implementation.

**FRESH STATE RULE applies here too:** on every "אנדי" / "Andy" / status
invocation, read `.ai/andy/current.json` fresh from disk during this turn.
Do not answer from a previous turn's Andy output, this session's earlier
read, or conversation memory — even if another tool (e.g. Codex) wrote the
file after Claude last read it. The freshly read file always wins. See the
canonical skill's "FRESH STATE RULE" section for the full requirement.

**Silent continuation:** Continue/bare Andy reads and verifies the checkpoint
without displaying a restoration report. Show checkpoint details only for an
explicit Status command, or a brief confirmation after explicit Save.

**Display format:** render the timestamp as `DD/MM/YYYY HH:mm` (e.g.
`10/09/2026 23:43`) per the canonical skill's "Timestamp display format"
section — this is display-only; the stored `current.json` value stays ISO
8601 and must never be rewritten in a different format. If the stored value
fails to parse, show the original raw string instead of guessing.

**Persistent auto-save gate:** after Andy is activated, this applies to later
turns even if the user does not repeat “Andy”. Before every final response that
follows any state or workspace change, read the canonical state fresh and call
`andy_state.py write` with `_base_updated_at` set to the exact `updated_at` just
read. Do not send the final response until the guarded write succeeds. If it
returns `stale_checkpoint`, read and reconcile the newer checkpoint first.
Checkpoint before risky or long actions, after every tool mutation of any size,
and before returning control to the user. Also checkpoint after at most three
completed user/assistant exchanges since the previous write, even when no
workspace change was detected. That heartbeat stores a compact conversation
delta: new requirements, decisions, restrictions, pending questions, current
task, and next action, without transcript or reasoning. Successful automatic
saves are completely silent; never print their status, timestamp, summary, or
JSON.
