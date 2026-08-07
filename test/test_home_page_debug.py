#!/usr/bin/env python3
"""
Debug the home page 500 error
"""

import os
import sys
from pathlib import Path

# Add the project root to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

def test_home_page():
    try:
        from app import app
        print("✅ App imported successfully")
        
        # Test that Bill model is accessible
        from db_models import Bill
        print("✅ Bill model imported successfully")
        
        with app.app_context():
            print(f"✅ App context created")
            
            # Test database query
            try:
                recent_bills = Bill.query.order_by(Bill.last_updated.desc()).limit(10).all()
                print(f"✅ Database query successful: {len(recent_bills)} bills found")
            except Exception as e:
                print(f"❌ Database query failed: {e}")
            
            # Test the route directly
            with app.test_client() as client:
                print("Testing home page route...")
                response = client.get('/')
                print(f"Status: {response.status_code}")
                
                if response.status_code == 200:
                    print("✅ Home page works!")
                    content = response.get_data(as_text=True)
                    print(f"Content length: {len(content)} characters")
                else:
                    print(f"❌ Home page error: {response.status_code}")
                    if response.status_code == 500:
                        # Try to get error details
                        content = response.get_data(as_text=True)
                        print(f"Error content: {content[:500]}...")
                        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_home_page()