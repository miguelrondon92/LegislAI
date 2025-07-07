# LegislAI Database Population Guide

This guide documents all the scripts and tools available for populating the LegislAI database with congressional data. Each script includes command-line arguments for customization.

## 📋 Overview

LegislAI provides several approaches to populate your database with congressional bills and analysis:

1. **Backfill System** - Systematic historical data population
2. **Recent Bills Fetching** - Get the latest bills from recent days  
3. **Database Management** - Setup, cleanup, and maintenance tools
4. **Testing & Validation** - Scripts to verify functionality

---

## 🚀 Primary Data Population Scripts

### 1. Backfill Orchestrator (Recommended)
**File:** `services/backfill_orchestrator.py`  
**Purpose:** Comprehensive system for populating database with historical congressional data

#### Basic Usage
```bash
# Discovery mode - find all bills from 119th Congress
python -m services.backfill_orchestrator --mode discovery --max-bills 100

# Full processing - discover + AI analysis
python -m services.backfill_orchestrator --mode full --batch-size 5

# Process only missing/unanalyzed bills
python -m services.backfill_orchestrator --mode gaps --batch-size 10
```

#### Command Arguments
| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `--congress` | int | 119 | Congress session number |
| `--mode` | choice | full | Processing mode: `discovery`, `full`, `gaps` |
| `--batch-size` | int | 10 | Number of bills to process per batch |
| `--max-bills` | int | 1000 | Maximum bills to process in session |
| `--resume` | flag | false | Resume from previous state |
| `--reset` | flag | false | Reset state and start fresh |
| `--status` | flag | false | Show current status |
| `--analyze-gaps` | flag | false | Run gap analysis only |

#### Processing Modes
- **`discovery`** - Only discover and catalog bills (no AI analysis)
- **`full`** - Discover bills + perform AI analysis + store results
- **`gaps`** - Only process missing bills or bills without analysis

#### Examples
```bash
# Start fresh discovery for 118th Congress
python -m services.backfill_orchestrator --congress 118 --mode discovery --reset

# Resume full processing with smaller batches
python -m services.backfill_orchestrator --mode full --batch-size 3 --resume

# Check current status
python -m services.backfill_orchestrator --status

# Analyze what's missing from database
python -m services.backfill_orchestrator --analyze-gaps

# Process only gaps with limit
python -m services.backfill_orchestrator --mode gaps --max-bills 50
```

---

### 2. Recent Bills Fetcher
**File:** `fetch_recent_bills.py`  
**Purpose:** Fetch bills from recent days using date-based filtering

#### Basic Usage
```bash
# Fetch bills from last 10 days (default)
python fetch_recent_bills.py

# Fetch from last 30 days, max 500 bills
python fetch_recent_bills.py --days 30 --max-bills 500

# Use specific date range
python fetch_recent_bills.py --use-date-range --start-date 2024-01-01 --end-date 2024-01-31
```

#### Command Arguments
| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `--days` | int | 10 | Number of days to look back |
| `--max-bills` | int | 1000 | Maximum bills to process |
| `--use-date-range` | flag | false | Use specific date range instead |
| `--start-date` | string | - | Start date (YYYY-MM-DD format) |
| `--end-date` | string | - | End date (YYYY-MM-DD format) |

#### Examples
```bash
# Last week's bills
python fetch_recent_bills.py --days 7 --max-bills 100

# Specific month
python fetch_recent_bills.py --use-date-range --start-date 2024-12-01 --end-date 2024-12-31

# Large recent fetch
python fetch_recent_bills.py --days 60 --max-bills 2000
```

---

### 3. Simple Recent Bills Fetcher
**File:** `fetch_recent_bills_simple.py`  
**Purpose:** Simplified, faster version for getting recent bills

#### Basic Usage
```bash
# Fetch recent bills (simple approach)
python fetch_recent_bills_simple.py --days 7 --max-bills 50
```

#### Command Arguments
| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `--days` | int | 10 | Number of days to look back |
| `--max-bills` | int | 50 | Maximum bills to process |

---

## 🛠 Database Management Scripts

### 4. Policy Categories Setup
**File:** `create_policy_categories.py`  
**Purpose:** Initialize policy categories in database (required for bill analysis)

#### Usage
```bash
# Create policy categories (run once during setup)
python create_policy_categories.py
```

**No arguments** - Creates standard federal policy categories if none exist.

---

### 5. Database Cleanup
**File:** `cleanup_ai_analysis.py`  
**Purpose:** Remove corrupted AI analysis data from database

