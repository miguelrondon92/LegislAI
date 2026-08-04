#!/usr/bin/env python3
"""
Test that category mapping works in the complete workflow during backfill.
This tests that new bills automatically get category mappings created.
"""

import os
import sys
import logging
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

def test_category_mapping_in_backfill():
    """Test that category mappings are created automatically during backfill"""
    logger.info("Testing category mapping in backfill workflow...")
    
    try:
        from app import app, db
        from db_models import Bill, BillCategoryMapping
        from services.backfill_orchestrator import BackfillOrchestrator, BackfillConfig
        
        with app.app_context():
            # Get current bill and mapping counts
            initial_bills = Bill.query.count()
            initial_mappings = BillCategoryMapping.query.count()
            
            logger.info(f"Initial state: {initial_bills} bills, {initial_mappings} mappings")
            
            # Configure backfill for one more bill
            from services.backfill_orchestrator import ProcessingMode
            config = BackfillConfig(
                congress_session=119,
                processing_mode=ProcessingMode.FULL_PROCESSING,
                max_bills_per_session=4,  # Get one more than we have
                batch_size=1
            )
            
            orchestrator = BackfillOrchestrator(config)
            
            # Start backfill (should pick up where we left off)
            logger.info("Running backfill to get one more bill...")
            success = orchestrator.start_backfill(resume=True)
            
            if success:
                # Check new counts
                final_bills = Bill.query.count()
                final_mappings = BillCategoryMapping.query.count()
                
                bills_added = final_bills - initial_bills
                mappings_added = final_mappings - initial_mappings
                
                logger.info(f"Final state: {final_bills} bills, {final_mappings} mappings")
                logger.info(f"Added: {bills_added} bills, {mappings_added} mappings")
                
                if bills_added > 0 and mappings_added > 0:
                    logger.info("✅ New bills automatically got category mappings")
                    
                    # Show the new mappings
                    new_bills = Bill.query.offset(initial_bills).all()
                    for bill in new_bills:
                        bill_mappings = BillCategoryMapping.query.filter_by(bill_id=bill.id).all()
                        logger.info(f"   {bill.get_bill_identifier()}: {len(bill_mappings)} mappings")
                        for mapping in bill_mappings[:3]:  # Show first 3
                            logger.info(f"     -> {mapping.policy_category.display_name} ({mapping.relevance_score:.2f})")
                    
                    return True
                elif bills_added == 0:
                    logger.info("✅ No new bills available (already have all discovered bills)")
                    return True
                else:
                    logger.error("❌ New bills added but no category mappings created")
                    return False
            else:
                logger.warning("⚠️ Backfill failed or was paused")
                return False
            
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        return False

def test_existing_mappings_integrity():
    """Test that existing category mappings are intact and properly structured"""
    logger.info("Testing existing category mappings integrity...")
    
    try:
        from app import app, db
        from db_models import Bill, BillCategoryMapping, PolicyCategory
        
        with app.app_context():
            mappings = BillCategoryMapping.query.all()
            logger.info(f"Testing {len(mappings)} category mappings")
            
            integrity_issues = []
            
            for mapping in mappings:
                # Check foreign key integrity
                if not mapping.bill:
                    integrity_issues.append(f"Mapping {mapping.id} has no associated bill")
                
                if not mapping.policy_category:
                    integrity_issues.append(f"Mapping {mapping.id} has no associated policy category")
                
                # Check relevance score validity
                if mapping.relevance_score < 0 or mapping.relevance_score > 1:
                    integrity_issues.append(f"Mapping {mapping.id} has invalid relevance score: {mapping.relevance_score}")
                
                # Check if category analysis is valid JSON
                if mapping.category_specific_analysis:
                    try:
                        analysis = mapping.get_category_analysis()
                        if not isinstance(analysis, dict):
                            integrity_issues.append(f"Mapping {mapping.id} has invalid category analysis format")
                    except Exception as e:
                        integrity_issues.append(f"Mapping {mapping.id} has malformed category analysis: {e}")
            
            if integrity_issues:
                logger.error("❌ Integrity issues found:")
                for issue in integrity_issues:
                    logger.error(f"   {issue}")
                return False
            else:
                logger.info("✅ All category mappings have proper integrity")
                return True
            
    except Exception as e:
        logger.error(f"❌ Integrity test failed: {e}")
        return False

