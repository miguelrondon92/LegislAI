import json
import os
import logging
from typing import Dict, List, Optional, Tuple, Any
import google.generativeai as genai
# from openai import OpenAI  # Removed - using Gemini only
import re
from datetime import datetime
from utils.constants import FEDERAL_POLICY_CATEGORIES
from utils.bill_chunker import BillChunker, BillChunk
import time
import random

logger = logging.getLogger(__name__)

class AIAnalysisPartialError(Exception):
    """Exception raised when AI analysis is only partially completed due to rate limits"""
    def __init__(self, message, completion_percentage=0, completed_chunks=0, total_chunks=0):
        super().__init__(message)
        self.completion_percentage = completion_percentage
        self.completed_chunks = completed_chunks
        self.total_chunks = total_chunks

class EnhancedAIAnalyzer:
    """Enhanced AI-powered legislative analysis with hidden provision detection"""
    
    def __init__(self):
        self.api_key = os.environ.get('GEMINI_API_KEY')
        if not self.api_key:
            logging.warning("GEMINI_API_KEY not found. AI analysis will be disabled.")
            self.client = None
        else:
            genai.configure(api_key=self.api_key)
            # gemini-1.5-flash is no longer available on many API keys; 2.0 is used elsewhere in repo
            self.client = genai.GenerativeModel('gemini-2.0-flash')
        
        # Rate limiting configuration
        self.max_requests_per_minute = 15  # Free tier limit
        self.max_chunks_per_bill = 15  # Maximum chunks to analyze per bill
        self.max_tokens_per_request = 30000  # Conservative token limit
        self.estimated_tokens_per_char = 0.25  # Rough estimate: 1 token ≈ 4 characters
        
        # Initialize bill chunker with adaptive sizing
        self.bill_chunker = BillChunker(max_chunk_size=6000, overlap_size=800)
        
        # Use the standardized federal policy categories
        self.policy_categories = FEDERAL_POLICY_CATEGORIES
        
        # Hidden provision detection patterns
        self.suspicious_patterns = [
            r'notwithstanding\s+any\s+other\s+provision\s+of\s+law',
            r'waiver\s+of\s+requirements',
            r'exemption\s+from\s+review',
            r'expedited\s+process',
            r'emergency\s+authority',
            r'discretionary\s+power',
            r'delegation\s+of\s+authority',
            r'confidential\s+information',
            r'classified\s+provisions',
            r'executive\s+privilege',
            r'national\s+security\s+exception',
            r'emergency\s+declaration',
            r'fast\s+track',
            r'expedited\s+approval',
            r'bypass\s+normal\s+procedures',
            r'override\s+existing\s+law',
            r'sunset\s+provision',
            r'grandfather\s+clause',
            r'retroactive\s+application',
            r'hidden\s+funding',
            r'earmark\s+disguised',
            r'policy\s+rider',
            r'unrelated\s+provision',
            r'last\s+minute\s+amendment',
            r'omnibus\s+provision',
            r'consolidated\s+appropriations',
            r'continuing\s+resolution\s+provision',
            r'budget\s+reconciliation\s+provision'
        ]
        
        # Add backoff configuration
        self.max_retries = 3
        self.base_delay = 1.0  # Start with 1 second
        self.max_delay = 60.0  # Max delay of 60 seconds
        self.backoff_multiplier = 2.0
        self.jitter_factor = 0.1  # Add 10% jitter
        
        # Request tracking for rate limiting
        self.request_count = 0
        self.last_request_time = None
        self.requests_this_minute = 0
        self.minute_start_time = None
    
    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count for text"""
        return int(len(text) * self.estimated_tokens_per_char)
    
    def _calculate_optimal_chunk_size(self, total_text_length: int) -> int:
        """Calculate optimal chunk size based on total text length and API limits"""
        # Target: stay under max_chunks_per_bill and max_tokens_per_request
        max_chars_per_chunk = min(
            self.max_tokens_per_request / self.estimated_tokens_per_char,
            total_text_length / self.max_chunks_per_bill
        )
        
        # Ensure reasonable bounds
        min_chunk_size = 1000
        max_chunk_size = 8000
        
        optimal_size = max(min_chunk_size, min(max_chunk_size, int(max_chars_per_chunk)))
        
        logger.info(f"📏 Text length: {total_text_length:,} chars")
        logger.info(f"🎯 Optimal chunk size: {optimal_size:,} chars")
        logger.info(f"📊 Estimated chunks: {total_text_length // optimal_size}")
        
        return optimal_size
    
    def _check_rate_limit(self) -> bool:
        """Check if we're at or approaching rate limits"""
        current_time = time.time()
        
        # Reset minute counter if needed
        if not self.minute_start_time or current_time - self.minute_start_time >= 60:
            self.minute_start_time = current_time
            self.requests_this_minute = 0
        
        # Check if we're at the limit (never exceed)
        if self.requests_this_minute >= self.max_requests_per_minute:
            logger.warning(f"🚫 Rate limit reached: {self.requests_this_minute} requests this minute")
            return True
        
        # Check if we're approaching limit (within 2 requests)
        if self.requests_this_minute >= self.max_requests_per_minute - 2:
            logger.warning(f"⚠️ Very close to rate limit: {self.requests_this_minute}/{self.max_requests_per_minute} requests")
            return True
        
        # Warn if approaching limit (80% threshold)
        if self.requests_this_minute >= self.max_requests_per_minute * 0.8:
            logger.warning(f"⚠️ Approaching rate limit: {self.requests_this_minute}/{self.max_requests_per_minute} requests")
        
        return False
    
    def _record_request(self):
        """Record a request for rate limiting - NEVER call this without checking limits first"""
        current_time = time.time()
        
        # Reset minute counter if needed
        if not self.minute_start_time or current_time - self.minute_start_time >= 60:
            self.minute_start_time = current_time
            self.requests_this_minute = 0
        
        # Safety check - never exceed the limit
        if self.requests_this_minute >= self.max_requests_per_minute:
            logger.error(f"🚫 CRITICAL: Attempted to record request when already at limit!")
            logger.error(f"   Current: {self.requests_this_minute}, Max: {self.max_requests_per_minute}")
            return False
        
        self.requests_this_minute += 1
        self.request_count += 1
        self.last_request_time = current_time
        
        logger.debug(f"📊 Request recorded: {self.requests_this_minute}/{self.max_requests_per_minute} this minute")
        return True
    
    def _wait_for_rate_limit(self):
        """Wait if we're at rate limit"""
        if self._check_rate_limit():
            wait_time = 60 - (time.time() - self.minute_start_time)
            if wait_time > 0:
                logger.info(f"⏳ Waiting {wait_time:.1f} seconds for rate limit reset...")
                time.sleep(wait_time)
                self.minute_start_time = time.time()
                self.requests_this_minute = 0
    
    def analyze_bill(self, bill_or_text, title=None) -> Dict:
        """Perform comprehensive AI analysis with hidden provision detection"""
        start_time = time.time()  # Track processing time
        logger.info(f"[AI] Starting analysis for bill: {title}")
        
        if not self.client:
            logging.warning("Gemini client not available")
            return {}
        
        try:
            # Handle both bill objects and text inputs
            if hasattr(bill_or_text, 'get_bill_identifier'):
                bill = bill_or_text
                text_to_analyze = self._prepare_bill_text(bill)
                title = bill.title
                summary = bill.summary
            else:
                text_to_analyze = str(bill_or_text)
                title = title or "Unknown Bill"
                summary = ""
            
            logger.debug(f"[AI] Full text length: {len(text_to_analyze)}")
            
            if not text_to_analyze:
                logging.warning(f"No text available for analysis")
                return {}
            
            # Calculate optimal chunk size based on text length
            text_length = len(text_to_analyze)
            optimal_chunk_size = self._calculate_optimal_chunk_size(text_length)
            
            # Update chunker with optimal size
            self.bill_chunker.max_chunk_size = optimal_chunk_size
            
            # Chunk the bill text for analysis
            chunks = self.bill_chunker.chunk_bill(text_to_analyze, title, summary)
            logger.info(f"Created {len(chunks)} chunks for enhanced analysis")
            
            # Limit chunks to prevent rate limit issues
            if len(chunks) > self.max_chunks_per_bill:
                logger.warning(f"⚠️ Too many chunks ({len(chunks)}), limiting to {self.max_chunks_per_bill}")
                # Sort by importance and take the most important chunks
                chunks.sort(key=lambda x: x.importance_score, reverse=True)
                chunks = chunks[:self.max_chunks_per_bill]
                logger.info(f"📊 Using top {len(chunks)} most important chunks")
            
            # Estimate total tokens for all chunks
            total_estimated_tokens = sum(self._estimate_tokens(chunk.content) for chunk in chunks)
            logger.info(f"📊 Total estimated tokens: {total_estimated_tokens:,}")
            
            # Calculate how many API requests this analysis will need
            estimated_requests = self._estimate_analysis_requests(chunks)
            logger.info(f"📊 Estimated API requests for analysis: {estimated_requests}")
            
            # Use progressive analysis instead of all-or-nothing approach
            available_requests = self.max_requests_per_minute - self.requests_this_minute
            logger.info(f"📊 Available API requests: {available_requests}/{self.max_requests_per_minute}")
            
            if available_requests <= 2:
                logger.warning(f"⚠️ Very low quota remaining ({available_requests}), waiting for rate limit reset...")
                self._wait_for_rate_limit_reset()
                available_requests = self.max_requests_per_minute - self.requests_this_minute
                logger.info(f"✅ Rate limit reset, available requests: {available_requests}")
            
            # Progressive analysis: analyze what we can with available quota
            chunks_to_analyze = self._calculate_analyzable_chunks(chunks, available_requests)
            
            if not chunks_to_analyze:
                logger.warning(f"⚠️ No chunks can be analyzed with current quota. Consider running later or increasing rate limits.")
                # Return minimal analysis based on title and summary only
                return self._create_minimal_analysis(title, summary)
            
            # Perform enhanced analysis on available chunks
            analysis_results = {}
            logger.info(f"🔍 Starting progressive analysis of {len(chunks_to_analyze)} priority chunks...")
            
            # 1. Hidden provision detection (NEW) - use progressive chunks
            logger.info(f"   🔍 Analyzing hidden provisions...")
            hidden_analysis = self._detect_hidden_provisions(chunks_to_analyze, title)
            if hidden_analysis:
                analysis_results['hidden_provisions'] = hidden_analysis
            
            # 2. Anomaly detection in chunks (NEW) - use progressive chunks  
            logger.info(f"   🔍 Detecting anomalies...")
            anomalies = self._detect_anomalies(chunks_to_analyze, title)
            if anomalies:
                analysis_results['anomalies'] = anomalies
            
            # 3. Context-aware suspicious language detection (NEW) - use progressive chunks
            logger.info(f"   🔍 Checking suspicious language...")
            suspicious_language = self._detect_suspicious_language(chunks_to_analyze, title)
            if suspicious_language:
                analysis_results['suspicious_language'] = suspicious_language
            
            # 4. Cross-reference analysis (NEW) - use progressive chunks
            logger.info(f"   🔍 Analyzing cross-references...")
            cross_references = self._analyze_cross_references(chunks_to_analyze, title)
            if cross_references:
                analysis_results['cross_references'] = cross_references
            
            # 5. Impact assessment for hidden provisions (NEW)
            impact_assessment = self._assess_hidden_impact(chunks, title)
            if impact_assessment:
                analysis_results['hidden_impact_assessment'] = impact_assessment
            
            # 6. Standard analyses (enhanced) with null safety
            try:
                summary = self._generate_bill_summary_chunked(chunks, title)
                if summary and isinstance(summary, str):
                    analysis_results['summary'] = {
                        'main_summary': summary,
                        'key_provisions': [],
                        'funding_amounts': 'Unknown',
                        'implementation_timeline': 'Unknown',
                        'plain_language_explanation': summary
                    }
            except Exception as e:
                logger.error(f"Summary generation failed: {e}")
            
            try:
                logger.info(f"   🔍 Categorizing policy implications...")
                categories = self._categorize_bill_chunked(chunks_to_analyze, title)
                if categories and isinstance(categories, dict):
                    analysis_results['policy_implications'] = categories
            except Exception as e:
                logger.error(f"Categorization failed: {e}")
            
            try:
                logger.info(f"   🔍 Analyzing stakeholders...")
                stakeholders = self._analyze_stakeholders_chunked(chunks_to_analyze, title)
                if stakeholders and isinstance(stakeholders, dict):
                    analysis_results['stakeholders'] = stakeholders
            except Exception as e:
                logger.error(f"Stakeholder analysis failed: {e}")
            
            try:
                complexity = self._assess_complexity(text_to_analyze)
                if complexity is not None and isinstance(complexity, (int, float)):
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
            except Exception as e:
                logger.error(f"Complexity assessment failed: {e}")
            
            try:
                controversy = self._detect_controversy(text_to_analyze, title)
                if controversy is not None and isinstance(controversy, (int, float)):
                    analysis_results['controversy_score'] = controversy
            except Exception as e:
                logger.error(f"Controversy detection failed: {e}")
            
            # Add enhanced metadata including progressive analysis info
            analysis_results['generated_at'] = datetime.now().isoformat()
            analysis_results['analysis_method'] = 'enhanced_chunked_with_hidden_detection'
            analysis_results['chunks_analyzed'] = len(chunks_to_analyze)
            analysis_results['total_chunks_available'] = len(chunks)
            analysis_results['analysis_completeness'] = 'full' if len(chunks_to_analyze) == len(chunks) else 'partial'
            analysis_results['hidden_detection_enabled'] = True
            
            # Log final analysis status and handle partial completion
            if len(chunks_to_analyze) < len(chunks):
                completion_percentage = (len(chunks_to_analyze)/len(chunks)*100)
                logger.warning(f"⚠️ Partial analysis completed: {len(chunks_to_analyze)}/{len(chunks)} chunks analyzed due to API quota limits")
                logger.info(f"   📊 Analysis completeness: {completion_percentage:.1f}%")
                logger.info(f"   💡 Tip: Re-run analysis later for remaining {len(chunks) - len(chunks_to_analyze)} chunks")
                
                # Store partial analysis but raise exception for user notification
                analysis_results['is_partial'] = True
                analysis_results['completion_percentage'] = completion_percentage
                analysis_results['remaining_chunks'] = len(chunks) - len(chunks_to_analyze)
            else:
                logger.info(f"✅ Full analysis completed: All {len(chunks)} chunks analyzed successfully")
                analysis_results['is_partial'] = False
                analysis_results['completion_percentage'] = 100.0
                analysis_results['remaining_chunks'] = 0
            
            # Add quota usage info to results
            analysis_results['quota_usage'] = {
                'requests_used': self.requests_this_minute,
                'requests_available_at_start': available_requests,
                'analysis_was_limited_by_quota': len(chunks_to_analyze) < len(chunks)
            }
            
            # Calculate overall risk score
            risk_score = self._calculate_overall_risk_score(analysis_results)
            analysis_results['overall_risk_score'] = risk_score
            
            # If we have a bill object, store the analysis using new table structure
            if hasattr(bill_or_text, 'create_new_analysis_version') and analysis_results:
                try:
                    # Extract complexity and controversy scores with safe navigation
                    complexity_assessment = analysis_results.get('complexity_assessment', {})
                    complexity_score = None
                    if complexity_assessment and isinstance(complexity_assessment, dict):
                        complexity_score = complexity_assessment.get('complexity_score')
                    
                    controversy_score = analysis_results.get('controversy_score', 0.0)
                    if not isinstance(controversy_score, (int, float)):
                        controversy_score = 0.0
                    
                    # Get processing metadata
                    chunks_analyzed = len(chunks) if chunks else 0
                    processing_time = time.time() - start_time
                    
                    # Create new analysis version
                    bill_or_text.create_new_analysis_version(
                        analysis_data=analysis_results,
                        complexity_score=complexity_score,
                        controversy_score=controversy_score,
                        analysis_method='chunked',
                        chunks_analyzed=chunks_analyzed,
                        processing_time=processing_time
                    )
                    
                    # Extract and store summary data separately with null safety
                    summary_data = analysis_results.get('summary', {})
                    if summary_data and isinstance(summary_data, dict):
                        bill_or_text.create_new_summary_version(
                            summary_text=summary_data.get('main_summary'),
                            plain_language_summary=summary_data.get('plain_language_explanation'),
                            key_provisions=summary_data.get('key_provisions', []),
                            funding_amounts=summary_data.get('funding_amounts'),
                            implementation_timeline=summary_data.get('implementation_timeline'),
                            summary_type='ai_generated'
                        )
                    
                    # Store policy category mappings if available
                    if 'policy_implications' in analysis_results:
                        policy_data = analysis_results['policy_implications']
                        if 'categories' in policy_data and isinstance(policy_data['categories'], list):
                            self._store_policy_categories(bill_or_text, policy_data['categories'], analysis_results)
                    
                    # Update display_ready status after analysis is complete
                    if hasattr(bill_or_text, 'update_display_ready_status'):
                        status_changed = bill_or_text.update_display_ready_status()
                        if status_changed:
                            logger.info(f"Bill {bill_or_text.get_bill_identifier()} is now display ready")
                            
                            # Trigger notifications for newly analyzed bill
                            if hasattr(bill_or_text, 'id'):
                                try:
                                    from services.notification_helper import trigger_bill_analysis_notification_async
                                    trigger_bill_analysis_notification_async(bill_or_text.id)
                                    logger.info(f"Notifications triggered for bill {bill_or_text.get_bill_identifier()}")
                                except Exception as e:
                                    logger.warning(f"Could not trigger notifications for bill {bill_or_text.get_bill_identifier()}: {e}")
                
                except Exception as e:
                    logger.error(f"Error creating new database structure: {e}")
            elif hasattr(bill_or_text, 'set_ai_analysis'):
                # Fallback to old method for backward compatibility
                bill_or_text.set_ai_analysis(analysis_results)
                
                # Store policy category mappings for old method too
                if 'policy_implications' in analysis_results:
                    policy_data = analysis_results['policy_implications']
                    if 'categories' in policy_data and isinstance(policy_data['categories'], list):
                        self._store_policy_categories(bill_or_text, policy_data['categories'], analysis_results)
                
                # Update display_ready status for old method too
                if hasattr(bill_or_text, 'update_display_ready_status'):
                    status_changed = bill_or_text.update_display_ready_status()
                    if status_changed:
                        logger.info(f"Bill {bill_or_text.get_bill_identifier()} is now display ready")
                        
                        # Trigger notifications for newly analyzed bill (fallback case)
                        if hasattr(bill_or_text, 'id'):
                            try:
                                from services.notification_helper import trigger_bill_analysis_notification_async
                                trigger_bill_analysis_notification_async(bill_or_text.id)
                                logger.info(f"Notifications triggered for bill {bill_or_text.get_bill_identifier()}")
                            except Exception as e:
                                logger.warning(f"Could not trigger notifications for bill {bill_or_text.get_bill_identifier()}: {e}")
            
            logger.info("[AI] Analysis completed successfully.")
            
            # Check for high-risk bills and trigger special notifications
            if hasattr(bill_or_text, 'id') and analysis_results:
                try:
                    overall_risk_score = analysis_results.get('overall_risk_score', 0)
                    if overall_risk_score >= 0.7:  # High risk threshold
                        from services.notification_helper import trigger_high_risk_bill_notification
                        trigger_high_risk_bill_notification(bill_or_text.id, overall_risk_score)
                        logger.info(f"High-risk notification triggered for bill {bill_or_text.get_bill_identifier()} (risk: {overall_risk_score:.2f})")
                except Exception as e:
                    logger.warning(f"Could not trigger high-risk notifications: {e}")
            
            # Check if analysis was partial and raise exception for user notification
            if analysis_results.get('is_partial', False):
                completion_percentage = analysis_results.get('completion_percentage', 0)
                remaining_chunks = analysis_results.get('remaining_chunks', 0)
                completed_chunks = analysis_results.get('chunks_analyzed', 0)
                total_chunks = analysis_results.get('total_chunks_available', 0)
                raise AIAnalysisPartialError(
                    f"Bill analysis was only {completion_percentage:.1f}% complete due to AI API rate limits. {remaining_chunks} chunks remaining.",
                    completion_percentage=completion_percentage,
                    completed_chunks=completed_chunks,
                    total_chunks=total_chunks
                )
            
            return analysis_results
            
        except AIAnalysisPartialError:
            # Re-raise partial analysis errors - they should be handled by the caller
            raise
        except Exception as e:
            logger.error(f"[AI] Exception during analysis: {e}")
            return {}
    
    def _detect_hidden_provisions(self, chunks: List[BillChunk], title: str) -> Optional[Dict]:
        """Detect potentially hidden or sneaky provisions in bill chunks"""
        try:
            if not self.client:
                return None
            
            # Analyze each chunk for hidden provisions
            hidden_provisions = []
            suspicious_chunks = []
            
            for i, chunk in enumerate(chunks):
                chunk_analysis = self._analyze_chunk_for_hidden_provisions(chunk, i, title)
                if chunk_analysis and isinstance(chunk_analysis, dict):
                    hidden_provisions.append(chunk_analysis)
                    if chunk_analysis.get('risk_level', 'low') in ['medium', 'high']:
                        suspicious_chunks.append(i)
            
            # Cross-reference analysis between chunks
            cross_chunk_analysis = self._cross_reference_chunks_for_hidden_provisions(chunks, suspicious_chunks)
            
            return {
                'detected_provisions': hidden_provisions,
                'suspicious_chunk_indices': suspicious_chunks,
                'cross_chunk_analysis': cross_chunk_analysis,
                'total_suspicious_chunks': len(suspicious_chunks),
                'overall_hidden_risk_score': self._calculate_hidden_risk_score(hidden_provisions)
            }
            
        except Exception as e:
            logging.error(f"Hidden provision detection error: {str(e)}")
            return None
    
    def _analyze_chunk_for_hidden_provisions(self, chunk: BillChunk, chunk_index: int, title: str) -> Optional[Dict]:
        """Analyze a single chunk for hidden provisions"""
        try:
            prompt = f"""
            Analyze this bill chunk for potentially hidden, sneaky, or buried provisions that might not be immediately obvious.
            
            Bill Title: {title}
            Chunk Type: {chunk.chunk_type}
            Chunk Index: {chunk_index}
            
            Bill Content:
            {chunk.content[:3000]}
            
            Look for:
            1. Provisions that seem unrelated to the main bill purpose
            2. Language that grants broad discretionary powers
            3. Exemptions or waivers that bypass normal procedures
            4. Funding provisions that seem hidden or disguised
            5. Policy riders that don't relate to the main bill
            6. Provisions that limit oversight or review
            7. Retroactive applications or grandfather clauses
            8. Emergency authorities or expedited processes
            9. Confidentiality or classification provisions
            10. Delegations of authority that seem excessive
            
            Respond in JSON format:
            {{
                "risk_level": "low|medium|high",
                "suspicious_provisions": [
                    {{
                        "type": "description of provision type",
                        "text": "exact text or description",
                        "risk_factors": ["list of risk factors"],
                        "potential_impact": "description of potential impact",
                        "recommendation": "what to watch for"
                    }}
                ],
                "overall_assessment": "brief assessment of this chunk",
                "confidence_score": 0.0-1.0
            }}
            """
            
            response = self.client.generate_content(prompt)
            
            if not response or not response.text:
                return None
            
            # Clean and parse JSON response
            cleaned_response = self._clean_json_response(response.text)
            try:
                result = json.loads(cleaned_response)
                result['chunk_index'] = chunk_index
                result['chunk_type'] = chunk.chunk_type
                return result
            except json.JSONDecodeError:
                logging.warning(f"Failed to parse hidden provision analysis for chunk {chunk_index}")
                return None
                
        except Exception as e:
            logging.error(f"Chunk hidden provision analysis error: {str(e)}")
            return None
    
    def _cross_reference_chunks_for_hidden_provisions(self, chunks: List[BillChunk], suspicious_chunks: List[int]) -> Optional[Dict]:
        """Cross-reference chunks to find hidden provisions that span multiple sections"""
        try:
            if len(suspicious_chunks) < 2:
                return None
            
            # Get suspicious chunk contents
            suspicious_contents = []
            for idx in suspicious_chunks:
                if idx < len(chunks):
                    suspicious_contents.append(f"Chunk {idx} ({chunks[idx].chunk_type}): {chunks[idx].content[:1500]}")
            
            combined_content = "\n\n---\n\n".join(suspicious_contents)
            
            prompt = f"""
            Analyze these suspicious bill chunks together to identify hidden provisions that might span multiple sections or be connected across chunks.
            
            Suspicious Chunks Content:
            {combined_content}
            
            Look for:
            1. Provisions that reference each other across chunks
            2. Hidden funding that's split across multiple sections
            3. Policy changes that are implemented piecemeal across chunks
            4. Oversight limitations that are distributed across sections
            5. Emergency authorities that build upon each other
            6. Delegations that compound across multiple provisions
            
            Respond in JSON format:
            {{
                "cross_chunk_provisions": [
                    {{
                        "provision_type": "description",
                        "involved_chunks": [chunk_indices],
                        "combined_impact": "description",
                        "risk_level": "low|medium|high",
                        "detection_difficulty": "easy|medium|hard"
                    }}
                ],
                "overall_pattern": "description of any overall pattern",
                "recommendations": ["list of recommendations"]
            }}
            """
            
            response = self.client.generate_content(prompt)
            
            if not response or not response.text:
                return None
            
            cleaned_response = self._clean_json_response(response.text)
            try:
                return json.loads(cleaned_response)
            except json.JSONDecodeError:
                logging.warning("Failed to parse cross-chunk analysis")
                return None
                
        except Exception as e:
            logging.error(f"Cross-reference analysis error: {str(e)}")
            return None
    
    def _detect_anomalies(self, chunks: List[BillChunk], title: str) -> Optional[Dict]:
        """Detect anomalies in bill structure and content"""
        try:
            if not self.client:
                return None
            
            # Analyze chunk patterns and content for anomalies
            chunk_summaries = []
            for i, chunk in enumerate(chunks):
                chunk_summaries.append(f"Chunk {i}: Type={chunk.chunk_type}, Length={len(chunk.content)}, Score={chunk.importance_score}")
            
            chunk_info = "\n".join(chunk_summaries)
            
            prompt = f"""
            Analyze this bill's chunk structure and content for anomalies that might indicate hidden provisions or unusual legislative tactics.
            
            Bill Title: {title}
            Number of Chunks: {len(chunks)}
            
            Chunk Information:
            {chunk_info}
            
            Look for anomalies such as:
            1. Unusually long or short chunks
            2. Chunks with very high or low importance scores
            3. Unusual distribution of content types
            4. Chunks that seem out of place
            5. Patterns that suggest rushed or last-minute additions
            6. Unusual language complexity variations
            7. Inconsistent formatting or structure
            
            Respond in JSON format:
            {{
                "detected_anomalies": [
                    {{
                        "type": "anomaly type",
                        "description": "description",
                        "affected_chunks": [chunk_indices],
                        "significance": "low|medium|high",
                        "potential_implications": "description"
                    }}
                ],
                "overall_anomaly_score": 0.0-1.0,
                "recommendations": ["list of recommendations"]
            }}
            """
            
            response = self.client.generate_content(prompt)
            
            if not response or not response.text:
                return None
            
            cleaned_response = self._clean_json_response(response.text)
            try:
                return json.loads(cleaned_response)
            except json.JSONDecodeError:
                logging.warning("Failed to parse anomaly detection")
                return None
                
        except Exception as e:
            logging.error(f"Anomaly detection error: {str(e)}")
            return None
    
    def _detect_suspicious_language(self, chunks: List[BillChunk], title: str) -> Optional[Dict]:
        """Detect suspicious language patterns using regex and AI analysis"""
        try:
            suspicious_findings = []
            
            # Pattern-based detection
            for i, chunk in enumerate(chunks):
                chunk_findings = {
                    'chunk_index': i,
                    'chunk_type': chunk.chunk_type,
                    'pattern_matches': [],
                    'ai_analysis': None
                }
                
                # Check for suspicious patterns
                for pattern in self.suspicious_patterns:
                    matches = re.findall(pattern, chunk.content, re.IGNORECASE)
                    if matches:
                        chunk_findings['pattern_matches'].append({
                            'pattern': pattern,
                            'matches': matches,
                            'context': self._get_context_around_matches(chunk.content, pattern)
                        })
                
                if chunk_findings['pattern_matches']:
                    suspicious_findings.append(chunk_findings)
            
            # AI-based suspicious language analysis
            if self.client and suspicious_findings:
                ai_analysis = self._ai_analyze_suspicious_language(chunks, suspicious_findings, title)
                return {
                    'pattern_based_findings': suspicious_findings,
                    'ai_analysis': ai_analysis,
                    'total_suspicious_chunks': len(suspicious_findings)
                }
            
            return {
                'pattern_based_findings': suspicious_findings,
                'ai_analysis': None,
                'total_suspicious_chunks': len(suspicious_findings)
            }
            
        except Exception as e:
            logging.error(f"Suspicious language detection error: {str(e)}")
            return None
    
    def _ai_analyze_suspicious_language(self, chunks: List[BillChunk], suspicious_findings: List[Dict], title: str) -> Optional[Dict]:
        """Use AI to analyze suspicious language patterns"""
        try:
            # Get suspicious chunks for AI analysis
            suspicious_chunks = []
            for finding in suspicious_findings:
                chunk_idx = finding['chunk_index']
                if chunk_idx < len(chunks):
                    suspicious_chunks.append(f"Chunk {chunk_idx}: {chunks[chunk_idx].content[:2000]}")
            
            combined_content = "\n\n---\n\n".join(suspicious_chunks)
            
            prompt = f"""
            Analyze these bill chunks that contain suspicious language patterns for potential hidden provisions or concerning legislative tactics.
            
            Bill Title: {title}
            
            Suspicious Content:
            {combined_content}
            
            Analyze for:
            1. Hidden policy changes disguised in technical language
            2. Broad discretionary powers that could be misused
            3. Provisions that bypass normal oversight
            4. Funding mechanisms that hide true costs
            5. Emergency authorities that seem excessive
            6. Provisions that limit transparency or accountability
            
            Respond in JSON format:
            {{
                "suspicious_provisions": [
                    {{
                        "type": "provision type",
                        "risk_level": "low|medium|high",
                        "description": "description",
                        "potential_abuse": "how it could be abused",
                        "recommendation": "what to watch for"
                    }}
                ],
                "overall_assessment": "overall assessment",
                "risk_score": 0.0-1.0
            }}
            """
            
            response = self.client.generate_content(prompt)
            
            if not response or not response.text:
                return None
            
            cleaned_response = self._clean_json_response(response.text)
            try:
                return json.loads(cleaned_response)
            except json.JSONDecodeError:
                logging.warning("Failed to parse AI suspicious language analysis")
                return None
                
        except Exception as e:
            logging.error(f"AI suspicious language analysis error: {str(e)}")
            return None
    
    def _get_context_around_matches(self, text: str, pattern: str, context_chars: int = 200) -> List[str]:
        """Get context around pattern matches"""
        contexts = []
        for match in re.finditer(pattern, text, re.IGNORECASE):
            start = max(0, match.start() - context_chars)
            end = min(len(text), match.end() + context_chars)
            context = text[start:end]
            contexts.append(context)
        return contexts
    
    def _analyze_cross_references(self, chunks: List[BillChunk], title: str) -> Optional[Dict]:
        """Analyze cross-references between bill sections and external laws"""
        try:
            if not self.client:
                return None
            
            # Extract potential cross-references
            cross_ref_patterns = [
                r'section\s+\d+',
                r'title\s+\d+',
                r'chapter\s+\d+',
                r'act\s+of\s+\d{4}',
                r'public\s+law\s+\d+-\d+',
                r'usc\s+\d+',
                r'cfr\s+\d+',
                r'amends\s+section',
                r'repeals\s+section',
                r'references\s+section'
            ]
            
            cross_refs = []
            for i, chunk in enumerate(chunks):
                chunk_refs = []
                for pattern in cross_ref_patterns:
                    matches = re.findall(pattern, chunk.content, re.IGNORECASE)
                    if matches:
                        chunk_refs.extend(matches)
                
                if chunk_refs:
                    cross_refs.append({
                        'chunk_index': i,
                        'chunk_type': chunk.chunk_type,
                        'references': chunk_refs
                    })
            
            if not cross_refs:
                return None
            
            # AI analysis of cross-references
            ref_content = []
            for ref in cross_refs:
                chunk_idx = ref['chunk_index']
                if chunk_idx < len(chunks):
                    ref_content.append(f"Chunk {chunk_idx}: {chunks[chunk_idx].content[:1500]}")
            
            combined_content = "\n\n---\n\n".join(ref_content)
            
            prompt = f"""
            Analyze these bill chunks that contain cross-references to other laws and regulations for potential hidden provisions or concerning changes.
            
            Bill Title: {title}
            
            Content with Cross-References:
            {combined_content}
            
            Look for:
            1. References that modify existing laws in unexpected ways
            2. Cross-references that grant new authorities
            3. Amendments that are buried in technical language
            4. Repeals of important provisions
            5. References that bypass normal legislative procedures
            6. Changes to unrelated laws through this bill
            
            Respond in JSON format:
            {{
                "concerning_references": [
                    {{
                        "reference_type": "type of reference",
                        "potential_impact": "description",
                        "risk_level": "low|medium|high",
                        "recommendation": "what to investigate"
                    }}
                ],
                "overall_assessment": "overall assessment",
                "recommendations": ["list of recommendations"]
            }}
            """
            
            response = self.client.generate_content(prompt)
            
            if not response or not response.text:
                return None
            
            cleaned_response = self._clean_json_response(response.text)
            try:
                result = json.loads(cleaned_response)
                result['cross_references_found'] = cross_refs
                return result
            except json.JSONDecodeError:
                logging.warning("Failed to parse cross-reference analysis")
                return None
                
        except Exception as e:
            logging.error(f"Cross-reference analysis error: {str(e)}")
            return None
    
    def _assess_hidden_impact(self, chunks: List[BillChunk], title: str) -> Optional[Dict]:
        """Assess the potential impact of hidden provisions"""
        try:
            if not self.client:
                return None
            
            # Use important chunks for impact assessment
            important_chunks = sorted(chunks, key=lambda x: x.importance_score, reverse=True)[:5]
            
            chunk_texts = []
            for i, chunk in enumerate(important_chunks):
                chunk_texts.append(f"Chunk {i} ({chunk.chunk_type}): {chunk.content[:2000]}")
            
            combined_text = "\n\n---\n\n".join(chunk_texts)
            
            prompt = f"""
            Assess the potential impact of any hidden or buried provisions in this bill.
            
            Bill Title: {title}
            
            Bill Content (from important chunks):
            {combined_text}
            
            Assess for:
            1. Economic impact of hidden provisions
            2. Social and community impact
            3. Environmental impact
            4. Impact on civil liberties and rights
            5. Impact on government transparency
            6. Impact on oversight and accountability
            7. Long-term consequences
            8. Unintended consequences
            
            Respond in JSON format:
            {{
                "impact_assessment": {{
                    "economic_impact": "description",
                    "social_impact": "description", 
                    "environmental_impact": "description",
                    "civil_liberties_impact": "description",
                    "transparency_impact": "description",
                    "oversight_impact": "description",
                    "long_term_consequences": "description",
                    "unintended_consequences": "description"
                }},
                "overall_impact_score": 0.0-1.0,
                "risk_factors": ["list of risk factors"],
                "recommendations": ["list of recommendations"]
            }}
            """
            
            response = self.client.generate_content(prompt)
            
            if not response or not response.text:
                return None
            
            cleaned_response = self._clean_json_response(response.text)
            try:
                return json.loads(cleaned_response)
            except json.JSONDecodeError:
                logging.warning("Failed to parse hidden impact assessment")
                return None
                
        except Exception as e:
            logging.error(f"Hidden impact assessment error: {str(e)}")
            return None
    
    def _calculate_hidden_risk_score(self, hidden_provisions: List[Dict]) -> float:
        """Calculate overall risk score for hidden provisions"""
        if not hidden_provisions:
            return 0.0
        
        risk_scores = []
        for provision in hidden_provisions:
            if provision and isinstance(provision, dict):
                risk_level = provision.get('risk_level', 'low')
                confidence = provision.get('confidence_score', 0.5)
                
                risk_value = {
                    'low': 0.2,
                    'medium': 0.5,
                    'high': 0.8
                }.get(risk_level, 0.2)
                
                risk_scores.append(risk_value * confidence)
        
        return sum(risk_scores) / len(risk_scores) if risk_scores else 0.0
    
    def _calculate_overall_risk_score(self, analysis_results: Dict) -> float:
        """Calculate overall risk score combining all analysis components"""
        risk_factors = []
        
        # Hidden provisions risk
        if 'hidden_provisions' in analysis_results:
            hidden_prov_data = analysis_results['hidden_provisions']
            if hidden_prov_data and isinstance(hidden_prov_data, dict):
                hidden_risk = hidden_prov_data.get('overall_hidden_risk_score', 0.0)
                risk_factors.append(hidden_risk * 0.4)  # 40% weight
        
        # Anomalies risk
        if 'anomalies' in analysis_results:
            anomalies_data = analysis_results['anomalies']
            if anomalies_data and isinstance(anomalies_data, dict):
                anomaly_risk = anomalies_data.get('overall_anomaly_score', 0.0)
                risk_factors.append(anomaly_risk * 0.2)  # 20% weight
        
        # Suspicious language risk
        if 'suspicious_language' in analysis_results:
            suspicious_lang_data = analysis_results['suspicious_language']
            if suspicious_lang_data and isinstance(suspicious_lang_data, dict):
                ai_analysis = suspicious_lang_data.get('ai_analysis', {})
                if ai_analysis and isinstance(ai_analysis, dict):
                    suspicious_risk = ai_analysis.get('risk_score', 0.0)
                    risk_factors.append(suspicious_risk * 0.2)  # 20% weight
        
        # Controversy risk
        if 'controversy_score' in analysis_results:
            controversy_risk = analysis_results['controversy_score']
            risk_factors.append(controversy_risk * 0.1)  # 10% weight
        
        # Complexity risk
        if 'complexity_assessment' in analysis_results:
            complexity_risk = analysis_results['complexity_assessment'].get('complexity_score', 0.0)
            risk_factors.append(complexity_risk * 0.1)  # 10% weight
        
        return sum(risk_factors) if risk_factors else 0.0
    
    # Include all the standard analysis methods from the original AIAnalyzer
    def _prepare_bill_text(self, bill) -> str:
        """Prepare bill text for analysis - no truncation"""
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
            
            response = self.client.generate_content(prompt)
            
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
                chunk_header = f"Chunk {i+1} ({chunk.chunk_type})"
                if hasattr(chunk, 'section_title') and chunk.section_title:
                    chunk_header += f" - {chunk.section_title}"
                if hasattr(chunk, 'section_number') and chunk.section_number:
                    chunk_header += f" (Section {chunk.section_number})"
                chunk_texts.append(f"{chunk_header}:\n{chunk.content[:1500]}")
            
            combined_text = "\n\n---\n\n".join(chunk_texts)
            
            prompt = f"""
            Categorize this congressional bill into the most relevant policy domains from the following list:
            {categories_list}
            
            Bill Title: {title}
            
            Bill Content (from {len(important_chunks)} key chunks):
            {combined_text}
            
            Respond in JSON format with categories and confidence scores:
            {{
                "primary_category": "most relevant category",
                "secondary_categories": ["list of other relevant categories"],
                "category_breakdown": {{
                    "category_name": {{
                        "relevance_score": 0.0-1.0,
                        "reasoning": "why this category is relevant",
                        "section": "section number if applicable",
                        "title": "section title if applicable"
                    }}
                }},
                "overall_assessment": "brief assessment of bill's policy focus"
            }}
            """
            
            response = self.client.generate_content(prompt)
            
            if not response or not response.text:
                logging.warning("Empty response from Gemini for categorization")
                return None
            
            # Clean and parse JSON response
            cleaned_response = self._clean_json_response(response.text)
            try:
                return json.loads(cleaned_response)
            except json.JSONDecodeError:
                logging.warning("Failed to parse categorization response")
                return None
                
        except Exception as e:
            logging.error(f"Chunked categorization error: {str(e)}")
            return None
    
    def _analyze_stakeholders_chunked(self, chunks: List[BillChunk], title: str) -> Optional[Dict]:
        """Analyze stakeholders using chunked analysis"""
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
            Analyze the stakeholders affected by this congressional bill.
            
            Bill Title: {title}
            
            Bill Content (from {len(important_chunks)} key chunks):
            {combined_text}
            
            Identify and analyze:
            1. Direct beneficiaries
            2. Groups that may be negatively affected
            3. Industry stakeholders
            4. Government agencies involved
            5. Geographic regions affected
            6. Economic sectors impacted
            
            Respond in JSON format:
            {{
                "stakeholders": {{
                    "beneficiaries": ["list of beneficiaries"],
                    "negatively_affected": ["list of negatively affected groups"],
                    "industry_stakeholders": ["list of industry stakeholders"],
                    "government_agencies": ["list of government agencies"],
                    "geographic_regions": ["list of affected regions"],
                    "economic_sectors": ["list of affected sectors"]
                }},
                "impact_assessment": "overall assessment of stakeholder impacts",
                "key_considerations": ["list of key considerations"]
            }}
            """
            
            response = self.client.generate_content(prompt)
            
            if not response or not response.text:
                logging.warning("Empty response from Gemini for stakeholder analysis")
                return None
            
            # Clean and parse JSON response
            cleaned_response = self._clean_json_response(response.text)
            try:
                return json.loads(cleaned_response)
            except json.JSONDecodeError:
                logging.warning("Failed to parse stakeholder analysis response")
                return None
                
        except Exception as e:
            logging.error(f"Chunked stakeholder analysis error: {str(e)}")
            return None
    
    def _clean_json_response(self, response_text: str) -> str:
        """Clean and extract JSON from AI response"""
        # Remove markdown code blocks
        response_text = re.sub(r'```json\s*', '', response_text)
        response_text = re.sub(r'```\s*$', '', response_text)
        
        # Find JSON object
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            return json_match.group()
        
        return response_text.strip()
    
    def _assess_complexity(self, bill_text: str) -> Optional[float]:
        """Assess bill complexity"""
        try:
            if not self.client:
                logger.warning("Complexity assessment: No Gemini client available")
                return None
            
            # Check if we're at rate limit and wait if needed
            if self._check_rate_limit():
                logger.warning("Complexity assessment: Rate limit reached, waiting for reset...")
                self._wait_for_rate_limit()
                logger.info("Complexity assessment: Rate limit reset, proceeding")
            
            # Use a sample of the text for complexity assessment
            sample_text = bill_text[:5000] if len(bill_text) > 5000 else bill_text
            
            prompt = f"""
            Assess the complexity of this congressional bill on a scale of 0.0 to 1.0, where 0.0 is very simple and 1.0 is extremely complex.
            
            Bill Text Sample:
            {sample_text}
            
            Consider factors like:
            - Technical language and jargon
            - Number of cross-references
            - Length and scope
            - Implementation complexity
            - Regulatory requirements
            
            Respond with only a number between 0.0 and 1.0.
            """
            
            # Record the request for rate limiting
            if not self._record_request():
                logger.warning("Complexity assessment: Failed to record request - quota exhausted")
                return None
            
            logger.debug("Complexity assessment: Making Gemini API call")
            response = self.client.generate_content(prompt)
            
            if not response:
                logger.warning("Complexity assessment: No response from Gemini")
                return None
                
            if not response.text:
                logger.warning("Complexity assessment: Empty response text from Gemini")
                return None
            
            # Extract numeric response
            try:
                response_text = response.text.strip()
                logger.debug(f"Complexity assessment: Raw response: '{response_text}'")
                complexity_score = float(response_text)
                clamped_score = max(0.0, min(1.0, complexity_score))  # Clamp between 0 and 1
                logger.info(f"Complexity assessment: Success - score: {clamped_score}")
                return clamped_score
            except ValueError as ve:
                logger.error(f"Complexity assessment: Failed to parse response '{response_text}': {ve}")
                return None
                
        except Exception as e:
            logger.error(f"Complexity assessment error: {str(e)}")
            return None
    
    def _detect_controversy(self, bill_text: str, title: str) -> Optional[float]:
        """Detect controversy level"""
        try:
            if not self.client:
                return None
            
            # Use a sample of the text for controversy detection
            sample_text = bill_text[:5000] if len(bill_text) > 5000 else bill_text
            
            prompt = f"""
            Assess the potential controversy level of this congressional bill on a scale of 0.0 to 1.0, where 0.0 is uncontroversial and 1.0 is highly controversial.
            
            Bill Title: {title}
            Bill Text Sample:
            {sample_text}
            
            Consider factors like:
            - Polarizing policy positions
            - Impact on civil liberties
            - Economic implications
            - Social and cultural implications
            - Partisan implications
            
            Respond with only a number between 0.0 and 1.0.
            """
            
            response = self.client.generate_content(prompt)
            
            if not response or not response.text:
                return None
            
            # Extract numeric response
            try:
                controversy_score = float(response.text.strip())
                return max(0.0, min(1.0, controversy_score))  # Clamp between 0 and 1
            except ValueError:
                return None
                
        except Exception as e:
            logging.error(f"Controversy detection error: {str(e)}")
            return None
    
    def calculate_alignment_score(self, user_preferences: Dict, bill_categories: Dict) -> float:
        """Calculate alignment between user preferences and bill categories"""
        try:
            if not user_preferences or not bill_categories:
                return 0.0
            
            # Extract user's preferred categories
            user_categories = user_preferences.get('policy_categories', [])
            if not user_categories:
                return 0.0
            
            # Extract bill's primary and secondary categories
            bill_primary = bill_categories.get('primary_category', '')
            bill_secondary = bill_categories.get('secondary_categories', [])
            
            # Calculate alignment score
            alignment_score = 0.0
            total_weight = 0.0
            
            # Primary category gets higher weight
            if bill_primary in user_categories:
                alignment_score += 0.7
                total_weight += 0.7
            
            # Secondary categories get lower weight
            for category in bill_secondary:
                if category in user_categories:
                    alignment_score += 0.3
                    total_weight += 0.3
            
            # Normalize score
            if total_weight > 0:
                return alignment_score / total_weight
            
            return 0.0
            
        except Exception as e:
            logging.error(f"Alignment score calculation error: {str(e)}")
            return 0.0

    def _call_ai_model(self, prompt):
        logger.debug(f"[AI] Calling model with prompt length: {len(prompt)}")
        
        # Check rate limits before making request
        self._wait_for_rate_limit()
        
        # Estimate tokens for this request
        estimated_tokens = self._estimate_tokens(prompt)
        logger.debug(f"[AI] Estimated tokens: {estimated_tokens:,}")
        
        # Check if this request would exceed token limits
        if estimated_tokens > self.max_tokens_per_request:
            logger.warning(f"⚠️ Request too large: {estimated_tokens:,} tokens (limit: {self.max_tokens_per_request:,})")
            return None
        
        for attempt in range(self.max_retries + 1):
            try:
                # Double-check rate limit before making request
                if self._check_rate_limit():
                    logger.error(f"🚫 Rate limit check failed on attempt {attempt + 1}")
                    return None
                
                # Record the request for rate limiting (with safety check)
                if not self._record_request():
                    logger.error(f"🚫 Failed to record request due to rate limit on attempt {attempt + 1}")
                    return None
                
                response = self.client.generate_content(prompt)
                logger.debug(f"[AI] Model raw API response: {str(response)[:2000]}... (truncated)")
                
                if hasattr(response, 'error') and response.error:
                    logger.error(f"[AI] Model error: {response.error}")
                    
                    # Check if it's a 429 rate limit error
                    if hasattr(response.error, 'code') and response.error.code == 429:
                        if attempt < self.max_retries:
                            delay = self._calculate_backoff_delay(attempt)
                            logger.warning(f"[AI] Rate limited (429). Attempt {attempt + 1}/{self.max_retries + 1}. "
                                         f"Waiting {delay:.1f} seconds before retry...")
                            time.sleep(delay)
                            continue
                        else:
                            logger.error(f"[AI] Rate limit exceeded after {self.max_retries + 1} attempts. "
                                       f"Stopping analysis to avoid further API abuse.")
                            return None
                    else:
                        # Non-429 error, don't retry
                        return None
                
                if hasattr(response, 'quota') and response.quota:
                    logger.warning(f"[AI] Model quota info: {response.quota}")
                
                return response
                
            except Exception as e:
                logger.error(f"[AI] Exception during model call (attempt {attempt + 1}): {e}")
                
                # Check if it's a 429 error in the exception
                if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                    if attempt < self.max_retries:
                        delay = self._calculate_backoff_delay(attempt)
                        logger.warning(f"[AI] Rate limited (429) via exception. Attempt {attempt + 1}/{self.max_retries + 1}. "
                                     f"Waiting {delay:.1f} seconds before retry...")
                        time.sleep(delay)
                        continue
                    else:
                        logger.error(f"[AI] Rate limit exceeded after {self.max_retries + 1} attempts. "
                                   f"Stopping analysis to avoid further API abuse.")
                        return None
                else:
                    # Non-429 exception, don't retry
                    return None
        
        return None
    
    def _calculate_backoff_delay(self, attempt: int) -> float:
        """Calculate exponential backoff delay with jitter"""
        # Exponential backoff: base_delay * (multiplier ^ attempt)
        delay = min(self.base_delay * (self.backoff_multiplier ** attempt), self.max_delay)
        
        # Add jitter to prevent thundering herd
        jitter = delay * self.jitter_factor * random.uniform(-1, 1)
        delay += jitter
        
        return max(0.1, delay)  # Ensure minimum delay of 0.1 seconds
    
    def get_rate_limit_status(self) -> Dict:
        """Get current rate limiting status"""
        current_time = time.time()
        
        # Calculate time until rate limit reset
        time_until_reset = 0
        if self.minute_start_time:
            time_until_reset = max(0, 60 - (current_time - self.minute_start_time))
        
        remaining_requests = max(0, self.max_requests_per_minute - self.requests_this_minute)
        
        return {
            'requests_this_minute': self.requests_this_minute,
            'max_requests_per_minute': self.max_requests_per_minute,
            'remaining_requests': remaining_requests,
            'total_requests': self.request_count,
            'time_until_reset': time_until_reset,
            'is_at_limit': self.requests_this_minute >= self.max_requests_per_minute,
            'is_approaching_limit': self.requests_this_minute >= self.max_requests_per_minute - 2,
            'last_request_time': self.last_request_time,
            'rate_limit_percentage': (self.requests_this_minute / self.max_requests_per_minute) * 100,
            'safe_remaining_requests': max(0, remaining_requests - 2)  # Leave 2 request buffer
        }
    
    def get_quota_info(self) -> Dict:
        """Get detailed quota information for planning"""
        status = self.get_rate_limit_status()
        
        return {
            'current_usage': {
                'requests_this_minute': status['requests_this_minute'],
                'max_requests_per_minute': status['max_requests_per_minute'],
                'remaining_requests': status['remaining_requests'],
                'safe_remaining_requests': status['safe_remaining_requests'],
                'percentage_used': status['rate_limit_percentage']
            },
            'limits': {
                'max_chunks_per_bill': self.max_chunks_per_bill,
                'max_tokens_per_request': self.max_tokens_per_request,
                'max_requests_per_minute': self.max_requests_per_minute
            },
            'timing': {
                'time_until_reset': status['time_until_reset'],
                'last_request_time': status['last_request_time']
            },
            'status': {
                'is_at_limit': status['is_at_limit'],
                'is_approaching_limit': status['is_approaching_limit'],
                'can_handle_large_bill': status['safe_remaining_requests'] >= 10,
                'can_handle_small_bill': status['safe_remaining_requests'] >= 5
            }
        }
    
    def reset_rate_limit_counters(self):
        """Reset rate limit counters (useful for testing or manual reset)"""
        self.requests_this_minute = 0
        self.minute_start_time = time.time()
        self.request_count = 0
        self.last_request_time = None
        logger.info("✅ Rate limit counters reset")
    
    def _estimate_analysis_requests(self, chunks: List[BillChunk]) -> int:
        """Estimate how many API requests will be needed for analysis"""
        # Each chunk typically needs multiple analysis types
        requests_per_chunk = 5  # Hidden provisions, summary, categories, stakeholders, etc.
        base_requests = len(chunks) * requests_per_chunk
        
        # Add requests for cross-chunk analysis
        cross_chunk_requests = max(1, len(chunks) // 3)  # Cross-reference analysis
        
        # Add requests for overall analysis
        overall_requests = 3  # Final summary, risk assessment, etc.
        
        total_requests = base_requests + cross_chunk_requests + overall_requests
        
        logger.debug(f"📊 Request estimation: {len(chunks)} chunks × {requests_per_chunk} + {cross_chunk_requests} cross-chunk + {overall_requests} overall = {total_requests}")
        
        return total_requests
    
    def _can_handle_analysis(self, estimated_requests: int) -> bool:
        """Check if we have enough API quota to handle this analysis"""
        remaining_requests = self.max_requests_per_minute - self.requests_this_minute
        
        # Add safety margin (leave 2 requests buffer)
        safe_remaining = max(0, remaining_requests - 2)
        
        can_handle = estimated_requests <= safe_remaining
        
        if not can_handle:
            logger.warning(f"⚠️ Analysis requires {estimated_requests} requests but only {safe_remaining} available")
            logger.warning(f"   Current usage: {self.requests_this_minute}/{self.max_requests_per_minute}")
            logger.warning(f"   Rate limit resets in {self.get_rate_limit_status()['time_until_reset']:.1f} seconds")
        
        return can_handle
    
    def _calculate_analyzable_chunks(self, chunks: List[BillChunk], available_requests: int) -> List[BillChunk]:
        """Calculate how many chunks we can analyze with available API quota"""
        if available_requests <= 2:  # Keep 2 requests as buffer
            logger.warning(f"⚠️ Insufficient quota ({available_requests}), no chunks can be analyzed")
            return []
        
        # Reserve requests for overall analysis (summary, final assessment)
        reserved_requests = 3
        usable_requests = max(0, available_requests - reserved_requests)
        
        # Each chunk needs approximately 5 requests for full analysis
        requests_per_chunk = 5
        max_chunks = max(0, usable_requests // requests_per_chunk)
        
        if max_chunks == 0:
            logger.warning(f"⚠️ Not enough quota for full chunk analysis. Available: {available_requests}, need minimum: {requests_per_chunk + reserved_requests}")
            return []
        
        # Sort chunks by importance and take the most important ones
        sorted_chunks = sorted(chunks, key=lambda x: x.importance_score, reverse=True)
        chunks_to_analyze = sorted_chunks[:max_chunks]
        
        logger.info(f"📊 Progressive Analysis: Analyzing {len(chunks_to_analyze)}/{len(chunks)} chunks with {usable_requests} available requests")
        if len(chunks_to_analyze) < len(chunks):
            logger.warning(f"⚠️ Partial analysis: {len(chunks) - len(chunks_to_analyze)} chunks will be skipped due to quota limits")
        
        return chunks_to_analyze
    
    def _wait_for_rate_limit_reset(self):
        """Wait for rate limit to reset and log progress"""
        if not self.minute_start_time:
            return
        
        current_time = time.time()
        elapsed = current_time - self.minute_start_time
        wait_time = max(0, 60 - elapsed)
        
        if wait_time > 0:
            logger.info(f"⏳ Waiting {wait_time:.1f} seconds for rate limit reset...")
            logger.info(f"   Current usage: {self.requests_this_minute}/{self.max_requests_per_minute}")
            logger.info(f"   This ensures continued analysis rather than stopping completely")
            
            # Wait in smaller increments to show progress
            while wait_time > 0:
                sleep_time = min(10, wait_time)  # Sleep max 10 seconds at a time
                time.sleep(sleep_time)
                wait_time -= sleep_time
                if wait_time > 0:
                    logger.info(f"   Still waiting... {wait_time:.1f} seconds remaining")
            
            # Reset rate limit counters
            self.requests_this_minute = 0
            self.minute_start_time = time.time()
            logger.info(f"✅ Rate limit reset complete, ready to continue analysis")
    
    def _create_minimal_analysis(self, title: str, summary: str) -> Dict:
        """Create minimal analysis when quota is insufficient for full analysis"""
        logger.info("📝 Creating minimal analysis due to quota constraints...")
        
        minimal_analysis = {
            'analysis_type': 'minimal',
            'reason': 'insufficient_api_quota',
            'title': title,
            'summary': summary if summary else 'No summary available',
            'analysis_completeness': 'partial',
            'analyzed_sections': 'title_and_summary_only',
            'recommendation': 'Run full analysis when API quota is available'
        }
        
        # Add basic pattern-based analysis without AI
        if title and summary:
            combined_text = f"{title} {summary}".lower()
            basic_flags = []
            
            # Check for basic suspicious patterns
            suspicious_keywords = ['emergency', 'waiver', 'notwithstanding', 'discretionary', 'classified']
            for keyword in suspicious_keywords:
                if keyword in combined_text:
                    basic_flags.append(keyword)
            
            if basic_flags:
                minimal_analysis['basic_flags'] = basic_flags
                minimal_analysis['requires_attention'] = True
            else:
                minimal_analysis['requires_attention'] = False
        
        logger.info("✅ Minimal analysis created - partial information available")
        return minimal_analysis

    def _parse_response(self, response):
        logger.debug(f"[AI] Parsing response: {str(response)[:2000]}... (truncated)")
        try:
            # Assume response is a dict or has a .text/.content attribute
            if hasattr(response, 'text'):
                raw = response.text
            elif hasattr(response, 'content'):
                raw = response.content
            else:
                raw = str(response)
            logger.debug(f"[AI] Raw text/content to parse: {raw[:2000]}... (truncated)")
            # Try to parse as JSON
            import json
            try:
                parsed = json.loads(raw)
                logger.debug(f"[AI] Parsed JSON: {str(parsed)[:1000]}... (truncated)")
                return parsed
            except Exception as json_err:
                logger.error(f"[AI] JSON parse error: {json_err}")
                # Fallback: try eval or return raw
                return None
        except Exception as e:
            logger.error(f"[AI] Exception during response parsing: {e}")
            return None
    
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
            result = self._call_ai_model(prompt)
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
    
    def _store_policy_categories(self, bill, categories, analysis=None):
        """Store policy category mappings for the bill, including sneakiness score per category"""
        try:
            # Import here to avoid circular imports
            from db_models import BillCategoryMapping, PolicyCategory, db
            import re
            import json
            
            if not hasattr(bill, 'id') or not bill.id:
                logger.error(f"Bill object has no ID, cannot store categories")
                return
            
            categories_stored = 0
            
            # Prepare sneakiness mapping if analysis is provided
            sneakiness_by_category = {}
            if analysis and 'hidden_provisions' in analysis:
                hidden_provisions = analysis['hidden_provisions'].get('detected_provisions', [])
                # Build a mapping: category_name -> max sneakiness score
                for provision in hidden_provisions:
                    provision_text = (provision.get('text') or '') + ' ' + (provision.get('type') or '')
                    risk_level = provision.get('risk_level', 'low')
                    confidence = provision.get('confidence_score', 0.5)
                    risk_value = {'low': 0.2, 'medium': 0.5, 'high': 0.8}.get(risk_level, 0.2)
                    sneakiness_score = risk_value * confidence
                    for cat in categories:
                        area = cat.get('area', '')
                        if area and re.search(re.escape(area), provision_text, re.IGNORECASE):
                            prev = sneakiness_by_category.get(area, 0.0)
                            sneakiness_by_category[area] = max(prev, sneakiness_score)
            
            for category_data in categories:
                try:
                    area = category_data.get('area', '').strip()
                    if not area:
                        continue
                    
                    # Get or create policy category
                    policy_category = PolicyCategory.query.filter_by(name=area).first()
                    if not policy_category:
                        policy_category = PolicyCategory(
                            name=area,
                            display_name=area,
                            description=f"Policy category for {area}",
                            is_active=True
                        )
                        db.session.add(policy_category)
                        db.session.flush()
                        logger.info(f"Created new policy category: {area}")
                    
                    # Check if mapping already exists
                    mapping = BillCategoryMapping.query.filter_by(
                        bill_id=bill.id,
                        policy_category_id=policy_category.id
                    ).first()
                    
                    # Extract relevance score from category data or use default
                    relevance_score = category_data.get('impact_level', 'medium')
                    if relevance_score == 'high':
                        score = 0.9
                    elif relevance_score == 'medium':
                        score = 0.7
                    elif relevance_score == 'low':
                        score = 0.5
                    else:
                        score = 0.7  # Default to medium
                    
                    # Get sneakiness score for this category
                    sneakiness_score = sneakiness_by_category.get(area, 0.0)
                    
                    # Build section reference
                    section_reference = category_data.get('section', '')
                    if section_reference and category_data.get('title'):
                        section_reference = f"{section_reference}: {category_data['title'][:100]}"
                    elif category_data.get('title'):
                        section_reference = category_data['title'][:150]
                    
                    if not mapping:
                        mapping = BillCategoryMapping(
                            bill_id=bill.id,
                            policy_category_id=policy_category.id,
                            relevance_score=score,
                            category_specific_analysis=json.dumps(category_data),
                            sneakiness_score=sneakiness_score,
                            section_reference=section_reference
                        )
                        db.session.add(mapping)
                        categories_stored += 1
                        logger.info(f"Created category mapping: {bill.get_bill_identifier()} -> {area} (score: {score}, sneakiness: {sneakiness_score})")
                    else:
                        mapping.category_specific_analysis = json.dumps(category_data)
                        mapping.sneakiness_score = sneakiness_score
                        mapping.section_reference = section_reference
                        logger.info(f"Updated existing category mapping: {bill.get_bill_identifier()} -> {area} (sneakiness: {sneakiness_score})")
                        
                except Exception as category_error:
                    logger.error(f"Error processing category '{area}': {category_error}")
                    continue
            
            if categories_stored > 0:
                db.session.commit()
                logger.info(f"Successfully stored {categories_stored} policy category mappings for {bill.get_bill_identifier()}")
            else:
                logger.warning(f"No new policy category mappings were stored for {bill.get_bill_identifier()}")
                
        except Exception as e:
            logger.error(f"Error storing policy categories for {bill.get_bill_identifier()}: {e}")
            if 'db' in locals():
                db.session.rollback() 