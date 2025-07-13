#!/usr/bin/env python3
"""
Fix category mappings for bills that have AI analysis with policy categories but missing mappings
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from db_models import Bill, BillCategoryMapping
from services.enhanced_ai_analyzer import EnhancedAIAnalyzer
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def fix_category_mappings():
    """Fix category mappings for bills that have analysis but missing mappings"""
    
    with app.app_context():
        # Find bills without category mappings
        bills_without_mappings = db.session.query(Bill).outerjoin(BillCategoryMapping).filter(BillCategoryMapping.bill_id.is_(None)).all()
        
        logger.info(f"Found {len(bills_without_mappings)} bills without category mappings")
        
        analyzer = EnhancedAIAnalyzer()
        fixed_count = 0
        skipped_count = 0
        
        for bill in bills_without_mappings:
            try:
                # Check if bill has AI analysis with categories
                ai_analysis = bill.get_active_ai_analysis()
                if not ai_analysis:
                    logger.debug(f"Skipping {bill.get_bill_identifier()}: No AI analysis")
                    skipped_count += 1
                    continue
                
                analysis_data = ai_analysis.get_analysis_data()
                if 'policy_implications' not in analysis_data:
                    logger.debug(f"Skipping {bill.get_bill_identifier()}: No policy_implications")
                    skipped_count += 1
                    continue
                
                policy_data = analysis_data['policy_implications']
                if 'categories' not in policy_data or not isinstance(policy_data['categories'], list):
                    logger.debug(f"Skipping {bill.get_bill_identifier()}: No categories in policy_implications")
                    skipped_count += 1
                    continue
                
                categories = policy_data['categories']
                if not categories:
                    logger.debug(f"Skipping {bill.get_bill_identifier()}: Empty categories list")
                    skipped_count += 1
                    continue
                
                # Apply category mappings
                logger.info(f"Applying category mappings for {bill.get_bill_identifier()} ({len(categories)} categories)")
                analyzer._store_policy_categories(bill, categories, analysis_data)
                
                # Verify mappings were created
                mapping_count = db.session.query(BillCategoryMapping).filter_by(bill_id=bill.id).count()
                if mapping_count > 0:
                    logger.info(f"✅ Successfully created {mapping_count} category mappings for {bill.get_bill_identifier()}")
                    fixed_count += 1
                else:
                    logger.warning(f"⚠️ No mappings created for {bill.get_bill_identifier()}")
                
            except Exception as e:
                logger.error(f"❌ Error processing {bill.get_bill_identifier()}: {e}")
                skipped_count += 1
                continue
        
        # Final summary
        logger.info(f"\n" + "="*50)
        logger.info(f"CATEGORY MAPPING FIX SUMMARY")
        logger.info(f"="*50)
        logger.info(f"Total bills processed: {len(bills_without_mappings)}")
        logger.info(f"Bills fixed (mappings created): {fixed_count}")
        logger.info(f"Bills skipped (no data or errors): {skipped_count}")
        
        # Updated stats
        total_bills = Bill.query.count()
        bills_with_mapping = db.session.query(Bill).join(BillCategoryMapping).distinct().count()
        bills_without_mapping = total_bills - bills_with_mapping
        
        logger.info(f"\nFINAL DATABASE STATE:")
        logger.info(f"Total bills: {total_bills}")
        logger.info(f"Bills with category mappings: {bills_with_mapping}")
        logger.info(f"Bills without category mappings: {bills_without_mapping}")
        
        if bills_without_mapping > 0:
            logger.info(f"\nRemaining {bills_without_mapping} bills need AI analysis with policy categorization first")

if __name__ == "__main__":
    fix_category_mappings()