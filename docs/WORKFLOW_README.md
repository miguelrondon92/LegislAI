# Legislative Analysis Workflow System

## Overview

The Legislative Analysis Workflow System is a comprehensive automated pipeline designed to achieve two primary goals:

1. **Store AI analysis in the database** - Analyze bills using AI and store comprehensive analysis results
2. **Push alerts to users** - Generate and deliver personalized alerts based on user policy preferences

The system operates continuously and supports both real-time RSS monitoring and backfilling of existing bills.

## Core Objectives

### 1. AI Analysis Storage
- Perform comprehensive AI analysis of bill content using Gemini API
- **Store analysis results in dedicated AIAnalysis table** with proper versioning and metadata
- **Store summaries in separate Summary table** with versioning support for bill changes
- Map bills to policy categories with relevance scores
- Maintain analysis history and versioning with processing metadata (chunks analyzed, processing time, analysis method)

### 2. User Alert Generation
- Match bills to user policy preferences and subscriptions
- Calculate user-bill alignment scores
- Generate personalized alerts with appropriate priority levels
- Support multiple notification channels (email, in-app)

## Workflow Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   RSS Monitor   │    │  Backfill Proc  │    │  Workflow Queue │
│   (Real-time)   │    │  (Existing)     │    │                 │
└─────────┬───────┘    └─────────┬───────┘    └─────────┬───────┘
          │                      │                      │
          └──────────────────────┼──────────────────────┘
                                 │
                    ┌─────────────▼─────────────┐
                    │   Bill Processing         │
                    │   (Fetch & Store)         │
                    └─────────────┬─────────────┘
                                  │
                    ┌─────────────▼─────────────┐
                    │   AI Analysis             │
                    │   (Analyze & Store)       │
                    └─────────────┬─────────────┘
                                  │
                    ┌─────────────▼─────────────┐
                    │   Alert Generation        │
                    │   (Match & Notify)        │
                    └─────────────┬─────────────┘
                                  │
                    ┌─────────────▼─────────────┐
                    │   Database Storage        │
                    │   (Analysis + Alerts)     │
                    └───────────────────────────┘
```

## Key Components

### 1. RSS Monitoring
- **Component**: `services/rss_monitoring.py`
- **Function**: Continuously monitors Congress.gov RSS feeds for new legislative activity
- **Feeds Monitored**:
  - House Floor Today
  - Senate Floor Today
  - Bills Presented to President
- **Features**:
  - Persistent tracking of seen items
  - Keyword filtering
  - Configurable check intervals
  - Duplicate prevention

### 2. Backfill Processor
- **Component**: `services/workflow_orchestrator.py` (Backfill Thread)
- **Function**: Processes existing bills that don't have AI analysis
- **Features**:
  - Finds bills without AI analysis
  - Processes in batches to avoid overwhelming the system
  - Runs independently of RSS monitoring
  - Can be enabled/disabled separately

### 3. Bill Processing
- **Component**: `services/bill_processor.py`
- **Function**: Fetches complete bill data from Congress API
- **Features**:
  - Fetches bill text, metadata, and actions
  - Stores bill information in database
  - Processes and stores bill actions with timestamps
  - Handles bill updates and versioning

### 4. AI Analysis
- **Component**: `services/ai_analyzer.py`
- **Function**: Performs comprehensive AI analysis of bill content
- **Analysis Types**:
  - Policy categorization with confidence scores
  - Stakeholder impact analysis
  - Complexity assessment
  - Key provisions extraction
  - Plain language summaries
  - Controversy detection

### 5. Alert Generation
- **Component**: `services/workflow_orchestrator.py` (Alert Logic)
- **Function**: Generates personalized alerts for users
- **Features**:
  - Policy preference matching
  - User-bill alignment scoring
  - Priority-based alert generation
  - Duplicate alert prevention

### 6. Database Storage
- **Component**: Database models and migrations
- **Stores**:
  - Bill metadata and AI analysis results
  - Policy category mappings with relevance scores
  - User policy subscriptions and preferences
  - Generated alerts with alignment scores
  - Bill actions with timestamps

## Database Schema Integration

### Bill Analysis Storage
```python
class Bill(db.Model):
    # ... existing fields ...
    ai_analysis = db.Column(db.Text)  # JSON stored analysis
    policy_categories = db.Column(db.Text)  # JSON policy categories
    complexity_score = db.Column(db.Float)
