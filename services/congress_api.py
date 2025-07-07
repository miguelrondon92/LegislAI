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
        Get a bill by its identifier (e.g., 'HR-1234', 'S-567', 'H.Res.516')
        """
        try:
            # Parse bill identifier
            parts = bill_identifier.upper().replace('-', '').replace(' ', '').replace('.', '')
            print(parts)
            
            # Handle different bill types
            if parts.startswith('HR') and not parts.startswith('HRES'):
                bill_type = 'hr'
                bill_number = parts[2:]
            elif parts.startswith('S') and not parts.startswith('SJRES') and not parts.startswith('SRES'):
                bill_type = 's'
                bill_number = parts[1:]
            elif parts.startswith('HRES'):
                bill_type = 'hres'
                bill_number = parts[4:]
            elif parts.startswith('SRES'):
                bill_type = 'sres'
                bill_number = parts[4:]
            elif parts.lower().replace(".","").startswith('hjres'):
                bill_type = 'hjres'
                bill_number = re.findall(r'\d+', parts)
                bill_number = bill_number[-1]
                print(f"bill_number: {bill_number}")
            elif parts.startswith('SJRES'):
                bill_type = 'sjres'
                bill_number = parts[5:]
            elif parts.startswith('HCONRES'):
                bill_type = 'hconres'
                bill_number = parts[7:]
            elif parts.startswith('SCONRES'):
                bill_type = 'sconres'
                bill_number = parts[7:]
            else:
                logging.error(f"Invalid bill identifier format: {bill_identifier}")
                return None
            
            # Use current congress (119th)
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
        """Get the full text of a bill with enhanced version selection"""
        endpoint = f"/bill/{congress}/{bill_type}/{bill_number}/text"
        text_data = self._make_request(endpoint)
        
        if not text_data or 'textVersions' not in text_data:
            logging.warning(f"No text versions available for {congress}-{bill_type}-{bill_number}")
            return None
        
        versions = text_data['textVersions']
        if not versions:
            logging.warning(f"Empty text versions for {congress}-{bill_type}-{bill_number}")
            return None
        
        logging.debug(f"Found {len(versions)} text versions for {congress}-{bill_type}-{bill_number}")
        
        # Prioritize version types (most complete first)
        preferred_types = ['Enrolled', 'Engrossed in House', 'Engrossed in Senate', 
                          'Referred in Senate', 'Referred in House', 'Reported in House',
                          'Reported in Senate', 'Introduced in House', 'Introduced in Senate']
        
        selected_version = None
        
        # Try to find preferred version type
        for preferred_type in preferred_types:
            for version in versions:
                if version.get('type', '').strip() == preferred_type:
                    selected_version = version
                    logging.debug(f"Selected {preferred_type} version for {congress}-{bill_type}-{bill_number}")
                    break
            if selected_version:
                break
        
        # Fallback to first available version
        if not selected_version:
            selected_version = versions[0]
            logging.debug(f"Using fallback version: {selected_version.get('type', 'Unknown')} for {congress}-{bill_type}-{bill_number}")
        
        # Extract text content from selected version
        formats = selected_version.get('formats', [])
        logging.debug(f"Available formats: {[f.get('type') for f in formats]}")
        
        # Prefer 'Formatted Text' but try other text formats as fallback
        format_preferences = ['Formatted Text', 'Text', 'HTML']
        
        for preferred_format in format_preferences:
            for format_info in formats:
                if format_info.get('type') == preferred_format:
                    text_url = format_info.get('url')
                    if text_url:
                        try:
                            logging.debug(f"Fetching {preferred_format} from: {text_url}")
                            text_response = self.session.get(text_url, timeout=60)  # Increased timeout
                            if text_response.status_code == 200:
                                # Clean HTML tags but preserve structure
                                clean_text = re.sub(r'<[^>]*>', '', text_response.text)
                                # Remove excessive whitespace
                                clean_text = re.sub(r'\n\s*\n', '\n\n', clean_text)
                                clean_text = clean_text.strip()
                                
                                logging.info(f"Successfully fetched {len(clean_text):,} characters of {preferred_format} for {congress}-{bill_type}-{bill_number}")
                                return clean_text
                            else:
                                logging.warning(f"HTTP {text_response.status_code} for {text_url}")
                        except Exception as e:
                            logging.error(f"Error fetching {preferred_format} from {text_url}: {str(e)}")
                            continue
        
        logging.error(f"Failed to fetch text content for {congress}-{bill_type}-{bill_number}")
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

    def get_bills_by_date_range(self, start_date, end_date, max_bills=1000):
        """
        Get bills updated within a specific date range with pagination support.
        
        Args:
            start_date (datetime): Start date for the range
            end_date (datetime): End date for the range  
            max_bills (int): Maximum number of bills to fetch
            
        Returns:
            list: List of bill data dictionaries
        """
        bills = []
        offset = 0
        limit = min(250, max_bills)  # API maximum per request
        
        while len(bills) < max_bills:
            params = {
                'limit': limit,
                'offset': offset,
                'sort': 'updateDate+desc'
            }
            
            # Add date filters if the API supports them
            # Note: Congress API may not support direct date filtering in all endpoints
            # We'll filter by date after fetching
            
            endpoint = "/bill"
            data = self._make_request(endpoint, params)
            
            if not data or 'bills' not in data:
                logging.warning(f"No bills data received at offset {offset}")
                break
            
            bill_list = data['bills']
            if not bill_list:
                logging.info("No more bills to fetch")
                break
            
            # Filter bills by date range
            for bill_summary in bill_list:
                update_date_str = bill_summary.get('updateDate')
                if not update_date_str:
                    continue
                
                try:
                    update_date = datetime.fromisoformat(update_date_str.replace('Z', '+00:00'))
                    if start_date <= update_date.replace(tzinfo=None) <= end_date:
                        bills.append(bill_summary)
                        
                        if len(bills) >= max_bills:
                            logging.info(f"Reached maximum number of bills ({max_bills})")
                            break
                except Exception as e:
                    logging.error(f"Error parsing date {update_date_str}: {str(e)}")
                    continue
            
            # If we got fewer bills than the limit, we've reached the end
            if len(bill_list) < limit:
                break
            
            # If we've reached our target, stop paginating
            if len(bills) >= max_bills:
                break
            
            offset += limit
            
            # Add delay to respect rate limits
            time.sleep(self.min_request_interval)
        
        logging.info(f"Fetched {len(bills)} bills from {start_date} to {end_date}")
        return bills

    def get_bills_by_introduction_date(self, start_date, end_date, max_bills=1000):
        """
        Get bills introduced within a specific date range.
        This method focuses on introduction dates rather than update dates.
        """
        bills = []
        offset = 0
        limit = min(250, max_bills)
        
        while len(bills) < max_bills:
            params = {
                'limit': limit,
                'offset': offset,
                'sort': 'introducedDate+desc'
            }
            
            endpoint = "/bill"
            data = self._make_request(endpoint, params)
            
            if not data or 'bills' not in data:
                logging.warning(f"No bills data received at offset {offset}")
                break
            
            bill_list = data['bills']
            if not bill_list:
                logging.info("No more bills to fetch")
                break
            
            # Filter bills by introduction date
            for bill_summary in bill_list:
                introduced_date_str = bill_summary.get('introducedDate')
                if not introduced_date_str:
                    continue
                
                try:
                    introduced_date = datetime.fromisoformat(introduced_date_str.replace('Z', '+00:00'))
                    if start_date <= introduced_date.replace(tzinfo=None) <= end_date:
                        bills.append(bill_summary)
                        
                        if len(bills) >= max_bills:
                            logging.info(f"Reached maximum number of bills ({max_bills})")
                            break
                except Exception as e:
                    logging.error(f"Error parsing introduction date {introduced_date_str}: {str(e)}")
                    continue
            
            # If we got fewer bills than the limit, we've reached the end
            if len(bill_list) < limit:
                break
            
            # If we've reached our target, stop paginating
            if len(bills) >= max_bills:
                break
            
            offset += limit
            
            # Add delay to respect rate limits
            time.sleep(self.min_request_interval)
        
        logging.info(f"Fetched {len(bills)} bills introduced from {start_date} to {end_date}")
        return bills

if __name__ == "__main__":
    c = CongressAPI()
    bill = c.get_bill_by_number("H.J.Res.87")
    print(json.dumps(bill, indent= 2))