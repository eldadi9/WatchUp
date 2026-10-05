# WatchUp POC Mission

Status 06/10/2026, version `0.3.6`: Yuli runs the program. The active slice is phase 1 in `ROADMAP.md`. This mission text is unchanged.

## Owner-approved mission

⁧להוביל את הקמת ה־POC של WatchUp עבור משפחה אחת וילדה אחת, באמצעות WhatsApp MCP + Bridge במצב קריאה בלבד, עם בידוד מלא ב־VPS, קליטת אירועים בזמן אמת, זיהוי מילים מוגדרות, התראות ודשבורד עברי מובן — בהתאם למסמכי התכנון המאושרים וללא שליחה או שינוי בוואטסאפ.⁩

## Yuli decision

- Complexity: complex
- Maximum parallelism: 1
- Default model class: STANDARD
- Escalation: HIGH only for security-sensitive review or difficult root-cause analysis
- Maximum retries: 3; attempt 3 requires re-plan
- Validation: deterministic checks, then Valdi; one repair and one revalidation per cycle
- Context: scoped worker packets only
- Checkpoints: Andy in the main thread only
- Work-unit budget: 100

## Ori decision — first work package

WP-1 is the read-only safety foundation:

1. Inventory every send, react, typing, edit, delete, upload, or outbound endpoint/tool in `whatsapp-mcp`.
2. Enforce read-only behavior at both the Python MCP layer and Go bridge boundary.
3. Keep read/query/group/contact/media ingestion capabilities working.
4. Add deterministic tests proving outbound actions are unavailable or refused.
5. Do not deploy, pair a WhatsApp account, use real family data, or touch the VPS.

## Stop condition

WP-1 ends only after deterministic tests pass, Valdi validates independently, and Gate records GO or NO-GO. No later POC work starts automatically.
