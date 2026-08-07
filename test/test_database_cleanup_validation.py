#!/usr/bin/env python3
"""
Test script to validate database cleanup and ensure no mock/test data exists.
This should be run after database cleanup to verify real data integrity.
"""

import os
import sys
import logging
import json
from pathlib import Path

# Add the project root to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

def test_no_mock_bills():
    """Test that no mock or test bills exist in database"""
    logger.info("Testing for mock/test bills...")
    
    try:
        from app import app, db
        from db_models import Bill
        
        with app.app_context():
            bills = Bill.query.all()
            logger.info(f"Found {len(bills)} bills in database")
            
            mock_bills = []
            for bill in bills:
                title_lower = bill.title.lower() if bill.title else ""
                sponsor_lower = bill.sponsor_name.lower() if bill.sponsor_name else ""
                
                # Check for test/mock indicators
                if any(keyword in title_lower for keyword in ['test', 'mock', 'fake', 'example']):
                    mock_bills.append(f"{bill.get_bill_identifier()} - Title contains mock keyword")
                
                if any(keyword in sponsor_lower for keyword in ['test', 'mock', 'fake']):
                    mock_bills.append(f"{bill.get_bill_identifier()} - Sponsor contains mock keyword")
                
                # Check for unrealistic bill numbers (common in tests)
                if bill.bill_number and bill.bill_number > 99999:
                    mock_bills.append(f"{bill.get_bill_identifier()} - Unrealistic bill number: {bill.bill_number}")
            
            if mock_bills:
                logger.error("❌ Found potential mock bills:")
                for mock_bill in mock_bills:
                    logger.error(f"   {mock_bill}")
                return False
            else:
                logger.info("✅ No mock bills found")
                return True
                
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        return False

def test_no_orphaned_mappings():
    """Test that no orphaned bill category mappings exist"""
    logger.info("Testing for orphaned bill category mappings...")
    
    try:
        from app import app, db
        from db_models import BillCategoryMapping
        
        with app.app_context():
            mappings = BillCategoryMapping.query.all()
            logger.info(f"Found {len(mappings)} bill category mappings")
            
            orphaned_mappings = []
            for mapping in mappings:
                if mapping.bill is None:
                    category_name = mapping.policy_category.display_name if mapping.policy_category else "Unknown"
                    orphaned_mappings.append(f"Mapping {mapping.id} -> {category_name} (no bill)")
            
            if orphaned_mappings:
                logger.error("❌ Found orphaned mappings:")
                for orphaned in orphaned_mappings:
                    logger.error(f"   {orphaned}")
                return False
            else:
                logger.info("✅ No orphaned mappings found")
                return True
                
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        return False

def test_ai_analysis_quality():
    """Test that AI analysis contains real data, not mock responses"""
    logger.info("Testing AI analysis quality...")
    
    try:
        from app import app, db
        from db_models import Bill
        
        with app.app_context():
            bills_with_analysis = Bill.query.filter(Bill.ai_analysis.isnot(None)).all()
            logger.info(f"Found {len(bills_with_analysis)} bills with AI analysis")
            
            mock_analysis = []
            for bill in bills_with_analysis:
                try:
                    analysis = json.loads(bill.ai_analysis)
                    analysis_text = json.dumps(analysis).lower()
                    
                    # Check for mock/test indicators in analysis
                    mock_indicators = ['mock', 'test', 'fake', 'example', 'dummy', 'placeholder']
                    for indicator in mock_indicators:
                        if indicator in analysis_text:
                            mock_analysis.append(f"{bill.get_bill_identifier()} - Contains '{indicator}' in analysis")
                            break
                    
                    # Check for overly generic analysis
                    if 'summary' in analysis and isinstance(analysis['summary'], dict):
                        summary_text = analysis['summary'].get('main_summary', '').lower()
                        if len(summary_text) < 50:  # Very short summaries might be mock
                            mock_analysis.append(f"{bill.get_bill_identifier()} - Suspiciously short summary")
                
                except json.JSONDecodeError:
                    mock_analysis.append(f"{bill.get_bill_identifier()} - Invalid JSON in analysis")
                except Exception as e:
                    logger.warning(f"Error checking analysis for {bill.get_bill_identifier()}: {e}")
            
            if mock_analysis:
                logger.error("❌ Found potential mock analysis:")
                for mock in mock_analysis:
                    logger.error(f"   {mock}")
                return False
            else:
                logger.info("✅ AI analysis appears to be real data")
                return True
                
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        return False

