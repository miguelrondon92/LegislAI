import re
from typing import Dict, List, Optional
from datetime import datetime, timedelta


def calculate_alignment_score(user_preferences: Dict, bill_categories: Dict) -> float:
    """Calculate alignment score between user preferences and bill categories"""
    try:
        if not user_preferences or not bill_categories:
            return 0.0
        
        total_score = 0.0
        total_weight = 0.0
        
        # Calculate weighted alignment
        for category, bill_confidence in bill_categories.items():
            if category in user_preferences:
                user_preference = user_preferences[category]  # -100 to +100
                
                # Convert bill confidence (0-100) to weight
                weight = bill_confidence / 100.0
                
                # Calculate alignment contribution
                alignment_contribution = (user_preference / 100.0) * weight * 100
                
                total_score += alignment_contribution
                total_weight += weight
        
        # Normalize by total weight
        if total_weight > 0:
            final_score = total_score / total_weight
            return max(-100.0, min(100.0, final_score))
        
        return 0.0
        
    except Exception as e:
        return 0.0


def format_currency(amount) -> str:
    """Format currency amounts with appropriate suffixes"""
    try:
        if not amount:
            return "$0"
        
        amount = float(amount)
        
        if amount >= 1e12:
            return f"${amount/1e12:.1f}T"
        elif amount >= 1e9:
            return f"${amount/1e9:.1f}B"
        elif amount >= 1e6:
            return f"${amount/1e6:.1f}M"
        elif amount >= 1e3:
            return f"${amount/1e3:.1f}K"
        else:
            return f"${amount:.0f}"
            
    except:
        return str(amount)


def get_bill_status_color(status: str) -> str:
    """Get Bootstrap color class for bill status"""
    status_colors = {
        'Introduced': 'primary',
        'In Committee': 'info',
        'Passed': 'success',
        'Signed into Law': 'success',
        'Vetoed': 'danger',
        'Active': 'warning',
        'Unknown': 'secondary'
    }
    return status_colors.get(status, 'secondary')


def get_alignment_color(score: float) -> str:
    """Get color class for alignment score"""
    if score > 50:
        return 'success'
    elif score > 20:
        return 'info'
    elif score > -20:
        return 'warning'
    elif score > -50:
        return 'danger'
    else:
        return 'dark'


def get_alignment_text(score: float) -> str:
    """Get descriptive text for alignment score"""
    if score > 70:
        return 'Strong Alignment'
    elif score > 30:
        return 'Good Alignment'
    elif score > 10:
        return 'Slight Alignment'
    elif score > -10:
        return 'Neutral'
    elif score > -30:
        return 'Slight Conflict'
    elif score > -70:
        return 'Strong Conflict'
    else:
        return 'Major Conflict'


def truncate_text(text: str, max_length: int = 200) -> str:
    """Truncate text to specified length with ellipsis"""
    if not text:
        return ""
    
    if len(text) <= max_length:
        return text
    
    # Try to break at a word boundary
    truncated = text[:max_length]
    last_space = truncated.rfind(' ')
    
    if last_space > max_length * 0.8:  # If we can break near the end
        return truncated[:last_space] + "..."
    else:
        return truncated + "..."


