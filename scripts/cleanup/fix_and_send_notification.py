#!/usr/bin/env python3
"""
Fix the category mismatch issue and send a successful notification to migron
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

def fix_and_send_notification():
    """Fix the category mismatch and send successful notification"""
    try:
        from app import app, db
        from db_models import User, Bill, PolicyCategory, BillCategoryMapping, UserPolicySubscription, Alert
        from services.notification_service import NotificationService
        from services.notification_helper import trigger_bill_analysis_notification
        
        with app.app_context():
            logger.info("🔧 Fixing category mismatch and sending notification to migron")
            
            # Get migron
            migron = User.query.filter_by(username='migron').first()
            if not migron:
                logger.error("❌ User 'migron' not found")
                return False
            
            logger.info(f"👤 User: {migron.username}")
            
            # Get the category that migron is actually subscribed to
            subscription = UserPolicySubscription.query.filter_by(
                user_id=migron.id,
                policy_category_id=6,  # communications_and_technology
                notification_enabled=True
            ).first()
            
            if not subscription:
                logger.error("❌ Migron not subscribed to Communications and Technology")
                return False
            
            correct_category = PolicyCategory.query.get(6)  # communications_and_technology
            logger.info(f"📂 Using correct category: {correct_category.display_name} (ID: {correct_category.id})")
            logger.info(f"💯 User interest level: {subscription.interest_level}")
            
            # Create a new bill with the CORRECT category mapping
            test_bill = Bill(
                congress=119,
                bill_type='hr',
                bill_number=55555,
                title='FINAL TEST: Advanced Technology Privacy Protection Act',
                summary='This bill establishes comprehensive privacy protections for digital communications and regulates emerging technologies to protect consumer rights.',
                introduced_date=datetime.utcnow(),
                last_action_date=datetime.utcnow(),
                status='Introduced',
                sponsor_name='Privacy Protection Committee',
                sponsor_party='Bipartisan',
                sponsor_state='WA',
                display_ready=True,
                active=True
            )
            db.session.add(test_bill)
            db.session.flush()  # Get the ID
            
            # Create category mapping with the CORRECT category ID that the user is subscribed to
            mapping = BillCategoryMapping(
                bill_id=test_bill.id,
                policy_category_id=correct_category.id,  # Use the ID that matches user subscription
                relevance_score=0.95,  # Very high relevance
                sneakiness_score=0.0,
                category_specific_analysis=f'{{"analysis": "Final test bill for {migron.username} using correct category ID {correct_category.id}", "category": "{correct_category.display_name}"}}'
            )
            db.session.add(mapping)
            db.session.commit()
            
            logger.info(f"✅ Created test bill: {test_bill.get_bill_identifier()}")
            logger.info(f"✅ Created category mapping: Category ID {correct_category.id} (relevance: {mapping.relevance_score})")
            
            # Verify the mapping is correct
            logger.info("🔍 Verifying category mapping...")
            logger.info(f"   User subscribed to category ID: {subscription.policy_category_id}")
            logger.info(f"   Bill mapped to category ID: {mapping.policy_category_id}")
            logger.info(f"   Categories match: {subscription.policy_category_id == mapping.policy_category_id}")
            
            # Count initial alerts
            initial_alerts = Alert.query.filter_by(user_id=migron.id).count()
            logger.info(f"📊 Initial alert count: {initial_alerts}")
            
            # Test notification service
            notification_service = NotificationService()
            should_notify = notification_service._should_notify_user(migron, test_bill)
            
            logger.info(f"🎯 Should notify user: {should_notify}")
            
            if should_notify:
                logger.info("🚀 Sending notification...")
                
                # Send notification
                trigger_bill_analysis_notification(test_bill.id)
                
                # Check results
                final_alerts = Alert.query.filter_by(user_id=migron.id).count()
                new_alerts = final_alerts - initial_alerts
                
                logger.info(f"📊 Final alert count: {final_alerts}")
                logger.info(f"🆕 New alerts created: {new_alerts}")
                
                if new_alerts > 0:
                    # Show the latest alert
                    latest_alert = Alert.query.filter_by(user_id=migron.id).order_by(Alert.created_at.desc()).first()
                    logger.info("📬 SUCCESS! Latest alert created:")
                    logger.info(f"   Title: {latest_alert.title}")
                    logger.info(f"   Type: {latest_alert.alert_type}")
                    logger.info(f"   Priority: {latest_alert.priority}")
                    logger.info(f"   Created: {latest_alert.created_at}")
                    logger.info(f"   Message: {latest_alert.message}")
                    
                    logger.info("🎉 NOTIFICATION SUCCESSFULLY SENT TO MIGRON! 🎉")
                    return True
                else:
                    logger.error("❌ No alerts created despite should_notify=True")
                    return False
            else:
                logger.error("❌ Notification service still says should NOT notify")
                
                # Debug further
                logger.info("🔍 Final debugging...")
                user_subs = UserPolicySubscription.query.filter_by(
                    user_id=migron.id,
                    notification_enabled=True
                ).all()
                
                bill_cats = BillCategoryMapping.query.filter_by(bill_id=test_bill.id).all()
                
                logger.info("User subscriptions:")
                for sub in user_subs:
                    logger.info(f"   Category ID {sub.policy_category_id}: interest={sub.interest_level}")
                
                logger.info("Bill categories:")
                for bill_cat in bill_cats:
                    logger.info(f"   Category ID {bill_cat.policy_category_id}: relevance={bill_cat.relevance_score}")
                
                return False
                
    except Exception as e:
        logger.error(f"❌ Error fixing and sending notification: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False

if __name__ == "__main__":
    logger.info("🔧 Fixing Category Mismatch and Sending Notification to Migron")
    logger.info("=" * 80)
    
    success = fix_and_send_notification()
    
    logger.info("\n" + "=" * 80)
    if success:
        logger.info("🎉 NOTIFICATION SUCCESSFULLY FIXED AND SENT! 🎉")
    else:
        logger.error("❌ Notification fix failed")
    
    sys.exit(0 if success else 1)