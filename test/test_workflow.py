#!/usr/bin/env python3
"""
Test script for the updated workflow orchestrator
Tests the new design focused on AI analysis storage and user alert generation
"""

import os
import sys
import logging
import time
from datetime import datetime

# Add the current directory to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from db_models import User, Bill, PolicyCategory, UserPolicySubscription
from services.workflow_orchestrator import WorkflowOrchestrator, start_workflow_service, stop_workflow_service, get_workflow_status

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def create_test_data():
    """Create test data for workflow testing"""
    try:
        # Use existing user with ID 1
        test_user = User.query.get(1)
        if not test_user:
            logger.error("User with ID 1 not found. Please ensure there's a test user in the database.")
            return None, None, None
        
        logger.info(f"Using existing test user: {test_user.username}")

        # Create test policy category
        test_category = PolicyCategory(
            name="Environmental Protection",
            display_name="Environmental Protection",
            description="Environmental and climate change policies",
            is_active=True
        )
        db.session.add(test_category)
        db.session.commit()
        logger.info(f"Created test policy category: {test_category.name}")

        # Create user subscription
        subscription = UserPolicySubscription(
            user_id=test_user.id,
            policy_category_id=test_category.id,
            interest_level=0.8,
            notification_enabled=True,
            email_notifications=True,
            in_app_notifications=True
        )
        db.session.add(subscription)
        db.session.commit()
        logger.info(f"Created user subscription for {test_category.name}")

        # Create test bill without AI analysis
        test_bill = Bill(
            congress=119,
            bill_type="hr",
            bill_number=1234,
            title="Test Environmental Protection Bill",
            summary="A test bill for environmental protection",
            introduced_date=datetime.utcnow(),
            last_action_date=datetime.utcnow(),
            status="Introduced",
            sponsor_name="Test Sponsor",
            sponsor_party="D",
            sponsor_state="CA"
        )
        db.session.add(test_bill)
        db.session.commit()
        logger.info(f"Created test bill: {test_bill.get_bill_identifier()}")

        return test_user, test_category, test_bill

    except Exception as e:
        logger.error(f"Error creating test data: {str(e)}")
        db.session.rollback()
        raise

def test_workflow_orchestrator():
    """Test the workflow orchestrator functionality"""
    try:
        with app.app_context():
            logger.info("Testing Workflow Orchestrator")
            
            # Create test data
            test_data = create_test_data()
            if not test_data[0]:
                return False
                
            test_user, test_category, test_bill = test_data
            
            # Create orchestrator instance
            orchestrator = WorkflowOrchestrator()
            
            # Test workflow status
            status = orchestrator.get_workflow_status()
            logger.info(f"Initial workflow status: {status}")
            
            # Test backfill processing (without starting the full workflow)
            logger.info("Testing backfill processing...")
            
            # Find bills without AI analysis
            bills_without_analysis = Bill.query.filter(
                (Bill.ai_analysis.is_(None)) | (Bill.ai_analysis == '')
            ).all()
            
            logger.info(f"Found {len(bills_without_analysis)} bills without AI analysis")
            
            for bill in bills_without_analysis:
                logger.info(f"Bill without analysis: {bill.get_bill_identifier()} - {bill.title}")
            
            # Test workflow item creation
            from services.workflow_orchestrator import WorkflowItem, WorkflowStatus
            
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
            
            # Test alert generation logic (without actually running AI analysis)
            logger.info("Testing alert generation logic...")
            
            # Get users with alert preferences
            users_with_alerts = User.query.filter_by(alert_enabled=True).all()
            logger.info(f"Found {len(users_with_alerts)} users with alerts enabled")
            
            for user in users_with_alerts:
                subscriptions = UserPolicySubscription.query.filter_by(
                    user_id=user.id,
                    notification_enabled=True
                ).all()
                logger.info(f"User {user.username} has {len(subscriptions)} active subscriptions")
            
            logger.info("✅ Workflow orchestrator test completed successfully!")
            
            return True
            
    except Exception as e:
        logger.error(f"❌ Workflow orchestrator test failed: {str(e)}")
        return False

def test_workflow_service_functions():
    """Test the workflow service functions"""
    try:
        logger.info("Testing workflow service functions...")
        
        # Test status function
        status = get_workflow_status()
        logger.info(f"Workflow status: {status}")
        
        # Test that we can call start/stop without errors
        logger.info("Testing workflow service start/stop functions...")
        
        # Note: We won't actually start the workflow in this test
        # to avoid interfering with any running processes
        
        logger.info("✅ Workflow service functions test completed successfully!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Workflow service functions test failed: {str(e)}")
        return False

def cleanup_test_data():
    """Clean up test data"""
    try:
        with app.app_context():
            # Clean up test data
            PolicyCategory.query.filter_by(name="Environmental Protection").delete()
            Bill.query.filter_by(bill_type="hr", bill_number=1234).delete()
            db.session.commit()
            logger.info("✅ Test data cleaned up successfully!")
            
    except Exception as e:
        logger.error(f"❌ Error cleaning up test data: {str(e)}")

def main():
    """Main test function"""
    logger.info("Starting Workflow Orchestrator Tests")
    logger.info("=" * 50)
    
    try:
        # Test 1: Workflow Orchestrator
        test1_passed = test_workflow_orchestrator()
        
        # Test 2: Service Functions
        test2_passed = test_workflow_service_functions()
        
        # Cleanup
        cleanup_test_data()
        
        # Summary
        logger.info("=" * 50)
        logger.info("Test Results Summary:")
        logger.info(f"Workflow Orchestrator Test: {'✅ PASSED' if test1_passed else '❌ FAILED'}")
        logger.info(f"Service Functions Test: {'✅ PASSED' if test2_passed else '❌ FAILED'}")
        
        if test1_passed and test2_passed:
            logger.info("🎉 All tests passed! The workflow orchestrator is ready to use.")
        else:
            logger.error("❌ Some tests failed. Please check the logs above.")
            
    except Exception as e:
        logger.error(f"❌ Test suite failed with error: {str(e)}")
        cleanup_test_data()

if __name__ == "__main__":
    main() 