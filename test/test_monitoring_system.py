#!/usr/bin/env python3
"""
Test script for the monitoring system with workflow orchestrator
This script tests the monitoring and processing of a specific small bill
"""

import os
import sys
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path

# Add the project root to the Python path
sys.path.insert(0, str(Path(__file__).parent))

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/monitoring_test.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

def test_congress_api():
    """Test the Congress API with a specific small bill"""
    print("="*60)
    print("🔍 TESTING CONGRESS API")
    print("="*60)
    
    from services.congress_api import CongressAPI
    
    api = CongressAPI()
    
    # Test with a small, simple bill (House Joint Resolution)
    test_bill_id = "H.J.Res.87"  # This is typically a small constitutional amendment resolution
    
    print(f"📋 Testing with bill: {test_bill_id}")
    
    try:
        # Get bill details
        bill_data = api.get_bill_by_number(test_bill_id)
        
        if bill_data:
            print(f"✅ Successfully fetched bill: {bill_data.get('title', 'No title')}")
            print(f"📊 Congress: {bill_data.get('congress', 'Unknown')}")
            print(f"📄 Type: {bill_data.get('type', 'Unknown')}")
            print(f"🔢 Number: {bill_data.get('number', 'Unknown')}")
            
            # Check if full text is available
            if 'full_text' in bill_data and bill_data['full_text']:
                text_length = len(bill_data['full_text'])
                print(f"📝 Full text length: {text_length:,} characters")
                
                # Show first 200 characters
                preview = bill_data['full_text'][:200] + "..." if len(bill_data['full_text']) > 200 else bill_data['full_text']
                print(f"📖 Text preview: {preview}")
                
                return bill_data
            else:
                print("⚠️ No full text available for this bill")
                return bill_data
        else:
            print("❌ Failed to fetch bill data")
            return None
            
    except Exception as e:
        print(f"❌ Error testing Congress API: {e}")
        logger.error(f"Congress API test failed: {e}")
        return None

def test_bill_processor():
    """Test the bill processor with the fetched bill"""
    print("\n" + "="*60)
    print("🔧 TESTING BILL PROCESSOR")
    print("="*60)
    
    from services.bill_processor import BillProcessor
    from services.congress_api import CongressAPI
    
    processor = BillProcessor()
    api = CongressAPI()
    
    # Get the test bill
    test_bill_id = "H.J.Res.87"
    
    try:
        # Fetch bill data
        bill_data = api.get_bill_by_number(test_bill_id)
        
        if not bill_data:
            print("❌ No bill data to process")
            return None
        
        print(f"📋 Processing bill: {bill_data.get('title', 'No title')}")
        
        # Process the bill
        processed_bill = processor.process_bill_data(bill_data)
        
        if processed_bill:
            print(f"✅ Successfully processed bill: {processed_bill.get_bill_identifier()}")
            print(f"📊 Title: {processed_bill.title}")
            print(f"🗓️ Introduced: {processed_bill.introduced_date}")
            print(f"📈 Status: {processed_bill.status}")
            
            return processed_bill
        else:
            print("❌ Failed to process bill")
            return None
            
    except Exception as e:
        print(f"❌ Error testing bill processor: {e}")
        logger.error(f"Bill processor test failed: {e}")
        return None

