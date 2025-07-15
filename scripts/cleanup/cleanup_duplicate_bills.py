#!/usr/bin/env python3
"""
Cleanup Duplicate Bills

This script finds duplicate bills in the database and marks all but the latest as inactive.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from app import app, db
from db_models import Bill
from datetime import datetime

def cleanup_duplicate_bills():
    """Find and cleanup duplicate bills, keeping only the latest version active"""
    
    with app.app_context():
        print("🧹 CLEANING UP DUPLICATE BILLS")
        print("=" * 60)
        
        # Find all bills grouped by congress, type, and number
        all_bills = Bill.query.all()
        print(f"Total bills in database: {len(all_bills)}")
        
        # Group bills by unique identifier
        bill_groups = {}
        for bill in all_bills:
            key = f"{bill.congress}-{bill.bill_type}-{bill.bill_number}"
            if key not in bill_groups:
                bill_groups[key] = []
            bill_groups[key].append(bill)
        
        # Find duplicates
        duplicates_found = 0
        bills_deactivated = 0
        
        for bill_key, bills in bill_groups.items():
            if len(bills) > 1:
                duplicates_found += 1
                print(f"\n📋 Found {len(bills)} versions of {bill_key}:")
                
                # Sort by last_updated desc to get the latest first
                bills.sort(key=lambda b: b.last_updated, reverse=True)
                
                # Keep the latest active, deactivate the rest
                for i, bill in enumerate(bills):
                    if i == 0:
                        # Latest version - keep active
                        bill.active = True
                        print(f"  ✅ Keeping active: ID {bill.id} - {bill.last_updated}")
                    else:
                        # Older versions - deactivate
                        bill.active = False
                        bills_deactivated += 1
                        print(f"  ❌ Deactivating: ID {bill.id} - {bill.last_updated}")
        
        if duplicates_found > 0:
            # Commit changes
            db.session.commit()
            print(f"\n🎯 CLEANUP SUMMARY:")
            print(f"   Duplicate bill groups found: {duplicates_found}")
            print(f"   Bills deactivated: {bills_deactivated}")
            print(f"   Database updated successfully!")
        else:
            print("✅ No duplicate bills found - database is clean!")
        
        # Verify cleanup
        print(f"\n📊 VERIFICATION:")
        active_bills = Bill.query.filter_by(active=True).all()
        print(f"   Active bills: {len(active_bills)}")
        
        # Check for remaining duplicates
        active_groups = {}
        for bill in active_bills:
            key = f"{bill.congress}-{bill.bill_type}-{bill.bill_number}"
            if key not in active_groups:
                active_groups[key] = []
            active_groups[key].append(bill)
        
        remaining_duplicates = sum(1 for bills in active_groups.values() if len(bills) > 1)
        if remaining_duplicates == 0:
            print("   ✅ No duplicate active bills remaining!")
        else:
            print(f"   ❌ {remaining_duplicates} duplicate groups still exist")

if __name__ == "__main__":
    cleanup_duplicate_bills()