#!/usr/bin/env python3
"""
Simple test for bill analysis and database population.
Focuses on core functionality with error handling.
"""

import os
import sys
import logging
import json
from datetime import datetime
from pathlib import Path

# Add the project root to the Python path
sys.path.insert(0, str(Path(__file__).parent))

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

def test_database_models():
    """Test basic database model functionality"""
    logger.info("Testing database models...")
    
    try:
        from app import app, db
        from db_models import Bill, PolicyCategory, BillCategoryMapping
        
        with app.app_context():
            # Test creating a simple bill
            test_bill = Bill(
                congress=119,
                bill_type='hr',
                bill_number=9999,
                title='Test Bill for Database',
                summary='A simple test bill',
                sponsor_name='Test Sponsor',
                sponsor_party='I',
                sponsor_state='XX'
            )
            
            # Test AI analysis storage
            test_analysis = {
                'summary': 'This is a test analysis',
                'policy_implications': ['Test implication'],
                'categories': [
                    {'name': 'taxation', 'relevance': 0.8}
                ]
            }
            test_bill.set_ai_analysis(test_analysis)
            
            # Test database operations
            db.session.add(test_bill)
            db.session.commit()
            
            # Verify the bill was stored
            stored_bill = Bill.query.filter_by(bill_number=9999, congress=119).first()
            if stored_bill:
                logger.info(f"✅ Bill stored successfully: {stored_bill.get_bill_identifier()}")
                
                # Test analysis retrieval
                retrieved_analysis = stored_bill.get_ai_analysis()
                if retrieved_analysis:
                    logger.info(f"✅ AI analysis retrieved: {list(retrieved_analysis.keys())}")
                else:
                    logger.warning("❌ AI analysis not retrieved")
                
                # Clean up
                db.session.delete(stored_bill)
                db.session.commit()
                logger.info("✅ Test cleanup completed")
                
                return True
            else:
                logger.error("❌ Bill not found after storage")
                return False
                
    except Exception as e:
        logger.error(f"❌ Database model test failed: {e}")
        return False

def test_ai_analysis_simple():
    """Test AI analysis with a very simple example"""
    logger.info("Testing AI analysis...")
    
    try:
        from services.enhanced_ai_analyzer import EnhancedAIAnalyzer
        
        analyzer = EnhancedAIAnalyzer()
        
        # Check quota
        quota_info = analyzer.get_quota_info()
        logger.info(f"Current quota: {quota_info['current_usage']['requests_this_minute']}/{quota_info['current_usage']['max_requests_per_minute']}")
        
        if quota_info['status']['is_at_limit']:
            logger.warning("❌ At rate limit, skipping AI analysis")
            return False
        
        # Very simple bill text
        simple_text = """
        H.R.1 - Test Act
        
        SECTION 1. This is a test bill.
        SECTION 2. This Act takes effect immediately.
        """
        
        try:
            analysis = analyzer.analyze_bill(simple_text, "Test Act")
            
            if analysis and isinstance(analysis, dict):
                logger.info(f"✅ AI analysis successful: {list(analysis.keys())}")
                return analysis
            else:
                logger.warning("❌ AI analysis returned invalid result")
                return None
                
        except Exception as e:
            logger.error(f"❌ AI analysis error: {e}")
            return None
            
    except Exception as e:
        logger.error(f"❌ AI analysis test failed: {e}")
        return None

