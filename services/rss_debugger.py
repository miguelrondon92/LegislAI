import feedparser
import requests
from datetime import datetime

def debug_feed(feed_url, feed_name):
    """Debug a single RSS feed"""
    print(f"\n{'='*60}")
    print(f"DEBUGGING FEED: {feed_name}")
    print(f"URL: {feed_url}")
    print('='*60)
    
    try:
        # Parse the feed
        feed = feedparser.parse(feed_url)
        
        # Check for parsing errors
        print(f"Feed parsed successfully: {'Yes' if not feed.bozo else 'No (with errors)'}")
        if feed.bozo:
            print(f"Parse error: {feed.bozo_exception}")
        
        # Feed metadata
        print(f"Feed title: {feed.feed.get('title', 'N/A')}")
        print(f"Feed description: {feed.feed.get('description', 'N/A')}")
        print(f"Feed last updated: {feed.feed.get('updated', 'N/A')}")
        print(f"Number of entries: {len(feed.entries)}")
        
        # Show first few entries
        for i, entry in enumerate(feed.entries[:5]):
            print(f"\n--- Entry {i+1} ---")
            print(f"Title: {entry.get('title', 'N/A')}")
            print(f"Link: {entry.get('link', 'N/A')}")
            print(f"Published: {entry.get('published', 'N/A')}")
            print(f"Updated: {entry.get('updated', 'N/A')}")
            print(f"ID: {entry.get('id', 'N/A')}")
            print(f"Description: {entry.get('description', 'N/A')[:100]}...")
        
        return len(feed.entries)
        
    except Exception as e:
        print(f"ERROR: {str(e)}")
        return 0

def test_congress_feeds():
    """Test all Congress.gov feeds"""
    feeds = {
        'house_floor_today': 'https://www.congress.gov/rss/house-floor-today.xml',
        'senate_floor_today': 'https://www.congress.gov/rss/senate-floor-today.xml', 
        'presented_to_president': 'https://www.congress.gov/rss/presented-to-president.xml'
    }
    
    total_entries = 0
    
    for feed_name, feed_url in feeds.items():
        entries = debug_feed(feed_url, feed_name)
        total_entries += entries
    
    print(f"\n{'='*60}")
    print(f"SUMMARY: Found {total_entries} total entries across all feeds")
    print('='*60)
    
    if total_entries == 0:
        print("\nPOSSIBLE ISSUES:")
        print("1. Congress might not be in session today")
        print("2. No recent floor activity")
        print("3. Feeds might be temporarily unavailable")
        print("4. Network connectivity issues")
        
        print("\nTRY ALTERNATIVE FEEDS:")
        alt_feeds = {
            'all_house_bills': 'https://www.congress.gov/rss/bills-house.xml',
            'all_senate_bills': 'https://www.congress.gov/rss/bills-senate.xml',
            'house_floor_this_week': 'https://www.congress.gov/rss/house-floor-this-week.xml'
        }
        
        for name, url in alt_feeds.items():
            print(f"\nTesting alternative feed: {name}")
            entries = debug_feed(url, name)
            if entries > 0:
                print(f"✅ {name} has {entries} entries!")

def test_single_feed(url):
    """Test a single feed URL"""
    debug_feed(url, "Custom Feed")

if __name__ == "__main__":
    print("Congress.gov RSS Feed Debugger")
    print("Testing your configured feeds...")
    
    test_congress_feeds()