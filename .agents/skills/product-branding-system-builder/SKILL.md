---
name: product-branding-system-builder
description: Builds a complete premium product branding system for any software repository — brand identity, color/typography/design tokens, UI and dashboard design language, mobile/app icon identity, README and GitHub presentation, and a file-by-file implementation plan. Use this whenever the user asks to "brand" a project, give it a "design system," make it "look premium/investor-ready," redesign its README as a landing page, create a brand book, define design tokens, or generate a GitHub/portfolio presentation for a repo — even if they just say "make this repo look professional" or "give this project an identity." Also use when the user wants brand-consistent app icons, splash screens, or a dashboard visual language. Always inspect the actual repository before writing anything — this skill never invents architecture, commands, or screenshots that don't exist.
---

# Product Branding System Builder

## What this is

A reusable process for turning any software project into something that feels like a
real, premium product — not a logo task, a full product identity and design system
exercise. Approach it the way a small senior team would: product designer, brand
architect, UI director, UX strategist, and (when the project has AI/agent features) an
AI product branding specialist.

This skill is deliberately generic. Never hardcode a project name, industry, or stack —
every run should adapt to whatever repository it's pointed at.

## The core rule: inspect before you invent

Before writing anything, read what's actually in the project: `README.md`,
`package.json`, `requirements.txt`, `pyproject.toml`, `vite.config.*`, `src/`, `app/`,
`docs/`, and any existing branding docs, screenshots, or design tokens. If a file
doesn't exist, don't fail — just note it as missing in the gap report.

This matters because a branding system that contradicts the real product (fake setup
commands, invented architecture, screenshots that don't exist) actively damages trust
instead of building it. Where something is genuinely unclear, mark it `TODO` rather than
guessing — a visible gap is more useful than a confident wrong answer.

## Optional inputs

If the user provides them, use them; otherwise infer carefully from the repo, and fall
back to placeholders + TODO markers rather than guessing: project name, product
category, target audience, product description, main use case, app personality,
preferred colors/style, a reference image folder, an existing logo/icon path, creator
name, version number, and which phases to run (docs only vs. README vs. UI
implementation vs. commit).

## Workflow: five phases, each gated by approval

Work in phases and stop between them unless the user has clearly asked for more than
one. This keeps a branding pass from silently turning into a large, hard-to-review code
change.

**Default behavior:** if the user just says "run the branding skill" / "build the brand
language" / "create the product branding system" with no further detail, do **Phase 1
only** — documentation, not code changes.

### Phase 0 — Brand board images (optional, only if asked or if image generation is available)
Generate the 11-image premium branding reference board (brand book, UI system,
dashboard language, mobile identity, README showcase, portfolio/case study, visual
direction, motion, product personality, GitHub presentation, AI product branding). See
`references/image-brief.md` for the exact prompt template — fill in the project name and
description from repo inspection or user input, never leave placeholders in the actual
generation call.

### Phase 1 — Branding documentation (the default)
Inspect the repo, work out what the product does/for whom/what makes it different, and
write the brand foundation into `docs/branding/`. See `references/documentation-outputs.md`
for the full file list and what belongs in each one, and `references/brand-system-guide.md`
for how to derive brand values, personality, color system, typography, UI system,
dashboard language, mobile identity, icon system, AI branding layer, and motion rules.
Also produce `BRANDING_GAP_REPORT.md` (what's missing) and `UI_UPGRADE_ROADMAP.md` (what
to do about it). No code changes in this phase.

### Phase 2 — README upgrade (only if requested)
Redesign `README.md` into something closer to a premium landing page: hero section,
product story, feature cards, architecture/workflow diagrams (Mermaid, kept valid), setup
instructions taken from the real repo (never invented — TODO if unclear), roadmap. See
`references/readme-github-system.md`. Don't commit unless explicitly asked.

### Phase 3 — UI branding implementation (only with explicit approval)
Apply the design tokens and component rules to the real codebase — layout, header,
navigation, cards/buttons/inputs/states, dashboard, mobile/PWA if relevant. Preserve all
existing functionality; this is a re-skin, not a rewrite. Build a file-by-file plan
first (`references/implementation-plan.md`) and get it approved before touching code.
Run tests/build after changes.

### Phase 4 — Asset and icon system (only if requested)
Define (and, if requested, generate) app icon, favicon, splash, and social preview
assets per `references/documentation-outputs.md`'s asset structure. Never claim an asset
exists if it wasn't actually created — list it as TODO instead.

### Phase 5 — Commit (only if explicitly requested)
Check branch and git status, summarize the diff, commit with a clear message. Don't push
unless separately asked.

## Approval gates

Treat these as checkpoints, not formalities — each one is a natural point where the user
might want to stop, redirect, or review before more gets built on top of it:
1. Branding docs created (end of Phase 1)
2. Implementation plan created (before any code changes)
3. User approves UI implementation
4. User approves README implementation
5. User approves asset/icon implementation
6. User approves commit/push

If the user says "apply the brand system" / "implement the branding" / "use the
branding docs and update the app," that's approval to move from planning into Phase 3 —
but still read all the `docs/branding/*.md` files and check git status first.

## Safety rules

These aren't stylistic preferences — they're what keeps a branding pass from turning
into an unreviewed rewrite of someone's application:

1. Don't change backend logic unless explicitly requested.
2. Don't remove existing functionality.
3. Don't change workflows unless explicitly requested.
4. Don't delete existing files without approval.
5. Don't invent architecture, commands, or screenshots.
6. Don't expose secrets or modify `.env` files.
7. Don't break existing design tokens without a stated reason.
8. Don't commit or push unless explicitly requested.
9. Keep the product feeling consistent, premium, and specific — not childish, generic,
   cluttered, or randomly decorated.

## Quality checks before finishing any phase

Markdown renders correctly, Mermaid diagrams are valid, internal links and screenshot
paths aren't broken, setup commands are real or marked TODO, brand docs don't
contradict each other or duplicate sections, no secrets were exposed, and existing
functionality is unchanged. If tests/build are relevant and safe to run, run them; if
not, say why not.

## Final report

End every run with a short report — see `references/report-formats.md` for the exact
structure to use (it differs slightly for a documentation-only run vs. an implementation
run). Always include what was created/changed, current git status, and a TODO list —
the TODO list is often the most useful part, since it's the honest record of what still
needs a human decision.

## Reference files

- `references/brand-system-guide.md` — how to derive brand values, personality, color
  system, typography, UI system, dashboard language, mobile identity, icon system, AI
  branding layer, and motion rules from a project
- `references/documentation-outputs.md` — the `docs/branding/*.md` file list, what goes
  in each, and the `assets/` folder structure
- `references/readme-github-system.md` — README redesign rules and GitHub presentation
  guidance
- `references/implementation-plan.md` — how to build `BRANDING_IMPLEMENTATION_PLAN.md`
  and carry out Phase 3 safely
- `references/image-brief.md` — the 11-image brand board generation prompt template
- `references/report-formats.md` — final report templates
