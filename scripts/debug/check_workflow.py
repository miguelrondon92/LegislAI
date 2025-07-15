import sys
sys.path.insert(0, '.')

from app import app

print("Checking workflow routes...")
with app.app_context():
    for rule in app.url_map.iter_rules():
        if 'workflow' in rule.rule:
            print(f"Found: {rule.rule} -> {rule.endpoint}")

print("Testing workflow dashboard...")
with app.test_client() as client:
    response = client.get('/workflow')
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        html = response.get_data(as_text=True)
        if 'startWorkflow' in html:
            print("✅ startWorkflow found")
        else:
            print("❌ startWorkflow NOT found")
            print("HTML length:", len(html))
    else:
        print(f"Error: {response.get_data(as_text=True)}")