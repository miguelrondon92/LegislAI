import feedparser
import requests
from datetime import datetime
import logging

class CongressRSSFeeds:
    """Parser for various Congress-related RSS feeds"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Legislative-Analysis-Platform/1.0'
        })
    
    def get_govinfo_feeds(self):
        """Get available GovInfo RSS feeds"""
        feeds = {
            'house_bills': 'https://www.congress.gov/rss/house-floor-today.xml',
            'senate_bills': 'https://www.congress.gov/rss/senate-floor-today.xml', 
            'presented_to_president': 'https://www.congress.gov/rss/presented-to-president.xml'
        }
        return feeds
    
    def parse_rss_feed(self, feed_url):
        """Parse an RSS feed and return structured data"""
        try:
            feed = feedparser.parse(feed_url)
            
            if feed.bozo:
                logging.warning(f"RSS feed may have issues: {feed_url}")
            
            items = []
            for entry in feed.entries:
                item = {
                    'title': entry.get('title', ''),
                    'link': entry.get('link', ''),
                    'description': entry.get('description', ''),
                    'published': self._parse_date(entry.get('published', '')),
                    'updated': self._parse_date(entry.get('updated', '')),
                    'id': entry.get('id', ''),
                    'tags': [tag.term for tag in entry.get('tags', [])]
                }
                items.append(item)
            
            return {
                'feed_info': {
                    'title': feed.feed.get('title', ''),
                    'description': feed.feed.get('description', ''),
                    'link': feed.feed.get('link', ''),
                    'updated': self._parse_date(feed.feed.get('updated', ''))
                },
                'items': items
            }
            
        except Exception as e:
            logging.error(f"Error parsing RSS feed {feed_url}: {str(e)}")
            return None
    
    def _parse_date(self, date_string):
        """Parse various date formats from RSS feeds"""
        if not date_string:
            return None
        
        try:
            # Try common RSS date formats
            for fmt in ['%a, %d %b %Y %H:%M:%S %Z',
                       '%Y-%m-%dT%H:%M:%S%z',
                       '%Y-%m-%d %H:%M:%S']:
                try:
                    return datetime.strptime(date_string, fmt)
                except ValueError:
                    continue
            
            # If standard formats fail, try feedparser's built-in parsing
            return datetime(*feedparser._parse_date(date_string)[:6])
        except:
            return None
    
    def get_recent_bills_rss(self, chamber='both', limit=50):
        """Get recent bills from RSS feeds"""
        feeds = self.get_govinfo_feeds()
        all_bills = []
        
        feed_urls = []
        if chamber in ['both', 'house']:
            feed_urls.append(feeds['house_bills'])
        if chamber in ['both', 'senate']:
            feed_urls.append(feeds['senate_bills'])
        
        for feed_url in feed_urls:
            feed_data = self.parse_rss_feed(feed_url)
            if feed_data and 'items' in feed_data:
                all_bills.extend(feed_data['items'][:limit])
        
        # Sort by published date, most recent first
        all_bills.sort(key=lambda x: x['published'] or datetime.min, reverse=True)
        return all_bills[:limit]
    
    def get_congressional_record_rss(self, limit=20):
        """Get recent Congressional Record entries"""
        feeds = self.get_govinfo_feeds()
        return self.parse_rss_feed(feeds['congressional_record'])
    
    def search_rss_feeds(self, keyword, feeds_to_search=None):
        """Search across multiple RSS feeds for keyword"""
        if feeds_to_search is None:
            feeds_to_search = self.get_govinfo_feeds()
        
        results = []
        keyword_lower = keyword.lower()
        
        for feed_name, feed_url in feeds_to_search.items():
            feed_data = self.parse_rss_feed(feed_url)
            if not feed_data:
                continue
                
            for item in feed_data['items']:
                title = item['title'].lower()
                description = item['description'].lower()
                
                if keyword_lower in title or keyword_lower in description:
                    item['source_feed'] = feed_name
                    results.append(item)
        
        return results
    
    def monitor_feeds(self, keywords, callback_func=None):
        """Monitor RSS feeds for specific keywords"""
        feeds = self.get_govinfo_feeds()
        matches = []
        
        for keyword in keywords:
            keyword_matches = self.search_rss_feeds(keyword, feeds)
            for match in keyword_matches:
                match['matched_keyword'] = keyword
                matches.append(match)
                
                if callback_func:
                    callback_func(match)
        
        return matches

# Example usage functions
def print_recent_bills():
    """Example: Print recent bills from RSS"""
    rss_parser = CongressRSSFeeds()
    recent_bills = rss_parser.get_recent_bills_rss(limit=10)
    
    print("Recent Bills from RSS:")
    print("=" * 50)
    for bill in recent_bills:
        print(f"Title: {bill['title']}")
        print(f"Published: {bill['published']}")
        print(f"Link: {bill['link']}")
        print("-" * 40)

def search_bills_by_keyword(keyword):
    """Example: Search RSS feeds for keyword"""
    rss_parser = CongressRSSFeeds()
    results = rss_parser.search_rss_feeds(keyword)
    
    print(f"Search results for '{keyword}':")
    print("=" * 50)
    for result in results:
        print(f"Title: {result['title']}")
        print(f"Source: {result['source_feed']}")
        print(f"Published: {result['published']}")
        print(f"Link: {result['link']}")
        print("-" * 40)

if __name__ == "__main__":
    # Example usage
    print_recent_bills()
    #search_bills_by_keyword("")