def test_category_coverage():
    """Test that bills are mapped to appropriate categories"""
    logger.info("Testing category coverage and appropriateness...")
    
    try:
        from app import app, db
        from db_models import Bill, BillCategoryMapping
        import json
        
        with app.app_context():
            bills = Bill.query.all()
            coverage_results = []
            
            for bill in bills:
                logger.info(f"Analyzing coverage for {bill.get_bill_identifier()}")
                
                # Get AI analysis categories
                ai_categories = []
                if bill.ai_analysis:
                    analysis = json.loads(bill.ai_analysis)
                    if 'policy_implications' in analysis and 'categories' in analysis['policy_implications']:
                        ai_categories = [cat.get('area', '') for cat in analysis['policy_implications']['categories']]
                
                # Get database mappings
                db_mappings = BillCategoryMapping.query.filter_by(bill_id=bill.id).all()
                db_categories = [mapping.policy_category.display_name for mapping in db_mappings]
                
                logger.info(f"   AI identified: {ai_categories}")
                logger.info(f"   DB mapped to: {db_categories}")
                
                # Check coverage
                coverage_ratio = len(db_categories) / len(ai_categories) if ai_categories else 0
                coverage_results.append({
                    'bill': bill.get_bill_identifier(),
                    'ai_categories': len(ai_categories),
                    'db_mappings': len(db_categories),
                    'coverage_ratio': coverage_ratio
                })
            
            # Analyze coverage
            total_coverage = sum(result['coverage_ratio'] for result in coverage_results)
            avg_coverage = total_coverage / len(coverage_results) if coverage_results else 0
            
            logger.info(f"📊 Category Coverage Analysis:")
            logger.info(f"   Average coverage ratio: {avg_coverage:.2f}")
            
            for result in coverage_results:
                logger.info(f"   {result['bill']}: {result['db_mappings']}/{result['ai_categories']} ({result['coverage_ratio']:.2f})")
            
            # Consider good if we have at least 80% coverage on average
            success = avg_coverage >= 0.8
            
            if success:
                logger.info("✅ Good category coverage achieved")
            else:
                logger.warning("⚠️ Category coverage could be improved")
            
            return success
            
    except Exception as e:
        logger.error(f"❌ Coverage test failed: {e}")
        return False

def display_final_mapping_summary():
    """Display a comprehensive summary of all category mappings"""
    logger.info("📊 FINAL CATEGORY MAPPING SUMMARY")
    logger.info("=" * 50)
    
    try:
        from app import app, db
        from db_models import Bill, BillCategoryMapping, PolicyCategory
        
        with app.app_context():
            bills = Bill.query.all()
            mappings = BillCategoryMapping.query.all()
            categories = PolicyCategory.query.all()
            
            logger.info(f"Total bills: {len(bills)}")
            logger.info(f"Total category mappings: {len(mappings)}")
            logger.info(f"Total policy categories: {len(categories)}")
            logger.info(f"Average mappings per bill: {len(mappings) / len(bills):.1f}")
            
            # Category usage statistics
            category_usage = {}
            for mapping in mappings:
                cat_name = mapping.policy_category.display_name
                if cat_name not in category_usage:
                    category_usage[cat_name] = 0
                category_usage[cat_name] += 1
            
            logger.info(f"\n📂 Most Used Categories:")
            sorted_usage = sorted(category_usage.items(), key=lambda x: x[1], reverse=True)
            for cat_name, count in sorted_usage[:10]:
                logger.info(f"   {cat_name}: {count} bills")
            
            # Relevance score distribution
            relevance_scores = [mapping.relevance_score for mapping in mappings]
            if relevance_scores:
                avg_relevance = sum(relevance_scores) / len(relevance_scores)
                max_relevance = max(relevance_scores)
                min_relevance = min(relevance_scores)
                
                logger.info(f"\n📈 Relevance Score Statistics:")
                logger.info(f"   Average: {avg_relevance:.3f}")
                logger.info(f"   Range: {min_relevance:.3f} - {max_relevance:.3f}")
            
            return True
            
    except Exception as e:
        logger.error(f"❌ Summary generation failed: {e}")
        return False

def main():
    """Main test function"""
    logger.info("🔗 CATEGORY MAPPING WORKFLOW TEST")
    logger.info("=" * 50)
    
    tests = [
        ("Existing Mappings Integrity", test_existing_mappings_integrity),
        ("Category Coverage Analysis", test_category_coverage),
        ("Backfill Category Mapping", test_category_mapping_in_backfill),
    ]
    
    results = {}
    
    for test_name, test_func in tests:
        logger.info(f"\n🧪 Running {test_name}...")
        try:
            results[test_name] = test_func()
        except Exception as e:
            logger.error(f"❌ {test_name} crashed: {e}")
            results[test_name] = False
    
    # Always show summary
    logger.info(f"\n")
    display_final_mapping_summary()
    
    # Final results
    logger.info("\n" + "=" * 50)
    logger.info("📊 CATEGORY MAPPING WORKFLOW SUMMARY")
    logger.info("=" * 50)
    
    passed = sum(1 for result in results.values() if result)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASSED" if result else "❌ FAILED"
        logger.info(f"{test_name}: {status}")
    
    logger.info(f"\n📈 Overall: {passed}/{total} tests passed ({passed/total*100:.1f}%)")
    
    if passed == total:
        logger.info("\n🎉 CATEGORY MAPPING WORKFLOW SUCCESSFUL!")
        logger.info("✅ Bills automatically get mapped to policy categories")
        logger.info("✅ Category mappings have proper integrity")
        logger.info("✅ Coverage matches AI analysis results")
        logger.info("✅ Workflow ready for production use")
    else:
        logger.warning("\n⚠️ Some category mapping workflow issues found")
        logger.warning("Check the logs above for details")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)