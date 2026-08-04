#!/usr/bin/env python3
"""Debug script to identify the issue with analysis metadata not being stored"""

import sys
import os
sys.path.insert(0, '.')

try:
    from app import app, db
    from db_models import Bill, AIAnalysis, Summary
    from services.enhanced_ai_analyzer import EnhancedAIAnalyzer
    
    print("✅ Successfully imported all required modules")
    
    with app.app_context():
        print("\n=== DATABASE CONNECTIVITY TEST ===")
        
        # Test database connectivity
        try:
            total_bills = Bill.query.count()
            print(f"✅ Total bills in database: {total_bills}")
        except Exception as e:
            print(f"❌ Error querying bills: {e}")
            sys.exit(1)
            
        try:
            total_ai_analyses = AIAnalysis.query.count()
            print(f"✅ Total AI analyses in database: {total_ai_analyses}")
        except Exception as e:
            print(f"❌ Error querying AI analyses: {e}")
            sys.exit(1)
            
        try:
            total_summaries = Summary.query.count()
            print(f"✅ Total summaries in database: {total_summaries}")
        except Exception as e:
            print(f"❌ Error querying summaries: {e}")
            sys.exit(1)
            
        print("\n=== BILL METHOD TEST ===")
        
        # Test Bill methods
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
                
            # Test the new methods
            print("\n=== TESTING NEW METHODS ===")
            
            try:
                # Test create_new_analysis_version
                test_analysis_data = {
                    'test': 'data',
                    'complexity_assessment': {
                        'complexity_score': 0.5
                    },
                    'controversy_score': 0.3
                }
                
                print("🔄 Testing create_new_analysis_version...")
                new_analysis = test_bill.create_new_analysis_version(
                    analysis_data=test_analysis_data,
                    complexity_score=0.5,
                    controversy_score=0.3,
                    analysis_method='test',
                    chunks_analyzed=1,
                    processing_time=1.0
                )
                
                if new_analysis:
                    print(f"✅ Successfully created new analysis version: {new_analysis.id}")
                    print(f"   - Analysis method: {new_analysis.analysis_method}")
                    print(f"   - Chunks analyzed: {new_analysis.chunks_analyzed}")
                    print(f"   - Processing time: {new_analysis.processing_time}")
                else:
                    print("❌ Failed to create new analysis version")
                    
            except Exception as e:
                print(f"❌ Error testing create_new_analysis_version: {e}")
                import traceback
                traceback.print_exc()
                
            try:
                # Test create_new_summary_version
                print("\n🔄 Testing create_new_summary_version...")
                new_summary = test_bill.create_new_summary_version(
                    summary_text="Test summary",
                    plain_language_summary="Plain language test",
                    key_provisions=["provision 1", "provision 2"],
                    funding_amounts="$1M",
                    implementation_timeline="2025",
                    summary_type='test'
                )
                
                if new_summary:
                    print(f"✅ Successfully created new summary version: {new_summary.id}")
                    print(f"   - Summary type: {new_summary.summary_type}")
                    print(f"   - Key provisions: {new_summary.get_key_provisions()}")
                else:
                    print("❌ Failed to create new summary version")
                    
            except Exception as e:
                print(f"❌ Error testing create_new_summary_version: {e}")
                import traceback
                traceback.print_exc()
                
        else:
            print("❌ No test bill found in database")
            
        print("\n=== ENHANCED AI ANALYZER TEST ===")
        
        # Test EnhancedAIAnalyzer
        try:
            analyzer = EnhancedAIAnalyzer()
            print(f"✅ Successfully created EnhancedAIAnalyzer")
            print(f"   - Client available: {analyzer.client is not None}")
            
            if test_bill:
                print("🔄 Testing analyze_bill method...")
                # Use a simple test to avoid rate limits
                test_text = "This is a test bill about transportation funding."
                result = analyzer.analyze_bill(test_text, title="Test Bill")
                
                if result:
                    print("✅ analyze_bill returned results")
                    print(f"   - Keys: {list(result.keys())}")
                else:
                    print("⚠️ analyze_bill returned empty results (likely due to API limits)")
                    
        except Exception as e:
            print(f"❌ Error testing EnhancedAIAnalyzer: {e}")
            import traceback
            traceback.print_exc()
            
        print("\n=== SUMMARY ===")
        print("If all tests pass, the issue is likely in the application code flow.")
        print("If any tests fail, there's a fundamental issue with the database or models.")

except Exception as e:
    print(f"❌ Critical error: {e}")
    import traceback
    traceback.print_exc()