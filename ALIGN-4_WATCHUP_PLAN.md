# ALIGN-4 — WatchUp Skills Propagation Plan

## Authorization

Owner GO received on 2026-10-04 for WatchUp only and for the complete copy of the 12 selected Skill packages.

## Scope

- Source of truth: `C:\Users\Master_PC\Desktop\Projects Eldad\EG_SKIILS\Skills_IL`
- Target project: `C:\Users\Master_PC\Desktop\Projects Eldad\01_Active_Projects\WatchUp`
- Canonical target: `<project>\.agents\skills\<skill-name>`
- Copy every file and subdirectory in each selected package.
- Preserve source packages unchanged.
- Do not install Dream Team, modify global configuration, deploy, pair WhatsApp, or start application implementation.

## Selected packages

1. `external-skills/impeccable/codex` → `.agents/skills/impeccable`
2. `external-skills/ponytail/skills/ponytail` → `.agents/skills/ponytail`
3. `external-skills/ponytail/skills/ponytail-review` → `.agents/skills/ponytail-review`
4. `localization/hebrew-rtl-best-practices` → `.agents/skills/hebrew-rtl-best-practices`
5. `localization/israeli-ui-design-system` → `.agents/skills/israeli-ui-design-system`
6. `localization/israeli-accessibility-compliance` → `.agents/skills/israeli-accessibility-compliance`
7. `localization/hebrew-i18n` → `.agents/skills/hebrew-i18n`
8. `EG-SKIILS/codex-rtl-documents` → `.agents/skills/codex-rtl-documents`
9. `security-compliance/israeli-privacy-shield` → `.agents/skills/israeli-privacy-shield`
10. `security-compliance/israeli-appsec-scanner` → `.agents/skills/israeli-appsec-scanner`
11. `developer-tools/israeli-postgres-toolkit` → `.agents/skills/israeli-postgres-toolkit`
12. `EG-SKIILS/product-branding-system-builder` → `.agents/skills/product-branding-system-builder`

## Verification gate

- All 12 target directories exist.
- Every target contains `SKILL.md`.
- Recursive file count matches its source.
- SHA-256 hashes match for every copied file.
- No files outside the plan scope are changed.
