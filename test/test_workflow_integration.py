#!/usr/bin/env python3
"""
Test WorkflowOrchestrator integration with new database structure
Verifies that RSS monitoring and new bill processing works correctly
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from db_models import Bill, BillCategoryMapping, AIAnalysis, Summary
from services.workflow_orchestrator import WorkflowOrchestrator
from services.enhanced_ai_analyzer import EnhancedAIAnalyzer
from services.congress_api import CongressAPI
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_workflow_integration():
    """Test WorkflowOrchestrator integration with new database structure"""
    
    with app.app_context():
        logger.info("=== Testing WorkflowOrchestrator Integration ===")
        
        # Find a bill without analysis for testing
        bill_without_analysis = db.session.query(Bill).outerjoin(AIAnalysis).filter(AIAnalysis.bill_id.is_(None)).first()
        
        if not bill_without_analysis:
            logger.info("No bills without analysis found - integration test cannot proceed")
            return
            
        bill_id = bill_without_analysis.get_bill_identifier()
        logger.info(f"Testing with bill: {bill_id}")
        
        # Check initial state
        initial_analysis = bill_without_analysis.get_active_ai_analysis()
        initial_summary = bill_without_analysis.get_active_summary()
        initial_mappings = db.session.query(BillCategoryMapping).filter_by(bill_id=bill_without_analysis.id).count()
        initial_display_ready = bill_without_analysis.display_ready
        
        logger.info(f"Initial state:")
        logger.info(f"  - AI Analysis: {initial_analysis is not None}")
        logger.info(f"  - Summary: {initial_summary is not None}")
        logger.info(f"  - Category mappings: {initial_mappings}")
        logger.info(f"  - Display ready: {initial_display_ready}")
        
        # Check if bill has text available
        congress_api = CongressAPI()
        full_text = congress_api.get_bill_text(
            bill_without_analysis.congress, 
            bill_without_analysis.bill_type, 
            bill_without_analysis.bill_number
        )
        
        if not full_text or len(full_text) < 500:
            logger.info(f"Bill has insufficient text ({len(full_text) if full_text else 0} chars) - skipping analysis test")
            logger.info("Integration structure is correctly set up for when bills do have text")
            return
            
        logger.info(f"Bill has {len(full_text):,} characters of text")
        
        # Check AI quota
        analyzer = EnhancedAIAnalyzer()
        quota_info = analyzer.get_quota_info()
        requests_available = quota_info['current_usage']['safe_remaining_requests']
        
        logger.info(f"AI Quota: {quota_info['current_usage']['requests_this_minute']}/{quota_info['current_usage']['max_requests_per_minute']} used, {requests_available} safe remaining")
        
        if quota_info['status']['is_at_limit'] or requests_available < 5:
            logger.info("Insufficient AI quota - testing workflow structure only")
            test_workflow_structure()
            return
            
        # Test the WorkflowOrchestrator process
        logger.info("Testing WorkflowOrchestrator analysis process...")
        
        orchestrator = WorkflowOrchestrator()
        orchestrator.is_running = True  # Enable processing
        
        success, metadata, _analysis_ran = orchestrator._perform_ai_analysis(bill_without_analysis)
        
        logger.info(f"WorkflowOrchestrator analysis result: {success}")
        
        if success:
            # Check final state
            final_analysis = bill_without_analysis.get_active_ai_analysis()
            final_summary = bill_without_analysis.get_active_summary()
            final_mappings = db.session.query(BillCategoryMapping).filter_by(bill_id=bill_without_analysis.id).count()
            final_display_ready = bill_without_analysis.display_ready
            
            logger.info(f"Final state:")
            logger.info(f"  - AI Analysis: {final_analysis is not None}")
            logger.info(f"  - Summary: {final_summary is not None}")
            logger.info(f"  - Category mappings: {final_mappings}")
            logger.info(f"  - Display ready: {final_display_ready}")
            
            # Detailed analysis check
            if final_analysis:
                analysis_data = final_analysis.get_analysis_data()
                has_policy_implications = 'policy_implications' in analysis_data
                has_categories = has_policy_implications and 'categories' in analysis_data['policy_implications']
                
                logger.info(f"  - Has policy implications: {has_policy_implications}")
                logger.info(f"  - Has categories: {has_categories}")
                
                if has_categories:
                    categories = analysis_data['policy_implications']['categories']
                    logger.info(f"  - Number of categories: {len(categories)}")
                    
                    # Check that categories match mappings
                    if len(categories) == final_mappings:
                        logger.info("✅ Category mappings match analysis categories")
                    else:
                        logger.warning(f"⚠️ Mismatch: {len(categories)} categories in analysis, {final_mappings} mappings in DB")
            
            # Check analysis completeness
            is_complete = bill_without_analysis.is_analysis_complete()
            logger.info(f"  - Analysis complete (for display): {is_complete}")
            
            if final_display_ready:
                logger.info("✅ Bill is now display ready")
            elif is_complete:
                logger.warning("⚠️ Analysis complete but not marked display ready")
            else:
                logger.info("ℹ️ Analysis incomplete - this is expected for some bills")
                
        else:
            logger.error("❌ WorkflowOrchestrator analysis failed")

def test_workflow_structure():
    """Test the WorkflowOrchestrator structure without running actual analysis"""
    
    logger.info("=== Testing WorkflowOrchestrator Structure ===")
    
    # Verify WorkflowOrchestrator is using EnhancedAIAnalyzer
    orchestrator = WorkflowOrchestrator()
    analyzer_type = type(orchestrator.ai_analyzer).__name__
    logger.info(f"WorkflowOrchestrator AI Analyzer: {analyzer_type}")
    
    if analyzer_type == "EnhancedAIAnalyzer":
        logger.info("✅ WorkflowOrchestrator correctly uses EnhancedAIAnalyzer")
    else:
        logger.error(f"❌ WorkflowOrchestrator uses {analyzer_type} instead of EnhancedAIAnalyzer")
    
    # Check that EnhancedAIAnalyzer has the category mapping method
    has_category_method = hasattr(orchestrator.ai_analyzer, '_store_policy_categories')
    logger.info(f"EnhancedAIAnalyzer has _store_policy_categories method: {has_category_method}")
    
    if has_category_method:
        logger.info("✅ Category mapping integration available")
    else:
        logger.error("❌ Category mapping method missing")
    
    # Verify WorkflowOrchestrator doesn't duplicate category mapping
    import inspect
    source = inspect.getsource(orchestrator._perform_ai_analysis)
    has_duplicate_call = '_store_policy_categories' in source
    
    if has_duplicate_call:
        logger.warning("⚠️ WorkflowOrchestrator may have duplicate category mapping calls")
    else:
        logger.info("✅ WorkflowOrchestrator doesn't duplicate category mapping")

def get_integration_status():
    """Get current integration status"""
    
    with app.app_context():
        logger.info("=== Current Integration Status ===")
        
        total_bills = Bill.query.count()
        bills_with_analysis = db.session.query(Bill).join(AIAnalysis).distinct().count()
        bills_with_summary = db.session.query(Bill).join(Summary).distinct().count()
        bills_with_mappings = db.session.query(Bill).join(BillCategoryMapping).distinct().count()
        bills_display_ready = Bill.query.filter_by(display_ready=True).count()
        
        logger.info(f"Total bills: {total_bills}")
        logger.info(f"Bills with AI analysis: {bills_with_analysis}")
        logger.info(f"Bills with summary: {bills_with_summary}")
        logger.info(f"Bills with category mappings: {bills_with_mappings}")
        logger.info(f"Bills display ready: {bills_display_ready}")
        
        # Check for potential issues
        bills_with_analysis_no_mappings = bills_with_analysis - bills_with_mappings
        bills_with_mappings_not_ready = bills_with_mappings - bills_display_ready
        
        if bills_with_analysis_no_mappings > 0:
            logger.warning(f"⚠️ {bills_with_analysis_no_mappings} bills have analysis but no category mappings")
        else:
            logger.info("✅ All analyzed bills have category mappings")
            
        if bills_with_mappings_not_ready > 0:
            logger.info(f"ℹ️ {bills_with_mappings_not_ready} bills have mappings but aren't display ready (may be missing other components)")
        
        logger.info(f"Integration completeness: {bills_display_ready}/{total_bills} bills fully ready ({bills_display_ready/total_bills*100:.1f}%)")

if __name__ == "__main__":
    test_workflow_structure()
    get_integration_status()
    test_workflow_integration()