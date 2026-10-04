---
name: andy
description: >-
  Use when the user says אנדי or Andy, with start, continue, status, save,
  switch, pause, close, or the equivalent Hebrew command. Also use when the
  user asks to resume work from a previous session or another AI tool in the
  same project without re-reading the full conversation.
---

# Andy — Session Continuity Agent

## Overview

Andy replaces manual HANDOFF documents with a small, local, tool-agnostic state
file. **The conversation is not the source of truth for continuity — a tiny
JSON snapshot is.** A new session (same tool or a different one: Codex,
Claude, Cursor, ChatGPT) reads that snapshot instead of the chat history and
continues from `next_action`.

Two things are strictly separate:

| | Location | Contains |
|---|---|---|
| **Skill** (this folder) | `.agents/skills/andy/` | Canonical rules for Codex and Cursor — general, copy-pasteable to any project |
| **State** (per project) | `.ai/andy/` | This project's snapshot only — never copied between projects |

Copying the skill into a new project must NEVER bring along another
project's state. Running `install_andy.bat` may pre-create a clean
`status: new` state; it never copies project context. Without the installer,
`.ai/andy/` is created when the user first invokes Andy.

Claude Code does not discover `.agents/skills/` directly. For Claude Code,
also install the thin adapter template from `adapters/claude/CLAUDE_SKILL.md` at
`.claude/skills/andy/SKILL.md`. The adapter points back to this canonical
skill; all tools still share the same `.ai/andy/` state.

## Commands

Recognize Hebrew and English equally. Match on "אנדי"/"Andy" plus the verb;
bare "אנדי" / "Andy" alone = **continue**.

| Hebrew | English | Action |
|---|---|---|
| אנדי התחל | Andy start | Start/init a workstream (see Init) |
| אנדי | Andy | Default = continue (see Continue) |
| אנדי המשך | Andy continue | Same as bare "אנדי" |
| אנדי מצב | Andy status | Read-only status report |
| אנדי שמור | Andy save | Forced checkpoint now |
| אנדי החלף | Andy switch | Checkpoint + prep for a different tool/session |
| אנדי עצור | Andy pause | Checkpoint, status=paused |
| אנדי סגור | Andy close | Final checkpoint, status=completed, archive to history/ |

## Project root and state location

Always resolve state relative to the **current project root** (git root if
in a repo, else the working directory the user is operating in). Never read
or write `.ai/andy/` in a different project. Never load history from another
project.

State lives once per project/repository. Linked Git worktrees are the same
project and share the canonical state under the primary worktree; unrelated
repositories never share state. The active worktree path is stored separately
so file and Git verification run against the checkout where work happened.

State lives at:
```
<project_root>/.ai/andy/
  current.json
  sessions/       # only needed for multiple concurrent workstreams
  history/        # snapshots at close/phase boundaries only
```

`current.json` follows `schema.json` in this skill folder. Use
`scripts/andy_state.py` for init/read/write/verify — it does atomic writes
(temp file + validate + rename) so a crash mid-write can't corrupt state, and
factors out git-drift checking so you don't hand-roll it each time:

```bash
python .agents/skills/andy/scripts/andy_state.py init   <project_root>
python .agents/skills/andy/scripts/andy_state.py read   <project_root>
python .agents/skills/andy/scripts/andy_state.py verify <project_root>
python .agents/skills/andy/scripts/andy_state.py write  <project_root> <file|->
python .agents/skills/andy/scripts/andy_state.py archive <project_root> [slug]
python .agents/skills/andy/scripts/andy_state.py migrate-worktrees <project_root>
```

If Python isn't available in the environment, perform the equivalent steps
manually (read JSON, edit in memory, write to a temp file, validate, replace)
— never edit `current.json` in place without a temp-file swap.

## current.json — what it is and isn't

It is a **small operational snapshot**: current phase/task, what's done,
what's next, restrictions, touched files, git pointer, who worked last. It is
NOT a transcript, not full memory, not a long handoff document, and never
holds reasoning or copied prompts. Target size: hundreds of tokens, not
thousands. See `schema.json` for the full field list.

## Init — "אנדי התחל" / "Andy start"

