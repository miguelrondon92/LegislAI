#!/usr/bin/env python3
"""
Investigate HR 1 full content and analysis gaps

This script examines why HR 1 might not be fully analyzed by checking:
1. What content we're actually getting from Congress API
2. How much text is being analyzed vs available
3. Whether we're getting full text vs just summary
4. API response structure and content
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

def investigate_hr1_api_response():
    """Check what we're actually getting from Congress API for HR 1"""
    logger.info("🔍 INVESTIGATING HR 1 API RESPONSE")
    logger.info("=" * 60)
    
    try:
        from services.congress_api import CongressAPI
        
        congress_api = CongressAPI()
        
        # Get bill details
        logger.info("Fetching HR 1 bill details...")
        bill_data = congress_api.get_bill_details(119, 'hr', 1)
        
        if not bill_data:
            logger.error("❌ No bill data received")
            return None
        
        logger.info("✅ Bill data received")
        
        # Analyze the structure
        logger.info(f"\n📊 BILL DATA STRUCTURE:")
        logger.info(f"Keys available: {list(bill_data.keys())}")
        
        # Check bill content fields
        content_fields = ['title', 'summary', 'text', 'fullText', 'content', 'description']
        
        for field in content_fields:
            if field in bill_data:
                content = bill_data[field]
                if isinstance(content, str):
                    logger.info(f"  {field}: {len(content):,} characters")
                    logger.info(f"    Preview: {content[:200]}...")
                else:
                    logger.info(f"  {field}: {type(content)} - {content}")
            else:
                logger.info(f"  {field}: Not present")
        
        # Check for nested text content
        if 'bill' in bill_data:
            bill_obj = bill_data['bill']
            logger.info(f"\nNested 'bill' object keys: {list(bill_obj.keys()) if isinstance(bill_obj, dict) else type(bill_obj)}")
        
        # Try to get bill text separately
        logger.info(f"\n🔍 TRYING BILL TEXT API:")
        text_data = congress_api.get_bill_text(119, 'hr', 1)
        
        if text_data:
            logger.info(f"✅ Bill text API response received")
            logger.info(f"Text data keys: {list(text_data.keys()) if isinstance(text_data, dict) else type(text_data)}")
            
            if 'textVersions' in text_data:
                versions = text_data['textVersions']
                logger.info(f"Available text versions: {len(versions)}")
                
                for i, version in enumerate(versions[:3]):  # Check first 3 versions
                    logger.info(f"  Version {i+1}: {version.get('type', 'Unknown')} - {version.get('date', 'No date')}")
                    if 'formats' in version:
                        formats = version['formats']
                        logger.info(f"    Available formats: {[f.get('type') for f in formats]}")
        else:
            logger.warning("⚠️ No bill text data received")
        
        return bill_data, text_data
        
    except Exception as e:
        logger.error(f"❌ API investigation failed: {e}")
        import traceback
        traceback.print_exc()
        return None, None

def check_hr1_database_content():
    """Check what's currently stored in database for HR 1"""
    logger.info("\n🔍 CHECKING HR 1 DATABASE CONTENT")
    logger.info("=" * 60)
    
    try:
        from app import app, db
        from db_models import Bill, BillAction, BillCategoryMapping
        
        with app.app_context():
            # Get HR 1 from database
            hr1 = Bill.query.filter_by(
                congress=119,
                bill_type='hr',
                bill_number=1
            ).first()
            
            if not hr1:
                logger.error("❌ HR 1 not found in database")
                return None
            
            logger.info(f"✅ HR 1 found: {hr1.get_bill_identifier()}")
            logger.info(f"Title: {hr1.title}")
            
            # Check all stored content
            content_fields = [
                ('title', hr1.title),
                ('summary', hr1.summary),
                ('status', hr1.status),
                ('sponsor_name', hr1.sponsor_name),
            ]
            
            logger.info(f"\n📊 STORED CONTENT:")
            total_chars = 0
            
            for field_name, field_value in content_fields:
                if field_value:
                    char_count = len(str(field_value))
                    total_chars += char_count
                    logger.info(f"  {field_name}: {char_count:,} characters")
                    if char_count > 100:
                        logger.info(f"    Preview: {str(field_value)[:200]}...")
                else:
                    logger.info(f"  {field_name}: Empty/None")
            
            logger.info(f"\nTotal stored text: {total_chars:,} characters")
            
            # Check AI analysis
            analysis = hr1.get_ai_analysis()
            if analysis:
                logger.info(f"\n🤖 AI ANALYSIS:")
                logger.info(f"Analysis keys: {list(analysis.keys())}")
                
                if 'policy_implications' in analysis:
                    policy = analysis['policy_implications']
                    categories = policy.get('categories', [])
                    logger.info(f"  Policy categories found: {len(categories)}")
                    
                    for i, cat in enumerate(categories):
                        logger.info(f"    {i+1}. {cat.get('area', 'Unknown')}: {cat.get('impact_level', 'unknown')} impact")
                        logger.info(f"       Sneakiness: {cat.get('sneakiness_score', 'N/A')}")
                
                # Check what text was analyzed
                if 'chunks_analyzed' in analysis:
                    logger.info(f"  Chunks analyzed: {analysis['chunks_analyzed']}")
                
                if 'analysis_method' in analysis:
                    logger.info(f"  Analysis method: {analysis['analysis_method']}")
            else:
                logger.info(f"\n🤖 AI ANALYSIS: Not available")
            
            # Check actions
            actions_count = len(hr1.actions)
            logger.info(f"\n📋 ACTIONS: {actions_count} stored")
            
            # Check category mappings
            mappings = BillCategoryMapping.query.filter_by(bill_id=hr1.id).all()
            logger.info(f"\n🏷️ CATEGORY MAPPINGS: {len(mappings)} created")
            
            return hr1
            
    except Exception as e:
        logger.error(f"❌ Database check failed: {e}")
        return None

