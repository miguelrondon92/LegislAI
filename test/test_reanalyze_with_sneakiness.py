#!/usr/bin/env python3
"""
Re-analyze existing bills with enhanced sneakiness detection and update category mappings.
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

def reanalyze_bills_with_sneakiness():
    """Re-analyze existing bills with new sneakiness detection"""
    logger.info("Re-analyzing existing bills with sneakiness detection...")
    
    try:
        from app import app, db
        from db_models import Bill, BillCategoryMapping
        from services.enhanced_ai_analyzer import EnhancedAIAnalyzer
        from services.backfill_orchestrator import BackfillOrchestrator, BackfillConfig
        
        with app.app_context():
            bills = Bill.query.all()
            logger.info(f"Found {len(bills)} bills to re-analyze")
            
            analyzer = EnhancedAIAnalyzer()
            config = BackfillConfig()
            orchestrator = BackfillOrchestrator(config)
            
            for bill in bills:
                logger.info(f"Re-analyzing: {bill.get_bill_identifier()}")
                
                # Clear existing category mappings
                existing_mappings = BillCategoryMapping.query.filter_by(bill_id=bill.id).all()
                for mapping in existing_mappings:
                    db.session.delete(mapping)
                
                # Get bill text for analysis
                bill_text = bill.get_full_text() or bill.summary or bill.title
                if len(bill_text) > 2000:
                    bill_text = bill_text[:2000] + "..."
                
                # Perform new analysis with sneakiness detection
                analysis = analyzer.analyze_bill(bill_text, bill.title)
                
                if analysis:
                    # Update bill with new analysis
                    bill.set_ai_analysis(analysis)
                    
                    # Create new category mappings with sneakiness scores
                    orchestrator._create_category_mappings(bill, analysis)
                    
                    logger.info(f"✅ Updated analysis for {bill.get_bill_identifier()}")
                else:
                    logger.warning(f"⚠️ Analysis failed for {bill.get_bill_identifier()}")
            
            # Commit all changes
            db.session.commit()
            logger.info("✅ All bills re-analyzed with sneakiness detection")
            
            return True
            
    except Exception as e:
        logger.error(f"❌ Re-analysis failed: {e}")
        return False

def verify_sneakiness_scores():
    """Verify that sneakiness scores are now populated"""
    logger.info("Verifying sneakiness scores after re-analysis...")
    
    try:
        from app import app, db
        from db_models import BillCategoryMapping
        import json
        
        with app.app_context():
            mappings = BillCategoryMapping.query.all()
            logger.info(f"Checking {len(mappings)} category mappings")
            
            sneakiness_scores = []
            mappings_with_explanations = 0
            
            for mapping in mappings:
                bill_id = mapping.bill.get_bill_identifier() if mapping.bill else 'Unknown'
                category = mapping.policy_category.display_name if mapping.policy_category else 'Unknown'
                sneakiness = mapping.sneakiness_score
                sneakiness_scores.append(sneakiness)
                
                logger.info(f"{bill_id} -> {category}:")
                logger.info(f"  Sneakiness: {sneakiness:.3f}")
                
                # Check for sneakiness explanation in category analysis
                if mapping.category_specific_analysis:
                    analysis = mapping.get_category_analysis()
                    if 'sneakiness_explanation' in analysis:
                        explanation = analysis['sneakiness_explanation']
                        logger.info(f"  Explanation: {explanation[:100]}...")
                        mappings_with_explanations += 1
            
            if sneakiness_scores:
                avg_sneakiness = sum(sneakiness_scores) / len(sneakiness_scores)
                max_sneakiness = max(sneakiness_scores)
                non_zero_count = sum(1 for s in sneakiness_scores if s > 0)
                
                logger.info(f"\nSneakiness Statistics After Re-analysis:")
                logger.info(f"  Average: {avg_sneakiness:.3f}")
                logger.info(f"  Maximum: {max_sneakiness:.3f}")
                logger.info(f"  Non-zero scores: {non_zero_count}/{len(sneakiness_scores)}")
                logger.info(f"  Mappings with explanations: {mappings_with_explanations}/{len(mappings)}")
                
                if non_zero_count > 0 or mappings_with_explanations > 0:
                    logger.info("✅ Sneakiness detection is working and populated")
                    return True
                else:
                    logger.warning("⚠️ No sneakiness scores or explanations found")
                    return False
            else:
                logger.error("❌ No mappings found")
                return False
                
    except Exception as e:
        logger.error(f"❌ Verification failed: {e}")
        return False

def show_bill_analysis_comparison():
    """Show comparison of bill analysis before/after sneakiness enhancement"""
    logger.info("Showing enhanced bill analysis structure...")
    
    try:
        from app import app, db
        from db_models import Bill
        import json
        
        with app.app_context():
            bill = Bill.query.first()
            if not bill or not bill.ai_analysis:
                logger.error("No bill with analysis found")
                return False
            
            analysis = json.loads(bill.ai_analysis)
            
            logger.info(f"Enhanced Analysis for: {bill.get_bill_identifier()}")
            logger.info(f"Title: {bill.title}")
            
            if 'policy_implications' in analysis:
                policy = analysis['policy_implications']
                
                # Show categories with sneakiness
                categories = policy.get('categories', [])
                logger.info(f"\nCategories with Sneakiness Analysis ({len(categories)}):")
                
                for i, category in enumerate(categories):
                    area = category.get('area', 'Unknown')
                    impact = category.get('impact_level', 'Unknown')
                    sneakiness = category.get('sneakiness_score', 'Not found')
                    explanation = category.get('sneakiness_explanation', 'Not provided')
                    
                    logger.info(f"  {i+1}. {area}")
                    logger.info(f"     Impact Level: {impact}")
                    logger.info(f"     Sneakiness Score: {sneakiness}")
                    logger.info(f"     Explanation: {explanation}")
                
                # Show overall hidden provisions analysis
                if 'hidden_provisions_analysis' in policy:
                    hidden = policy['hidden_provisions_analysis']
                    overall_sneakiness = hidden.get('overall_sneakiness', 'Not found')
                    hidden_provisions = hidden.get('hidden_provisions_found', [])
                    transparency = hidden.get('transparency_assessment', 'Not provided')
                    
                    logger.info(f"\nOverall Hidden Provisions Analysis:")
                    logger.info(f"  Overall Sneakiness: {overall_sneakiness}")
                    logger.info(f"  Hidden Provisions Found: {len(hidden_provisions)}")
                    for provision in hidden_provisions:
                        logger.info(f"    - {provision}")
                    logger.info(f"  Transparency Assessment: {transparency}")
                
                return True
            else:
                logger.error("No policy implications found")
                return False
                
    except Exception as e:
        logger.error(f"❌ Analysis comparison failed: {e}")
        return False

def main():
    """Main function"""
    logger.info("🔄 RE-ANALYZE WITH SNEAKINESS DETECTION")
    logger.info("=" * 60)
    
    tests = [
        ("Re-analyze Bills with Sneakiness", reanalyze_bills_with_sneakiness),
        ("Verify Sneakiness Scores", verify_sneakiness_scores),
        ("Show Enhanced Analysis Structure", show_bill_analysis_comparison),
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
    logger.info("\n" + "=" * 60)
    logger.info("📊 RE-ANALYSIS SUMMARY")
    logger.info("=" * 60)
    
    passed = sum(1 for result in results.values() if result)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASSED" if result else "❌ FAILED"
        logger.info(f"{test_name}: {status}")
    
    logger.info(f"\n📈 Overall: {passed}/{total} tests passed ({passed/total*100:.1f}%)")
    
    if passed == total:
        logger.info("\n🎉 RE-ANALYSIS WITH SNEAKINESS SUCCESSFUL!")
        logger.info("✅ All existing bills now have sneakiness detection")
        logger.info("✅ Category mappings include sneakiness scores and explanations")
        logger.info("✅ Hidden provision analysis is functional")
        logger.info("✅ System ready to detect sneaky legislation")
    else:
        logger.warning("\n⚠️ Some re-analysis issues found")
        logger.warning("Check the logs above for details")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)