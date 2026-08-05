## Handoff: Analysis / API / Frontend → QA

- **Change:** Hidden provisions now persist to `HiddenProvision` on the live complete-analysis path; bill detail heals empty tables from analysis JSON. Profile shows collapsible **“N hidden provisions detected”** reading only the DB.
- **Contract:** `HiddenProvision` is the read source of truth; `analysis_data.hidden_provisions` remains the analyzer snapshot/write payload. Shared helper: `services/hidden_provisions.py`.
- **Migration needed:** no
- **display_ready impact:** none (provisions do not gate display_ready)
- **Downstream owners:** Frontend | QA
- **Suggested tests:** `test/test_hidden_provisions_store.py`; live `/bill/119/hr/22` shows count > 0 after heal; search/home risk badges after table populate
