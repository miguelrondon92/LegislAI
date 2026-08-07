## Handoff: Docs / QA → Orchestrator

- **Change:** Synced agent + user docs with shipped UI/contracts:
  - UI label is **“N hidden provisions detected”** (not sneaky riders) — `AGENTS.md`, `pipeline-contract.md`, prior handoff amended.
  - Complexity: JSON/`get_complexity_score_new()` are **0.0–1.0** (legacy `>1` ÷100); templates ×100 — `pipeline-contract.md`, `schema-surface.md`, `docs/CLAUDE.md`.
- **Contract fields:** none added/removed; documentation only.
- **Migration needed:** no
- **display_ready impact:** none

### Secrets review (2026-08-05, branch `ui_fixes`)

| Check | Result |
|-------|--------|
| `.gitignore` | `.env`, `.env.*` (`!.env.example`), `config/production.env`, `.git.old-secret-history` present |
| `git check-ignore` | `.env` and `.git.old-secret-history` ignored |
| Tracked env/secret paths | Templates/hooks/CI only (`.env.example`, `*.template` / `*.example`, secret-scan workflow/hooks) — no live `.env` |
| `git log -- .env` | Empty (no `.env` in current history) |
| HEAD content scan | No `AIza…` / `sk-…` / PEM private-key blobs in tracked source (placeholders excluded) |
| History note | Repo previously rewritten (“Initial clean snapshot…”) to remove committed secrets; do not open or commit `.git.old-secret-history` |
| CI | `.github/workflows/secret-scan.yml` (TruffleHog) on PRs to `main` |

No live secrets found in current tree/history; no history rewrite performed. Did **not** read or dump `.env` / old-secret-history contents.

- **Downstream owners:** QA (spot-check docs vs `/bill/...` UI)
- **Suggested tests:** n/a (docs-only); optional confirm profile shows “hidden provisions” and complexity ~65/100 on HR22
