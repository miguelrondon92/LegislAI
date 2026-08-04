#!/usr/bin/env python3
"""
Test script to send a notification to the dev user 'mig ron' and debug the process.
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

def find_dev_user():
    """Find the dev user 'mig ron'"""
    try:
        from app import app, db
        from db_models import User
        
        with app.app_context():
            logger.info("🔍 Searching for dev user 'mig ron'...")
            
            # Search for users that might match "mig ron"
            possible_users = User.query.filter(
                User.username.like('%mig%') | 
                User.first_name.like('%mig%') | 
                User.last_name.like('%ron%') |
                User.email.like('%mig%')
            ).all()
            
            logger.info(f"📋 Found {len(possible_users)} possible matches:")
            
            for user in possible_users:
                logger.info(f"   👤 User ID {user.id}:")
                logger.info(f"      Username: {user.username}")
                logger.info(f"      Name: {user.first_name} {user.last_name}")
                logger.info(f"      Email: {user.email}")
                logger.info(f"      Alerts enabled: {user.alert_enabled}")
                logger.info(f"      Alert frequency: {user.alert_frequency}")
                logger.info(f"      Created: {user.created_at}")
                logger.info("")
            
            # If no matches, show all users for debugging
            if not possible_users:
                logger.info("❌ No users found matching 'mig ron', showing all users:")
                all_users = User.query.all()
                for user in all_users:
                    logger.info(f"   👤 User ID {user.id}: {user.username} ({user.first_name} {user.last_name}) - {user.email}")
            
            return possible_users
            
    except Exception as e:
        logger.error(f"❌ Error finding dev user: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return []

def check_user_subscriptions(user):
    """Check what policy subscriptions the user has"""
    try:
        from app import app, db
        from db_models import UserPolicySubscription, PolicyCategory
        
        with app.app_context():
            logger.info(f"🔍 Checking policy subscriptions for user {user.username}...")
            
            subscriptions = UserPolicySubscription.query.filter_by(user_id=user.id).all()
            
            logger.info(f"📊 Found {len(subscriptions)} policy subscriptions:")
            
            for sub in subscriptions:
                category = PolicyCategory.query.get(sub.policy_category_id)
                logger.info(f"   📂 {category.display_name if category else 'Unknown Category'}")
                logger.info(f"      Interest level: {sub.interest_level}")
                logger.info(f"      Notifications enabled: {sub.notification_enabled}")
                logger.info(f"      Email notifications: {sub.email_notifications}")
                logger.info("")
            
            return subscriptions
            
    except Exception as e:
        logger.error(f"❌ Error checking user subscriptions: {e}")
        return []

def check_user_watchlist(user):
    """Check what bills the user has in their watchlist"""
    try:
        from app import app, db
        from db_models import WatchlistItem, Bill
        
        with app.app_context():
            logger.info(f"👀 Checking watchlist for user {user.username}...")
            
            watchlist_items = WatchlistItem.query.filter_by(user_id=user.id).all()
            
            logger.info(f"📋 Found {len(watchlist_items)} watchlist items:")
            
            for item in watchlist_items:
                bill = Bill.query.get(item.bill_id)
                if bill:
                    logger.info(f"   📄 {bill.get_bill_identifier()}: {bill.title[:60]}...")
                    logger.info(f"      Keywords: {item.keywords}")
                    logger.info(f"      Policy area: {item.policy_area}")
                    logger.info("")
            
            return watchlist_items
            
    except Exception as e:
        logger.error(f"❌ Error checking user watchlist: {e}")
        return []

def create_test_bill_for_user(user):
    """Create or find a test bill that should trigger notifications for this user"""
    try:
        from app import app, db
        from db_models import Bill, PolicyCategory, BillCategoryMapping, UserPolicySubscription
        
        with app.app_context():
            logger.info(f"📄 Creating test bill for user {user.username}...")
            
            # Get user's subscriptions to create a relevant bill
            subscriptions = UserPolicySubscription.query.filter_by(
                user_id=user.id,
                notification_enabled=True
            ).all()
            
            if not subscriptions:
                logger.info("📝 User has no active subscriptions, creating a default healthcare subscription...")
                
                # Create or find healthcare category
                healthcare_category = PolicyCategory.query.filter_by(name='healthcare').first()
                if not healthcare_category:
                    healthcare_category = PolicyCategory(
                        name='healthcare',
                        display_name='Healthcare',
                        description='Healthcare policy and medical legislation',
                        color='#00aa44',
                        icon='heart',
                        is_active=True
                    )
                    db.session.add(healthcare_category)
                    db.session.commit()
                
                # Create subscription
                subscription = UserPolicySubscription(
                    user_id=user.id,
                    policy_category_id=healthcare_category.id,
                    interest_level=0.8,
                    notification_enabled=True,
                    email_notifications=True,
                    in_app_notifications=True
                )
                db.session.add(subscription)
                db.session.commit()
                
                subscriptions = [subscription]
                logger.info(f"✅ Created healthcare subscription with interest level {subscription.interest_level}")
            
            # Create test bill
            test_bill = Bill(
                congress=119,
                bill_type='hr',
                bill_number=88888,
                title=f'Test Notification Bill for {user.username} - Healthcare Reform',
                summary='A test bill created specifically to test notifications for the dev user. This bill addresses healthcare reform and medical policy changes.',
                introduced_date=datetime.utcnow(),
                last_action_date=datetime.utcnow(),
                status='Introduced',
                sponsor_name='Dev Test Sponsor',
                sponsor_party='Independent',
                sponsor_state='DV',
                display_ready=True,
                active=True
            )
            db.session.add(test_bill)
            db.session.commit()
            
            logger.info(f"✅ Created test bill: {test_bill.get_bill_identifier()}")
            
            # Create category mapping for the bill
            subscription = subscriptions[0]  # Use first subscription
            category = PolicyCategory.query.get(subscription.policy_category_id)
            
            mapping = BillCategoryMapping(
                bill_id=test_bill.id,
                policy_category_id=category.id,
                relevance_score=0.9,  # High relevance
                sneakiness_score=0.0,
                category_specific_analysis=f'{{"analysis": "Test bill for {user.username} notification testing"}}'
            )
            db.session.add(mapping)
            db.session.commit()
            
            logger.info(f"✅ Created category mapping: {category.display_name} (relevance: {mapping.relevance_score})")
            
            return test_bill
            
    except Exception as e:
        logger.error(f"❌ Error creating test bill: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None

def send_notification_to_user(user, bill):
    """Send a notification to the user about the bill"""
    try:
        from app import app, db
        from db_models import Alert
        from services.notification_service import NotificationService
        from services.notification_helper import trigger_bill_analysis_notification
        
        with app.app_context():
            logger.info(f"🚀 Sending notification to user {user.username}...")
            
            # Count existing alerts
            initial_alerts = Alert.query.filter_by(user_id=user.id).count()
            logger.info(f"📊 Initial alert count: {initial_alerts}")
            
            # Method 1: Use notification service directly
            logger.info("📡 Method 1: Using NotificationService directly...")
            notification_service = NotificationService()
            
            # Check if user should be notified
            should_notify = notification_service._should_notify_user(user, bill)
            logger.info(f"🎯 Should notify user: {should_notify}")
            
            if should_notify:
                notification_service.process_new_bill_analysis(bill.id)
                logger.info("✅ NotificationService.process_new_bill_analysis() completed")
            else:
                logger.warning("⚠️ NotificationService says user should NOT be notified")
                
                # Debug why not
                logger.info("🔍 Debugging notification logic...")
                
                # Check watchlist
                from db_models import WatchlistItem
                watchlist_match = WatchlistItem.query.filter_by(user_id=user.id, bill_id=bill.id).first()
                logger.info(f"   👀 Watchlist match: {bool(watchlist_match)}")
                
                # Check policy subscriptions
                from db_models import UserPolicySubscription, BillCategoryMapping
                user_subs = UserPolicySubscription.query.filter_by(user_id=user.id, notification_enabled=True).all()
                bill_cats = BillCategoryMapping.query.filter_by(bill_id=bill.id).all()
                
                logger.info(f"   📂 User subscriptions: {len(user_subs)}")
                logger.info(f"   🔗 Bill categories: {len(bill_cats)}")
                
                for sub in user_subs:
                    for bill_cat in bill_cats:
                        if sub.policy_category_id == bill_cat.policy_category_id:
                            logger.info(f"   ✅ Category match found! Interest: {sub.interest_level}, Relevance: {bill_cat.relevance_score}")
                            if sub.interest_level >= 0.5 and bill_cat.relevance_score >= 0.6:
                                logger.info(f"   ✅ Thresholds met!")
                            else:
                                logger.info(f"   ❌ Thresholds not met (need interest>=0.5 and relevance>=0.6)")
            
            # Method 2: Use notification helper
            logger.info("📡 Method 2: Using notification helper...")
            try:
                trigger_bill_analysis_notification(bill.id)
                logger.info("✅ trigger_bill_analysis_notification() completed")
            except Exception as e:
                logger.error(f"❌ Notification helper failed: {e}")
            
            # Check final alert count
            final_alerts = Alert.query.filter_by(user_id=user.id).count()
            new_alerts = final_alerts - initial_alerts
            logger.info(f"📊 Final alert count: {final_alerts}")
            logger.info(f"🆕 New alerts created: {new_alerts}")
            
            # Show latest alerts
            if new_alerts > 0:
                latest_alerts = Alert.query.filter_by(user_id=user.id).order_by(Alert.created_at.desc()).limit(new_alerts).all()
                logger.info(f"📬 Latest alerts created:")
                for i, alert in enumerate(latest_alerts):
                    logger.info(f"   Alert {i+1}:")
                    logger.info(f"      Title: {alert.title}")
                    logger.info(f"      Type: {alert.alert_type}")
                    logger.info(f"      Priority: {alert.priority}")
                    logger.info(f"      Created: {alert.created_at}")
                    logger.info(f"      Message: {alert.message[:200]}...")
                    logger.info("")
            
            return new_alerts > 0
            
    except Exception as e:
        logger.error(f"❌ Error sending notification: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False

def test_email_sending(user):
    """Test if email sending is configured correctly"""
    try:
        from app import app, mail
        from flask_mail import Message
        import os
        
        with app.app_context():
            logger.info(f"📧 Testing email configuration for user {user.email}...")
            
            # Check email configuration
            logger.info("⚙️ Email configuration:")
            logger.info(f"   MAIL_SERVER: {app.config.get('MAIL_SERVER', 'Not set')}")
            logger.info(f"   MAIL_PORT: {app.config.get('MAIL_PORT', 'Not set')}")
            logger.info(f"   MAIL_USERNAME: {app.config.get('MAIL_USERNAME', 'Not set')}")
            logger.info(f"   MAIL_USE_TLS: {app.config.get('MAIL_USE_TLS', 'Not set')}")
            logger.info(f"   MAIL_USE_SSL: {app.config.get('MAIL_USE_SSL', 'Not set')}")
            
            # Check environment variables
            logger.info("🌍 Environment variables:")
            for var in ['MAIL_SERVER', 'MAIL_PORT', 'MAIL_USERNAME', 'MAIL_PASSWORD']:
                value = os.environ.get(var, 'Not set')
                # Don't log the actual password
                if var == 'MAIL_PASSWORD':
                    value = '***Set***' if value != 'Not set' else 'Not set'
                logger.info(f"   {var}: {value}")
            
            # Try to send a test email
            if app.config.get('MAIL_SERVER'):
                logger.info("📤 Attempting to send test email...")
                
                msg = Message(
                    subject="LegislAI Notification Test",
                    recipients=[user.email],
                    body=f"""
