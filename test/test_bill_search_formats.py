#!/usr/bin/env python3
"""
Test Bill Search Format Handling

Test that the bill search page properly handles different bill number formats
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from app import app

def test_bill_search_formats():
    """Test various bill number formats"""
    with app.test_client() as client:
        # Test formats that should work
        test_formats = [
            'HR 1',
            'HR-1', 
            'H.R.1',
            'H R 1',
            'hr 1',
            'HR1',
            'S 567',
            'S-567',
            'S.567'
        ]
        
        print("🔍 TESTING BILL NUMBER FORMATS")
        print("=" * 50)
        
        for format_test in test_formats:
            try:
                response = client.post('/bill_search', data={
                    'search_query': format_test,
                    'search_type': 'bill_number',
                    'congress': '119'
                })
                
                if response.status_code == 200:
                    content = response.get_data(as_text=True)
                    if 'error' in content.lower() and 'not found' in content.lower():
                        print(f"⚠️  {format_test:12} - Processed but bill not found (expected)")
                    elif 'Search Results' in content or 'bill' in content.lower():
                        print(f"✅ {format_test:12} - Successfully processed and found results")
                    else:
                        print(f"⚠️  {format_test:12} - Processed but unclear results")
                else:
                    print(f"❌ {format_test:12} - HTTP {response.status_code}")
                    
            except Exception as e:
                print(f"❌ {format_test:12} - Error: {e}")
        
        print("\n📋 TESTING EMPTY/INVALID INPUTS")
        print("=" * 50)
        
        invalid_tests = ['', '   ', 'invalid123', '###']
        
        for invalid_test in invalid_tests:
            try:
                response = client.post('/bill_search', data={
                    'search_query': invalid_test,
                    'search_type': 'bill_number', 
                    'congress': '119'
                })
                
                if response.status_code == 200:
                    content = response.get_data(as_text=True)
                    if 'not found' in content.lower() or 'error' in content.lower():
                        print(f"✅ '{invalid_test:10}' - Properly handled as invalid")
                    else:
                        print(f"⚠️  '{invalid_test:10}' - Processed but unclear handling")
                else:
                    print(f"❌ '{invalid_test:10}' - HTTP {response.status_code}")
                    
            except Exception as e:
                print(f"❌ '{invalid_test:10}' - Error: {e}")

if __name__ == "__main__":
    test_bill_search_formats()