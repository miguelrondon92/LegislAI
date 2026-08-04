#!/usr/bin/env python3
"""Simple database test to check if models are working"""

import sqlite3
import os

def test_database_tables():
    """Test if the database tables exist"""
    db_path = './instance/legislative_analysis.db'
    
    if not os.path.exists(db_path):
        print(f"❌ Database file not found at {db_path}")
        return False
        
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Get all tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]
        
        print(f"✅ Found {len(tables)} tables in database:")
        for table in tables:
            print(f"   - {table}")
            
        # Check if our new tables exist
        if 'ai_analysis' in tables:
            print("✅ ai_analysis table exists")
            
            # Check record count
            cursor.execute("SELECT COUNT(*) FROM ai_analysis")
            count = cursor.fetchone()[0]
            print(f"   - Records: {count}")
            
            # Check structure
            cursor.execute("PRAGMA table_info(ai_analysis)")
            columns = cursor.fetchall()
            print(f"   - Columns: {[col[1] for col in columns]}")
            
        else:
            print("❌ ai_analysis table missing")
            
        if 'summary' in tables:
            print("✅ summary table exists")
            
            # Check record count
            cursor.execute("SELECT COUNT(*) FROM summary")
            count = cursor.fetchone()[0]
            print(f"   - Records: {count}")
            
            # Check structure
            cursor.execute("PRAGMA table_info(summary)")
            columns = cursor.fetchall()
            print(f"   - Columns: {[col[1] for col in columns]}")
            
        else:
            print("❌ summary table missing")
            
        if 'bill' in tables:
            print("✅ bill table exists")
            
            # Check record count
            cursor.execute("SELECT COUNT(*) FROM bill")
            count = cursor.fetchone()[0]
            print(f"   - Records: {count}")
            
            # Check a few recent bills
            cursor.execute("SELECT id, congress, bill_type, bill_number, title FROM bill ORDER BY id DESC LIMIT 3")
            recent_bills = cursor.fetchall()
            print("   - Recent bills:")
            for bill in recent_bills:
                print(f"     {bill[0]}: {bill[1]}-{bill[2]}{bill[3]} - {bill[4][:50]}...")
                
        else:
            print("❌ bill table missing")
            
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Database error: {e}")
        return False

if __name__ == "__main__":
    print("=== SIMPLE DATABASE TEST ===")
    test_database_tables()