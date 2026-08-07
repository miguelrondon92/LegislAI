#!/usr/bin/env python3
"""
Script to process bill items from seen_items.json
"""

import logging
import sys
import os

# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from services.bill_processor import BillProcessor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def main():
    """Main function to process seen items"""
    try:
        with app.app_context():
            # Initialize the bill processor
            processor = BillProcessor()
            
            # Process all items from seen_items.json
            processed_bills = processor.process_seen_items()
            
            if processed_bills:
                print(f"✅ Successfully processed {len(processed_bills)} bills:")
                for bill in processed_bills:
                    print(f"  - {bill.get_bill_identifier()}: {bill.title[:50]}...")
                    
                    # Check if policy categories were populated
                    policy_categories = bill.get_policy_categories()
                    if policy_categories:
                        primary_area = policy_categories.get('primary_policy_area', 'Unknown')
                        print(f"    Policy Area: {primary_area}")
                    else:
                        print(f"    Policy Area: Not analyzed yet")
            else:
                print("❌ No bills were processed")
                
    except Exception as e:
        logging.error(f"Error in main: {str(e)}")
        print(f"❌ Error: {str(e)}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code) 