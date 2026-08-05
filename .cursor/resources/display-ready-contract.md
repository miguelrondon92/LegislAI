# display_ready Contract

`Bill.display_ready` gates homepage listing, polished bill pages, and notification triggers.

## Definition (implementation: `Bill.update_display_ready_status`)

A bill is display-ready when **all** are true:

1. Has title and summary (bill metadata from ETL)
2. Has active `AIAnalysis` with usable complexity signal
3. Has active `Summary` row
4. Has at least one `BillCategoryMapping`

Agents must call / preserve `update_display_ready_status()` after mutations that affect these inputs.

## What is NOT required

- `policy_analysis.status == ready` (deep Policy Analysis enricher)
- `stakeholders.status == ready` (Stakeholder Analysis enricher)

Bills may be `display_ready=True` while those sections show pending/queued placeholders. Enrichment completion creates a new `AIAnalysis` version but must not flip `display_ready` false.

## Ownership

| Layer | Responsibility |
|-------|----------------|
| ETL | Populate title, summary, actions; never set `display_ready=True` without analysis |
| Analysis | Create AIAnalysis, Summary, category mappings; then update status |
| Database | Keep helper methods and columns consistent |
| API | Trigger analysis-if-needed and category extraction for search/direct URL |
| Frontend | Treat `display_ready=False` as incomplete / progressive loading states |
| QA | Assert false→true transition in workflow and search tests |

## Regression checklist

- [ ] New bill from search ends `display_ready=True` when quota allows
- [ ] Partial analysis can extract categories and become ready
- [ ] Homepage only lists ready bills (or shows incomplete state intentionally)
- [ ] Notification path keys off ready transition where applicable
- [ ] Enrichments pending does not block `display_ready=True`
- [ ] After enrichers finish, bill detail shows Policy Analysis narrative + Stakeholder groups (template shape)
