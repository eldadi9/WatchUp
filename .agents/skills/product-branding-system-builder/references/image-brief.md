# Brand Board Image Brief (Phase 0)

Use this as the base prompt for generating the 11-image premium branding reference
board. Fill in `[PROJECT_NAME]` and `[SHORT_DESCRIPTION]` from repo inspection or user
input before generating — never send the literal placeholders to an image tool.

```
Create a complete premium visual branding image set for a modern AI software product.
The product name is: [PROJECT_NAME]
The product purpose is: [SHORT_DESCRIPTION]
Style: premium, cinematic, modern SaaS, AI-native, clean, elegant, startup-quality, investor-ready.
Avoid: childish design, clutter, random colors, generic templates, cheap gradients, unreadable text.
Create 11 separate images, each one independent, professional, and usable as a reference image for designers and developers.
```

## The 11 images

1. **Brand Book** — logo direction, color palette, typography, visual mood, product personality, brand rules.
2. **UI System** — buttons, cards, inputs, badges, tables, empty states, loading states, design tokens.
3. **Dashboard Design Language** — futuristic but clean command center: KPI cards, charts, activity feed, workflow panels, agent status cards.
4. **Mobile App Identity** — app icon direction, splash screen, mobile screens, navigation, touch-friendly UI.
5. **README Showcase** — cinematic hero section, badges, feature cards, architecture diagram, screenshots, roadmap layout.
6. **Portfolio / Case Study** — product story, problem, solution, process, architecture, results, visuals.
7. **Visual Direction** — mood board: color atmosphere, lighting, gradients, UI examples, icon style, product vibe.
8. **Motion + Premium Feel** — motion direction, micro-interactions, glow, transitions, loading states, cinematic feel.
9. **Product Personality** — tone of voice, values, user feeling, product character, trust, clarity, intelligence, confidence.
10. **GitHub Presentation** — README structure, badges, screenshots, diagrams, setup, roadmap, open-source polish.
11. **AI Product Branding** — agents, workflows, orchestration, automation, AI status indicators, human approval, intelligent system flow.

## General visual rules

Consistent brand language across all 11. Premium dark mode first, with smart contrast.
Clean spacing, strong hierarchy, realistic SaaS visuals. Minimal, large, readable text —
no tiny unreadable text. Each image should look like a professional design reference
board, not a cartoon, and should be suitable for GitHub, README, portfolio, product
branding, and investor presentation. Output each image separately, with one consistent
visual identity across the full set.

## After generating

Save the images under `assets/branding/` numbered to match the list above
(`01-brand-book.png` … `11-ai-product-branding.png`), and treat them as the visual
source of truth for `references/implementation-plan.md` — not as decorative filler.
