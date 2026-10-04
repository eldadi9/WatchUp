# Documentation Outputs

## `docs/branding/` files

Create or update these. If a file already exists, improve it carefully — don't delete
useful content, duplicate sections, or overwrite project-specific information that's
still accurate.

| File | Contents |
|---|---|
| `MASTER_BRAND_SYSTEM.md` | The single top-level summary tying every other doc together — brand foundation, values, personality, and a pointer to each of the files below. |
| `BRAND_BOOK.md` | Logo direction, color palette, typography, visual mood, product personality, brand rules. |
| `DESIGN_TOKENS.md` | The color/typography/spacing/radius/shadow token list, using the token naming from `brand-system-guide.md`. |
| `DESIGN_SYSTEM.md` | The full UI system: components, states, patterns. |
| `DASHBOARD_UI_SYSTEM.md` | Dashboard design language, if the project has one. |
| `MOBILE_APP_GUIDE.md` | Mobile/PWA identity, if relevant. |
| `README_DESIGN_GUIDE.md` | How the README should be structured and why. |
| `GITHUB_SHOWCASE_GUIDE.md` | Badges, screenshots, diagrams, repo description, social preview guidance. |
| `CASE_STUDY_GUIDE.md` | How to present this project as a portfolio case study. |
| `ANIMATION_STYLE_GUIDE.md` | Motion and micro-interaction rules. |
| `ASSETS_STRUCTURE.md` | The asset folder layout below, annotated for this project. |
| `BRANDING_GAP_REPORT.md` | What's missing today — no icon, no design tokens, inconsistent color use, etc. This is the honest inventory the roadmap is built from. |
| `UI_UPGRADE_ROADMAP.md` | What to do about the gaps, roughly ordered. |

## Asset structure

Use this layout if the project doesn't already have its own asset structure; if it does,
align with the existing one rather than introducing a conflicting layout.

```
assets/
  icons/
  logos/
  splash/
  social/
  screenshots/
  mockups/
  dashboard/
  mobile/
  animations/
  readme/
  branding/
```
