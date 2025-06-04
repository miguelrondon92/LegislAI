import re
from datetime import datetime
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

def parse_congress_date(date_str: str) -> Optional[datetime]:
    """Parse various date formats from Congress API"""
    if not date_str:
        return None
    
    # Common formats from Congress API
    formats = [
        "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S",
        "%m/%d/%Y"
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    
    logger.warning(f"Could not parse date: {date_str}")
    return None

def extract_bill_number_from_title(title: str) -> Optional[str]:
    """Extract bill number from title like 'H.R.1234 - Some Bill Title'"""
    match = re.search(r'([HS]\.?(?:R\.?|RES\.?|CON\.?RES\.?|J\.?RES\.?)\s*\d+)', title, re.IGNORECASE)
    if match:
        return match.group(1).replace('.', '').replace(' ', '').upper()
    return None

def format_bill_number(bill_type: str, bill_number: int) -> str:
    """Format bill type and number into standard display format"""
    bill_type = bill_type.upper()
    
    format_map = {
        'HR': f'H.R. {bill_number}',
        'S': f'S. {bill_number}',
        'HJRES': f'H.J.Res. {bill_number}',
        'SJRES': f'S.J.Res. {bill_number}',
        'HCONRES': f'H.Con.Res. {bill_number}',
        'SCONRES': f'S.Con.Res. {bill_number}',
        'HRES': f'H.Res. {bill_number}',
        'SRES': f'S.Res. {bill_number}'
    }
    
    return format_map.get(bill_type, f'{bill_type} {bill_number}')

def calculate_alignment_color(score: float) -> str:
    """Return CSS color class based on alignment score"""
    if score >= 70:
        return 'text-success'
    elif score >= 30:
        return 'text-warning'
    elif score >= -30:
        return 'text-secondary'
    else:
        return 'text-danger'

def get_policy_category_defaults() -> Dict[str, int]:
    """Get default policy preferences (all neutral at 50)"""
    categories = [
        "Healthcare", "Environment", "Economy", "Education", "Defense",
        "Immigration", "Technology", "Civil Rights", "Agriculture", "Energy",
        "Transportation", "Housing", "Tax Policy", "Social Security", "Labor",
        "Trade", "Foreign Relations", "Criminal Justice", "Veterans Affairs", "Budget"
    ]
    return {category: 50 for category in categories}

def truncate_text(text: str, max_length: int = 200) -> str:
    """Truncate text to specified length with ellipsis"""
    if len(text) <= max_length:
        return text
    return text[:max_length].rsplit(' ', 1)[0] + '...'

def format_currency(amount: str) -> str:
    """Format currency amounts from bill text"""
    # Simple regex to find dollar amounts
    pattern = r'\$[\d,]+(?:\.\d{2})?(?:\s*(?:million|billion|trillion))?'
    matches = re.findall(pattern, amount, re.IGNORECASE)
    return matches

def clean_bill_text(text: str) -> str:
    """Clean and normalize bill text for analysis"""
    if not text:
        return ""
    
    # Remove excessive whitespace
    text = re.sub(r'\s+', ' ', text)
    
    # Remove common XML/HTML artifacts
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'&[a-zA-Z]+;', ' ', text)
    
    # Remove page numbers and other artifacts
    text = re.sub(r'\n\s*\d+\s*\n', '\n', text)
    text = re.sub(r'\n\s*Page \d+\s*\n', '\n', text)
    
    return text.strip()

def get_priority_level(score: float, threshold_high: float = 80, threshold_medium: float = 40) -> str:
    """Determine priority level based on alignment score"""
    abs_score = abs(score)
    if abs_score >= threshold_high:
        return 'high'
    elif abs_score >= threshold_medium:
        return 'medium'
    else:
        return 'low'

def format_status_badge(status: str) -> str:
    """Return Bootstrap badge class for bill status"""
    status_lower = status.lower() if status else ""
    
    if 'passed' in status_lower or 'enacted' in status_lower:
        return 'badge bg-success'
    elif 'introduced' in status_lower:
        return 'badge bg-primary'
    elif 'committee' in status_lower:
        return 'badge bg-warning'
    elif 'failed' in status_lower or 'died' in status_lower:
        return 'badge bg-danger'
    else:
        return 'badge bg-secondary'

def extract_funding_amounts(text: str) -> List[str]:
    """Extract funding amounts from bill text"""
    # Pattern to match various funding formats
    patterns = [
        r'\$[\d,]+(?:\.\d{2})?\s*(?:million|billion|trillion)',
        r'appropriated?\s+\$[\d,]+(?:\.\d{2})?',
        r'funding\s+of\s+\$[\d,]+(?:\.\d{2})?',
        r'budget\s+of\s+\$[\d,]+(?:\.\d{2})?'
    ]
    
    amounts = []
    for pattern in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        amounts.extend(matches)
    
    return list(set(amounts))  # Remove duplicates

def validate_email(email: str) -> bool:
    """Simple email validation"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))

def get_readable_date(date_obj: datetime) -> str:
    """Format datetime object for display"""
    if not date_obj:
        return "Unknown"
    return date_obj.strftime("%B %d, %Y")
