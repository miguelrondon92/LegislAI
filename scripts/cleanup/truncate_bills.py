#!/usr/bin/env python3
"""
Script to truncate the bills table and all its related tables.
This will allow you to fetch recent bills again from scratch.
"""

import os
import sys
import logging

# Add the current directory to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from db_models import Bill, BillAction, Alert, UserBillAlignment, WatchlistItem

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def truncate_bills_and_related():
    """Truncate bills table and all related tables"""
    with app.app_context():
        try:
            logger.info("Starting truncation of bills and related tables...")
            
            # Get counts before truncation
            bill_count = Bill.query.count()
            bill_action_count = BillAction.query.count()
            alert_count = Alert.query.count()
            alignment_count = UserBillAlignment.query.count()
            watchlist_count = WatchlistItem.query.count()
            
            logger.info(f"Current counts:")
            logger.info(f"  - Bills: {bill_count}")
            logger.info(f"  - Bill Actions: {bill_action_count}")
            logger.info(f"  - Alerts: {alert_count}")
            logger.info(f"  - User Bill Alignments: {alignment_count}")
            logger.info(f"  - Watchlist Items: {watchlist_count}")
            
            # Check if running non-interactively
            import sys
            if not sys.stdin.isatty():
                logger.info("Running non-interactively, proceeding with truncation...")
            else:
                # Confirm with user
                response = input(f"\nThis will delete {bill_count} bills and all related data. Continue? (y/N): ")
                if response.lower() != 'y':
                    logger.info("Truncation cancelled by user.")
                    return
            
            # Truncate in order (child tables first, then parent)
            logger.info("Truncating child tables...")
            
            # 1. Delete bill actions (child of bill)
            deleted_actions = BillAction.query.delete()
            logger.info(f"Deleted {deleted_actions} bill actions")
            
            # 2. Delete alerts (child of bill)
            deleted_alerts = Alert.query.delete()
            logger.info(f"Deleted {deleted_alerts} alerts")
            
            # 3. Delete user bill alignments (child of bill)
            deleted_alignments = UserBillAlignment.query.delete()
            logger.info(f"Deleted {deleted_alignments} user bill alignments")
            
            # 4. Delete watchlist items (child of bill)
            deleted_watchlist = WatchlistItem.query.delete()
            logger.info(f"Deleted {deleted_watchlist} watchlist items")
            
            # 5. Finally, delete bills (parent table)
            deleted_bills = Bill.query.delete()
            logger.info(f"Deleted {deleted_bills} bills")
            
            # Commit all changes
            db.session.commit()
            
            logger.info("✅ Successfully truncated all bills and related tables!")
            
            # Verify truncation
            new_bill_count = Bill.query.count()
            new_bill_action_count = BillAction.query.count()
            new_alert_count = Alert.query.count()
            new_alignment_count = UserBillAlignment.query.count()
            new_watchlist_count = WatchlistItem.query.count()
            
            logger.info(f"New counts:")
            logger.info(f"  - Bills: {new_bill_count}")
            logger.info(f"  - Bill Actions: {new_bill_action_count}")
            logger.info(f"  - Alerts: {new_alert_count}")
            logger.info(f"  - User Bill Alignments: {new_alignment_count}")
            logger.info(f"  - Watchlist Items: {new_watchlist_count}")
            
        except Exception as e:
            logger.error(f"Error during truncation: {str(e)}")
            db.session.rollback()
            raise

def main():
    """Main function"""
    logger.info("Bill truncation utility")
    logger.info("This will delete ALL bills and related data from the database.")
    logger.info("Make sure you have a backup if needed.")
    
    truncate_bills_and_related()

if __name__ == "__main__":
    main() 