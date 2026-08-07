#!/usr/bin/env python3
"""Test workflow orchestrator imports"""

import sys
sys.path.insert(0, '.')

print("Testing workflow orchestrator imports...")

try:
    print("1. Testing basic import...")
    from services.workflow_orchestrator import WorkflowOrchestrator
    print("✅ WorkflowOrchestrator imported successfully")
    
    print("2. Testing instantiation...")
    orchestrator = WorkflowOrchestrator()
    print("✅ WorkflowOrchestrator instantiated successfully")
    
    print("3. Testing get_workflow_status method...")
    status = orchestrator.get_workflow_status()
    print("✅ get_workflow_status() works")
    print(f"   Status: {status}")
    
    print("4. Testing start_workflow method...")
    try:
        result = orchestrator.start_workflow()
        print("✅ start_workflow() executed")
        print(f"   Result: {result}")
    except Exception as e:
        print(f"❌ start_workflow() failed: {e}")
        import traceback
        traceback.print_exc()
        
    print("5. Testing workflow queue...")
    print(f"   Queue length: {len(orchestrator.workflow_queue) if hasattr(orchestrator, 'workflow_queue') else 'No queue attr'}")
    
except ImportError as e:
    print(f"❌ Import error: {e}")
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()