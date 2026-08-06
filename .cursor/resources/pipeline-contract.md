# LegislAI Pipeline Contract

Shared contract between ETL, Database, Analysis, API, and Frontend agents.
Update this file when a layer changes the data shape; then run `legislai-pipeline-handoff`.

## End-to-end flow

```
[ETL] Congress API / RSS  — via services/bill_sync.sync_bill (all entry points)
        │  Bill identity: congress + bill_type + bill_number
        │  Two freshness axes (see below)
        │  Metadata: title, summary, sponsor_*, status, dates, actions
        ▼
[Database] Bill (active, version) + BillAction
        │
        ▼
[Analysis] EnhancedAIAnalyzer (Tier A | Tier B)
        │  → AIAnalysis (analysis_data JSON, scores, versioning, active)
        │  → Summary (summary_text, plain_language, key_provisions, …)
        │  → BillCategoryMapping (relevance, sneakiness_score)
        │  → HiddenProvision (canonical hidden provisions for UI)
        │  → pending stubs: policy_analysis.status, stakeholders.status
        ▼
[Database] Bill.update_display_ready_status()
        │  display_ready == True when title/summary + active AIAnalysis
        │  + Summary + at least one BillCategoryMapping exist
        │  (does NOT wait on enrichments)
        ▼
[API] routes serve bill_detail / search / homepage / alerts
        │  + queue analysis_enrichers when pending and RPM allows
        │  + heal HiddenProvision from analysis JSON when table empty
        ▼
[Frontend] Policy Areas | Policy Analysis | Stakeholders | **N hidden provisions detected** (collapsible; reads HiddenProvision only)
        ▼
[Analysis enrichers] async Gemini → stakeholders + policy_analysis ready
```

### ETL entry points (unified via `bill_sync`)

| Entry | Activity refresh | Content ingest |
|-------|------------------|----------------|
| Bill search / bill detail | TTL-gated (default 6h), async off request thread | On miss only |
| RSS / workflow | Always on discovery | On miss; existing bills get activity refresh |
| Backfill CLI | Non-terminal or recent `last_action_date` | `allow_content_ingest=True` |

### Two freshness axes

1. **Activity refresh** (`bill_sync.refresh_activity`) — append missing `BillAction` rows (dedupe `(bill_id, action_date, action_text)`), update `status` / `last_action_date` / `last_updated` on the **active** row. No Gemini. Does **not** fork a Bill version. Does **not** change `display_ready`.
2. **Content ingest** (`BillProcessor.process_bill_data`) — first create or deliberate re-fetch. May fork a new `Bill` version on `content_hash` change (title+summary+full_text). New version starts `display_ready=False` with no carried-forward analysis (known trade-off; version model unchanged).

Never set `display_ready` in ETL. Analysis owns readiness after artifacts exist.

### Cross-ingestor gates (search / RSS / backfill)

- **Bill work lease** (`services/bill_work_lease.py`, table `bill_work_lease`): unique `(bill_id, work_kind)` with TTL. Kinds: `analyze`, `enrich`. Search, workflow, and backfill must `try_acquire` before Gemini; skip/defer if held.
- **Shared Gemini budget** (`services/gemini_rate_budget.py` + `get_shared_ai_analyzer()`): one process-wide FIFO RPM/TPM window (15 RPM / 220k usable TPM). Counters also persisted in `gemini_rate_budget_state` so CLI backfill and Flask share the ceiling.

### Admin UIs

- **RSS dashboard** (`/rss`, legacy `/workflow`) — controls `WorkflowOrchestrator` via `/api/workflow/*`; activity ring at `/api/workflow/logs`.
- **Backfill dashboard** (`/backfill`) — controls in-process `BackfillOrchestrator` via `/api/backfill/*`; activity ring at `/api/backfill/logs`.
- Both pipelines append **OpsAlert** rows on real Gemini analyze start/finish/fail with `source=rss` or `source=backfill` (lease / already-analyzed skips stay ring-buffer only).

## Identity keys (immutable)

- Natural key: `(congress, bill_type, bill_number)` with `active=True`
- Display id helper: `Bill.get_bill_identifier()` → `{congress}-{TYPE}{number}`

## Versioning rules

- Prefer **new rows** with incremented `*_version` and `active` flag over mutating historical analysis/summary.
- Only one active `AIAnalysis` and one active `Summary` per bill.
- Bill updates from Congress may bump `Bill.version`; Analysis decides whether to re-analyze.

