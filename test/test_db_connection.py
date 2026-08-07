#!/usr/bin/env python3
"""Simple test to check database connectivity"""

try:
    from app import app
    from db_models import db, Bill, AIAnalysis, Summary
    
    with app.app_context():
        print("✅ Successfully imported models")
        
        # Check if tables exist
        try:
            total_bills = Bill.query.count()
            print(f"✅ Total bills in database: {total_bills}")
        except Exception as e:
            print(f"❌ Error querying bills: {e}")
            
        try:
            total_ai_analysis = AIAnalysis.query.count()
            print(f"✅ Total AI analyses in database: {total_ai_analysis}")
        except Exception as e:
            print(f"❌ Error querying AI analyses: {e}")
            
        try:
            total_summaries = Summary.query.count()
            print(f"✅ Total summaries in database: {total_summaries}")
        except Exception as e:
            print(f"❌ Error querying summaries: {e}")
            
        # Test creating a Bill method
        test_bill = Bill.query.first()
        if test_bill:
            print(f"✅ Found test bill: {test_bill.get_bill_identifier()}")
            
            # Test if the new methods exist
            if hasattr(test_bill, 'create_new_analysis_version'):
                print("✅ create_new_analysis_version method exists")
            else:
                print("❌ create_new_analysis_version method missing")
                
            if hasattr(test_bill, 'create_new_summary_version'):
                print("✅ create_new_summary_version method exists")
            else:
                print("❌ create_new_summary_version method missing")
                
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()