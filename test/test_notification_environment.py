#!/usr/bin/env python3
"""
Test notification environment controls
"""

import sys
import os
import logging

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_notification_environment_controls():
    """Test that notifications are properly controlled by environment variables"""
    
    # Test 1: Development environment (should enable notifications)
    logger.info("🧪 Test 1: Development environment")
    os.environ['FLASK_ENV'] = 'development'
    os.environ.pop('NOTIFICATIONS_ENABLED', None)  # Remove if exists
    
    from services.notification_service import NotificationService
    from services.notification_helper import _should_enable_notifications
    
    service = NotificationService()
    helper_enabled = _should_enable_notifications()
    
    logger.info(f"   NotificationService enabled: {service.notifications_enabled}")
    logger.info(f"   Helper function enabled: {helper_enabled}")
    
    assert service.notifications_enabled == True, "Development should enable notifications"
    assert helper_enabled == True, "Helper should enable notifications in development"
    
    # Test 2: Production environment with notifications disabled (default)
    logger.info("🧪 Test 2: Production environment (disabled)")
    os.environ['FLASK_ENV'] = 'production'
    os.environ['NOTIFICATIONS_ENABLED'] = 'false'
    
    # Need to reimport to get fresh environment check
    import importlib
    import services.notification_service
    import services.notification_helper
    importlib.reload(services.notification_service)
    importlib.reload(services.notification_helper)
    
    from services.notification_service import NotificationService
    from services.notification_helper import _should_enable_notifications
    
    service = NotificationService()
    helper_enabled = _should_enable_notifications()
    
    logger.info(f"   NotificationService enabled: {service.notifications_enabled}")
    logger.info(f"   Helper function enabled: {helper_enabled}")
    
    assert service.notifications_enabled == False, "Production should disable notifications by default"
    assert helper_enabled == False, "Helper should disable notifications in production"
    
    # Test 3: Production environment with notifications explicitly enabled
    logger.info("🧪 Test 3: Production environment (explicitly enabled)")
    os.environ['FLASK_ENV'] = 'production'
    os.environ['NOTIFICATIONS_ENABLED'] = 'true'
    
    # Reload modules again
    importlib.reload(services.notification_service)
    importlib.reload(services.notification_helper)
    
    from services.notification_service import NotificationService
    from services.notification_helper import _should_enable_notifications
    
    service = NotificationService()
    helper_enabled = _should_enable_notifications()
    
    logger.info(f"   NotificationService enabled: {service.notifications_enabled}")
    logger.info(f"   Helper function enabled: {helper_enabled}")
    
    assert service.notifications_enabled == True, "Production with NOTIFICATIONS_ENABLED=true should enable notifications"
    assert helper_enabled == True, "Helper should enable notifications when explicitly enabled"
    
    # Test 4: Test notification service methods with disabled notifications
    logger.info("🧪 Test 4: Disabled notification service methods")
    os.environ['FLASK_ENV'] = 'production'
    os.environ['NOTIFICATIONS_ENABLED'] = 'false'
    
    # Reload modules
    importlib.reload(services.notification_service)
    importlib.reload(services.notification_helper)
    
    from services.notification_service import NotificationService
    from services.notification_helper import trigger_bill_analysis_notification
    
    service = NotificationService()
    
    # These should return early and not process anything
    logger.info("   Testing process_new_bill_analysis (should skip)")
    service.process_new_bill_analysis(999)  # Non-existent bill ID
    
    logger.info("   Testing send_pending_notifications (should skip)")
    service.send_pending_notifications()
    
    logger.info("   Testing trigger_bill_analysis_notification (should skip)")
    trigger_bill_analysis_notification(999)
    
    logger.info("✅ All tests passed! Notification environment controls are working correctly.")
    
    # Restore development environment
    os.environ['FLASK_ENV'] = 'development'
    os.environ.pop('NOTIFICATIONS_ENABLED', None)
    
    return True

if __name__ == "__main__":
    try:
        test_notification_environment_controls()
        print("\n🎉 All notification environment tests passed!")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)