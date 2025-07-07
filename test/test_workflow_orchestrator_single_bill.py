#!/usr/bin/env python3
"""
Test the workflow orchestrator with exactly 1 bill (backfill mode)
- Ensures only 1 bill is present without AI analysis
- Runs the orchestrator to process that bill
- Prints/logs the results
"""
import os
import sys
import logging
from datetime import datetime

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from db_models import Bill, BillCategoryMapping
from services.workflow_orchestrator import WorkflowOrchestrator

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Also set orchestrator and analyzer loggers to DEBUG and add stream handler
for log_name in [
    'services.workflow_orchestrator',
    'services.enhanced_ai_analyzer',
    'services.ai_analyzer',
    'services.bill_processor',
    'services.congress_api',
]:
    l = logging.getLogger(log_name)
    l.setLevel(logging.DEBUG)
    if not any(isinstance(h, logging.StreamHandler) for h in l.handlers):
        l.addHandler(logging.StreamHandler(sys.stdout))

def setup_single_bill():
    """Ensure there is exactly 1 bill without AI analysis in the DB."""
    with app.app_context():
        from db_models import Alert, WatchlistItem, UserBillAlignment, BillAction, BillCategoryMapping
        
        # Remove all bills except one (for test isolation)
        bills = db.session.query(Bill).all()
        if len(bills) > 1:
            # Keep the most recent bill
            keep_bill = sorted(bills, key=lambda b: b.id, reverse=True)[0]
            
            # Delete all dependent data for bills we're removing
            for bill in bills:
                if bill.id != keep_bill.id:
                    logger.info(f"Cleaning up dependent data for bill {bill.get_bill_identifier()}")
                    
                    # Delete in order: child tables first, then parent
                    deleted_alerts = db.session.query(Alert).filter_by(bill_id=bill.id).delete()
                    deleted_watchlist = db.session.query(WatchlistItem).filter_by(bill_id=bill.id).delete()
                    deleted_alignments = db.session.query(UserBillAlignment).filter_by(bill_id=bill.id).delete()
                    deleted_actions = db.session.query(BillAction).filter_by(bill_id=bill.id).delete()
                    deleted_categories = db.session.query(BillCategoryMapping).filter_by(bill_id=bill.id).delete()
                    
                    logger.info(f"  - Deleted {deleted_alerts} alerts")
                    logger.info(f"  - Deleted {deleted_watchlist} watchlist items")
                    logger.info(f"  - Deleted {deleted_alignments} user alignments")
                    logger.info(f"  - Deleted {deleted_actions} bill actions")
                    logger.info(f"  - Deleted {deleted_categories} category mappings")
                    
                    # Now safe to delete the bill
                    db.session.delete(bill)
            
            db.session.commit()
            logger.info(f"Deleted all but 1 bill (kept {keep_bill.get_bill_identifier()})")
            bill = keep_bill
        elif len(bills) == 1:
            bill = bills[0]
        else:
            # Create a dummy bill for testing
            bill = Bill(
                congress=119,
                bill_type='s',
                bill_number=9999,
                title='Test Bill for Workflow Orchestrator',
                summary='A test bill to verify workflow orchestrator end-to-end.',
                introduced_date=datetime.utcnow(),
                status='introduced'
            )
            db.session.add(bill)
            db.session.commit()
            logger.info(f"Created test bill: {bill.get_bill_identifier()}")
        
        # Remove AI analysis and category mappings for this bill
        bill.ai_analysis = None
        db.session.query(BillCategoryMapping).filter_by(bill_id=bill.id).delete()
        db.session.commit()
        logger.info(f"Reset AI analysis and category mappings for bill {bill.get_bill_identifier()}")
        return bill

def run_workflow_on_single_bill():
    """Run the workflow orchestrator backfill for a single bill."""
    with app.app_context():
        # Setup test DB state
        bill = setup_single_bill()
        logger.info(f"Ready to process bill: {bill.get_bill_identifier()} - {bill.title}")
        # Patch the orchestrator to only process 1 bill in backfill
        orchestrator = WorkflowOrchestrator()
        # Monkeypatch the backfill limit to 1 for this test
        orig_run_backfill = orchestrator._run_backfill_processor
        def single_bill_backfill():
            logger.info("[TEST] Running single-bill backfill processor...")
            # Only process 1 bill
            bills_without_analysis = db.session.query(Bill).filter(
                (Bill.ai_analysis.is_(None)) | (Bill.ai_analysis == '')
            ).limit(1).all()
            for bill in bills_without_analysis:
                from services.workflow_orchestrator import WorkflowItem, WorkflowStatus
                workflow_item = WorkflowItem(
                    bill_identifier=bill.get_bill_identifier(),
                    congress=bill.congress,
                    bill_type=bill.bill_type,
                    bill_number=bill.bill_number,
                    title=bill.title or f"Bill {bill.get_bill_identifier()}",
                    source='backfill',
                    discovered_at=datetime.utcnow(),
                    status=WorkflowStatus.PENDING,
                    bill_id=bill.id
                )
                with orchestrator.processing_lock:
                    orchestrator.workflow_queue.append(workflow_item)
                logger.info(f"[TEST] Added bill to workflow queue: {workflow_item.bill_identifier}")
        orchestrator._run_backfill_processor = single_bill_backfill
        # Run the backfill processor to populate the queue
        orchestrator._run_backfill_processor()
        print(f"[DEBUG] Workflow queue after backfill: {[item.bill_identifier for item in orchestrator.workflow_queue]}")
        
        # Process the workflow item directly instead of relying on the orchestrator's main loop
        if orchestrator.workflow_queue:
            workflow_item = orchestrator.workflow_queue[0]
            print(f"[DEBUG] Processing workflow item directly: {workflow_item.bill_identifier}")
            orchestrator._process_workflow_item(workflow_item)
            print(f"[DEBUG] Finished processing workflow item: {workflow_item.bill_identifier}")
        else:
            print("[DEBUG] No items in workflow queue to process")
        
        # Check results
        bill = db.session.query(Bill).get(bill.id)
        analysis = bill.get_ai_analysis()
        categories = db.session.query(BillCategoryMapping).filter_by(bill_id=bill.id).all()
        logger.info("\n=== TEST RESULTS ===")
        logger.info(f"AI analysis present: {'Yes' if analysis else 'No'}")
        logger.info(f"Category mappings: {len(categories)}")
        for mapping in categories:
            logger.info(f" - {mapping.policy_category_id}: {mapping.relevance_score}")
        logger.info("====================\n")
        if analysis and categories:
            logger.info("🎉 Workflow orchestrator test PASSED!")
        else:
            logger.error("❌ Workflow orchestrator test FAILED!")

if __name__ == "__main__":
    run_workflow_on_single_bill() 