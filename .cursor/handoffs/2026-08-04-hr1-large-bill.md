## Handoff: Analysis / API / Frontend → QA
Date: 2026-08-04
Status: ready

### Change
- Live E2E for **119-HR1** (Tier B large bill, ~1.05M chars / ~315k tokens) vs **119-HR22** (Tier A small bill).
- Bugfix: empty Tier B waves no longer persist a fresh `minimal` analysis that wiped `tier_b_map_findings` (broke reduce accuracy after resume).
- Bugfix: history heal of map findings + remapping of orphan keys; skip persist when `_no_progress`.
- Bug fix: bill detail resume quota uses `_can_continue_tier_b_wave()` (TPM for one macro), schedules delayed wave when blocked.
- Bug fix: restored `elif bill.get_ai_analysis()` in `bill_analysis` (accidental overwrite set `analysis=None` on complete bills).
- Frontend: Tier B auto-poll scales with `data-remaining-chunks` (up to 40 × 18s).

### Contract delta
- Fields added: `_no_progress` (ephemeral; stripped before persist), `_needs_rereduce` (ephemeral prior-load)
- Fields changed: none for persisted JSON shape
- Migration required: no

### display_ready impact
none (semantics unchanged). HR-1 reached `display_ready=True` after full Tier B reduce + category mappings; enrichments remain async.

### Live results
| Bill | Tier | Text | Result |
|------|------|------|--------|
| 119-HR1 | B `map_reduce_macro_chunks` | ~1.05M chars, 3 macros | 100% complete, 3 map findings, 7 categories, enrichments ready; profile ~8–125ms |
| 119-HR22 | A `single_pass_full_text` | ~31k chars | Still display_ready (regression smoke) |

Ops lifecycle observed: `continuation_queued` → `partial_analysis` / `continuation_finished` (partial) → delayed wave → `continuation_finished` (100%) → `enrichment_queued` / `enrichment_finished`.

### Next owner actions
- [x] QA: `test/test_size_aware_analysis.py` (13 tests) including empty-wave preserve + orphan remap + TPM gate
- [x] Live curl `/bill/119/hr/1`, `/ops/logs?bill=HR1`, search `HR-1`, `/bill/119/hr/22`

### Suggested tests
- [x] Empty wave preserves `tier_b_map_findings`
- [x] Orphan keys remapped
- [x] `_can_continue_tier_b_wave` respects TPM
- [ ] Optional: integration fixture for heal-from-history → re-reduce

## Final QA verdict
- **Successful**: full text persisted; Tier B 100%; Summary + categories + display_ready
- **Timely**: search/profile non-blocking; delayed waves after minute reset; longer auto-poll for remaining chunks
- **Accurate**: reduce uses all 3 map findings after heal (summary covers tax/SNAP/Medicaid/immigration/debt ceiling)
