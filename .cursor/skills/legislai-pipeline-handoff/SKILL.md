---
name: legislai-pipeline-handoff
description: Produce a structured handoff packet so LegislAI layer changes propagate from ETL through database, analysis, API, and frontend. Use after finishing work in any pipeline layer or when orchestrating multi-agent collaboration.
---

# LegislAI Pipeline Handoff

## Instructions

After completing a layer change (or when blocking on another owner):

1. Identify **from** and **to** owners using `.cursor/resources/agent-roster.md`.
2. Diff against `.cursor/resources/pipeline-contract.md` — update the contract if the data shape changed.
3. Write a handoff packet (chat summary and optionally `.cursor/handoffs/<slug>.md`):

```markdown
## Handoff: <FROM> → <TO>
Date: <ISO date>
Status: ready | blocked

### Change
<1-5 bullets>

### Contract delta
- Fields added: …
- Fields changed: …
- Fields removed: …
- Migration required: yes/no

### display_ready impact
none | inputs changed | semantics changed

### Next owner actions
- [ ] …

### Suggested tests
- [ ] …
```

4. If multiple downstream owners, emit **one packet per owner** or a single packet with clear sections.
5. Orchestrator must not skip QA when UI-visible behavior changed.

## Ordering reminder

```
ETL → Database → Analysis → API → Frontend → QA
```

If Database is blocked, do not continue Analysis writers that need the new column.
