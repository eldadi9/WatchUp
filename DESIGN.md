# WatchUp Visual System

## Direction

Calm parental supervision journal: a bright, mobile-first control center that feels protective and clear rather than invasive or technical.

## Identity

- Original eye mark inside a green shield-like field; never copy the WhatsApp logo.
- Deep green is reserved for connection, primary actions, and the WatchUp identity.
- Warm off-white paper and ink-like text keep long monitoring sessions calm.

## Interface Rules

- Hebrew first: `lang="he"`, `dir="rtl"`, logical CSS properties, isolated LTR values.
- Events form the main reading spine; severity is conveyed by label, icon, and color.
- Connection freshness is always visible.
- Content excerpts are minimal and synthetic in WP-3.
- Cards use one depth treatment, 14px radii, strong focus rings, and 44px minimum targets.
- Mobile uses bottom navigation; wide screens use a fixed inline-start rail.

## Voice

Calm, direct, specific, non-alarmist. Say what happened, why it was surfaced, and what the parent can do next.

## Stitch Design Contract

This section is the source of truth for Google Stitch and the local implementation.

### Atmosphere

WatchUp is a calm, warm and immediately understandable parental control center. It should feel like an Apple-quality family product rather than a surveillance console: generous space, one clear action at a time, progressive disclosure and reassuring language. Density 5/10, structural variance 5/10, motion 3/10.

The core screen set is: status dashboard, alert journal, groups and contacts, and event detail. Monitoring settings remain a supporting MVP screen.

### Palette

- Calm Canvas `#F3F6F4` — application background.
- Clean Surface `#FFFFFF` — focused content surfaces.
- Deep Ink `#14201C` — primary text; pure black is banned.
- Quiet Text `#68756F` — supporting copy and metadata.
- Whisper Line `#E5EBE8` — subtle separators.
- WatchUp Green `#08785B` — the single brand accent for primary actions, focus and healthy connection.
- Red, amber and blue are semantic exceptions reserved for event severity, never decoration.

No neon, purple AI glow, gradient text or colored outer glow. Elevation is neutral, soft and directional.

### Typography and RTL

- Hebrew is the source language with document-level `lang="he"` and `dir="rtl"`.
- UI stack: Segoe UI, Arial and an installed Hebrew system fallback; the POC does not depend on a network font.
- Main headings: 28–58px, weight 750–800, tracking no tighter than `-0.04em`.
- Body text: at least 14px on mobile and 16px in primary reading areas, with relaxed 1.6 leading.
- Functional text never drops below 11px.
- LTR numbers and phone values are isolated with `bdi` or `dir="ltr"`.
- Layout uses logical CSS properties only.

### Components

- Buttons have at least a 44px touch target. Primary is solid green; secondary is white with a quiet edge. Press feedback is tactile and restrained.
- Content surfaces use 16–24px radii. Use either an edge or elevation, never a heavy combination of both.
- Lists rely on spacing and dividers instead of nested cards.
- Severity is always communicated by label, icon and color together.
- Forms use labels above inputs, feedback below and `dir="auto"` for free text.
- Loading uses skeletons shaped like the destination; empty states explain what will appear and how.

### Layout

- Desktop uses a fixed logical-start navigation rail and a contained workspace up to 1400px.
- Mobile collapses to one column with a four-item bottom navigation. Horizontal scrolling is a critical failure.
- The supplied child illustration anchors the dashboard hero beside one plain-language status sentence and an explicit read-only connection indicator.
- Alerts lead with priority. Event detail explains what was detected, why it surfaced and what the parent can do.
- Groups and contacts use clear tabs and show changes before activity totals.

### Motion

Use a single quiet 180–220ms screen transition, tactile press feedback and an accessible status toast. Animate transform and opacity only, respect `prefers-reduced-motion`, and avoid decorative loops.

### Safety and Content Rules

- Keep the voice calm, direct and non-alarmist.
- Explain what happened, why it matters and the available next step.
- Label synthetic data explicitly.
- Never invent safety scores or capabilities.
- Never expose send, react, block, delete, leave-group or WhatsApp-setting actions.
- Show the minimum context needed to understand an event, not a full conversation.

### Banned Patterns

No pure black, neon, gradient text, emoji as an icon system, generic three-card feature rows, filler copy, generic names, horizontal overflow, overlapping content or controls that imply changing WhatsApp. The owner-supplied green eye mark is the product identity; do not copy the WhatsApp logo.

