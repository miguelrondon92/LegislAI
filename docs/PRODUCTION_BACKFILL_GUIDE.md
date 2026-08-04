# Production Backfill Orchestrator Guide

## Overview

The backfill orchestrator now supports production mode with PostgreSQL database integration. This guide covers how to run the backfill orchestrator in production environments.

## Production Mode Features

### ✅ Key Capabilities
- **PostgreSQL Database Support**: Automatically configures for production PostgreSQL database
- **Enhanced Performance**: Optimized rate limiting for production infrastructure
- **Separate State Management**: Uses production-specific state files
- **Safety Features**: Confirmation prompts for destructive operations
- **Environment Validation**: Validates required production environment variables
- **Production Logging**: Appropriate log levels and detailed status reporting

### 🔧 Technical Improvements
- **Congress API Delay**: Reduced from 3.6s to 2.0s for better infrastructure
- **AI API Delay**: Reduced from 4.0s to 3.0s for production usage
- **State Frequency**: Saves state every 10 operations (vs 5 in development)
- **Database Pooling**: Production-optimized connection pool settings

## Setup Instructions

### 1. Environment Configuration

Create your production environment file:
```bash
cp config/production.env.template config/production.env
```

Update `config/production.env` with your production values:
```bash
# Database Configuration (REQUIRED)
DATABASE_URL=postgresql://username:password@localhost:5432/legislai_production

# API Keys (REQUIRED)
GEMINI_API_KEY=your-production-gemini-api-key
CONGRESS_API_KEY=your-congress-api-key

# Flask Configuration
FLASK_ENV=production
FLASK_DEBUG=false
LOG_LEVEL=WARNING
SESSION_SECRET=your-secure-random-secret-key

# Email Configuration (if needed)
MAIL_SERVER=smtp.sendgrid.net
MAIL_PORT=587
MAIL_USERNAME=apikey
MAIL_PASSWORD=your-sendgrid-api-key
MAIL_USE_TLS=true
```

### 2. Database Setup

Ensure your PostgreSQL database is ready:
```sql
CREATE DATABASE legislai_production;
CREATE USER legislai_user WITH PASSWORD 'secure_password';
GRANT ALL PRIVILEGES ON DATABASE legislai_production TO legislai_user;
```

Run database migrations:
```bash
# Set production database URL
export DATABASE_URL=postgresql://username:password@localhost:5432/legislai_production

# Run migrations
flask db upgrade
```

## Usage Examples

### Basic Operations

```bash
# Check production database status
python services/backfill_orchestrator.py --prod --status

# Analyze gaps in production database
python services/backfill_orchestrator.py --prod --analyze-gaps

# Run analysis-only mode (safest for existing data)
python services/backfill_orchestrator.py --prod --mode analysis-only

# Full processing with custom batch size
python services/backfill_orchestrator.py --prod --mode full --batch-size 3 --congress 119
```

### Advanced Operations

```bash
# Resume previous production operation
python services/backfill_orchestrator.py --prod --resume

# Process only missing bills
python services/backfill_orchestrator.py --prod --mode gaps --batch-size 5

# Discovery only (find new bills without processing)
python services/backfill_orchestrator.py --prod --mode discovery --max-bills 500

# Reset production state (with safety confirmation)
python services/backfill_orchestrator.py --prod --reset
```

## Production Safety Features

### 🛡️ Safety Confirmations
When using `--reset` in production mode, you'll be prompted:
```
⚠️  WARNING: You are about to reset backfill state in PRODUCTION mode. Type 'CONFIRM' to proceed:
```

### 📋 Environment Validation
Before starting, the system validates:
- `DATABASE_URL` is set and points to PostgreSQL
- `GEMINI_API_KEY` is configured
- Database connection is successful
- All required environment variables are present

### 📁 Separate State Files
Production mode uses separate state files to avoid conflicts:
- Development: `logs/backfill_state_{congress}.json`
- Production: `logs/backfill_state_prod_{congress}.json`

## Monitoring and Logging

