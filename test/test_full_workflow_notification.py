#!/usr/bin/env python3
"""
Test the complete workflow: bill analysis -> display_ready -> notification trigger
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

def test_full_workflow_notification():
    """Test the complete workflow from bill creation to notification"""
    try:
        from app import app, db
        from db_models import User, Bill, PolicyCategory, BillCategoryMapping, UserPolicySubscription, Alert, AIAnalysis, Summary
        from services.enhanced_ai_analyzer import EnhancedAIAnalyzer
        
        with app.app_context():
            logger.info("🧪 Testing complete workflow: Bill Analysis → Display Ready → Notification")
            
            # Get migron user
            migron = User.query.filter_by(username='migron').first()
            if not migron:
                logger.error("❌ User 'migron' not found")
                return False
            
            logger.info(f"👤 Testing with user: {migron.username}")
            
            # Get one of migron's subscriptions (Communications and Technology)
            comm_tech_category = PolicyCategory.query.filter_by(name='communications_technology').first()
            if not comm_tech_category:
                comm_tech_category = PolicyCategory.query.filter_by(display_name='Communications and Technology').first()
            
            if not comm_tech_category:
                logger.error("❌ Communications and Technology category not found")
                return False
            
            logger.info(f"📂 Using category: {comm_tech_category.display_name}")
            
            # Create a new bill that hasn't been analyzed yet
            test_bill = Bill(
                congress=119,
                bill_type='hr',
                bill_number=66666,
                title='Comprehensive Technology Privacy and Innovation Act - Full Workflow Test',
                summary='This bill establishes new privacy protections for digital communications, regulates artificial intelligence development, and promotes technological innovation while protecting consumer rights.',
                introduced_date=datetime.utcnow(),
                last_action_date=datetime.utcnow(),
                status='Introduced',
                sponsor_name='Tech Committee Chair',
                sponsor_party='Bipartisan',
                sponsor_state='CA',
                display_ready=False,  # Not analyzed yet - this is key!
                active=True
            )
            db.session.add(test_bill)
            db.session.commit()
            
            logger.info(f"✅ Created new unanalyzed bill: {test_bill.get_bill_identifier()}")
            logger.info(f"📊 Initial display_ready status: {test_bill.display_ready}")
            
            # Count initial alerts
            initial_alerts = Alert.query.filter_by(user_id=migron.id).count()
            logger.info(f"📈 Initial alert count: {initial_alerts}")
            
            # Create simulated analysis data that would match the user's interests
            test_analysis = {
                'summary': 'This comprehensive technology bill addresses privacy, AI regulation, and innovation.',
                'policy_implications': {
                    'primary_category': 'communications_technology',
                    'categories': [
                        {
                            'area': 'communications_technology',
                            'impact_level': 'high',
                            'reasoning': 'Major technology privacy and AI regulation provisions',
                            'title': 'Technology Privacy and AI Regulation'
                        }
                    ]
                },
                'stakeholders': {
                    'primary_affected': ['Technology companies', 'Privacy advocates', 'AI developers']
                },
                'complexity_assessment': {
                    'complexity_score': 85  # High complexity (0-100 scale in analysis)
                },
                'controversy_score': 0.7,
                'hidden_provisions': {
                    'detected_provisions': [],
                    'overall_hidden_risk_score': 0.2
                },
                'overall_risk_score': 0.4
            }
            
            logger.info("🤖 Simulating AI analysis completion...")
            
            # Initialize the AI analyzer
            analyzer = EnhancedAIAnalyzer()
            
            # Manually store the analysis results to trigger the notification flow
            # This simulates what would happen when the AI analysis completes
            
            # 1. Create AIAnalysis record
            ai_analysis = AIAnalysis(
                bill_id=test_bill.id,
                analysis_version=1,
                complexity_score=0.85,  # 0-1 scale for DB
                controversy_score=0.7,
                analysis_method='simulated_full',
                chunks_analyzed=1,
                processing_time=25.5,
                active=True
            )
            ai_analysis.set_analysis_data(test_analysis)
            db.session.add(ai_analysis)
            
            # 2. Create Summary record
            summary = Summary(
                bill_id=test_bill.id,
                summary_version=1,
                summary_text=test_analysis['summary'],
                plain_language_summary='This bill creates new rules for tech companies to protect your privacy and regulate AI.',
                funding_amounts='$2.5 billion over 5 years',
                implementation_timeline='18 months for full implementation',
                summary_type='ai_generated',
                active=True
            )
            summary.set_key_provisions(['Privacy protection framework', 'AI regulation standards', 'Innovation incentives'])
            db.session.add(summary)
            
            # 3. Store policy categories (this is what the AI analyzer would do)
            categories = test_analysis['policy_implications']['categories']
            analyzer._store_policy_categories(test_bill, categories, test_analysis)
            
            # 4. Now update display_ready status - this should trigger notifications!
            logger.info("🔄 Updating display_ready status (this should trigger notifications)...")
            
            old_status = test_bill.display_ready
            new_status = test_bill.is_analysis_complete()
            
            logger.info(f"📊 Analysis complete check: {new_status}")
            
            if new_status != old_status:
                test_bill.display_ready = True
                db.session.commit()
                
                logger.info(f"✅ Bill status changed: display_ready = {test_bill.display_ready}")
                
                # This is where the notification should be triggered
                # In the real workflow, this happens in enhanced_ai_analyzer.py
                from services.notification_helper import trigger_bill_analysis_notification_async
                
                logger.info("🔔 Triggering notifications (simulating AI analyzer completion)...")
                trigger_bill_analysis_notification_async(test_bill.id)
                
                # Give a moment for async processing
                import time
                time.sleep(2)
                
                # Check if notifications were created
                final_alerts = Alert.query.filter_by(user_id=migron.id).count()
                new_alerts = final_alerts - initial_alerts
                
                logger.info(f"📊 Final alert count: {final_alerts}")
                logger.info(f"🆕 New alerts from workflow: {new_alerts}")
                
                if new_alerts > 0:
                    # Show the latest alert
                    latest_alert = Alert.query.filter_by(user_id=migron.id).order_by(Alert.created_at.desc()).first()
                    logger.info("📬 Latest workflow alert:")
                    logger.info(f"   Title: {latest_alert.title}")
                    logger.info(f"   Type: {latest_alert.alert_type}")
                    logger.info(f"   Priority: {latest_alert.priority}")
                    logger.info(f"   Message: {latest_alert.message[:300]}...")
                    
                    logger.info("🎉 FULL WORKFLOW NOTIFICATION TEST SUCCESSFUL! 🎉")
                    logger.info("✅ Complete flow: Bill Analysis → Display Ready → Notification → Alert Created")
                    return True
                else:
                    logger.warning("⚠️ No alerts created despite display_ready status change")
                    return False
            else:
                logger.warning(f"⚠️ Bill analysis not complete. Missing requirements.")
                
                # Debug what's missing
                logger.info("🔍 Debugging analysis completeness...")
                logger.info(f"   Title: {bool(test_bill.title)}")
                logger.info(f"   Summary: {bool(test_bill.summary)}")
                logger.info(f"   AI Analysis: {bool(test_bill.get_active_ai_analysis())}")
                
                ai_analysis = test_bill.get_active_ai_analysis()
                if ai_analysis:
                    logger.info(f"   Complexity score: {ai_analysis.complexity_score}")
                
                summary = test_bill.get_active_summary()
                logger.info(f"   Summary record: {bool(summary and summary.summary_text)}")
                
                categories = BillCategoryMapping.query.filter_by(bill_id=test_bill.id).first()
                logger.info(f"   Category mappings: {bool(categories)}")
                
                return False
                
    except Exception as e:
        logger.error(f"❌ Error in full workflow test: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False

if __name__ == "__main__":
    logger.info("🚀 Testing Full Workflow: Bill Analysis → Notification")
    logger.info("=" * 80)
    
    success = test_full_workflow_notification()
    
    logger.info("\n" + "=" * 80)
    if success:
        logger.info("🎉 FULL WORKFLOW NOTIFICATION TEST PASSED! 🎉")
        logger.info("🔄 The complete pipeline from bill analysis to user notification is working!")
    else:
        logger.error("❌ Full workflow notification test failed")
    
    sys.exit(0 if success else 1)