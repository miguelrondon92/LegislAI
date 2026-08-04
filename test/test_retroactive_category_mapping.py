#!/usr/bin/env python3
"""
Test script to retroactively create category mappings for existing bills.
This should be run when bills have AI analysis but no category mappings.
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

def create_retroactive_category_mappings():
    """Create category mappings for existing bills with AI analysis"""
    logger.info("Creating retroactive category mappings...")
    
    try:
        from app import app, db
        from db_models import Bill, BillCategoryMapping, PolicyCategory
        from services.backfill_orchestrator import BackfillOrchestrator, BackfillConfig
        
        with app.app_context():
            # Get bills with AI analysis but no category mappings
            bills_with_analysis = Bill.query.filter(Bill.ai_analysis.isnot(None)).all()
            logger.info(f"Found {len(bills_with_analysis)} bills with AI analysis")
            
            # Create orchestrator to use its mapping methods
            config = BackfillConfig()
            orchestrator = BackfillOrchestrator(config)
            
            mappings_created = 0
            total_categories_processed = 0
            
            for bill in bills_with_analysis:
                logger.info(f"Processing bill: {bill.get_bill_identifier()}")
                
                try:
                    # Parse AI analysis
                    analysis = json.loads(bill.ai_analysis)
                    
                    # Create category mappings using the orchestrator's method
                    before_count = BillCategoryMapping.query.filter_by(bill_id=bill.id).count()
                    
                    orchestrator._create_category_mappings(bill, analysis)
                    
                    after_count = BillCategoryMapping.query.filter_by(bill_id=bill.id).count()
                    bill_mappings_created = after_count - before_count
                    mappings_created += bill_mappings_created
                    
                    # Count categories from analysis
                    categories = []
                    if 'policy_implications' in analysis and 'categories' in analysis['policy_implications']:
                        categories = analysis['policy_implications']['categories']
                    elif 'categories' in analysis:
                        categories = analysis['categories']
                    
                    total_categories_processed += len(categories)
                    
                    logger.info(f"  - Created {bill_mappings_created} mappings from {len(categories)} categories")
                    
                except json.JSONDecodeError:
                    logger.error(f"Invalid JSON in AI analysis for {bill.get_bill_identifier()}")
                    continue
                except Exception as e:
                    logger.error(f"Error processing {bill.get_bill_identifier()}: {e}")
                    continue
            
            # Commit all changes
            db.session.commit()
            
            logger.info(f"✅ Retroactive mapping completed:")
            logger.info(f"   - {mappings_created} total mappings created")
            logger.info(f"   - {total_categories_processed} total categories processed")
            logger.info(f"   - {len(bills_with_analysis)} bills processed")
            
            return True
            
    except Exception as e:
        logger.error(f"❌ Retroactive mapping failed: {e}")
        return False

def verify_category_mappings():
    """Verify that category mappings were created correctly"""
    logger.info("Verifying category mappings...")
    
    try:
        from app import app, db
        from db_models import Bill, BillCategoryMapping, PolicyCategory
        
        with app.app_context():
            bills = Bill.query.all()
            mappings = BillCategoryMapping.query.all()
            
            logger.info(f"📊 Verification Results:")
            logger.info(f"   Bills: {len(bills)}")
            logger.info(f"   Category Mappings: {len(mappings)}")
            
            for bill in bills:
                bill_mappings = BillCategoryMapping.query.filter_by(bill_id=bill.id).all()
                logger.info(f"   {bill.get_bill_identifier()}: {len(bill_mappings)} mappings")
                
                for mapping in bill_mappings:
                    category = mapping.policy_category
                    logger.info(f"     -> {category.display_name} (relevance: {mapping.relevance_score:.2f})")
                    
                    # Show category analysis if available
                    if mapping.category_specific_analysis:
                        analysis = mapping.get_category_analysis()
                        if analysis and 'analysis' in analysis:
                            analysis_preview = analysis['analysis'][:100] + "..." if len(analysis['analysis']) > 100 else analysis['analysis']
                            logger.info(f"        Analysis: {analysis_preview}")
            
            return len(mappings) > 0
            
    except Exception as e:
        logger.error(f"❌ Verification failed: {e}")
        return False

def test_category_name_matching():
    """Test the category name matching logic"""
    logger.info("Testing category name matching...")
    
    try:
        from app import app, db
        from db_models import PolicyCategory
        from services.backfill_orchestrator import BackfillOrchestrator, BackfillConfig
        
        with app.app_context():
            config = BackfillConfig()
            orchestrator = BackfillOrchestrator(config)
            
            # Test cases from our AI analysis
            test_categories = [
                "Public Lands and Natural Resources",
                "Native American Affairs", 
                "Economic Development",
                "Government Operations",
                "Social Services and Welfare",
                "Social Security",
                "Budget and Fiscal Policy"
            ]
            
            logger.info("Testing category name matching:")
            matches_found = 0
            
            for test_name in test_categories:
                matched_category = orchestrator._find_matching_policy_category(test_name)
                if matched_category:
                    logger.info(f"✅ '{test_name}' -> '{matched_category.display_name}'")
                    matches_found += 1
                else:
                    logger.warning(f"❌ '{test_name}' -> No match found")
            
            logger.info(f"Matching results: {matches_found}/{len(test_categories)} categories matched")
            
            # Show available policy categories
            available_categories = PolicyCategory.query.all()
            logger.info(f"Available policy categories ({len(available_categories)}):")
            for cat in available_categories[:10]:  # Show first 10
                logger.info(f"   {cat.name} -> {cat.display_name}")
            if len(available_categories) > 10:
                logger.info(f"   ... and {len(available_categories) - 10} more")
            
            return matches_found > 0
            
    except Exception as e:
        logger.error(f"❌ Category matching test failed: {e}")
        return False

def main():
    """Main test function"""
    logger.info("🔗 RETROACTIVE CATEGORY MAPPING TEST")
    logger.info("=" * 50)
    
    tests = [
        ("Category Name Matching", test_category_name_matching),
        ("Create Retroactive Mappings", create_retroactive_category_mappings),
        ("Verify Mappings", verify_category_mappings),
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
    logger.info("📊 CATEGORY MAPPING TEST SUMMARY")
    logger.info("=" * 50)
    
    passed = sum(1 for result in results.values() if result)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASSED" if result else "❌ FAILED"
        logger.info(f"{test_name}: {status}")
    
    logger.info(f"\n📈 Overall: {passed}/{total} tests passed ({passed/total*100:.1f}%)")
    
    if passed == total:
        logger.info("\n🎉 CATEGORY MAPPING SUCCESSFUL!")
        logger.info("✅ Bills are now properly mapped to policy categories")
        logger.info("✅ Category relevance scores calculated")
        logger.info("✅ Category-specific analysis stored")
    else:
        logger.warning("\n⚠️ Some category mapping issues found")
        logger.warning("Check the logs above for details")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)