#!/usr/bin/env python3
"""
Backfill specific bill: 119th Congress HR 1

This script demonstrates how to backfill a specific bill by fetching it directly
from the Congress API and processing it through the full workflow.
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

def backfill_hr1_method1_direct_api():
    """Method 1: Direct API fetch and processing"""
    logger.info("🎯 METHOD 1: Direct API Fetch")
    logger.info("=" * 50)
    
    try:
        from app import app, db
        from db_models import Bill, BillAction
        from services.congress_api import get_shared_congress_api
        from services.bill_processor import BillProcessor
        from services.enhanced_ai_analyzer import EnhancedAIAnalyzer
        from services import bill_sync
        
        congress_api = get_shared_congress_api()
        bill_processor = BillProcessor(congress_api=congress_api)
        ai_analyzer = EnhancedAIAnalyzer()
        
        with app.app_context():
            # Check if HR 1 already exists
            existing_bill = Bill.query.filter_by(
                congress=119,
                bill_type='hr',
                bill_number=1
            ).first()
            
            if existing_bill:
                logger.info(f"HR 1 already exists: {existing_bill.get_bill_identifier()}")
                logger.info(f"Title: {existing_bill.title}")
                return existing_bill
            
            logger.info("Fetching HR 1 from Congress API...")
            
            # Fetch bill details
            bill_data = congress_api.get_bill_details(119, 'hr', 1)
            
            if not bill_data:
                logger.error("❌ Could not fetch HR 1 from Congress API")
                return None
            
            logger.info("✅ Bill data fetched successfully")
            logger.info(f"Title: {bill_data.get('title', 'No title')}")
            
            # Process bill data
            logger.info("Processing bill data...")
            bill = bill_processor.process_bill_data(bill_data)
            
            if not bill:
                logger.error("❌ Failed to process bill data")
                return None
            
            logger.info(f"✅ Bill processed: {bill.get_bill_identifier()}")
            
            # Fetch bill actions via shared sync
            logger.info("Fetching bill actions...")
            bill_sync.refresh_activity(bill, congress_api=congress_api)
            
            actions_count = len(bill.actions)
            logger.info(f"✅ Fetched {actions_count} actions")
            
            # Perform AI analysis
            logger.info("Performing AI analysis...")
            bill_text = bill.summary or bill.title
            if bill_text:
                analysis = ai_analyzer.analyze_bill(bill_text, bill.title)
                if analysis:
                    bill.set_ai_analysis(analysis)
                    logger.info("✅ AI analysis completed")
                else:
                    logger.warning("⚠️ AI analysis failed")
            
            # Create category mappings
            logger.info("Creating category mappings...")
            from services.backfill_orchestrator import BackfillOrchestrator, BackfillConfig
            config = BackfillConfig()
            orchestrator = BackfillOrchestrator(config)
            
            if bill.get_ai_analysis():
                orchestrator._create_category_mappings(bill, bill.get_ai_analysis())
                logger.info("✅ Category mappings created")
            
            db.session.commit()
            
            logger.info(f"🎉 HR 1 successfully backfilled!")
            logger.info(f"   Bill ID: {bill.get_bill_identifier()}")
            logger.info(f"   Title: {bill.title}")
            logger.info(f"   Actions: {len(bill.actions)}")
            logger.info(f"   AI Analysis: {'✅' if bill.ai_analysis else '❌'}")
            
            return bill
            
    except Exception as e:
        logger.error(f"❌ Method 1 failed: {e}")
        import traceback
        traceback.print_exc()
        return None

def backfill_hr1_method2_orchestrator():
    """Method 2: Using BackfillOrchestrator for single bill"""
    logger.info("\n🎯 METHOD 2: Using BackfillOrchestrator")
    logger.info("=" * 50)
    
    try:
        from app import app, db
        from db_models import Bill
        from services.backfill_orchestrator import BackfillOrchestrator, BackfillConfig
        
        with app.app_context():
            # Create a bill info structure for HR 1
            hr1_bill_info = {
                'identifier': '119-HR1',
                'congress': 119,
                'bill_type': 'hr',
                'bill_number': 1,
                'title': 'HR 1 - To be fetched',
                'existing_in_db': False
            }
            
            # Use orchestrator to process single bill
            config = BackfillConfig()
            orchestrator = BackfillOrchestrator(config)
            
            logger.info("Processing HR 1 through orchestrator...")
            success = orchestrator._process_single_bill(hr1_bill_info)
            
            if success:
                # Check result
                bill = Bill.query.filter_by(
                    congress=119,
                    bill_type='hr',
                    bill_number=1
                ).first()
                
                if bill:
                    logger.info(f"✅ HR 1 processed successfully!")
                    logger.info(f"   Title: {bill.title}")
                    logger.info(f"   Actions: {len(bill.actions)}")
                    logger.info(f"   AI Analysis: {'✅' if bill.ai_analysis else '❌'}")
                    return bill
                else:
                    logger.error("❌ Bill processed but not found in database")
                    return None
            else:
                logger.error("❌ Orchestrator processing failed")
                return None
                
    except Exception as e:
        logger.error(f"❌ Method 2 failed: {e}")
        return None

def backfill_hr1_method3_route():
    """Method 3: Using the web route (simulates user visiting page)"""
    logger.info("\n🎯 METHOD 3: Using Web Route")
    logger.info("=" * 50)
    
    try:
        from app import app
        from db_models import Bill
        
        with app.app_context():
            with app.test_client() as client:
                logger.info("Visiting HR 1 page to trigger backfill...")
                
                # Visit the bill page - this will trigger automatic fetching
                response = client.get('/bill/119/hr/1')
                
                logger.info(f"Response status: {response.status_code}")
                
                if response.status_code == 200:
                    # Check if bill was created
                    bill = Bill.query.filter_by(
                        congress=119,
                        bill_type='hr',
                        bill_number=1
                    ).first()
                    
                    if bill:
                        logger.info(f"✅ HR 1 backfilled via web route!")
                        logger.info(f"   Title: {bill.title}")
                        logger.info(f"   Actions: {len(bill.actions)}")
                        logger.info(f"   AI Analysis: {'✅' if bill.ai_analysis else '❌'}")
                        return bill
                    else:
                        logger.error("❌ Page loaded but bill not found")
                        return None
                else:
                    logger.error(f"❌ Page load failed: {response.status_code}")
                    return None
                    
    except Exception as e:
        logger.error(f"❌ Method 3 failed: {e}")
        return None

def show_hr1_info(bill):
    """Display detailed information about HR 1"""
    if not bill:
        logger.warning("No bill to display")
        return
    
    logger.info("\n📋 HR 1 DETAILS")
    logger.info("=" * 50)
    logger.info(f"Identifier: {bill.get_bill_identifier()}")
    logger.info(f"Title: {bill.title}")
    logger.info(f"Status: {bill.status}")
    logger.info(f"Sponsor: {bill.sponsor_name}")
    logger.info(f"Introduced: {bill.introduced_date}")
    logger.info(f"Last Action: {bill.last_action_date}")
    
    logger.info(f"\nActions: {len(bill.actions)}")
    for i, action in enumerate(bill.actions[:5]):  # Show first 5
        logger.info(f"  {i+1}. {action.get_formatted_date()} - {action.action_type}")
        logger.info(f"     {action.action_text[:100]}...")
    
    if len(bill.actions) > 5:
        logger.info(f"  ... and {len(bill.actions) - 5} more actions")
    
    analysis = bill.get_ai_analysis()
    if analysis:
        logger.info(f"\nAI Analysis: ✅ Available")
        if 'policy_implications' in analysis:
            categories = analysis['policy_implications'].get('categories', [])
            logger.info(f"Policy Categories: {len(categories)}")
            for cat in categories[:3]:
                logger.info(f"  - {cat.get('area', 'Unknown')}: {cat.get('impact_level', 'unknown')} impact")
    else:
        logger.info(f"\nAI Analysis: ❌ Not available")
    
    logger.info(f"\n🔗 View at: http://127.0.0.1:5000/bill/119/hr/1")

def main():
    """Main function to backfill HR 1"""
    logger.info("🎯 BACKFILL HR 1 - 119th CONGRESS")
    logger.info("=" * 60)
    
    # Try methods in order of preference
    methods = [
        ("Direct API", backfill_hr1_method1_direct_api),
        ("Orchestrator", backfill_hr1_method2_orchestrator),
        ("Web Route", backfill_hr1_method3_route),
    ]
    
    bill = None
    
    for method_name, method_func in methods:
        logger.info(f"\n🔄 Trying {method_name} method...")
        
        try:
            bill = method_func()
            if bill:
                logger.info(f"✅ {method_name} method succeeded!")
                break
            else:
                logger.warning(f"⚠️ {method_name} method failed")
        except Exception as e:
            logger.error(f"❌ {method_name} method crashed: {e}")
    
    if bill:
        show_hr1_info(bill)
        logger.info("\n🎉 HR 1 BACKFILL SUCCESSFUL!")
    else:
        logger.error("\n❌ All methods failed to backfill HR 1")
        
        logger.info("\n💡 MANUAL ALTERNATIVES:")
        logger.info("1. Visit http://127.0.0.1:5000/bill/119/hr/1 in browser")
        logger.info("2. Use Congress API directly:")
        logger.info("   python -c \"from services.congress_api import CongressAPI; api=CongressAPI(); print(api.get_bill_details(119, 'hr', 1))\"")
        logger.info("3. Run backfill orchestrator:")
        logger.info("   python services/backfill_orchestrator.py --congress 119 --mode gaps")

if __name__ == "__main__":
    main()