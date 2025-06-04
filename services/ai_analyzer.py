import json
import os
import logging
from typing import Dict, List, Optional
from openai import OpenAI


class AIAnalyzer:
    """AI-powered legislative analysis using OpenAI"""
    
    def __init__(self):
        self.api_key = os.environ.get('OPENAI_API_KEY')
        if not self.api_key:
            logging.warning("OpenAI API key not found. AI analysis will be disabled.")
            self.client = None
        else:
            self.client = OpenAI(api_key=self.api_key)
    
    def analyze_bill(self, bill) -> Dict:
        """Perform comprehensive AI analysis of a bill"""
        if not self.client:
            logging.warning("OpenAI client not available")
            return {}
        
        try:
            # Prepare bill text for analysis
            text_to_analyze = self._prepare_bill_text(bill)
            
            if not text_to_analyze:
                logging.warning(f"No text available for bill {bill.get_bill_identifier()}")
                return {}
            
            # Perform different types of analysis
            analysis_results = {}
            
            # 1. Policy categorization
            categories = self._categorize_bill(text_to_analyze, bill.title)
            if categories:
                bill.set_policy_categories(categories)
                analysis_results['categories'] = categories
            
            # 2. Stakeholder analysis
            stakeholders = self._analyze_stakeholders(text_to_analyze, bill.title)
            if stakeholders:
                bill.set_stakeholder_analysis(stakeholders)
                analysis_results['stakeholders'] = stakeholders
            
            # 3. Complexity scoring
            complexity = self._assess_complexity(text_to_analyze)
            if complexity is not None:
                bill.complexity_score = complexity
                analysis_results['complexity'] = complexity
            
            # 4. Controversy detection
            controversy = self._detect_controversy(text_to_analyze, bill.title)
            if controversy is not None:
                bill.controversy_score = controversy
                analysis_results['controversy'] = controversy
            
            return analysis_results
            
        except Exception as e:
            logging.error(f"AI analysis error for bill {bill.get_bill_identifier()}: {str(e)}")
            return {}
    
    def _prepare_bill_text(self, bill) -> str:
        """Prepare bill text for AI analysis"""
        # Combine available text sources
        text_parts = []
        
        if bill.title:
            text_parts.append(f"Title: {bill.title}")
        
        if bill.summary:
            text_parts.append(f"Summary: {bill.summary}")
        
        if bill.full_text:
            # Limit text length for API efficiency
            full_text = bill.full_text[:10000]  # Limit to first 10k characters
            text_parts.append(f"Full Text: {full_text}")
        
        return "\n\n".join(text_parts)
    
    def _categorize_bill(self, bill_text: str, title: str) -> Optional[Dict]:
        """Categorize bill into policy domains with confidence scores"""
        try:
            # the newest OpenAI model is "gpt-4o" which was released May 13, 2024.
            # do not change this unless explicitly requested by the user
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": """You are an expert policy analyst. Categorize the given bill into policy domains and assign confidence scores.
                        
Available categories: Healthcare, Environment, Economy, Education, Defense, Immigration, Technology, Agriculture, Transportation, Energy, Justice, Social Services, Tax Policy, Trade, Civil Rights.

Return JSON with categories as keys and confidence scores (0-100) as values. Only include categories with confidence > 20."""
                    },
                    {
                        "role": "user",
                        "content": f"Title: {title}\n\nBill Text:\n{bill_text[:3000]}"
                    }
                ],
                response_format={"type": "json_object"},
                temperature=0.3
            )
            
            result = json.loads(response.choices[0].message.content)
            
            # Validate and normalize scores
            normalized_result = {}
            for category, score in result.items():
                if isinstance(score, (int, float)) and 0 <= score <= 100:
                    normalized_result[category] = float(score)
            
            return normalized_result if normalized_result else None
            
        except Exception as e:
            logging.error(f"Policy categorization error: {str(e)}")
            return None
    
    def _analyze_stakeholders(self, bill_text: str, title: str) -> Optional[Dict]:
        """Identify stakeholders affected by the bill"""
        try:
            # the newest OpenAI model is "gpt-4o" which was released May 13, 2024.
            # do not change this unless explicitly requested by the user
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": """You are an expert policy analyst. Identify stakeholder groups affected by this bill and assess the impact.

