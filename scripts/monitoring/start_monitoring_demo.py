#!/usr/bin/env python3
"""
Demo script to start the monitoring system and show it working
This demonstrates how to use the workflow orchestrator in practice
"""

import os
import sys
import time
import signal
import logging
from datetime import datetime
from pathlib import Path

# Add the project root to the Python path
sys.path.insert(0, str(Path(__file__).parent))

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/monitoring_demo.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

def signal_handler(signum, frame):
    """Handle Ctrl+C gracefully"""
    print("\n🛑 Stopping monitoring system...")
    sys.exit(0)

def demo_monitoring_system():
    """Demonstrate the monitoring system in action"""
    print("🚀 LEGISLAI MONITORING SYSTEM DEMO")
    print("="*60)
    
    from services.workflow_orchestrator import WorkflowOrchestrator
    
    # Create orchestrator
    orchestrator = WorkflowOrchestrator()
    
    print("📊 Initial Status:")
    status = orchestrator.get_workflow_status()
    print(f"   Queue size: {status['queue_size']}")
    print(f"   Bills discovered: {status['statistics']['bills_discovered']}")
    print(f"   Bills processed: {status['statistics']['bills_processed']}")
    print(f"   Bills analyzed: {status['statistics']['bills_analyzed']}")
    
    print("\n🎯 Configuration:")
    print("   RSS Monitoring: Enabled")
    print("   Backfill Processing: Disabled (for demo)")
    print("   Check Interval: 30 seconds (faster for demo)")
    
    print("\n📡 Available RSS Feeds:")
    from services.rss_monitoring import PersistentRSSMonitor
    monitor = PersistentRSSMonitor()
    for feed_name, feed_url in monitor.feeds.items():
        print(f"   • {feed_name}: {feed_url}")
    
    print("\n🤖 AI Analysis Status:")
    try:
        from services.enhanced_ai_analyzer import EnhancedAIAnalyzer
        analyzer = EnhancedAIAnalyzer()
        quota_info = analyzer.get_quota_info()
        print(f"   Requests available: {quota_info['current_usage']['safe_remaining_requests']}")
        print(f"   Rate limit: {quota_info['current_usage']['requests_this_minute']}/{quota_info['current_usage']['max_requests_per_minute']}")
        print(f"   Status: {'🟢 Available' if not quota_info['status']['is_at_limit'] else '🔴 Rate Limited'}")
    except Exception as e:
        print(f"   Status: ⚠️ Error checking quota: {e}")
    
    print(f"\n⏰ Starting monitoring at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("📋 The system will:")
    print("   1. Monitor RSS feeds every 30 seconds")
    print("   2. Extract bill information from new items")
    print("   3. Add bills to processing queue")
    print("   4. Fetch bill details from Congress API")
    print("   5. Perform AI analysis (if quota allows)")
    print("   6. Generate user alerts")
    
    print("\n🔍 Press Ctrl+C to stop monitoring")
    print("="*60)
    
    # Set up signal handler for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        # Start monitoring with faster interval for demo
        orchestrator.start_workflow(
            check_interval=30,  # Check every 30 seconds
            enable_rss=True,
            enable_backfill=False
        )
    except KeyboardInterrupt:
        print("\n🛑 Monitoring stopped by user")
        orchestrator.stop_workflow()
    except Exception as e:
        print(f"\n❌ Error during monitoring: {e}")
        logger.error(f"Monitoring error: {e}")
        orchestrator.stop_workflow()

def quick_status_check():
    """Quick status check without starting full monitoring"""
    print("🔍 QUICK STATUS CHECK")
    print("="*40)
    
    from services.workflow_orchestrator import WorkflowOrchestrator
    
    orchestrator = WorkflowOrchestrator()
    status = orchestrator.get_workflow_status()
    
    print(f"📊 Workflow Status:")
    print(f"   Running: {status['is_running']}")
    print(f"   Queue size: {status['queue_size']}")
    
    print(f"\n📈 Statistics:")
    stats = status['statistics']
    print(f"   Bills discovered: {stats['bills_discovered']}")
    print(f"   Bills processed: {stats['bills_processed']}")
    print(f"   Bills analyzed: {stats['bills_analyzed']}")
    print(f"   Alerts generated: {stats['alerts_generated']}")
    print(f"   Errors: {stats['errors']}")
    
    if stats['last_run']:
        print(f"   Last run: {stats['last_run']}")
    
    print(f"\n🤖 AI Analysis:")
    print(f"   Total chunks analyzed: {stats['total_chunks_analyzed']}")
    print(f"   Total text processed: {stats['total_text_processed']:,} characters")
    
    # Rate limiting info
    rate_info = status['rate_limiting']
    if rate_info['workflow_stopped_due_to_rate_limit']:
        print(f"\n⚠️ Workflow stopped due to rate limit")
        print(f"   Rate limit hits: {rate_info['rate_limit_hits']}")
        if rate_info['last_rate_limit_time']:
            print(f"   Last rate limit: {rate_info['last_rate_limit_time']}")
    else:
        print(f"\n✅ Rate limiting: Normal")

def simulate_processing():
    """Simulate processing a few items without full monitoring"""
    print("🧪 SIMULATION MODE")
    print("="*40)
    
    from services.workflow_orchestrator import WorkflowOrchestrator
    from services.rss_monitoring import PersistentRSSMonitor
    
    # Check for new RSS items
    monitor = PersistentRSSMonitor(storage_file='demo_seen_items.json')
    orchestrator = WorkflowOrchestrator()
    
    print("📡 Checking RSS feeds for new items...")
    
    total_new_items = 0
    for feed_name, feed_url in monitor.feeds.items():
        try:
            new_items = monitor.parse_feed(feed_url)
            total_new_items += len(new_items)
            
            print(f"   {feed_name}: {len(new_items)} new items")
            
            # Process first 2 items from each feed
            for item in new_items[:2]:
                print(f"      📋 Found: {item['title'][:60]}...")
                orchestrator._handle_new_rss_item(item)
                
        except Exception as e:
            print(f"   ❌ {feed_name}: Error - {e}")
    
    print(f"\n📊 Total new items: {total_new_items}")
    print(f"📊 Items in queue: {len(orchestrator.workflow_queue)}")
    
    if orchestrator.workflow_queue:
        print(f"\n🔄 Processing queue items...")
        
        items_to_process = orchestrator.workflow_queue[:3]  # Process first 3 items
        
        for item in items_to_process:
            print(f"   Processing: {item.bill_identifier}")
            try:
                orchestrator._process_workflow_item(item)
                print(f"      Status: {item.status.value}")
                if item.error_message:
                    print(f"      Error: {item.error_message}")
            except Exception as e:
                print(f"      Error: {e}")
    
    # Clean up
    demo_file = Path('demo_seen_items.json')
    if demo_file.exists():
        demo_file.unlink()

def main():
    """Main function"""
    print("🎯 LEGISLAI MONITORING SYSTEM")
    print("="*60)
    
    # Ensure logs directory exists
    Path("logs").mkdir(exist_ok=True)
    
    if len(sys.argv) > 1:
        mode = sys.argv[1].lower()
    else:
        print("Available modes:")
        print("  python start_monitoring_demo.py demo     - Start full monitoring demo")
        print("  python start_monitoring_demo.py status   - Quick status check")
        print("  python start_monitoring_demo.py simulate - Simulate processing")
        print("\nEnter mode (demo/status/simulate): ", end="")
        mode = input().lower().strip()
    
    if mode == "demo":
        demo_monitoring_system()
    elif mode == "status":
        quick_status_check()
    elif mode == "simulate":
        simulate_processing()
    else:
        print(f"❌ Unknown mode: {mode}")
        print("Available modes: demo, status, simulate")
        sys.exit(1)

if __name__ == "__main__":
    main()