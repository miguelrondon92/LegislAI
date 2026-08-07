#!/usr/bin/env python3
"""
Test script to verify backoff logic for 429 rate limit errors
"""

import os
import sys
import logging
import time
from datetime import datetime, timedelta

# Add the current directory to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from db_models import Bill
from services.enhanced_ai_analyzer import EnhancedAIAnalyzer
from services.workflow_orchestrator import WorkflowOrchestrator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_backoff_logic():
    """Test the backoff logic with a small bill"""
    try:
        with app.app_context():
            logger.info("Testing Backoff Logic for Rate Limit Handling")
            
            # Get a small bill for testing
            bill = db.session.query(Bill).filter(
                Bill.ai_analysis.is_(None)
            ).first()
            
            if not bill:
                logger.error("No bills without AI analysis found for testing")
                return
            
            logger.info(f"Testing with bill: {bill.get_bill_identifier()} - {bill.title[:50]}...")
            
            # Create workflow orchestrator
            orchestrator = WorkflowOrchestrator()
            
            # Test rate limit pause logic
            logger.info("Testing rate limit pause logic...")
            
            # Simulate a rate limit hit
            orchestrator.stats['rate_limit_hits'] = 1
            orchestrator.stats['last_rate_limit_time'] = datetime.utcnow()
            orchestrator.stats['rate_limit_pause_until'] = datetime.utcnow() + timedelta(minutes=1)  # 1 minute pause
            
            # Try to analyze a bill during pause
            logger.info("Attempting analysis during rate limit pause...")
            success, metadata, _analysis_ran = orchestrator._perform_ai_analysis(bill)
            
            if not success:
                logger.info("✅ Correctly skipped analysis during rate limit pause")
            else:
                logger.error("❌ Analysis should have been skipped during pause")
            
            # Wait for pause to expire
            logger.info("Waiting for rate limit pause to expire...")
            time.sleep(2)  # Wait 2 seconds
            
            # Clear the pause manually for testing
            orchestrator.stats['rate_limit_pause_until'] = None
            
            # Test normal analysis (this will likely hit rate limits in real scenario)
            logger.info("Testing normal analysis (may hit rate limits)...")
            success, metadata, _analysis_ran = orchestrator._perform_ai_analysis(bill)
            
            if success:
                logger.info("✅ Analysis completed successfully")
            else:
                logger.info("⚠️ Analysis failed (likely due to rate limiting)")
                logger.info(f"Rate limit hits: {orchestrator.stats['rate_limit_hits']}")
                if orchestrator.stats['rate_limit_pause_until']:
                    logger.info(f"Paused until: {orchestrator.stats['rate_limit_pause_until']}")
            
            # Test backoff configuration
            logger.info("Testing backoff configuration...")
            analyzer = EnhancedAIAnalyzer()
            logger.info(f"Max retries: {analyzer.max_retries}")
            logger.info(f"Base delay: {analyzer.base_delay}s")
            logger.info(f"Max delay: {analyzer.max_delay}s")
            logger.info(f"Backoff multiplier: {analyzer.backoff_multiplier}")
            
            # Test delay calculation
            for attempt in range(4):
                delay = analyzer._calculate_backoff_delay(attempt)
                logger.info(f"Attempt {attempt + 1} delay: {delay:.2f}s")
            
            logger.info("✅ Backoff logic test completed")
            
    except Exception as e:
        logger.error(f"Error testing backoff logic: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_backoff_logic() 