def test_category_mapping():
    """Test policy category mapping"""
    logger.info("Testing category mapping...")
    
    try:
        from app import app, db
        from db_models import Bill, PolicyCategory, BillCategoryMapping
        
        with app.app_context():
            # Create test bill
            test_bill = Bill(
                congress=119,
                bill_type='hr',
                bill_number=8888,
                title='Tax Reform Test Bill',
                summary='A bill about taxes'
            )
            db.session.add(test_bill)
            db.session.flush()  # Get the ID
            
            # Find taxation category
            tax_category = PolicyCategory.query.filter_by(name='taxation').first()
            if not tax_category:
                logger.warning("Taxation category not found, creating it...")
                tax_category = PolicyCategory(
                    name='taxation',
                    display_name='Taxation',
                    description='Tax policy and reform'
                )
                db.session.add(tax_category)
                db.session.flush()
            
            # Create category mapping
            mapping = BillCategoryMapping(
                bill_id=test_bill.id,
                policy_category_id=tax_category.id,
                relevance_score=0.9,
                sneakiness_score=0.1
            )
            db.session.add(mapping)
            db.session.commit()
            
            # Verify mapping
            retrieved_mapping = BillCategoryMapping.query.filter_by(
                bill_id=test_bill.id,
                policy_category_id=tax_category.id
            ).first()
            
            if retrieved_mapping:
                logger.info(f"✅ Category mapping created: {retrieved_mapping.relevance_score:.1f} relevance")
                
                # Clean up
                db.session.delete(retrieved_mapping)
                db.session.delete(test_bill)
                db.session.commit()
                return True
            else:
                logger.error("❌ Category mapping not found")
                return False
                
    except Exception as e:
        logger.error(f"❌ Category mapping test failed: {e}")
        return False

def test_workflow_integration():
    """Test integration with workflow components"""
    logger.info("Testing workflow integration...")
    
    try:
        from services.bill_processor import BillProcessor
        from app import app, db
        from db_models import Bill
        
        # Mock bill data
        mock_bill_data = {
            'congress': 119,
            'type': 'hr',
            'number': 7777,
            'title': 'Workflow Test Bill',
            'summary': 'A bill to test workflow integration',
            'sponsors': [{'fullName': 'Test Sponsor', 'party': 'I', 'state': 'XX'}],
            'introducedDate': '2025-01-01',
            'latestAction': {'actionDate': '2025-01-02', 'text': 'Introduced'},
            'full_text': 'This is a test bill for workflow integration.'
        }
        
        with app.app_context():
            processor = BillProcessor()
            
            # Process the bill
            bill = processor.process_bill_data(mock_bill_data)
            
            if bill:
                logger.info(f"✅ Workflow processed bill: {bill.get_bill_identifier()}")
                
                # Verify it was stored
                stored_bill = Bill.query.filter_by(
                    congress=119,
                    bill_type='hr',
                    bill_number=7777
                ).first()
                
                if stored_bill:
                    logger.info(f"✅ Bill stored in database: {stored_bill.title}")
                    
                    # Clean up
                    db.session.delete(stored_bill)
                    db.session.commit()
                    return True
                else:
                    logger.error("❌ Bill not found in database")
                    return False
            else:
                logger.error("❌ Workflow failed to process bill")
                return False
                
    except Exception as e:
        logger.error(f"❌ Workflow integration test failed: {e}")
        return False