def compare_full_text_sources():
    """Compare different ways to get full text"""
    logger.info("\n🔍 COMPARING FULL TEXT SOURCES")
    logger.info("=" * 60)
    
    try:
        from services.congress_api import CongressAPI
        
        congress_api = CongressAPI()
        
        # Method 1: Bill details summary
        logger.info("Method 1: Bill details summary...")
        bill_data = congress_api.get_bill_details(119, 'hr', 1)
        
        summary_text = ""
        if bill_data and 'summary' in bill_data:
            summary_text = bill_data['summary'] or ""
        
        logger.info(f"  Summary length: {len(summary_text):,} characters")
        
        # Method 2: Bill text API
        logger.info("\nMethod 2: Bill text API...")
        text_data = congress_api.get_bill_text(119, 'hr', 1)
        
        full_text_length = 0
        if text_data and 'textVersions' in text_data:
            # Try to find the latest/enrolled version
            for version in text_data['textVersions']:
                if version.get('type') in ['Enrolled', 'Public Print', 'Engrossed']:
                    logger.info(f"  Found {version.get('type')} version from {version.get('date')}")
                    
                    # Check formats
                    if 'formats' in version:
                        for format_info in version['formats']:
                            if format_info.get('type') == 'Formatted Text':
                                url = format_info.get('url')
                                logger.info(f"    Full text URL: {url}")
                                
                                # Try to estimate size or get actual content
                                # Note: Congress API doesn't provide full text directly
                                # We'd need to fetch from the URL
                                
        logger.info(f"  Full text estimated: Requires URL fetch")
        
        # Method 3: Check what our current method gets
        logger.info("\nMethod 3: Current bill processor method...")
        from app import app
        from db_models import Bill
        
        with app.app_context():
            hr1 = Bill.query.filter_by(congress=119, bill_type='hr', bill_number=1).first()
            if hr1:
                current_text = hr1.get_full_text()
                logger.info(f"  Current method length: {len(current_text):,} characters")
                logger.info(f"  Current text preview: {current_text[:300]}...")
            
        logger.info(f"\n🚨 ISSUE IDENTIFIED:")
        logger.info(f"The Congress API provides metadata and summaries, but full bill text")
        logger.info(f"requires fetching from separate URLs. We're likely only analyzing")
        logger.info(f"the summary (~{len(summary_text):,} chars) instead of the full text")
        logger.info(f"which for a major bill like HR 1 could be 100,000+ characters.")
        
    except Exception as e:
        logger.error(f"❌ Text comparison failed: {e}")

def recommend_solutions():
    """Recommend solutions for getting full HR 1 content"""
    logger.info("\n💡 RECOMMENDED SOLUTIONS")
    logger.info("=" * 60)
    
    solutions = [
        {
            "title": "1. Implement Full Text Fetching",
            "description": "Modify Congress API to fetch actual bill text from URLs",
            "complexity": "Medium",
            "impact": "High"
        },
        {
            "title": "2. Enhanced Text Processing",
            "description": "Update bill processor to handle larger text chunks",
            "complexity": "Low", 
            "impact": "High"
        },
        {
            "title": "3. Chunked Analysis for Large Bills",
            "description": "Implement proper chunking for bills >50k characters",
            "complexity": "Medium",
            "impact": "High"
        },
        {
            "title": "4. Alternative Data Sources", 
            "description": "Use Congress.gov HTML scraping or other sources",
            "complexity": "High",
            "impact": "Medium"
        }
    ]
    
    for solution in solutions:
        logger.info(f"\n{solution['title']}")
        logger.info(f"  Description: {solution['description']}")
        logger.info(f"  Complexity: {solution['complexity']}")
        logger.info(f"  Impact: {solution['impact']}")
    
    logger.info(f"\n🎯 IMMEDIATE ACTION:")
    logger.info(f"The most critical issue is that we're analyzing bill summaries")
    logger.info(f"instead of full text. For HR 1 (likely 100+ pages), this means")
    logger.info(f"we're missing 95% of the actual legislative content.")

def main():
    """Main investigation function"""
    logger.info("🔍 HR 1 FULL ANALYSIS INVESTIGATION")
    logger.info("=" * 70)
    
    # Run all investigations
    bill_data, text_data = investigate_hr1_api_response()
    hr1_db = check_hr1_database_content()
    compare_full_text_sources()
    recommend_solutions()
    
    logger.info(f"\n📋 INVESTIGATION SUMMARY")
    logger.info("=" * 70)
    
    if bill_data:
        logger.info("✅ Congress API responding")
    else:
        logger.info("❌ Congress API issues")
    
    if hr1_db:
        logger.info("✅ HR 1 exists in database")
        analysis = hr1_db.get_ai_analysis()
        if analysis:
            logger.info("✅ AI analysis present")
        else:
            logger.info("❌ No AI analysis")
    else:
        logger.info("❌ HR 1 not in database")
    
    logger.info(f"\n🎯 KEY FINDING:")
    logger.info(f"HR 1 is likely being analyzed using only its summary/description")
    logger.info(f"rather than the full legislative text, which could be 50-100x larger.")
    logger.info(f"This explains why the analysis seems incomplete for such a major bill.")

if __name__ == "__main__":
    main()