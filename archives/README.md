# Archives Directory

This directory contains legacy code, one-off scripts, deprecated modules, and historical documentation kept for reference only.

## Contents

### Legacy Core Modules
- `bill_analyzer.py` - Original bill analysis logic (replaced by enhanced_ai_analyzer.py)
- `congress_api.py` - Legacy Congress API client (replaced by services/congress_api.py)
- `models.py` - Old database models (replaced by db_models.py)

### One-off Scripts
- `fetch_recent_bills.py` - Simple bill fetching script
- `fetch_recent_bills_simple.py` - Simplified version of bill fetcher
- `perform_ai_analysis.py` - Standalone AI analysis script
- `send_notification_to_migron.py` - Test notification script for specific user
- `workflow_verification_summary.py` - Workflow verification report generator

### Historical documentation (`docs/`)

Implementation summaries and fix logs superseded by the [root README](../README.md), [AGENTS.md](../AGENTS.md), and [pipeline-contract](../.cursor/resources/pipeline-contract.md):

| File | Former topic |
|------|----------------|
| `AI_ANALYZER_CONSOLIDATION_*.md` | Pre/post consolidation of analyzers |
| `FULL_TEXT_ANALYSIS_IMPLEMENTATION_SUMMARY.md` | Full-text analysis rollout |
| `ASYNC_*.md`, `WORKFLOW_ORCHESTRATOR_INTEGRATION_STATUS.md` | Early async / workflow status |
| `BACKOFF_IMPLEMENTATION.md`, `LIMIT_ENFORCEMENT_SUMMARY.md` | Pre–shared-budget rate limiting |
| `DATABASE_OPTIMIZATION_IMPLEMENTATION_LOG.md` | Long DB refactor log |
| `HIDDEN_PROVISIONS_IMPLEMENTATION_SUMMARY.md` | Hidden provisions feature log |
| `BILL_SEARCH_*`, `HOMEPAGE_*`, `FRONTEND_*`, `PROGRESSIVE_LOADING_*`, `BILL_TEXT_*`, `SERVER_LOG_*` | One-off UI/search/fix notes |
| `continued_ideas.md` | Product brainstorm (folded into root README) |
| `GEMINI_API_FIX_SUMMARY.md`, `DEPLOYMENT_FIX_REPORT.md` | Test/deploy fix notes |

## Notes

- These files are preserved for historical reference and potential code recovery
- Do not use archived modules or treat archived docs as current architecture
- For current implementations, refer to the main codebase, [`/services/`](../services/README.md), and the [root README](../README.md)