#### Usage
```bash
# Clean up error analysis data
python cleanup_ai_analysis.py
```

**No arguments** - Automatically finds and removes AI analysis containing error messages.

---

### 6. Bills Truncation
**File:** `truncate_bills.py`  
**Purpose:** Clear all bills and related data from database

#### Usage
```bash
# WARNING: This deletes ALL bill data
python truncate_bills.py
```

**No arguments** - Interactive confirmation required. Deletes all bills, actions, alerts, and related data.

---

## 🧪 Testing & Validation Scripts

### 7. Backfill System Tests
**File:** `test_backfill_system.py`  
**Purpose:** Validate backfill orchestrator functionality

#### Usage
```bash
# Test all backfill components
python test_backfill_system.py
```

### 8. Simple Workflow Demo
**File:** `test_simple_workflow.py`  
**Purpose:** Demonstrate complete bill analysis workflow

#### Usage
```bash
# Run workflow demonstration
python test_simple_workflow.py
```

### 9. System Summary
**File:** `test_summary.py`  
**Purpose:** Show current database state and system status

#### Usage
```bash
# Display system overview
python test_summary.py
```

---

## 📋 Recommended Workflow

### First-Time Setup
```bash
# 1. Create policy categories
python create_policy_categories.py

# 2. Test system functionality
python test_backfill_system.py

# 3. Start with discovery mode to understand data volume
python -m services.backfill_orchestrator --mode discovery --max-bills 50

# 4. Check what was found
python -m services.backfill_orchestrator --analyze-gaps

# 5. Begin full processing with small batches
python -m services.backfill_orchestrator --mode full --batch-size 3 --max-bills 20
```

### Regular Updates
```bash
# Daily: Fetch recent bills
python fetch_recent_bills_simple.py --days 1 --max-bills 25

# Weekly: Fetch broader recent range
python fetch_recent_bills.py --days 7 --max-bills 100

# Monthly: Check for gaps and fill
python -m services.backfill_orchestrator --mode gaps --max-bills 200
```

### Large Data Population
```bash
# For historical data population (run in screen/tmux)
python -m services.backfill_orchestrator --mode full --batch-size 5 --congress 119 --reset

# Monitor progress
python -m services.backfill_orchestrator --status

# Resume if interrupted
python -m services.backfill_orchestrator --mode full --resume
```

---

## ⚠️ Important Notes

### Rate Limiting
- Congress API: 3.6 second intervals (1000 requests/hour)
- Gemini AI API: 4.0 second intervals (configurable)
- All scripts respect these limits automatically

### Environment Variables Required
```bash
CONGRESS_API_KEY=your_congress_api_key
GEMINI_API_KEY=your_gemini_api_key
DATABASE_URL=sqlite:///legislative_analysis.db  # or PostgreSQL URL
```

### Resource Considerations
- **Storage**: Each bill with analysis ~50-200KB
- **Time**: Full analysis ~10-15 seconds per bill
- **Memory**: Chunked processing handles large bills efficiently
- **Network**: Respects API rate limits, plan for long-running jobs

### Error Handling
- All scripts include comprehensive error logging
- State persistence allows resuming interrupted jobs
- Cleanup tools available for corrupted data
- Progress tracking for long-running operations

---

## 🔍 Monitoring & Status

### Check System Status
```bash
# Overall system health
python test_summary.py

# Backfill specific status
python -m services.backfill_orchestrator --status

# API quota status
python check_gemini_quota.py
```

### Log Files
- Backfill state: `logs/backfill_state_{congress}.json`
- Application logs: `logs/`
- Monitor disk space for large data populations

---

## 🆘 Troubleshooting

### Common Issues

**"No bills found"**
```bash
# Check API connectivity
python debug_congress_api.py

# Verify API keys in .env file
```

**"AI analysis failed"**
```bash
# Check Gemini quota
python check_gemini_quota.py

# Clean corrupted analysis
python cleanup_ai_analysis.py
```

**"Database errors"**
```bash
# Check database health
python test_summary.py

# Reset if needed (WARNING: destructive)
python truncate_bills.py
```

**"Backfill stuck"**
```bash
# Check status
python -m services.backfill_orchestrator --status

# Reset and restart
python -m services.backfill_orchestrator --reset
```

---

This guide covers all database population tools in LegislAI. For development and testing purposes, also see the various `test_*.py` scripts which demonstrate specific functionality and can be run to verify system components.