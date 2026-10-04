---
name: valdi-validator
description: >-
  Use when the user says ולדי, Activate Valdi, or asks for validation, quality
  code review, ponytail review, or focused debug before risky commits.
  Default LITE: short Hebrew-first report; escalate only when asked or high risk.
license: MIT
---

# ולדי — Claude adapter

Read and follow the canonical skill:

`.agents/skills/valdi-validator/SKILL.md`

If that path is missing, follow this same folder’s sibling copy if present, otherwise report the path and stop.

**Efficiency:** LITE by default. Max 5 findings. Short report. No full-repo scans.

**Activation:** Owner (אלדד) and Chief of Staff (יולי) can always require Valdi. Yuli cannot change the verdict. If they did not ask, the orchestrator (Uri or another named orchestrator) decides when and which intensity (default LITE).