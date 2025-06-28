import os
import json
import logging
import time
from google import genai
from .analysis_cache import AnalysisCache
from utils.constants import FEDERAL_POLICY_CATEGORIES
from datetime import datetime

class AIAnalyzer:
    """AI-powered analysis of legislative bills using Gemini"""
    
    def __init__(self):
        self.api_key = os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            logging.warning("GEMINI_API_KEY not found. AI analysis will be disabled.")
            self.client = None
        else:
            self.client = genai.Client(api_key=self.api_key)
        self.model = "gemini-2.0-flash"
        self.cache = AnalysisCache()
    
    def analyze_bill(self, bill_text, bill_title):
        """
        Perform comprehensive AI analysis of a bill
        Returns dictionary with analysis results
        """
        try:
            summary_analysis = self._get_bill_summary(bill_text, bill_title)
            policy_analysis = self._analyze_policy_implications(bill_text, bill_title)
            stakeholder_analysis = self._identify_stakeholders(bill_text, bill_title)
            complexity_analysis = self._assess_complexity_and_impact(bill_text, bill_title)
            full_analysis = {
                'summary': summary_analysis,
                'policy_implications': policy_analysis,
                'stakeholders': stakeholder_analysis,
                'complexity_assessment': complexity_analysis,
                'generated_at': str(datetime.utcnow())
            }
            return full_analysis
        except Exception as e:
            logging.error(f"Error in AI analysis: {str(e)}")
            return {
                'error': 'Unable to complete AI analysis',
                'summary': {'main_summary': 'Analysis unavailable due to technical error'},
                'policy_implications': {'categories': [], 'main_themes': []},
                'stakeholders': {'affected_groups': [], 'winners_losers': []},
                'complexity_assessment': {'score': 0, 'reading_level': 'Unknown'}
            }
    
    def _gemini_json(self, prompt, system_message=None, max_tokens=1000):
        if not self.client:
            return None
        try:
            contents = prompt
            response = self.client.models.generate_content(
                model=self.model,
                contents=contents
            )
            # Gemini returns a response with a 'candidates' list
            text = response.candidates[0].content.parts[0].text
            
            # Handle Gemini's markdown code block format
            if text.startswith('```json'):
                # Extract JSON from markdown code blocks
                start = text.find('```json') + 7
                end = text.rfind('```')
                if end > start:
                    text = text[start:end].strip()
            elif text.startswith('```'):
                # Handle generic code blocks
                start = text.find('```') + 3
                end = text.rfind('```')
                if end > start:
                    text = text[start:end].strip()
            
            return json.loads(text)
        except Exception as e:
            logging.error(f"Gemini API error: {str(e)}")
            return None
    
    def _get_bill_summary(self, bill_text, bill_title):
        prompt = f"""
        Analyze this congressional bill and provide a comprehensive summary.\n\n        Bill Title: {bill_title}\n\n        Bill Text: {bill_text[:8000]}  # Limit text length for API\n\n        Please provide your analysis in JSON format with these fields:\n        {{\n            \"main_summary\": \"A 2-3 sentence summary of what this bill does\",\n            \"key_provisions\": [\"list\", \"of\", \"key\", \"provisions\"],\n            \"funding_amounts\": \"Any significant funding amounts mentioned\",\n            \"implementation_timeline\": \"When this would take effect\",\n            \"plain_language_explanation\": \"Explain this bill as if to a high school student\"\n        }}\n        """
        result = self._gemini_json(prompt)
        if result:
            return result
        return {
            "main_summary": "Unable to generate summary due to technical error",
            "key_provisions": [],
            "funding_amounts": "Unknown",
            "implementation_timeline": "Unknown",
            "plain_language_explanation": "Analysis unavailable"
        }
    
    def _analyze_policy_implications(self, bill_text, bill_title):
        categories_list = ', '.join(FEDERAL_POLICY_CATEGORIES)
        prompt = f"""
        Analyze the policy implications of this congressional bill.\n\n        Bill Title: {bill_title}\n        Bill Text: {bill_text[:8000]}\n\n        Categorize this bill and analyze its policy implications. Use ONLY the following categories for all policy area fields:\n        {categories_list}\n\n        Respond in JSON format:\n        {{\n            \"primary_policy_area\": \"The main policy area (must be one of the provided categories)\",\n            \"secondary_areas\": [\"list\", \"of\", \"secondary\", \"policy\", \"areas\"],\n            \"categories\": [\n                {{\n                    \"area\": \"policy area name (must be one of the provided categories)\",\n                    \"impact_level\": \"low/medium/high\",\n                    \"description\": \"How this bill affects this area\"\n                }}\n            ],\n            \"controversial_aspects\": [\"aspects that might be controversial\"],\n            \"bipartisan_potential\": \"Assessment of bipartisan support likelihood\",\n            \"main_themes\": [\"key\", \"themes\", \"in\", \"the\", \"bill\"]\n        }}\n        """
        result = self._gemini_json(prompt)
        if result:
            return result
        return {
            "primary_policy_area": "Unknown",
            "secondary_areas": [],
            "categories": [],
            "controversial_aspects": [],
            "bipartisan_potential": "Unknown",
            "main_themes": []
        }
    
    def _identify_stakeholders(self, bill_text, bill_title):
        prompt = f"""
        Identify the stakeholders who would be affected by this congressional bill.\n\n        Bill Title: {bill_title}\n        Bill Text: {bill_text[:8000]}\n\n        Analyze who would be affected and respond in JSON format:\n        {{\n            \"affected_groups\": [\n                {{\n                    \"group\": \"name of affected group\",\n                    \"impact_type\": \"positive/negative/mixed\",\n                    \"impact_description\": \"how they would be affected\"\n                }}\n            ],\n            \"winners_losers\": {{\n                \"potential_winners\": [\"groups that would benefit\"],\n                \"potential_losers\": [\"groups that might be negatively affected\"],\n                \"neutral_parties\": [\"groups with mixed or neutral impact\"]\n            }},\n            \"geographic_impact\": \"Which regions/states would be most affected\",\n            \"industry_sectors\": [\"sectors\", \"that\", \"would\", \"be\", \"affected\"]\n        }}\n        """
        result = self._gemini_json(prompt)
        if result:
            return result
        return {
            "affected_groups": [],
            "winners_losers": {
                "potential_winners": [],
                "potential_losers": [],
                "neutral_parties": []
            },
            "geographic_impact": "Unknown",
            "industry_sectors": []
        }
    
    def _assess_complexity_and_impact(self, bill_text, bill_title):
        prompt = f"""
        Assess the complexity and potential impact of this congressional bill.\n\n        Bill Title: {bill_title}\n        Bill Text: {bill_text[:6000]}\n\n        Provide your assessment in JSON format:\n        {{\n            \"complexity_score\": 85,  # 0-100 scale\n            \"reading_level\": \"Graduate/College/High School/Middle School\",\n            \"implementation_difficulty\": \"Easy/Moderate/Difficult/Very Difficult\",\n            \"scope_of_impact\": \"Local/State/National/International\",\n            \"estimated_cost_impact\": \"Low/Medium/High/Very High\",\n            \"regulatory_burden\": \"Minimal/Light/Moderate/Heavy\",\n            \"urgency_level\": \"Low/Medium/High/Critical\",\n            \"complexity_factors\": [\"factors that make this bill complex\"]\n        }}\n        """
        result = self._gemini_json(prompt, max_tokens=800)
        if result:
            return result
        return {
            "complexity_score": 50,
            "reading_level": "Unknown",
            "implementation_difficulty": "Unknown",
            "scope_of_impact": "Unknown",
            "estimated_cost_impact": "Unknown",
            "regulatory_burden": "Unknown",
            "urgency_level": "Unknown",
            "complexity_factors": []
        }
    
    def calculate_alignment_score(self, bill_analysis, user_preferences):
        """
        Calculate how well a bill aligns with user policy preferences
        Returns score from -100 to +100
        """
        try:
            # Extract policy areas from bill analysis
            policy_implications = bill_analysis.get('policy_implications', {})
            primary_area = policy_implications.get('primary_policy_area', '').lower()
            secondary_areas = [area.lower() for area in policy_implications.get('secondary_areas', [])]
            
            total_score = 0
            total_weight = 0
            
            # Check alignment for each policy area the user cares about
            for policy_area, preferences in user_preferences.items():
                if not isinstance(preferences, dict):
                    continue
                
                importance = preferences.get('importance', 'medium')
                stance = preferences.get('stance', 'neutral')
                
                # Weight based on importance
                weight_map = {'low': 1, 'medium': 2, 'high': 3}
                weight = weight_map.get(importance, 2)
                
                # Check if this policy area is relevant to the bill
                relevance = 0
                if policy_area.replace('_', ' ') in primary_area or primary_area in policy_area:
                    relevance = 1.0  # Primary area
                elif any(policy_area.replace('_', ' ') in area or area in policy_area for area in secondary_areas):
                    relevance = 0.6  # Secondary area
                elif policy_area in ['civil_rights', 'government_reform'] and 'government' in primary_area:
                    relevance = 0.4  # Tangentially related
                
                if relevance > 0:
                    # Calculate stance alignment (simplified)
                    stance_score = 0
                    if stance == 'very_supportive':
                        stance_score = 80
                    elif stance == 'supportive':
                        stance_score = 40
                    elif stance == 'neutral':
                        stance_score = 0
                    elif stance == 'opposed':
                        stance_score = -40
                    elif stance == 'very_opposed':
                        stance_score = -80
                    
                    weighted_score = stance_score * weight * relevance
                    total_score += weighted_score
                    total_weight += weight * relevance
            
            # Calculate final alignment score
            if total_weight > 0:
                alignment_score = total_score / total_weight
                return max(-100, min(100, alignment_score))
            else:
                return 0  # No relevant policy areas found
                
        except Exception as e:
            logging.error(f"Error calculating alignment score: {str(e)}")
            return 0
    
    def generate_user_specific_analysis(self, bill_analysis, user_preferences, alignment_score):
        """Generate personalized analysis based on user preferences"""
        try:
            # Create a summary of user preferences
            strong_preferences = []
            for area, prefs in user_preferences.items():
                if isinstance(prefs, dict) and prefs.get('importance') == 'high':
                    stance = prefs.get('stance', 'neutral')
                    if stance != 'neutral':
                        strong_preferences.append(f"{area}: {stance}")
            
            prompt = f"""
            Based on this bill analysis and user preferences, provide personalized insights.\n\n            Bill Analysis Summary: {bill_analysis.get('summary', {}).get('main_summary', '')}\n            Policy Areas: {bill_analysis.get('policy_implications', {}).get('primary_policy_area', '')}\n\n            User's Strong Preferences: {'; '.join(strong_preferences)}\n            Calculated Alignment Score: {alignment_score}\n\n            Provide personalized analysis in JSON format:\n            {{\n                \"personal_impact\": \"How this bill might personally affect someone with these preferences\",\n                \"key_concerns\": [\"specific concerns based on user preferences\"],\n                \"potential_benefits\": [\"potential benefits for this user\"],\n                \"action_recommendations\": [\"what actions the user might consider taking\"],\n                \"explanation_of_score\": \"Why the alignment score is what it is\"\n            }}\n            """
            result = self._gemini_json(prompt, max_tokens=800)
            if result:
                return result
            return {
                "personal_impact": "Unable to generate personalized analysis",
                "key_concerns": [],
                "potential_benefits": [],
                "action_recommendations": [],
                "explanation_of_score": "Analysis unavailable due to technical error"
            }
        except Exception as e:
            logging.error(f"Error generating user-specific analysis: {str(e)}")
            return {
                "personal_impact": "Unable to generate personalized analysis",
                "key_concerns": [],
                "potential_benefits": [],
                "action_recommendations": [],
                "explanation_of_score": "Analysis unavailable due to technical error"
            }
