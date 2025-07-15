# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

LegislAI is a Python-based Flask web application that analyzes U.S. legislative bills using AI to provide policy insights and user-specific alerts. The system fetches bills from the Congress API, performs AI analysis to identify policy implications and hidden provisions, and notifies users based on their policy preferences.

## Core Architecture

### Application Structure
- **Flask Application** (`app.py`): Main web application with extensions (SQLAlchemy, Flask-Login, Flask-Mail, Flask-Migrate)
- **Database Models** (`db_models.py`): SQLAlchemy models for bills, users, alerts, policy categories, and relationships
- **Authentication** (`auth.py`): User authentication and registration system with Flask-Login
- **Routes** (`routes.py`): Web routes for bill search, analysis, profile management, and workflow API endpoints
- **Services Layer** (`services/`): Core business logic modules (17 service files)
- **Utils** (`utils/`): Utility functions for text processing, bill chunking, and constants
- **Templates** (`templates/`): Jinja2 HTML templates for the web interface
- **Static Assets** (`static/`): CSS and JavaScript files

### Key Services
- **WorkflowOrchestrator** (`services/workflow_orchestrator.py`): Main processing pipeline that coordinates RSS monitoring, bill fetching, AI analysis, and alert generation
- **EnhancedAIAnalyzer** (`services/enhanced_ai_analyzer.py`): AI analysis using Google Gemini with chunked processing for large bills
- **CongressAPI** (`services/congress_api.py`): Interface to Congress.gov API for fetching bill data
- **BillProcessor** (`services/bill_processor.py`): Processes and stores bill data in the database
- **NotificationService** (`services/notification_service.py`): Manages email notifications and alerts
- **RSSMonitoring** (`services/rss_monitoring.py`): Monitors Congress RSS feeds for new bills
- **BackfillOrchestrator** (`services/backfill_orchestrator.py`): Handles careful, rate-limited processing of historical bills (default batch size: 1)

### Data Models
- **Bill**: Legislative bills with metadata, complexity scores, and versioning. Now uses relationships to AIAnalysis and Summary tables
- **AIAnalysis**: Stores AI analysis results with versioning support. Includes complexity/controversy scores, analysis metadata, and processing statistics
- **Summary**: Stores bill summaries with versioning. Supports multiple summary types and key provisions tracking
- **User**: User accounts with policy preferences, notification settings, and authentication
- **Alert**: User-specific notifications about relevant bills with alignment scores
- **PolicyCategory**: 36 standardized federal policy categories (see `utils/constants.py`)
- **UserPolicySubscription**: User preferences for policy areas with interest levels and notification settings
- **BillCategoryMapping**: Links bills to policy categories with relevance scores
- **BillAction**: Congressional actions and timeline events for bills
- **UserBillAlignment**: User-specific alignment scores and analysis details for bills
- **WatchlistItem**: User-created watchlists for tracking specific bills
- **HiddenProvision**: Detected hidden/sneaky provisions in bills with detailed risk analysis

## Web Routes and API Endpoints

### Main Web Routes
- `/` - Homepage dashboard showing recent bills and user alerts
- `/bill_search` - Bill search interface with multiple search types
- `/bill/<congress>/<bill_type>/<bill_number>` - Individual bill analysis page
- `/profile` - User profile and policy preference management  
- `/alerts` - User alerts dashboard
- `/workflow` - Administrative workflow monitoring dashboard

### API Endpoints
- `/api/generate_alerts` - Generate user alerts based on preferences
- `/api/bill/<congress>/<bill_type>/<bill_number>/text` - Fetch bill full text
- `/api/workflow/start` - Start the workflow orchestrator
- `/api/workflow/stop` - Stop the workflow orchestrator  
- `/api/workflow/status` - Get workflow status and statistics
- `/api/workflow/recent` - Get recent workflow activity

### Authentication Routes (Blueprint: `/auth`)
- `/auth/signin` - User login
- `/auth/signup` - User registration
- `/auth/profile` - User profile setup

## Common Development Tasks

### Running the Application
```bash
# Install dependencies
pip install -r requirements.txt

# Set up database
flask db upgrade

# Run the application
python app.py
```

### Testing
```bash
# Run comprehensive test suite
python test/run_all_tests.py

# Run specific test categories
python test/test_workflow.py
python test/test_chunked_analysis.py
python test/test_notifications.py
python test/test_hr1_analysis.py
```

