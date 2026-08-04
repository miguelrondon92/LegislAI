#!/usr/bin/env python3
"""
Simple test for notification environment controls
"""

import os
import sys

def test_notification_helper_environment():
    """Test notification helper environment detection"""
    
    # Add the project root to the path
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    print("🧪 Testing notification environment controls...")
    
    # Test 1: Development environment
    print("\n📍 Test 1: Development environment")
    os.environ['FLASK_ENV'] = 'development'
    os.environ.pop('NOTIFICATIONS_ENABLED', None)  # Remove if exists
    
    from services.notification_helper import _should_enable_notifications
    
    enabled = _should_enable_notifications()
    print(f"   Result: {enabled}")
    assert enabled == True, "Development should enable notifications"
    
    # Test 2: Production environment (disabled by default)
    print("\n📍 Test 2: Production environment (disabled)")
    os.environ['FLASK_ENV'] = 'production'
    os.environ['NOTIFICATIONS_ENABLED'] = 'false'
    
    enabled = _should_enable_notifications()
    print(f"   Result: {enabled}")
    assert enabled == False, "Production should disable notifications by default"
    
    # Test 3: Production environment (explicitly enabled)
    print("\n📍 Test 3: Production environment (explicitly enabled)")
    os.environ['FLASK_ENV'] = 'production'
    os.environ['NOTIFICATIONS_ENABLED'] = 'true'
    
    enabled = _should_enable_notifications()
    print(f"   Result: {enabled}")
    assert enabled == True, "Production with NOTIFICATIONS_ENABLED=true should enable notifications"
    
    # Test 4: Unknown environment (should default to production behavior)
    print("\n📍 Test 4: Unknown environment")
    os.environ['FLASK_ENV'] = 'staging'
    os.environ['NOTIFICATIONS_ENABLED'] = 'false'
    
    enabled = _should_enable_notifications()
    print(f"   Result: {enabled}")
    assert enabled == False, "Unknown environment should default to disabled"
    
    print("\n✅ All notification environment tests passed!")
    
    # Restore development environment
    os.environ['FLASK_ENV'] = 'development'
    os.environ.pop('NOTIFICATIONS_ENABLED', None)
    
    return True

if __name__ == "__main__":
    try:
        test_notification_helper_environment()
        print("\n🎉 Notification environment controls are working correctly!")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)