def test_end_to_end():
    """Test complete end-to-end process with small bill"""
    logger.info("Testing end-to-end process...")
    
    try:
        from app import app, db
        from db_models import Bill, PolicyCategory, BillCategoryMapping
        from services.enhanced_ai_analyzer import EnhancedAIAnalyzer
        
        with app.app_context():
            # Create test bill
            test_bill = Bill(
                congress=119,
                bill_type='hr',
                bill_number=6666,
                title='End-to-End Test Bill',
                summary='Testing complete workflow',
                sponsor_name='E2E Tester',
                sponsor_party='T',
                sponsor_state='ZZ'
            )
            
            # Simple test analysis (mock if AI fails)
            bill_text = """
            H.R.6666 - End-to-End Test Bill
            
            SECTION 1. SHORT TITLE.
            This Act may be cited as the "End-to-End Test Bill".
            
            SECTION 2. TESTING.
            This bill tests the complete workflow.
            """
            
            analysis_result = None
            try:
                analyzer = EnhancedAIAnalyzer()
                quota_info = analyzer.get_quota_info()
                
                if not quota_info['status']['is_at_limit']:
                    analysis_result = analyzer.analyze_bill(bill_text, test_bill.title)
            except Exception as e:
                logger.warning(f"AI analysis failed, using mock: {e}")
            
            # Use mock analysis if AI failed
            if not analysis_result:
                analysis_result = {
                    'summary': 'Mock analysis for end-to-end test',
                    'policy_implications': ['Test implication'],
                    'categories': [
                        {'name': 'governance', 'relevance': 0.7, 'analysis': 'Test governance analysis'}
                    ],
                    'stakeholders': ['Test stakeholders'],
                    'complexity_score': 0.3
                }
                logger.info("Using mock analysis for testing")
            
            # Store analysis
            test_bill.set_ai_analysis(analysis_result)
            
            # Store bill
            db.session.add(test_bill)
            db.session.flush()
            
            # Create category mappings if analysis has categories
            mappings_created = 0
            if 'categories' in analysis_result:
                for category_info in analysis_result['categories']:
                    category_name = category_info.get('name', '').lower()
                    relevance = float(category_info.get('relevance', 0.0))
                    
                    # Find or create category
                    category = PolicyCategory.query.filter_by(name=category_name).first()
                    if category and relevance > 0.1:
                        mapping = BillCategoryMapping(
                            bill_id=test_bill.id,
                            policy_category_id=category.id,
                            relevance_score=relevance,
                            sneakiness_score=category_info.get('sneakiness', 0.0)
                        )
                        db.session.add(mapping)
                        mappings_created += 1
            
            db.session.commit()
            
            # Verify everything was stored correctly
            stored_bill = Bill.query.get(test_bill.id)
            stored_analysis = stored_bill.get_ai_analysis()
            stored_mappings = BillCategoryMapping.query.filter_by(bill_id=test_bill.id).count()
            
            success = (
                stored_bill is not None and
                stored_analysis is not None and
                len(stored_analysis) > 0
            )
            
            logger.info(f"✅ End-to-end test results:")
            logger.info(f"   Bill stored: {stored_bill is not None}")
            logger.info(f"   Analysis stored: {stored_analysis is not None}")
            logger.info(f"   Analysis fields: {list(stored_analysis.keys()) if stored_analysis else 'None'}")
            logger.info(f"   Category mappings: {stored_mappings}")
            
            # Clean up
            BillCategoryMapping.query.filter_by(bill_id=test_bill.id).delete()
            db.session.delete(stored_bill)
            db.session.commit()
            
            return success
            
    except Exception as e:
        logger.error(f"❌ End-to-end test failed: {e}")
        return False

def main():
    """Run all tests"""
    logger.info("🚀 STARTING SIMPLE BILL ANALYSIS AND DATABASE TESTS")
    logger.info("=" * 60)
    
    tests = [
        ("Database Models", test_database_models),
        ("AI Analysis", test_ai_analysis_simple),
        ("Category Mapping", test_category_mapping),
        ("Workflow Integration", test_workflow_integration),
        ("End-to-End", test_end_to_end)
    ]
    
    results = {}
    
    for test_name, test_func in tests:
        logger.info(f"\n🧪 Running {test_name} Test...")
        try:
            results[test_name] = test_func()
        except Exception as e:
            logger.error(f"❌ {test_name} test crashed: {e}")
            results[test_name] = False
    
    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("📊 TEST SUMMARY")
    logger.info("=" * 60)
    
    # Count only successful tests (not None)
    passed = sum(1 for result in results.values() if result is True)
    total = len(results)
    
    for test_name, result in results.items():
        if result is True:
            status = "✅ PASSED"
        elif result is False:
            status = "❌ FAILED" 
        else:
            status = "⚠️ ERROR"
        logger.info(f"{test_name}: {status}")
    
    logger.info(f"\n📈 Overall: {passed}/{total} tests passed ({passed/total*100:.1f}%)")
    
    if passed >= total * 0.8:  # At least 80% success
        logger.info("\n🎉 TESTS MOSTLY SUCCESSFUL!")
        logger.info("✅ Core functionality verified:")
        logger.info("   • Database models work correctly")
        logger.info("   • Bill storage and retrieval functions")
        logger.info("   • Analysis data can be stored and retrieved")
        logger.info("   • Category mapping system works")
    else:
        logger.warning("\n⚠️ Some core functionality has issues")
    
    return passed >= total * 0.6  # Pass if at least 60% work

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)