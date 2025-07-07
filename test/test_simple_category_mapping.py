#!/usr/bin/env python3
"""
Simple test script to verify bill_category_mapping population with a smaller bill
"""

import os
import sys
import logging

# Add the current directory to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from db_models import Bill, BillCategoryMapping, PolicyCategory
from services.congress_api import CongressAPI
from services.workflow_orchestrator import WorkflowOrchestrator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_simple_category_mapping():
    """Test with a smaller bill that's more likely to complete"""
    try:
        with app.app_context():
            logger.info("Testing Simple Bill Category Mapping")
            logger.info("=" * 50)
            
            # First, check current state
            initial_mappings = BillCategoryMapping.query.count()
            initial_categories = PolicyCategory.query.count()
            logger.info(f"Initial state: {initial_mappings} mappings, {initial_categories} categories")
            
            # Test with much smaller bills - try resolutions or simple bills
            test_bills = [
                (119, 'hres', 123),  # Simple House resolution
                (119, 'sres', 45),   # Simple Senate resolution
                (118, 'hjres', 12),  # Simple joint resolution
                (117, 'hr', 1234),   # Simple House bill
            ]
            
            for congress, bill_type, bill_number in test_bills:
                logger.info(f"\nTrying bill: {congress}-{bill_type.upper()}{bill_number}")
                
                # Check if bill already exists in database
                existing_bill = Bill.query.filter_by(
                    congress=congress,
                    bill_type=bill_type,
                    bill_number=bill_number
                ).first()
                
                if existing_bill:
                    logger.info(f"Bill already exists in database: {existing_bill.get_bill_identifier()}")
                    bill = existing_bill
                else:
                    logger.info("Bill not in database, fetching from Congress API...")
                    
                    # Fetch bill data from Congress API
                    congress_api = CongressAPI()
                    bill_data = congress_api.get_bill_details(congress, bill_type, bill_number)
                    
                    if not bill_data:
                        logger.warning(f"Could not fetch bill data for {congress}-{bill_type.upper()}{bill_number}")
                        continue
                    
                    # Create bill in database
                    bill = Bill(
                        congress=congress,
                        bill_type=bill_type,
                        bill_number=bill_number,
                        title=bill_data.get('title', f'Bill {congress}-{bill_type.upper()}{bill_number}'),
                        summary=bill_data.get('summary', ''),
                        version=1,
                        active=True
                    )
                    
                    db.session.add(bill)
                    db.session.commit()
                    logger.info(f"Created bill in database: {bill.get_bill_identifier()}")
                
                # Verify bill has no AI analysis yet
                if bill.get_ai_analysis():
                    logger.info("Bill already has AI analysis, clearing it for testing...")
                    bill.set_ai_analysis(None)
                    db.session.commit()
                
                # Test Congress API text fetching
                congress_api = CongressAPI()
                full_text = congress_api.get_bill_text(congress, bill_type, bill_number)
                
                if not full_text:
                    logger.warning(f"Could not fetch full text for {bill.get_bill_identifier()}")
                    continue
                
                text_length = len(full_text)
                logger.info(f"✅ Successfully fetched full text ({text_length:,} characters)")
                
                # Skip if text is too large (over 200K characters for faster testing)
                if text_length > 200000:
                    logger.info(f"Text too large ({text_length:,} chars), trying next bill...")
                    continue
                
                # Create workflow orchestrator and process the bill
                logger.info("Processing bill through workflow orchestrator...")
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
                logger.info("Running workflow processing...")
                orchestrator._process_workflow_item(workflow_item)
                
                # Check results
                logger.info("Checking workflow results...")
                
                if workflow_item.status == WorkflowStatus.COMPLETED:
                    logger.info("✅ Workflow processing completed successfully")
                    
                    if workflow_item.analysis_completed:
                        logger.info("✅ AI analysis completed")
                        
                        # Refresh bill from database
                        db.session.refresh(bill)
                        
                        # Check if analysis was stored
                        analysis = bill.get_ai_analysis()
                        if analysis:
                            logger.info("✅ AI analysis stored in database")
                            
                            # Check for policy categories in analysis
                            if 'policy_implications' in analysis:
                                policy_data = analysis['policy_implications']
                                categories = policy_data.get('categories', [])
                                logger.info(f"   Found {len(categories)} policy categories in analysis")
                                
                                for i, cat in enumerate(categories[:3]):  # Show first 3
                                    area = cat.get('area', 'Unknown')
                                    impact = cat.get('impact_level', 'Unknown')
                                    logger.info(f"   Category {i+1}: {area} (impact: {impact})")
                            else:
                                logger.warning("❌ No policy_implications found in analysis")
                        else:
                            logger.warning("❌ AI analysis not stored in database")
                            
                        # Check if category mappings were created
                        final_mappings = BillCategoryMapping.query.count()
                        final_categories = PolicyCategory.query.count()
                        
                        logger.info(f"Final state: {final_mappings} mappings, {final_categories} categories")
                        
                        if final_mappings > initial_mappings:
                            logger.info(f"✅ Successfully created {final_mappings - initial_mappings} category mappings!")
                            
                            # Show some details about the mappings
                            bill_mappings = BillCategoryMapping.query.filter_by(bill_id=bill.id).all()
                            logger.info(f"   Bill has {len(bill_mappings)} category mappings:")
                            
                            for mapping in bill_mappings:
                                category = PolicyCategory.query.get(mapping.policy_category_id)
                                category_name = category.name if category else "Unknown"
                                logger.info(f"     - {category_name} (relevance: {mapping.relevance_score}, sneakiness: {mapping.sneakiness_score})")
                            
                            return True
                        else:
                            logger.warning("❌ No category mappings were created")
                    else:
                        logger.warning("❌ AI analysis not completed")
                else:
                    logger.error(f"❌ Workflow processing failed: {workflow_item.error_message}")
            
            logger.warning("❌ No bills were successfully processed")
            return False
                
    except Exception as e:
        logger.error(f"❌ Test failed: {str(e)}")
        return False

def main():
    """Main test function"""
    logger.info("Starting Simple Bill Category Mapping Test")
    logger.info("=" * 60)
    
    try:
        success = test_simple_category_mapping()
        
        if success:
            logger.info("\n✅ Bill category mapping test completed successfully!")
            logger.info("The workflow can now populate bill_category_mapping table.")
        else:
            logger.warning("\n⚠️ Bill category mapping test had issues.")
            
    except Exception as e:
        logger.error(f"❌ Test suite failed with error: {str(e)}")

if __name__ == "__main__":
    main() 