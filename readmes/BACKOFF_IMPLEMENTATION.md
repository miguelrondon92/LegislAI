# Backoff Logic Implementation for Rate Limit Handling

## Overview

The workflow system now includes comprehensive backoff logic to handle 429 (rate limit) errors from the Gemini API gracefully. This prevents the system from overwhelming the API and ensures sustainable operation.

## Key Features

### 1. Exponential Backoff with Jitter
- **Base delay**: 1 second
- **Maximum delay**: 60 seconds
- **Backoff multiplier**: 2x (exponential)
- **Jitter factor**: 10% (prevents thundering herd)
- **Maximum retries**: 3 attempts

### 2. Workflow-Level Rate Limit Management
- **Automatic pause**: 15-minute pause when rate limit is hit
- **Smart resumption**: Automatically resumes when pause expires
- **Bill skipping**: Skips bills during pause periods
- **Retry logic**: Bills are retried in next backfill cycle

### 3. Enhanced Logging
- Clear indication when rate limits are hit
- Progress tracking during backoff delays
- Pause/resume notifications
- Detailed error context

## Implementation Details

### Enhanced AI Analyzer (`services/enhanced_ai_analyzer.py`)

```python
class EnhancedAIAnalyzer:
    def __init__(self):
        # Backoff configuration
        self.max_retries = 3
        self.base_delay = 1.0
        self.max_delay = 60.0
        self.backoff_multiplier = 2.0
        self.jitter_factor = 0.1
```

**Key Methods:**
- `_call_ai_model()`: Implements retry logic with exponential backoff
- `_calculate_backoff_delay()`: Calculates delay with jitter

### Workflow Orchestrator (`services/workflow_orchestrator.py`)

**Rate Limit Tracking:**
```python
self.stats = {
    'rate_limit_hits': 0,
    'last_rate_limit_time': None,
    'rate_limit_pause_until': None,
}
```

**Pause Logic:**
- Automatically pauses AI analysis for 15 minutes when rate limit is hit
- Skips bills during pause periods
- Resumes automatically when pause expires

## How It Works

### 1. Rate Limit Detection
When a 429 error occurs:
1. **Immediate retry**: Attempts up to 3 retries with exponential backoff
2. **Pause activation**: If all retries fail, activates 15-minute pause
3. **Bill skipping**: Subsequent bills are skipped until pause expires

### 2. Backoff Sequence
```
Attempt 1: 1.0s delay (base)
Attempt 2: 2.0s delay (2x)
Attempt 3: 4.0s delay (4x)
Attempt 4: 8.0s delay (8x, but capped at 60s)
```

### 3. Jitter Addition
Each delay includes ±10% random jitter to prevent synchronized retries.

### 4. Workflow Pause
- **Duration**: 15 minutes
- **Scope**: All AI analysis operations
- **Automatic**: No manual intervention required
- **Resume**: Automatic when time expires

## Benefits

### 1. API Respect
- Prevents overwhelming the Gemini API
- Maintains good standing with API provider
- Reduces risk of account suspension

### 2. System Stability
- Prevents infinite retry loops
- Maintains workflow operation during rate limits
- Graceful degradation of functionality

### 3. User Experience
- Clear logging of what's happening
- Predictable behavior during rate limits
- Automatic recovery without manual intervention

### 4. Cost Management
- Reduces unnecessary API calls during rate limits
- Prevents wasted processing time
- Optimizes resource usage

## Monitoring

### Status Information
The workflow status now includes rate limiting information:

```json
{
  "rate_limiting": {
    "rate_limit_hits": 2,
    "last_rate_limit_time": "2024-01-15T10:30:00",
    "rate_limit_pause_until": "2024-01-15T10:45:00",
    "is_paused": true
  }
}
```

### Log Messages
- `⚠️ Rate limited (429). Attempt X/Y. Waiting Z seconds...`
- `⏸️ Pausing AI analysis until HH:MM:SS to respect rate limits`
- `✅ Rate limit pause expired, resuming AI analysis`
- `📋 Bill will be retried in next backfill cycle when API quota resets`

## Configuration

### Adjustable Parameters
```python
# In EnhancedAIAnalyzer
self.max_retries = 3          # Number of retry attempts
self.base_delay = 1.0         # Initial delay in seconds
self.max_delay = 60.0         # Maximum delay in seconds
self.backoff_multiplier = 2.0 # Exponential multiplier
self.jitter_factor = 0.1      # Jitter percentage

# In WorkflowOrchestrator
pause_duration = timedelta(minutes=15)  # Pause duration
```

### Production Recommendations
- **Conservative settings**: Use longer delays in production
- **Monitor usage**: Track rate limit frequency
- **Adjust quotas**: Consider upgrading API quota if needed
- **Load balancing**: Distribute processing across time periods

## Testing

### Test Script
Run `test_backoff_logic.py` to verify:
- Rate limit pause logic
- Backoff delay calculations
- Workflow behavior during pauses
- Automatic resumption

### Expected Behavior
1. **During rate limits**: Bills are skipped with informative logs
2. **After pause expires**: Normal processing resumes
3. **Retry cycles**: Bills are retried in subsequent backfill runs
4. **No data loss**: All bills remain in queue for future processing

## Future Enhancements

### Potential Improvements
1. **Adaptive backoff**: Adjust delays based on rate limit frequency
2. **Quota monitoring**: Track API usage and predict rate limits
3. **Distributed processing**: Spread analysis across multiple time periods
4. **Priority queuing**: Process high-priority bills first when quota is limited
5. **Alternative APIs**: Fallback to different AI providers during rate limits

## Conclusion

The backoff logic implementation provides robust handling of rate limit errors while maintaining system stability and user experience. The system now gracefully handles API limitations without overwhelming the service or losing bill processing opportunities. 