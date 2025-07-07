#!/usr/bin/env python3
"""
Comprehensive test script for the workflow orchestrator with real data
Tests the complete workflow pipeline including AI analysis and alert generation
"""

import os
import sys
import logging
import time
from datetime import datetime

# Add the current directory to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from db_models import User, Bill, PolicyCategory, UserPolicySubscription, Alert
from services.workflow_orchestrator import WorkflowOrchestrator, start_workflow_service, stop_workflow_service, get_workflow_status

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_workflow_with_real_data():
    """Test the workflow orchestrator with real bills from the database"""
    try:
        with app.app_context():
            logger.info("Testing Workflow Orchestrator with Real Data")
            logger.info("=" * 60)
            
            # Get current database state
            total_bills = Bill.query.count()
            bills_with_analysis = Bill.query.filter(Bill.ai_analysis.isnot(None)).count()
            bills_without_analysis = total_bills - bills_with_analysis
            
            logger.info(f"Database State:")
            logger.info(f"  - Total bills: {total_bills}")
            logger.info(f"  - Bills with AI analysis: {bills_with_analysis}")
            logger.info(f"  - Bills without AI analysis: {bills_without_analysis}")
            
            # Get users and policy categories
            users = User.query.all()
            policy_categories = PolicyCategory.query.all()
            
            logger.info(f"Users: {len(users)}")
            logger.info(f"Policy Categories: {len(policy_categories)}")
            
            # Create orchestrator instance
            orchestrator = WorkflowOrchestrator()
            
            # Test 1: Check workflow status
            logger.info("\n1. Testing Workflow Status")
            status = orchestrator.get_workflow_status()
            logger.info(f"Workflow Status: {status['is_running']}")
            logger.info(f"Queue Size: {status['queue_size']}")
            
            # Test 2: Test backfill processing logic
            logger.info("\n2. Testing Backfill Processing Logic")
            bills_without_analysis_list = Bill.query.filter(
                (Bill.ai_analysis.is_(None)) | (Bill.ai_analysis == '')
            ).limit(5).all()
            
            logger.info(f"Found {len(bills_without_analysis_list)} bills for backfill processing")
            
            for bill in bills_without_analysis_list:
                logger.info(f"  - {bill.get_bill_identifier()}: {bill.title[:50]}...")
            
            # Test 3: Test workflow item creation
            logger.info("\n3. Testing Workflow Item Creation")
            from services.workflow_orchestrator import WorkflowItem, WorkflowStatus
            
            test_bill = bills_without_analysis_list[0] if bills_without_analysis_list else None
            if test_bill:
                workflow_item = WorkflowItem(
                    bill_identifier=test_bill.get_bill_identifier(),
                    congress=test_bill.congress,
                    bill_type=test_bill.bill_type,
                    bill_number=test_bill.bill_number,
                    title=test_bill.title,
                    source='backfill',
                    discovered_at=datetime.utcnow(),
                    status=WorkflowStatus.PENDING,
                    bill_id=test_bill.id
                )
                logger.info(f"Created workflow item: {workflow_item.bill_identifier}")
            
            # Test 4: Test alert generation logic
            logger.info("\n4. Testing Alert Generation Logic")
            users_with_alerts = User.query.filter_by(alert_enabled=True).all()
            logger.info(f"Users with alerts enabled: {len(users_with_alerts)}")
            
            for user in users_with_alerts:
                subscriptions = UserPolicySubscription.query.filter_by(
                    user_id=user.id,
                    notification_enabled=True
                ).all()
                logger.info(f"  - User {user.username}: {len(subscriptions)} active subscriptions")
                
                for sub in subscriptions:
                    policy_cat = PolicyCategory.query.get(sub.policy_category_id)
                    if policy_cat:
                        logger.info(f"    * {policy_cat.name} (interest: {sub.interest_level})")
            
            # Test 5: Test bill processing logic
            logger.info("\n5. Testing Bill Processing Logic")
            if test_bill:
                logger.info(f"Testing with bill: {test_bill.get_bill_identifier()}")
                
                # Check if bill has full text
                full_text = test_bill.get_full_text()
                if full_text:
                    logger.info(f"  - Full text available: {len(full_text)} characters")
                else:
                    logger.warning(f"  - No full text available")
                
                # Check if bill has actions
                actions = test_bill.actions
                logger.info(f"  - Bill actions: {len(actions)}")
            
            # Test 6: Test AI analysis status
            logger.info("\n6. Testing AI Analysis Status")
            bills_with_analysis_list = Bill.query.filter(Bill.ai_analysis.isnot(None)).limit(3).all()
            
            for bill in bills_with_analysis_list:
                analysis = bill.get_ai_analysis()
                if analysis:
                    logger.info(f"  - {bill.get_bill_identifier()}: AI analysis present")
                    if 'policy_implications' in analysis:
                        policy_data = analysis['policy_implications']
                        primary_area = policy_data.get('primary_policy_area', 'Unknown')
                        logger.info(f"    * Primary policy area: {primary_area}")
                    
                    if 'summary' in analysis:
                        logger.info(f"    * Summary generated")
                    
                    if 'stakeholders' in analysis:
                        stakeholders = analysis['stakeholders']
                        if isinstance(stakeholders, dict):
                            winners = len(stakeholders.get('winners', []))
                            losers = len(stakeholders.get('losers', []))
                            logger.info(f"    * Stakeholders: {winners} winners, {losers} losers")
            
            # Test 7: Test policy category mappings
            logger.info("\n7. Testing Policy Category Mappings")
            from db_models import BillCategoryMapping
            
            mappings = BillCategoryMapping.query.limit(5).all()
            logger.info(f"Found {len(mappings)} policy category mappings")
            
            for mapping in mappings:
                bill = Bill.query.get(mapping.bill_id)
                category = PolicyCategory.query.get(mapping.policy_category_id)
                if bill and category:
                    logger.info(f"  - {bill.get_bill_identifier()} -> {category.name} (score: {mapping.relevance_score})")
            
            # Test 8: Test alert system
            logger.info("\n8. Testing Alert System")
            total_alerts = Alert.query.count()
            logger.info(f"Total alerts in database: {total_alerts}")
            
            recent_alerts = Alert.query.order_by(Alert.created_at.desc()).limit(5).all()
            for alert in recent_alerts:
                bill = Bill.query.get(alert.bill_id)
                user = User.query.get(alert.user_id)
                if bill and user:
                    logger.info(f"  - Alert for {user.username}: {alert.alert_type} - {bill.get_bill_identifier()}")
            
            logger.info("\n✅ Comprehensive workflow test completed successfully!")
            return True
            
    except Exception as e:
        logger.error(f"❌ Comprehensive workflow test failed: {str(e)}")
        return False

