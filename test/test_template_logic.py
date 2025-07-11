#!/usr/bin/env python3
"""
Test the template logic for HR43 enacted status
"""
from app import app
from db_models import db, Bill, BillAction

with app.app_context():
    # Get HR43 bill and actions
    bill = Bill.query.filter_by(congress=119, bill_type='hr', bill_number=43).first()
    actions = BillAction.query.filter_by(bill_id=bill.id).all()
    
    print(f"Testing template logic for {bill.get_bill_identifier()}")
    print(f"Found {len(actions)} actions")
    
    # Simulate the template logic
    completed_stages = []
    
    for action in actions:
        action_type_lower = action.action_type.lower()
        action_text_lower = action.action_text.lower()
        
        print(f"\nAction: {action.action_type}")
        print(f"Text: {action.action_text[:80]}...")
        print(f"Type lower: {action_type_lower}")
        print(f"Text lower: {action_text_lower[:80]}...")
        
        if 'introduced' in action_type_lower or 'introrefer' in action_type_lower:
            if 'Introduced' not in completed_stages:
                completed_stages.append('Introduced')
                print("  -> Added: Introduced")
        elif 'committee' in action_type_lower or 'referred' in action_text_lower:
            if 'Committee' not in completed_stages:
                completed_stages.append('Committee')
                print("  -> Added: Committee")
        elif 'becamelaw' in action_type_lower or 'became public law' in action_text_lower or 'signed by president' in action_text_lower or 'enacted' in action_text_lower:
            if 'Enacted' not in completed_stages:
                completed_stages.append('Enacted')
                print("  -> Added: Enacted")
            if 'Passed' not in completed_stages:
                completed_stages.append('Passed')
                print("  -> Added: Passed")
            if 'Floor Vote' not in completed_stages:
                completed_stages.append('Floor Vote')
                print("  -> Added: Floor Vote")
        elif 'passed' in action_type_lower or 'passed' in action_text_lower:
            if 'Passed' not in completed_stages:
                completed_stages.append('Passed')
                print("  -> Added: Passed")
            if 'Floor Vote' not in completed_stages:
                completed_stages.append('Floor Vote')
                print("  -> Added: Floor Vote")
        elif 'floor' in action_type_lower or 'vote' in action_text_lower:
            if 'Floor Vote' not in completed_stages:
                completed_stages.append('Floor Vote')
                print("  -> Added: Floor Vote")
    
    print(f"\nFinal completed stages: {completed_stages}")
    
    # Check specific stages
    progress_stages = [
        ('Introduced', 'file-plus'),
        ('Committee', 'users'),
        ('Floor Vote', 'vote'),
        ('Passed', 'check-circle'),
        ('Enacted', 'award')
    ]
    
    print("\nStage status:")
    for stage, icon in progress_stages:
        status = "COMPLETED" if stage in completed_stages else "PENDING"
        print(f"  {stage}: {status}")