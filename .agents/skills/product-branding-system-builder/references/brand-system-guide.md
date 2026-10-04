# Brand System Guide

How to derive each layer of the brand system from a real project. Use only what fits —
don't force sections that don't apply to this particular product.

## Brand discovery

Work out, from the repo and any user input: what the product does, who it serves, what
problem it solves, what makes it valuable and different, what the user should feel using
it, what tone and visual style fit it, and how mature the product currently looks. Turn
this into a short brand foundation statement before touching color or type — every later
decision should trace back to it.

## Brand values

Pick 3-6 values that genuinely fit *this* project (don't default to a generic list).
For each: name, meaning, and how it should shape design, copywriting, UI, and README
presentation. Good candidates include clarity, trust, speed, intelligence, automation,
simplicity, premium quality, human control, reliability, focus, confidence — but only
use ones the project actually earns.

## Product personality

Define a personality summary, tone of voice, writing style, visual mood, and UI
behavior — what the product should feel like, and what it must avoid. It should never
come across as childish, random, generic, cluttered, cheap, inconsistent,
over-designed, or confusing.

## Visual style system

Define: visual direction, color system, typography direction, spacing/radius/shadow
system, card/button/input style, empty/loading/status states, notification style,
dashboard style, mobile style, icon style, diagram style, screenshot style, README
style, case study style. Every visual decision should support the product story and
user experience — avoid decoration that isn't doing work.

## Color system

Define primary/secondary/background/surface/text/border/status colors, gradient and
glow rules (if relevant), and dark-mode guidance (light-mode too, if relevant). If the
project already has design tokens or CSS variables, align with them rather than
replacing them — only propose a new system if the existing one is clearly incomplete.
Use practical token names: `brand.primary`, `brand.secondary`, `background.default`,
`background.surface`, `text.primary`, `text.secondary`, `border.default`,
`status.success`, `status.warning`, `status.error`.

## Typography system

Primary font recommendation, fallback fonts, heading scale, body/caption/button text
style, dashboard number style, README heading style, and code/documentation typography
guidance. It should read as readable, clean, modern, and premium — and consistent
across every surface.

## UI system

Rules for layouts, sections, cards, buttons, inputs, forms, tables, tabs, navigation,
sidebars, headers, modals, empty/loading/error/success states, badges, KPI cards,
activity feeds, timelines, and dashboard widgets — plus agent/workflow panels if the
project has AI or automation features. Be specific enough that a developer could
actually implement each rule without guessing.

## Dashboard design language (if the project has one)

The dashboard should feel like a focused control center, not a basic admin page. Cover
layout principles, KPI card rules, data hierarchy, table design, status badge rules,
graph/chart style, activity feed style, automation/AI insight panel style (if relevant),
empty state, and responsive behavior.

## Mobile app identity (if the project has mobile/PWA support)

Cover app icon direction, splash screen, PWA icon rules, favicon rules, mobile
navigation, touch spacing, mobile layout principles, mobile loading/empty states, and
onboarding direction. The icon must stay readable at small sizes.

## App icon system

Define main icon, iOS icon, Android adaptive icon, PWA icon, favicon, transparent icon,
monochrome icon, notification icon, splash icon, and GitHub/social avatar. Rules: strong
silhouette, minimal shapes, clear meaning, readable small, no tiny text, no clutter,
consistent with the rest of the identity. If there's no icon yet, write an icon
*direction* document — don't claim a final asset exists.

## AI product branding (if the project has AI, agents, automation, or orchestration)

Define AI personality, visual metaphor, agent naming rules, agent card style, workflow
visualization style, AI status indicators, trust/approval language, human-in-the-loop
language, explainability rules, automation confidence states, and error/fallback tone.
The AI should read as useful and trustworthy — not magical, not fake.

## Animation and motion system

Hover transitions, loading animations, page transitions, status changes, AI activity
indicators, dashboard micro-interactions, mobile interactions. Motion should be subtle,
fast, premium, and performance-safe — avoid excessive movement, cheap animation, random
effects, or slow transitions.

## Reference images (if the user provides a folder)

Inspect them for inspiration only — don't copy directly. Extract mood, layout logic,
color direction, visual hierarchy, dashboard feel, mobile feel, icon feel, premium
quality, motion direction, and storytelling style, then translate that into a
project-specific system rather than reproducing the reference.
