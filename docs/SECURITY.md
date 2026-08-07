# Security notes for LegislAI

## Secrets

Never commit `.env`, API keys, passwords, or private keys. Use [`.env.example`](../.env.example) as the template. Local `.env` and `.git.old-secret-history/` are gitignored.

App secrets are read from the environment (see `.env.example`):

- `SESSION_SECRET` — Flask session signing
- `GEMINI_API_KEY` / `CONGRESS_API_KEY` — analysis and Congress.gov
- `LEGISLAI_ADMIN_USERNAME` / `LEGISLAI_ADMIN_PASSWORD` — ops/admin UI
- Mail and `OPS_ALERT_WEBHOOK_URL` — optional notifications

## Before making the repository public

Even when automated scans are clean, treat any prior private history as potentially exposed:

1. **Rotate** Gemini, Congress.gov, mail, admin password, `SESSION_SECRET`, and any webhook URLs in the providers’ consoles.
2. Update your local `.env` with the new values (never commit it).
3. Re-run a full-history scan (`gitleaks detect` / TruffleHog) on the SHA you will publish.
4. Confirm CI secret-scan on `main` is green.

## Scanning

- Local: `gitleaks detect --source .` or TruffleHog against the git repo
- CI: [`.github/workflows/secret-scan.yml`](../.github/workflows/secret-scan.yml)
