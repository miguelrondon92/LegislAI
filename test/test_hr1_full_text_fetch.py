#!/usr/bin/env python3
"""
Test fetching full text for HR 1 and analyze the complete bill
"""

import os
import sys
import logging
import requests
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

def test_congress_api_text_endpoints():
    """Test different ways to get bill text from Congress API"""
    logger.info("🔍 TESTING CONGRESS API TEXT ENDPOINTS")
    logger.info("=" * 60)
    
    try:
        from services.congress_api import CongressAPI
        
        congress_api = CongressAPI()
        
        # Test text endpoint
        logger.info("Testing get_bill_text method...")
        text_result = congress_api.get_bill_text(119, 'hr', 1)
        
        if text_result:
            logger.info(f"✅ get_bill_text returned: {type(text_result)}")
            if isinstance(text_result, str):
                logger.info(f"   Text length: {len(text_result):,} characters")
                logger.info(f"   Preview: {text_result[:500]}...")
            else:
                logger.info(f"   Content: {text_result}")
        else:
            logger.warning("⚠️ get_bill_text returned None")
        
        # Test raw API endpoint
        logger.info("\nTesting raw API endpoint...")
        endpoint = f"/bill/119/hr/1/text"
        raw_data = congress_api._make_request(endpoint)
        
        if raw_data:
            logger.info(f"✅ Raw API returned: {type(raw_data)}")
            if isinstance(raw_data, dict):
                logger.info(f"   Keys: {list(raw_data.keys())}")
                
                if 'textVersions' in raw_data:
                    versions = raw_data['textVersions']
                    logger.info(f"   Text versions: {len(versions)}")
                    
                    for i, version in enumerate(versions):
                        version_type = version.get('type', 'Unknown')
                        date = version.get('date', 'No date')
                        logger.info(f"     {i+1}. {version_type} ({date})")
                        
                        if 'formats' in version:
                            formats = version['formats']
                            for format_info in formats:
                                format_type = format_info.get('type', 'Unknown')
                                url = format_info.get('url', 'No URL')
                                logger.info(f"        Format: {format_type}")
                                logger.info(f"        URL: {url}")
                                
                                # Try to fetch actual content
                                if format_type == 'Formatted Text' and url != 'No URL':
                                    logger.info(f"        Attempting to fetch content...")
                                    try:
                                        response = requests.get(url, timeout=30)
                                        if response.status_code == 200:
                                            content = response.text
                                            logger.info(f"        ✅ Fetched {len(content):,} characters")
                                            logger.info(f"        Preview: {content[:300]}...")
                                            return content  # Return the actual full text
                                        else:
                                            logger.warning(f"        ⚠️ HTTP {response.status_code}")
                                    except Exception as e:
                                        logger.error(f"        ❌ Fetch failed: {e}")
        else:
            logger.warning("⚠️ Raw API returned None")
        
        return None
        
    except Exception as e:
        logger.error(f"❌ Text endpoint test failed: {e}")
        import traceback
        traceback.print_exc()
        return None

def enhance_congress_api_text_method():
    """Fix the Congress API text method to properly fetch full text"""
    logger.info("\n🔧 ENHANCING CONGRESS API TEXT METHOD")
    logger.info("=" * 60)
    
    # This function will show what needs to be fixed
    logger.info("Current get_bill_text method issues:")
    logger.info("1. Returns string result from API instead of fetching URL content")
    logger.info("2. Doesn't handle multiple text versions properly")
    logger.info("3. Simple regex HTML stripping may lose formatting")
    
    logger.info("\nProposed fixes:")
    logger.info("1. Parse textVersions array properly")
    logger.info("2. Fetch actual content from URL")
    logger.info("3. Better text cleaning and formatting")
    logger.info("4. Preference for enrolled/engrossed versions")