1. Resolve project root.
2. Run `andy_state.py init <project_root>` (creates `.ai/andy/` + subfolders
   + a default `current.json` only if one doesn't already exist).
3. If the installer already created `current.json` with `status: new`, continue
   Init normally. **If a workstream is active, paused, blocked, or completed,
   do not silently overwrite it.** Show its current goal/status and handle it
   according to the relevant command flow. Start a parallel workstream only
   when the user requests one.
4. Otherwise, from the current conversation, fill in: `goal`,
   `current_phase`, `current_task`, `next_action`, known `restrictions`
   (e.g. "no commit", "no push", "no production changes" — capture these
   verbatim, they are binding, see Safety), and `source_of_truth` pointers
   (e.g. `PRD.md`) rather than copying their content.
5. Capture git state if this is a repo (`branch`, `head`, `dirty`).
6. Set `status: active`, `last_worker` to the current tool if identifiable.
7. Checkpoint (write the file).

For a linked Git worktree, pass that worktree root to every command. The helper
locates the primary repository's canonical state and records the active
worktree in `workspace_root` automatically.

## FRESH STATE RULE (hard rule)

Every Andy continue/status invocation MUST perform a fresh read of the
project-local `.ai/andy/current.json` during the **current turn**. Previously
loaded Andy state, conversation context, prior Andy replies, summaries, or
memory MUST NOT be used as a substitute for this read — not even if you
"already read it earlier in this session." If the freshly read file conflicts
with anything you previously believed about Andy's state, the freshly read
file wins, unconditionally.

Concretely, on every "אנדי" / "Andy" / "Andy continue" / "אנדי מצב":
1. Resolve the project root fresh (don't assume it's unchanged).
2. Read `current.json` from disk this turn (via `andy_state.py read` or
   equivalent) — never answer from what a prior turn already reported.
3. Note the freshly read `updated_at` and `last_worker`.
4. Only after that read: run git/file verification and compare reality to
   the freshly read state — never to a remembered previous state.
5. Display the loaded checkpoint only for an explicit Status command. A bare
   Andy/Continue command loads and verifies it silently, then continues the
   work. Never print checkpoint data merely because an automatic save ran.
6. Never say "same state as before" unless you both (a) actually performed
   this fresh read this turn, and (b) explicitly compared its `updated_at`
   to the previously loaded checkpoint's `updated_at` and confirmed they
   match. Silence on this comparison means don't claim it.

This applies identically across tools (Codex, Claude, Cursor) — whichever
tool most recently wrote `current.json` is authoritative, regardless of
which tool is being asked to continue.

### Timestamp display format (display-only)

`current.json` always stores timestamps in ISO 8601 (e.g.
`2026-09-10T23:43:57Z`) — **never change this storage format.** It is only
the user-facing rendering that differs:

- Wherever a timestamp is shown to the user — `Checkpoint loaded:`,
  `Last checkpoint:`, or any other display of `updated_at` — render it as
  `DD/MM/YYYY HH:mm` (e.g. `10/09/2026 23:43`), derived from the exact value
  read this turn.
- If the stored value carries explicit timezone/offset info, convert
  correctly and show local time; don't silently assume a timezone that
  isn't in the data. If the value is bare UTC (`Z`) with no target timezone
  known, display the UTC clock time as-is (e.g. `23:43`) rather than
  guessing a conversion.
- If the stored value fails to parse as a valid timestamp, fall back to
  showing the original raw stored string rather than `unavailable` — reserve
  `unavailable` for when `updated_at` itself is missing or null (see step 5
  above).
- This formatting applies only to display. Any value written back to
  `current.json` (via `andy_state.py write`) stays ISO 8601, untouched.

## Continue — bare "אנדי" / "Andy" / "אנדי המשך"

1. Resolve project root, read `current.json` **fresh from disk this turn**
   (see FRESH STATE RULE above — do not reuse a previously loaded copy).
   - Missing but `history/` has entries → don't guess; offer to restore
     from the latest history snapshot.
   - Corrupt → the script auto-backs it up; report this and ask how to
     proceed rather than silently reinitializing.
   - Multiple active workstreams under `sessions/` → list them briefly and
     ask which one, don't guess.
2. **Verify before trusting the snapshot** (cheap checks only):
   - Files in `files_touched`/`files_created` still exist.
   - Git branch/head match what's stored (script's `verify` reports
     `git_drift`).
   - `next_action` still makes sense given what's actually in the repo now.