```

### Policy Category Mapping
```python
class BillCategoryMapping(db.Model):
    bill_id = db.Column(db.Integer, db.ForeignKey('bill.id'))
    policy_category_id = db.Column(db.Integer, db.ForeignKey('policy_category.id'))
    relevance_score = db.Column(db.Float)  # 0.0 to 1.0
    category_specific_analysis = db.Column(db.Text)  # JSON analysis
```

### User Alert System
```python
class Alert(db.Model):
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    bill_id = db.Column(db.Integer, db.ForeignKey('bill.id'))
    alert_type = db.Column(db.String(50))  # 'policy_match', 'alignment', etc.
    alignment_score = db.Column(db.Float)
    priority = db.Column(db.String(20))  # 'low', 'medium', 'high', 'critical'
```

## WorkflowOrchestrator

The main orchestrator coordinates all workflow components with focus on the two primary goals:

```python
class WorkflowOrchestrator:
    def __init__(self):
        self.rss_monitor = PersistentRSSMonitor()
        self.bill_processor = BillProcessor()
        self.ai_analyzer = AIAnalyzer()
        self.notification_service = NotificationService()
        self.congress_api = CongressAPI()
```

**Key Methods**:
- `start_workflow(enable_rss=True, enable_backfill=False)` - Start workflow with configurable sources
- `_process_workflow_item()` - Process individual bills through the pipeline
- `_perform_ai_analysis()` - Analyze and store AI results in database
- `_generate_user_alerts()` - Create alerts based on user preferences
- `_run_backfill_processor()` - Process existing bills without analysis

## API Endpoints

### Workflow Control
- `POST /api/workflow/start` - Start the automated workflow
- `POST /api/workflow/stop` - Stop the automated workflow
- `GET /api/workflow/status` - Get workflow status and statistics
- `GET /api/workflow/recent` - Get recent workflow items

### Configuration Options
- `enable_rss`: Enable/disable RSS monitoring
- `enable_backfill`: Enable/disable backfill processing
- `check_interval`: RSS monitoring frequency (default: 300 seconds)

## Database Structure Updates

### New Analysis Storage (Recently Implemented)

The workflow now uses an optimized database structure for storing AI analysis results:

**AIAnalysis Table**: Dedicated table for AI analysis with versioning
- Stores analysis data, complexity/controversy scores, and processing metadata
- Supports multiple versions per bill with `active` flag
- Tracks processing time, chunks analyzed, and analysis method

**Summary Table**: Separate table for bill summaries with versioning
- Stores multiple summary types (ai_generated, manual, updated)
- Supports key provisions tracking and implementation timelines
- Enables summary updates when bills change

**Enhanced AI Analyzer Integration**:
```python
# Workflow now creates analysis versions with metadata
bill.create_new_analysis_version(
    analysis_data=analysis_results,
    complexity_score=complexity_score,
    controversy_score=controversy_score,
    analysis_method='chunked',
    chunks_analyzed=len(chunks),
    processing_time=processing_time
)
```

**Benefits for Workflow**:
- Proper versioning when bills are updated
- Metadata tracking for performance monitoring
- Better query performance for analysis data
- Separation of concerns (analysis vs summary data)

## Web Interface

### Workflow Dashboard
Accessible at `/workflow`, the dashboard provides:

- **Real-time Status**: Current workflow status (running/stopped)
- **Statistics**: Bills discovered, processed, analyzed, and alerts generated
- **Source Breakdown**: RSS vs backfill processing statistics
- **Recent Items**: Table of recent workflow items with status
- **Control Panel**: Start/stop workflow with configuration options
- **Process Diagram**: Visual representation of the workflow steps

### Features
- Auto-refresh every 30 seconds
- Real-time status indicators
- Error tracking and display
- Workflow control with source configuration
- Responsive design

## Configuration

### RSS Monitoring
Configure RSS feeds in `services/rss_monitoring.py`:

```python
self.feeds = {
    'house_bills': 'https://www.congress.gov/rss/house-floor-today.xml',
    'senate_bills': 'https://www.congress.gov/rss/senate-floor-today.xml',
    'presented_to_president': 'https://www.congress.gov/rss/presented-to-president.xml'
}
```

### Processing Intervals
- RSS monitoring: 5 minutes (configurable)
- Backfill processing: 5 minutes
- Workflow processing: 1 minute
- Dashboard refresh: 30 seconds

### Keywords
Default keywords for RSS filtering:
- 'bill', 'legislation', 'act', 'resolution'

## Usage

### Starting the Workflow

1. **RSS Monitoring Only** (default):
   ```python
   start_workflow_service(enable_rss=True, enable_backfill=False)
   ```

2. **Backfill Processing Only**:
   ```python
   start_workflow_service(enable_rss=False, enable_backfill=True)
   ```

3. **Both RSS and Backfill**:
   ```python
   start_workflow_service(enable_rss=True, enable_backfill=True)
   ```

4. **Via Web Interface**:
   - Navigate to `/workflow`
   - Configure source options
   - Click "Start" button

5. **Via API**:
   ```bash
   curl -X POST http://localhost:5000/api/workflow/start \
     -H "Content-Type: application/json" \
     -d '{"enable_rss": true, "enable_backfill": false}'
   ```

### Monitoring
- **Dashboard**: Real-time monitoring at `/workflow`
- **Logs**: Check `logs/workflow.log` for detailed logs
- **API**: Use `/api/workflow/status` for programmatic monitoring

### Stopping the Workflow
1. **Via Web Interface**: Click "Stop" button
2. **Via API**: `POST /api/workflow/stop`
3. **Programmatically**: `stop_workflow_service()`

## AI Analysis Features

### Chunked Bill Analysis (Enhanced)
The AI analyzer now uses a sophisticated chunked analysis approach that eliminates truncation limits and provides comprehensive analysis of entire bills:

1. **Bill Chunking System**:
   - Automatically splits bills into manageable sections
   - Identifies structured sections (SECTION, TITLE, PART, etc.)
   - Calculates importance scores for each chunk
   - Combines related chunks intelligently
   - Maintains context across chunk boundaries

2. **Policy Categorization**:
   - Analyzes multiple chunks to identify policy areas
   - Primary and secondary policy areas with confidence scores
   - Impact levels (low/medium/high)
   - Bipartisan potential assessment
   - Controversial aspects identification

3. **Stakeholder Analysis**:
   - Comprehensive stakeholder identification across all bill sections
   - Affected groups and organizations
   - Economic impact assessment
   - Geographic distribution of effects
   - Winners/losers analysis

4. **Complexity Assessment**:
   - Full-text complexity analysis (no truncation)
   - Reading level analysis
   - Implementation difficulty
   - Regulatory burden assessment
   - Cost impact estimation

5. **Summary Generation**:
   - Plain language explanations based on key chunks
   - Key provisions extraction from entire bill
   - Main themes identification
   - Funding and timeline analysis

### Chunked Analysis Benefits
- **No Truncation**: Processes entire bills regardless of length
- **Intelligent Sectioning**: Respects bill structure and hierarchy
- **Importance Scoring**: Prioritizes most relevant sections
- **Context Preservation**: Maintains relationships between sections
- **Scalable**: Handles bills of any size efficiently

### Analysis Storage
All analysis results are stored in structured format with chunked analysis metadata:

```json
{
  "summary": {
    "main_summary": "...",
    "key_provisions": [...],
    "plain_language_explanation": "..."
  },
  "policy_implications": {
    "primary_policy_area": "...",
    "categories": [...],
    "bipartisan_potential": "..."
  },
  "stakeholders": {
    "affected_groups": [...],
    "economic_impact": "..."
  },
  "complexity_assessment": {
    "complexity_score": 0.75,
    "reading_level": "..."
  },
  "generated_at": "2024-01-01T12:00:00",
  "analysis_method": "chunked",
  "chunks_analyzed": 15
}
```

## Alert Generation System

### User Preference Matching
The system matches bills to users based on:

1. **Policy Subscriptions**:
   - User subscriptions to specific policy categories
   - Interest levels (0.0 to 1.0)
   - Notification preferences

2. **Alignment Scoring**:
   - Calculates user-bill alignment scores (-100 to +100)
   - Considers policy category matches
   - Factors in user interest levels

3. **Alert Types**:
   - `policy_match`: Bill matches user's policy interests
   - `alignment`: High positive alignment with user preferences
   - `conflict`: High negative alignment with user preferences
   - `new_bill`: New bill in user's watchlist

### Alert Priority System
- **Critical**: Alignment score > 90 or < -90
- **High**: Alignment score > 70 or < -70
- **Medium**: Alignment score > 50 or < -50
- **Low**: Alignment score > 30 or < -30

## Error Handling

### Robust Error Recovery
- Individual bill failures don't stop the workflow
- Automatic retry mechanisms for transient failures
- Comprehensive error logging with context
- Graceful degradation when services are unavailable

### Error Types Handled
- RSS feed unavailability
- Congress API errors and rate limits
- AI analysis failures and API quota issues
- Database connection issues
- Network timeouts and connectivity problems

## Performance Considerations

### Scalability
- Threaded RSS monitoring and backfill processing
- Asynchronous bill processing
- Database connection pooling
- Efficient query patterns with proper indexing

### Resource Management
- Memory-efficient bill text handling
- Configurable processing intervals
- Automatic cleanup of old data
- Optimized database indexes for common queries

### Rate Limiting
- Respects Congress API rate limits
- Implements exponential backoff for failures
- Configurable processing delays
- Queue-based processing to prevent overwhelming

## Security

### API Security
- Input validation for all parameters
- SQL injection prevention through ORM
- Rate limiting for API endpoints
- Authentication and authorization (for production)

### Data Privacy
- User preference encryption
- Secure API key storage
- Audit logging for data access
- Data retention policies

## Deployment

### Production Considerations

1. **Environment Variables**:
   ```bash
   GEMINI_API_KEY=your_gemini_api_key
   DATABASE_URL=postgresql://user:pass@host/db
   MAIL_SERVER=smtp.gmail.com
   MAIL_PORT=587
   MAIL_USE_TLS=True
   MAIL_USERNAME=your_email@gmail.com
   MAIL_PASSWORD=your_app_password
   ```

2. **Process Management**:
   - Use systemd or supervisor for process management
   - Implement health checks for workflow status
   - Set up monitoring and alerting for system health

3. **Database**:
   - Use PostgreSQL for production
   - Set up regular backups
   - Configure connection pooling
   - Monitor query performance

4. **Logging**:
   - Configure log rotation
   - Set up log aggregation
   - Monitor error rates and patterns

## Troubleshooting

### Common Issues

1. **RSS Feed Errors**:
   - Check feed URLs and network connectivity
   - Verify feed format and accessibility
   - Check for rate limiting from Congress.gov

2. **AI Analysis Failures**:
   - Verify Gemini API key and quota
   - Check API response formats
   - Monitor for content length limits

3. **Database Errors**:
   - Check connection and permissions
   - Verify schema migrations
   - Monitor for deadlocks and timeouts

4. **Alert Generation Issues**:
   - Check user preference data
   - Verify policy category mappings
   - Monitor for duplicate alert prevention

### Debug Mode
Enable debug logging by setting log level to DEBUG:

```python
logging.getLogger('services.workflow_orchestrator').setLevel(logging.DEBUG)
```

## Future Enhancements

### Planned Features
- Webhook support for real-time notifications
- Advanced bill comparison and tracking
- Machine learning for user preference learning
- Integration with external legislative databases
- Mobile app notifications
- Advanced analytics and reporting

### Scalability Improvements
- Microservices architecture
- Message queue integration (Redis/RabbitMQ)
- Distributed processing with Celery
- Cloud-native deployment with Kubernetes
- Horizontal scaling for high-volume processing

## Support

For issues and questions:
1. Check the logs in `logs/workflow.log`
2. Review the API documentation
3. Test individual components
4. Monitor system resources and performance

The workflow system is designed to be robust, scalable, and maintainable, providing a solid foundation for automated legislative analysis and user engagement with clear focus on the two primary goals: AI analysis storage and user alert generation. 