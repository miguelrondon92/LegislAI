import json
import os
import logging
from typing import Dict, List, Optional, Tuple
from google import genai
# from openai import OpenAI  # Removed - using Gemini only
import re
from datetime import datetime
from utils.constants import FEDERAL_POLICY_CATEGORIES
from utils.bill_chunker import BillChunker, BillChunk
#from .notification_service import NotificationService

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
        #self.notification_service = NotificationService()
        
        # Initialize bill chunker
        self.bill_chunker = BillChunker(max_chunk_size=8000, overlap_size=500)
        
        # Use the standardized federal policy categories
        self.policy_categories = FEDERAL_POLICY_CATEGORIES
    
    def analyze_bill(self, bill_or_text, title=None) -> Dict:
        """Perform comprehensive AI analysis of a bill using chunked approach"""
        if not self.client:
            logging.warning("Gemini client not available")
            return {}
        
        try:
            # Handle both bill objects and text inputs
            if hasattr(bill_or_text, 'get_bill_identifier'):
                # It's a bill object
                bill = bill_or_text
                text_to_analyze = self._prepare_bill_text(bill)
                title = bill.title
                summary = bill.summary
            else:
                # It's text input
                text_to_analyze = str(bill_or_text)
                title = title or "Unknown Bill"
                summary = ""
            
            if not text_to_analyze:
                logging.warning(f"No text available for analysis")
                return {}
            
            # Chunk the bill text for analysis
            chunks = self.bill_chunker.chunk_bill(text_to_analyze, title, summary)
            logger.info(f"Created {len(chunks)} chunks for analysis")
            
            # Perform different types of analysis using chunks
            analysis_results = {}
            
            # 1. Generate summary first (most important)
            summary = self._generate_bill_summary_chunked(chunks, title)
            if summary and "Unable to generate summary due to technical error" not in summary:
                analysis_results['summary'] = {
                    'main_summary': summary,
                    'key_provisions': [],
                    'funding_amounts': 'Unknown',
                    'implementation_timeline': 'Unknown',
                    'plain_language_explanation': summary
                }
            
            # 2. Policy categorization using chunks
            categories = self._categorize_bill_chunked(chunks, title)
            if categories and isinstance(categories, dict):
                analysis_results['policy_implications'] = categories
            
            # 3. Stakeholder analysis using chunks
            stakeholders = self._analyze_stakeholders_chunked(chunks, title)
            if stakeholders and isinstance(stakeholders, dict):
                analysis_results['stakeholders'] = stakeholders
            
            # 4. Complexity scoring (can use full text)
            complexity = self._assess_complexity(text_to_analyze)
            if complexity is not None:
                analysis_results['complexity_assessment'] = {
                    'complexity_score': complexity,
                    'reading_level': 'Unknown',
                    'implementation_difficulty': 'Unknown',
                    'scope_of_impact': 'Unknown',
                    'estimated_cost_impact': 'Unknown',
                    'regulatory_burden': 'Unknown',
                    'urgency_level': 'Unknown',
                    'complexity_factors': []
                }
            
            # 5. Controversy detection (can use full text)
            controversy = self._detect_controversy(text_to_analyze, title)
            if controversy is not None:
                analysis_results['controversy_score'] = controversy
            
            # Add timestamp and chunk information
            analysis_results['generated_at'] = datetime.now().isoformat()
            analysis_results['analysis_method'] = 'chunked'
            analysis_results['chunks_analyzed'] = len(chunks)
            
            # If we have a bill object, store the analysis
            if hasattr(bill_or_text, 'set_ai_analysis'):
                bill_or_text.set_ai_analysis(analysis_results)
            
            return analysis_results
            
        except Exception as e:
            logging.error(f"AI analysis error: {str(e)}")
            return {}
    
    def _prepare_bill_text(self, bill) -> str:
        """Prepare bill text for analysis - no longer truncating"""
        text_parts = []
        
        if bill.title:
            text_parts.append(f"Title: {bill.title}")
        
        if bill.summary:
            text_parts.append(f"Summary: {bill.summary}")
        
        # Fetch full text from API when needed - NO TRUNCATION
        full_text = bill.get_full_text()
        if full_text:
            text_parts.append(f"Full Text: {full_text}")
        
        return "\n\n".join(text_parts)
    
    def _generate_bill_summary_chunked(self, chunks: List[BillChunk], title: str) -> Optional[str]:
        """Generate bill summary using chunked analysis"""
        try:
            if not self.client:
                return None
            
            # Use the most important chunks for summary
            important_chunks = sorted(chunks, key=lambda x: x.importance_score, reverse=True)[:3]
            
            chunk_texts = []
            for i, chunk in enumerate(important_chunks):
                chunk_texts.append(f"Chunk {i+1} ({chunk.chunk_type}):\n{chunk.content[:2000]}")
            
            combined_text = "\n\n---\n\n".join(chunk_texts)
            
            prompt = f"""
            Create a comprehensive summary of this congressional bill based on the following chunks.
            
            Bill Title: {title}
            
            Bill Content (from {len(important_chunks)} key chunks):
            {combined_text}
            
            Please provide a clear, comprehensive summary that:
            1. Explains what the bill does in simple terms
            2. Highlights the main changes it would make
            3. Mentions who would be affected
            4. Notes any significant funding or timeline requirements
            
            Keep it concise but comprehensive, suitable for someone without legal expertise.
            """
            
            response = self.client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt
            )
            
            if not response or not response.text:
                logging.warning("Empty response from Gemini for summary")
                return None
            
            return response.text.strip()
            
        except Exception as e:
            logging.error(f"Chunked summary generation error: {str(e)}")
            return None
    
    def _categorize_bill_chunked(self, chunks: List[BillChunk], title: str) -> Optional[Dict]:
        """Categorize bill into policy domains using chunked analysis"""
        try:
            if not self.client:
                return None
                
            categories_list = ', '.join(self.policy_categories)
            
            # Use the most important chunks for categorization
            important_chunks = sorted(chunks, key=lambda x: x.importance_score, reverse=True)[:5]
            
            chunk_texts = []
            for i, chunk in enumerate(important_chunks):
                chunk_texts.append(f"Chunk {i+1} ({chunk.chunk_type}):\n{chunk.content[:1500]}")
            
            combined_text = "\n\n---\n\n".join(chunk_texts)
            
            prompt = f"""
            Analyze the policy implications of this congressional bill based on the following chunks.
            
            Bill Title: {title}
            
            Bill Content (from {len(important_chunks)} key chunks):
            {combined_text}
            
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
            
            if not response or not response.text:
                logging.warning("Empty response from Gemini")
                return None
            
            logging.info(f"Gemini response: {response.text[:500]}...")
            
            # Clean the response to extract JSON
            cleaned_response = self._clean_json_response(response.text)
            result = json.loads(cleaned_response)
            
            # Validate that we got actual data
            if not result or not isinstance(result, dict):
                return None
                
            return result
            
        except Exception as e:
            logging.error(f"Chunked policy categorization error: {str(e)}")
            return None
    
    def _analyze_stakeholders_chunked(self, chunks: List[BillChunk], title: str) -> Optional[Dict]:
        """Identify stakeholders affected by the bill using chunked analysis"""
        try:
            if not self.client:
                return None
                
            # Use the most important chunks for stakeholder analysis
            important_chunks = sorted(chunks, key=lambda x: x.importance_score, reverse=True)[:5]
            
            chunk_texts = []
            for i, chunk in enumerate(important_chunks):
                chunk_texts.append(f"Chunk {i+1} ({chunk.chunk_type}):\n{chunk.content[:1500]}")
            
            combined_text = "\n\n---\n\n".join(chunk_texts)
            
            prompt = f"""
            You are an expert policy analyst. Identify stakeholder groups affected by this bill based on the following chunks.

            Bill Title: {title}
            
            Bill Content (from {len(important_chunks)} key chunks):
            {combined_text}

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
            
            if not response or not response.text:
                logging.warning("Empty response from Gemini for stakeholder analysis")
                return None
            
            logging.info(f"Gemini stakeholder response: {response.text[:500]}...")
            
            # Clean the response to extract JSON
            cleaned_response = self._clean_json_response(response.text)
            result = json.loads(cleaned_response)
            
            # Validate that we got actual data
            if not result or not isinstance(result, dict):
                return None
                
            return result
            
        except Exception as e:
            logging.error(f"Chunked stakeholder analysis error: {str(e)}")
            return None

    def _clean_json_response(self, response_text: str) -> str:
        """Clean JSON response by removing markdown code blocks if present"""
        if not response_text:
            return ""
        
        # Remove markdown code blocks if present
        if response_text.startswith("```json"):
            response_text = response_text[7:]  # Remove ```json
        elif response_text.startswith("```"):
            response_text = response_text[3:]  # Remove ```
        
        if response_text.endswith("```"):
            response_text = response_text[:-3]  # Remove trailing ```
        
        return response_text.strip()

    def _assess_complexity(self, bill_text: str) -> Optional[float]:
        """Assess bill complexity on a 0-1 scale - uses full text"""
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
        """Detect potentially controversial provisions - uses full text"""
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
        """Generate a plain language summary of the bill - now uses chunked approach"""
        try:
            if not self.client:
                return None
            
            # Create chunks for summary generation
            chunks = self.bill_chunker.chunk_bill(bill_text, title)
            
            # Use the most important chunks
            important_chunks = sorted(chunks, key=lambda x: x.importance_score, reverse=True)[:3]
            
            chunk_texts = []
            for i, chunk in enumerate(important_chunks):
                chunk_texts.append(f"Chunk {i+1} ({chunk.chunk_type}):\n{chunk.content[:2000]}")
            
            combined_text = "\n\n---\n\n".join(chunk_texts)
            
            prompt = f"""
            Create a clear, plain-language summary of this congressional bill based on the following chunks.
            
            Bill Title: {title}
            
            Bill Content (from {len(important_chunks)} key chunks):
            {combined_text}
            
            Write a summary that:
            1. Explains what the bill does in simple terms
            2. Highlights the main changes it would make
            3. Mentions who would be affected
            4. Notes any significant funding or timeline requirements
            
            Keep it concise but comprehensive, suitable for someone without legal expertise.
            """
            
            response = self.client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt
            )
            
            if not response or not response.text:
                return None
            
            return response.text.strip()
            
        except Exception as e:
            logging.error(f"Chunked summary generation error: {str(e)}")
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