def test_real_congress_data():
    """Test that bills are from real Congress sessions with realistic data"""
    logger.info("Testing for real Congress data...")
    
    try:
        from app import app, db
        from db_models import Bill
        
        with app.app_context():
            bills = Bill.query.all()
            
            invalid_data = []
            for bill in bills:
                # Check Congress session is realistic (118th, 119th, etc.)
                if bill.congress < 100 or bill.congress > 130:
                    invalid_data.append(f"{bill.get_bill_identifier()} - Unrealistic Congress: {bill.congress}")
                
                # Check bill type is valid
                valid_types = ['hr', 's', 'hres', 'sres', 'hjres', 'sjres', 'hconres', 'sconres']
                if bill.bill_type not in valid_types:
                    invalid_data.append(f"{bill.get_bill_identifier()} - Invalid bill type: {bill.bill_type}")
                
                # Check for realistic bill numbers
                if bill.bill_number <= 0:
                    invalid_data.append(f"{bill.get_bill_identifier()} - Invalid bill number: {bill.bill_number}")
            
            if invalid_data:
                logger.error("❌ Found invalid Congress data:")
                for invalid in invalid_data:
                    logger.error(f"   {invalid}")
                return False
            else:
                logger.info("✅ All bills appear to be from real Congress sessions")
                return True
                
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        return False

def test_database_consistency():
    """Test overall database consistency"""
    logger.info("Testing database consistency...")
    
    try:
        from app import app, db
        from db_models import Bill, BillCategoryMapping, PolicyCategory
        
        with app.app_context():
            # Check that all mappings have valid foreign keys
            mappings = BillCategoryMapping.query.all()
            bills = Bill.query.all()
            categories = PolicyCategory.query.all()
            
            bill_ids = {bill.id for bill in bills}
            category_ids = {cat.id for cat in categories}
            
            consistency_errors = []
            
            for mapping in mappings:
                if mapping.bill_id not in bill_ids:
                    consistency_errors.append(f"Mapping {mapping.id} references non-existent bill_id {mapping.bill_id}")
                
                if mapping.policy_category_id not in category_ids:
                    consistency_errors.append(f"Mapping {mapping.id} references non-existent category_id {mapping.policy_category_id}")
            
            if consistency_errors:
                logger.error("❌ Database consistency errors:")
                for error in consistency_errors:
                    logger.error(f"   {error}")
                return False
            else:
                logger.info("✅ Database is consistent")
                return True
                
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        return False

def main():
    """Run all cleanup validation tests"""
    logger.info("🧹 DATABASE CLEANUP VALIDATION")
    logger.info("=" * 50)
    
    tests = [
        ("Mock Bills Check", test_no_mock_bills),
        ("Orphaned Mappings Check", test_no_orphaned_mappings),
        ("AI Analysis Quality Check", test_ai_analysis_quality),
        ("Real Congress Data Check", test_real_congress_data),
        ("Database Consistency Check", test_database_consistency),
    ]
    
    results = {}
    
    for test_name, test_func in tests:
        logger.info(f"\n🧪 Running {test_name}...")
        try:
            results[test_name] = test_func()
        except Exception as e:
            logger.error(f"❌ {test_name} crashed: {e}")
            results[test_name] = False
    
    # Summary
    logger.info("\n" + "=" * 50)
    logger.info("📊 CLEANUP VALIDATION SUMMARY")
    logger.info("=" * 50)
    
    passed = sum(1 for result in results.values() if result)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASSED" if result else "❌ FAILED"
        logger.info(f"{test_name}: {status}")
    
    logger.info(f"\n📈 Overall: {passed}/{total} tests passed ({passed/total*100:.1f}%)")
    
    if passed == total:
        logger.info("\n🎉 DATABASE CLEANUP VALIDATION SUCCESSFUL!")
        logger.info("✅ Database contains only real congressional data")
        logger.info("✅ No mock or test data found")
        logger.info("✅ All relationships are consistent")
        logger.info("✅ Ready for production use")
    else:
        logger.warning("\n⚠️ Database cleanup validation found issues")
        logger.warning("Please review and fix the failed tests above")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)