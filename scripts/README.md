# Scripts Directory

This directory contains utility scripts organized by purpose.

## Directory Structure

### `/setup/`
Scripts for initial setup and configuration:
- `create_policy_categories.py` - Initialize policy categories in database
- `migrate_ai_data.py` - Migrate AI analysis data between database schemas
- `setup_real_email.py` - Configure real email delivery (Gmail/SendGrid)

### `/debug/`
Debugging and diagnostic scripts:
- `check_gemini_quota.py` - Check Gemini API quota and usage
- `check_workflow.py` - Verify workflow orchestrator status
- `debug_analysis_issue.py` - Debug AI analysis problems
- `debug_congress_api.py` - Debug Congress.gov API issues
- `debug_notification_issue.py` - Debug notification system
- `debug_template.py` - Debug template rendering issues
- `investigate_email_delivery.py` - Investigate email delivery problems

### `/cleanup/`
Maintenance and cleanup scripts:
- `cleanup_ai_analysis.py` - Clean up orphaned AI analysis data
- `cleanup_duplicate_bills.py` - Remove duplicate bill records
- `fix_and_send_notification.py` - Fix and resend failed notifications
- `fix_category_mappings.py` - Fix bill category mapping issues
- `truncate_bills.py` - Remove old bill data

### `/monitoring/`
Monitoring and background process scripts:
- `process_seen_items.py` - Process RSS feed seen items
- `start_monitoring_demo.py` - Start monitoring system demo

## Usage

Run scripts from the project root directory:

```bash
# Setup example
python scripts/setup/create_policy_categories.py

# Debug example
python scripts/debug/check_workflow.py

# Cleanup example
python scripts/cleanup/cleanup_duplicate_bills.py

# Monitoring example
python scripts/monitoring/start_monitoring_demo.py
```