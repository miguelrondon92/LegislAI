# LegislAI Pipeline Contract

Shared contract between ETL, Database, Analysis, API, and Frontend agents.
Update this file when a layer changes the data shape; then run `legislai-pipeline-handoff`.

## End-to-end flow

```
[ETL] Congress API / RSS
        │  Bill identity: congress + bill_type + bill_number
        │  Metadata: title, summary, sponsor_*, status, dates, actions
        ▼
[Database] Bill (active, version) + BillAction
        │
        ▼
[Analysis] EnhancedAIAnalyzer
        │  → AIAnalysis (analysis_data JSON, scores, versioning, active)
        │  → Summary (summary_text, plain_language, key_provisions, …)
        │  → BillCategoryMapping (relevance, sneakiness_score)
        │  → HiddenProvision (optional risk artifacts)
        ▼
[Database] Bill.update_display_ready_status()
        │  display_ready == True when title/summary + active AIAnalysis
        │  + Summary + at least one BillCategoryMapping exist
        ▼
[API] routes serve bill_detail / search / homepage / alerts
        ▼
[Frontend] templates + static JS render scores, categories, provisions
```

## Identity keys (immutable)

- Natural key: `(congress, bill_type, bill_number)` with `active=True`
- Display id helper: `Bill.get_bill_identifier()` → `{congress}-{TYPE}{number}`

## Versioning rules

- Prefer **new rows** with incremented `*_version` and `active` flag over mutating historical analysis/summary.
- Only one active `AIAnalysis` and one active `Summary` per bill.
- Bill updates from Congress may bump `Bill.version`; Analysis decides whether to re-analyze.

## Analysis JSON (minimum keys Frontend/API may rely on)

Documented consumers: `bill_detail.html`, `dashboard.html`, bill search helpers, category extraction in routes.

Critical shapes (support all three category formats):

```json
{
  "policy_implications": {
    "categories": [{"area": "Taxation", "impact_level": 0.7, "reasoning": "..."}],
    "category_breakdown": {"Taxation": {"relevance_score": 0.7, "reasoning": "..."}},
    "primary_category": "...",
    "secondary_categories": ["..."]
  },
  "complexity_assessment": {"complexity_score": 0-100},
  "stakeholder_analysis": {},
  "key_provisions": []
}
```

If you rename or remove keys, update:
1. `services/enhanced_ai_analyzer.py` writers
2. Category extraction in `routes.py`
3. Templates reading those keys
4. Tests under `test/`

## display_ready

See [display-ready-contract.md](display-ready-contract.md). Notifications and homepage listing assume this flag.

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
