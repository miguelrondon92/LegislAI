import os
import requests
import logging
from datetime import datetime
from typing import Dict, List, Optional
import time
from urllib.parse import quote

logger = logging.getLogger(__name__)

class CongressAPI:
    """Client for interacting with the Congress.gov API"""
    
    def __init__(self):
        self.api_key = os.environ.get("CONGRESS_API_KEY")
        self.base_url = "https://api.congress.gov/v3"
        self.session = requests.Session()
        
        # Set required headers
        if self.api_key:
            self.session.headers.update({
                'X-API-Key': self.api_key,
                'User-Agent': 'Legislative-Analysis-Platform/1.0 (contact@example.com)'
            })
        else:
            logger.warning("CONGRESS_API_KEY not found in environment variables")
        
        # Rate limiting
        self.last_request_time = 0
        self.min_request_interval = 1.0  # Minimum seconds between requests
    
    def _rate_limit(self):
        """Implement basic rate limiting"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        if time_since_last < self.min_request_interval:
            time.sleep(self.min_request_interval - time_since_last)
        self.last_request_time = time.time()
    
    def _make_request(self, endpoint: str, params: Dict = None) -> Optional[Dict]:
        """Make a request to the Congress API with error handling"""
        self._rate_limit()
        
        url = f"{self.base_url}/{endpoint}"
        
        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed: {e}")
            return None
    
    def search_bills(self, query: str = "", congress: int = 118, limit: int = 20, 
                    bill_type: str = None, status: str = None) -> List[Dict]:
        """Search for bills with optional filters"""
        params = {
            'format': 'json',
            'limit': limit
        }
        
        if query:
            params['q'] = query
        
        endpoint = f"bill/{congress}"
        
        # Add filters if provided
        if bill_type:
            endpoint += f"/{bill_type.lower()}"
        
        response = self._make_request(endpoint, params)
        if response and 'bills' in response:
            return response['bills']
        return []
    
    def get_bill_details(self, congress: int, bill_type: str, bill_number: int) -> Optional[Dict]:
        """Get detailed information about a specific bill"""
        endpoint = f"bill/{congress}/{bill_type.lower()}/{bill_number}"
        
        response = self._make_request(endpoint, {'format': 'json'})
        if response and 'bill' in response:
            return response['bill']
        return None
    
    def get_bill_text(self, congress: int, bill_type: str, bill_number: int) -> Optional[Dict]:
        """Get the full text of a bill"""
        endpoint = f"bill/{congress}/{bill_type.lower()}/{bill_number}/text"
        
        response = self._make_request(endpoint, {'format': 'json'})
        if response and 'textVersions' in response:
            return response['textVersions']
        return None
    
    def get_bill_actions(self, congress: int, bill_type: str, bill_number: int) -> List[Dict]:
        """Get actions taken on a bill"""
        endpoint = f"bill/{congress}/{bill_type.lower()}/{bill_number}/actions"
        
        response = self._make_request(endpoint, {'format': 'json'})
        if response and 'actions' in response:
            return response['actions']
        return []
    
    def get_bill_amendments(self, congress: int, bill_type: str, bill_number: int) -> List[Dict]:
        """Get amendments to a bill"""
        endpoint = f"bill/{congress}/{bill_type.lower()}/{bill_number}/amendments"
        
        response = self._make_request(endpoint, {'format': 'json'})
        if response and 'amendments' in response:
            return response['amendments']
        return []
    
    def get_recent_bills(self, congress: int = 118, limit: int = 20) -> List[Dict]:
        """Get recently introduced bills"""
        params = {
            'format': 'json',
            'limit': limit,
            'sort': 'updateDate+desc'
        }
        
        endpoint = f"bill/{congress}"
        
        response = self._make_request(endpoint, params)
        if response and 'bills' in response:
            return response['bills']
        return []
    
    def get_members(self, congress: int = 118, chamber: str = None) -> List[Dict]:
        """Get information about congress members"""
        params = {'format': 'json'}
        
        endpoint = f"member/{congress}"
        if chamber:
            endpoint += f"/{chamber.lower()}"
        
        response = self._make_request(endpoint, params)
        if response and 'members' in response:
            return response['members']
        return []
    
    def get_committees(self, congress: int = 118, chamber: str = None) -> List[Dict]:
        """Get committee information"""
        params = {'format': 'json'}
        
        endpoint = f"committee/{congress}"
        if chamber:
            endpoint += f"/{chamber.lower()}"
        
        response = self._make_request(endpoint, params)
        if response and 'committees' in response:
            return response['committees']
        return []
    
    def parse_bill_identifier(self, bill_id: str) -> Optional[tuple]:
        """Parse a bill identifier like 'HR1234' or '118hr1234' into components"""
        bill_id = bill_id.upper().strip()
        
        # Try format like '118HR1234'
        if len(bill_id) > 5 and bill_id[:3].isdigit():
            congress = int(bill_id[:3])
            remainder = bill_id[3:]
        else:
            congress = 118  # Default to current congress
            remainder = bill_id
        
        # Extract bill type and number
        bill_types = ['HR', 'S', 'HJRES', 'SJRES', 'HCONRES', 'SCONRES', 'HRES', 'SRES']
        
        for bill_type in bill_types:
            if remainder.startswith(bill_type):
                number_str = remainder[len(bill_type):].lstrip('0')
                if number_str.isdigit():
                    return (congress, bill_type.lower(), int(number_str))
        
        return None

# Global instance
congress_api = CongressAPI()