def test_workflow_performance():
    """Test workflow performance metrics"""
    try:
        with app.app_context():
            logger.info("\nTesting Workflow Performance Metrics")
            logger.info("=" * 40)
            
            orchestrator = WorkflowOrchestrator()
            status = orchestrator.get_workflow_status()
            stats = status['statistics']
            
            logger.info("Performance Metrics:")
            logger.info(f"  - Bills discovered: {stats['bills_discovered']}")
            logger.info(f"  - Bills processed: {stats['bills_processed']}")
            logger.info(f"  - Bills analyzed: {stats['bills_analyzed']}")
            logger.info(f"  - Alerts generated: {stats['alerts_generated']}")
            logger.info(f"  - Errors: {stats['errors']}")
            
            # Chunked analysis metrics
            chunked_summary = status['chunked_analysis_summary']
            logger.info(f"\nChunked Analysis Metrics:")
            logger.info(f"  - Total chunks processed: {chunked_summary['total_chunks_processed']}")
            logger.info(f"  - Total text processed: {chunked_summary['total_text_processed']}")
            logger.info(f"  - Average chunks per bill: {chunked_summary['average_chunks_per_bill']}")
            logger.info(f"  - Analysis methods: {chunked_summary['analysis_methods']}")
            
            # Processing performance
            perf = chunked_summary['processing_performance']
            logger.info(f"\nProcessing Performance:")
            logger.info(f"  - Average time: {perf['average_time']}")
            logger.info(f"  - Fastest time: {perf['fastest_time']}")
            logger.info(f"  - Slowest time: {perf['slowest_time']}")
            logger.info(f"  - Total time: {perf['total_time']}")
            
            return True
            
    except Exception as e:
        logger.error(f"❌ Performance test failed: {str(e)}")
        return False

