import sys
sys.path.insert(0, '.')

print("Testing workflow API...")

try:
    from app import app
    with app.test_client() as client:
        print("Testing /api/workflow/status")
        r = client.get('/api/workflow/status')
        print(f"Status: {r.status_code}")
        if r.status_code == 200:
            print(f"Data: {r.get_json()}")
        else:
            print(f"Error: {r.get_data(as_text=True)}")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()