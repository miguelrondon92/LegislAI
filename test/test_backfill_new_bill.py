#!/usr/bin/env python3
"""
Test script to add a new bill using the backfill system and test new database structure
"""

from app import app, db
from db_models import Bill, AIAnalysis, Summary
from services.congress_api import CongressAPI
from services.enhanced_ai_analyzer import EnhancedAIAnalyzer
import time

def test_new_bill_insertion():
    """Test inserting a new bill and creating AI analysis using new table structure"""
    
    with app.app_context():
        print("=== Testing New Bill Insertion with New Database Structure ===\n")
        
        # Initialize services
        congress_api = CongressAPI()
        ai_analyzer = EnhancedAIAnalyzer()
        
        # Test bill: HR2 (different from existing bills)
        congress = 119
        bill_type = "hr"
        bill_number = 2
        
        print(f"Testing bill: {congress}-{bill_type.upper()}{bill_number}")
        
        # Check if bill already exists
        existing_bill = Bill.query.filter_by(
            congress=congress,
            bill_type=bill_type,
            bill_number=bill_number
        ).first()
        
        if existing_bill:
            print(f"❌ Bill {congress}-{bill_type.upper()}{bill_number} already exists!")
            return
        
        print("✅ Bill not in database, proceeding with insertion...")
        
        # Step 1: Fetch bill data from Congress API
        print("\n--- Step 1: Fetching from Congress API ---")
        try:
            bill_data = congress_api.get_bill_details(congress, bill_type, bill_number)
            if not bill_data:
                print("❌ Could not fetch bill data from Congress API")
                return
            
            print(f"✅ Fetched bill data: {bill_data.get('title', 'No title')[:100]}...")
            
        except Exception as e:
            print(f"❌ Error fetching from Congress API: {e}")
            return
        
        # Step 2: Create Bill record
        print("\n--- Step 2: Creating Bill record ---")
        try:
            # Parse introduced date if available
            introduced_date = None
            if bill_data.get('introducedDate'):
                try:
                    introduced_date = datetime.strptime(bill_data['introducedDate'], '%Y-%m-%d')
                except:
                    pass
            
            bill = Bill(
                congress=congress,
                bill_type=bill_type,
                bill_number=bill_number,
                title=bill_data.get('title'),
                summary=bill_data.get('summary', {}).get('text') if bill_data.get('summary') else None,
                introduced_date=introduced_date,
                status=bill_data.get('latestAction', {}).get('text'),
                sponsor_name=bill_data.get('sponsors', [{}])[0].get('fullName') if bill_data.get('sponsors') else None,
                congress_api_url=bill_data.get('url'),
                active=True,
                version=1
            )
            
            db.session.add(bill)
            db.session.commit()
            
            print(f"✅ Created Bill record with ID: {bill.id}")
            
        except Exception as e:
            print(f"❌ Error creating Bill record: {e}")
            db.session.rollback()
            return
        
        # Step 3: Test AI Analysis with new table structure
        print("\n--- Step 3: Performing AI Analysis ---")
        try:
            # Create some sample text for analysis (since Congress API might not have full text)
            sample_text = f"""
            {bill.title or 'Sample Bill'}
            
            This is a sample bill for testing the new database structure.
            The bill aims to improve legislative processes and ensure proper
            data management within congressional databases.
            
            SECTION 1. SHORT TITLE.
            This Act may be cited as the "Database Structure Improvement Act".
            
            SECTION 2. FINDINGS.
            Congress finds that proper database design is crucial for
            efficient legislative analysis and tracking.
            
            SECTION 3. IMPLEMENTATION.
            The improvements shall be implemented within 90 days of enactment.
            """
            
            print(f"📝 Analyzing bill text ({len(sample_text)} characters)...")
            
            # Perform AI analysis - this should use the new table structure
            start_time = time.time()
            analysis = ai_analyzer.analyze_bill(bill)
            processing_time = time.time() - start_time
            
            if analysis:
                print(f"✅ AI Analysis completed in {processing_time:.2f} seconds")
                print(f"   Analysis keys: {list(analysis.keys())[:5]}...")
                
                # Check if new records were created
                ai_analysis_record = bill.get_active_ai_analysis()
                summary_record = bill.get_active_summary()
                
                if ai_analysis_record:
                    print(f"✅ AIAnalysis record created:")
                    print(f"   ID: {ai_analysis_record.id}")
                    print(f"   Version: {ai_analysis_record.analysis_version}")
                    print(f"   Method: {ai_analysis_record.analysis_method}")
                    print(f"   Complexity: {ai_analysis_record.complexity_score}")
                    print(f"   Active: {ai_analysis_record.active}")
                else:
                    print("❌ No AIAnalysis record found")
                
                if summary_record:
                    print(f"✅ Summary record created:")
                    print(f"   ID: {summary_record.id}")
                    print(f"   Version: {summary_record.summary_version}")
                    print(f"   Type: {summary_record.summary_type}")
                    print(f"   Active: {summary_record.active}")
                    print(f"   Summary length: {len(summary_record.summary_text or '') if summary_record.summary_text else 0} chars")
                else:
                    print("❌ No Summary record found")
                
            else:
                print("❌ AI Analysis failed")
                
        except Exception as e:
            print(f"❌ Error during AI analysis: {e}")
            import traceback
            traceback.print_exc()
        
        # Step 4: Test the new methods
        print("\n--- Step 4: Testing New Bill Methods ---")
        try:
            complexity = bill.get_complexity_score_new()
            controversy = bill.get_controversy_score_new()
            summary_text = bill.get_summary_text()
            
            print(f"✅ New method test results:")
            print(f"   get_complexity_score_new(): {complexity}")
            print(f"   get_controversy_score_new(): {controversy}")
            print(f"   get_summary_text(): {len(summary_text or '') if summary_text else 0} chars")
            
        except Exception as e:
            print(f"❌ Error testing new methods: {e}")
        
        print(f"\n=== Test Completed for Bill ID: {bill.id} ===")
        return bill

if __name__ == '__main__':
    test_new_bill_insertion()