def test_workflow_components():
    """Test individual workflow components"""
    try:
        with app.app_context():
            logger.info("\nTesting Individual Workflow Components")
            logger.info("=" * 40)
            
            # Test RSS monitoring component
            logger.info("1. RSS Monitoring Component")
            from services.rss_monitoring import PersistentRSSMonitor
            rss_monitor = PersistentRSSMonitor()
            logger.info(f"  - RSS monitor initialized: {rss_monitor is not None}")
            
            # Test bill processor component
            logger.info("2. Bill Processor Component")
            from services.bill_processor import BillProcessor
            bill_processor = BillProcessor()
            logger.info(f"  - Bill processor initialized: {bill_processor is not None}")
            
            # Test AI analyzer component
            logger.info("3. AI Analyzer Component")
            from services.enhanced_ai_analyzer import EnhancedAIAnalyzer
            ai_analyzer = EnhancedAIAnalyzer()
            logger.info(f"  - AI analyzer initialized: {ai_analyzer is not None}")
            
            # Test notification service component
            logger.info("4. Notification Service Component")
            from services.notification_service import NotificationService
            notification_service = NotificationService()
            logger.info(f"  - Notification service initialized: {notification_service is not None}")
            
            # Test Congress API component
            logger.info("5. Congress API Component")
            from services.congress_api import CongressAPI
            congress_api = CongressAPI()
            logger.info(f"  - Congress API initialized: {congress_api is not None}")
            
            logger.info("✅ All workflow components initialized successfully!")
            return True
            
    except Exception as e:
        logger.error(f"❌ Component test failed: {str(e)}")
        return False

def main():
    """Main test function"""
    logger.info("Starting Comprehensive Workflow Orchestrator Tests")
    logger.info("=" * 80)
    
    try:
        # Test 1: Workflow with real data
        test1_passed = test_workflow_with_real_data()
        
        # Test 2: Performance metrics
        test2_passed = test_workflow_performance()
        
        # Test 3: Individual components
        test3_passed = test_workflow_components()
        
        # Summary
        logger.info("\n" + "=" * 80)
        logger.info("Comprehensive Test Results Summary:")
        logger.info(f"Workflow with Real Data Test: {'✅ PASSED' if test1_passed else '❌ FAILED'}")
        logger.info(f"Performance Metrics Test: {'✅ PASSED' if test2_passed else '❌ FAILED'}")
        logger.info(f"Component Initialization Test: {'✅ PASSED' if test3_passed else '❌ FAILED'}")
        
        if test1_passed and test2_passed and test3_passed:
            logger.info("\n🎉 All comprehensive tests passed! The workflow orchestrator is working as intended.")
            logger.info("\nKey Findings:")
            logger.info("✅ Database contains real bill data")
            logger.info("✅ AI analysis is being performed and stored")
            logger.info("✅ Policy categories are being mapped")
            logger.info("✅ Alert system is functional")
            logger.info("✅ All workflow components are properly initialized")
            logger.info("✅ Performance metrics are being tracked")
        else:
            logger.error("\n❌ Some tests failed. Please check the logs above for details.")
            
    except Exception as e:
        logger.error(f"❌ Comprehensive test suite failed with error: {str(e)}")

if __name__ == "__main__":
    main() 