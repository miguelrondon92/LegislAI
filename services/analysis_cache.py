"""
Analysis Caching Service for Legislative AI Platform
Implements intelligent caching to prevent expensive re-processing of AI analyses
"""

import hashlib
import json
import logging
from datetime import datetime
from typing import Dict, Optional, List, Any
from sqlalchemy import text
from app import db

class AnalysisCache:
    """Intelligent caching service for AI-generated bill analyses"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def get_content_hash(self, content: str) -> str:
        """Generate SHA-256 hash of content for cache keys"""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()
    
    def get_analysis_cache(self, bill_id: str, analysis_type: str, input_hash: str) -> Optional[Dict]:
        """Check if analysis already exists in cache"""
        try:
            query = text("""
                SELECT analysis_data, created_at, llm_model, confidence_score
                FROM bill_analyses 
                WHERE bill_id = :bill_id 
                AND analysis_type = :analysis_type 
                AND input_hash = :input_hash
                ORDER BY created_at DESC 
                LIMIT 1
            """)
            
            result = db.session.execute(query, {
                'bill_id': bill_id,
                'analysis_type': analysis_type,
                'input_hash': input_hash
            }).fetchone()
            
            if result:
                self.logger.info(f"Cache HIT for {analysis_type} analysis of bill {bill_id}")
                return {
                    'analysis_data': result[0],
                    'created_at': result[1],
                    'llm_model': result[2],
                    'confidence_score': result[3],
                    'from_cache': True
                }
            
            self.logger.info(f"Cache MISS for {analysis_type} analysis of bill {bill_id}")
            return None
            
        except Exception as e:
            self.logger.error(f"Error checking analysis cache: {str(e)}")
            return None
    
    def store_analysis(self, bill_id: str, analysis_type: str, analysis_data: Dict, 
                      input_hash: str, llm_model: str = None, confidence_score: float = None,
                      processing_time_ms: int = None) -> bool:
        """Store analysis results in cache"""
        try:
            analysis_hash = self.get_content_hash(json.dumps(analysis_data, sort_keys=True))
            
            query = text("""
                INSERT INTO bill_analyses 
                (bill_id, analysis_type, analysis_data, analysis_hash, input_hash, 
                 llm_model, confidence_score, processing_time_ms)
                VALUES (:bill_id, :analysis_type, :analysis_data, :analysis_hash, 
                        :input_hash, :llm_model, :confidence_score, :processing_time_ms)
                ON CONFLICT (bill_id, analysis_type, input_hash) 
                DO UPDATE SET 
                    analysis_data = EXCLUDED.analysis_data,
                    analysis_hash = EXCLUDED.analysis_hash,
                    created_at = CURRENT_TIMESTAMP,
                    llm_model = EXCLUDED.llm_model,
                    confidence_score = EXCLUDED.confidence_score,
                    processing_time_ms = EXCLUDED.processing_time_ms
            """)
            
            db.session.execute(query, {
                'bill_id': bill_id,
                'analysis_type': analysis_type,
                'analysis_data': json.dumps(analysis_data),
                'analysis_hash': analysis_hash,
                'input_hash': input_hash,
                'llm_model': llm_model,
                'confidence_score': confidence_score,
                'processing_time_ms': processing_time_ms
            })
            
            db.session.commit()
            self.logger.info(f"Stored {analysis_type} analysis for bill {bill_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error storing analysis: {str(e)}")
            db.session.rollback()
            return False
    
    def get_user_alignment_cache(self, user_id: int, bill_id: str, 
                                user_preferences_hash: str, bill_content_hash: str) -> Optional[Dict]:
        """Check cached user-bill alignment score"""
        try:
            query = text("""
                SELECT alignment_score, detailed_scores, reasoning, calculated_at
                FROM user_alignments 
                WHERE user_id = :user_id 
                AND bill_id = :bill_id 
                AND user_preferences_hash = :user_preferences_hash
                AND bill_content_hash = :bill_content_hash
            """)
            
            result = db.session.execute(query, {
                'user_id': user_id,
                'bill_id': bill_id,
                'user_preferences_hash': user_preferences_hash,
                'bill_content_hash': bill_content_hash
            }).fetchone()
            
            if result:
                return {
                    'alignment_score': result[0],
                    'detailed_scores': result[1],
                    'reasoning': result[2],
                    'calculated_at': result[3],
                    'from_cache': True
                }
            return None
            
        except Exception as e:
            self.logger.error(f"Error checking alignment cache: {str(e)}")
            return None
    
    def store_user_alignment(self, user_id: int, bill_id: str, alignment_score: int,
                           detailed_scores: Dict, reasoning: str, user_preferences_hash: str,
                           bill_content_hash: str) -> bool:
        """Store user-bill alignment score in cache"""
        try:
            query = text("""
                INSERT INTO user_alignments 
                (user_id, bill_id, alignment_score, detailed_scores, reasoning,
                 user_preferences_hash, bill_content_hash)
                VALUES (:user_id, :bill_id, :alignment_score, :detailed_scores, 
                        :reasoning, :user_preferences_hash, :bill_content_hash)
                ON CONFLICT (user_id, bill_id) 
                DO UPDATE SET 
                    alignment_score = EXCLUDED.alignment_score,
                    detailed_scores = EXCLUDED.detailed_scores,
                    reasoning = EXCLUDED.reasoning,
                    user_preferences_hash = EXCLUDED.user_preferences_hash,
                    bill_content_hash = EXCLUDED.bill_content_hash,
                    calculated_at = CURRENT_TIMESTAMP
            """)
            
            db.session.execute(query, {
                'user_id': user_id,
                'bill_id': bill_id,
                'alignment_score': alignment_score,
                'detailed_scores': json.dumps(detailed_scores),
                'reasoning': reasoning,
                'user_preferences_hash': user_preferences_hash,
                'bill_content_hash': bill_content_hash
            })
            
            db.session.commit()
            return True
            
        except Exception as e:
            self.logger.error(f"Error storing alignment: {str(e)}")
            db.session.rollback()
            return False
    
    def store_bill_with_analysis(self, bill_data: Dict) -> Optional[str]:
        """Store bill in enhanced table and return UUID"""
        try:
            # Create content hash from title and summary (not full text)
            content_for_hash = bill_data.get('title', '') + bill_data.get('summary', '')
            content_hash = self.get_content_hash(content_for_hash)
            congress_id = f"{bill_data['congress']}-{bill_data['bill_type']}-{bill_data['bill_number']}"
            
            query = text("""
                INSERT INTO bills_enhanced 
                (congress_id, bill_number, bill_type, congress, title, summary,
                 version_hash, status, sponsors, committees, introduced_date, last_action_date,
                 congress_api_url)
                VALUES (:congress_id, :bill_number, :bill_type, :congress, :title, :summary, 
                        :version_hash, :status, :sponsors, :committees, 
                        :introduced_date, :last_action_date, :congress_api_url)
                ON CONFLICT (congress_id) 
                DO UPDATE SET 
                    title = EXCLUDED.title,
                    summary = EXCLUDED.summary,
                    version_hash = EXCLUDED.version_hash,
                    status = EXCLUDED.status,
                    sponsors = EXCLUDED.sponsors,
                    committees = EXCLUDED.committees,
                    last_action_date = EXCLUDED.last_action_date,
                    last_updated = CURRENT_TIMESTAMP
                RETURNING id
            """)
            
            result = db.session.execute(query, {
                'congress_id': congress_id,
                'bill_number': bill_data.get('bill_number', ''),
                'bill_type': bill_data.get('bill_type', ''),
                'congress': bill_data.get('congress', 0),
                'title': bill_data.get('title', ''),
                'summary': bill_data.get('summary', ''),
                'version_hash': content_hash,
                'status': bill_data.get('status', ''),
                'sponsors': json.dumps(bill_data.get('sponsors', [])),
                'committees': json.dumps(bill_data.get('committees', [])),
                'introduced_date': bill_data.get('introduced_date'),
                'last_action_date': bill_data.get('last_action_date'),
                'congress_api_url': bill_data.get('congress_api_url', '')
            }).fetchone()
            
            db.session.commit()
            
            if result:
                bill_id = str(result[0])
                self.logger.info(f"Stored bill {congress_id} with ID {bill_id}")
                return bill_id
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error storing bill: {str(e)}")
            db.session.rollback()
            return None
    
    def get_cached_bill(self, congress: int, bill_type: str, bill_number: int) -> Optional[Dict]:
        """Retrieve bill from enhanced cache"""
        try:
            congress_id = f"{congress}-{bill_type}-{bill_number}"
            
            query = text("""
                SELECT id, title, summary, version_hash, status, 
                       sponsors, committees, introduced_date, last_action_date,
                       congress_api_url, last_updated
                FROM bills_enhanced 
                WHERE congress_id = :congress_id
            """)
            
            result = db.session.execute(query, {'congress_id': congress_id}).fetchone()
            
            if result:
                return {
                    'id': str(result[0]),
                    'congress': congress,
                    'bill_type': bill_type,
                    'bill_number': bill_number,
                    'title': result[1],
                    'summary': result[2],
                    'version_hash': result[3],
                    'status': result[4],
                    'sponsors': result[5] if result[5] else [],
                    'committees': result[6] if result[6] else [],
                    'introduced_date': result[7],
                    'last_action_date': result[8],
                    'congress_api_url': result[9],
                    'last_updated': result[10],
                    'from_cache': True
                }
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error retrieving cached bill: {str(e)}")
            return None
    
    def record_analysis_metrics(self, analysis_type: str, bill_count: int, 
                              total_processing_time_ms: int, cache_hit_rate: float):
        """Record analysis performance metrics"""
        try:
            avg_time = total_processing_time_ms / bill_count if bill_count > 0 else 0
            
            query = text("""
                INSERT INTO analysis_metrics 
                (analysis_type, bill_count, total_processing_time_ms, 
                 average_processing_time_ms, cache_hit_rate)
                VALUES (:analysis_type, :bill_count, :total_processing_time_ms,
                        :average_processing_time_ms, :cache_hit_rate)
            """)
            
            db.session.execute(query, {
                'analysis_type': analysis_type,
                'bill_count': bill_count,
                'total_processing_time_ms': total_processing_time_ms,
                'average_processing_time_ms': avg_time,
                'cache_hit_rate': cache_hit_rate
            })
            
            db.session.commit()
            
        except Exception as e:
            self.logger.error(f"Error recording metrics: {str(e)}")
            db.session.rollback()