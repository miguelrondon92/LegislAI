#!/usr/bin/env python3
"""
Script to create policy categories in the database
"""

from app import app, db
from models import PolicyCategory
from utils.constants import FEDERAL_POLICY_CATEGORIES

def create_policy_categories():
    """Create policy categories from constants if they don't exist"""
    with app.app_context():
        # Check if categories already exist
        existing_categories = PolicyCategory.query.count()
        
        if existing_categories == 0:
            print("Creating policy categories...")
            
            for category_name in FEDERAL_POLICY_CATEGORIES:
                category = PolicyCategory(
                    name=category_name.lower().replace(' ', '_').replace('&', 'and'),
                    display_name=category_name,
                    description=f"Bills and legislation related to {category_name.lower()}",
                    color='#007bff',
                    is_active=True
                )
                db.session.add(category)
                print(f"Added category: {category_name}")
            
            db.session.commit()
            print(f"Successfully created {len(FEDERAL_POLICY_CATEGORIES)} policy categories")
        else:
            print(f"Policy categories already exist ({existing_categories} found)")

if __name__ == '__main__':
    create_policy_categories() 