import json
import os
import logging
from typing import Dict, List, Optional, Tuple
from google import genai
from openai import OpenAI
import re
from datetime import datetime
from utils.constants import FEDERAL_POLICY_CATEGORIES
#from .notification_service import NotificationService

logger = logging.getLogger(__name__)

class AIAnalyzer:
    """AI-powered legislative analysis using Gemini"""
    
    def __init__(self):
        self.api_key = os.environ.get('GEMENI_API_KEY')
        if not self.api_key:
            logging.warning("Gemini API key not found. AI analysis will be disabled.")
            self.client = None
        else:
            self.client = genai.Client(api_key=self.api_key)
        #self.notification_service = NotificationService()
        
        # Use the standardized federal policy categories
        self.policy_categories = FEDERAL_POLICY_CATEGORIES
    
    def analyze_bill(self, bill) -> Dict:
        """Perform comprehensive AI analysis of a bill"""
        if not self.client:
            logging.warning("Gemini client not available")
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
                analysis_results['policy_implications'] = categories
            
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
            
            # 5. Generate summary
            summary = self.generate_bill_summary(text_to_analyze, bill.title)
            if summary:
                analysis_results['summary'] = summary
            
            # Store the complete analysis
            bill.set_ai_analysis(analysis_results)
            
            # Trigger notifications for this bill
            # self.notification_service.process_new_bill_analysis(bill.id)
            
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
            full_text = bill.full_text#[:10000]  # Limit to first 10k characters
            text_parts.append(f"Full Text: {full_text}")
        
        return "\n\n".join(text_parts)
    
    def _categorize_bill(self, bill_text: str, title: str) -> Optional[Dict]:
        """Categorize bill into policy domains with confidence scores"""
        try:
            categories_list = ', '.join(self.policy_categories)
            prompt = f"""
            Analyze the policy implications of this congressional bill.
            
            Bill Title: {title}
            Bill Text: {bill_text[:3000]}
            
            Categorize this bill and analyze its policy implications. Use ONLY the following categories for all policy area fields:
            {categories_list}
            
            Respond in JSON format:
            {{
                "primary_policy_area": "The main policy area (must be one of the provided categories)",
                "secondary_areas": ["list", "of", "secondary", "policy", "areas"],
                "categories": [
                    {{
                        "area": "policy area name (must be one of the provided categories)",
                        "impact_level": "low/medium/high",
                        "description": "How this bill affects this area"
                    }}
                ],
                "controversial_aspects": ["aspects that might be controversial"],
                "bipartisan_potential": "Assessment of bipartisan support likelihood",
                "main_themes": ["key", "themes", "in", "the", "bill"]
            }}
            """
            
            response = self.client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt
            )
            
            result = json.loads(response.text)
            return result
            
        except Exception as e:
            logging.error(f"Policy categorization error: {str(e)}")
            return None
    
    def _analyze_stakeholders(self, bill_text: str, title: str) -> Optional[Dict]:
        """Identify stakeholders affected by the bill"""
        try:
            prompt = f"""
            You are an expert policy analyst. Identify stakeholder groups affected by this bill and assess the impact.

            Bill Title: {title}
            Bill Text: {bill_text[:3000]}

            Return JSON with this structure:
            {{
                "winners": ["group1", "group2"],
                "losers": ["group3", "group4"],
                "neutral": ["group5"],
                "impacts": {{
                    "group1": "positive impact description",
                    "group3": "negative impact description"
                }}
            }}

            Focus on major stakeholder groups like: businesses, consumers, workers, taxpayers, government agencies, nonprofits, specific industries, etc.
            """
            
            response = self.client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt
            )
            
            result = json.loads(response.text)
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
            prompt = f"""
            You are an expert at explaining complex legislation in plain language.
            Create a clear, concise summary that explains:
            1. What the bill does
            2. Who it affects
            3. Key provisions
            4. Potential impacts
            Write for a general audience without legal jargon.
            
            Bill Title: {title}
            Bill Text: {bill_text[:4000]}
            """
            
            response = self.client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt
            )
            
            return response.text
            
        except Exception as e:
            logging.error(f"Summary generation error: {str(e)}")
            return None
if __name__ == "__main__": 
    with open('test_data.json', 'r') as file:
        bill = json.load(file)
    ai = AIAnalyzer()
    print(f"keys: {bill.keys()}")

    bill_text = bill['full_text']
    title = bill['title']
    print(f"bill_text: {bill_text[:50]}")
    print(f"bill title: {title}")

    summary = ai.generate_bill_summary(bill_text, title)

    print(f"summary: {summary}")