## Analysis JSON (minimum keys Frontend/API may rely on)

Documented consumers: `templates/bill_analysis.html`, dashboards, bill search helpers, category extraction in routes.

Critical shapes (core + enrichments):

```json
{
  "policy_areas": {
    "primary_category": "...",
    "secondary_categories": ["..."]
  },
  "policy_implications": {
    "categories": [{"area": "Taxation", "impact_level": "high", "reasoning": "..."}],
    "primary_category": "...",
    "secondary_categories": ["..."]
  },
  "policy_analysis": {
    "status": "pending|ready|skipped",
    "overall_assessment": "...",
    "category_breakdown": {"Taxation": {"relevance_score": 0.7, "reasoning": "..."}},
    "controversial_aspects": [],
    "bipartisan_potential": "..."
  },
  "stakeholders": {
    "status": "pending|ready|skipped",
    "affected_groups": [{"group": "...", "impact_type": "positive|negative|neutral", "impact_description": "..."}],
    "winners_losers": {
      "potential_winners": [],
      "potential_losers": [],
      "neutral_parties": []
    },
    "geographic_impact": "..."
  },
  "complexity_assessment": {"complexity_score": 0.0},
  "key_provisions": []
}
```

`complexity_assessment.complexity_score` is a float **0.0–1.0** (analyzer contract). `Bill.get_complexity_score_new()` returns 0–1 (only divides by 100 if a legacy value is `>1`). Templates display as X/100 via ×100.

Do **not** use legacy template keys alone (`winners` / `losers` at top level of `stakeholders`, or `stakeholder_analysis`). Enrichers normalize flat Gemini shapes into the template shape above.

### Analysis tier / progress (2026-08-04)

Size-aware routing in `EnhancedAIAnalyzer.analyze_bill`:

| `analysis_method` | When | Partial? |
|-------------------|------|----------|
| `single_pass_full_text` | Tier A (≤~150k tokens) | No — two full-text Gemini passes |
| `map_reduce_macro_chunks` | Tier B (oversized) | Yes until all macro-chunks covered |
| `minimal` | No full text / no quota | Yes / incomplete |

Progress keys (API + Frontend may rely on):

- `is_partial`, `completion_percentage` (fraction of bill **characters** covered)
- `chars_analyzed`, `total_chars`
- `analyzed_chunk_keys` (Tier B resume; stable chunk ids)
- `chunks_analyzed`, `total_chunks_available`, `remaining_chunks`
- `limit_cause` (`local_minute_budget` | `gemini_api_429` | `map_failures` | null)
- `provider_model`, `analysis_tier` (`A` | `B` | `C`)
- `tier_b_map_findings` (Tier B map payloads; usable findings only count toward completion)

### Tier B 429 recovery (required)

Hitting Gemini **429 is OK** on free tier. Local RPM/TPM only approximate our side; they do not guarantee Google accepts every call.

**What must never happen:** treat a failed map as progress, then reduce empty stubs into `is_partial=False` / `display_ready` with a “mapping errors” summary.

Contract:

1. **Usable map only** — A chunk counts as analyzed only if the finding is usable: not `map_failed`, and non-empty `summary` (or non-empty `key_provisions`).
2. **Failed ≠ done** — On map call → `None` / empty / `map_failed`: do **not** add the chunk key to `analyzed_chunk_keys`. Leave it for remapping.
3. **Early-stop on 429** — If `_hit_gemini_api_429` during a wave, stop further map calls that wave; persist partial with `limit_cause=gemini_api_429`.
4. **Resume is the recovery path** — Later waves (bill detail / search `force_continue`, delayed wave after minute reset) remap failed keys when quota allows. Completion comes from delayed waves, not from marking failures done.
5. **No garbage complete** — Do not reduce / claim 100% until usable findings cover all macros. Never reduce when every finding is `map_failed`. If reduce text narrates map failure (“mapping errors”, “failed to extract”), treat as incomplete (`limit_cause=map_failures`) and keep partial.
6. **Ops** — Real `continuation_queued` when a wave is spawned; `continuation_finished` partial with `limit_cause=gemini_api_429|map_failures` when still incomplete; complete only after a usable reduce. Do not persist in-flight refresh spam.