### 📊 Status Monitoring
```bash
# Real-time status check
python services/backfill_orchestrator.py --prod --status

# Example output:
{
  "congress_session": 119,
  "status": "processing",
  "processing_mode": "analysis_only",
  "start_time": "2025-07-18T19:00:00.000000",
  "last_update": "2025-07-18T19:15:30.000000",
  "processing": {
    "bills_processed": 45,
    "bills_analyzed": 42,
    "bills_failed": 3,
    "current_batch": 9
  }
}
```

### 📝 Enhanced Logging
Production mode provides detailed logging:
```
2025-07-18 19:20:06 - INFO - 🚀 Starting backfill orchestrator in PRODUCTION mode
2025-07-18 19:20:06 - INFO - 📊 Database: postgresql://username:password@localhost:5432/...
2025-07-18 19:20:06 - INFO - 🔑 API Key: ✅ Configured
2025-07-18 19:20:06 - INFO - 📁 Using production state file: logs/backfill_state_prod_119.json
```

## Performance Optimization

### ⚡ Production Configuration
The production mode automatically applies optimizations:

| Setting | Development | Production |
|---------|-------------|------------|
| Congress API Delay | 3.6s | 2.0s |
| AI API Delay | 4.0s | 3.0s |
| State Save Frequency | Every 5 bills | Every 10 bills |
| Database Pool Size | Default | 10 connections |
| Database Max Overflow | Default | 20 connections |
| Log Level | INFO | WARNING |

### 📈 Recommended Batch Sizes
- **Analysis-only mode**: 1-3 (safest, recommended)
- **Gap processing**: 3-5 (moderate speed)
- **Full discovery**: 1-2 (most careful)

## Troubleshooting

### Common Issues

#### 1. Database Connection Errors
```bash
# Test database connection
python -c "
import os
os.environ['DATABASE_URL'] = 'your-production-db-url'
from app import app, db
with app.app_context():
    print('Database connection successful!')
"
```

#### 2. Missing Environment Variables
```
ValueError: Missing required production environment variables: DATABASE_URL, GEMINI_API_KEY
```
**Solution**: Ensure all required variables are set in `config/production.env`

#### 3. State File Conflicts
If you see state loading from the wrong file:
- Development state: `logs/backfill_state_{congress}.json`
- Production state: `logs/backfill_state_prod_{congress}.json`

### 🔍 Debug Mode
Enable debug logging for troubleshooting:
```bash
# Temporarily enable debug logging
LOG_LEVEL=DEBUG python services/backfill_orchestrator.py --prod --status
```

## Best Practices

### 🎯 Recommended Workflow

1. **Start with Status Check**:
   ```bash
   python services/backfill_orchestrator.py --prod --status
   ```

2. **Analyze Gaps**:
   ```bash
   python services/backfill_orchestrator.py --prod --analyze-gaps
   ```

3. **Run Analysis-Only Mode** (safest):
   ```bash
   python services/backfill_orchestrator.py --prod --mode analysis-only
   ```

4. **Monitor Progress**:
   ```bash
   python services/backfill_orchestrator.py --prod --status
   ```

### 🔒 Security Considerations

- Store sensitive credentials in environment variables, not in code
- Use strong, unique passwords for database connections
- Regularly rotate API keys
- Monitor logs for suspicious activity
- Use secure connections (SSL/TLS) for database connections

### 📊 Performance Monitoring

- Monitor API quota usage with `check_gemini_quota.py`
- Track processing speed and error rates
- Set up alerting for failed operations
- Regular database performance monitoring

## Integration with CI/CD

### GitHub Actions Example
```yaml
name: Production Backfill
on:
  schedule:
    - cron: '0 2 * * *'  # Daily at 2 AM

jobs:
  backfill:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Setup Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.9'
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Run production backfill
        env:
          DATABASE_URL: ${{ secrets.DATABASE_URL }}
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
        run: |
          python services/backfill_orchestrator.py --prod --mode analysis-only --batch-size 2
```

## Support

For production issues:
1. Check logs in `logs/` directory
2. Verify environment configuration
3. Test database connectivity
4. Monitor API quota status
5. Review state file for stuck operations

The production mode is designed to be robust and safe for continuous operation in production environments.