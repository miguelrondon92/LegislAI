import os
import json
import logging
import time
from typing import Dict, List, Optional
from google import genai
from .analysis_cache import AnalysisCache
from utils.constants import FEDERAL_POLICY_CATEGORIES
from datetime import datetime
from utils.bill_chunker import BillChunker, BillChunk

logger = logging.getLogger(__name__)

class AIAnalyzer:
    """AI-powered legislative analysis using Gemini with chunked analysis"""
    
    def __init__(self):
        self.api_key = os.environ.get('GEMINI_API_KEY')
        if not self.api_key:
            logging.warning("GEMINI_API_KEY not found. AI analysis will be disabled.")
            self.client = None
        else:
            self.client = genai.Client(api_key=self.api_key)
        
        # Initialize bill chunker
        self.bill_chunker = BillChunker(max_chunk_size=8000, overlap_size=500)
        
        # Use the standardized federal policy categories
        self.policy_categories = FEDERAL_POLICY_CATEGORIES
        self.model = "gemini-2.0-flash"
    
    def analyze_bill(self, bill_text, bill_title):
        """
        Perform comprehensive AI analysis of a bill using chunked approach
        
        Args:
            bill_text: Full bill text (no truncation)
            bill_title: Bill title
            
        Returns:
            Dictionary containing analysis results
        """
        if not self.client:
            return {
                'error': 'Unable to complete AI analysis',
                'summary': {'main_summary': 'Analysis unavailable due to technical error'},
                'policy_implications': {'categories': [], 'main_themes': []},
                'stakeholders': {'affected_groups': [], 'winners_losers': []},
                'complexity_assessment': {'score': 0, 'reading_level': 'Unknown'}
            }
        
        try:
            # Chunk the bill text for analysis
            chunks = self.bill_chunker.chunk_bill(bill_text, bill_title)
            logger.info(f"Created {len(chunks)} chunks for analysis")
            
            # Perform different types of analysis using chunks
            analysis_results = {}
            
            # 1. Generate summary
            summary = self._get_bill_summary_chunked(chunks, bill_title)
            analysis_results['summary'] = summary
            
            # 2. Analyze policy implications
            policy_implications = self._analyze_policy_implications_chunked(chunks, bill_title)
            analysis_results['policy_implications'] = policy_implications
            
            # 3. Identify stakeholders
            stakeholders = self._identify_stakeholders_chunked(chunks, bill_title)
            analysis_results['stakeholders'] = stakeholders
            
            # 4. Assess complexity and impact
            complexity = self._assess_complexity_and_impact_chunked(chunks, bill_title)
            analysis_results['complexity_assessment'] = complexity
            
            # Add metadata
            analysis_results['generated_at'] = datetime.now().isoformat()
            analysis_results['analysis_method'] = 'chunked'
            analysis_results['chunks_analyzed'] = len(chunks)
            
            return analysis_results
            
        except Exception as e:
            logging.error(f"AI analysis error: {str(e)}")
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
    
    def _get_bill_summary_chunked(self, chunks: List[BillChunk], bill_title: str):
        """Generate bill summary using chunked analysis"""
        try:
            # Use the most important chunks for summary
            important_chunks = sorted(chunks, key=lambda x: x.importance_score, reverse=True)[:3]
            
            chunk_texts = []
            for i, chunk in enumerate(important_chunks):
                chunk_texts.append(f"Chunk {i+1} ({chunk.chunk_type}):\n{chunk.content[:2000]}")
            
            combined_text = "\n\n---\n\n".join(chunk_texts)
            
            prompt = f"""
            Analyze this congressional bill and provide a comprehensive summary based on the following chunks.
            
            Bill Title: {bill_title}
            
            Bill Content (from {len(important_chunks)} key chunks):
            {combined_text}
            
            Please provide your analysis in JSON format with these fields:
            {{
                "main_summary": "A 2-3 sentence summary of what this bill does",
                "key_provisions": ["list", "of", "key", "provisions"],
                "funding_amounts": "Any significant funding amounts mentioned",
                "implementation_timeline": "When this would take effect",
                "plain_language_explanation": "Explain this bill as if to a high school student"
            }}
            """
            
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
        except Exception as e:
            logging.error(f"Chunked summary generation error: {str(e)}")
            return {
                "main_summary": "Unable to generate summary due to technical error",
                "key_provisions": [],
                "funding_amounts": "Unknown",
                "implementation_timeline": "Unknown",
                "plain_language_explanation": "Analysis unavailable"
            }
    
    def _analyze_policy_implications_chunked(self, chunks: List[BillChunk], bill_title: str):
        """Analyze policy implications using chunked analysis"""
        try:
            categories_list = ', '.join(FEDERAL_POLICY_CATEGORIES)
            
            # Use the most important chunks for policy analysis
            important_chunks = sorted(chunks, key=lambda x: x.importance_score, reverse=True)[:5]
            
            chunk_texts = []
            for i, chunk in enumerate(important_chunks):
                chunk_texts.append(f"Chunk {i+1} ({chunk.chunk_type}):\n{chunk.content[:1500]}")
            
            combined_text = "\n\n---\n\n".join(chunk_texts)
            
            prompt = f"""
            Analyze the policy implications of this congressional bill based on the following chunks, paying special attention to any hidden provisions or unexpected elements that might have been "snuck in" to the legislation.
            
            Bill Title: {bill_title}
            
            Bill Content (from {len(important_chunks)} key chunks):
            {combined_text}
            
            Categorize this bill and analyze its policy implications. Use ONLY the following categories for all policy area fields:
            {categories_list}
            
            For each policy area, carefully examine if there are any provisions that seem:
            - Unrelated to the main purpose of the bill
            - Hidden in complex language or buried in technical sections
            - Beneficial to narrow special interests
            - Inserted without clear justification
            - Using vague or misleading language to disguise their true impact
            
            Respond in JSON format:
            {{
                "primary_policy_area": "The main policy area (must be one of the provided categories)",
                "secondary_areas": ["list", "of", "secondary", "policy", "areas"],
                "categories": [
                    {{
                        "area": "policy area name (must be one of the provided categories)",
                        "impact_level": "low/medium/high",
                        "description": "How this bill affects this area",
                        "sneakiness_score": 0.0,
                        "sneakiness_explanation": "Why this category got its sneakiness score (0.0 = transparent, 1.0 = very sneaky)"
                    }}
                ],
                "controversial_aspects": ["aspects that might be controversial"],
                "bipartisan_potential": "Assessment of bipartisan support likelihood", 
                "main_themes": ["key", "themes", "in", "the", "bill"],
                "hidden_provisions_analysis": {{
                    "overall_sneakiness": 0.0,
                    "hidden_provisions_found": ["list of any hidden or sneaky provisions"],
                    "transparency_assessment": "Assessment of how transparent vs sneaky this bill is overall"
                }}
            }}
            
            Sneakiness Score Guide:
            - 0.0-0.2: Very transparent, straightforward provisions directly related to stated purpose
            - 0.3-0.4: Mostly transparent with some complex language that could be clearer  
            - 0.5-0.6: Moderate concern - some provisions that seem tangentially related or benefit specific groups
            - 0.7-0.8: High concern - provisions that appear unrelated to main purpose or use misleading language
            - 0.9-1.0: Very sneaky - hidden provisions that seem designed to benefit special interests or accomplish unstated goals
            """
            
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
        except Exception as e:
            logging.error(f"Chunked policy analysis error: {str(e)}")
            return {
                "primary_policy_area": "Unknown",
                "secondary_areas": [],
                "categories": [],
                "controversial_aspects": [],
                "bipartisan_potential": "Unknown",
                "main_themes": []
            }
    
    def _identify_stakeholders_chunked(self, chunks: List[BillChunk], bill_title: str):
        """Identify stakeholders using chunked analysis"""
        try:
            # Use the most important chunks for stakeholder analysis
            important_chunks = sorted(chunks, key=lambda x: x.importance_score, reverse=True)[:5]
            
            chunk_texts = []
            for i, chunk in enumerate(important_chunks):
                chunk_texts.append(f"Chunk {i+1} ({chunk.chunk_type}):\n{chunk.content[:1500]}")
            
            combined_text = "\n\n---\n\n".join(chunk_texts)
            
            prompt = f"""
            Identify the stakeholders who would be affected by this congressional bill based on the following chunks.
            
            Bill Title: {bill_title}
            
            Bill Content (from {len(important_chunks)} key chunks):
            {combined_text}
            
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
        except Exception as e:
            logging.error(f"Chunked stakeholder analysis error: {str(e)}")
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
    
    def _assess_complexity_and_impact_chunked(self, chunks: List[BillChunk], bill_title: str):
        """Assess complexity and impact using chunked analysis"""
        try:
            # Use the most important chunks for complexity assessment
            important_chunks = sorted(chunks, key=lambda x: x.importance_score, reverse=True)[:5]
            
            chunk_texts = []
            for i, chunk in enumerate(important_chunks):
                chunk_texts.append(f"Chunk {i+1} ({chunk.chunk_type}):\n{chunk.content[:1200]}")
            
            combined_text = "\n\n---\n\n".join(chunk_texts)
            
            prompt = f"""
            Assess the complexity and potential impact of this congressional bill based on the following chunks.
            
            Bill Title: {bill_title}
            
            Bill Content (from {len(important_chunks)} key chunks):
            {combined_text}
            
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
        except Exception as e:
            logging.error(f"Chunked complexity assessment error: {str(e)}")
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
