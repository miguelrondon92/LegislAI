# Notification Environment Controls

## Overview

The LegislAI notification system now includes environment-based controls to prevent notifications from being sent in production environments unless explicitly enabled.

## Environment Behavior

### Development Environment
- **FLASK_ENV=development** - Notifications are **always enabled**
- No additional configuration needed
- All notification features work as expected

### Production Environment
- **FLASK_ENV=production** - Notifications are **disabled by default**
- Must explicitly set `NOTIFICATIONS_ENABLED=true` to enable notifications
- Provides safety net to prevent accidental email sending in production

### Configuration Variables

| Variable | Values | Default | Description |
|----------|--------|---------|-------------|
| `FLASK_ENV` | `development`, `production` | `production` | Flask environment mode |
| `NOTIFICATIONS_ENABLED` | `true`, `false` | `false` | Explicit notification control |

## Notification Logic

```python
def _should_enable_notifications():
    flask_env = os.environ.get('FLASK_ENV', 'production').lower()
    notifications_enabled = os.environ.get('NOTIFICATIONS_ENABLED', 'false').lower() == 'true'
    
    # Enable notifications in development or if explicitly enabled
    if flask_env == 'development':
        return True
    elif notifications_enabled:
        return True
    else:
        return False
```

## Components Protected

### 1. NotificationService
- `process_new_bill_analysis()` - Skips processing if disabled
- `send_pending_notifications()` - Skips email delivery if disabled

### 2. NotificationScheduler
- `start()` - Prevents scheduler from starting if disabled
- Background notification jobs won't run

### 3. NotificationHelper
- `trigger_bill_analysis_notification()` - Early return if disabled
- `trigger_high_risk_bill_notification()` - Early return if disabled
- `trigger_bill_analysis_notification_async()` - Skips async processing

## Production Setup

### To Keep Notifications Disabled (Recommended)
```bash
# In production .env file
FLASK_ENV=production
NOTIFICATIONS_ENABLED=false  # or omit entirely
```

### To Enable Notifications in Production
```bash
# In production .env file
FLASK_ENV=production
NOTIFICATIONS_ENABLED=true
```

## Development Setup

```bash
# In development .env file
FLASK_ENV=development
# NOTIFICATIONS_ENABLED not needed - auto-enabled
```

## Logging

When notifications are disabled, the system logs:
- `"Notifications disabled in production environment"`
- `"Notifications disabled - skipping bill {bill_id}"`
- `"Notifications disabled - skipping email delivery"`
- `"Notification scheduler start skipped - notifications disabled"`

## Testing

Run the test suite to verify environment controls:

```bash
python test/test_notification_environment_simple.py
```

## Benefits

1. **Production Safety** - Prevents accidental email sending
2. **Development Flexibility** - Full notification testing in development
3. **Explicit Control** - Clear, intentional notification enabling in production
4. **Logging Visibility** - Clear logs when notifications are disabled
5. **Graceful Degradation** - System continues to work without notifications

## Future Considerations

- Add notification queue for production (store but don't send)
- Add notification preview/testing endpoints
- Add per-user notification disable controls
- Add notification rate limiting for production