Hello {user.get_full_name()},

This is a test email to verify that notifications are working correctly in LegislAI.

If you receive this email, the notification system is successfully configured!

Best regards,
LegislAI Development Team
                    """,
                    sender=os.environ.get('MAIL_DEFAULT_SENDER', 'noreply@legislai.com')
                )
                
                try:
                    mail.send(msg)
                    logger.info("✅ Test email sent successfully!")
                    return True
                except Exception as e:
                    logger.error(f"❌ Failed to send test email: {e}")
                    return False
            else:
                logger.warning("⚠️ Email not configured - skipping email test")
                return None
                
    except Exception as e:
        logger.error(f"❌ Error testing email: {e}")
        return False

def main():
    """Main test function"""
    logger.info("🚀 Starting dev user notification test")
    logger.info("=" * 80)
    
    # Step 1: Find dev user
    users = find_dev_user()
    
    if not users:
        logger.error("❌ No dev user found matching 'mig ron'")
        return False
    
    # Use the first matching user
    dev_user = users[0]
    logger.info(f"👤 Using dev user: {dev_user.username} ({dev_user.get_full_name()}) - {dev_user.email}")
    
    # Enable alerts if not already enabled
    if not dev_user.alert_enabled:
        logger.info("🔔 Enabling alerts for dev user...")
        dev_user.alert_enabled = True
        from app import db
        db.session.commit()
    
    logger.info("\n" + "=" * 80)
    
    # Step 2: Check user subscriptions and watchlist
    subscriptions = check_user_subscriptions(dev_user)
    watchlist = check_user_watchlist(dev_user)
    
    logger.info("\n" + "=" * 80)
    
    # Step 3: Create test bill
    test_bill = create_test_bill_for_user(dev_user)
    
    if not test_bill:
        logger.error("❌ Failed to create test bill")
        return False
    
    logger.info("\n" + "=" * 80)
    
    # Step 4: Send notification
    notification_success = send_notification_to_user(dev_user, test_bill)
    
    logger.info("\n" + "=" * 80)
    
    # Step 5: Test email configuration
    email_success = test_email_sending(dev_user)
    
    logger.info("\n" + "=" * 80)
    logger.info("📊 FINAL RESULTS:")
    logger.info(f"   User found: ✅")
    logger.info(f"   User has subscriptions: {'✅' if subscriptions else '❌'}")
    logger.info(f"   Test bill created: ✅")
    logger.info(f"   Notification sent: {'✅' if notification_success else '❌'}")
    if email_success is not None:
        logger.info(f"   Email sent: {'✅' if email_success else '❌'}")
    else:
        logger.info(f"   Email config: ⚠️ Not configured")
    
    if notification_success:
        logger.info("🎉 NOTIFICATION TEST SUCCESSFUL! 🎉")
        return True
    else:
        logger.error("❌ Notification test failed")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)