# WatchUp WP-3 UI Implementation Plan

## Scope

Build a local Hebrew RTL synthetic dashboard. No API wiring, VPS deployment, WhatsApp pairing, or real family data.

## Files to Create

- `watchup-web/index.html` — semantic application shell and dashboard content.
- `watchup-web/styles.css` — tokens, responsive RTL layout, components, and states.
- `watchup-web/app.js` — local filters, monitored phrase form, review actions, and navigation.
- `watchup-web/tests/test_static_dashboard.py` — deterministic structural and safety checks.

## Execution

1. Define tokens and responsive shell.
2. Build accessible dashboard and event timeline.
3. Add synthetic-only interactions.
4. Run static tests, accessibility audit, and Impeccable detector.
5. Review at mobile and desktop widths.

## Validation

- Hebrew document direction and semantic landmarks.
- Keyboard-operable controls and visible focus.
- No outbound WhatsApp action or real data.
- Responsive layout and clear synthetic-data disclosure.

