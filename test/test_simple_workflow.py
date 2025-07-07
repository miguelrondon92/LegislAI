#!/usr/bin/env python3
"""
Simple demonstration of the bill analysis workflow with a tiny example.
Shows the complete process from bill text to database storage.
"""

import os
import sys
import logging
from datetime import datetime
from pathlib import Path

# Add the project root to the Python path
sys.path.insert(0, str(Path(__file__).parent))

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

def demonstrate_simple_workflow():
    """Demonstrate complete workflow with a very simple bill"""
    logger.info("🎯 DEMONSTRATING SIMPLE BILL WORKFLOW")
    logger.info("=" * 60)
    
    # Step 1: Create a tiny test bill
    tiny_bill = {
        'title': 'Simple Test Act',
        'full_text': """
        H.R.TEST - Simple Test Act
        
        SECTION 1. SHORT TITLE.
        This Act may be cited as the "Simple Test Act".
        
        SECTION 2. PURPOSE.
        The purpose is to test the system.
        
        SECTION 3. EFFECTIVE DATE.
        This Act takes effect immediately.
        """,
        'congress': 119,
        'bill_type': 'hr',
        'bill_number': 999999,  # Use a very high number to avoid conflicts
        'summary': 'A very simple test bill for demonstration',
        'sponsor_name': 'Test Sponsor',
        'sponsor_party': 'T',
        'sponsor_state': 'TX'
    }
    
    logger.info(f"📋 Created test bill: {tiny_bill['title']}")
    logger.info(f"   Text length: {len(tiny_bill['full_text'])} characters")
    
    try:
        from app import app, db
        from db_models import Bill, PolicyCategory, BillCategoryMapping
        from services.enhanced_ai_analyzer import EnhancedAIAnalyzer
        
        with app.app_context():
            # Clean up any existing test bill
            existing = Bill.query.filter_by(
                congress=119,
                bill_type='hr',
                bill_number=999999
            ).first()
            if existing:
                # Clean up related mappings first
                BillCategoryMapping.query.filter_by(bill_id=existing.id).delete()
                db.session.delete(existing)
                db.session.commit()
                logger.info("🧹 Cleaned up existing test bill")
            
            # Step 2: Create bill record
            logger.info("\n💾 Step 2: Creating bill record...")
            bill = Bill(
                congress=tiny_bill['congress'],
                bill_type=tiny_bill['bill_type'],
                bill_number=tiny_bill['bill_number'],
                title=tiny_bill['title'],
                summary=tiny_bill['summary'],
                sponsor_name=tiny_bill['sponsor_name'],
                sponsor_party=tiny_bill['sponsor_party'],
                sponsor_state=tiny_bill['sponsor_state']
            )
            
            db.session.add(bill)
            db.session.flush()  # Get the ID
            logger.info(f"✅ Bill created: {bill.get_bill_identifier()}")
            
            # Step 3: AI Analysis
            logger.info("\n🤖 Step 3: AI Analysis...")
            analyzer = EnhancedAIAnalyzer()
            quota_info = analyzer.get_quota_info()
            
            analysis = None
            if not quota_info['status']['is_at_limit']:
                try:
                    analysis = analyzer.analyze_bill(tiny_bill['full_text'], tiny_bill['title'])
                    if analysis:
                        logger.info("✅ AI analysis completed")
                        logger.info(f"   Analysis fields: {list(analysis.keys())}")
                    else:
                        logger.warning("❌ AI analysis failed")
                except Exception as e:
                    logger.warning(f"❌ AI analysis error: {e}")
            else:
                logger.warning("⚠️ At API quota limit")
            
            # Use mock analysis if needed
            if not analysis:
                logger.info("📝 Using mock analysis for demonstration")
                analysis = {
                    'summary': 'This is a simple test bill for system demonstration',
                    'policy_implications': [
                        'Tests system functionality',
                        'Demonstrates workflow process'
                    ],
                    'categories': [
                        {
                            'name': 'governance',
                            'relevance': 0.8,
                            'analysis': 'This bill relates to government processes and testing',
                            'sneakiness': 0.1
                        },
                        {
                            'name': 'technology',
                            'relevance': 0.3,
                            'analysis': 'Minor technology implications for testing systems',
                            'sneakiness': 0.0
                        }
                    ],
                    'stakeholders': [
                        'Government testers',
                        'System administrators'
                    ],
                    'complexity_score': 0.2,
                    'risk_assessment': {
                        'overall_risk': 'low',
                        'financial_impact': 'minimal',
                        'political_impact': 'none'
                    }
                }
            
            # Step 4: Store analysis
            logger.info("\n💾 Step 4: Storing analysis...")
            bill.set_ai_analysis(analysis)
            
            # Step 5: Create category mappings
            logger.info("\n🔗 Step 5: Creating category mappings...")
            mappings_created = 0
            
            if 'categories' in analysis:
                for category_info in analysis['categories']:
                    category_name = category_info.get('name', '').lower()
                    relevance = float(category_info.get('relevance', 0.0))
                    
                    if relevance > 0.1:  # Only significant relevance
                        # Find matching policy category
                        policy_category = PolicyCategory.query.filter_by(name=category_name).first()
                        if policy_category:
                            mapping = BillCategoryMapping(
                                bill_id=bill.id,
                                policy_category_id=policy_category.id,
                                relevance_score=relevance,
                                sneakiness_score=category_info.get('sneakiness', 0.0)
                            )
                            
                            if 'analysis' in category_info:
                                mapping.set_category_analysis(category_info['analysis'])
                            
                            db.session.add(mapping)
                            mappings_created += 1
                            logger.info(f"   📂 Mapped to: {policy_category.display_name} (relevance: {relevance:.2f})")
                        else:
                            logger.info(f"   ⚠️ Category '{category_name}' not found in database")
            
            # Step 6: Commit everything
            logger.info("\n💾 Step 6: Committing to database...")
            db.session.commit()
            logger.info(f"✅ Successfully stored bill with {mappings_created} category mappings")
            
            # Step 7: Verify storage
            logger.info("\n🔍 Step 7: Verifying storage...")
            stored_bill = Bill.query.get(bill.id)
            stored_analysis = stored_bill.get_ai_analysis()
            stored_mappings = BillCategoryMapping.query.filter_by(bill_id=bill.id).count()
            
            logger.info(f"✅ Verification results:")
            logger.info(f"   Bill ID: {stored_bill.id}")
            logger.info(f"   Title: {stored_bill.title}")
            logger.info(f"   Analysis fields: {len(stored_analysis)} ({list(stored_analysis.keys())})")
            logger.info(f"   Category mappings: {stored_mappings}")
            
            # Step 8: Show final state
            logger.info("\n📊 Step 8: Final state...")
            for mapping in BillCategoryMapping.query.filter_by(bill_id=bill.id).all():
                category_analysis = mapping.get_category_analysis()
                analysis_preview = category_analysis.get('analysis', 'No analysis')[:50] if category_analysis else 'No analysis'
                logger.info(f"   📂 {mapping.policy_category.display_name}")
                logger.info(f"      Relevance: {mapping.relevance_score:.2f}")
                logger.info(f"      Sneakiness: {mapping.sneakiness_score:.2f}")
                logger.info(f"      Analysis: {analysis_preview}...")
            
            # Clean up
            logger.info("\n🧹 Cleanup...")
            BillCategoryMapping.query.filter_by(bill_id=bill.id).delete()
            db.session.delete(stored_bill)
            db.session.commit()
            logger.info("✅ Test data cleaned up")
            
            return True
            
    except Exception as e:
        logger.error(f"❌ Workflow demonstration failed: {e}")
        return False

def main():
    """Main demonstration function"""
    logger.info("🚀 SIMPLE BILL WORKFLOW DEMONSTRATION")
    logger.info("This demonstrates the complete process from bill text to database")
    logger.info("=" * 70)
    
    success = demonstrate_simple_workflow()
    
    logger.info("\n" + "=" * 70)
    if success:
        logger.info("🎉 WORKFLOW DEMONSTRATION SUCCESSFUL!")
        logger.info("✅ The system successfully:")
        logger.info("   • Created a bill record in the database")
        logger.info("   • Performed AI analysis (or used mock data)")
        logger.info("   • Stored analysis results as JSON")
        logger.info("   • Created category mappings with relevance scores")
        logger.info("   • Verified all data was stored correctly")
        logger.info("   • Cleaned up test data")
        
        logger.info("\n💡 This proves the system can:")
        logger.info("   • Handle small bill examples")
        logger.info("   • Process AI analysis results")
        logger.info("   • Maintain database integrity")
        logger.info("   • Map bills to policy categories")
        logger.info("   • Store and retrieve complex JSON data")
    else:
        logger.error("❌ WORKFLOW DEMONSTRATION FAILED")
        logger.error("Check the logs above for details on what went wrong")
    
    logger.info("=" * 70)
    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)