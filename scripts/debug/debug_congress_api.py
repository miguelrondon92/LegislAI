#!/usr/bin/env python3
"""
Debug script to see what Congress API returns for bill text
"""

import os
import sys
import json

# Add the current directory to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from services.congress_api import CongressAPI

def debug_bill_text():
    """Debug what Congress API returns for bill text"""
    congress_api = CongressAPI()
    
    # Test with multiple bills to find one with text
    test_bills = [
        (119, 's', 2207),  # Original test
        (118, 'hr', 2670), # Infrastructure bill (more likely to have text)
        (118, 's', 2226),  # Another bill from previous congress
        (117, 'hr', 5376), # Inflation Reduction Act
    ]
    
    for congress, bill_type, bill_number in test_bills:
        print(f"\n{'='*60}")
        print(f"Testing bill: {congress}-{bill_type.upper()}{bill_number}")
        
        # Get the text endpoint response
        endpoint = f"/bill/{congress}/{bill_type}/{bill_number}/text"
        print(f"Endpoint: {endpoint}")
        
        # Make the request manually to see the response
        url = f"{congress_api.base_url}{endpoint}"
        
        response = congress_api.session.get(url, timeout=30)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Response keys: {list(data.keys())}")
            
            if 'textVersions' in data:
                versions = data['textVersions']
                print(f"Number of text versions: {len(versions)}")
                
                if len(versions) > 0:
                    print("✅ Found bill with text versions!")
                    
                    for i, version in enumerate(versions):
                        print(f"\nVersion {i+1}:")
                        print(f"  Type: {version.get('type')}")
                        print(f"  Date: {version.get('date')}")
                        print(f"  Formats: {len(version.get('formats', []))}")
                        
                        formats = version.get('formats', [])
                        for j, format_info in enumerate(formats):
                            print(f"    Format {j+1}:")
                            print(f"      Type: {format_info.get('type')}")
                            print(f"      URL: {format_info.get('url')}")
                            
                            # Try to fetch the actual text
                            if format_info.get('type') == 'Formatted Text':
                                text_url = format_info.get('url')
                                if text_url:
                                    print(f"      Fetching text from: {text_url}")
                                    try:
                                        text_response = congress_api.session.get(text_url, timeout=30)
                                        print(f"      Text response status: {text_response.status_code}")
                                        if text_response.status_code == 200:
                                            text_content = text_response.text
                                            print(f"      Text length: {len(text_content)}")
                                            print(f"      Text preview: {text_content[:500]}...")
                                            
                                            # Test the text extraction
                                            import re
                                            clean_text = re.sub(r'<[^>]*>', '', text_content)
                                            print(f"      Clean text length: {len(clean_text)}")
                                            print(f"      Clean text preview: {clean_text[:500]}...")
                                            
                                            return True  # Found a working bill
                                        else:
                                            print(f"      Text response error: {text_response.text[:200]}")
                                    except Exception as e:
                                        print(f"      Error fetching text: {e}")
                else:
                    print("❌ No text versions available for this bill")
            else:
                print("No textVersions in response")
        else:
            print(f"Error response: {response.text}")
    
    return False

if __name__ == "__main__":
    success = debug_bill_text()
    if success:
        print("\n✅ Found a bill with available text!")
    else:
        print("\n❌ No bills with available text found") 