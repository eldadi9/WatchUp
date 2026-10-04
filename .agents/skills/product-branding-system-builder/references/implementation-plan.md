# Implementation Plan (Phase 3)

Once branding docs exist, don't stop at documentation if the user wants the brand
actually applied to the app. Translate the brand system into a concrete,
execution-ready plan before touching any code — this is what makes Phase 3 safe to
approve.

## Build `docs/branding/BRANDING_IMPLEMENTATION_PLAN.md`

Use the existing branding docs as the source of truth (`MASTER_BRAND_SYSTEM.md`,
`BRAND_BOOK.md`, `DESIGN_TOKENS.md`, `DESIGN_SYSTEM.md`, `DASHBOARD_UI_SYSTEM.md`,
`MOBILE_APP_GUIDE.md`, `README_DESIGN_GUIDE.md`, `GITHUB_SHOWCASE_GUIDE.md`,
`ANIMATION_STYLE_GUIDE.md`, `UI_UPGRADE_ROADMAP.md`, `BRANDING_GAP_REPORT.md`) and, if
brand board images were generated in Phase 0, the images under `assets/branding/`. Map
the brand system onto real files found by inspecting the repo — don't make abstract
recommendations when a concrete file path is available.

Cover each of these areas, only where they apply to the project:

1. **Global layout** — app shell, header, sidebar/bottom nav, content areas, spacing,
   typography, dark/light mode, RTL if relevant, overall hierarchy.
2. **Logo and top identity** — logo placement and size, app name, version badge,
   favicon/PWA icon alignment, mobile logo behavior.
3. **Design tokens** — find the real files (`global.css`, `index.css`, `tailwind.config.*`,
   `theme.ts`, `tokens.ts`, component style files — never invented ones) and map colors,
   typography, spacing, radius, shadows, borders, and status colors into them. For each
   token group: current state, target state, files to update, risk level, how to
   validate the change.
4. **Components** — a component-by-component plan (buttons, cards, inputs, forms,
   tables, modals, navigation, badges, alerts, empty/loading/error/success states, KPI
   cards, agent/workflow panels if relevant). For each: current problem, branding
   target, files to update, exact visual change, functional risk, test required.
5. **Pages** — a page-by-page plan from the app's actual routes: current state, desired
   state, components involved, files to update, priority, dependencies.
6. **Dashboard** (if relevant) — shell, KPI cards, charts, tables, activity feed, status
   panels, responsive behavior, RTL support if relevant.
7. **Mobile/PWA** (if relevant) — icon, splash, header, bottom nav, touch spacing, cards,
   manifest assets.
8. **README/GitHub** — hero, feature cards, screenshots, diagrams, roadmap, setup,
   badges, social preview.
9. **Assets** — logo files, icons, favicons, splash, social previews, screenshots,
   mockups. Never claim an asset exists if it wasn't generated — list it under "files to
   create" instead.

## Files-to-change table

Include a table like this, listing only files that actually exist in the repo (put
files that need to be newly created in a separate "Files to Create" list):

| Area | File | Change Type | Why | Risk | Validation |
|---|---|---|---|---|---|

## Execution order

1. Backup / git status check
2. Read branding docs
3. Implement design tokens
4. Implement global layout styles
5. Implement shared components
6. Implement page-level branding
7. Implement dashboard branding
8. Implement mobile/PWA branding
9. Implement README/GitHub showcase
10. Validate build, tests, screenshots, git diff

## Stop and get approval

After writing `BRANDING_IMPLEMENTATION_PLAN.md`, stop. Don't start changing UI code
until the user explicitly says something like "approve branding implementation," "start
implementing the brand system," or "apply the design to the app." This is the point
where a plan turns into an actual diff — worth a deliberate go-ahead rather than
momentum carrying it forward.

## While implementing

Read all `docs/branding/*.md` files and the implementation plan first, check git
status, then make small, safe changes: keep all functionality working, don't delete
existing logic, don't change backend behavior, don't break routes/forms/data loading,
prefer shared tokens/components over one-off styling, and run tests/build after
changes. Show a git diff summary at the end so the user can review exactly what moved.
