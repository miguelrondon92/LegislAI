#!/usr/bin/env python3
"""
Script to fetch all bills from the last 10 days using the Congress API
and store them in the database.
"""

import os
import sys
import logging
from datetime import datetime, timedelta
from sqlalchemy import text

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

def fetch_recent_bills(days=10, max_bills=1000):
    """
    Fetch all bills from the last N days and store them in the database.
    
    Args:
        days (int): Number of days to look back (default: 10)
        max_bills (int): Maximum number of bills to process (default: 1000)
    """
    with app.app_context():
        congress_api = CongressAPI()
        bill_processor = BillProcessor()
        
        logger.info(f"Starting to fetch bills from the last {days} days...")
        
        # Calculate cutoff date
        cutoff_date = datetime.now() - timedelta(days=days)
        end_date = datetime.now()
        logger.info(f"Date range: {cutoff_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
        
        bills_stored = 0
        bills_skipped = 0
        
        try:
            # Use the enhanced method to get bills by date range
            logger.info("Fetching bills by update date...")
            bills_by_update = congress_api.get_bills_by_date_range(cutoff_date, end_date, max_bills)
            
            logger.info("Fetching bills by introduction date...")
            bills_by_intro = congress_api.get_bills_by_introduction_date(cutoff_date, end_date, max_bills)
            
            # Combine and deduplicate bills
            all_bills = {}
            for bill in bills_by_update + bills_by_intro:
                congress = bill.get('congress')
                bill_type = bill.get('type', '').lower()
                bill_number = bill.get('number')
                
                if all([congress, bill_type, bill_number]):
                    bill_key = f"{congress}-{bill_type}-{bill_number}"
                    all_bills[bill_key] = bill
            
            logger.info(f"Found {len(all_bills)} unique bills in the date range")
            
            # Process each unique bill
            for i, (bill_key, bill_summary) in enumerate(all_bills.items(), 1):
                try:
                    congress = bill_summary.get('congress')
                    bill_type = bill_summary.get('type', '').lower()
                    bill_number = bill_summary.get('number')
                    
                    logger.info(f"Processing bill {i}/{len(all_bills)}: {bill_type.upper()}-{bill_number}")
                    
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
                    logger.error(f"Error processing bill {bill_key}: {str(e)}")
                    bills_skipped += 1
                    continue
                
                # Check if we've reached the maximum number of bills to store
                if bills_stored >= max_bills:
                    logger.info(f"Reached maximum number of bills to store ({max_bills})")
                    break
            
            # Commit any remaining changes
            db.session.commit()
            
            logger.info(f"Fetch operation completed:")
            logger.info(f"  - Bills stored: {bills_stored}")
            logger.info(f"  - Bills skipped: {bills_skipped}")
            
        except Exception as e:
            logger.error(f"Error during bill fetching: {str(e)}")
            db.session.rollback()

def get_bills_by_date_range(start_date, end_date):
    """
    Alternative method to get bills by specific date range.
    This uses the Congress API's date filtering capabilities.
    """
    with app.app_context():
        congress_api = CongressAPI()
        bill_processor = BillProcessor()
        
        logger.info(f"Fetching bills from {start_date} to {end_date}")
        
        # Format dates for API
        start_str = start_date.strftime('%Y-%m-%d')
        end_str = end_date.strftime('%Y-%m-%d')
        
        # Use the search endpoint with date filters
        params = {
            'limit': 250,
            'sort': 'updateDate+desc',
            'fromDateTime': f"{start_str}T00:00:00Z",
            'toDateTime': f"{end_str}T23:59:59Z"
        }
        
        bills_stored = 0
        
        try:
            endpoint = "/bill"
            data = congress_api._make_request(endpoint, params)
            
            if not data or 'bills' not in data:
                logger.error("No bills data received from Congress API")
                return
            
            logger.info(f"Received {len(data['bills'])} bills from date range")
            
            for bill_summary in data['bills']:
                try:
                    congress = bill_summary.get('congress')
                    bill_type = bill_summary.get('type', '').lower()
                    bill_number = bill_summary.get('number')
                    
                    if not all([congress, bill_type, bill_number]):
                        continue
                    
                    # Check if bill already exists
                    existing_bill = Bill.query.filter_by(
                        congress=congress,
                        bill_type=bill_type,
                        bill_number=bill_number
                    ).first()
                    
                    if existing_bill:
                        continue
                    
                    # Get detailed bill information
                    detailed_bill = congress_api.get_bill_details(congress, bill_type, bill_number)
                    
                    if detailed_bill:
                        bill = bill_processor.process_bill_data(detailed_bill)
                        if bill:
                            bills_stored += 1
                            logger.info(f"Stored: {bill.get_bill_identifier()}")
                    
                    # Rate limiting
                    import time
                    time.sleep(0.1)
                    
                except Exception as e:
                    logger.error(f"Error processing bill: {str(e)}")
                    continue
            
            db.session.commit()
            logger.info(f"Stored {bills_stored} new bills from date range")
            
        except Exception as e:
            logger.error(f"Error during date range fetching: {str(e)}")
            db.session.rollback()

def main():
    """Main function to run the bill fetching script"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Fetch recent bills from Congress API')
    parser.add_argument('--days', type=int, default=10, 
                       help='Number of days to look back (default: 10)')
    parser.add_argument('--max-bills', type=int, default=1000,
                       help='Maximum number of bills to process (default: 1000)')
    parser.add_argument('--use-date-range', action='store_true',
                       help='Use specific date range instead of days back')
    parser.add_argument('--start-date', type=str,
                       help='Start date in YYYY-MM-DD format (for date range mode)')
    parser.add_argument('--end-date', type=str,
                       help='End date in YYYY-MM-DD format (for date range mode)')
    
    args = parser.parse_args()
    
    if args.use_date_range:
        if not args.start_date or not args.end_date:
            logger.error("Start date and end date are required for date range mode")
            return
        
        try:
            start_date = datetime.strptime(args.start_date, '%Y-%m-%d')
            end_date = datetime.strptime(args.end_date, '%Y-%m-%d')
        except ValueError as e:
            logger.error(f"Invalid date format: {str(e)}")
            return
        
        get_bills_by_date_range(start_date, end_date)
    else:
        fetch_recent_bills(days=args.days, max_bills=args.max_bills)

if __name__ == "__main__":
    main() 