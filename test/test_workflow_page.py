#!/usr/bin/env python3
"""Test the workflow page functionality"""

import sys
import os
sys.path.insert(0, '.')

from app import app
import requests
import time
import threading

def test_flask_routes():
    """Test that Flask routes exist"""
    print("=== FLASK ROUTES TEST ===")
    with app.app_context():
        workflow_routes = []
        for rule in app.url_map.iter_rules():
            if 'workflow' in rule.rule:
                workflow_routes.append(f'{rule.rule} -> {rule.endpoint}')
        
        if workflow_routes:
            print("✅ Found workflow routes:")
            for route in workflow_routes:
                print(f"   {route}")
        else:
            print("❌ No workflow routes found")
        
        return len(workflow_routes) > 0

def start_test_server():
    """Start the Flask test server"""
    print("🚀 Starting Flask test server on port 5001...")
    app.run(host='127.0.0.1', port=5001, debug=False)

def test_workflow_endpoints():
    """Test workflow API endpoints"""
    print("\n=== WORKFLOW ENDPOINTS TEST ===")
    base_url = "http://127.0.0.1:5001"
    
    # Wait for server to start
    time.sleep(2)
    
    try:
        # Test workflow dashboard page
        print("📄 Testing workflow dashboard page...")
        response = requests.get(f"{base_url}/workflow", timeout=10)
        if response.status_code == 200:
            print("✅ Workflow dashboard page loads successfully")
            if 'startWorkflow' in response.text:
                print("✅ startWorkflow function found in page")
            else:
                print("❌ startWorkflow function NOT found in page")
        else:
            print(f"❌ Workflow dashboard failed: {response.status_code}")
        
        # Test workflow status endpoint
        print("\n📊 Testing workflow status endpoint...")
        response = requests.get(f"{base_url}/api/workflow/status", timeout=10)
        if response.status_code == 200:
            print("✅ Workflow status endpoint works")
            data = response.json()
            print(f"   Response: {data}")
        else:
            print(f"❌ Workflow status failed: {response.status_code}")
        
        # Test workflow start endpoint
        print("\n🎯 Testing workflow start endpoint...")
        response = requests.post(f"{base_url}/api/workflow/start", timeout=10)
        if response.status_code == 200:
            print("✅ Workflow start endpoint works")
            data = response.json()
            print(f"   Response: {data}")
        else:
            print(f"❌ Workflow start failed: {response.status_code}")
            print(f"   Response: {response.text}")
        
    except Exception as e:
        print(f"❌ Error testing endpoints: {e}")

def main():
    """Main test function"""
    print("🧪 WORKFLOW PAGE TESTING")
    print("=" * 50)
    
    # Test that routes exist
    routes_exist = test_flask_routes()
    
    if not routes_exist:
        print("❌ No workflow routes found, testing cannot continue")
        return
    
    # Start server in background thread
    server_thread = threading.Thread(target=start_test_server, daemon=True)
    server_thread.start()
    
    # Test endpoints
    test_workflow_endpoints()
    
    print("\n✅ Testing complete!")

if __name__ == "__main__":
    main()