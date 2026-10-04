# Installation Readiness

**Overall:** READY WITH WARNINGS
**Schema:** 1.0
**Generated:** 2026-10-03T23:51:00.997199Z

> Installed is not discovered/active: files on disk do not prove the host loaded them.

## Lifecycle counts

| Stage | Agents | Skills | Source version |
|---|---:|---:|---|
| Requested | 0 | 3 | new-project-tool |
| Resolved | 10 | 1 | new-project-tool |
| Installed | 10 | 1 | new-project-tool |
| Verified | 10 | 2 | new-project-tool |

## Resolved component provenance

| Canonical ID | Type | Source | Version |
|---|---|---|---|
| bundle.full-dream-team | bundle | canonical-generated | unversioned |
| configuration.dream-team-project | configuration | canonical-generated | unversioned |
| continuity.andy | continuity | canonical-generated | unversioned |
| role.ori | orchestrator | canonical-generated | unversioned |
| role.valdi | validator | canonical-generated | unversioned |
| role.yuli | chief-of-staff | canonical-generated | unversioned |
| template.dream-team-runtime | template | canonical-generated | unversioned |
| worker.amy | worker | canonical-generated | unversioned |
| worker.dani | worker | canonical-generated | unversioned |
| worker.gonesh | worker | canonical-generated | unversioned |
| worker.mark | worker | canonical-generated | unversioned |
| worker.mori | worker | canonical-generated | unversioned |
| worker.peri | worker | canonical-generated | unversioned |
| worker.saker | worker | canonical-generated | unversioned |
| worker.sefi | worker | canonical-generated | unversioned |
| worker.teddy | worker | canonical-generated | unversioned |

## Bundle and de-duplication decisions

- `deduplicated`: {"decision": "deduplicated", "detail": "andy -> continuity.andy (provided by Full Dream Team)"}
- `deduplicated`: {"decision": "deduplicated", "detail": "valdi-validator -> role.valdi (provided by Full Dream Team)"}
- `deduplicated`: {"decision": "deduplicated", "detail": "yuli-ceo -> role.yuli (provided by Full Dream Team)"}
- `expanded-bundle`: {"component_id": "bundle.full-dream-team", "decision": "expanded-bundle", "resolved_components": ["bundle.full-dream-team", "configuration.dream-team-project", "continuity.andy", "role.ori", "role.valdi", "role.yuli", "template.dream-team-runtime", "worker.amy", "worker.dani", "worker.gonesh", "worker.mark", "worker.mori", "worker.peri", "worker.saker", "worker.sefi", "worker.teddy"]}

## Installation stages

| Stage | Agents | Skills |
|---|---:|---:|
| Bootstrap installed | 0 | 0 |
| HTML Manager additions | 10 | 1 |
| Final verified installed state | 10 | 14 |
- Pre-existing or externally installed components are counted only in the final verified state: skill:role.ori, skill:skill.codex-rtl-documents, skill:skill.hebrew-i18n, skill:skill.hebrew-rtl-best-practices, skill:skill.impeccable, skill:skill.israeli-accessibility-compliance, skill:skill.israeli-appsec-scanner, skill:skill.israeli-postgres-toolkit, skill:skill.israeli-privacy-shield, skill:skill.israeli-ui-design-system, skill:skill.ponytail, skill:skill.ponytail-review, skill:skill.product-branding-system-builder

## Blockers

- None.

## Warnings

- DOCS.IDEA: Install or restore idea at docs/IDEA.md.

## Checks

