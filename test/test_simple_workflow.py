#!/usr/bin/env python3
"""Simple test to check workflow routes"""

import sys
sys.path.insert(0, '.')

try:
    from app import app
    from routes import *
    
    print("=== WORKFLOW ROUTES TEST ===")
    
    with app.test_client() as client:
        print("📄 Testing workflow dashboard page...")
        response = client.get('/workflow')
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            html = response.get_data(as_text=True)
            if 'startWorkflow' in html:
                print("✅ startWorkflow function found in HTML")
            else:
                print("❌ startWorkflow function NOT found in HTML")
                # Let's check what's in the HTML
                print("🔍 Checking for script content...")
                if 'function startWorkflow' in html:
                    print("✅ Function definition found")
                elif 'startWorkflow(' in html:
                    print("✅ Function call found")
                else:
                    print("❌ No startWorkflow references found")
                    print("First 1000 chars of response:")
                    print(html[:1000])
        else:
            print(f"❌ Failed to load page: {response.status_code}")
            print(f"Response: {response.get_data(as_text=True)[:500]}")
            
        print("\n📊 Testing workflow status endpoint...")
        response = client.get('/api/workflow/status')
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            print("✅ Status endpoint works")
            print(f"   Response: {response.get_json()}")
        else:
            print(f"❌ Status endpoint failed")
            print(f"   Response: {response.get_data(as_text=True)}")
            
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()