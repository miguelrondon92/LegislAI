import time
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Set, Dict, List, Callable
import feedparser
import requests

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('rss_monitor.log'),
        logging.StreamHandler()
    ]
)

class PersistentRSSMonitor:
    """Continuously monitor RSS feeds and track new items"""
    
    def __init__(self, storage_file='seen_items.json'):
        self.storage_file = Path(storage_file)
        self.seen_items = self._load_seen_items()
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Legislative-Analysis-Platform/1.0'
        })
        
        # Default feeds to monitor
        self.feeds = {
            'house_bills': 'https://www.congress.gov/rss/house-floor-today.xml',
            'senate_bills': 'https://www.congress.gov/rss/senate-floor-today.xml', 
            'presented_to_president': 'https://www.congress.gov/rss/presented-to-president.xml'
        }
    
    def _load_seen_items(self) -> Set[str]:
        """Load previously seen item IDs from storage"""
        if self.storage_file.exists():
            try:
                with open(self.storage_file, 'r') as f:
                    data = json.load(f)
                    return set(data.get('seen_items', []))
            except Exception as e:
                logging.error(f"Error loading seen items: {e}")
        return set()
    
    def _save_seen_items(self):
        """Save seen item IDs to storage"""
        try:
            data = {
                'seen_items': list(self.seen_items),
                'last_updated': datetime.now().isoformat()
            }
            with open(self.storage_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logging.error(f"Error saving seen items: {e}")
    
    def parse_feed(self, feed_url: str) -> List[Dict]:
        """Parse RSS feed and return new items only"""
        try:
            feed = feedparser.parse(feed_url)
            new_items = []
            
            for entry in feed.entries:
                item_id = entry.get('id') or entry.get('link', '')
                
                if item_id not in self.seen_items:
                    item = {
                        'id': item_id,
                        'title': entry.get('title', ''),
                        'link': entry.get('link', ''),
                        'description': entry.get('description', ''),
                        'published': entry.get('published', ''),
                        'feed_url': feed_url,
                        'discovered_at': datetime.now().isoformat()
                    }
                    new_items.append(item)
                    self.seen_items.add(item_id)
            
            return new_items
            
        except Exception as e:
            logging.error(f"Error parsing feed {feed_url}: {e}")
            return []
    
    def check_keywords(self, item: Dict, keywords: List[str]) -> List[str]:
        """Check if item contains any of the specified keywords"""
        text = f"{item['title']} {item['description']}".lower()
        matched_keywords = [kw for kw in keywords if kw.lower() in text]
        return matched_keywords
    
    def monitor_feeds(self, 
                     keywords: List[str] = None, 
                     callback: Callable = None,
                     check_interval: int = 300):  # 5 minutes default
        """
        Continuously monitor RSS feeds
        
        Args:
            keywords: List of keywords to watch for (optional)
            callback: Function to call when new items are found
            check_interval: Seconds between checks
        """
        logging.info(f"Starting RSS monitor with {len(self.feeds)} feeds")
        logging.info(f"Keywords: {keywords or 'All items'}")
        logging.info(f"Check interval: {check_interval} seconds")
        
        try:
            while True:
                total_new_items = 0
                
                for feed_name, feed_url in self.feeds.items():
                    try:
                        new_items = self.parse_feed(feed_url)
                        
                        for item in new_items:
                            total_new_items += 1
                            
                            # Check keywords if specified
                            if keywords:
                                matched_keywords = self.check_keywords(item, keywords)
                                if matched_keywords:
                                    item['matched_keywords'] = matched_keywords
                                    self._handle_new_item(item, feed_name, callback)
                            else:
                                # No keyword filter, process all new items
                                self._handle_new_item(item, feed_name, callback)
                        
                    except Exception as e:
                        logging.error(f"Error checking feed {feed_name}: {e}")
                
                # Save seen items after each cycle
                if total_new_items > 0:
                    self._save_seen_items()
                    logging.info(f"Found {total_new_items} new items this cycle")
                
                # Wait before next check
                logging.info(f"Sleeping for {check_interval} seconds...")
                time.sleep(check_interval)
                
        except KeyboardInterrupt:
            logging.info("Monitor stopped by user")
            self._save_seen_items()
        except Exception as e:
            logging.error(f"Monitor error: {e}")
            self._save_seen_items()
    
    def _handle_new_item(self, item: Dict, feed_name: str, callback: Callable = None):
        """Handle a new item discovery"""
        item['source_feed'] = feed_name
        
        # Log the discovery
        logging.info(f"NEW ITEM in {feed_name}: {item['title']}")
        
        # Call custom callback if provided
        if callback:
            try:
                callback(item)
            except Exception as e:
                logging.error(f"Callback error: {e}")
        else:
            # Default action - print details
            self._default_item_handler(item)
    
    def _default_item_handler(self, item: Dict):
        """Default handler for new items"""
        print("\n" + "="*60)
        print(f"NEW LEGISLATIVE ITEM FOUND!")
        print("="*60)
        print(f"Title: {item['title']}")
        print(f"Source: {item['source_feed']}")
        print(f"Link: {item['link']}")
        if 'matched_keywords' in item:
            print(f"Matched Keywords: {', '.join(item['matched_keywords'])}")
        print(f"Published: {item['published']}")
        print(f"Description: {item['description'][:200]}...")
        print("="*60)
    
    def add_feed(self, name: str, url: str):
        """Add a new RSS feed to monitor"""
        self.feeds[name] = url
        logging.info(f"Added feed: {name} -> {url}")
    
    def remove_feed(self, name: str):
        """Remove a feed from monitoring"""
        if name in self.feeds:
            del self.feeds[name]
            logging.info(f"Removed feed: {name}")
    
    def get_stats(self) -> Dict:
        """Get monitoring statistics"""
        return {
            'feeds_monitored': len(self.feeds),
            'items_seen': len(self.seen_items),
            'storage_file': str(self.storage_file),
            'feeds': list(self.feeds.keys())
        }

# Custom callback functions
def email_alert(item: Dict):
    """Example: Send email alert for new items"""
    # You would implement email sending here
    print(f"📧 EMAIL ALERT: {item['title']}")

def slack_notification(item: Dict):
    """Example: Send Slack notification"""
    # You would implement Slack webhook here
    print(f"💬 SLACK: New legislative item: {item['title']}")

def save_to_database(item: Dict):
    """Example: Save item to database"""
    # You would implement database saving here
    print(f"💾 DB SAVE: {item['title']}")

# Main monitoring functions
def start_keyword_monitor(keywords: List[str], interval: int = 300):
    """Start monitoring with specific keywords"""
    monitor = PersistentRSSMonitor()
    
    def combined_callback(item):
        email_alert(item)
        slack_notification(item)
        save_to_database(item)
    
    monitor.monitor_feeds(
        keywords=keywords,
        callback=combined_callback,
        check_interval=interval
    )

def start_basic_monitor(interval: int = 600):
    """Start basic monitoring of all items"""
    monitor = PersistentRSSMonitor()
    monitor.monitor_feeds(check_interval=interval)

if __name__ == "__main__":
    # Monitor all items without keyword filtering
    print("Starting Congress.gov RSS Monitor...")
    print("Monitoring feeds:")
    print("- House Floor Today")
    print("- Senate Floor Today") 
    print("- Bills Presented to President")
    print("Press Ctrl+C to stop")
    
    # Start monitoring without keywords (will capture all new items)
    start_basic_monitor(interval=10)  # Check every 10 seconds