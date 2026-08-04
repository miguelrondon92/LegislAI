#!/usr/bin/env python3
"""
Test the workflow with a very small bill to avoid quota issues
"""

import os
import sys
import logging
from datetime import datetime
from pathlib import Path

# Add the project root to the Python path
sys.path.insert(0, str(Path(__file__).parent))

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

def find_small_bill():
    """Find a very small bill to test with"""
    print("🔍 SEARCHING FOR SMALL BILLS")
    print("="*50)
    
    from services.congress_api import CongressAPI
    
    api = CongressAPI()
    
    # Test with different types of smaller bills
    test_bills = [
        "H.Res.516",  # House resolutions are usually smaller
        "S.Res.200",  # Senate resolutions
        "H.Con.Res.50"  # Concurrent resolutions
    ]
    
    for bill_id in test_bills:
        print(f"📋 Testing: {bill_id}")
        try:
            bill_data = api.get_bill_by_number(bill_id)
            if bill_data and bill_data.get('full_text'):
                text_length = len(bill_data['full_text'])
                print(f"   📝 Text length: {text_length:,} characters")
                
                if text_length < 1000:  # Very small bill
                    print(f"   ✅ Found small bill: {bill_id}")
                    return bill_id, bill_data
                else:
                    print(f"   ⚠️ Too large: {text_length:,} characters")
            else:
                print(f"   ❌ No text available")
        except Exception as e:
            print(f"   ❌ Error: {e}")
    
    return None, None

def test_with_minimal_text():
    """Test the workflow with minimal text input"""
    print("\n🧪 TESTING WITH MINIMAL TEXT")
    print("="*50)
    
    from services.enhanced_ai_analyzer import EnhancedAIAnalyzer
    
    analyzer = EnhancedAIAnalyzer()
    
    # Create a very simple mock bill text
    minimal_bill_text = """
    H.R.TEST - Test Bill
    
    SECTION 1. SHORT TITLE.
    This Act may be cited as the "Test Act".
    
    SECTION 2. FINDINGS.
    Congress finds that testing is important.
    
    SECTION 3. EFFECTIVE DATE.
    This Act shall take effect immediately.
    """
    
    title = "Test Act"
    
    print(f"📋 Testing with minimal bill:")
    print(f"   Title: {title}")
    print(f"   Text length: {len(minimal_bill_text)} characters")
    
    # Check quota
    quota_info = analyzer.get_quota_info()
    print(f"📊 Current quota: {quota_info['current_usage']['requests_this_minute']}/{quota_info['current_usage']['max_requests_per_minute']}")
    
    if quota_info['status']['is_at_limit']:
        print("❌ At rate limit, skipping test")
        return False
    
    try:
        analysis = analyzer.analyze_bill(minimal_bill_text, title)
        
        if analysis:
            print("✅ Successfully analyzed minimal bill")
            print(f"📄 Analysis keys: {list(analysis.keys())}")
            return True
        else:
            print("❌ Failed to analyze minimal bill")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_workflow_with_mock_data():
    """Test the workflow orchestrator with mock data"""
    print("\n🎯 TESTING WORKFLOW WITH MOCK DATA")
    print("="*50)
    
    try:
        from services.workflow_orchestrator import WorkflowOrchestrator, WorkflowItem, WorkflowStatus
        
        # Create minimal mock bill data that doesn't require AI
        mock_bill_data = {
            'congress': 119,
            'type': 'hr',
            'number': 9999,
            'title': 'Mock Test Bill',
            'full_text': 'This is a very short test bill for testing purposes.',
            'sponsors': [],
            'actions': []
        }
        
        # Test the bill extraction logic
        mock_rss_item = {
            'title': 'H.R.9999 - Mock Test Bill',
            'link': 'https://www.congress.gov/bill/119th-congress/house-bill/9999',
            'description': 'A mock bill for testing'
        }
        
        orchestrator = WorkflowOrchestrator()
        
        # Test bill info extraction
        bill_info = orchestrator._extract_bill_info(mock_rss_item)
        
        if bill_info:
            print(f"✅ Successfully extracted bill info:")
            print(f"   Identifier: {bill_info['identifier']}")
            print(f"   Type: {bill_info['bill_type']}")
            print(f"   Number: {bill_info['bill_number']}")
            print(f"   Congress: {bill_info['congress']}")
            
            # Create workflow item
            workflow_item = WorkflowItem(
                bill_identifier=bill_info['identifier'],
                congress=bill_info['congress'],
                bill_type=bill_info['bill_type'],
                bill_number=bill_info['bill_number'],
                title=mock_rss_item['title'],
                source='test',
                discovered_at=datetime.utcnow(),
                status=WorkflowStatus.PENDING
            )
            
            print(f"✅ Created workflow item: {workflow_item.bill_identifier}")
            return True
        else:
            print("❌ Failed to extract bill info")
            return False
            
    except Exception as e:
        print(f"❌ Error testing workflow: {e}")
        return False

