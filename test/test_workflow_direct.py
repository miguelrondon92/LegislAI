#!/usr/bin/env python3
"""Direct test of workflow functionality"""

import sys
import os
sys.path.insert(0, '.')

def test_workflow_directly():
    """Test workflow functionality step by step"""
    print("=== DIRECT WORKFLOW TEST ===")
    
    try:
        # Test 1: Import the app
        print("1. Testing app import...")
        from app import app
        print("✅ App imported successfully")
        
        # Test 2: Test with Flask test client
        print("\n2. Testing with Flask test client...")
        with app.test_client() as client:
            
            # Test the workflow page itself
            print("   Testing workflow page...")
            response = client.get('/workflow')
            print(f"   Status: {response.status_code}")
            if response.status_code == 200:
                print("   ✅ Workflow page loads")
                html = response.get_data(as_text=True)
                if 'startWorkflow' in html:
                    print("   ✅ JavaScript functions found")
                else:
                    print("   ❌ JavaScript functions NOT found")
            else:
                print(f"   ❌ Workflow page failed: {response.get_data(as_text=True)[:200]}")
            
            # Test the status API
            print("\n   Testing status API...")
            response = client.get('/api/workflow/status')
            print(f"   Status: {response.status_code}")
            if response.status_code == 200:
                print("   ✅ Status API works")
                try:
                    data = response.get_json()
                    print(f"   Response keys: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}")
                    print(f"   Full response: {data}")
                except Exception as e:
                    print(f"   ❌ JSON parse error: {e}")
                    print(f"   Raw: {response.get_data(as_text=True)}")
            else:
                print(f"   ❌ Status API failed: {response.get_data(as_text=True)}")
            
            # Test the recent items API
            print("\n   Testing recent items API...")
            response = client.get('/api/workflow/recent')
            print(f"   Status: {response.status_code}")
            if response.status_code == 200:
                print("   ✅ Recent items API works")
                try:
                    data = response.get_json()
                    print(f"   Response keys: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}")
                    print(f"   Items count: {len(data.get('items', []))}")
                except Exception as e:
                    print(f"   ❌ JSON parse error: {e}")
                    print(f"   Raw: {response.get_data(as_text=True)}")
            else:
                print(f"   ❌ Recent items API failed: {response.get_data(as_text=True)}")
    
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

def test_workflow_orchestrator_directly():
    """Test WorkflowOrchestrator class directly"""
    print("\n=== WORKFLOW ORCHESTRATOR TEST ===")
    
    try:
        print("1. Importing WorkflowOrchestrator...")
        from services.workflow_orchestrator import WorkflowOrchestrator
        print("✅ Import successful")
        
        print("2. Creating instance...")
        orchestrator = WorkflowOrchestrator()
        print("✅ Instance created")
        
        print("3. Testing get_workflow_status...")
        status = orchestrator.get_workflow_status()
        print("✅ get_workflow_status works")
        print(f"   Type: {type(status)}")
        print(f"   Keys: {list(status.keys()) if isinstance(status, dict) else 'Not a dict'}")
        print(f"   is_running: {status.get('is_running', 'NOT FOUND')}")
        print(f"   queue_size: {status.get('queue_size', 'NOT FOUND')}")
        print(f"   statistics: {type(status.get('statistics', 'NOT FOUND'))}")
        
        print("\n4. Testing get_recent_workflow_items...")
        items = orchestrator.get_recent_workflow_items()
        print("✅ get_recent_workflow_items works")
        print(f"   Type: {type(items)}")
        print(f"   Count: {len(items) if isinstance(items, list) else 'Not a list'}")
        
    except Exception as e:
        print(f"❌ WorkflowOrchestrator error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_workflow_directly()
    test_workflow_orchestrator_directly()