3. Respect the saved status before continuing:
   - `active` → continue directly from `next_action`.
   - `paused` → state that the paused work is being resumed, set `active`,
     checkpoint, then continue from `next_action`.
   - `blocked` → report the blocker and do not continue until it is resolved.
   - `completed` → do not reopen it silently; offer to start a new workstream
     or restore a history snapshot.
   - `new` → collect the missing goal/task context and complete Init first.
4. If something drifted slightly (e.g. an extra commit landed), update the
   relevant fields and continue.
5. If there's a real conflict (state says a file exists but it's gone, or
   the branch changed to something unrelated) — **do not guess**. Report
   the mismatch in one or two lines and ask how to proceed.
6. Continue from `next_action` without printing a restoration report. The
   read, verification, and any automatic checkpoint remain behind the scenes.
   Report only a real blocker or conflict that requires user action.

## Status — "אנדי מצב" / "Andy status"

Read-only, but still bound by the FRESH STATE RULE above — read
`current.json` fresh from disk this turn before reporting anything. Report:
Project, Goal, Status, Phase, Current task, Last completed, Open tasks, Next
action, Last worker, Blockers, Git state, and a **mandatory**
`Checkpoint loaded: <updated_at>` (equivalently `Last checkpoint:`) line
sourced from this turn's fresh read and rendered as `DD/MM/YYYY HH:mm` per
"Timestamp display format" above (e.g. `Last checkpoint: 10/09/2026 23:43`),
or `Checkpoint loaded: unavailable` if `updated_at` is missing/null — never
guessed. Do not modify `current.json` beyond what verification
strictly requires (e.g. it's fine to note drift, not fine to rewrite the
plan) — status must never write a checkpoint.

## Save — "אנדי שמור" / "Andy save"

Force a checkpoint immediately regardless of the auto-checkpoint rules
below. After it succeeds, show one short confirmation with the new checkpoint
time. This explicit command is one of only two commands that displays Andy
state information; the other is Status. Keep it short and precise — same
delta-update principle applies.

Always call the helper with a project root and a JSON patch file, even for an
empty checkpoint. Do not pipe raw stdin unless the helper argument is `-`.

Recommended save sequence:

1. Read state fresh and copy its exact `updated_at` value.
2. Write a tiny patch JSON file containing `_base_updated_at` plus only actual
   state changes. For an empty forced checkpoint, include only
   `_base_updated_at`.
3. Run:

```bash
python .agents/skills/andy/scripts/andy_state.py write <project_root> <patch_file>
```

4. Delete the temporary patch file after a successful write.

`_base_updated_at` is a compare-and-swap guard and is not stored. If another
session saved first, the helper returns `stale_checkpoint`; read again,
reconcile the newer state, and retry. Never overwrite a newer checkpoint with
an older snapshot.

## Switch — "אנדי החלף" / "Andy switch"

Prepare state so a *different* tool/session can pick up seamlessly:

1. Full, current checkpoint: `current_task`, `last_completed`,
   `next_action`, `files_touched`, `tests`/`errors`/`blockers`, `git`.
2. Make sure any decision made in this session that matters going forward
   is in `decisions`.
3. Set `last_worker` to the current tool's name.
4. Keep `status: active` — switching tools isn't pausing or finishing.
5. Do NOT produce a long handoff doc. The state file is the handoff.
6. Tell the user in one line that state is ready for another tool, e.g.
   "State saved — open the project in Codex/Cursor and say 'אנדי'/'Andy' to
   continue."

## Pause — "אנדי עצור" / "Andy pause"

Checkpoint, `status: paused`, keep `next_action` and any `blockers`. Do not
mark anything completed.

## Close — "אנדי סגור" / "Andy close"

1. Final checkpoint with a short completed-summary.
2. `status: completed`.
3. Run `andy_state.py archive <project_root> [slug]` to copy the validated
   final snapshot into `history/<UTC-timestamp>_<slug>.json`.
