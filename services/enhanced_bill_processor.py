"""
Enhanced Bill Processor with Analysis Caching
Integrates Congress API, AI analysis, and intelligent storage
"""

import logging
import time
from datetime import datetime
from typing import Dict, List, Optional, Any
from .congress_api import CongressAPI
from .ai_analysis import AIAnalyzer
from .analysis_cache import AnalysisCache

class EnhancedBillProcessor:
    """Process bills with intelligent caching and storage"""
    
    def __init__(self):
        self.congress_api = CongressAPI()
        self.ai_analyzer = AIAnalyzer()
        self.cache = AnalysisCache()
        self.logger = logging.getLogger(__name__)
    
    def process_bill_comprehensive(self, congress: int, bill_type: str, bill_number: int) -> Optional[Dict]:
        """
        Process a bill with full analysis and intelligent caching
        Returns complete bill data with AI analysis
        """
        try:
            # Check if bill exists in enhanced cache
            cached_bill = self.cache.get_cached_bill(congress, bill_type, bill_number)
            
            if cached_bill:
                self.logger.info(f"Retrieved bill {congress}-{bill_type}-{bill_number} from cache")
                # Check if we need to refresh analysis
                if self._should_refresh_analysis(cached_bill):
                    return self._refresh_bill_analysis(cached_bill)
                return cached_bill
            
            # Fetch fresh bill data from Congress API
            self.logger.info(f"Fetching bill {congress}-{bill_type}-{bill_number} from Congress API")
            bill_data = self.congress_api.get_bill_details(congress, bill_type, bill_number)
            
            if not bill_data:
                self.logger.warning(f"Could not fetch bill {congress}-{bill_type}-{bill_number}")
                return None
            
            # Get full bill text for analysis (but don't store it)
            bill_text = self.congress_api.get_bill_text(congress, bill_type, bill_number)
            if bill_text:
                bill_data['full_text'] = bill_text
            
            # Store bill in enhanced database (without full text)
            bill_id = self.cache.store_bill_with_analysis(bill_data)
            if not bill_id:
                self.logger.error("Failed to store bill in database")
                return bill_data
            
            # Perform AI analysis with caching (using the text we just fetched)
            if bill_data.get('full_text'):
                analysis = self.ai_analyzer.analyze_bill_with_cache(
                    bill_id, bill_data['full_text'], bill_data.get('title', '')
                )
                bill_data['ai_analysis'] = analysis
            
            return bill_data
            
        except Exception as e:
            self.logger.error(f"Error processing bill: {str(e)}")
            return None
    
    def search_bills_with_analysis(self, query: str, limit: int = 20) -> List[Dict]:
        """
        Search bills and return with cached analysis where available
        """
        try:
            # Get basic bill search results
            search_results = self.congress_api.search_bills(query, limit)
            
            enhanced_results = []
            for bill in search_results:
                # Check if we have enhanced data for this bill
                cached_bill = self.cache.get_cached_bill(
                    bill['congress'], bill['bill_type'], bill['bill_number']
                )
                
                if cached_bill:
                    # Use cached version with analysis
                    enhanced_results.append(cached_bill)
                else:
                    # Use basic search result
                    enhanced_results.append(bill)
            
            return enhanced_results
            
        except Exception as e:
            self.logger.error(f"Error in enhanced bill search: {str(e)}")
            return []
    
    def get_user_bill_alignment(self, user_id: int, bill_id: str, user_preferences: Dict) -> Dict:
        """
        Calculate user-bill alignment with caching
        """
        try:
            # Generate hashes for cache lookup
            preferences_hash = self.cache.get_content_hash(str(sorted(user_preferences.items())))
            
            # Get bill content hash from database
            cached_bill = self._get_bill_by_id(bill_id)
            if not cached_bill:
                return {'error': 'Bill not found'}
            
            bill_content_hash = cached_bill.get('version_hash', '')
            
            # Check cache first
            cached_alignment = self.cache.get_user_alignment_cache(
                user_id, bill_id, preferences_hash, bill_content_hash
            )
            
            if cached_alignment:
                self.logger.info(f"Retrieved alignment score from cache for user {user_id}, bill {bill_id}")
                return cached_alignment
            
            # Calculate fresh alignment
            start_time = time.time()
            
            # Get or generate bill analysis
            bill_analysis = self._get_bill_analysis(bill_id, cached_bill)
            alignment_score = self.ai_analyzer.calculate_alignment_score(bill_analysis, user_preferences)
            
            # Generate detailed reasoning
            reasoning = self.ai_analyzer.generate_user_specific_analysis(
                bill_analysis, user_preferences, alignment_score
            )
            
            processing_time = int((time.time() - start_time) * 1000)
            
            # Prepare detailed scores by category
            detailed_scores = self._calculate_detailed_alignment(bill_analysis, user_preferences)
            
            result = {
                'alignment_score': alignment_score,
                'detailed_scores': detailed_scores,
                'reasoning': reasoning,
                'processing_time_ms': processing_time
            }
            
            # Store in cache
            self.cache.store_user_alignment(
                user_id, bill_id, alignment_score, detailed_scores, 
                reasoning, preferences_hash, bill_content_hash
            )
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error calculating alignment: {str(e)}")
            return {'error': f'Alignment calculation failed: {str(e)}'}
    
    def generate_policy_alerts(self, user_id: int, user_preferences: Dict) -> List[Dict]:
        """
        Generate personalized policy alerts based on recent bills
        """
        try:
            # Get recent bills that might interest the user
            recent_bills = self._get_recent_bills_for_user(user_preferences)
            
            alerts = []
            for bill in recent_bills:
                # Calculate alignment for this bill
                alignment = self.get_user_bill_alignment(user_id, bill['id'], user_preferences)
                
                if alignment.get('alignment_score', 0) > 60:  # High alignment
                    alerts.append({
                        'type': 'high_alignment',
                        'bill': bill,
                        'alignment_score': alignment['alignment_score'],
                        'reason': alignment.get('reasoning', ''),
                        'priority': 'high'
                    })
                elif alignment.get('alignment_score', 0) < -60:  # High conflict
                    alerts.append({
                        'type': 'high_conflict',
                        'bill': bill,
                        'alignment_score': alignment['alignment_score'],
                        'reason': alignment.get('reasoning', ''),
                        'priority': 'high'
                    })
            
            return sorted(alerts, key=lambda x: abs(x['alignment_score']), reverse=True)
            
        except Exception as e:
            self.logger.error(f"Error generating alerts: {str(e)}")
            return []
    
    def _should_refresh_analysis(self, cached_bill: Dict) -> bool:
        """Check if bill analysis needs refreshing"""
        last_updated = cached_bill.get('last_updated')
        if not last_updated:
            return True
        
        # Refresh if older than 24 hours
        age_hours = (datetime.utcnow() - last_updated).total_seconds() / 3600
        return age_hours > 24
    
    def _refresh_bill_analysis(self, cached_bill: Dict) -> Dict:
        """Refresh analysis for an existing cached bill"""
        try:
            bill_id = cached_bill['id']
            
            # Fetch fresh text from API for analysis
            if cached_bill.get('congress_api_url'):
                # Parse congress, bill_type, bill_number from API URL
                url_parts = cached_bill['congress_api_url'].split('/')
                if len(url_parts) >= 6:
                    congress = url_parts[-3]
                    bill_type = url_parts[-2]
                    bill_number = url_parts[-1]
                    
                    # Fetch full text from Congress API
                    bill_text = self.congress_api.get_bill_text(int(congress), bill_type, int(bill_number))
                    if bill_text:
                        analysis = self.ai_analyzer.analyze_bill_with_cache(
                            bill_id, bill_text, cached_bill.get('title', '')
                        )
                        cached_bill['ai_analysis'] = analysis
            
            return cached_bill
            
        except Exception as e:
            self.logger.error(f"Error refreshing analysis: {str(e)}")
            return cached_bill
    
    def _get_bill_by_id(self, bill_id: str) -> Optional[Dict]:
        """Retrieve bill data by ID from enhanced cache"""
        try:
            from sqlalchemy import text
            from app import db
            
            query = text("""
                SELECT congress_id, title, version_hash, status,
                       sponsors, committees, last_updated, congress_api_url
                FROM bills_enhanced 
                WHERE id = :bill_id
            """)
            
            result = db.session.execute(query, {'bill_id': bill_id}).fetchone()
            
            if result:
                return {
                    'id': bill_id,
                    'congress_id': result[0],
                    'title': result[1],
                    'version_hash': result[2],
                    'status': result[3],
                    'sponsors': result[4] or [],
                    'committees': result[5] or [],
                    'last_updated': result[6],
                    'congress_api_url': result[7]
                }
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error retrieving bill by ID: {str(e)}")
            return None
    
    def _get_bill_analysis(self, bill_id: str, bill_data: Dict) -> Dict:
        """Get or generate comprehensive bill analysis"""
        try:
            # Create content hash from title and summary (not full text)
            content_for_hash = bill_data.get('title', '') + bill_data.get('summary', '')
            content_hash = self.cache.get_content_hash(content_for_hash)
            
            # Check for cached comprehensive analysis
            cached = self.cache.get_analysis_cache(bill_id, 'comprehensive', content_hash)
            if cached:
                return cached['analysis_data']
            
            # Generate fresh analysis by fetching text from API
            if bill_data.get('congress_api_url'):
                # Parse congress, bill_type, bill_number from API URL
                url_parts = bill_data['congress_api_url'].split('/')
                if len(url_parts) >= 6:
                    congress = url_parts[-3]
                    bill_type = url_parts[-2]
                    bill_number = url_parts[-1]
                    
                    # Fetch full text from Congress API
                    bill_text = self.congress_api.get_bill_text(int(congress), bill_type, int(bill_number))
                    if bill_text:
                        return self.ai_analyzer.analyze_bill_with_cache(
                            bill_id, bill_text, bill_data.get('title', '')
                        )
            
            return {}
            
        except Exception as e:
            self.logger.error(f"Error getting bill analysis: {str(e)}")
            return {}
    
    def _calculate_detailed_alignment(self, bill_analysis: Dict, user_preferences: Dict) -> Dict:
        """Calculate alignment scores by policy category"""
        try:
            detailed_scores = {}
            
            policy_implications = bill_analysis.get('policy_implications', {})
            
            for category, user_weight in user_preferences.items():
                if category in policy_implications:
                    bill_impact = policy_implications[category].get('impact_score', 0)
                    # Calculate alignment based on user preference and bill impact
                    alignment = (bill_impact * user_weight) / 100
                    detailed_scores[category] = min(100, max(-100, alignment))
                else:
                    detailed_scores[category] = 0
            
            return detailed_scores
            
        except Exception as e:
            self.logger.error(f"Error calculating detailed alignment: {str(e)}")
            return {}
    
    def _get_recent_bills_for_user(self, user_preferences: Dict) -> List[Dict]:
        """Get recent bills that might interest the user based on preferences"""
        try:
            from sqlalchemy import text
            from app import db
            
            # Get bills from the last 30 days
            query = text("""
                SELECT id, congress_id, title, status, last_updated
                FROM bills_enhanced 
                WHERE last_updated >= CURRENT_DATE - INTERVAL '30 days'
                ORDER BY last_updated DESC
                LIMIT 50
            """)
            
            results = db.session.execute(query).fetchall()
            
            bills = []
            for result in results:
                bills.append({
                    'id': str(result[0]),
                    'congress_id': result[1],
                    'title': result[2],
                    'status': result[3],
                    'last_updated': result[4]
                })
            
            return bills
            
        except Exception as e:
            self.logger.error(f"Error getting recent bills: {str(e)}")
            return []