def test_ai_analyzer():
    """Test the AI analyzer with the processed bill"""
    print("\n" + "="*60)
    print("🤖 TESTING AI ANALYZER")
    print("="*60)
    
    from services.enhanced_ai_analyzer import EnhancedAIAnalyzer
    from services.congress_api import CongressAPI
    
    analyzer = EnhancedAIAnalyzer()
    api = CongressAPI()
    
    # Check quota first
    quota_info = analyzer.get_quota_info()
    print(f"📊 AI Quota Status:")
    print(f"   Requests this minute: {quota_info['current_usage']['requests_this_minute']}/{quota_info['current_usage']['max_requests_per_minute']}")
    print(f"   Safe remaining: {quota_info['current_usage']['safe_remaining_requests']}")
    print(f"   At limit: {quota_info['status']['is_at_limit']}")
    
    if quota_info['status']['is_at_limit']:
        print("⚠️ AI analyzer is at rate limit, skipping analysis test")
        return None
    
    # Get the test bill
    test_bill_id = "H.J.Res.87"
    
    try:
        # Fetch bill data
        bill_data = api.get_bill_by_number(test_bill_id)
        
        if not bill_data or not bill_data.get('full_text'):
            print("❌ No bill text available for analysis")
            return None
        
        full_text = bill_data['full_text']
        title = bill_data.get('title', 'Untitled Bill')
        
        print(f"📋 Analyzing bill: {title}")
        print(f"📝 Text length: {len(full_text):,} characters")
        
        # Perform AI analysis
        analysis = analyzer.analyze_bill(full_text, title)
        
        if analysis:
            print(f"✅ Successfully analyzed bill")
            print(f"📄 Analysis components: {list(analysis.keys())}")
            
            # Show key analysis results
            if 'summary' in analysis:
                print(f"📝 Summary: {analysis['summary'][:200]}...")
            
            if 'policy_implications' in analysis:
                policy_data = analysis['policy_implications']
                print(f"🎯 Primary policy area: {policy_data.get('primary_policy_area', 'Unknown')}")
                
                if 'categories' in policy_data:
                    categories = [cat.get('area', 'Unknown') for cat in policy_data['categories']]
                    print(f"📊 Policy categories: {', '.join(categories[:3])}")
            
            if 'stakeholders' in analysis:
                stakeholders = analysis['stakeholders']
                if isinstance(stakeholders, dict):
                    winners = len(stakeholders.get('winners', []))
                    losers = len(stakeholders.get('losers', []))
                    print(f"👥 Stakeholders: {winners} winners, {losers} losers")
            
            return analysis
        else:
            print("❌ Failed to analyze bill")
            return None
            
    except Exception as e:
        print(f"❌ Error testing AI analyzer: {e}")
        logger.error(f"AI analyzer test failed: {e}")
        return None

def test_workflow_orchestrator():
    """Test the workflow orchestrator with a single bill"""
    print("\n" + "="*60)
    print("🎯 TESTING WORKFLOW ORCHESTRATOR")
    print("="*60)
    
    from services.workflow_orchestrator import WorkflowOrchestrator, WorkflowItem, WorkflowStatus
    
    orchestrator = WorkflowOrchestrator()
    
    # Create a test workflow item
    test_item = WorkflowItem(
        bill_identifier="H.J.Res.87",
        congress=119,
        bill_type="hjres",
        bill_number=87,
        title="Test Bill for Monitoring System",
        source="manual_test",
        discovered_at=datetime.utcnow(),
        status=WorkflowStatus.PENDING
    )
    
    print(f"📋 Creating test workflow item: {test_item.bill_identifier}")
    
    try:
        # Add the item to the queue
        orchestrator.workflow_queue.append(test_item)
        print(f"✅ Added item to workflow queue")
        
        # Process the single item
        print(f"🔄 Processing workflow item...")
        orchestrator._process_workflow_item(test_item)
        
        # Check the results
        print(f"📊 Workflow item status: {test_item.status.value}")
        
        if test_item.status == WorkflowStatus.COMPLETED:
            print(f"✅ Successfully processed workflow item")
            print(f"📋 Bill ID: {test_item.bill_id}")
            print(f"🤖 Analysis completed: {test_item.analysis_completed}")
            print(f"🔔 Alerts generated: {test_item.alerts_generated}")
            
            if test_item.analysis_completed:
                print(f"📊 Analysis metadata:")
                print(f"   Text length: {test_item.text_length:,} characters" if test_item.text_length else "   Text length: Unknown")
                print(f"   Chunks analyzed: {test_item.chunks_analyzed}" if test_item.chunks_analyzed else "   Chunks analyzed: Unknown")
                print(f"   Analysis method: {test_item.analysis_method}" if test_item.analysis_method else "   Analysis method: Unknown")
                print(f"   Processing time: {test_item.processing_time:.2f}s" if test_item.processing_time else "   Processing time: Unknown")
            
            return test_item
        else:
            print(f"❌ Workflow item failed: {test_item.error_message}")
            return None
            
    except Exception as e:
        print(f"❌ Error testing workflow orchestrator: {e}")
        logger.error(f"Workflow orchestrator test failed: {e}")
        return None