Routes: `_tier_b_needs_resume` covers incomplete Tier B **and** fake-complete rows (all `map_failed` / failure-narration summary) so bill detail and search remapped them.

### Policy areas vs enrichments (2026-08-04)

Core analysis writes category labels separately from deep policy narrative:

- `policy_areas`: `{ "primary_category": "...", "secondary_categories": ["..."] }` (UI badges — **Policy Areas** card)
- `policy_implications.categories` — still required for `BillCategoryMapping` / display_ready
- `policy_analysis`: deep narrative for **Policy Analysis** card; `status` pending|ready|skipped
- `stakeholders`: template-canonical shape for **Stakeholder Analysis** card; `status` pending|ready|skipped

Downstream enrichers (`services/analysis_enrichers.py` → `run_downstream_enrichments`) fill `policy_analysis` and `stakeholders` asynchronously when RPM allows. Merge into a **new** `AIAnalysis` version; stamp `provider_model`. `display_ready` does **not** wait on enrichments.

**Quota gate (required):** use `enrichment_quota_ok(analyzer)` which reads `get_rate_limit_status()["remaining_requests"]` (need ≥ 2). Do **not** use `get_quota_info()["status"]["safe_remaining_requests"]` — that nest does not exist (always looked like 0 and caused false `local_minute_budget` skip spam). On real deferral: keep `pending`, do not persist a skip version, routes cooldown via `_enrichment_defer_until`.

Ops classes: `enrichment_queued`, `enrichment_finished` (plus existing Gemini failure classes). Extra may include `limit_cause`, `remaining_requests`, `event=deferred|queued|finished`.

API: enrich uses DB lease kind `enrich` via `bill_work_lease` (must not block Tier B resume / `analyze` lease). Template context: `enrichment_flags` (`stakeholders_pending`, `policy_analysis_pending`, `any_enrichment_pending`, `enrichment_queued`).

Tests: `test/test_downstream_enrichers.py`, `test/test_size_aware_analysis.py`.

### Hidden provisions (DB source of truth)

Product name in UI: **hidden provisions**. Pipeline names: `hidden_provisions` (analysis JSON snapshot) → **`HiddenProvision` rows** (canonical).

- On **complete** live analysis persist (`EnhancedAIAnalyzer._persist_analysis_results`), call `services.hidden_provisions.store_hidden_provisions` (replace prior rows for the bill; stamp `provider_model`). Skip while `is_partial`.
- Bill detail **heals** empty tables from active analysis JSON via `heal_hidden_provisions_from_analysis`.
- Frontend (`bill_analysis.html`, search, home, notifications) reads **only** `Bill.get_hidden_provisions*` — never analysis JSON for this card.
- Collapsible profile header: **“N hidden provisions detected”**.

Tests: `test/test_hidden_provisions_store.py`.

If you rename or remove keys, update:
1. `services/enhanced_ai_analyzer.py` + `services/analysis_enrichers.py` writers
2. Category extraction / enrichment queue in `routes.py`
3. `templates/bill_analysis.html`
4. Tests under `test/`

## display_ready

See [display-ready-contract.md](display-ready-contract.md). Notifications and homepage listing assume this flag.

## Gemini failure contingency

- Do not fabricate analysis JSON or force `display_ready=True` when Gemini fails.
- Structured ops log: logger `legislai.ops.gemini` (`GEMINI_FAILURE ...`).
- Persist `OpsAlert` for in-app `/ops/logs` (unread filters by bill / class).
- Optional programmer webhook: `OPS_ALERT_WEBHOOK_URL` via `services/ops_alert_service.py` (independent of user `NOTIFICATIONS_ENABLED`).
- User-facing: preserve partial/quota messaging in bill analysis and search templates.

## Handoff packet (required)

When finishing a layer change, leave a short note (PR comment, chat, or `.cursor/handoffs/<topic>.md`):

```markdown
## Handoff: <layer> → <next>
- Change: …
- Contract fields added/changed/removed: …
- Migration needed: yes/no
- display_ready impact: …
- Downstream owners: Database | Analysis | API | Frontend | QA
- Suggested tests: …
```

## Forbidden

- Writing secrets into models, fixtures, templates, or docs
- Frontend calling Gemini/Congress directly
- ETL writing analysis JSON into `Bill.ai_analysis` as the primary store (use AIAnalysis table)
- Skipping migrations when `db_models.py` changes