### Backfill Operations (Careful Processing)
```bash
# Careful analysis-only mode (batch size 1, default)
python services/backfill_orchestrator.py --mode analysis-only

# Full processing with rate limiting (discovers and processes new bills)
python services/backfill_orchestrator.py --mode full --congress 119

# Process only missing/unanalyzed bills
python services/backfill_orchestrator.py --mode gaps

# Discovery only (find bills but don't process)
python services/backfill_orchestrator.py --mode discovery

# Resume previous operation
python services/backfill_orchestrator.py --resume

# Custom batch size (if faster processing is needed)
python services/backfill_orchestrator.py --mode analysis-only --batch-size 5
```

### Database Operations
```bash
# Create migration
flask db migrate -m "description"

# Apply migration
flask db upgrade

# Downgrade migration
flask db downgrade

# Direct SQLite access
sqlite3 instance/legislative_analysis.db
```

## Environment Variables

Required environment variables (set in `.env`):
- `DATABASE_URL`: Database connection string (default: sqlite:///legislative_analysis.db)
- `SESSION_SECRET`: Flask session secret key  
- `GEMINI_API_KEY`: Google Gemini API key for AI analysis
- `CONGRESS_API_KEY`: Congress.gov API key (optional for most operations)
- `MAIL_SERVER`, `MAIL_PORT`, `MAIL_USERNAME`, `MAIL_PASSWORD`: Email settings for notifications

## Key Features

### AI Analysis Pipeline
The system uses a sophisticated chunked analysis approach for large bills:
1. Bills are fetched from Congress API using `CongressAPI` service
2. Full text is divided into intelligent chunks using `BillChunker` (max 6000 chars, 800 char overlap)
3. Each chunk is analyzed by Google Gemini AI via `EnhancedAIAnalyzer`
4. Results are combined into comprehensive analysis including:
   - Policy implications categorized into 36 federal policy areas
   - Stakeholder impact analysis with winners/losers
   - Hidden provision detection using 28 suspicious language patterns with detailed reasoning and risk scoring
   - Complexity scoring (0-1 scale, displayed as 0-100)
   - Controversy assessment and risk scoring

### User Notification System
- Users subscribe to policy categories with granular interest levels (0.0-1.0)
- System generates alerts when new bills match user preferences via alignment scoring
- Alignment scores calculated based on user preferences vs bill content
- Email notifications sent based on user frequency preferences (daily/weekly/monthly)
- In-app alert dashboard with read/unread status tracking

### Bill Management and Versioning
- Bills support versioning system with `active` flag for latest versions
- **New Database Structure**: AI analysis and summaries moved to separate tables (AIAnalysis, Summary) with their own versioning
- Each bill can have multiple analysis/summary versions with `active` flag indicating current version
- Homepage displays only active bills to avoid duplicates
- Bill detail pages use `.first()` query pattern for consistency
- Complexity scores retrieved from AIAnalysis table via `get_complexity_score_new()` method
- Bill actions timeline shows congressional progress and history

### Workflow Management
The `WorkflowOrchestrator` coordinates:
- RSS monitoring for new bills via `PersistentRSSMonitor`
- Bill data fetching and storage with duplicate detection
- AI analysis processing with rate limiting and chunking
- Alert generation and delivery to subscribed users
- Comprehensive error handling and retry logic
- Statistical tracking and monitoring

## Important Technical Notes

### Rate Limiting and Performance
- Gemini API limited to 15 requests/minute (free tier)
- Maximum 15 chunks analyzed per bill to prevent quota exhaustion
- Intelligent chunking with overlap to maintain context
- All AI analysis cached in database to avoid reprocessing
- Workflow can be started/stopped via API endpoints
- **BackfillOrchestrator**: Default batch size of 1 for careful processing with 3.6s Congress API delay and 4.0s AI API delay
- **Automatic pause on quota exhaustion** with resumable state persistence

### Database and Data Consistency
- SQLite by default, PostgreSQL support via `DATABASE_URL`
- **New Database Structure**: AI analysis data moved to separate AIAnalysis table with proper versioning
- Bill complexity scores stored as 0-100 scale in analysis JSON, converted to 0-1 scale by new methods for template compatibility
- Both homepage and bill detail pages display as X/100 scale for consistency using `get_complexity_score_new()` method
- Bill queries use consistent `.first()` pattern to ensure same records across pages
- Comprehensive migration system with Alembic
- Backward compatibility maintained: old `ai_analysis` field still available as fallback

### Database Structure Optimization (Recently Implemented)
- **Moved AI analysis to separate AIAnalysis table** with `bill_id` mapping for proper normalization
- **Added Summary table** with versioning and `active` field for when bills change and summaries need updates
- **New Bill methods**: `get_complexity_score_new()`, `get_controversy_score_new()`, `get_summary_text()` use new table structure
- **AI analysis versioning**: Each bill can have multiple analysis versions with metadata (processing time, chunks analyzed, analysis method)
- **Summary versioning**: Multiple summary types supported (ai_generated, manual, updated) with key provisions tracking
- **Migration completed**: All existing data preserved and migrated to new structure (15 AI analyses + 15 summaries)
- **Backward compatibility**: Old `Bill.ai_analysis` field maintained as fallback, existing code continues to work
- **Enhanced AI analyzer**: Now creates new analysis versions using `create_new_analysis_version()` method

### Hidden Provisions Detection System
A sophisticated system for detecting and analyzing potentially problematic bill language:

#### Detection Capabilities
- **28 Pattern-Based Detection**: Sophisticated regex patterns for suspicious language:
  - "notwithstanding any other provision of law"
  - "waiver of requirements", "exemption from review"
  - "emergency authority", "discretionary power"
  - "fast track", "expedited approval"
  - "sunset provision", "grandfather clause"
  - And 18 additional patterns for comprehensive coverage

#### Risk Assessment Framework
- **Risk Levels**: Low, Medium, High with color-coded visual indicators
- **Confidence Scoring**: 0.0-1.0 confidence in detection accuracy
- **Risk Factors**: Detailed JSON array of specific concerns
- **Impact Analysis**: Potential consequences and recommendations
- **Overall Risk Score**: Calculated aggregate score per bill

#### Database Storage
- **HiddenProvision Table**: Comprehensive storage of detected provisions
- **Bill Integration**: Foreign key relationships with proper indexing
- **Analysis Versioning**: Links to specific AI analysis versions
- **Metadata Tracking**: Chunk location, detection method, timestamps

#### Web Interface Integration
- **Search Results**: Color-coded badges showing hidden provision counts
- **Bill Analysis**: Detailed accordion-style provision breakdown
- **Dashboard**: Risk indicators on recent bills display
- **Interactive Features**: Expand/collapse all provisions, risk filtering

#### Bill Helper Methods
- `get_hidden_provisions(risk_level=None)` - Filter provisions by risk level
- `get_hidden_provisions_count()` - Risk level breakdown statistics
- `has_high_risk_provisions()` - Boolean check for high-risk items
- `get_overall_hidden_risk_score()` - Calculated aggregate risk assessment

## New Database Schema (AIAnalysis & Summary Tables)

### AIAnalysis Table
```python
class AIAnalysis(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    bill_id = db.Column(db.Integer, db.ForeignKey('bill.id'), nullable=False)
    analysis_data = db.Column(db.Text)  # JSON stored analysis results
    complexity_score = db.Column(db.Float)  # 0-1 scale for compatibility
    controversy_score = db.Column(db.Float)
    analysis_version = db.Column(db.Integer, nullable=False, default=1)
    active = db.Column(db.Boolean, nullable=False, default=True)
    analysis_method = db.Column(db.String(50))  # 'chunked', 'full', etc.
    chunks_analyzed = db.Column(db.Integer)
    processing_time = db.Column(db.Float)  # seconds
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
```

### Summary Table
```python
class Summary(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    bill_id = db.Column(db.Integer, db.ForeignKey('bill.id'), nullable=False)
    summary_text = db.Column(db.Text)
    plain_language_summary = db.Column(db.Text)
    key_provisions = db.Column(db.Text)  # JSON array
    funding_amounts = db.Column(db.String(500))
    implementation_timeline = db.Column(db.String(500))
    summary_version = db.Column(db.Integer, nullable=False, default=1)
    active = db.Column(db.Boolean, nullable=False, default=True)
    summary_type = db.Column(db.String(50), default='ai_generated')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
```

### HiddenProvision Table
```python
class HiddenProvision(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    bill_id = db.Column(db.Integer, db.ForeignKey('bill.id'), nullable=False)
    provision_type = db.Column(db.String(200), nullable=False)  # Type of provision
    provision_text = db.Column(db.Text, nullable=False)  # Exact text or description
    risk_level = db.Column(db.String(20), nullable=False)  # low, medium, high
    confidence_score = db.Column(db.Float, nullable=False, default=0.0)  # 0.0-1.0
    risk_factors = db.Column(db.Text)  # JSON array of risk factors
    potential_impact = db.Column(db.Text)  # Description of potential impact
    recommendation = db.Column(db.Text)  # What to watch for
    overall_assessment = db.Column(db.Text)  # Brief assessment
    chunk_index = db.Column(db.Integer)  # Which chunk this was found in
    chunk_type = db.Column(db.String(100))  # Type of chunk (section, subsection, etc.)
    section_reference = db.Column(db.String(200))  # Section reference if available
    analysis_version = db.Column(db.Integer, nullable=False, default=1)
    detection_method = db.Column(db.String(50), default='ai_enhanced')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
```

### New Bill Methods
- `get_active_ai_analysis()` - Returns active AIAnalysis record
- `get_active_summary()` - Returns active Summary record  
- `get_complexity_score_new()` - Gets complexity from AIAnalysis table (0-1 scale for templates)
- `get_controversy_score_new()` - Gets controversy score from AIAnalysis table
- `get_summary_text()` - Gets summary text from Summary table (fallback to old field)
- `create_new_analysis_version()` - Creates new analysis version, deactivating previous ones
- `create_new_summary_version()` - Creates new summary version with versioning support

### Hidden Provisions Bill Methods
- `get_hidden_provisions(risk_level=None)` - Returns hidden provisions filtered by risk level
- `get_hidden_provisions_count()` - Returns risk level breakdown dictionary
- `has_high_risk_provisions()` - Boolean check for high-risk provisions
- `get_overall_hidden_risk_score()` - Calculated aggregate risk score (0.0-1.0)

## File Structure Notes

- `services/` - 17 core business logic modules
- `templates/` - Jinja2 HTML templates with responsive Bootstrap design
- `static/` - CSS and JavaScript assets (style.css, main.js, policy_slider.js)
- `migrations/` - Database migration files with version control
- `utils/` - Utility functions (bill_chunker.py, constants.py, text_processing.py)
- `test/` - Comprehensive test suite (40+ test files)
- `logs/` - Application logs and monitoring data
- `readme's/` - Additional documentation and implementation summaries (see below for complete list)

## Documentation Index (readme's/ folder)

### Core System Documentation
- **`CLAUDE.md`** - This file: Comprehensive system overview and developer guide
- **`WORKFLOW_README.md`** - Workflow orchestrator system documentation
- **`DATABASE_POPULATION_GUIDE.md`** - Complete guide for populating database with congressional data

### Implementation Summaries  
- **`DATABASE_OPTIMIZATION_IMPLEMENTATION_LOG.md`** - Comprehensive log of database structure optimization (AI analysis → separate tables)
- **`DATABASE_OPTIMIZATION_SUMMARY.md`** - Technical summary of database optimization with schema definitions
- **`HIDDEN_PROVISIONS_IMPLEMENTATION_SUMMARY.md`** - Complete hidden provisions detection system implementation
- **`FULL_TEXT_ANALYSIS_IMPLEMENTATION_SUMMARY.md`** - Full text analysis enhancement implementation
- **`BILL_SEARCH_ENHANCEMENT_SUMMARY.md`** - Bill search functionality improvements
- **`HOMEPAGE_DUPLICATE_FIX_SUMMARY.md`** - Homepage duplicate bill display fixes

### System Configuration  
- **`BACKOFF_IMPLEMENTATION.md`** - Rate limiting and backoff implementation details
- **`LIMIT_ENFORCEMENT_SUMMARY.md`** - Rate limit enforcement and monitoring

### Recent Updates
- **`RECENT_UPDATES.md`** - Summary of recent major system changes and enhancements
- **`continued_ideas.md`** - Future enhancement ideas and development roadmap

## Latest Fixes and Enhancements (July 2025)

### API Rate Limit Handling & User Experience Enhancement (July 14, 2025)

#### Comprehensive 429 Error Handling System
- **Custom Exception Classes** for specific error scenarios:
  - `APIRateLimitError` - Congress API rate limit exceeded  
  - `AIAnalysisPartialError` - AI analysis incomplete due to rate limits
- **Graceful Error Recovery** - 429 errors converted to user-friendly messages
- **Partial Analysis Preservation** - AI analysis saves partial results when rate limited

#### Enhanced User Communication System
- **Prominent Bill Profile Alerts** - Red danger alerts on non-display-ready bills stating: "We're sorry, but this bill is not fully analyzed due to API limitations"
- **Search Result Status Badges** - "Analysis In Progress" indicators for incomplete bills
- **Fallback Content Display** - Congress API summaries shown for non-display-ready bills with clear "From Congress.gov" labeling
- **Completion Tracking** - Partial analysis percentages displayed to users

#### Bill Summary Text Cleaning System
- **HTML Entity Decoding** - Converts `&lt;DOC&gt;` and similar entities to readable text or removes them
- **Document Markup Removal** - Removes XML/SGML tags like `<DOC>`, `<DOCID>`, legislative bill references
- **Template Integration** - New `clean_summary` Jinja2 filter automatically cleans bill summaries
- **Professional Display** - Whitespace normalization and formatting cleanup for better readability

#### Error Handling Flow Implementation
1. **Congress API 429 Detection** - Rate limit errors caught and user-friendly messages displayed
2. **AI API Rate Limit Management** - Partial analysis saved to database with completion metadata
3. **User Experience Continuity** - Fallback content ensures users always see useful information
4. **Production Resilience** - System continues functioning under API constraints

#### Components Enhanced
- `services/congress_api.py` - 429 error detection and `APIRateLimitError` exception
- `services/enhanced_ai_analyzer.py` - `AIAnalysisPartialError` with completion tracking
- `routes.py` - Comprehensive error handling in search and analysis routes
- `templates/bill_analysis.html` - Prominent alerts and fallback summary section
- `utils/text_processing.py` - Bill summary cleaning with `clean_bill_summary()` function
- `app.py` - Custom `clean_summary` template filter registration

### Bill Text Acquisition Improvements
- **Enhanced Congress API text fetching** (`services/congress_api.py`)
- **Exhaustive retry logic** with progressive timeouts (30s → 60s → 120s)
- **Format fallback system** - tries ALL available formats, not just preferred ones
- **Comprehensive error handling** for different HTTP status codes (404, 429, 503)
- **Content validation** to ensure meaningful text is retrieved
- **Rate limiting protection** with exponential backoff

### Category Mapping System Fixes
- **Fixed missing category mappings** for bills with AI analysis data
- **Root cause**: EnhancedAIAnalyzer was creating analysis but not calling category mapping
- **Solution**: Added `_store_policy_categories()` method to EnhancedAIAnalyzer class
- **Results**: Bills with category mappings increased from 10 to 21 (110% improvement)
- **Created batch fix script** (`fix_category_mappings.py`) for retroactive repairs

### Display-Ready System Enhancement
- **Analysis-only mode** now properly gets bills to display-ready state
- **Category mappings** are now created during AI analysis process
- **Improved completion tracking** for bills requiring full analysis vs just mapping
- **Enhanced logging** and progress reporting for analysis-only operations

### WorkflowOrchestrator RSS Integration
- **Full compatibility** with new database structure and enhanced AI analysis
- **Automatic category mapping** for bills discovered via RSS monitoring
- **Complete end-to-end processing** from RSS discovery to display-ready status
- **Enhanced error handling** prevents pipeline failures during bill text acquisition
- **Zero duplicate processing** - removed redundant category mapping calls
- **Production ready** for continuous RSS monitoring with complete automation

### Bill Search Integration Enhancement
- **Complete system integration** with new database structure and enhanced features
- **Search coverage improved** from 8 bills (10.7%) to 75 bills (100% coverage)
- **Template compatibility** with new complexity score methods (`get_complexity_score_new()`)
- **Prioritized search results** - display-ready bills shown first, but all bills included
- **Enhanced analysis triggering** - automatic AI analysis for bills without existing analysis
- **Comprehensive integration testing** - test suite validates all components work together
- **Fixed duplicate category mapping** - removed redundant calls in search routes

### Integration Test Results (July 13, 2025)
```
✅ Bill Number Search: Working (found HR618 with all metadata)
✅ Keyword Search: Working (2 bills found for 'agriculture')  
✅ Sponsor Search: Working (1 bill found for 'Johnson')
✅ Analysis Triggering: Correct logic for new bill analysis
✅ Database Structure: 44 bills using new AIAnalysis table, 21 with category mappings
✅ Template Compatibility: Complexity scores display as X/100 format
✅ Search Coverage: 8 → 75 bills searchable (840% improvement)
✅ Hidden Provisions: Display system working correctly
✅ No Integration Issues: All components verified working together
```