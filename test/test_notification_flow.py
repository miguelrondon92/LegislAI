#!/usr/bin/env python3
"""
Test script to verify the complete notification flow works end-to-end.
This tests the entire pipeline from bill analysis to user notifications.
"""

import sys
import os
import logging
from datetime import datetime

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

def test_notification_flow():
    """Test the complete notification flow"""
    try:
        # Import with app context
        from app import app, db
        from db_models import User, Bill, PolicyCategory, UserPolicySubscription, Alert, BillCategoryMapping
        from services.notification_service import NotificationService
        from services.notification_helper import trigger_bill_analysis_notification
        
        with app.app_context():
            logger.info("🧪 Starting notification flow test...")
            
            # Step 1: Create test user with policy subscriptions
            logger.info("📝 Step 1: Creating test user and policy subscriptions")
            
            # Check if test user already exists
            test_user = User.query.filter_by(email='test_notifications@example.com').first()
            if not test_user:
                test_user = User(
                    username='test_notification_user',
                    email='test_notifications@example.com',
                    first_name='Test',
                    last_name='User',
                    alert_enabled=True,
                    alert_frequency='daily'
                )
                test_user.set_password('testpassword123')
                db.session.add(test_user)
                db.session.commit()
                logger.info(f"✅ Created test user: {test_user.username}")
            else:
                logger.info(f"✅ Using existing test user: {test_user.username}")
            
            # Create test policy category
            test_category = PolicyCategory.query.filter_by(name='test_healthcare').first()
            if not test_category:
                test_category = PolicyCategory(
                    name='test_healthcare',
                    display_name='Test Healthcare',
                    description='Test healthcare policy category for notifications',
                    color='#00aa44',
                    icon='heart',
                    is_active=True
                )
                db.session.add(test_category)
                db.session.commit()
                logger.info(f"✅ Created test policy category: {test_category.name}")
            else:
                logger.info(f"✅ Using existing test policy category: {test_category.name}")
            
            # Subscribe user to policy category
            existing_subscription = UserPolicySubscription.query.filter_by(
                user_id=test_user.id,
                policy_category_id=test_category.id
            ).first()
            
            if not existing_subscription:
                subscription = UserPolicySubscription(
                    user_id=test_user.id,
                    policy_category_id=test_category.id,
                    interest_level=0.8,  # High interest
                    notification_enabled=True,
                    email_notifications=True,
                    in_app_notifications=True
                )
                db.session.add(subscription)
                db.session.commit()
                logger.info(f"✅ Created policy subscription: interest level {subscription.interest_level}")
            else:
                logger.info(f"✅ Using existing policy subscription: interest level {existing_subscription.interest_level}")
            
            # Step 2: Create test bill
            logger.info("📄 Step 2: Creating test bill")
            
            test_bill = Bill.query.filter_by(
                congress=119,
                bill_type='hr',
                bill_number=99999
            ).first()
            
            if not test_bill:
                test_bill = Bill(
                    congress=119,
                    bill_type='hr',
                    bill_number=99999,
                    title='Test Healthcare Reform Act - Notification Test',
                    summary='A test bill to verify notification functionality for healthcare policy changes.',
                    introduced_date=datetime.utcnow(),
                    last_action_date=datetime.utcnow(),
                    status='Introduced',
                    sponsor_name='Test Sponsor',
                    sponsor_party='Independent',
                    sponsor_state='TS',
                    display_ready=True,
                    active=True
                )
                db.session.add(test_bill)
                db.session.commit()
                logger.info(f"✅ Created test bill: {test_bill.get_bill_identifier()}")
            else:
                logger.info(f"✅ Using existing test bill: {test_bill.get_bill_identifier()}")
            
            # Step 3: Create bill category mapping
            logger.info("🔗 Step 3: Creating bill category mapping")
            
            existing_mapping = BillCategoryMapping.query.filter_by(
                bill_id=test_bill.id,
                policy_category_id=test_category.id
            ).first()
            
            if not existing_mapping:
                mapping = BillCategoryMapping(
                    bill_id=test_bill.id,
                    policy_category_id=test_category.id,
                    relevance_score=0.9,  # High relevance
                    sneakiness_score=0.0,
                    category_specific_analysis='{"analysis": "Test healthcare bill for notifications"}'
                )
                db.session.add(mapping)
                db.session.commit()
                logger.info(f"✅ Created bill category mapping: relevance {mapping.relevance_score}")
            else:
                logger.info(f"✅ Using existing bill category mapping: relevance {existing_mapping.relevance_score}")
            
            # Step 4: Count existing alerts
            logger.info("📊 Step 4: Checking initial alert state")
            
            initial_alert_count = Alert.query.filter_by(user_id=test_user.id).count()
            logger.info(f"📈 Initial alert count for user: {initial_alert_count}")
            
            # Step 5: Test notification trigger
            logger.info("🚀 Step 5: Testing notification trigger")
            
            notification_service = NotificationService()
            notification_service.process_new_bill_analysis(test_bill.id)
            
            # Check if new alerts were created
            final_alert_count = Alert.query.filter_by(user_id=test_user.id).count()
            new_alerts = final_alert_count - initial_alert_count
            
            logger.info(f"📈 Final alert count for user: {final_alert_count}")
            logger.info(f"🆕 New alerts created: {new_alerts}")
            
            # Step 6: Test notification helper
            logger.info("🔧 Step 6: Testing notification helper")
            
            try:
                trigger_bill_analysis_notification(test_bill.id)
                logger.info("✅ Notification helper executed successfully")
            except Exception as e:
                logger.error(f"❌ Notification helper failed: {e}")
                return False
            
            # Step 7: Verify alert content
            logger.info("🔍 Step 7: Verifying alert content")
            
            latest_alerts = Alert.query.filter_by(
                user_id=test_user.id,
                bill_id=test_bill.id
            ).order_by(Alert.created_at.desc()).limit(3).all()
            
            if latest_alerts:
                for i, alert in enumerate(latest_alerts):
                    logger.info(f"📬 Alert {i+1}:")
                    logger.info(f"   Type: {alert.alert_type}")
                    logger.info(f"   Title: {alert.title}")
                    logger.info(f"   Priority: {alert.priority}")
                    logger.info(f"   Created: {alert.created_at}")
                    logger.info(f"   Message preview: {alert.message[:100]}...")
            else:
                logger.warning("⚠️ No alerts found for test user and bill")
                return False
            
            # Step 8: Test should_notify_user logic
            logger.info("🤔 Step 8: Testing notification logic")
            
            should_notify = notification_service._should_notify_user(test_user, test_bill)
            logger.info(f"🎯 Should notify user: {should_notify}")
            
            if should_notify:
                relevant_categories = notification_service._get_relevant_categories_for_user(test_user, test_bill)
                category_names = [cat.display_name for cat in relevant_categories]
                logger.info(f"📂 Relevant categories: {category_names}")
                
                max_interest = notification_service._get_user_max_interest_for_bill(test_user, test_bill)
                logger.info(f"💯 User's max interest level: {max_interest}")
            
            # Step 9: Summary
            logger.info("📋 Step 9: Test Summary")
            logger.info("=" * 60)
            logger.info(f"✅ User created/verified: {test_user.username}")
            logger.info(f"✅ Policy category: {test_category.display_name}")
            logger.info(f"✅ Test bill: {test_bill.get_bill_identifier()}")
            logger.info(f"✅ Bill category mapping: relevance {existing_mapping.relevance_score if existing_mapping else mapping.relevance_score}")
            logger.info(f"✅ User subscription: interest {existing_subscription.interest_level if existing_subscription else subscription.interest_level}")
            logger.info(f"✅ Notification logic works: {should_notify}")
            logger.info(f"✅ Alerts generated: {new_alerts}")
            logger.info(f"✅ Latest alerts: {len(latest_alerts)}")
            
            if should_notify and new_alerts > 0 and latest_alerts:
                logger.info("🎉 NOTIFICATION FLOW TEST PASSED! 🎉")
                return True
            else:
                logger.warning("⚠️ Some notification components may not be working correctly")
                return False
                
    except Exception as e:
        logger.error(f"❌ Notification flow test failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False

def test_watchlist_notifications():
    """Test watchlist-based notifications"""
    try:
        from app import app, db
        from db_models import User, Bill, WatchlistItem, Alert
        from services.notification_service import NotificationService
        
        with app.app_context():
            logger.info("👀 Testing watchlist notifications...")
            
            # Get test user
            test_user = User.query.filter_by(email='test_notifications@example.com').first()
            if not test_user:
                logger.error("Test user not found. Run main test first.")
                return False
                
            # Get test bill
            test_bill = Bill.query.filter_by(congress=119, bill_type='hr', bill_number=99999).first()
            if not test_bill:
                logger.error("Test bill not found. Run main test first.")
                return False
            
            # Add bill to watchlist
            existing_watchlist = WatchlistItem.query.filter_by(
                user_id=test_user.id,
                bill_id=test_bill.id
            ).first()
            
            if not existing_watchlist:
                watchlist_item = WatchlistItem(
                    user_id=test_user.id,
                    bill_id=test_bill.id,
                    keywords='healthcare, reform',
                    policy_area='healthcare'
                )
                db.session.add(watchlist_item)
                db.session.commit()
                logger.info("✅ Added bill to user's watchlist")
            else:
                logger.info("✅ Bill already in user's watchlist")
            
            # Test notification logic
            notification_service = NotificationService()
            should_notify = notification_service._should_notify_user(test_user, test_bill)
            
            logger.info(f"👀 Watchlist notification check: {should_notify}")
            
            if should_notify:
                logger.info("🎉 WATCHLIST NOTIFICATION TEST PASSED! 🎉")
                return True
            else:
                logger.warning("⚠️ Watchlist notification not working correctly")
                return False
                
    except Exception as e:
        logger.error(f"❌ Watchlist notification test failed: {e}")
        return False

if __name__ == "__main__":
    logger.info("🚀 Starting LegislAI Notification System Tests")
    logger.info("=" * 80)
    
    # Test main notification flow
    main_test_passed = test_notification_flow()
    
    logger.info("\n" + "=" * 80)
    
    # Test watchlist notifications
    watchlist_test_passed = test_watchlist_notifications()
    
    logger.info("\n" + "=" * 80)
    logger.info("📊 FINAL RESULTS:")
    logger.info(f"   Main notification flow: {'✅ PASSED' if main_test_passed else '❌ FAILED'}")
    logger.info(f"   Watchlist notifications: {'✅ PASSED' if watchlist_test_passed else '❌ FAILED'}")
    
    if main_test_passed and watchlist_test_passed:
        logger.info("🎉 ALL NOTIFICATION TESTS PASSED! 🎉")
        logger.info("🔔 Users will now be notified when bills matching their interests are analyzed!")
        sys.exit(0)
    else:
        logger.error("❌ Some notification tests failed. Check the logs above for details.")
        sys.exit(1)