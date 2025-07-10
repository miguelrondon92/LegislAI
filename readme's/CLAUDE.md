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
- **BackfillOrchestrator** (`services/backfill_orchestrator.py`): Handles bulk processing of historical bills

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
   - Hidden provision detection using pattern matching
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

### New Bill Methods
- `get_active_ai_analysis()` - Returns active AIAnalysis record
- `get_active_summary()` - Returns active Summary record  
- `get_complexity_score_new()` - Gets complexity from AIAnalysis table (0-1 scale for templates)
- `get_controversy_score_new()` - Gets controversy score from AIAnalysis table
- `get_summary_text()` - Gets summary text from Summary table (fallback to old field)
- `create_new_analysis_version()` - Creates new analysis version, deactivating previous ones
- `create_new_summary_version()` - Creates new summary version with versioning support

## File Structure Notes

- `services/` - 17 core business logic modules
- `templates/` - Jinja2 HTML templates with responsive Bootstrap design
- `static/` - CSS and JavaScript assets (style.css, main.js, policy_slider.js)
- `migrations/` - Database migration files with version control
- `utils/` - Utility functions (bill_chunker.py, constants.py, text_processing.py)
- `test/` - Comprehensive test suite (40+ test files)
- `logs/` - Application logs and monitoring data
- `readme's/` - Additional documentation and implementation summaries