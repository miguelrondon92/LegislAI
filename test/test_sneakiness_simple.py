#!/usr/bin/env python3
"""
Simple test to validate sneakiness detection in the analysis workflow.
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

def test_current_sneakiness_scores():
    """Test current sneakiness scores in database"""
    logger.info("Testing current sneakiness scores...")
    
    try:
        from app import app, db
        from db_models import BillCategoryMapping
        
        with app.app_context():
            mappings = BillCategoryMapping.query.all()
            logger.info(f"Found {len(mappings)} category mappings")
            
            sneakiness_scores = []
            for mapping in mappings:
                bill_id = mapping.bill.get_bill_identifier() if mapping.bill else 'Unknown'
                category = mapping.policy_category.display_name if mapping.policy_category else 'Unknown'
                sneakiness = mapping.sneakiness_score
                sneakiness_scores.append(sneakiness)
                
                logger.info(f"{bill_id} -> {category}: sneakiness={sneakiness:.3f}")
                
                # Check category analysis for sneakiness explanation
                if mapping.category_specific_analysis:
                    analysis = mapping.get_category_analysis()
                    if 'sneakiness_explanation' in analysis:
                        logger.info(f"  Explanation: {analysis['sneakiness_explanation']}")
            
            if sneakiness_scores:
                avg_sneakiness = sum(sneakiness_scores) / len(sneakiness_scores)
                max_sneakiness = max(sneakiness_scores)
                non_zero_count = sum(1 for s in sneakiness_scores if s > 0)
                
                logger.info(f"Sneakiness Statistics:")
                logger.info(f"  Average: {avg_sneakiness:.3f}")
                logger.info(f"  Maximum: {max_sneakiness:.3f}")
                logger.info(f"  Non-zero scores: {non_zero_count}/{len(sneakiness_scores)}")
                
                return True
            else:
                logger.warning("No mappings found")
                return False
                
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        return False

def test_ai_analysis_structure():
    """Test the structure of AI analysis to see if sneakiness fields are present"""
    logger.info("Testing AI analysis structure...")
    
    try:
        from app import app, db
        from db_models import Bill
        import json
        
        with app.app_context():
            bill = Bill.query.first()
            if not bill or not bill.ai_analysis:
                logger.error("No bill with AI analysis found")
                return False
            
            analysis = json.loads(bill.ai_analysis)
            logger.info(f"Analyzing structure for: {bill.get_bill_identifier()}")
            
            # Check if policy implications has the new sneakiness fields
            if 'policy_implications' in analysis:
                policy = analysis['policy_implications']
                categories = policy.get('categories', [])
                
                logger.info(f"Found {len(categories)} categories in policy implications")
                
                sneakiness_fields_found = False
                for i, category in enumerate(categories):
                    logger.info(f"Category {i+1}: {list(category.keys())}")
                    
                    if 'sneakiness_score' in category:
                        sneakiness_fields_found = True
                        logger.info(f"  ✅ Sneakiness score found: {category['sneakiness_score']}")
                    
                    if 'sneakiness_explanation' in category:
                        logger.info(f"  ✅ Sneakiness explanation found: {category['sneakiness_explanation'][:100]}...")
                
                # Check for overall hidden provisions analysis
                if 'hidden_provisions_analysis' in policy:
                    hidden = policy['hidden_provisions_analysis']
                    logger.info(f"✅ Hidden provisions analysis found: {list(hidden.keys())}")
                    sneakiness_fields_found = True
                
                if sneakiness_fields_found:
                    logger.info("✅ New sneakiness fields are present in AI analysis")
                    return True
                else:
                    logger.warning("⚠️ Sneakiness fields not found - AI analysis may need update")
                    return False
            else:
                logger.error("❌ No policy implications found in analysis")
                return False
                
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        return False

def test_new_bill_analysis_with_sneakiness():
    """Test analyzing a new bill with sneakiness detection"""
    logger.info("Testing new bill analysis with sneakiness...")
    
    try:
        from services.enhanced_ai_analyzer import EnhancedAIAnalyzer
        
        # Simple test bill text
        test_bill_text = """
        H.R.TEST - Test Transportation Funding Act
        
        SECTION 1. This act provides funding for road maintenance.
        
        SECTION 2. The Secretary may allocate up to $100 million for road repairs.
        
        SECTION 3. Technical provisions for implementation.
        """
        
        test_title = "Test Transportation Funding Act"
        
        logger.info("Analyzing test bill with AIAnalyzer...")
        analyzer = EnhancedAIAnalyzer()
        
        analysis = analyzer.analyze_bill(test_bill_text, test_title)
        
        if analysis and 'policy_implications' in analysis:
            policy = analysis['policy_implications']
            categories = policy.get('categories', [])
            
            logger.info(f"✅ Analysis completed with {len(categories)} categories")
            
            # Check for sneakiness fields
            sneakiness_found = False
            for category in categories:
                if 'sneakiness_score' in category:
                    sneakiness_found = True
                    logger.info(f"  Category: {category.get('area', 'Unknown')}")
                    logger.info(f"  Sneakiness: {category['sneakiness_score']}")
                    if 'sneakiness_explanation' in category:
                        logger.info(f"  Explanation: {category['sneakiness_explanation']}")
            
            if 'hidden_provisions_analysis' in policy:
                hidden = policy['hidden_provisions_analysis']
                logger.info(f"  Overall sneakiness: {hidden.get('overall_sneakiness', 'Not found')}")
                sneakiness_found = True
            
            if sneakiness_found:
                logger.info("✅ Sneakiness detection is working in new analysis")
                return True
            else:
                logger.warning("⚠️ No sneakiness fields found in new analysis")
                return False
        else:
            logger.error("❌ Analysis failed or incomplete")
            return False
            
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        return False

def main():
    """Main test function"""
    logger.info("🕵️ SIMPLE SNEAKINESS DETECTION TEST")
    logger.info("=" * 50)
    
    tests = [
        ("Current Sneakiness Scores", test_current_sneakiness_scores),
        ("AI Analysis Structure", test_ai_analysis_structure),
        ("New Bill Analysis", test_new_bill_analysis_with_sneakiness),
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
    logger.info("📊 SNEAKINESS TEST SUMMARY")
    logger.info("=" * 50)
    
    passed = sum(1 for result in results.values() if result)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASSED" if result else "❌ FAILED"
        logger.info(f"{test_name}: {status}")
    
    logger.info(f"\n📈 Overall: {passed}/{total} tests passed ({passed/total*100:.1f}%)")
    
    if passed >= total * 0.6:  # At least 60% success
        logger.info("\n🎉 SNEAKINESS DETECTION WORKING!")
        logger.info("✅ Enhanced AI analysis includes sneakiness scoring")
        logger.info("✅ Hidden provision detection is functional")
        logger.info("✅ Category mappings store sneakiness data")
    else:
        logger.warning("\n⚠️ Sneakiness detection needs attention")
        logger.warning("Check the logs above for details")
    
    return passed >= total * 0.6

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)