4. Never delete prior history. A new workstream started later must not
   overwrite past history entries.

## Delta updates (required)

Pass only changed fields to `andy_state.py write`. The helper recursively
merges object fields into the current validated state, then atomically writes
the result. Arrays supplied in a patch replace that array, so read first and
include retained entries when appending. Example — after
finishing "Plate 4":

```
last_completed += "Plate 4"
current_task = "Plate 5"
next_action = "Revise Plate 5 with stronger E visual language"
```

Everything else (goal, restrictions, git, older history) stays untouched by
the helper.
This is what keeps the file small and keeps token cost low.

## Auto-checkpoint: event-based hard gate

Checkpoint immediately after **any change, with no importance threshold**:
any file creation/edit/deletion, command result that changes observable state,
task or phase progress, decision, user confirmation, `next_action` update,
test or validation result, error or blocker, status update, or git change.
Agents do not decide whether a change is "important enough" to save.

**Before-final-response gate:** while Andy's state is `active`, `paused`, or
`blocked`, every tool must check whether the current turn made any state or
workspace change. If yes, it MUST perform a fresh read and successful guarded `write`
before sending its final response. A final response that describes unsaved
completed work is a protocol failure. This applies on later turns even when the
user does not repeat the word Andy.

**Main thread only (token governance):** the gate applies to the main /
coordinating thread. A dispatched subagent (Codex `spawn_agent`, Claude
`Agent`/`Task`, engine worker) never reads this skill, never reads
`current.json`, and never writes Andy state. It returns its result to Ori; the
main thread saves the checkpoint.

**Silent operation is mandatory:** automatic reads, verification, writes, and
successful checkpoints produce no user-facing status, timestamp, JSON, or
"saved" message. They happen behind the scenes. Display Andy state only for an
explicit `Andy status` / `אנדי מצב`, or a brief save confirmation for explicit
`Andy save` / `אנדי שמור`. Errors that genuinely block work may still be
reported.

### Reliability rules

1. **Before-risk checkpoint:** save before a long-running command, broad edit,
   context-heavy analysis, model/tool switch, compaction risk, or any action
   likely to consume the remainder of the session. Record the intended action
   in `next_action` before starting it.
2. **After-mutation checkpoint:** after every tool result that changes files,
   tests, validation, git state, decisions, blockers, task, or phase, checkpoint
   before starting another substantial action.
3. **Turn-boundary checkpoint:** never return control to the user with any
   unsaved change. This includes questions asked after partial work.
4. **Phase-boundary checkpoint:** checkpoint immediately before and after a
   task or phase transition. The first write preserves the old phase's final
   state; the second records the new current task and next action.
5. **Concurrency retry:** every write uses `_base_updated_at`. On
   `stale_checkpoint`, read fresh, merge only this session's delta, preserve
   newer unrelated fields, and retry. Never replace the newer full snapshot.
6. **Canonical repository state:** all linked worktrees share one state file;
   `workspace_root` identifies the checkout where the latest work occurred.
7. **Restore verification:** Continue verifies the saved worktree, branch,
   commit, dirty flag, and referenced files before acting. If reality is newer,
   reconcile the checkpoint silently when unambiguous.
8. **No deferred batching:** do not wait for several prompts before saving.
   Every change closes with its own checkpoint.
9. **Three-exchange heartbeat:** even when no workspace change was detected,
   checkpoint silently after at most three completed user/assistant exchanges
   with no changes since the previous checkpoint. Count exchanges in the active session and
   reset the count after every successful write. This is a safety heartbeat,
   not permission to delay a change checkpoint.
10. **Conversation delta:** the three-exchange heartbeat is not an empty
    timestamp write. Persist a concise delta of every newly clarified
    requirement, answer that affects future work, decision, pending question,
    restriction, current task, and next action. Never store the transcript or
    reasoning. If nothing operational was added, an empty guarded checkpoint
    is allowed.
11. **Small-state restore:** a new session restores from this compact JSON and
    its named source-of-truth files. It must not reread the old chat or scan the
    whole repository merely to reconstruct conversational context.

