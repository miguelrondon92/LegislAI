#!/usr/bin/env python3
"""
Debug why the notification was processed but no alert was created
"""

import sys
import os
import logging

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

def debug_notification_logic():
    """Debug the notification matching logic step by step"""
    try:
        from app import app, db
        from db_models import User, Bill, PolicyCategory, BillCategoryMapping, UserPolicySubscription
        from services.notification_service import NotificationService
        
        with app.app_context():
            logger.info("🔍 Debugging notification logic step by step")
            
            # Get migron and the latest test bill
            migron = User.query.filter_by(username='migron').first()
            test_bill = Bill.query.filter_by(congress=119, bill_type='hr', bill_number=66666).first()
            
            if not migron or not test_bill:
                logger.error("❌ User or bill not found")
                return False
            
            logger.info(f"👤 User: {migron.username}")
            logger.info(f"📄 Bill: {test_bill.get_bill_identifier()}")
            logger.info(f"📊 Bill display_ready: {test_bill.display_ready}")
            
            # Check user subscriptions in detail
            logger.info("\n📂 User's Policy Subscriptions:")
            user_subs = UserPolicySubscription.query.filter_by(user_id=migron.id).all()
            
            for sub in user_subs:
                category = PolicyCategory.query.get(sub.policy_category_id)
                logger.info(f"   - Category ID {sub.policy_category_id}: {category.name if category else 'Unknown'}")
                logger.info(f"     Display Name: {category.display_name if category else 'Unknown'}")
                logger.info(f"     Interest: {sub.interest_level}")
                logger.info(f"     Notifications enabled: {sub.notification_enabled}")
                logger.info(f"     Email enabled: {sub.email_notifications}")
                logger.info("")
            
            # Check bill category mappings in detail
            logger.info("🔗 Bill's Category Mappings:")
            bill_cats = BillCategoryMapping.query.filter_by(bill_id=test_bill.id).all()
            
            for bill_cat in bill_cats:
                category = PolicyCategory.query.get(bill_cat.policy_category_id)
                logger.info(f"   - Category ID {bill_cat.policy_category_id}: {category.name if category else 'Unknown'}")
                logger.info(f"     Display Name: {category.display_name if category else 'Unknown'}")
                logger.info(f"     Relevance Score: {bill_cat.relevance_score}")
                logger.info(f"     Sneakiness Score: {bill_cat.sneakiness_score}")
                logger.info("")
            
            # Check for exact matches
            logger.info("🎯 Checking for matches:")
            matches_found = 0
            
            for sub in user_subs:
                for bill_cat in bill_cats:
                    if sub.policy_category_id == bill_cat.policy_category_id:
                        category = PolicyCategory.query.get(sub.policy_category_id)
                        logger.info(f"   ✅ MATCH FOUND: {category.display_name if category else 'Unknown'}")
                        logger.info(f"      User interest: {sub.interest_level} (threshold: ≥0.5)")
                        logger.info(f"      Bill relevance: {bill_cat.relevance_score} (threshold: ≥0.6)")
                        logger.info(f"      Notifications enabled: {sub.notification_enabled}")
                        
                        interest_ok = sub.interest_level >= 0.5
                        relevance_ok = bill_cat.relevance_score >= 0.6
                        notifications_ok = sub.notification_enabled
                        
                        logger.info(f"      Interest threshold met: {interest_ok}")
                        logger.info(f"      Relevance threshold met: {relevance_ok}")
                        logger.info(f"      Notifications enabled: {notifications_ok}")
                        
                        if interest_ok and relevance_ok and notifications_ok:
                            logger.info(f"      🎉 ALL CONDITIONS MET - SHOULD NOTIFY!")
                            matches_found += 1
                        else:
                            logger.info(f"      ❌ CONDITIONS NOT MET")
                        logger.info("")
            
            logger.info(f"📊 Total qualifying matches: {matches_found}")
            
            # Test the notification service logic directly
            logger.info("\n🧪 Testing NotificationService logic:")
            notification_service = NotificationService()
            
            should_notify = notification_service._should_notify_user(migron, test_bill)
            logger.info(f"🎯 NotificationService says should notify: {should_notify}")
            
            if should_notify:
                logger.info("✅ Notification service logic is working correctly")
                
                # Check if user is in the list of users to notify
                users_to_notify = notification_service._get_users_to_notify(test_bill)
                migron_in_list = any(user.id == migron.id for user in users_to_notify)
                
                logger.info(f"👥 Total users to notify: {len(users_to_notify)}")
                logger.info(f"📋 Migron in notification list: {migron_in_list}")
                
                if migron_in_list:
                    logger.info("✅ User is correctly identified for notification")
                    
                    # Test alert creation
                    from db_models import Alert
                    initial_count = Alert.query.filter_by(user_id=migron.id).count()
                    
                    logger.info(f"📊 Current alert count: {initial_count}")
                    
                    # Try creating notification manually
                    logger.info("🔨 Attempting to create notification manually...")
                    notification_service._create_notification(migron, test_bill)
                    db.session.commit()
                    
                    final_count = Alert.query.filter_by(user_id=migron.id).count()
                    logger.info(f"📊 Final alert count: {final_count}")
                    
                    if final_count > initial_count:
                        logger.info("✅ Manual notification creation successful!")
                        
                        # Show the alert
                        latest_alert = Alert.query.filter_by(user_id=migron.id).order_by(Alert.created_at.desc()).first()
                        logger.info("📬 Latest alert:")
                        logger.info(f"   Title: {latest_alert.title}")
                        logger.info(f"   Type: {latest_alert.alert_type}")
                        logger.info(f"   Priority: {latest_alert.priority}")
                        
                        return True
                    else:
                        logger.error("❌ Manual notification creation failed")
                        return False
                else:
                    logger.error("❌ User not in notification list despite should_notify=True")
                    return False
            else:
                logger.error("❌ Notification service says should NOT notify")
                return False
                
    except Exception as e:
        logger.error(f"❌ Error debugging notification logic: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False

if __name__ == "__main__":
    logger.info("🔍 Debugging Notification Logic")
    logger.info("=" * 80)
    
    success = debug_notification_logic()
    
    logger.info("\n" + "=" * 80)
    if success:
        logger.info("🎉 NOTIFICATION DEBUG SUCCESSFUL!")
    else:
        logger.error("❌ Notification debug revealed issues")
    
    sys.exit(0 if success else 1)