Return JSON with this structure:
{
    "winners": ["group1", "group2"],
    "losers": ["group3", "group4"],
    "neutral": ["group5"],
    "impacts": {
        "group1": "positive impact description",
        "group3": "negative impact description"
    }
}

Focus on major stakeholder groups like: businesses, consumers, workers, taxpayers, government agencies, nonprofits, specific industries, etc."""
                    },
                    {
                        "role": "user",
                        "content": f"Title: {title}\n\nBill Text:\n{bill_text[:3000]}"
                    }
                ],
                response_format={"type": "json_object"},
                temperature=0.3
            )
            
            result = json.loads(response.choices[0].message.content)
            return result
            
        except Exception as e:
            logging.error(f"Stakeholder analysis error: {str(e)}")
            return None
    
    def _assess_complexity(self, bill_text: str) -> Optional[float]:
        """Assess bill complexity on a 0-1 scale"""
        try:
            # Simple heuristics for complexity
            text_length = len(bill_text)
            word_count = len(bill_text.split())
            
            # Count technical terms and complex structures
            technical_indicators = [
                'subsection', 'paragraph', 'subparagraph', 'clause',
                'amended', 'modified', 'repealed', 'inserted',
                'notwithstanding', 'pursuant to', 'except as provided',
                'CFR', 'USC', 'Public Law'
            ]
            
            technical_count = sum(bill_text.lower().count(term) for term in technical_indicators)
            
            # Simple complexity formula
            length_score = min(text_length / 50000, 1.0)  # Normalize by 50k chars
            technical_score = min(technical_count / 50, 1.0)  # Normalize by 50 terms
            
            complexity = (length_score * 0.4 + technical_score * 0.6)
            
            return max(0.0, min(1.0, complexity))
            
        except Exception as e:
            logging.error(f"Complexity assessment error: {str(e)}")
            return None
    
    def _detect_controversy(self, bill_text: str, title: str) -> Optional[float]:
        """Detect potentially controversial provisions"""
        try:
            # Keywords that often indicate controversial content
            controversial_terms = [
                'abortion', 'gun', 'firearm', 'immigration', 'border wall',
                'climate change', 'tax increase', 'regulation', 'mandate',
                'surveillance', 'privacy', 'discrimination', 'religious freedom',
                'healthcare', 'medicare', 'social security', 'welfare'
            ]
            
            text_lower = bill_text.lower()
            title_lower = title.lower()
            
            controversy_count = 0
            for term in controversial_terms:
                if term in text_lower or term in title_lower:
                    controversy_count += 1
            
            # Normalize controversy score
            controversy_score = min(controversy_count / 10.0, 1.0)
            
            return controversy_score
            
        except Exception as e:
            logging.error(f"Controversy detection error: {str(e)}")
            return None
    
    def calculate_alignment_score(self, user_preferences: Dict, bill_categories: Dict) -> float:
        """Calculate alignment between user preferences and bill categories"""
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
            logging.error(f"Alignment calculation error: {str(e)}")
            return 0.0
    
    def generate_bill_summary(self, bill_text: str, title: str) -> Optional[str]:
        """Generate a plain-language summary of the bill"""
        try:
            # the newest OpenAI model is "gpt-4o" which was released May 13, 2024.
            # do not change this unless explicitly requested by the user
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": """You are an expert at explaining complex legislation in plain language. 
                        Create a clear, concise summary that explains:
                        1. What the bill does
                        2. Who it affects
                        3. Key provisions
                        4. Potential impacts
                        
                        Write for a general audience without legal jargon."""
                    },
                    {
                        "role": "user",
                        "content": f"Title: {title}\n\nBill Text:\n{bill_text[:4000]}"
                    }
                ],
                temperature=0.4,
                max_tokens=500
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            logging.error(f"Summary generation error: {str(e)}")
            return None