| ID | Component | Severity | Result | Evidence | Remediation |
|---|---|---|---|---|---|
| AGENT.CLAUDE.AMY | worker.amy | BLOCKER | PASS | `{"exists": true, "kind": "agent", "path": ".claude/agents/dt-amy-integrations.md", "provider": "claude"}` | None. |
| VERSION.CLAUDE.AGENT-AMY | version-agent-amy | WARNING | PASS | `{"exists": true, "expected_sha256": "1b592f32f3ac592159841f7b321180d75c0ebe3485b59b1ddfed4706469098f6", "kind": "file", "path": ".claude/agents/dt-amy-integrations.md", "provider": "claude", "sha256": "1b592f32f3ac592159841f7b321180d75c0ebe3485b59b1ddfed4706469098f6"}` | None. |
| AGENT.CLAUDE.DANI | worker.dani | BLOCKER | PASS | `{"exists": true, "kind": "agent", "path": ".claude/agents/dt-dani-data-ai.md", "provider": "claude"}` | None. |
| VERSION.CLAUDE.AGENT-DANI | version-agent-dani | WARNING | PASS | `{"exists": true, "expected_sha256": "ea0eb094ade3f8cd526ddcc3a2b96c05d6064ee8dcf5dd04ce05672566809dcd", "kind": "file", "path": ".claude/agents/dt-dani-data-ai.md", "provider": "claude", "sha256": "ea0eb094ade3f8cd526ddcc3a2b96c05d6064ee8dcf5dd04ce05672566809dcd"}` | None. |
| AGENT.CLAUDE.GONESH | worker.gonesh | BLOCKER | PASS | `{"exists": true, "kind": "agent", "path": ".claude/agents/dt-gonesh-exec.md", "provider": "claude"}` | None. |
| VERSION.CLAUDE.AGENT-GONESH | version-agent-gonesh | WARNING | PASS | `{"exists": true, "expected_sha256": "32917d3667754aaa2af7ee3f5a9c8e3739d45219897d23d85445c4745333a115", "kind": "file", "path": ".claude/agents/dt-gonesh-exec.md", "provider": "claude", "sha256": "32917d3667754aaa2af7ee3f5a9c8e3739d45219897d23d85445c4745333a115"}` | None. |
| AGENT.CLAUDE.MARK | worker.mark | BLOCKER | PASS | `{"exists": true, "kind": "agent", "path": ".claude/agents/dt-mark-growth.md", "provider": "claude"}` | None. |
| VERSION.CLAUDE.AGENT-MARK | version-agent-mark | WARNING | PASS | `{"exists": true, "expected_sha256": "a819925f7e4d7b969eaa73d6e281af8aab2f0c4bf82872f825a036f262a310db", "kind": "file", "path": ".claude/agents/dt-mark-growth.md", "provider": "claude", "sha256": "a819925f7e4d7b969eaa73d6e281af8aab2f0c4bf82872f825a036f262a310db"}` | None. |
| AGENT.CLAUDE.MORI | worker.mori | BLOCKER | PASS | `{"exists": true, "kind": "agent", "path": ".claude/agents/dt-mori-ux-ui.md", "provider": "claude"}` | None. |
| VERSION.CLAUDE.AGENT-MORI | version-agent-mori | WARNING | PASS | `{"exists": true, "expected_sha256": "f5a7837b7143943d59698dd8ef4ab62f97e3af9d2f941bd269224634d7f18a49", "kind": "file", "path": ".claude/agents/dt-mori-ux-ui.md", "provider": "claude", "sha256": "f5a7837b7143943d59698dd8ef4ab62f97e3af9d2f941bd269224634d7f18a49"}` | None. |
| AGENT.CLAUDE.PERI | worker.peri | BLOCKER | PASS | `{"exists": true, "kind": "agent", "path": ".claude/agents/dt-peri-product.md", "provider": "claude"}` | None. |
| VERSION.CLAUDE.AGENT-PERI | version-agent-peri | WARNING | PASS | `{"exists": true, "expected_sha256": "b11f49ac3cc9569ad6e36ff9eabcea2c6260941986d074c9e65a7cd977567d2b", "kind": "file", "path": ".claude/agents/dt-peri-product.md", "provider": "claude", "sha256": "b11f49ac3cc9569ad6e36ff9eabcea2c6260941986d074c9e65a7cd977567d2b"}` | None. |
| AGENT.CLAUDE.SAKER | worker.saker | BLOCKER | PASS | `{"exists": true, "kind": "agent", "path": ".claude/agents/dt-saker-research.md", "provider": "claude"}` | None. |
| VERSION.CLAUDE.AGENT-SAKER | version-agent-saker | WARNING | PASS | `{"exists": true, "expected_sha256": "6c7441bdc7b674f80bf1858f1e7f9eff31b189e3353dd2e6a12edf8384ac568d", "kind": "file", "path": ".claude/agents/dt-saker-research.md", "provider": "claude", "sha256": "6c7441bdc7b674f80bf1858f1e7f9eff31b189e3353dd2e6a12edf8384ac568d"}` | None. |
| AGENT.CLAUDE.SEFI | worker.sefi | BLOCKER | PASS | `{"exists": true, "kind": "agent", "path": ".claude/agents/dt-sefi-devops-security.md", "provider": "claude"}` | None. |
| VERSION.CLAUDE.AGENT-SEFI | version-agent-sefi | WARNING | PASS | `{"exists": true, "expected_sha256": "c523b48297d1fc01ff48d3f9d3168f6975ef0c8ad789d97a5eab4b4e2949910b", "kind": "file", "path": ".claude/agents/dt-sefi-devops-security.md", "provider": "claude", "sha256": "c523b48297d1fc01ff48d3f9d3168f6975ef0c8ad789d97a5eab4b4e2949910b"}` | None. |
| AGENT.CLAUDE.TEDDY | worker.teddy | BLOCKER | PASS | `{"exists": true, "kind": "agent", "path": ".claude/agents/dt-teddy-leaddev.md", "provider": "claude"}` | None. |
| VERSION.CLAUDE.AGENT-TEDDY | version-agent-teddy | WARNING | PASS | `{"exists": true, "expected_sha256": "b25a5a65bd7b410244880965551e1cecc27a0b659e3982a61c27ce2bf61450c1", "kind": "file", "path": ".claude/agents/dt-teddy-leaddev.md", "provider": "claude", "sha256": "b25a5a65bd7b410244880965551e1cecc27a0b659e3982a61c27ce2bf61450c1"}` | None. |
| AGENT.CLAUDE.VALDI | role.valdi | BLOCKER | PASS | `{"exists": true, "kind": "agent", "path": ".claude/agents/dt-valdi-validate.md", "provider": "claude"}` | None. |
| VERSION.CLAUDE.AGENT-VALDI | version-agent-valdi | WARNING | PASS | `{"exists": true, "expected_sha256": "41648f571804f5171f3e16b16448d2b3f41a397fa83f493d414efcee42e8b7e4", "kind": "file", "path": ".claude/agents/dt-valdi-validate.md", "provider": "claude", "sha256": "41648f571804f5171f3e16b16448d2b3f41a397fa83f493d414efcee42e8b7e4"}` | None. |
| GOVERNANCE-HOOK.CLAUDE.DREAM-TEAM-AGENT-GOVERNOR | rule-dream-team-agent-governor | BLOCKER | PASS | `{"exists": true, "kind": "file", "path": ".claude/hooks/dream-team-agent-governor.py", "provider": "claude"}` | None. |
| VERSION.CLAUDE.GOVERNANCE-HOOK-DREAM-TEAM-AGENT-GOVERNOR | version-governance-hook-dream-team-agent-governor | WARNING | PASS | `{"exists": true, "expected_sha256": "da83ab50d33e79d202cb25c83aa336a9606c5d51743498307904de0ee9f8d33c", "kind": "file", "path": ".claude/hooks/dream-team-agent-governor.py", "provider": "claude", "sha256": "da83ab50d33e79d202cb25c83aa336a9606c5d51743498307904de0ee9f8d33c"}` | None. |
| GOVERNANCE-HOOK.CLAUDE.DREAM-TEAM-GOVERNOR-POLICY | rule-dream-team-governor-policy | BLOCKER | PASS | `{"exists": true, "kind": "file", "path": ".claude/hooks/dream-team-governor-policy.json", "provider": "claude"}` | None. |
| VERSION.CLAUDE.GOVERNANCE-HOOK-DREAM-TEAM-GOVERNOR-POLICY | version-governance-hook-dream-team-governor-policy | WARNING | PASS | `{"exists": true, "expected_sha256": "162e0018c14c3860a541c2417a850184985e70a8bd19e45bc8f59fd010d133f4", "kind": "file", "path": ".claude/hooks/dream-team-governor-policy.json", "provider": "claude", "sha256": "162e0018c14c3860a541c2417a850184985e70a8bd19e45bc8f59fd010d133f4"}` | None. |
| AGENT.CODEX.AMY | worker.amy | BLOCKER | PASS | `{"exists": true, "kind": "agent", "path": ".codex/agents/amy.toml", "provider": "codex"}` | None. |
| VERSION.CODEX.AGENT-AMY | version-agent-amy | WARNING | PASS | `{"exists": true, "expected_sha256": "b54d4bccdc8d3321742f95416841b768b7b5e33fc2f9575933c52f38511775be", "kind": "file", "path": ".codex/agents/amy.toml", "provider": "codex", "sha256": "b54d4bccdc8d3321742f95416841b768b7b5e33fc2f9575933c52f38511775be"}` | None. |
| AGENT.CODEX.DANI | worker.dani | BLOCKER | PASS | `{"exists": true, "kind": "agent", "path": ".codex/agents/dani.toml", "provider": "codex"}` | None. |
| VERSION.CODEX.AGENT-DANI | version-agent-dani | WARNING | PASS | `{"exists": true, "expected_sha256": "321d0e380f9eabb1ec82a230c32897d931780f8ade5d5c2abf76a30e028842cd", "kind": "file", "path": ".codex/agents/dani.toml", "provider": "codex", "sha256": "321d0e380f9eabb1ec82a230c32897d931780f8ade5d5c2abf76a30e028842cd"}` | None. |
| AGENT.CODEX.GONESH | worker.gonesh | BLOCKER | PASS | `{"exists": true, "kind": "agent", "path": ".codex/agents/gonesh.toml", "provider": "codex"}` | None. |
| VERSION.CODEX.AGENT-GONESH | version-agent-gonesh | WARNING | PASS | `{"exists": true, "expected_sha256": "ce3bf8d888530f26abd97bbf78a1c1ca3dd1e21f17d9db723db26030e488c693", "kind": "file", "path": ".codex/agents/gonesh.toml", "provider": "codex", "sha256": "ce3bf8d888530f26abd97bbf78a1c1ca3dd1e21f17d9db723db26030e488c693"}` | None. |
| AGENT.CODEX.MARK | worker.mark | BLOCKER | PASS | `{"exists": true, "kind": "agent", "path": ".codex/agents/mark.toml", "provider": "codex"}` | None. |
| VERSION.CODEX.AGENT-MARK | version-agent-mark | WARNING | PASS | `{"exists": true, "expected_sha256": "0999ec3c2d2ca24152886ddbea22c4b397061d570aa3a120710ba5fd07b48ec5", "kind": "file", "path": ".codex/agents/mark.toml", "provider": "codex", "sha256": "0999ec3c2d2ca24152886ddbea22c4b397061d570aa3a120710ba5fd07b48ec5"}` | None. |
| AGENT.CODEX.MORI | worker.mori | BLOCKER | PASS | `{"exists": true, "kind": "agent", "path": ".codex/agents/mori.toml", "provider": "codex"}` | None. |
| VERSION.CODEX.AGENT-MORI | version-agent-mori | WARNING | PASS | `{"exists": true, "expected_sha256": "667fcb3c87cda072c54e21431cd6080aa8a1acf61048d7bc71419c5084a78dd3", "kind": "file", "path": ".codex/agents/mori.toml", "provider": "codex", "sha256": "667fcb3c87cda072c54e21431cd6080aa8a1acf61048d7bc71419c5084a78dd3"}` | None. |
| AGENT.CODEX.PERI | worker.peri | BLOCKER | PASS | `{"exists": true, "kind": "agent", "path": ".codex/agents/peri.toml", "provider": "codex"}` | None. |
| VERSION.CODEX.AGENT-PERI | version-agent-peri | WARNING | PASS | `{"exists": true, "expected_sha256": "071c5e8118aab9fe88f537f63ec2ff34e2fe45e5c7e9c70c9dffac00609b52ea", "kind": "file", "path": ".codex/agents/peri.toml", "provider": "codex", "sha256": "071c5e8118aab9fe88f537f63ec2ff34e2fe45e5c7e9c70c9dffac00609b52ea"}` | None. |
| AGENT.CODEX.SAKER | worker.saker | BLOCKER | PASS | `{"exists": true, "kind": "agent", "path": ".codex/agents/saker.toml", "provider": "codex"}` | None. |
| VERSION.CODEX.AGENT-SAKER | version-agent-saker | WARNING | PASS | `{"exists": true, "expected_sha256": "ac3cb0d6ce8ff556fd0e8aac9e6c3643a1168091e26bd87b19922ef88e03f872", "kind": "file", "path": ".codex/agents/saker.toml", "provider": "codex", "sha256": "ac3cb0d6ce8ff556fd0e8aac9e6c3643a1168091e26bd87b19922ef88e03f872"}` | None. |
| AGENT.CODEX.SEFI | worker.sefi | BLOCKER | PASS | `{"exists": true, "kind": "agent", "path": ".codex/agents/sefi.toml", "provider": "codex"}` | None. |
| VERSION.CODEX.AGENT-SEFI | version-agent-sefi | WARNING | PASS | `{"exists": true, "expected_sha256": "a4782d9297b3c0b53d4d72f4d21799f834f3a3fa13d733abdddb1cf7eaf48f8e", "kind": "file", "path": ".codex/agents/sefi.toml", "provider": "codex", "sha256": "a4782d9297b3c0b53d4d72f4d21799f834f3a3fa13d733abdddb1cf7eaf48f8e"}` | None. |
| AGENT.CODEX.TEDDY | worker.teddy | BLOCKER | PASS | `{"exists": true, "kind": "agent", "path": ".codex/agents/teddy.toml", "provider": "codex"}` | None. |
| VERSION.CODEX.AGENT-TEDDY | version-agent-teddy | WARNING | PASS | `{"exists": true, "expected_sha256": "2ecd0a7732e39569800064b561041e7d801fdf44fef3937f3ba650d77ea5977e", "kind": "file", "path": ".codex/agents/teddy.toml", "provider": "codex", "sha256": "2ecd0a7732e39569800064b561041e7d801fdf44fef3937f3ba650d77ea5977e"}` | None. |
| AGENT.CODEX.VALDI | role.valdi | BLOCKER | PASS | `{"exists": true, "kind": "agent", "path": ".codex/agents/valdi.toml", "provider": "codex"}` | None. |
| VERSION.CODEX.AGENT-VALDI | version-agent-valdi | WARNING | PASS | `{"exists": true, "expected_sha256": "f9d6617cbc185e0f440b7ee65b71f6e3c8149f9c58a23532e64d3a2c48bf190d", "kind": "file", "path": ".codex/agents/valdi.toml", "provider": "codex", "sha256": "f9d6617cbc185e0f440b7ee65b71f6e3c8149f9c58a23532e64d3a2c48bf190d"}` | None. |
| GOVERNANCE-CONFIG.CODEX.CONFIG | rule-config | BLOCKER | PASS | `{"exists": true, "kind": "file", "path": ".codex/config.toml", "provider": "codex"}` | None. |
| VERSION.CODEX.GOVERNANCE-CONFIG-CONFIG | version-governance-config-config | WARNING | PASS | `{"exists": true, "expected_sha256": "427be3a91e3c2b3b3381a1110e1413c2c7b6837669a07a7c536765bc990a81f7", "kind": "file", "path": ".codex/config.toml", "provider": "codex", "sha256": "427be3a91e3c2b3b3381a1110e1413c2c7b6837669a07a7c536765bc990a81f7"}` | None. |
| AGENT.CURSOR.AMY | worker.amy | BLOCKER | PASS | `{"exists": true, "kind": "agent", "path": ".cursor/agents/amy.md", "provider": "cursor"}` | None. |
| VERSION.CURSOR.AGENT-AMY | version-agent-amy | WARNING | PASS | `{"exists": true, "expected_sha256": "8cd101996cf849d1d0a8f6972e65034ed82078e1c0559715000751d6c6bc7312", "kind": "file", "path": ".cursor/agents/amy.md", "provider": "cursor", "sha256": "8cd101996cf849d1d0a8f6972e65034ed82078e1c0559715000751d6c6bc7312"}` | None. |
| AGENT.CURSOR.DANI | worker.dani | BLOCKER | PASS | `{"exists": true, "kind": "agent", "path": ".cursor/agents/dani.md", "provider": "cursor"}` | None. |
| VERSION.CURSOR.AGENT-DANI | version-agent-dani | WARNING | PASS | `{"exists": true, "expected_sha256": "61847ceb993d26f21b92b902fa921f0a118520b45ffcb8d6c1d0d7616cd94aa5", "kind": "file", "path": ".cursor/agents/dani.md", "provider": "cursor", "sha256": "61847ceb993d26f21b92b902fa921f0a118520b45ffcb8d6c1d0d7616cd94aa5"}` | None. |
| AGENT.CURSOR.GONESH | worker.gonesh | BLOCKER | PASS | `{"exists": true, "kind": "agent", "path": ".cursor/agents/gonesh.md", "provider": "cursor"}` | None. |
| VERSION.CURSOR.AGENT-GONESH | version-agent-gonesh | WARNING | PASS | `{"exists": true, "expected_sha256": "d2c547f9c628dfdf7028c6e32c059240da5f841b08443a86765959f6f95346a8", "kind": "file", "path": ".cursor/agents/gonesh.md", "provider": "cursor", "sha256": "d2c547f9c628dfdf7028c6e32c059240da5f841b08443a86765959f6f95346a8"}` | None. |
| AGENT.CURSOR.MARK | worker.mark | BLOCKER | PASS | `{"exists": true, "kind": "agent", "path": ".cursor/agents/mark.md", "provider": "cursor"}` | None. |
| VERSION.CURSOR.AGENT-MARK | version-agent-mark | WARNING | PASS | `{"exists": true, "expected_sha256": "0bb5053267e274824731164b0e08adeb1fc717cc3cfda9547fb0593ec15f75ad", "kind": "file", "path": ".cursor/agents/mark.md", "provider": "cursor", "sha256": "0bb5053267e274824731164b0e08adeb1fc717cc3cfda9547fb0593ec15f75ad"}` | None. |
| AGENT.CURSOR.MORI | worker.mori | BLOCKER | PASS | `{"exists": true, "kind": "agent", "path": ".cursor/agents/mori.md", "provider": "cursor"}` | None. |
| VERSION.CURSOR.AGENT-MORI | version-agent-mori | WARNING | PASS | `{"exists": true, "expected_sha256": "657529e2f961d869714a834964444d0f5fb3c9f49f0f60f534cc53f564fb269c", "kind": "file", "path": ".cursor/agents/mori.md", "provider": "cursor", "sha256": "657529e2f961d869714a834964444d0f5fb3c9f49f0f60f534cc53f564fb269c"}` | None. |
| AGENT.CURSOR.PERI | worker.peri | BLOCKER | PASS | `{"exists": true, "kind": "agent", "path": ".cursor/agents/peri.md", "provider": "cursor"}` | None. |
| VERSION.CURSOR.AGENT-PERI | version-agent-peri | WARNING | PASS | `{"exists": true, "expected_sha256": "b4a7e11f68ceee3b79ce2075e941ea9ddbbd9693c6e7459c34252b82c494b241", "kind": "file", "path": ".cursor/agents/peri.md", "provider": "cursor", "sha256": "b4a7e11f68ceee3b79ce2075e941ea9ddbbd9693c6e7459c34252b82c494b241"}` | None. |
| AGENT.CURSOR.SAKER | worker.saker | BLOCKER | PASS | `{"exists": true, "kind": "agent", "path": ".cursor/agents/saker.md", "provider": "cursor"}` | None. |
| VERSION.CURSOR.AGENT-SAKER | version-agent-saker | WARNING | PASS | `{"exists": true, "expected_sha256": "6f197457d9c8c546c13e17333c417ae40426c11945771d342889b2989528aace", "kind": "file", "path": ".cursor/agents/saker.md", "provider": "cursor", "sha256": "6f197457d9c8c546c13e17333c417ae40426c11945771d342889b2989528aace"}` | None. |
| AGENT.CURSOR.SEFI | worker.sefi | BLOCKER | PASS | `{"exists": true, "kind": "agent", "path": ".cursor/agents/sefi.md", "provider": "cursor"}` | None. |
| VERSION.CURSOR.AGENT-SEFI | version-agent-sefi | WARNING | PASS | `{"exists": true, "expected_sha256": "e4ced518342c925266d7a7a1de034a80a0b900fa36ccef00ffc4f0eaa292e839", "kind": "file", "path": ".cursor/agents/sefi.md", "provider": "cursor", "sha256": "e4ced518342c925266d7a7a1de034a80a0b900fa36ccef00ffc4f0eaa292e839"}` | None. |
| AGENT.CURSOR.TEDDY | worker.teddy | BLOCKER | PASS | `{"exists": true, "kind": "agent", "path": ".cursor/agents/teddy.md", "provider": "cursor"}` | None. |
| VERSION.CURSOR.AGENT-TEDDY | version-agent-teddy | WARNING | PASS | `{"exists": true, "expected_sha256": "d934ea2433a5df6d354e4da4a14a8ff4e7c66f369633c0988db14957440fff38", "kind": "file", "path": ".cursor/agents/teddy.md", "provider": "cursor", "sha256": "d934ea2433a5df6d354e4da4a14a8ff4e7c66f369633c0988db14957440fff38"}` | None. |
| AGENT.CURSOR.VALDI | role.valdi | BLOCKER | PASS | `{"exists": true, "kind": "agent", "path": ".cursor/agents/valdi.md", "provider": "cursor"}` | None. |
| VERSION.CURSOR.AGENT-VALDI | version-agent-valdi | WARNING | PASS | `{"exists": true, "expected_sha256": "781fc0fa30291bcbd82bb5346e394e2f2ae4d9e7904b5cdeb11024370dc3a830", "kind": "file", "path": ".cursor/agents/valdi.md", "provider": "cursor", "sha256": "781fc0fa30291bcbd82bb5346e394e2f2ae4d9e7904b5cdeb11024370dc3a830"}` | None. |
| RULE.CURSOR.AMY | rule-amy | BLOCKER | PASS | `{"exists": true, "kind": "file", "path": ".cursor/rules/amy.mdc", "provider": "cursor"}` | None. |
| VERSION.CURSOR.RULE-AMY | version-rule-amy | WARNING | PASS | `{"exists": true, "expected_sha256": "0e83f5d10117ef5fefb92c8c54ed521381adfbe352f3aa39be3d81faeebc28f0", "kind": "file", "path": ".cursor/rules/amy.mdc", "provider": "cursor", "sha256": "0e83f5d10117ef5fefb92c8c54ed521381adfbe352f3aa39be3d81faeebc28f0"}` | None. |
| RULE.CURSOR.DANI | rule-dani | BLOCKER | PASS | `{"exists": true, "kind": "file", "path": ".cursor/rules/dani.mdc", "provider": "cursor"}` | None. |
| VERSION.CURSOR.RULE-DANI | version-rule-dani | WARNING | PASS | `{"exists": true, "expected_sha256": "e06d1d544cbc09ee1e0e32c3ff0fd4b4cb4b4a6a633e5eeb63f6ec6fd8b0cf12", "kind": "file", "path": ".cursor/rules/dani.mdc", "provider": "cursor", "sha256": "e06d1d544cbc09ee1e0e32c3ff0fd4b4cb4b4a6a633e5eeb63f6ec6fd8b0cf12"}` | None. |
| RULE.CURSOR.GONESH | rule-gonesh | BLOCKER | PASS | `{"exists": true, "kind": "file", "path": ".cursor/rules/gonesh.mdc", "provider": "cursor"}` | None. |
| VERSION.CURSOR.RULE-GONESH | version-rule-gonesh | WARNING | PASS | `{"exists": true, "expected_sha256": "599b8df3adbd2498c8ba16b3e872caecadc83788eff03242db5ca5b60b24392a", "kind": "file", "path": ".cursor/rules/gonesh.mdc", "provider": "cursor", "sha256": "599b8df3adbd2498c8ba16b3e872caecadc83788eff03242db5ca5b60b24392a"}` | None. |
| RULE.CURSOR.MARK | rule-mark | BLOCKER | PASS | `{"exists": true, "kind": "file", "path": ".cursor/rules/mark.mdc", "provider": "cursor"}` | None. |
| VERSION.CURSOR.RULE-MARK | version-rule-mark | WARNING | PASS | `{"exists": true, "expected_sha256": "b872a051e08a8f5f572171e73e9bb9f90fa5905921e6942cde6a96e2985b8ad2", "kind": "file", "path": ".cursor/rules/mark.mdc", "provider": "cursor", "sha256": "b872a051e08a8f5f572171e73e9bb9f90fa5905921e6942cde6a96e2985b8ad2"}` | None. |
| RULE.CURSOR.MORI | rule-mori | BLOCKER | PASS | `{"exists": true, "kind": "file", "path": ".cursor/rules/mori.mdc", "provider": "cursor"}` | None. |
| VERSION.CURSOR.RULE-MORI | version-rule-mori | WARNING | PASS | `{"exists": true, "expected_sha256": "5c8779f468308aceaa9e27067b1ab3ad9a7480addaf01f452e14a67213ae047a", "kind": "file", "path": ".cursor/rules/mori.mdc", "provider": "cursor", "sha256": "5c8779f468308aceaa9e27067b1ab3ad9a7480addaf01f452e14a67213ae047a"}` | None. |
| RULE.CURSOR.ORI | rule-ori | BLOCKER | PASS | `{"exists": true, "kind": "file", "path": ".cursor/rules/ori.mdc", "provider": "cursor"}` | None. |
| VERSION.CURSOR.RULE-ORI | version-rule-ori | WARNING | PASS | `{"exists": true, "expected_sha256": "c4e50e64d70cfbdc862dd0fe0d648ddfe220f1a190c4f6e0e8f6baf33c3a8afb", "kind": "file", "path": ".cursor/rules/ori.mdc", "provider": "cursor", "sha256": "c4e50e64d70cfbdc862dd0fe0d648ddfe220f1a190c4f6e0e8f6baf33c3a8afb"}` | None. |
| RULE.CURSOR.PERI | rule-peri | BLOCKER | PASS | `{"exists": true, "kind": "file", "path": ".cursor/rules/peri.mdc", "provider": "cursor"}` | None. |
| VERSION.CURSOR.RULE-PERI | version-rule-peri | WARNING | PASS | `{"exists": true, "expected_sha256": "45bd2c5f748efb3acb568f7744c5c6967378091995789ffbfc2c3155793a75aa", "kind": "file", "path": ".cursor/rules/peri.mdc", "provider": "cursor", "sha256": "45bd2c5f748efb3acb568f7744c5c6967378091995789ffbfc2c3155793a75aa"}` | None. |
| RULE.CURSOR.SAKER | rule-saker | BLOCKER | PASS | `{"exists": true, "kind": "file", "path": ".cursor/rules/saker.mdc", "provider": "cursor"}` | None. |
| VERSION.CURSOR.RULE-SAKER | version-rule-saker | WARNING | PASS | `{"exists": true, "expected_sha256": "0323da08411413b40b481b0a0ba273eccb5b9ea4a94aaba2d9d1e748ab576591", "kind": "file", "path": ".cursor/rules/saker.mdc", "provider": "cursor", "sha256": "0323da08411413b40b481b0a0ba273eccb5b9ea4a94aaba2d9d1e748ab576591"}` | None. |
| RULE.CURSOR.SEFI | rule-sefi | BLOCKER | PASS | `{"exists": true, "kind": "file", "path": ".cursor/rules/sefi.mdc", "provider": "cursor"}` | None. |
| VERSION.CURSOR.RULE-SEFI | version-rule-sefi | WARNING | PASS | `{"exists": true, "expected_sha256": "e40ae0c1268a30ec479e613ff35976ca048e60dac8aeff58cde751621c883d84", "kind": "file", "path": ".cursor/rules/sefi.mdc", "provider": "cursor", "sha256": "e40ae0c1268a30ec479e613ff35976ca048e60dac8aeff58cde751621c883d84"}` | None. |
| RULE.CURSOR.TEDDY | rule-teddy | BLOCKER | PASS | `{"exists": true, "kind": "file", "path": ".cursor/rules/teddy.mdc", "provider": "cursor"}` | None. |
| VERSION.CURSOR.RULE-TEDDY | version-rule-teddy | WARNING | PASS | `{"exists": true, "expected_sha256": "36b21c7a1cac5ed875b1ca7c0a345919501dabc3c6183868149b84f4f4da5f0b", "kind": "file", "path": ".cursor/rules/teddy.mdc", "provider": "cursor", "sha256": "36b21c7a1cac5ed875b1ca7c0a345919501dabc3c6183868149b84f4f4da5f0b"}` | None. |
| RULE.CURSOR.VALDI | rule-valdi | BLOCKER | PASS | `{"exists": true, "kind": "file", "path": ".cursor/rules/valdi.mdc", "provider": "cursor"}` | None. |
| VERSION.CURSOR.RULE-VALDI | version-rule-valdi | WARNING | PASS | `{"exists": true, "expected_sha256": "43668c74f73bfc751d505a8952f11a5f6a0a637091093d2510499dbb976d8870", "kind": "file", "path": ".cursor/rules/valdi.mdc", "provider": "cursor", "sha256": "43668c74f73bfc751d505a8952f11a5f6a0a637091093d2510499dbb976d8870"}` | None. |
| RULE.CURSOR.YULI | rule-yuli | BLOCKER | PASS | `{"exists": true, "kind": "file", "path": ".cursor/rules/yuli.mdc", "provider": "cursor"}` | None. |
| VERSION.CURSOR.RULE-YULI | version-rule-yuli | WARNING | PASS | `{"exists": true, "expected_sha256": "964941b7e50540b1dc6bcbe4a473454c5e1d5d23062213eaf506138b75872aca", "kind": "file", "path": ".cursor/rules/yuli.mdc", "provider": "cursor", "sha256": "964941b7e50540b1dc6bcbe4a473454c5e1d5d23062213eaf506138b75872aca"}` | None. |
| DOCS.PRD | prd | WARNING | PASS | `{"exists": true, "kind": "file", "path": "PRD.md"}` | None. |
| DOCS.IDEA | idea | WARNING | WARN | `{"exists": false, "kind": "file", "path": "docs/IDEA.md"}` | Install or restore idea at docs/IDEA.md. |
| TARGET.AGENTS | target-agents | WARNING | PASS | `{"exists": true, "kind": "file", "path": "AGENTS.md"}` | None. |
| TARGET.CLAUDE | target-claude | WARNING | PASS | `{"exists": true, "kind": "file", "path": "CLAUDE.md"}` | None. |
| IDENTITY.PROJECT | project-identity | BLOCKER | PASS | `{"exists": true, "kind": "file", "path": ".dream-team/project.json"}` | None. |
| ORCHESTRATOR.CLAUDE | role.ori | BLOCKER | PASS | `{"exists": true, "kind": "skill", "path": ".claude/skills/watchup-orchestrator/SKILL.md", "provider": "claude"}` | None. |
| ANDY.CORE | continuity.andy | BLOCKER | PASS | `{"exists": true, "kind": "skill", "path": ".agents/skills/andy/SKILL.md", "provider": "shared"}` | None. |
| ANDY.STATE | andy-state | BLOCKER | PASS | `{"exists": true, "kind": "file", "path": ".ai/andy/current.json"}` | None. |
| ANDY.CLAUDE | continuity.andy | BLOCKER | PASS | `{"exists": true, "kind": "skill", "path": ".claude/skills/andy/SKILL.md", "provider": "claude"}` | None. |
| DOCS.CLAUDE.PLACEHOLDERS | target-claude | BLOCKER | PASS | `{"count": 0, "path": "CLAUDE.md", "placeholders": []}` | None. |
