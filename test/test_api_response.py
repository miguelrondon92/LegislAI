#!/usr/bin/env python3
"""Test what the workflow API endpoints actually return"""

import sys
sys.path.insert(0, '.')

from app import app
import json

def test_api_responses():
    """Test the actual API responses"""
    print("=== TESTING API RESPONSES ===")
    
    with app.test_client() as client:
        print("\n1. Testing /api/workflow/status")
        response = client.get('/api/workflow/status')
        print(f"   Status Code: {response.status_code}")
        
        if response.status_code == 200:
            try:
                data = response.get_json()
                print("   Response Structure:")
                print(f"   - Type: {type(data)}")
                if isinstance(data, dict):
                    for key in data.keys():
                        print(f"   - {key}: {type(data[key])}")
                    if 'statistics' in data:
                        stats = data['statistics']
                        print("   Statistics keys:")
                        for key in stats.keys():
                            print(f"     - {key}: {stats[key]}")
                print("\n   Full Response:")
                print(json.dumps(data, indent=2, default=str))
            except Exception as e:
                print(f"   JSON Error: {e}")
                print(f"   Raw Response: {response.get_data(as_text=True)}")
        else:
            print(f"   Error Response: {response.get_data(as_text=True)}")
        
        print("\n2. Testing /api/workflow/recent")
        response = client.get('/api/workflow/recent')
        print(f"   Status Code: {response.status_code}")
        
        if response.status_code == 200:
            try:
                data = response.get_json()
                print("   Response Structure:")
                print(f"   - Type: {type(data)}")
                if isinstance(data, dict):
                    for key in data.keys():
                        print(f"   - {key}: {type(data[key])}")
                        if key == 'items' and isinstance(data[key], list):
                            print(f"     - Items count: {len(data[key])}")
                print("\n   Full Response:")
                print(json.dumps(data, indent=2, default=str))
            except Exception as e:
                print(f"   JSON Error: {e}")
                print(f"   Raw Response: {response.get_data(as_text=True)}")
        else:
            print(f"   Error Response: {response.get_data(as_text=True)}")

if __name__ == "__main__":
    test_api_responses()