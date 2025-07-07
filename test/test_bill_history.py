#!/usr/bin/env python3
"""
Test bill history functionality and check current data
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

def test_bill_history_data():
    """Check what bill history data we currently have"""
    logger.info("🔍 TESTING BILL HISTORY DATA")
    logger.info("=" * 50)
    
    try:
        from app import app, db
        from db_models import Bill, BillAction
        
        with app.app_context():
            # Get bills and their actions
            bills = Bill.query.all()
            logger.info(f"Found {len(bills)} bills in database")
            
            for bill in bills:
                logger.info(f"\n📄 Bill: {bill.get_bill_identifier()}")
                logger.info(f"   Title: {bill.title}")
                logger.info(f"   Status: {bill.status}")
                logger.info(f"   Introduced: {bill.introduced_date}")
                logger.info(f"   Last Action: {bill.last_action_date}")
                
                # Check actions
                actions = bill.actions
                logger.info(f"   Actions count: {len(actions)}")
                
                if actions:
                    logger.info("   📋 Action History:")
                    for i, action in enumerate(actions[:5]):  # Show first 5
                        logger.info(f"      {i+1}. {action.action_date} - {action.action_type}")
                        logger.info(f"         {action.action_text[:100]}...")
                else:
                    logger.info("   ⚠️ No actions found - may need to fetch from Congress API")
                    
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

def test_bill_page_with_history():
    """Test the bill page to see if history is displayed"""
    logger.info("\n🌐 TESTING BILL PAGE HISTORY DISPLAY")
    logger.info("=" * 50)
    
    try:
        from app import app
        from db_models import Bill
        
        with app.app_context():
            # Get a bill to test
            bill = Bill.query.first()
            if not bill:
                logger.warning("No bills found to test")
                return
                
            logger.info(f"Testing bill page for: {bill.get_bill_identifier()}")
            
            with app.test_client() as client:
                url = f'/bill/{bill.congress}/{bill.bill_type}/{bill.bill_number}'
                response = client.get(url)
                
                logger.info(f"Bill page status: {response.status_code}")
                
                if response.status_code == 200:
                    content = response.get_data(as_text=True)
                    
                    # Check for history elements
                    history_indicators = [
                        'Legislative History',
                        'timeline',
                        'action',
                        'Bill Actions'
                    ]
                    
                    found_indicators = []
                    for indicator in history_indicators:
                        if indicator.lower() in content.lower():
                            found_indicators.append(indicator)
                    
                    logger.info(f"History elements found: {found_indicators}")
                    
                    if 'Legislative History' in content:
                        logger.info("✅ Legislative History section exists")
                    else:
                        logger.info("⚠️ Legislative History section not found")
                        
                    if 'timeline' in content.lower():
                        logger.info("✅ Timeline structure exists")
                    else:
                        logger.info("⚠️ Timeline structure not found")
                        
                else:
                    logger.error(f"Bill page failed: {response.status_code}")
                    
    except Exception as e:
        logger.error(f"❌ Bill page test failed: {e}")

def main():
    """Main test function"""
    test_bill_history_data()
    test_bill_page_with_history()
    
    logger.info("\n📋 BILL HISTORY ENHANCEMENT PLAN:")
    logger.info("1. Add method to fetch bill actions from Congress API")
    logger.info("2. Enhance BillAction model with better formatting")
    logger.info("3. Improve timeline visualization")
    logger.info("4. Add progress tracking (introduced -> committee -> floor -> enacted)")
    logger.info("5. Add bill status badges and progress indicators")

if __name__ == "__main__":
    main()