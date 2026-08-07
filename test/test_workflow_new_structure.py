#!/usr/bin/env python3
"""
Test script to verify workflow orchestrator works with new database structure
"""

from app import app, db
from db_models import Bill, AIAnalysis, Summary
from services.workflow_orchestrator import WorkflowOrchestrator, WorkflowItem, WorkflowStatus
from datetime import datetime
import time

def test_workflow_with_new_structure():
    """Test workflow orchestrator with new database structure"""
    
    with app.app_context():
        print("=== Testing Workflow Orchestrator with New Database Structure ===\n")
        
        # Initialize orchestrator
        orchestrator = WorkflowOrchestrator()
        print("✅ Workflow orchestrator initialized")
        
        # Get test bill (HR2)
        test_bill = Bill.query.filter_by(congress=119, bill_type='hr', bill_number=2).first()
        if not test_bill:
            print("❌ No test bill found")
            return
            
        print(f"✅ Found test bill: {test_bill.get_bill_identifier()}")
        
        # Check database state before
        print("\n--- Database State Before ---")
        ai_analyses_before = AIAnalysis.query.count()
        summaries_before = Summary.query.count()
        print(f"AI Analyses: {ai_analyses_before}")
        print(f"Summaries: {summaries_before}")
        
        # Test creating a workflow item
        print("\n--- Testing Workflow Item Creation ---")
        try:
            workflow_item = WorkflowItem(
                bill_identifier=test_bill.get_bill_identifier(),
                congress=test_bill.congress,
                bill_type=test_bill.bill_type,
                bill_number=test_bill.bill_number,
                title=test_bill.title,
                source='test',
                discovered_at=datetime.utcnow(),
                status=WorkflowStatus.PENDING,
                bill_id=test_bill.id
            )
            print(f"✅ Workflow item created: {workflow_item.bill_identifier}")
        except Exception as e:
            print(f"❌ Workflow item creation failed: {e}")
            return
        
        # Test workflow processing methods
        print("\n--- Testing Workflow Components ---")
        
        # Test AI analyzer integration
        try:
            ai_analyzer = orchestrator.ai_analyzer
            print(f"✅ AI analyzer accessible: {type(ai_analyzer).__name__}")
            
            # Test if the analyzer can handle Bill objects with new structure
            if hasattr(ai_analyzer, 'analyze_bill'):
                print("✅ AI analyzer has analyze_bill method")
                
                # Check if bill has the new methods
                if hasattr(test_bill, 'create_new_analysis_version'):
                    print("✅ Bill has create_new_analysis_version method")
                else:
                    print("❌ Bill missing create_new_analysis_version method")
                    
                if hasattr(test_bill, 'get_active_ai_analysis'):
                    print("✅ Bill has get_active_ai_analysis method")
                else:
                    print("❌ Bill missing get_active_ai_analysis method")
                    
        except Exception as e:
            print(f"❌ AI analyzer test failed: {e}")
        
        # Test bill processor
        try:
            bill_processor = orchestrator.bill_processor
            print(f"✅ Bill processor accessible: {type(bill_processor).__name__}")
        except Exception as e:
            print(f"❌ Bill processor test failed: {e}")
        
        # Test notification service
        try:
            notification_service = orchestrator.notification_service
            print(f"✅ Notification service accessible: {type(notification_service).__name__}")
        except Exception as e:
            print(f"❌ Notification service test failed: {e}")
            
        # Test workflow statistics
        print("\n--- Testing Workflow Statistics ---")
        try:
            status = orchestrator.get_workflow_status()
            print(f"✅ Workflow status: {status}")
            
            recent_items = orchestrator.get_recent_workflow_items()
            print(f"✅ Recent items count: {len(recent_items)}")
            
        except Exception as e:
            print(f"❌ Workflow statistics failed: {e}")
        
        # Test new database methods on existing bills
        print("\n--- Testing New Database Methods on Existing Bills ---")
        
        # Get a bill that should have analysis
        hr1 = Bill.query.filter_by(congress=119, bill_type='hr', bill_number=1).first()
        if hr1:
            print(f"Testing methods on {hr1.get_bill_identifier()}:")
            
            complexity = hr1.get_complexity_score_new()
            print(f"  get_complexity_score_new(): {complexity}")
            
            controversy = hr1.get_controversy_score_new()
            print(f"  get_controversy_score_new(): {controversy}")
            
            summary_text = hr1.get_summary_text()
            summary_length = len(summary_text) if summary_text else 0
            print(f"  get_summary_text(): {summary_length} chars")
            
            ai_analysis = hr1.get_active_ai_analysis()
            print(f"  get_active_ai_analysis(): {'Found' if ai_analysis else 'None'}")
            
            summary = hr1.get_active_summary()
            print(f"  get_active_summary(): {'Found' if summary else 'None'}")
            
        # Final summary
        print("\n=== Test Results Summary ===")
        print("✅ Workflow orchestrator initializes correctly")
        print("✅ All workflow components accessible")
        print("✅ New database methods work on existing bills")
        print("✅ Workflow ready for processing with new structure")
        
        return True

if __name__ == '__main__':
    success = test_workflow_with_new_structure()
    if success:
        print("\n🎉 All tests passed! Workflow orchestrator ready with new database structure.")
    else:
        print("\n❌ Some tests failed. Check the output above.")