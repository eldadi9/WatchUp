# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Delegated: React/Next.js PWA was approved in `ARCHITECTURE.md`; the first synthetic dashboard should use the smallest implementation that fits the existing backend and can later consume its API.

## Users

- Eldad and his wife are the parent users in the POC.
- One nine-year-old child account is monitored in the POC.
- The parent needs a calm, immediate view of changes and risks without reading every conversation.

## Product Purpose

WatchUp gives parents a clear, live view of significant WhatsApp events: connection health, new contacts and groups, unknown senders, monitored phrases, and items that need attention. POC success means the parents can understand what happened and why it matters, with 95% of processed events visible within 30 seconds.

## Positioning

WatchUp is an exception-first parental safety control center. It summarizes and explains relevant changes while technically preventing all outbound WhatsApp actions.

## Operating Context

- Mobile-first Hebrew dashboard, also usable on desktop.
- One child and two parents in the POC.
- Live status, daily alerts, weekly summaries, monitoring rules, contacts, and groups.
- Synthetic data only for WP-3; real WhatsApp pairing requires separate Owner approval.

## Capabilities and Constraints

- Strictly read-only WhatsApp access; no send, edit, delete, react, or typing actions.
- Four alert levels: information, review, important, and critical.
- Monitoring rules can match a word or phrase, including the POC phrase “אוהבת אותך”.
- Child and family data are highly sensitive and must remain isolated from every other project.
- No multi-family, payments, stores, or WhatsApp Business flow in the POC.

## Brand Commitments

- Product name: WatchUp.
- A green identity with an original prominent eye symbol; do not copy the WhatsApp logo.
- Voice: calm, direct, protective, and non-alarmist.

## Evidence on Hand

- Product requirements: `REQUIREMENTS.md`.
- Approved product scope: `PRD.md`.
- Technical direction: `ARCHITECTURE.md` and `SECURITY_PLAN.md`.
- No final logo, customer proof, production screenshots, or real user data exist yet; do not fabricate them.

## Product Principles

1. Show exceptions before full content.
2. Explain why an event matters in plain language.
3. Reveal only the minimum context needed for a parent decision.
4. Keep connection freshness and data provenance visible.
5. Preserve human control and technical read-only guarantees.

## Accessibility & Inclusion

- Hebrew and correct RTL behavior are required for the MVP.
- The interface must be keyboard operable, mobile-friendly, readable without technical knowledge, and built with semantic structure and clear focus states.
