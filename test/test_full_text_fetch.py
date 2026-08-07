#!/usr/bin/env python3
"""
Test script to verify full text fetching from Congress API
"""

import os
import sys
import logging

# Add the current directory to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from db_models import Bill
from services.congress_api import CongressAPI
from services.workflow_orchestrator import WorkflowOrchestrator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_full_text_fetching():
    """Test fetching full text from Congress API"""
    try:
        with app.app_context():
            logger.info("Testing Full Text Fetching from Congress API")
            logger.info("=" * 50)
            
            # Get a bill that doesn't have AI analysis
            bill = Bill.query.filter(
                (Bill.ai_analysis.is_(None)) | (Bill.ai_analysis == '')
            ).first()
            
            if not bill:
                logger.info("No bills found without AI analysis")
                return True
            
            logger.info(f"Testing with bill: {bill.get_bill_identifier()}")
            logger.info(f"Title: {bill.title}")
            
            # Test Congress API text fetching
            congress_api = CongressAPI()
            full_text = congress_api.get_bill_text(bill.congress, bill.bill_type, bill.bill_number)
            
            if full_text:
                logger.info(f"✅ Successfully fetched full text")
                logger.info(f"   Length: {len(full_text):,} characters")
                logger.info(f"   Preview: {full_text[:200]}...")
                
                # Test workflow orchestrator
                logger.info("\nTesting Workflow Orchestrator with fetched text...")
                orchestrator = WorkflowOrchestrator()
                
                # Create a workflow item
                from services.workflow_orchestrator import WorkflowItem, WorkflowStatus
                from datetime import datetime
                
                workflow_item = WorkflowItem(
                    bill_identifier=bill.get_bill_identifier(),
                    congress=bill.congress,
                    bill_type=bill.bill_type,
                    bill_number=bill.bill_number,
                    title=bill.title,
                    source='test',
                    discovered_at=datetime.utcnow(),
                    status=WorkflowStatus.PENDING,
                    bill_id=bill.id
                )
                
                # Process the workflow item
                logger.info("Processing workflow item...")
                orchestrator._process_workflow_item(workflow_item)
                
                # Check results
                if workflow_item.status == WorkflowStatus.COMPLETED:
                    logger.info("✅ Workflow processing completed successfully")
                    if workflow_item.analysis_completed:
                        logger.info("✅ AI analysis completed")
                        
                        # Check if analysis was stored
                        bill.refresh()
                        analysis = bill.get_ai_analysis()
                        if analysis:
                            logger.info("✅ AI analysis stored in database")
                            if 'policy_implications' in analysis:
                                policy_data = analysis['policy_implications']
                                primary_area = policy_data.get('primary_policy_area', 'Unknown')
                                logger.info(f"   Primary policy area: {primary_area}")
                        else:
                            logger.warning("❌ AI analysis not stored in database")
                    else:
                        logger.warning("❌ AI analysis not completed")
                else:
                    logger.error(f"❌ Workflow processing failed: {workflow_item.error_message}")
                
                return True
            else:
                logger.warning(f"❌ Could not fetch full text for {bill.get_bill_identifier()}")
                logger.info("This might be normal for some bill types (resolutions, etc.)")
                return False
                
    except Exception as e:
        logger.error(f"❌ Test failed: {str(e)}")
        return False

def main():
    """Main test function"""
    logger.info("Starting Full Text Fetching Test")
    logger.info("=" * 60)
    
    try:
        success = test_full_text_fetching()
        
        if success:
            logger.info("\n✅ Full text fetching test completed successfully!")
            logger.info("The workflow can now fetch full text from Congress API for AI analysis.")
        else:
            logger.warning("\n⚠️ Full text fetching test had issues.")
            logger.info("This might be normal for some bill types that don't have full text available.")
            
    except Exception as e:
        logger.error(f"❌ Test suite failed with error: {str(e)}")

if __name__ == "__main__":
    main() 