Pure explanations and questions with no state or workspace change use the
three-exchange heartbeat. They do not require an immediate checkpoint before
that heartbeat is reached.

Track this cheaply in `checkpoint_health`:
- `turns_since_checkpoint` remains for diagnostics but is not a delay timer.
- Use it as the persisted value for the three-exchange heartbeat when the
  current tool can track completed exchanges reliably.
- Set `dirty_since_checkpoint = true` in session memory the moment any
  change happens; the before-final-response gate must then write.
- `andy_state.py write` records the checkpoint timestamp and resets
  `turns_since_checkpoint = 0` and `dirty_since_checkpoint = false`.

## Token efficiency (non-negotiable)

Never store: full transcript, reasoning, full prompts, a full HANDOFF doc
recreated each save, or content copied from `AGENTS.md`/`CLAUDE.md`/PRD
files — reference them by path in `source_of_truth` instead. Never re-scan
the whole repo on every "אנדי" — check only what verification needs (files
named in state, git branch/head).

Checkpoint budget: `current.json` stays at or below **6144 bytes**
(`resource_governance.checkpoint.max_bytes`). Keep only the newest
`last_completed` / `decisions` / `tests` / `validation` entries. When it grows
past the budget, run `python andy_state.py compact <project_root>`: the oldest
entries move to `history/*_compact-overflow.json`. To continue work, read the
resume packet (`python andy_state.py resume <project_root>`: objective,
completed, active, blocked, changed files, validation state, next exact
action, essential decisions) instead of the whole file.

## Safety and restrictions

Andy has no elevated permissions. Restrictions found in the project (e.g.
"no commit", "no push", "no deploy", "read only", "do not touch production
DB") go into `restrictions` verbatim and bind every tool that reads this
state afterward. Saying "אנדי" or "Andy" is never itself authorization to
commit, push, deploy, delete, or touch production — normal project rules and
explicit user confirmation still apply on top of Andy.

## Source of truth hierarchy

1. Actual files/code in the project.
2. Git state (if present — git is a verification layer, not a requirement;
   Andy works fine without it).
3. Project constitution files (`AGENTS.md`, `CLAUDE.md`, PRD, etc.) —
   referenced, not duplicated.
4. Andy's `current.json` — authoritative for "where did work stop", but
   never overrides what's actually in the code. Reality wins; update Andy's
   state to match reality, not the other way around.

## Project isolation (hard requirement)

Never read, write, or reference `.ai/andy/` outside the current project
repository. Linked worktrees whose `git rev-parse --git-common-dir` resolves to
the same directory are one project and intentionally share the primary
worktree's canonical state. Reject every other external path, absolute path in
state file lists, and `..` traversal. Never let one repository's
`current.json`, `sessions/`, or `history/` leak into another. Copying `andy/`
(the skill) to a new project must never copy `.ai/andy/` (the state).

## Common mistakes

| Mistake | Fix |
|---|---|
| Writing a full HANDOFF.md on "אנדי החלף" | The state file *is* the handoff — don't create a parallel doc |
| Rewriting all of `current.json` on every save | Delta-update only the changed fields |
| Sending a final reply after any change without saving | The before-final-response gate requires a fresh guarded write first |
| Printing checkpoint details after a normal automatic save | Keep autosave silent; display state only for explicit Status or Save commands |
| Separate Andy states in linked worktrees | Run `migrate-worktrees` once; later commands resolve the canonical repository state |
| Trusting `current.json` blindly on resume | Run cheap verification first; report conflicts, don't guess |
| Answering "אנדי"/status from a previous turn's Andy read or conversation memory | Always re-read `current.json` from disk this turn (FRESH STATE RULE) — a prior read, even from earlier this session, is not sufficient |
| Saying "same state as before" without comparing `updated_at` | Only say it after freshly reading the file this turn and confirming `updated_at` actually matches |
| Copying `.ai/andy/` when copying the skill to a new project | Only copy `andy/` (the skill folder); state is created fresh via "אנדי התחל" |
| Treating "אנדי" as permission to commit/push/deploy | Restrictions and normal confirmation rules still apply |
| Guessing which workstream when several are active | List them, ask — never guess |
