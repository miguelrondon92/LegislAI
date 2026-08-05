import requests
import os
import time
import logging
import threading
from datetime import datetime, timedelta
from urllib.parse import urlencode
import json
import re

class APIRateLimitError(Exception):
    """Exception raised when Congress API rate limit is exceeded"""
    pass

CURRENT_CONGRESS = 119

_shared_congress_api = None
_shared_congress_lock = threading.Lock()


def get_shared_congress_api():
    """Process-wide CongressAPI so rate-limit spacing is shared across callers."""
    global _shared_congress_api
    with _shared_congress_lock:
        if _shared_congress_api is None:
            _shared_congress_api = CongressAPI()
        return _shared_congress_api


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
    
    def _make_request(self, endpoint, params=None, max_retries=3):
        """Make a rate-limited request to the Congress API with retry logic"""
        # Implement rate limiting
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        if time_since_last < self.min_request_interval:
            time.sleep(self.min_request_interval - time_since_last)
        
        url = f"{self.base_url}{endpoint}"
        if params:
            url += "?" + urlencode(params)
        
        for attempt in range(max_retries):
            try:
                self.last_request_time = time.time()
                response = self.session.get(url, timeout=30)
                
                # Handle rate limiting specifically
                if response.status_code == 429:
                    wait_time = 2 ** attempt  # Exponential backoff
                    if attempt < max_retries - 1:
                        logging.warning(f"Congress API rate limited (429), retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})")
                        time.sleep(wait_time)
                        continue
                    else:
                        logging.error(f"Congress API rate limit exceeded after {max_retries} attempts")
                        raise APIRateLimitError("Congress API rate limit exceeded. Please try again later.")
                
                response.raise_for_status()
                return response.json()
            except requests.exceptions.ConnectionError as e:
                if "Connection reset by peer" in str(e) or "Connection aborted" in str(e):
                    if attempt < max_retries - 1:
                        wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                        logging.warning(f"Congress API connection reset, retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})")
                        time.sleep(wait_time)
                        continue
                    else:
                        logging.error(f"Congress API connection failed after {max_retries} attempts: {str(e)}")
                        return None
                else:
                    logging.error(f"Congress API connection error: {str(e)}")
                    return None
            except requests.exceptions.Timeout as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    logging.warning(f"Congress API timeout, retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                    continue
                else:
                    logging.error(f"Congress API timeout after {max_retries} attempts: {str(e)}")
                    return None
            except requests.exceptions.HTTPError as e:
                if e.response and e.response.status_code == 429:
                    # This shouldn't happen now since we handle 429 above, but just in case
                    logging.error(f"Congress API rate limit exceeded: {str(e)}")
                    raise APIRateLimitError("Congress API rate limit exceeded. Please try again later.")
                logging.error(f"Congress API HTTP error: {str(e)}")
                return None
            except requests.exceptions.RequestException as e:
                logging.error(f"Congress API request failed: {str(e)}")
                return None
        
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
        """Get the full text of a bill with enhanced version selection and exhaustive retry logic"""
        bill_id = f"{congress}-{bill_type}-{bill_number}"
        
        endpoint = f"/bill/{congress}/{bill_type}/{bill_number}/text"
        text_data = self._make_request(endpoint)
        
        if not text_data or 'textVersions' not in text_data:
            logging.warning(f"No text versions available for {bill_id}")
            return None
        
        versions = text_data['textVersions']
        if not versions:
            logging.warning(f"Empty text versions for {bill_id}")
            return None
        
        logging.debug(f"Found {len(versions)} text versions for {bill_id}")
        
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
                    logging.debug(f"Selected {preferred_type} version for {bill_id}")
                    break
            if selected_version:
                break
        
        # Fallback to first available version
        if not selected_version:
            selected_version = versions[0]
            logging.debug(f"Using fallback version: {selected_version.get('type', 'Unknown')} for {bill_id}")
        
        # Extract text content from selected version with exhaustive retry
        formats = selected_version.get('formats', [])
        logging.debug(f"Available formats: {[f.get('type') for f in formats]}")
        
        # Try ALL available formats, not just preferred ones
        format_preferences = ['Formatted Text', 'Text', 'HTML', 'XML', 'PDF']
        
        # First try preferred formats
        for preferred_format in format_preferences:
            success = self._try_fetch_format(formats, preferred_format, bill_id)
            if success:
                return success
        
        # If preferred formats fail, try ALL available formats
        logging.warning(f"Preferred formats failed for {bill_id}, trying all available formats")
        for format_info in formats:
            format_type = format_info.get('type', 'Unknown')
            if format_type not in format_preferences:  # Try formats we haven't tried yet
                success = self._try_fetch_single_format(format_info, format_type, bill_id)
                if success:
                    return success
        
        logging.error(f"EXHAUSTED ALL OPTIONS: Failed to fetch text content for {bill_id} after trying all {len(formats)} available formats")
        logging.error(f"Available formats were: {[f.get('type') for f in formats]}")
        return None
    
    def _try_fetch_format(self, formats, preferred_format, bill_id):
        """Try to fetch a specific format type with retries"""
        for format_info in formats:
            if format_info.get('type') == preferred_format:
                return self._try_fetch_single_format(format_info, preferred_format, bill_id)
        return None
    
    def _try_fetch_single_format(self, format_info, format_type, bill_id):
        """Try to fetch from a single format with comprehensive error handling"""
        text_url = format_info.get('url')
        if not text_url:
            logging.debug(f"No URL for {format_type} format for {bill_id}")
            return None
        
        max_retries = 3
        timeouts = [30, 60, 120]  # Progressive timeout increases
        
        for attempt in range(max_retries):
            try:
                timeout = timeouts[min(attempt, len(timeouts)-1)]
                logging.debug(f"Fetching {format_type} from: {text_url} (attempt {attempt+1}/{max_retries}, timeout={timeout}s)")
                
                text_response = self.session.get(text_url, timeout=timeout)
                
                if text_response.status_code == 200:
                    # Handle different content types
                    content_type = text_response.headers.get('content-type', '').lower()
                    
                    if 'pdf' in content_type:
                        logging.warning(f"PDF format not supported for text extraction for {bill_id}")
                        continue
                    
                    # Clean and process text content
                    raw_text = text_response.text
                    if not raw_text or len(raw_text.strip()) < 100:  # Minimal content check
                        logging.warning(f"Insufficient content in {format_type} for {bill_id} (only {len(raw_text)} chars)")
                        continue
                    
                    # Clean HTML tags but preserve structure
                    clean_text = re.sub(r'<[^>]*>', '', raw_text)
                    # Remove excessive whitespace
                    clean_text = re.sub(r'\n\s*\n', '\n\n', clean_text)
                    clean_text = clean_text.strip()
                    
                    if len(clean_text) > 100:  # Final sanity check
                        logging.info(f"Successfully fetched {len(clean_text):,} characters of {format_type} for {bill_id}")
                        return clean_text
                    else:
                        logging.warning(f"Cleaned content too short for {bill_id} ({len(clean_text)} chars)")
                        
                elif text_response.status_code == 404:
                    logging.warning(f"Format {format_type} not found (404) for {bill_id}")
                    break  # Don't retry 404s
                elif text_response.status_code in [429, 503]:
                    wait_time = 2 ** attempt  # Exponential backoff
                    logging.warning(f"Rate limited/service unavailable ({text_response.status_code}) for {bill_id}, waiting {wait_time}s")
                    time.sleep(wait_time)
                    continue
                else:
                    logging.warning(f"HTTP {text_response.status_code} for {format_type} at {text_url}")
                    
            except requests.exceptions.Timeout:
                logging.warning(f"Timeout ({timeout}s) fetching {format_type} for {bill_id} (attempt {attempt+1}/{max_retries})")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)  # Wait before retry
                    continue
            except requests.exceptions.ConnectionError as e:
                logging.warning(f"Connection error fetching {format_type} for {bill_id}: {str(e)} (attempt {attempt+1}/{max_retries})")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
            except Exception as e:
                logging.error(f"Unexpected error fetching {format_type} for {bill_id}: {str(e)} (attempt {attempt+1}/{max_retries})")
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue
        
        logging.warning(f"Failed to fetch {format_type} for {bill_id} after {max_retries} attempts")
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