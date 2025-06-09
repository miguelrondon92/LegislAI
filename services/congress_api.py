import requests
import os
import time
import logging
from datetime import datetime, timedelta
from urllib.parse import urlencode
import json
import re

CURRENT_CONGRESS = 119

class CongressAPI:
    """Client for interacting with the Congress.gov API"""
    
    def __init__(self):
        self.api_key = os.environ.get("CONGRESS_API_KEY", "")
        self.base_url = "https://api.congress.gov/v3"
        self.session = requests.Session()
        
        # Set required headers
        self.session.headers.update({
            'X-API-Key': self.api_key,
            'User-Agent': 'Legislative-Analysis-Platform/1.0 (educational-purpose)'
        })
        
        # Rate limiting
        self.last_request_time = 0
        self.min_request_interval = 3.6  # Roughly 1000 requests per hour limit
    
    def _make_request(self, endpoint, params=None):
        """Make a rate-limited request to the Congress API"""
        # Implement rate limiting
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        if time_since_last < self.min_request_interval:
            time.sleep(self.min_request_interval - time_since_last)
        
        url = f"{self.base_url}{endpoint}"
        if params:
            url += "?" + urlencode(params)
        
        try:
            self.last_request_time = time.time()
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logging.error(f"Congress API request failed: {str(e)}")
            return None
    
    def get_bill_by_number(self, bill_identifier):
        """
        Get a bill by its identifier (e.g., 'HR-1234', 'S-567')
        """
        try:
            # Parse bill identifier
            parts = bill_identifier.upper().replace('-', '').replace(' ', '')
            print(parts)
            if parts.startswith('HR'):
                bill_type = 'hr'
                bill_number = parts[2:]
            elif parts.startswith('S') and not parts.startswith('SJRES'):
                bill_type = 's'
                bill_number = parts[1:]
            elif parts.lower().replace(".","").startswith('hjres'):
                bill_type = 'hjres'
                bill_number = re.findall(r'\d+', parts)
                bill_number = bill_number[-1]
                print(f"bill_number: {bill_number}")
            elif parts.startswith('SJRES'):
                bill_type = 'sjres'
                bill_number = parts[5:]
            else:
                logging.error(f"Invalid bill identifier format: {bill_identifier}")
                return None
            
            # Use current congress (118th)
            congress = CURRENT_CONGRESS
            
            return self.get_bill_details(congress, bill_type, bill_number)
            
        except Exception as e:
            logging.error(f"Error parsing bill identifier {bill_identifier}: {str(e)}")
            return None
    
    def get_bill_details(self, congress, bill_type, bill_number):
        """Get detailed information about a specific bill"""
        endpoint = f"/bill/{congress}/{bill_type}/{bill_number}"
        bill_data = self._make_request(endpoint)
        
        if not bill_data or 'bill' not in bill_data:
            return None
        
        bill = bill_data['bill']
        
        # Get bill text
        text_data = self.get_bill_text(congress, bill_type, bill_number)
        if text_data:
            bill['full_text'] = text_data
        
        # Get bill actions for status
        actions_data = self.get_bill_actions(congress, bill_type, bill_number)
        if actions_data:
            bill['actions'] = actions_data
        
        return bill
    
    def get_bill_text(self, congress, bill_type, bill_number):
        """Get the full text of a bill"""
        endpoint = f"/bill/{congress}/{bill_type}/{bill_number}/text"
        text_data = self._make_request(endpoint)
        
        if not text_data or 'textVersions' not in text_data:
            return None
        
        # Get the most recent version
        versions = text_data['textVersions']
        if not versions:
            return None
        
        # Try to get the introduced version or the latest available
        latest_version = versions[0]
        
        # Extract text content
        formats = latest_version.get('formats', [])
        for format_info in formats:
            if format_info.get('type') == 'Formatted Text':
                text_url = format_info.get('url')
                if text_url:
                    try:
                        text_response = self.session.get(text_url, timeout=30)
                        if text_response.status_code == 200:
                            return re.sub(r'<[^>]*>', '', text_response.text)
                    except Exception as e:
                        logging.error(f"Error fetching bill text: {str(e)}")
        
        return None
    
    def get_bill_actions(self, congress, bill_type, bill_number):
        """Get actions taken on a bill"""
        endpoint = f"/bill/{congress}/{bill_type}/{bill_number}/actions"
        return self._make_request(endpoint)
    
    def search_bills(self, query, limit=50):
        """Search for bills by keyword"""
        params = {
            'q': query,
            'limit': min(limit, 250),  # API maximum
            'sort': 'updateDate+desc'
        }
        
        endpoint = "/bill"
        data = self._make_request(endpoint, params)
        
        if not data or 'bills' not in data:
            return []
        
        # Return basic bill summaries to avoid timeout
        bills = []
        for bill_summary in data['bills'][:limit]:
            try:
                congress = bill_summary.get('congress')
                bill_type = bill_summary.get('type', '').lower()
                bill_number = bill_summary.get('number')
                
                if congress and bill_type and bill_number:
                    # Create basic bill object from search results
                    basic_bill = {
                        'congress': congress,
                        'bill_type': bill_type,
                        'bill_number': bill_number,
                        'title': bill_summary.get('title', ''),
                        'summary': bill_summary.get('title', ''),
                        'sponsor_name': '',
                        'sponsor_party': '',
                        'sponsor_state': '',
                        'introduced_date': None,
                        'last_action_date': None,
                        'status': 'Unknown',
                        'congress_api_url': bill_summary.get('url', ''),
                        'full_text': None
                    }
                    
                    # Parse latest action if available
                    if 'latestAction' in bill_summary:
                        action = bill_summary['latestAction']
                        basic_bill['status'] = action.get('text', 'Unknown')[:50]
                        if 'actionDate' in action:
                            try:
                                from datetime import datetime
                                basic_bill['last_action_date'] = datetime.strptime(action['actionDate'], '%Y-%m-%d')
                            except:
                                pass
                    
                    bills.append(basic_bill)
                        
            except Exception as e:
                logging.error(f"Error processing bill in search results: {str(e)}")
                continue
        
        return bills
    
    def search_bills_by_sponsor(self, sponsor_name, limit=20):
        """Search for bills by sponsor name"""
        # This is a simplified search - the API doesn't have direct sponsor search
        # We'll search for bills and filter by sponsor in the results
        params = {
            'limit': 100,  # Get more results to filter
            'sort': 'updateDate+desc'
        }
        
        endpoint = "/bill"
        data = self._make_request(endpoint, params)
        
        if not data or 'bills' not in data:
            return []
        
        matching_bills = []
        sponsor_name_lower = sponsor_name.lower()
        
        for bill_summary in data['bills']:
            # Check if sponsor name matches
            sponsors = bill_summary.get('sponsors', [])
            for sponsor in sponsors:
                sponsor_full_name = f"{sponsor.get('firstName', '')} {sponsor.get('lastName', '')}".lower()
                if sponsor_name_lower in sponsor_full_name:
                    # Get detailed bill info
                    congress = bill_summary.get('congress')
                    bill_type = bill_summary.get('type', '').lower()
                    bill_number = bill_summary.get('number')
                    
                    if congress and bill_type and bill_number:
                        detailed_bill = self.get_bill_details(congress, bill_type, bill_number)
                        if detailed_bill:
                            matching_bills.append(detailed_bill)
                            
                        if len(matching_bills) >= limit:
                            return matching_bills
                    break
        
        return matching_bills
    
    def get_recent_bills(self, days=7, limit=20):
        """Get bills introduced or updated in the last N days"""
        params = {
            'limit': limit,
            'sort': 'updateDate+desc'
        }
        
        endpoint = "/bill"
        data = self._make_request(endpoint, params)
        
        if not data or 'bills' not in data:
            return []
        
        cutoff_date = datetime.now() - timedelta(days=days)
        recent_bills = []
        
        for bill_summary in data['bills']:
            update_date_str = bill_summary.get('updateDate')
            if update_date_str:
                try:
                    update_date = datetime.fromisoformat(update_date_str.replace('Z', '+00:00'))
                    if update_date.replace(tzinfo=None) >= cutoff_date:
                        congress = bill_summary.get('congress')
                        bill_type = bill_summary.get('type', '').lower()
                        bill_number = bill_summary.get('number')
                        
                        if congress and bill_type and bill_number:
                            detailed_bill = self.get_bill_details(congress, bill_type, bill_number)
                            if detailed_bill:
                                recent_bills.append(detailed_bill)
                except Exception as e:
                    logging.error(f"Error parsing date: {str(e)}")
                    continue
        
        return recent_bills

if __name__ == "__main__":
    c = CongressAPI()
    bill = c.get_bill_by_number("H.J.Res.87")
    print(json.dumps(bill, indent= 2))