#!/usr/bin/env python3
"""
Script to perform AI analysis on existing bills that don't have it yet.
"""

import os
import sys
import logging

# Add the current directory to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from models import Bill
from services.ai_analyzer import AIAnalyzer
from services.congress_api import CongressAPI

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def perform_ai_analysis_on_existing_bills():
    """Perform AI analysis on bills that don't have it yet"""
    with app.app_context():
        try:
            ai_analyzer = AIAnalyzer()
            congress_api = CongressAPI()
            
            # Get bills without AI analysis
            bills_without_analysis = Bill.query.filter(Bill.ai_analysis.is_(None)).all()
            
            logger.info(f"Found {len(bills_without_analysis)} bills without AI analysis")
            
            if not bills_without_analysis:
                logger.info("All bills already have AI analysis")
                return
            
            processed_count = 0
            
            for bill in bills_without_analysis:
                try:
                    logger.info(f"Performing AI analysis on {bill.get_bill_identifier()}: {bill.title}")
                    
                    # Check if AI analyzer is available
                    if not ai_analyzer.client:
                        logger.warning(f"AI analyzer not available for bill {bill.get_bill_identifier()}. Skipping.")
                        continue
                    
                    # Perform AI analysis
                    analysis = ai_analyzer.analyze_bill(bill)
                    
                    # Only save analysis if it's valid and not empty
                    if analysis and isinstance(analysis, dict) and len(analysis) > 0:
                        # Check if analysis contains actual data (not just error messages)
                        has_valid_data = False
                        for key, value in analysis.items():
                            if value and value != "Unknown" and value != "Unable to generate summary due to technical error":
                                if isinstance(value, list) and len(value) > 0:
                                    has_valid_data = True
                                    break
                                elif isinstance(value, dict) and len(value) > 0:
                                    has_valid_data = True
                                    break
                                elif isinstance(value, str) and len(value) > 10:
                                    has_valid_data = True
                                    break
                                elif isinstance(value, (int, float)) and value != 0:
                                    has_valid_data = True
                                    break
                        
                        if has_valid_data:
                            bill.set_ai_analysis(analysis)
                            
                            # Extract complexity score
                            complexity_assessment = analysis.get('complexity_assessment', {})
                            if isinstance(complexity_assessment, dict):
                                complexity_score = complexity_assessment.get('complexity_score', 0)
                                if isinstance(complexity_score, (int, float)):
                                    bill.complexity_score = float(complexity_score)
                            
                            # Store policy categories
                            policy_implications = analysis.get('policy_implications', {})
                            if policy_implications and isinstance(policy_implications, dict):
                                bill.set_policy_categories(policy_implications)
                            
                            db.session.commit()
                            processed_count += 1
                            logger.info(f"✅ Successfully performed AI analysis for bill {bill.get_bill_identifier()}")
                        else:
                            logger.warning(f"AI analysis returned empty or error data for bill {bill.get_bill_identifier()}. Not saving to database.")
                    else:
                        logger.warning(f"No valid AI analysis returned for bill {bill.get_bill_identifier()}")
                        
                except Exception as e:
                    logger.error(f"Error performing AI analysis for bill {bill.get_bill_identifier()}: {str(e)}")
                    db.session.rollback()
                    continue
            
            logger.info(f"AI analysis completed: {processed_count} bills processed")
            
        except Exception as e:
            logger.error(f"Error during AI analysis: {str(e)}")
            db.session.rollback()

def main():
    """Main function"""
    logger.info("Starting AI analysis on existing bills...")
    perform_ai_analysis_on_existing_bills()
    logger.info("AI analysis process completed.")

if __name__ == "__main__":
    main() 