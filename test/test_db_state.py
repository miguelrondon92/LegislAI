#!/usr/bin/env python3

"""Check database state and analysis data"""

from app import app
from db_models import db, Bill, AIAnalysis, Summary, BillCategoryMapping, PolicyCategory
import json

def check_database_state():
    with app.app_context():
        print('=== DATABASE ANALYSIS ===')
        
        # Count bills in database  
        total_bills = Bill.query.count()
        print(f'Total bills in database: {total_bills}')
        
        # Count bills with old AI analysis
        bills_with_old_analysis = Bill.query.filter(Bill.ai_analysis.isnot(None)).filter(Bill.ai_analysis != '').count()
        print(f'Bills with old AI analysis: {bills_with_old_analysis}')
        
        # Count bills with new AI analysis
        bills_with_new_analysis = AIAnalysis.query.count()
        print(f'Bills with new AI analysis: {bills_with_new_analysis}')
        
        # Count summary records
        summary_count = Summary.query.count()
        print(f'Summary records: {summary_count}')
        
        # Count category mappings
        category_mappings = BillCategoryMapping.query.count()
        print(f'Category mappings: {category_mappings}')
        
        # Count category mappings with sneakiness scores
        sneaky_mappings = BillCategoryMapping.query.filter(BillCategoryMapping.sneakiness_score > 0).count()
        print(f'Category mappings with sneakiness scores: {sneaky_mappings}')
        
        # Count policy categories
        policy_categories = PolicyCategory.query.count()
        print(f'Policy categories: {policy_categories}')
        
        # Show recent bills with analysis
        recent_bills = Bill.query.order_by(Bill.id.desc()).limit(5).all()
        print(f'\n=== RECENT BILLS ANALYSIS ===')
        for bill in recent_bills:
            print(f'Bill: {bill.get_bill_identifier()} - {bill.title[:50]}...')
            print(f'  Old analysis: {"Yes" if bill.ai_analysis else "No"}')
            
            # Check new analysis
            new_analysis = AIAnalysis.query.filter_by(bill_id=bill.id, active=True).first()
            print(f'  New analysis: {"Yes" if new_analysis else "No"}')
            
            # Check summary
            summary = Summary.query.filter_by(bill_id=bill.id).first()
            print(f'  Summary: {"Yes" if summary else "No"}')
            
            # Check category mappings
            mappings = BillCategoryMapping.query.filter_by(bill_id=bill.id).count()
            print(f'  Category mappings: {mappings}')
            
            # Check for sneakiness
            sneaky_mappings = BillCategoryMapping.query.filter_by(bill_id=bill.id).filter(BillCategoryMapping.sneakiness_score > 0).count()
            print(f'  Sneakiness mappings: {sneaky_mappings}')
            print()

if __name__ == "__main__":
    check_database_state()