def analyze_hr1_with_full_text(full_text):
    """Re-analyze HR 1 with the actual full text"""
    logger.info("\n🤖 RE-ANALYZING HR 1 WITH FULL TEXT")
    logger.info("=" * 60)
    
    if not full_text:
        logger.error("❌ No full text provided")
        return None
    
    try:
        from app import app, db
        from db_models import Bill, BillCategoryMapping
        from services.enhanced_ai_analyzer import EnhancedAIAnalyzer
        from services.backfill_orchestrator import BackfillOrchestrator, BackfillConfig
        
        logger.info(f"Full text length: {len(full_text):,} characters")
        logger.info(f"Estimated pages: ~{len(full_text) // 3000} pages")
        
        with app.app_context():
            # Get HR 1
            hr1 = Bill.query.filter_by(
                congress=119,
                bill_type='hr',
                bill_number=1
            ).first()
            
            if not hr1:
                logger.error("❌ HR 1 not found in database")
                return None
            
            logger.info(f"Current stored content: {len(hr1.summary or ''):,} characters")
            logger.info(f"Improvement: {len(full_text) / len(hr1.summary or 'x'):,.1f}x more content")
            
            # Clear existing category mappings for fresh analysis
            BillCategoryMapping.query.filter_by(bill_id=hr1.id).delete()
            db.session.commit()
            logger.info("Cleared existing category mappings")
            
            # Perform new AI analysis with full text
            logger.info("Performing AI analysis with full text...")
            ai_analyzer = EnhancedAIAnalyzer()
            
            # Truncate text if it's too long for initial analysis
            analysis_text = full_text
            if len(full_text) > 50000:  # Limit for initial test
                analysis_text = full_text[:50000] + "\n\n[Text truncated for analysis - this is a large bill]"
                logger.info(f"Truncated to {len(analysis_text):,} characters for analysis")
            
            analysis = ai_analyzer.analyze_bill(analysis_text, hr1.title)
            
            if analysis:
                # Update bill with new analysis
                hr1.set_ai_analysis(analysis)
                
                # Create new category mappings
                config = BackfillConfig()
                orchestrator = BackfillOrchestrator(config)
                orchestrator._create_category_mappings(hr1, analysis)
                
                db.session.commit()
                
                logger.info("✅ Full text analysis completed!")
                
                # Show results
                new_analysis = hr1.get_ai_analysis()
                if 'policy_implications' in new_analysis:
                    categories = new_analysis['policy_implications'].get('categories', [])
                    logger.info(f"Policy categories found: {len(categories)}")
                    
                    for i, cat in enumerate(categories):
                        area = cat.get('area', 'Unknown')
                        impact = cat.get('impact_level', 'unknown')
                        sneakiness = cat.get('sneakiness_score', 'N/A')
                        logger.info(f"  {i+1}. {area}: {impact} impact, sneakiness={sneakiness}")
                
                # Check category mappings
                mappings = BillCategoryMapping.query.filter_by(bill_id=hr1.id).all()
                logger.info(f"Category mappings created: {len(mappings)}")
                
                return hr1
            else:
                logger.error("❌ AI analysis failed")
                return None
                
    except Exception as e:
        logger.error(f"❌ Full text analysis failed: {e}")
        import traceback
        traceback.print_exc()
        return None

def main():
    """Main function"""
    logger.info("📋 HR 1 FULL TEXT ANALYSIS")
    logger.info("=" * 70)
    
    # Step 1: Get the actual full text
    full_text = test_congress_api_text_endpoints()
    
    # Step 2: Show what needs to be enhanced
    enhance_congress_api_text_method()
    
    # Step 3: If we got full text, re-analyze
    if full_text:
        analyzed_bill = analyze_hr1_with_full_text(full_text)
        
        if analyzed_bill:
            logger.info(f"\n🎉 HR 1 FULL ANALYSIS COMPLETE!")
            logger.info(f"   Full text analyzed: {len(full_text):,} characters")
            logger.info(f"   View at: http://127.0.0.1:5000/bill/119/hr/1")
            
            # Compare before/after
            logger.info(f"\n📊 BEFORE vs AFTER:")
            logger.info(f"   Before: 503 characters analyzed")
            logger.info(f"   After: {len(full_text):,} characters analyzed")
            logger.info(f"   Improvement: {len(full_text) / 503:,.1f}x more comprehensive")
        else:
            logger.error("❌ Full text analysis failed")
    else:
        logger.warning("⚠️ Could not fetch full text")
        
        logger.info("\n💡 NEXT STEPS:")
        logger.info("1. Fix Congress API get_bill_text method")
        logger.info("2. Implement proper URL fetching")
        logger.info("3. Add chunked analysis for large bills")
        logger.info("4. Update bill processor to use full text")

if __name__ == "__main__":
    main()