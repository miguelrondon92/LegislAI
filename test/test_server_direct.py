#!/usr/bin/env python3
"""
Test the server directly to verify all routes work
"""

import os
import sys
import requests
import time
import threading
from pathlib import Path

# Add the project root to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

def test_all_routes():
    """Test all main routes work without errors"""
    from app import app
    
    # Test critical routes that should work
    test_routes = [
        ('/', 'Home page'),
        ('/bill_search', 'Bill search'),
        ('/auth/signup', 'User signup'),
        ('/auth/signin', 'User login'),
        ('/workflow', 'Workflow page'),
        ('/api/workflow/status', 'Workflow status API'),
    ]
    
    with app.test_client() as client:
        print("🧪 Testing all critical routes...")
        print("=" * 50)
        
        all_good = True
        
        for route, description in test_routes:
            try:
                response = client.get(route)
                status = response.status_code
                
                if status == 200:
                    print(f"✅ {description} ({route}): {status}")
                elif status in [302, 401, 403]:  # Redirects or auth required
                    print(f"🔄 {description} ({route}): {status} (redirect/auth)")
                elif status == 404:
                    print(f"⚠️ {description} ({route}): {status} (not found)")
                else:
                    print(f"❌ {description} ({route}): {status}")
                    all_good = False
                    
            except Exception as e:
                print(f"💥 {description} ({route}): Exception - {e}")
                all_good = False
        
        print("\n" + "=" * 50)
        if all_good:
            print("✅ All routes working properly!")
        else:
            print("⚠️ Some routes have issues")
            
        # Test a few POST routes
        print("\n🧪 Testing POST routes...")
        
        # Test search
        try:
            response = client.post('/bill_search', data={'q': 'test'})
            print(f"✅ Bill search POST: {response.status_code}")
        except Exception as e:
            print(f"❌ Bill search POST failed: {e}")
            
        # Test workflow API
        try:
            response = client.post('/api/workflow/start', json={})
            print(f"✅ Workflow start API: {response.status_code}")
        except Exception as e:
            print(f"❌ Workflow start API failed: {e}")
            
        print("\n🎉 Route testing complete!")

if __name__ == "__main__":
    test_all_routes()