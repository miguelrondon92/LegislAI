# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

LegislAI is a Python-based Flask web application that analyzes U.S. legislative bills using AI to provide policy insights and user-specific alerts. The system fetches bills from the Congress API, performs AI analysis to identify policy implications and hidden provisions, and notifies users based on their policy preferences.

## Core Architecture

### Application Structure
- **Flask Application** (`app.py`): Main web application with extensions (SQLAlchemy, Flask-Login, Flask-Mail, Flask-Migrate)
- **Database Models** (`db_models.py`): SQLAlchemy models for bills, users, alerts, policy categories, and relationships
- **Authentication** (`auth.py`): User authentication and registration system
- **Routes** (`routes.py`): Web routes for bill search, analysis, profile management, and workflow API endpoints
- **Services Layer** (`services/`): Core business logic modules

### Key Services
- **WorkflowOrchestrator** (`services/workflow_orchestrator.py`): Main processing pipeline that coordinates RSS monitoring, bill fetching, AI analysis, and alert generation
- **EnhancedAIAnalyzer** (`services/enhanced_ai_analyzer.py`): AI analysis using Google Gemini with chunked processing for large bills
- **CongressAPI** (`services/congress_api.py`): Interface to Congress.gov API for fetching bill data
- **BillProcessor** (`services/bill_processor.py`): Processes and stores bill data in the database
- **NotificationService** (`services/notification_service.py`): Manages email notifications and alerts

### Data Models
- **Bill**: Legislative bills with full text, metadata, and AI analysis
- **User**: User accounts with policy preferences and notification settings
- **Alert**: User-specific notifications about relevant bills
- **PolicyCategory**: Categorization system for policy areas
- **UserPolicySubscription**: User preferences for policy areas and notification settings
- **BillCategoryMapping**: Links bills to policy categories with relevance scores

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
# Run various test scripts
python test_workflow.py
python test_chunked_analysis.py
python test_notifications.py
```

### Database Operations
```bash
# Create migration
flask db migrate -m "description"

# Apply migration
flask db upgrade

# Downgrade migration
flask db downgrade
```

## Environment Variables

Required environment variables (set in `.env`):
- `DATABASE_URL`: Database connection string
- `SESSION_SECRET`: Flask session secret key
- `GEMINI_API_KEY`: Google Gemini API key for AI analysis
- `CONGRESS_API_KEY`: Congress.gov API key
- `MAIL_SERVER`, `MAIL_PORT`, `MAIL_USERNAME`, `MAIL_PASSWORD`: Email settings

## Key Features

### AI Analysis Pipeline
The system uses a chunked analysis approach for large bills:
1. Bills are fetched from Congress API
2. Full text is divided into chunks for processing
3. Each chunk is analyzed by Google Gemini AI
4. Results are combined into comprehensive analysis including:
   - Policy implications and categories
   - Stakeholder impact analysis
   - Hidden provision detection
   - Overall risk scoring

### User Notification System
- Users subscribe to policy categories with interest levels
- System generates alerts when new bills match user preferences
- Alignment scores calculated based on user preferences vs bill content
- Email notifications sent based on user frequency preferences

### Workflow Management
The `WorkflowOrchestrator` coordinates:
- RSS monitoring for new bills
- Bill data fetching and storage
- AI analysis processing
- Alert generation and delivery
- Rate limiting and error handling

## Important Notes

- The system includes sophisticated rate limiting for the Gemini API to prevent quota exhaustion
- Large bills are processed using intelligent chunking to handle the 1M character limit
- The workflow can be started/stopped via API endpoints at `/api/workflow/start` and `/api/workflow/stop`
- Database uses SQLite by default but can be configured for PostgreSQL via `DATABASE_URL`
- All AI analysis is cached in the database to avoid reprocessing

## File Structure Notes

- `services/` contains the core business logic
- `templates/` contains Jinja2 HTML templates
- `static/` contains CSS and JavaScript assets
- `migrations/` contains database migration files
- `utils/` contains utility functions for text processing and bill chunking
- Test files are in root directory with `test_` prefix