import os
import json
import logging
import time
from openai import OpenAI
from .analysis_cache import AnalysisCache

class AIAnalyzer:
    """AI-powered analysis of legislative bills using OpenAI"""
    
    def __init__(self):
        self.client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        # the newest OpenAI model is "gpt-4o" which was released May 13, 2024.
        # do not change this unless explicitly requested by the user
        self.model = "gpt-4o"
        self.cache = AnalysisCache()
    
    def analyze_bill(self, bill_text, bill_title):
        """
        Perform comprehensive AI analysis of a bill
        Returns dictionary with analysis results
        """
        try:
            # First, get a summary and key points
            summary_analysis = self._get_bill_summary(bill_text, bill_title)
            
            # Then analyze policy implications
            policy_analysis = self._analyze_policy_implications(bill_text, bill_title)
            
            # Identify stakeholders
            stakeholder_analysis = self._identify_stakeholders(bill_text, bill_title)
            
            # Assess complexity and impact
            complexity_analysis = self._assess_complexity_and_impact(bill_text, bill_title)
            
            # Combine all analyses
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
    
    def _get_bill_summary(self, bill_text, bill_title):
        """Generate a comprehensive summary of the bill"""
        prompt = f"""
        Analyze this congressional bill and provide a comprehensive summary.
        
        Bill Title: {bill_title}
        
        Bill Text: {bill_text[:8000]}  # Limit text length for API
        
        Please provide your analysis in JSON format with these fields:
        {{
            "main_summary": "A 2-3 sentence summary of what this bill does",
            "key_provisions": ["list", "of", "key", "provisions"],
            "funding_amounts": "Any significant funding amounts mentioned",
            "implementation_timeline": "When this would take effect",
            "plain_language_explanation": "Explain this bill as if to a high school student"
        }}
        """
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert legislative analyst. Provide accurate, objective analysis of congressional bills."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                max_tokens=1000
            )
            
            return json.loads(response.choices[0].message.content)
            
        except Exception as e:
            logging.error(f"Error in bill summary analysis: {str(e)}")
            return {
                "main_summary": "Unable to generate summary due to technical error",
                "key_provisions": [],
                "funding_amounts": "Unknown",
                "implementation_timeline": "Unknown",
                "plain_language_explanation": "Analysis unavailable"
            }
    
    def _analyze_policy_implications(self, bill_text, bill_title):
        """Analyze the policy implications and categorize the bill"""
        prompt = f"""
        Analyze the policy implications of this congressional bill.
        
        Bill Title: {bill_title}
        Bill Text: {bill_text[:8000]}
        
        Categorize this bill and analyze its policy implications. Respond in JSON format:
        {{
            "primary_policy_area": "The main policy area (healthcare, environment, economy, etc.)",
            "secondary_areas": ["list", "of", "secondary", "policy", "areas"],
            "categories": [
                {{
                    "area": "policy area name",
                    "impact_level": "low/medium/high",
                    "description": "How this bill affects this area"
                }}
            ],
            "controversial_aspects": ["aspects that might be controversial"],
            "bipartisan_potential": "Assessment of bipartisan support likelihood",
            "main_themes": ["key", "themes", "in", "the", "bill"]
        }}
        """
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a policy expert analyzing legislative bills objectively."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                max_tokens=1000
            )
            
            return json.loads(response.choices[0].message.content)
            
        except Exception as e:
            logging.error(f"Error in policy analysis: {str(e)}")
            return {
                "primary_policy_area": "Unknown",
                "secondary_areas": [],
                "categories": [],
                "controversial_aspects": [],
                "bipartisan_potential": "Unknown",
                "main_themes": []
            }
    
    def _identify_stakeholders(self, bill_text, bill_title):
        """Identify stakeholders affected by the bill"""
        prompt = f"""
        Identify the stakeholders who would be affected by this congressional bill.
        
        Bill Title: {bill_title}
        Bill Text: {bill_text[:8000]}
        
        Analyze who would be affected and respond in JSON format:
        {{
            "affected_groups": [
                {{
                    "group": "name of affected group",
                    "impact_type": "positive/negative/mixed",
                    "impact_description": "how they would be affected"
                }}
            ],
            "winners_losers": {{
                "potential_winners": ["groups that would benefit"],
                "potential_losers": ["groups that might be negatively affected"],
                "neutral_parties": ["groups with mixed or neutral impact"]
            }},
            "geographic_impact": "Which regions/states would be most affected",
            "industry_sectors": ["sectors", "that", "would", "be", "affected"]
        }}
        """
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a stakeholder analysis expert for legislative bills."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                max_tokens=1000
            )
            
            return json.loads(response.choices[0].message.content)
            
        except Exception as e:
            logging.error(f"Error in stakeholder analysis: {str(e)}")
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
        """Assess the complexity and potential impact of the bill"""
        prompt = f"""
        Assess the complexity and potential impact of this congressional bill.
        
        Bill Title: {bill_title}
        Bill Text: {bill_text[:6000]}
        
        Provide your assessment in JSON format:
        {{
            "complexity_score": 85,  # 0-100 scale
            "reading_level": "Graduate/College/High School/Middle School",
            "implementation_difficulty": "Easy/Moderate/Difficult/Very Difficult",
            "scope_of_impact": "Local/State/National/International",
            "estimated_cost_impact": "Low/Medium/High/Very High",
            "regulatory_burden": "Minimal/Light/Moderate/Heavy",
            "urgency_level": "Low/Medium/High/Critical",
            "complexity_factors": ["factors that make this bill complex"]
        }}
        """
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert in legislative complexity analysis."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                max_tokens=800
            )
            
            return json.loads(response.choices[0].message.content)
            
        except Exception as e:
            logging.error(f"Error in complexity analysis: {str(e)}")
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
            Based on this bill analysis and user preferences, provide personalized insights.
            
            Bill Analysis Summary: {bill_analysis.get('summary', {}).get('main_summary', '')}
            Policy Areas: {bill_analysis.get('policy_implications', {}).get('primary_policy_area', '')}
            
            User's Strong Preferences: {'; '.join(strong_preferences)}
            Calculated Alignment Score: {alignment_score}
            
            Provide personalized analysis in JSON format:
            {{
                "personal_impact": "How this bill might personally affect someone with these preferences",
                "key_concerns": ["specific concerns based on user preferences"],
                "potential_benefits": ["potential benefits for this user"],
                "action_recommendations": ["what actions the user might consider taking"],
                "explanation_of_score": "Why the alignment score is what it is"
            }}
            """
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are providing personalized political analysis based on user preferences."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                max_tokens=800
            )
            
            return json.loads(response.choices[0].message.content)
            
        except Exception as e:
            logging.error(f"Error generating user-specific analysis: {str(e)}")
            return {
                "personal_impact": "Unable to generate personalized analysis",
                "key_concerns": [],
                "potential_benefits": [],
                "action_recommendations": [],
                "explanation_of_score": "Analysis unavailable due to technical error"
            }

# Import datetime for timestamps
from datetime import datetime