def extract_bill_funding(bill_text: str) -> List[Dict]:
    """Extract funding information from bill text"""
    try:
        if not bill_text:
            return []
        
        # Patterns to match funding amounts
        patterns = [
            r'\$([0-9,]+(?:\.[0-9]+)?)\s*(billion|million|thousand)?',
            r'([0-9,]+(?:\.[0-9]+)?)\s*dollars?',
            r'appropriated\s+\$?([0-9,]+(?:\.[0-9]+)?)',
            r'authorized\s+\$?([0-9,]+(?:\.[0-9]+)?)'
        ]
        
        funding_items = []
        
        for pattern in patterns:
            matches = re.finditer(pattern, bill_text, re.IGNORECASE)
            for match in matches:
                amount_str = match.group(1).replace(',', '')
                try:
                    amount = float(amount_str)
                    
                    # Apply multiplier if present
                    if len(match.groups()) > 1 and match.group(2):
                        multiplier_text = match.group(2).lower()
                        if 'billion' in multiplier_text:
                            amount *= 1e9
                        elif 'million' in multiplier_text:
                            amount *= 1e6
                        elif 'thousand' in multiplier_text:
                            amount *= 1e3
                    
                    # Extract context around the match
                    start = max(0, match.start() - 100)
                    end = min(len(bill_text), match.end() + 100)
                    context = bill_text[start:end].strip()
                    
                    funding_items.append({
                        'amount': amount,
                        'context': context,
                        'formatted_amount': format_currency(amount)
                    })
                    
                except ValueError:
                    continue
        
        # Sort by amount descending and remove duplicates
        funding_items.sort(key=lambda x: x['amount'], reverse=True)
        
        # Remove near-duplicates (same amount)
        unique_items = []
        for item in funding_items:
            if not any(abs(item['amount'] - existing['amount']) < item['amount'] * 0.01 
                      for existing in unique_items):
                unique_items.append(item)
        
        return unique_items[:10]  # Return top 10
        
    except Exception as e:
        return []


def get_priority_level(alignment_score: float) -> str:
    """Get priority level based on alignment score"""
    abs_score = abs(alignment_score)
    
    if abs_score > 80:
        return 'critical'
    elif abs_score > 60:
        return 'high'
    elif abs_score > 30:
        return 'medium'
    else:
        return 'low'


def format_date_relative(date_obj: datetime) -> str:
    """Format date as relative time (e.g., '2 days ago')"""
    try:
        if not date_obj:
            return "Unknown"
        
        now = datetime.utcnow()
        diff = now - date_obj
        
        if diff.days > 365:
            years = diff.days // 365
            return f"{years} year{'s' if years != 1 else ''} ago"
        elif diff.days > 30:
            months = diff.days // 30
            return f"{months} month{'s' if months != 1 else ''} ago"
        elif diff.days > 0:
            return f"{diff.days} day{'s' if diff.days != 1 else ''} ago"
        elif diff.seconds > 3600:
            hours = diff.seconds // 3600
            return f"{hours} hour{'s' if hours != 1 else ''} ago"
        elif diff.seconds > 60:
            minutes = diff.seconds // 60
            return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
        else:
            return "Just now"
            
    except:
        return str(date_obj.strftime('%Y-%m-%d') if date_obj else "Unknown")


def clean_bill_identifier(identifier: str) -> str:
    """Clean and standardize bill identifier"""
    try:
        if not identifier:
            return ""
        
        # Remove extra spaces and convert to uppercase
        clean_id = identifier.strip().upper()
        
        # Add hyphen if missing (e.g., "HR1234" -> "HR-1234")
        if re.match(r'^[A-Z]+\d+$', clean_id):
            match = re.match(r'^([A-Z]+)(\d+)$', clean_id)
            if match:
                clean_id = f"{match.group(1)}-{match.group(2)}"
        
        return clean_id
        
    except:
        return identifier


def extract_keywords(text: str, max_keywords: int = 10) -> List[str]:
    """Extract key terms from bill text"""
    try:
        if not text:
            return []
        
        # Common stop words to ignore
        stop_words = {
            'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with',
            'by', 'from', 'up', 'about', 'into', 'through', 'during', 'before',
            'after', 'above', 'below', 'between', 'among', 'this', 'that', 'these',
            'those', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have',
            'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should',
            'may', 'might', 'must', 'shall', 'can', 'a', 'an', 'as', 'if', 'each',
            'section', 'subsection', 'paragraph', 'act', 'bill', 'law', 'code'
        }
        
        # Extract words (3+ characters, alphanumeric)
        words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
        
        # Count word frequencies
        word_counts = {}
        for word in words:
            if word not in stop_words:
                word_counts[word] = word_counts.get(word, 0) + 1
        
        # Sort by frequency and return top keywords
        sorted_words = sorted(word_counts.items(), key=lambda x: x[1], reverse=True)
        
        return [word for word, count in sorted_words[:max_keywords]]
        
    except:
        return []
