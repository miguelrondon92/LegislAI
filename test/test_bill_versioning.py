from app import app, db
from db_models import Bill
from services.bill_processor import BillProcessor
from datetime import datetime

# Test data for the same bill, with a change in summary for version 2
def get_bill_data(version=1):
    base = {
        'congress': 118,
        'type': 'hr',
        'number': 1234,
        'title': 'Test Bill for Versioning',
        'sponsors': [{
            'firstName': 'Jane',
            'lastName': 'Doe',
            'party': 'D',
            'state': 'NY'
        }],
        'introducedDate': datetime.utcnow().isoformat(),
        'actions': {'actions': [{'text': 'Introduced', 'actionDate': datetime.utcnow().date().isoformat()}]},
        'full_text': 'This is the full text of the bill.'
    }
    if version == 1:
        base['summary'] = 'This is the original summary.'
    else:
        base['summary'] = 'This is the updated summary with an amendment.'
    return base

def print_bill_versions():
    bills = Bill.query.filter_by(congress=118, bill_type='hr', bill_number=1234).order_by(Bill.version).all()
    print(f"Found {len(bills)} versions:")
    for b in bills:
        print(f"  Version {b.version}: active={b.active}, summary='{b.summary}'")

if __name__ == "__main__":
    with app.app_context():
        # Clean up any previous test data
        Bill.query.filter_by(congress=118, bill_type='hr', bill_number=1234).delete()
        db.session.commit()

        processor = BillProcessor()
        print("Ingesting version 1...")
        processor.process_bill_data(get_bill_data(version=1))
        print_bill_versions()

        print("\nIngesting version 2 (with changed summary)...")
        processor.process_bill_data(get_bill_data(version=2))
        print_bill_versions() 