#!/usr/bin/env python3
"""
Simple script to fetch recent bills from the Congress API and store them in the database.
This version focuses on efficiency and getting the most recent bills quickly.
"""

import os
import sys
import logging
from datetime import datetime, timedelta

# Add the current directory to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from models import Bill, BillAction
from services.congress_api import CongressAPI
from services.bill_processor import BillProcessor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def fetch_recent_bills_simple(days=10, max_bills=50):
    """
    Fetch recent bills using a simpler approach - get the most recent bills
    and filter by date after fetching.
    
    Args:
        days (int): Number of days to look back (default: 10)
        max_bills (int): Maximum number of bills to process (default: 50)
    """
    with app.app_context():
        congress_api = CongressAPI()
        bill_processor = BillProcessor()
        
        logger.info(f"Starting to fetch recent bills (last {days} days)...")
        
        # Calculate cutoff date
        cutoff_date = datetime.now() - timedelta(days=days)
        logger.info(f"Cutoff date: {cutoff_date.strftime('%Y-%m-%d')}")
        
        bills_stored = 0
        bills_skipped = 0
        
        try:
            # Get the most recent bills (we'll fetch more than we need to account for date filtering)
            fetch_limit = min(max_bills * 3, 250)  # Fetch 3x more to account for date filtering
            
            logger.info(f"Fetching {fetch_limit} most recent bills...")
            
            # Make a single API call to get recent bills
            params = {
                'limit': fetch_limit,
                'sort': 'updateDate+desc'
            }
            
            endpoint = "/bill"
            data = congress_api._make_request(endpoint, params)
            
            if not data or 'bills' not in data:
                logger.error("No bills data received from Congress API")
                return
            
            bill_list = data['bills']
            logger.info(f"Received {len(bill_list)} bills from Congress API")
            
            # Filter bills by date and process them
            recent_bills = []
            for bill_summary in bill_list:
                update_date_str = bill_summary.get('updateDate')
                if not update_date_str:
                    continue
                
                try:
                    update_date = datetime.fromisoformat(update_date_str.replace('Z', '+00:00'))
                    if update_date.replace(tzinfo=None) >= cutoff_date:
                        recent_bills.append(bill_summary)
                        
                        if len(recent_bills) >= max_bills:
                            break
                except Exception as e:
                    logger.warning(f"Error parsing date {update_date_str}: {str(e)}")
                    continue
            
            logger.info(f"Found {len(recent_bills)} bills from the last {days} days")
            
            # Process each recent bill
            for i, bill_summary in enumerate(recent_bills, 1):
                try:
                    congress = bill_summary.get('congress')
                    bill_type = bill_summary.get('type', '').lower()
                    bill_number = bill_summary.get('number')
                    
                    if not all([congress, bill_type, bill_number]):
                        logger.warning(f"Missing required bill data: {bill_summary}")
                        bills_skipped += 1
                        continue
                    
                    logger.info(f"Processing bill {i}/{len(recent_bills)}: {bill_type.upper()}-{bill_number}")
                    
                    # Check if bill already exists in database
                    existing_bill = Bill.query.filter_by(
                        congress=congress,
                        bill_type=bill_type,
                        bill_number=bill_number
                    ).first()
                    
                    if existing_bill:
                        logger.info(f"Bill already exists: {bill_type.upper()}-{bill_number}")
                        bills_skipped += 1
                        continue
                    
                    # Get detailed bill information
                    logger.info(f"Fetching details for {bill_type.upper()}-{bill_number}...")
                    detailed_bill = congress_api.get_bill_details(congress, bill_type, bill_number)
                    
                    if not detailed_bill:
                        logger.warning(f"Could not fetch details for {bill_type.upper()}-{bill_number}")
                        bills_skipped += 1
                        continue
                    
                    # Process and store the bill
                    bill = bill_processor.process_bill_data(detailed_bill)
                    
                    if bill:
                        bills_stored += 1
                        logger.info(f"Successfully stored: {bill.get_bill_identifier()}")
                    else:
                        logger.error(f"Failed to process bill: {bill_type.upper()}-{bill_number}")
                        bills_skipped += 1
                    
                    # Add a small delay to be respectful to the API
                    import time
                    time.sleep(0.1)
                    
                except Exception as e:
                    logger.error(f"Error processing bill: {str(e)}")
                    bills_skipped += 1
                    continue
            
            # Commit any remaining changes
            db.session.commit()
            
            logger.info(f"Fetch operation completed:")
            logger.info(f"  - Bills stored: {bills_stored}")
            logger.info(f"  - Bills skipped: {bills_skipped}")
            
        except Exception as e:
            logger.error(f"Error during bill fetching: {str(e)}")
            db.session.rollback()

def main():
    """Main function to run the bill fetching script"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Fetch recent bills from Congress API (Simple Version)')
    parser.add_argument('--days', type=int, default=10, 
                       help='Number of days to look back (default: 10)')
    parser.add_argument('--max-bills', type=int, default=50,
                       help='Maximum number of bills to process (default: 50)')
    
    args = parser.parse_args()
    
    fetch_recent_bills_simple(days=args.days, max_bills=args.max_bills)

if __name__ == "__main__":
    main() 