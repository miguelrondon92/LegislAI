# LegislAI Project Structure

## Root Directory Files
- `app.py` - Main Flask application entry point
- `auth.py` - Authentication and user management
- `db_models.py` - Database models and schema definitions
- `main.py` - Alternative application entry point
- `manage.py` - Database management commands
- `routes.py` - Flask route definitions
- `run_app.py` - Application runner script
- `utils.py` - General utility functions
- `workflow_admin.py` - Workflow administration interface
- `pyproject.toml` - Python project configuration
- `requirements.txt` - Python dependencies
- `uv.lock` - UV package manager lock file

## Directory Structure

### `/services/` - Core Business Logic
Contains the main service layer implementations:
- `enhanced_ai_analyzer.py` - AI-powered bill analysis
- `notification_service.py` - User notification system
- `workflow_orchestrator.py` - Bill processing workflow coordination
- `congress_api.py` - Congress.gov API integration
- `bill_processor.py` - Bill data processing
- Other specialized services...

### `/templates/` - HTML Templates
Flask Jinja2 templates for web interface:
- `base.html` - Base template
- `dashboard.html` - User dashboard
- `bill_detail.html` - Bill analysis view
- `auth/` - Authentication templates
- `admin/` - Admin interface templates

### `/static/` - Static Assets
- `css/` - Stylesheets
- `js/` - JavaScript files
- `generated-icon.png` - Application icon

### `/test/` - Test Suite
Comprehensive test files organized by functionality:
- Unit tests for all major components
- Integration tests for workflows
- Sample data and test fixtures

### `/scripts/` - Utility Scripts
Organized by purpose:
- `setup/` - Initial setup and configuration
- `debug/` - Debugging and diagnostic tools
- `cleanup/` - Maintenance and cleanup utilities
- `monitoring/` - Monitoring and background processes

### `/utils/` - Utility Modules
Reusable utility functions:
- `bill_chunker.py` - Text chunking for AI analysis
- `text_processing.py` - Text manipulation utilities
- `constants.py` - Application constants
- `helpers.py` - General helper functions

### `/config/` - Configuration Files
- `production_email_config.env` - Email service configuration
- `production.env.template` - Production environment template with secure defaults

### `/docs/` - Documentation
Comprehensive project documentation:
- `README.md` - Main project documentation
- `CLAUDE.md` - System architecture documentation
- `RECENT_UPDATES.md` - Recent changes log
- `ENHANCED_ANALYSIS_PIPELINE_DOCUMENTATION.md` - Technical documentation
- Feature implementation summaries and development logs
- AI analyzer consolidation documentation
- Database optimization guides
- Frontend enhancement logs

### `/archives/` - Legacy Code
Deprecated and legacy modules kept for reference:
- Old implementations replaced by current services
- One-off scripts no longer in use
- Historical code for reference

### `/migrations/` - Database Migrations
Alembic database migration scripts and configuration

### `/logs/` - Application Logs
Runtime logs, monitoring data, and state files

### `/instance/` - Flask Instance Data
- `legislative_analysis.db` - SQLite database file

### `/backup_old_analyzers/` - Legacy Analyzers
Backup of old AI analysis implementations

### `/venv/` - Python Virtual Environment
Python virtual environment (if using venv)

## Key Design Patterns

1. **Service Layer Architecture** - Business logic separated into `/services/`
2. **Utility Separation** - Common functions in `/utils/`
3. **Script Organization** - Utilities organized by purpose in `/scripts/`
4. **Template Structure** - Hierarchical template organization
5. **Test Organization** - Comprehensive test suite in `/test/`
6. **Documentation Separation** - Different docs for different audiences

## Environment Configuration

### Logging Configuration
The application uses environment-based logging configuration:

**Development (.env):**
```
LOG_LEVEL=DEBUG
```

**Production:**
```
LOG_LEVEL=WARNING
```

**Available Log Levels:**
- `DEBUG` - Detailed debugging information
- `INFO` - General information messages
- `WARNING` - Warning messages (production default)
- `ERROR` - Error messages only
- `CRITICAL` - Critical errors only

**Log Format:**
```
%(asctime)s - %(name)s - %(levelname)s - %(message)s
```

### Notification Configuration
The application controls notification delivery based on environment:

**Development (.env):**
```
FLASK_ENV=development
# Notifications automatically enabled in development
```

**Production:**
```
FLASK_ENV=production
NOTIFICATIONS_ENABLED=false  # Explicitly enable with 'true'
```

**Notification Behavior:**
- `FLASK_ENV=development` - Notifications always enabled
- `FLASK_ENV=production` + `NOTIFICATIONS_ENABLED=true` - Notifications enabled
- `FLASK_ENV=production` + `NOTIFICATIONS_ENABLED=false` - Notifications disabled (default)

### Environment Templates
- Development settings in `.env`
- Production template in `config/production.env.template`
- Copy production template and customize for deployment

## Development Workflow

1. Core application files remain in root for Flask conventions
2. Business logic implemented in services
3. Utilities for common operations
4. Scripts for administrative tasks
5. Tests for quality assurance
6. Documentation for maintainability
7. Environment-based configuration for different deployment stages