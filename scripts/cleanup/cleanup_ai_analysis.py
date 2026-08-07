#!/usr/bin/env python3
"""
Script to clean up existing AI analysis error data from the database.
"""

import os
import sys
import json
import logging

# Add the current directory to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from db_models import Bill

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def cleanup_ai_analysis_errors():
    """Remove AI analysis data that contains error messages"""
    with app.app_context():
        try:
            # Get all bills with AI analysis
            bills = Bill.query.filter(Bill.ai_analysis.isnot(None)).all()
            
            cleaned_count = 0
            total_count = len(bills)
            
            logger.info(f"Found {total_count} bills with AI analysis data")
            
            for bill in bills:
                try:
                    analysis = bill.get_ai_analysis()
                    
                    # Check if analysis contains error messages
                    has_error = False
                    if isinstance(analysis, dict):
                        for key, value in analysis.items():
                            if isinstance(value, str) and "Unable to generate summary due to technical error" in value:
                                has_error = True
                                break
                            elif isinstance(value, dict):
                                for sub_key, sub_value in value.items():
                                    if isinstance(sub_value, str) and "Unable to generate summary due to technical error" in sub_value:
                                        has_error = True
                                        break
                    
                    if has_error:
                        # Clear the AI analysis
                        bill.ai_analysis = None
                        bill.complexity_score = None
                        bill.policy_categories = None
                        cleaned_count += 1
                        logger.info(f"Cleaned AI analysis for bill {bill.get_bill_identifier()}")
                        
                except Exception as e:
                    logger.error(f"Error processing bill {bill.get_bill_identifier()}: {str(e)}")
                    continue
            
            # Commit changes
            db.session.commit()
            
            logger.info(f"Cleanup completed: {cleaned_count} bills cleaned out of {total_count}")
            
        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}")
            db.session.rollback()

def main():
    """Main function"""
    logger.info("Starting AI analysis cleanup...")
    cleanup_ai_analysis_errors()
    logger.info("Cleanup finished.")

if __name__ == "__main__":
    main() 