import os
import json
import logging
from typing import Dict, List, Optional, Tuple
from openai import OpenAI
import re
from datetime import datetime

logger = logging.getLogger(__name__)

class BillAnalyzer:
    """AI-powered bill analysis using OpenAI"""
    
    def __init__(self):
        self.openai_api_key = os.environ.get("OPENAI_API_KEY")
        if not self.openai_api_key:
            logger.warning("OPENAI_API_KEY not found in environment variables")
            self.client = None
        else:
            self.client = OpenAI(api_key=self.openai_api_key)
        
        # Policy categories for classification
        self.policy_categories = [
            "Healthcare", "Environment", "Economy", "Education", "Defense",
            "Immigration", "Technology", "Civil Rights", "Agriculture", "Energy",
            "Transportation", "Housing", "Tax Policy", "Social Security", "Labor",
            "Trade", "Foreign Relations", "Criminal Justice", "Veterans Affairs", "Budget"
        ]
    
    def categorize_bill(self, bill_text: str, bill_title: str) -> Dict:
        """Categorize a bill into policy domains using AI"""
        if not self.client:
            return {"categories": [], "confidence": 0.0, "reasoning": "OpenAI API not available"}
        
        try:
            prompt = f"""
            Analyze the following congressional bill and categorize it into relevant policy domains.
            
            Bill Title: {bill_title}
            Bill Text: {bill_text[:8000]}...  # Truncate for token limits
            
            Available categories: {', '.join(self.policy_categories)}
            
            Please respond with JSON in this format:
            {{
                "categories": ["category1", "category2"],  // 1-3 most relevant categories
                "confidence": 0.85,  // confidence score 0-1
                "reasoning": "Brief explanation of categorization",
                "controversy_score": 3,  // 1-5 scale, 5 being most controversial
                "complexity_score": 4  // 1-5 scale, 5 being most complex
            }}
            """
            
            # the newest OpenAI model is "gpt-4o" which was released May 13, 2024.
            # do not change this unless explicitly requested by the user
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            return result
            
        except Exception as e:
            logger.error(f"Bill categorization failed: {e}")
            return {"categories": [], "confidence": 0.0, "reasoning": f"Analysis failed: {str(e)}"}
    
    def analyze_stakeholder_impact(self, bill_text: str, bill_title: str) -> Dict:
        """Analyze which stakeholders are affected by the bill"""
        if not self.client:
            return {"stakeholders": {}, "reasoning": "OpenAI API not available"}
        
        try:
            prompt = f"""
            Analyze the stakeholder impact of this congressional bill.
            
            Bill Title: {bill_title}
            Bill Text: {bill_text[:8000]}...
            
            Identify key stakeholder groups and how they would be affected (positively or negatively).
            
            Please respond with JSON in this format:
            {{
                "stakeholders": {{
                    "Consumers": {{"impact": "positive", "explanation": "Lower costs due to..."}},
                    "Small Businesses": {{"impact": "negative", "explanation": "Increased compliance costs..."}},
                    "Healthcare Providers": {{"impact": "mixed", "explanation": "Benefits from... but costs from..."}}
                }},
                "funding_flows": ["$50M to renewable energy research", "$100M to rural broadband"],
                "special_interests": ["Identifies provisions that may benefit narrow constituencies"],
                "reasoning": "Overall analysis summary"
            }}
            """
            
            # the newest OpenAI model is "gpt-4o" which was released May 13, 2024.
            # do not change this unless explicitly requested by the user
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            return result
            
        except Exception as e:
            logger.error(f"Stakeholder analysis failed: {e}")
            return {"stakeholders": {}, "reasoning": f"Analysis failed: {str(e)}"}
    
    def score_policy_alignment(self, bill_text: str, bill_title: str, user_preferences: Dict) -> Dict:
        """Score how well a bill aligns with user policy preferences"""
        if not self.client or not user_preferences:
            return {"alignment_score": 0, "section_scores": {}, "reasoning": "Insufficient data for analysis"}
        
        try:
            # Convert user preferences to readable format
            prefs_text = []
            for category, score in user_preferences.items():
                if score > 60:
                    prefs_text.append(f"Strongly supports {category}")
                elif score > 40:
                    prefs_text.append(f"Moderately supports {category}")
                elif score < 20:
                    prefs_text.append(f"Strongly opposes {category}")
                elif score < 40:
                    prefs_text.append(f"Moderately opposes {category}")
            
            prompt = f"""
            Analyze how well this congressional bill aligns with the user's policy preferences.
            
            Bill Title: {bill_title}
            Bill Text: {bill_text[:8000]}...
            
            User Policy Preferences:
            {chr(10).join(prefs_text)}
            
            Provide an alignment score from -100 (completely opposed) to +100 (perfectly aligned).
            
            Please respond with JSON in this format:
            {{
                "alignment_score": 45,  // -100 to +100
                "section_scores": {{
                    "Section 1 - Main Provisions": 60,
                    "Section 2 - Funding": -20,
                    "Section 3 - Implementation": 30
                }},
                "key_provisions": [
                    {{"provision": "Increases healthcare funding", "alignment": "positive", "impact": "high"}},
                    {{"provision": "New environmental regulations", "alignment": "neutral", "impact": "medium"}}
                ],
                "reasoning": "Detailed explanation of alignment analysis",
                "concerns": ["Potential issues that conflict with user preferences"],
                "benefits": ["Aspects that align well with user values"]
            }}
            """
            
            # the newest OpenAI model is "gpt-4o" which was released May 13, 2024.
            # do not change this unless explicitly requested by the user
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            return result
            
        except Exception as e:
            logger.error(f"Policy alignment scoring failed: {e}")
            return {"alignment_score": 0, "section_scores": {}, "reasoning": f"Analysis failed: {str(e)}"}
    
    def extract_key_sections(self, bill_text: str) -> List[Dict]:
        """Extract and summarize key sections of a bill"""
        if not self.client:
            return []
        
        try:
            prompt = f"""
            Analyze this congressional bill text and extract the key sections with plain-language summaries.
            
            Bill Text: {bill_text[:10000]}...
            
            Please respond with JSON in this format:
            {{
                "sections": [
                    {{
                        "title": "Section 1: Main Provisions",
                        "summary": "Plain language explanation of what this section does",
                        "complexity": "medium",  // low, medium, high
                        "importance": "high"     // low, medium, high
                    }}
                ]
            }}
            """
            
            # the newest OpenAI model is "gpt-4o" which was released May 13, 2024.
            # do not change this unless explicitly requested by the user
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            return result.get("sections", [])
            
        except Exception as e:
            logger.error(f"Section extraction failed: {e}")
            return []
    
    def generate_plain_language_summary(self, bill_text: str, bill_title: str) -> str:
        """Generate a plain language summary of the bill"""
        if not self.client:
            return "AI analysis not available. Please check OpenAI API configuration."
        
        try:
            prompt = f"""
            Create a clear, plain-language summary of this congressional bill that a typical citizen can understand.
            
            Bill Title: {bill_title}
            Bill Text: {bill_text[:8000]}...
            
            Write a summary that:
            1. Explains what the bill does in simple terms
            2. Highlights the main changes it would make
            3. Mentions who would be affected
            4. Notes any significant funding or timeline requirements
            
            Keep it concise but comprehensive, suitable for someone without legal expertise.
            """
            
            # the newest OpenAI model is "gpt-4o" which was released May 13, 2024.
            # do not change this unless explicitly requested by the user
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}]
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"Summary generation failed: {e}")
            return f"Unable to generate summary: {str(e)}"

# Global instance
bill_analyzer = BillAnalyzer()
