import re
import logging
from bs4 import BeautifulSoup

def clean_bill_text(raw_text):
    """
    Clean and normalize bill text from various formats (HTML, XML, plain text)
    """
    if not raw_text:
        return ""
    
    try:
        # If text contains HTML/XML tags, parse with BeautifulSoup
        if '<' in raw_text and '>' in raw_text:
            soup = BeautifulSoup(raw_text, 'html.parser')
            
            # Remove script and style elements
            for script in soup(["script", "style"]):
                script.decompose()
            
            # Get text content
            text = soup.get_text()
        else:
            text = raw_text
        
        # Clean up whitespace and formatting
        text = re.sub(r'\n\s*\n', '\n\n', text)  # Normalize paragraph breaks
        text = re.sub(r'[ \t]+', ' ', text)  # Normalize spaces
        text = text.strip()
        
        # Remove excessive whitespace
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        return text
        
    except Exception as e:
        logging.error(f"Error cleaning bill text: {str(e)}")
        return raw_text

def extract_sections(bill_text):
    """
    Extract sections from bill text for easier analysis
    Returns list of section texts
    """
    if not bill_text:
        return []
    
    try:
        sections = []
        
        # Common patterns for bill sections
        section_patterns = [
            r'SECTION\s+\d+\.',  # SECTION 1.
            r'SEC\.\s+\d+\.',    # SEC. 1.
            r'\(\w+\)',          # (a), (b), etc.
            r'\d+\.',            # 1., 2., etc.
        ]
        
        # Try to split by section markers
        for pattern in section_patterns:
            matches = list(re.finditer(pattern, bill_text, re.IGNORECASE))
            if len(matches) >= 2:  # Found multiple sections
                current_sections = []
                for i, match in enumerate(matches):
                    start = match.start()
                    end = matches[i + 1].start() if i + 1 < len(matches) else len(bill_text)
                    section_text = bill_text[start:end].strip()
                    if len(section_text) > 50:  # Ignore very short sections
                        current_sections.append(section_text)
                
                if current_sections:
                    sections = current_sections
                    break
        
        # If no clear sections found, split by paragraphs
        if not sections:
            paragraphs = bill_text.split('\n\n')
            sections = [p.strip() for p in paragraphs if len(p.strip()) > 100]
        
        # If still no sections, use the whole text as one section
        if not sections:
            sections = [bill_text]
        
        return sections[:20]  # Limit to first 20 sections
        
    except Exception as e:
        logging.error(f"Error extracting sections: {str(e)}")
        return [bill_text] if bill_text else []

def extract_funding_amounts(text):
    """
    Extract funding amounts and financial information from bill text
    """
    if not text:
        return []
    
    try:
        funding_amounts = []
        
        # Patterns for different currency formats
        currency_patterns = [
            r'\$[\d,]+(?:\.\d{2})?(?:\s*(?:million|billion|trillion))?',
            r'(?:USD?|dollars?)\s*[\d,]+(?:\.\d{2})?(?:\s*(?:million|billion|trillion))?',
            r'[\d,]+(?:\.\d{2})?\s*(?:million|billion|trillion)\s*dollars?'
        ]
        
        for pattern in currency_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                amount = match.group().strip()
                if amount not in funding_amounts:
                    funding_amounts.append(amount)
        
        return funding_amounts[:10]  # Limit results
        
    except Exception as e:
        logging.error(f"Error extracting funding amounts: {str(e)}")
        return []

def extract_dates(text):
    """
    Extract important dates from bill text
    """
    if not text:
        return []
    
    try:
        dates = []
        
        # Common date patterns
        date_patterns = [
            r'(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}',
            r'\d{1,2}/\d{1,2}/\d{4}',
            r'\d{4}-\d{2}-\d{2}',
            r'(?:effective|beginning|starting|ending)\s+(?:on\s+)?[\w\s,]+\d{4}'
        ]
        
        for pattern in date_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                date_text = match.group().strip()
                if date_text not in dates:
                    dates.append(date_text)
        
        return dates[:10]  # Limit results
        
    except Exception as e:
        logging.error(f"Error extracting dates: {str(e)}")
        return []

def extract_key_terms(text):
    """
    Extract key terms and phrases that might be important for analysis
    """
    if not text:
        return []
    
    try:
        key_terms = []
        
        # Patterns for important terms
        important_patterns = [
            r'(?:shall|must|required to|prohibited from|authorized to)\s+[\w\s]{10,50}',
            r'(?:establishment|creation|amendment|repeal)\s+of\s+[\w\s]{5,30}',
            r'(?:appropriat\w+|fund\w+|allocat\w+)\s+[\w\s]{5,30}',
            r'(?:subject to|in accordance with|pursuant to)\s+[\w\s]{5,30}'
        ]
        
        for pattern in important_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                term = match.group().strip()
                if len(term) > 10 and term not in key_terms:
                    key_terms.append(term)
        
        return key_terms[:15]  # Limit results
        
    except Exception as e:
        logging.error(f"Error extracting key terms: {str(e)}")
        return []

def summarize_text(text, max_length=500):
    """
    Create a basic summary of text by extracting key sentences
    """
    if not text or len(text) <= max_length:
        return text
    
    try:
        # Split into sentences
        sentences = re.split(r'[.!?]+', text)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 20]
        
        if not sentences:
            return text[:max_length] + "..."
        
        # Take first few sentences up to max_length
        summary = ""
        for sentence in sentences:
            if len(summary + sentence) > max_length:
                break
            summary += sentence + ". "
        
        return summary.strip()
        
    except Exception as e:
        logging.error(f"Error summarizing text: {str(e)}")
        return text[:max_length] + "..."
