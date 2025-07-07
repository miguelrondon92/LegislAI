import os
import json
import logging
from typing import Dict, List, Optional, Tuple
from google import genai
import re
from datetime import datetime
from utils.bill_chunker import BillChunker, BillChunk

logger = logging.getLogger(__name__)

class BillAnalyzer:
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
        
        # Policy categories for classification
        self.policy_categories = [
            'healthcare', 'education', 'environment', 'economy', 'immigration',
            'defense', 'transportation', 'energy', 'agriculture', 'technology',
            'civil_rights', 'government_reform', 'taxation', 'housing', 'labor'
        ]
    
    def _clean_json_response(self, response_text: str) -> str:
        """Clean and extract JSON from AI response"""
        response_text = re.sub(r'```json\s*', '', response_text)
        response_text = re.sub(r'```\s*$', '', response_text)
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            return json_match.group()
        return response_text.strip()
    
    def categorize_bill(self, bill_text: str, bill_title: str) -> Dict:
        """Categorize a bill into policy domains using chunked analysis"""
        if not self.client:
            return {"categories": [], "confidence": 0.0, "reasoning": "Gemini API not available"}
        
        try:
            # Create chunks for analysis
            chunks = self.bill_chunker.chunk_bill(bill_text, bill_title)
            
            # Use the most important chunks for categorization
            important_chunks = sorted(chunks, key=lambda x: x.importance_score, reverse=True)[:5]
            
            chunk_texts = []
            for i, chunk in enumerate(important_chunks):
                chunk_texts.append(f"Chunk {i+1} ({chunk.chunk_type}):\n{chunk.content[:1500]}")
            
            combined_text = "\n\n---\n\n".join(chunk_texts)
            
            prompt = f"""
            Analyze the following congressional bill and categorize it into relevant policy domains.
            
            Bill Title: {bill_title}
            
            Bill Content (from {len(important_chunks)} key chunks):
            {combined_text}
            
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
            
            response = self.client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt
            )
            
            if not response or not response.text:
                return {"categories": [], "confidence": 0.0, "reasoning": "Empty response from Gemini"}
            
            cleaned_response = self._clean_json_response(response.text)
            result = json.loads(cleaned_response)
            return result
            
        except Exception as e:
            logger.error(f"Bill categorization failed: {e}")
            return {"categories": [], "confidence": 0.0, "reasoning": f"Analysis failed: {str(e)}"}
    
    def analyze_stakeholder_impact(self, bill_text: str, bill_title: str) -> Dict:
        """Analyze which stakeholders are affected by the bill using chunked analysis"""
        if not self.client:
            return {"stakeholders": {}, "reasoning": "Gemini API not available"}
        
        try:
            # Create chunks for analysis
            chunks = self.bill_chunker.chunk_bill(bill_text, bill_title)
            
            # Use the most important chunks for stakeholder analysis
            important_chunks = sorted(chunks, key=lambda x: x.importance_score, reverse=True)[:5]
            
            chunk_texts = []
            for i, chunk in enumerate(important_chunks):
                chunk_texts.append(f"Chunk {i+1} ({chunk.chunk_type}):\n{chunk.content[:1500]}")
            
            combined_text = "\n\n---\n\n".join(chunk_texts)
            
            prompt = f"""
            Analyze the stakeholder impact of this congressional bill based on the following chunks.
            
            Bill Title: {bill_title}
            
            Bill Content (from {len(important_chunks)} key chunks):
            {combined_text}
            
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
            
            response = self.client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt
            )
            
            if not response or not response.text:
                return {"stakeholders": {}, "reasoning": "Empty response from Gemini"}
            
            cleaned_response = self._clean_json_response(response.text)
            result = json.loads(cleaned_response)
            return result
            
        except Exception as e:
            logger.error(f"Stakeholder analysis failed: {e}")
            return {"stakeholders": {}, "reasoning": f"Analysis failed: {str(e)}"}
    
    def score_policy_alignment(self, bill_text: str, bill_title: str, user_preferences: Dict) -> Dict:
        """Score how well a bill aligns with user policy preferences using chunked analysis"""
        if not self.client or not user_preferences:
            return {"alignment_score": 0, "section_scores": {}, "reasoning": "Insufficient data for analysis"}
        
        try:
            # Create chunks for analysis
            chunks = self.bill_chunker.chunk_bill(bill_text, bill_title)
            
            # Use the most important chunks for alignment analysis
            important_chunks = sorted(chunks, key=lambda x: x.importance_score, reverse=True)[:5]
            
            chunk_texts = []
            for i, chunk in enumerate(important_chunks):
                chunk_texts.append(f"Chunk {i+1} ({chunk.chunk_type}):\n{chunk.content[:1500]}")
            
            combined_text = "\n\n---\n\n".join(chunk_texts)
            
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
            Analyze how well this congressional bill aligns with the user's policy preferences based on the following chunks.
            
            Bill Title: {bill_title}
            
            Bill Content (from {len(important_chunks)} key chunks):
            {combined_text}
            
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
            
            response = self.client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt
            )
            
            if not response or not response.text:
                return {"alignment_score": 0, "section_scores": {}, "reasoning": "Empty response from Gemini"}
            
            cleaned_response = self._clean_json_response(response.text)
            result = json.loads(cleaned_response)
            return result
            
        except Exception as e:
            logger.error(f"Policy alignment scoring failed: {e}")
            return {"alignment_score": 0, "section_scores": {}, "reasoning": f"Analysis failed: {str(e)}"}
    
    def extract_key_sections(self, bill_text: str) -> List[Dict]:
        """Extract and summarize key sections of a bill using chunked analysis"""
        if not self.client:
            return []
        
        try:
            # Create chunks for analysis
            chunks = self.bill_chunker.chunk_bill(bill_text, "")
            
            # Use the most important chunks for section extraction
            important_chunks = sorted(chunks, key=lambda x: x.importance_score, reverse=True)[:8]
            
            chunk_texts = []
            for i, chunk in enumerate(important_chunks):
                chunk_texts.append(f"Chunk {i+1} ({chunk.chunk_type}):\n{chunk.content[:1200]}")
            
            combined_text = "\n\n---\n\n".join(chunk_texts)
            
            prompt = f"""
            Analyze this congressional bill text and extract the key sections with plain-language summaries based on the following chunks.
            
            Bill Content (from {len(important_chunks)} key chunks):
            {combined_text}
            
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
            
            response = self.client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt
            )
            
            if not response or not response.text:
                return []
            
            cleaned_response = self._clean_json_response(response.text)
            result = json.loads(cleaned_response)
            return result.get("sections", [])
            
        except Exception as e:
            logger.error(f"Key section extraction failed: {e}")
            return []
    
    def generate_plain_language_summary(self, bill_text: str, bill_title: str) -> str:
        """Generate a plain language summary of the bill using chunked analysis"""
        if not self.client:
            return "AI analysis not available. Please check Gemini API configuration."
        
        try:
            # Create chunks for summary generation
            chunks = self.bill_chunker.chunk_bill(bill_text, bill_title)
            
            # Use the most important chunks for summary
            important_chunks = sorted(chunks, key=lambda x: x.importance_score, reverse=True)[:3]
            
            chunk_texts = []
            for i, chunk in enumerate(important_chunks):
                chunk_texts.append(f"Chunk {i+1} ({chunk.chunk_type}):\n{chunk.content[:2000]}")
            
            combined_text = "\n\n---\n\n".join(chunk_texts)
            
            prompt = f"""
            Create a clear, plain-language summary of this congressional bill based on the following chunks.
            
            Bill Title: {bill_title}
            
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
                return "Unable to generate summary: Empty response from Gemini"
            
            return response.text.strip()
            
        except Exception as e:
            logger.error(f"Summary generation failed: {e}")
            return f"Unable to generate summary: {str(e)}"

# Global instance
bill_analyzer = BillAnalyzer()
