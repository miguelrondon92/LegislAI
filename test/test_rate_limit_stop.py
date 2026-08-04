#!/usr/bin/env python3
"""
Test script to verify rate limit stop behavior
"""

import os
import sys
import logging
import time
from datetime import datetime

# Add the current directory to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from db_models import Bill
from services.workflow_orchestrator import WorkflowOrchestrator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_rate_limit_stop():
    """Test that workflow stops when rate limits are hit"""
    try:
        with app.app_context():
            logger.info("Testing Rate Limit Stop Behavior")
            
            # Get a bill for testing
            bill = db.session.query(Bill).filter(
                Bill.ai_analysis.is_(None)
            ).first()
            
            if not bill:
                logger.error("No bills without AI analysis found for testing")
                return
            
            logger.info(f"Testing with bill: {bill.get_bill_identifier()}")
            
            # Create workflow orchestrator
            orchestrator = WorkflowOrchestrator()
            
            # Test initial state
            logger.info("Testing initial workflow state...")
            logger.info(f"Workflow running: {orchestrator.is_running}")
            logger.info(f"Rate limit hits: {orchestrator.stats['rate_limit_hits']}")
            logger.info(f"Stopped due to rate limit: {orchestrator.stats['workflow_stopped_due_to_rate_limit']}")
            
            # Simulate a rate limit hit
            logger.info("Simulating rate limit hit...")
            orchestrator.stats['rate_limit_hits'] = 1
            orchestrator.stats['last_rate_limit_time'] = datetime.utcnow()
            orchestrator.stats['workflow_stopped_due_to_rate_limit'] = True
            orchestrator.is_running = False
            
            # Test workflow status after rate limit
            logger.info("Testing workflow status after rate limit...")
            status = orchestrator.get_workflow_status()
            
            logger.info(f"Workflow running: {status['is_running']}")
            logger.info(f"Rate limiting status: {status['rate_limiting']['status']}")
            logger.info(f"Stopped due to rate limit: {status['rate_limiting']['workflow_stopped_due_to_rate_limit']}")
            
            # Test reset functionality
            logger.info("Testing rate limit state reset...")
            orchestrator.reset_rate_limit_state()
            
            logger.info(f"Stopped due to rate limit after reset: {orchestrator.stats['workflow_stopped_due_to_rate_limit']}")
            
            # Test restart with reset
            logger.info("Testing workflow restart with rate limit reset...")
            orchestrator.start_workflow(enable_rss=False, enable_backfill=False)
            
            logger.info(f"Workflow running after restart: {orchestrator.is_running}")
            logger.info(f"Stopped due to rate limit after restart: {orchestrator.stats['workflow_stopped_due_to_rate_limit']}")
            
            # Test AI analysis during stopped state
            logger.info("Testing AI analysis during stopped workflow...")
            orchestrator.is_running = False  # Simulate stopped state
            success, metadata = orchestrator._perform_ai_analysis(bill)
            
            if not success:
                logger.info("✅ Correctly skipped analysis when workflow is stopped")
            else:
                logger.error("❌ Analysis should have been skipped when workflow is stopped")
            
            logger.info("✅ Rate limit stop behavior test completed")
            
    except Exception as e:
        logger.error(f"Error testing rate limit stop behavior: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_rate_limit_stop() 