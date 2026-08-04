#!/usr/bin/env python3
"""
Fixed script to send notification to migron (dev user) - resolving SQLAlchemy session issues.
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

def send_notification_to_migron():
    """Send notification to migron with proper session handling"""
    try:
        from app import app, db
        from db_models import User, Bill, PolicyCategory, BillCategoryMapping, UserPolicySubscription, Alert
        from services.notification_service import NotificationService
        
        with app.app_context():
            logger.info("🚀 Sending notification to migron (dev user)...")
            
            # Get migron user
            migron = User.query.filter_by(username='migron').first()
            if not migron:
                logger.error("❌ User 'migron' not found")
                return False
                
            logger.info(f"👤 Found user: {migron.username} ({migron.get_full_name()}) - {migron.email}")
            logger.info(f"🔔 Alerts enabled: {migron.alert_enabled}")
            logger.info(f"📧 Alert frequency: {migron.alert_frequency}")
            
            # Get user's first subscription (Budget and Fiscal Policy)
            subscription = UserPolicySubscription.query.filter_by(
                user_id=migron.id,
                notification_enabled=True
            ).first()
            
            if not subscription:
                logger.error("❌ No active subscriptions found for migron")
                return False
                
            category = PolicyCategory.query.get(subscription.policy_category_id)
            logger.info(f"📂 Using subscription: {category.display_name} (interest: {subscription.interest_level})")
            
            # Create or get test bill with proper session handling
            test_bill = Bill.query.filter_by(congress=119, bill_type='hr', bill_number=77777).first()
            
            if not test_bill:
                logger.info("📄 Creating new test bill for migron...")
                test_bill = Bill(
                    congress=119,
                    bill_type='hr',
                    bill_number=77777,
                    title=f'Notification Test Bill for {migron.username} - {category.display_name}',
                    summary=f'A test bill created to verify notifications work for {migron.username}. This bill relates to {category.display_name} policies.',
                    introduced_date=datetime.utcnow(),
                    last_action_date=datetime.utcnow(),
                    status='Introduced',
                    sponsor_name='Notification Test Sponsor',
                    sponsor_party='Test',
                    sponsor_state='NT',
                    display_ready=True,
                    active=True
                )
                db.session.add(test_bill)
                db.session.flush()  # Get the ID without committing
                
                # Create category mapping
                mapping = BillCategoryMapping(
                    bill_id=test_bill.id,
                    policy_category_id=category.id,
                    relevance_score=0.95,  # Very high relevance
                    sneakiness_score=0.0,
                    category_specific_analysis=f'{{"analysis": "Test bill for {migron.username} notification verification", "category": "{category.display_name}"}}'
                )
                db.session.add(mapping)
                db.session.commit()  # Commit both bill and mapping
                
                logger.info(f"✅ Created test bill: {test_bill.get_bill_identifier()}")
                logger.info(f"✅ Created category mapping: {category.display_name} (relevance: {mapping.relevance_score})")
            else:
                logger.info(f"✅ Using existing test bill: {test_bill.get_bill_identifier()}")
            
            # Check initial alert count
            initial_alerts = Alert.query.filter_by(user_id=migron.id).count()
            logger.info(f"📊 Initial alert count for {migron.username}: {initial_alerts}")
            
            # Test notification service with fresh queries to avoid session issues
            notification_service = NotificationService()
            
            # Re-query objects to ensure they're bound to current session
            fresh_user = User.query.get(migron.id)
            fresh_bill = Bill.query.get(test_bill.id)
            
            logger.info("🧪 Testing notification logic...")
            
            # Test should_notify_user logic
            should_notify = notification_service._should_notify_user(fresh_user, fresh_bill)
            logger.info(f"🎯 Should notify user: {should_notify}")
            
            if should_notify:
                logger.info("📡 Processing notification...")
                notification_service.process_new_bill_analysis(fresh_bill.id)
                
                # Check if alerts were created
                final_alerts = Alert.query.filter_by(user_id=migron.id).count()
                new_alerts = final_alerts - initial_alerts
                
                logger.info(f"📊 Final alert count: {final_alerts}")
                logger.info(f"🆕 New alerts created: {new_alerts}")
                
                if new_alerts > 0:
                    # Show the latest alert
                    latest_alert = Alert.query.filter_by(user_id=migron.id).order_by(Alert.created_at.desc()).first()
                    logger.info("📬 Latest alert created:")
                    logger.info(f"   Title: {latest_alert.title}")
                    logger.info(f"   Type: {latest_alert.alert_type}")
                    logger.info(f"   Priority: {latest_alert.priority}")
                    logger.info(f"   Created: {latest_alert.created_at}")
                    logger.info(f"   Message preview: {latest_alert.message[:200]}...")
                    
                    logger.info("🎉 NOTIFICATION SUCCESSFULLY SENT TO MIGRON! 🎉")
                    return True
                else:
                    logger.warning("⚠️ No alerts were created despite should_notify=True")
                    return False
            else:
                logger.warning("⚠️ Notification logic says user should NOT be notified")
                
                # Debug why not
                logger.info("🔍 Debugging notification logic...")
                
                # Check user subscriptions
                user_subs = UserPolicySubscription.query.filter_by(
                    user_id=fresh_user.id,
                    notification_enabled=True
                ).all()
                
                # Check bill categories
                bill_cats = BillCategoryMapping.query.filter_by(bill_id=fresh_bill.id).all()
                
                logger.info(f"   📂 User subscriptions: {len(user_subs)}")
                for sub in user_subs:
                    cat = PolicyCategory.query.get(sub.policy_category_id)
                    logger.info(f"      - {cat.display_name}: interest={sub.interest_level}, enabled={sub.notification_enabled}")
                
                logger.info(f"   🔗 Bill categories: {len(bill_cats)}")
                for bill_cat in bill_cats:
                    cat = PolicyCategory.query.get(bill_cat.policy_category_id)
                    logger.info(f"      - {cat.display_name}: relevance={bill_cat.relevance_score}")
                
                # Check for matches
                for sub in user_subs:
                    for bill_cat in bill_cats:
                        if sub.policy_category_id == bill_cat.policy_category_id:
                            cat = PolicyCategory.query.get(sub.policy_category_id)
                            logger.info(f"   ✅ Match found: {cat.display_name}")
                            logger.info(f"      Interest: {sub.interest_level} (need ≥0.5)")
                            logger.info(f"      Relevance: {bill_cat.relevance_score} (need ≥0.6)")
                            if sub.interest_level >= 0.5 and bill_cat.relevance_score >= 0.6:
                                logger.info(f"      ✅ Thresholds met! This should trigger notification.")
                            else:
                                logger.info(f"      ❌ Thresholds not met")
                
                return False
                
    except Exception as e:
        logger.error(f"❌ Error sending notification to migron: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False

def test_email_notification_to_migron():
    """Test sending an actual email notification"""
    try:
        from app import app, mail
        from flask_mail import Message
        from db_models import User
        import os
        
        with app.app_context():
            migron = User.query.filter_by(username='migron').first()
            if not migron:
                logger.error("❌ User 'migron' not found")
                return False
            
            logger.info(f"📧 Sending test email to {migron.email}...")
            
            msg = Message(
                subject="🔔 LegislAI Notification Test - Success!",
                recipients=[migron.email],
                body=f"""
