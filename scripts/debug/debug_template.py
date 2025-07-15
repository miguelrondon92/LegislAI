#!/usr/bin/env python3
"""
Debug template rendering for HR43
"""
from flask import render_template_string
from app import app
from db_models import db, Bill, BillAction

# Test template
test_template = '''
{% set completed_stages = [] %}
{% for action in bill_actions %}
    {% set action_type_lower = action.action_type.lower() %}
    {% set action_text_lower = action.action_text.lower() %}
    
    Action: {{ action.action_type }} - {{ action.action_text[:50] }}...<br>
    Type lower: {{ action_type_lower }}<br>
    Text lower: {{ action_text_lower[:50] }}...<br>
    
    {% if 'becamelaw' in action_type_lower or 'became public law' in action_text_lower or 'signed by president' in action_text_lower or 'enacted' in action_text_lower %}
        {% set _ = completed_stages.append('Enacted') %}
        {% set _ = completed_stages.append('Passed') %}
        {% set _ = completed_stages.append('Floor Vote') %}
        -> ENACTED DETECTED!<br>
    {% elif 'passed' in action_type_lower or 'passed' in action_text_lower %}
        {% set _ = completed_stages.append('Passed') %}
        {% set _ = completed_stages.append('Floor Vote') %}
        -> PASSED DETECTED!<br>
    {% elif 'floor' in action_type_lower or 'vote' in action_text_lower %}
        {% set _ = completed_stages.append('Floor Vote') %}
        -> FLOOR VOTE DETECTED!<br>
    {% elif 'committee' in action_type_lower or 'referred' in action_text_lower %}
        {% set _ = completed_stages.append('Committee') %}
        -> COMMITTEE DETECTED!<br>
    {% elif 'introduced' in action_type_lower or 'introrefer' in action_type_lower %}
        {% set _ = completed_stages.append('Introduced') %}
        -> INTRODUCED DETECTED!<br>
    {% endif %}
    <br>
{% endfor %}

<h3>Completed Stages:</h3>
{% for stage in completed_stages %}
    {{ stage }}<br>
{% endfor %}

<h3>Stage Status:</h3>
{% set progress_stages = [
    ('Introduced', 'file-plus'),
    ('Committee', 'users'),
    ('Floor Vote', 'vote'),
    ('Passed', 'check-circle'),
    ('Enacted', 'award')
] %}

{% for stage, icon in progress_stages %}
    {{ stage }}: {{ 'COMPLETED' if stage in completed_stages else 'PENDING' }}<br>
{% endfor %}
'''

with app.app_context():
    # Get HR43 bill and actions
    bill = Bill.query.filter_by(congress=119, bill_type='hr', bill_number=43).first()
    actions = BillAction.query.filter_by(bill_id=bill.id).all()
    
    print("Rendering template...")
    result = render_template_string(test_template, bill_actions=actions)
    print(result)