def test_monitoring_integration():
    """Test the complete monitoring system integration"""
    print("\n" + "="*60)
    print("🔗 TESTING MONITORING INTEGRATION")
    print("="*60)
    
    from services.workflow_orchestrator import WorkflowOrchestrator
    
    orchestrator = WorkflowOrchestrator()
    
    # Create a mock RSS item to simulate monitoring discovery
    mock_rss_item = {
        'title': 'H.J.Res.87 - Test Constitutional Amendment',
        'link': 'https://www.congress.gov/bill/119th-congress/house-joint-resolution/87',
        'description': 'A test constitutional amendment resolution',
        'published': datetime.utcnow().isoformat(),
        'source_feed': 'test_feed'
    }
    
    print(f"📋 Simulating RSS item discovery: {mock_rss_item['title']}")
    
    try:
        # Handle the mock RSS item
        orchestrator._handle_new_rss_item(mock_rss_item)
        
        # Check if it was added to the queue
        if orchestrator.workflow_queue:
            print(f"✅ Successfully added RSS item to workflow queue")
            print(f"📊 Queue size: {len(orchestrator.workflow_queue)}")
            
            # Process the queue
            items_to_process = orchestrator.workflow_queue.copy()
            orchestrator.workflow_queue.clear()
            
            for item in items_to_process:
                print(f"🔄 Processing item: {item.bill_identifier}")
                orchestrator._process_workflow_item(item)
                
                if item.status == WorkflowStatus.COMPLETED:
                    print(f"✅ Successfully processed: {item.bill_identifier}")
                else:
                    print(f"❌ Failed to process: {item.bill_identifier} - {item.error_message}")
            
            return True
        else:
            print("❌ Failed to add RSS item to workflow queue")
            return False
            
    except Exception as e:
        print(f"❌ Error testing monitoring integration: {e}")
        logger.error(f"Monitoring integration test failed: {e}")
        return False

def main():
    """Main test function"""
    print("🚀 STARTING MONITORING SYSTEM TEST")
    print("="*60)
    
    # Ensure logs directory exists
    Path("logs").mkdir(exist_ok=True)
    
    test_results = {}
    
    # Test 1: Congress API
    print("\n📋 TEST 1: Congress API")
    test_results['congress_api'] = test_congress_api() is not None
    
    # Test 2: Bill Processor
    print("\n🔧 TEST 2: Bill Processor")
    test_results['bill_processor'] = test_bill_processor() is not None
    
    # Test 3: AI Analyzer
    print("\n🤖 TEST 3: AI Analyzer")
    test_results['ai_analyzer'] = test_ai_analyzer() is not None
    
    # Test 4: Workflow Orchestrator
    print("\n🎯 TEST 4: Workflow Orchestrator")
    test_results['workflow_orchestrator'] = test_workflow_orchestrator() is not None
    
    # Test 5: Monitoring Integration
    print("\n🔗 TEST 5: Monitoring Integration")
    test_results['monitoring_integration'] = test_monitoring_integration()
    
    # Summary
    print("\n" + "="*60)
    print("📊 TEST SUMMARY")
    print("="*60)
    
    passed = sum(test_results.values())
    total = len(test_results)
    
    for test_name, result in test_results.items():
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{test_name.replace('_', ' ').title()}: {status}")
    
    print(f"\n📈 Overall: {passed}/{total} tests passed ({passed/total*100:.1f}%)")
    
    if passed == total:
        print("🎉 ALL TESTS PASSED! The monitoring system is working correctly.")
    else:
        print("⚠️ Some tests failed. Check the logs for details.")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)