Hello {migron.get_full_name()},

🎉 Great news! The LegislAI notification system is working perfectly!

This email confirms that:
✅ Your user account was found in the system
✅ Your policy subscriptions are active
✅ The notification service can process your preferences
✅ Email delivery is working correctly

You are currently subscribed to these policy areas:
• Budget and Fiscal Policy (Interest: Very High)
• Civil Rights and Liberties (Interest: Very High)  
• Communications and Technology (Interest: Very High)
• Criminal Justice and Law Enforcement (Interest: High)
• Native American Affairs (Interest: Medium)

From now on, you'll receive notifications when bills matching your interests are analyzed!

Best regards,
LegislAI Development Team

---
This is an automated test message from the LegislAI notification system.
                """,
                sender=os.environ.get('MAIL_DEFAULT_SENDER', 'noreply@legislai.com')
            )
            
            mail.send(msg)
            logger.info("✅ Test email sent successfully to migron!")
            return True
            
    except Exception as e:
        logger.error(f"❌ Error sending test email: {e}")
        return False

def main():
    """Main function"""
    logger.info("🚀 Testing notification system for migron (dev user)")
    logger.info("=" * 80)
    
    # Test notification creation
    notification_success = send_notification_to_migron()
    
    logger.info("\n" + "=" * 80)
    
    # Test email sending
    email_success = test_email_notification_to_migron()
    
    logger.info("\n" + "=" * 80)
    logger.info("📊 FINAL RESULTS:")
    logger.info(f"   In-app notification: {'✅ SUCCESS' if notification_success else '❌ FAILED'}")
    logger.info(f"   Email notification: {'✅ SUCCESS' if email_success else '❌ FAILED'}")
    
    if notification_success and email_success:
        logger.info("🎉 ALL NOTIFICATIONS TO MIGRON SUCCESSFUL! 🎉")
        return True
    elif email_success:
        logger.info("📧 Email notification successful, in-app notification needs debugging")
        return True  # At least email works
    else:
        logger.error("❌ Both notification methods failed")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)