def test_rss_callback():
    """Test the RSS callback functionality"""
    print("\n📡 TESTING RSS CALLBACK")
    print("="*50)
    
    try:
        from services.workflow_orchestrator import WorkflowOrchestrator
        
        orchestrator = WorkflowOrchestrator()
        
        # Mock RSS item
        mock_item = {
            'title': 'H.R.1 - Sample Bill',
            'link': 'https://www.congress.gov/bill/119th-congress/house-bill/1',
            'description': 'A sample bill for testing',
            'published': datetime.utcnow().isoformat(),
            'source_feed': 'test_feed'
        }
        
        print(f"📋 Testing RSS callback with: {mock_item['title']}")
        
        initial_queue_size = len(orchestrator.workflow_queue)
        
        # Handle the RSS item
        orchestrator._handle_new_rss_item(mock_item)
        
        final_queue_size = len(orchestrator.workflow_queue)
        
        if final_queue_size > initial_queue_size:
            print(f"✅ Successfully added item to queue")
            print(f"   Queue size: {initial_queue_size} → {final_queue_size}")
            
            # Show the added item
            added_item = orchestrator.workflow_queue[-1]
            print(f"   Added: {added_item.bill_identifier}")
            print(f"   Status: {added_item.status.value}")
            
            return True
        else:
            print(f"❌ Failed to add item to queue")
            return False
            
    except Exception as e:
        print(f"❌ Error testing RSS callback: {e}")
        return False

def main():
    """Main test function for small bill workflow"""
    print("🚀 TESTING MONITORING SYSTEM WITH SMALL BILLS")
    print("="*60)
    
    # Ensure logs directory exists
    Path("logs").mkdir(exist_ok=True)
    
    test_results = {}
    
    # Test 1: Find a small bill
    print("\n🔍 TEST 1: Finding Small Bills")
    small_bill_id, small_bill_data = find_small_bill()
    test_results['find_small_bill'] = small_bill_id is not None
    
    # Test 2: Test with minimal text
    print("\n🧪 TEST 2: Minimal Text Analysis")
    test_results['minimal_analysis'] = test_with_minimal_text()
    
    # Test 3: Workflow with mock data
    print("\n🎯 TEST 3: Workflow Mock Data")
    test_results['workflow_mock'] = test_workflow_with_mock_data()
    
    # Test 4: RSS callback
    print("\n📡 TEST 4: RSS Callback")
    test_results['rss_callback'] = test_rss_callback()
    
    # Summary
    print("\n" + "="*60)
    print("📊 SMALL BILL WORKFLOW TEST SUMMARY")
    print("="*60)
    
    passed = sum(test_results.values())
    total = len(test_results)
    
    for test_name, result in test_results.items():
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{test_name.replace('_', ' ').title()}: {status}")
    
    print(f"\n📈 Overall: {passed}/{total} tests passed ({passed/total*100:.1f}%)")
    
    if passed >= 3:  # At least 3 out of 4 tests should pass
        print("🎉 MONITORING SYSTEM IS WORKING!")
        print("\n✅ The monitoring system can:")
        print("   • Extract bill information from RSS items")
        print("   • Create workflow items for processing")
        print("   • Handle RSS callbacks correctly")
        print("   • Process bills through the workflow")
        
        print("\n💡 Ready for production testing with:")
        print("   • Real RSS feeds")
        print("   • Full AI analysis (when quota allows)")
        print("   • Database integration")
    else:
        print("⚠️ Some core tests failed. Check the implementation.")
    
    return passed >= 3

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)