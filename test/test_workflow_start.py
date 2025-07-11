#!/usr/bin/env python3
"""Test the workflow start functionality"""

import sys
import requests
import time
import threading
import logging
sys.path.insert(0, '.')

from app import app

def run_test_server():
    """Run Flask app for testing"""
    app.run(host='127.0.0.1', port=5000, debug=False, use_reloader=False)

def test_workflow_start():
    """Test the workflow start button functionality"""
    print("🧪 TESTING WORKFLOW START FUNCTIONALITY")
    print("="*50)
    
    # Start server in background
    server_thread = threading.Thread(target=run_test_server, daemon=True)
    server_thread.start()
    
    # Wait for server to start
    print("⏳ Waiting for server to start...")
    time.sleep(3)
    
    base_url = "http://127.0.0.1:5000"
    
    try:
        # Test 1: Load workflow dashboard
        print("\n📄 Testing workflow dashboard page...")
        response = requests.get(f"{base_url}/workflow", timeout=10)
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            print("✅ Workflow dashboard loads successfully")
            html = response.text
            if 'startWorkflow' in html:
                print("✅ startWorkflow function found in page")
            else:
                print("❌ startWorkflow function NOT found")
        else:
            print(f"❌ Failed to load dashboard: {response.status_code}")
            return
        
        # Test 2: Check workflow status endpoint
        print("\n📊 Testing workflow status endpoint...")
        response = requests.get(f"{base_url}/api/workflow/status", timeout=10)
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print("✅ Status endpoint works")
            print(f"   Is running: {data.get('is_running', 'unknown')}")
            print(f"   Queue size: {data.get('queue_size', 'unknown')}")
            stats = data.get('statistics', {})
            print(f"   Bills discovered: {stats.get('bills_discovered', 0)}")
            print(f"   Bills processed: {stats.get('bills_processed', 0)}")
        else:
            print(f"❌ Status endpoint failed: {response.status_code}")
            print(f"   Response: {response.text}")
        
        # Test 3: Try starting the workflow (simulate clicking Start button)
        print("\n🚀 Testing workflow start (simulating Start button click)...")
        response = requests.post(f"{base_url}/api/workflow/start", 
                               headers={'Content-Type': 'application/json'},
                               timeout=30)
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print("✅ Workflow start endpoint works")
            print(f"   Response: {data}")
            
            # Check if workflow is now running
            print("\n🔍 Checking if workflow started...")
            time.sleep(2)
            response = requests.get(f"{base_url}/api/workflow/status", timeout=10)
            if response.status_code == 200:
                data = response.json()
                print(f"   Is running now: {data.get('is_running', 'unknown')}")
        else:
            print(f"❌ Workflow start failed: {response.status_code}")
            print(f"   Response: {response.text}")
            
            # Check for specific error patterns
            if "ModuleNotFoundError" in response.text:
                print("   🔍 Looks like a missing module error")
            elif "ImportError" in response.text:
                print("   🔍 Looks like an import error")
            elif "database" in response.text.lower():
                print("   🔍 Looks like a database error")
                
        # Test 4: Check recent items endpoint
        print("\n📋 Testing recent items endpoint...")
        response = requests.get(f"{base_url}/api/workflow/recent", timeout=10)
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print("✅ Recent items endpoint works")
            items = data.get('items', [])
            print(f"   Items count: {len(items)}")
            if items:
                print(f"   First item: {items[0]}")
        else:
            print(f"❌ Recent items failed: {response.status_code}")
            print(f"   Response: {response.text}")
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Request error: {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n✅ Testing complete!")

if __name__ == "__main__":
    test_workflow_start()