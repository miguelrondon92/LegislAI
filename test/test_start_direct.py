#!/usr/bin/env python3
"""Test workflow start directly"""

import sys
sys.path.insert(0, '.')

print("Testing workflow start directly...")

try:
    # Test the exact code that runs when start button is clicked
    from services.workflow_orchestrator import WorkflowOrchestrator
    
    print("Creating WorkflowOrchestrator...")
    orchestrator = WorkflowOrchestrator()
    
    print("Calling start_workflow()...")
    orchestrator.start_workflow()
    
    print("✅ start_workflow() completed successfully")
    
    # Check status
    print("Checking status...")
    status = orchestrator.get_workflow_status()
    print(f"Is running: {status.get('is_running')}")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()