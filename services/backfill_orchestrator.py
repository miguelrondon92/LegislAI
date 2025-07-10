#!/usr/bin/env python3
"""
Backfill Orchestrator - Systematically populate the database with historical congressional data.

This service handles:
- Session-based bill discovery and processing
- State persistence for resumability
- Rate-limited batch processing
- Gap analysis to identify missing bills
- Progress tracking and reporting

Key Features:
- Can target specific congressional sessions (e.g., 119th Congress)
- Remembers where it left off if interrupted
- Respects both Congress API and AI API rate limits
- Provides detailed progress reporting
- Can run in discovery-only mode or full processing mode
"""

import os
import sys
import json
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app import app, db
from db_models import Bill, BillCategoryMapping, PolicyCategory
from services.congress_api import CongressAPI
from services.enhanced_ai_analyzer import EnhancedAIAnalyzer
from services.bill_processor import BillProcessor

logger = logging.getLogger(__name__)

class BackfillStatus(Enum):
    """Backfill operation status"""
    NOT_STARTED = "not_started"
    DISCOVERING = "discovering"
    PROCESSING = "processing"
    PAUSED = "paused"
    COMPLETED = "completed"
    ERROR = "error"

class ProcessingMode(Enum):
    """Processing mode options"""
    DISCOVERY_ONLY = "discovery_only"  # Only discover bills, don't process
    FULL_PROCESSING = "full_processing"  # Discover and process with AI
    GAPS_ONLY = "gaps_only"  # Only process missing/unanalyzed bills

@dataclass
class BackfillState:
    """Persistent state for backfill operations"""
    congress_session: int
    status: str
    processing_mode: str
    start_time: Optional[str] = None
    last_update: Optional[str] = None
    
    # Discovery progress
    total_bills_discovered: int = 0
    bills_discovered: List[Dict] = None
    discovery_offset: int = 0
    discovery_complete: bool = False
    
    # Processing progress
    bills_processed: int = 0
    bills_analyzed: int = 0
    bills_failed: int = 0
    current_batch: int = 0
    last_processed_bill: Optional[str] = None
    
    # Error tracking
    errors: List[Dict] = None
    api_quota_hits: int = 0
    
    # Statistics
    stats: Dict = None
    
    def __post_init__(self):
        if self.bills_discovered is None:
            self.bills_discovered = []
        if self.errors is None:
            self.errors = []
        if self.stats is None:
            self.stats = {
                'session_total_bills': 0,
                'db_existing_bills': 0,
                'db_analyzed_bills': 0,
                'missing_bills': 0,
                'unanalyzed_bills': 0
            }

@dataclass
class BackfillConfig:
    """Configuration for backfill operations"""
    congress_session: int = 119
    processing_mode: ProcessingMode = ProcessingMode.FULL_PROCESSING
    batch_size: int = 10
    max_bills_per_session: int = 10000
    congress_api_delay: float = 3.6  # Rate limit for Congress API
    ai_api_delay: float = 4.0  # Rate limit for AI API
    auto_pause_on_quota: bool = True
    save_state_frequency: int = 5  # Save state every N bills
    discovery_limit: int = 1000  # Max bills to discover in one batch
    retry_failed: bool = True
    max_retries: int = 3

class BackfillOrchestrator:
    """
    Main orchestrator for backfilling congressional data.
    
    This class coordinates the discovery and processing of bills from Congress API,
    manages state persistence, and handles rate limiting across multiple APIs.
    """
    
    def __init__(self, config: BackfillConfig = None):
        self.config = config or BackfillConfig()
        self.state_file = Path("logs") / f"backfill_state_{self.config.congress_session}.json"
        self.state_file.parent.mkdir(exist_ok=True)
        
        # Initialize services
        self.congress_api = CongressAPI()
        self.ai_analyzer = EnhancedAIAnalyzer()
        self.bill_processor = BillProcessor()
        
        # Load or initialize state
        self.state = self._load_state()
        
        logger.info(f"Backfill Orchestrator initialized for Congress {self.config.congress_session}")
        logger.info(f"Mode: {self.config.processing_mode.value}")
        logger.info(f"State file: {self.state_file}")
    
    def _load_state(self) -> BackfillState:
        """Load state from file or create new state"""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    state_data = json.load(f)
                logger.info(f"Loaded existing state from {self.state_file}")
                return BackfillState(**state_data)
            except Exception as e:
                logger.error(f"Error loading state file: {e}")
        
        # Create new state
        logger.info("Creating new backfill state")
        return BackfillState(
            congress_session=self.config.congress_session,
            status=BackfillStatus.NOT_STARTED.value,
            processing_mode=self.config.processing_mode.value,
            start_time=datetime.now().isoformat()
        )
    
    def _save_state(self):
        """Save current state to file"""
        try:
            self.state.last_update = datetime.now().isoformat()
            with open(self.state_file, 'w') as f:
                json.dump(asdict(self.state), f, indent=2)
            logger.debug(f"State saved to {self.state_file}")
        except Exception as e:
            logger.error(f"Error saving state: {e}")
    
    def analyze_gaps(self) -> Dict:
        """
        Analyze what bills exist vs. what's in our database.
        
        Returns:
            Dict with gap analysis results
        """
        logger.info("Starting gap analysis...")
        
        with app.app_context():
            # Get database statistics
            db_bills = Bill.query.filter_by(congress=self.config.congress_session).all()
            db_bill_ids = set(bill.get_bill_identifier() for bill in db_bills)
            db_analyzed_bills = [bill for bill in db_bills if bill.ai_analysis]
            
            self.state.stats['db_existing_bills'] = len(db_bills)
            self.state.stats['db_analyzed_bills'] = len(db_analyzed_bills)
            
            logger.info(f"Database has {len(db_bills)} bills from Congress {self.config.congress_session}")
            logger.info(f"Of those, {len(db_analyzed_bills)} have AI analysis")
        
        # If we haven't discovered bills yet, we need to do discovery first
        if not self.state.discovery_complete:
            logger.info("No discovery data available. Need to run discovery first.")
            return {
                'status': 'discovery_needed',
                'db_bills': len(db_bills),
                'db_analyzed_bills': len(db_analyzed_bills),
                'discovered_bills': 0,
                'missing_bills': 'unknown',
                'unanalyzed_bills': len(db_bills) - len(db_analyzed_bills)
            }
        
        # Compare discovered bills vs database
        discovered_bill_ids = set(bill['identifier'] for bill in self.state.bills_discovered)
        missing_bills = discovered_bill_ids - db_bill_ids
        unanalyzed_bills = [bill for bill in db_bills if not bill.ai_analysis]
        
        self.state.stats['session_total_bills'] = len(discovered_bill_ids)
        self.state.stats['missing_bills'] = len(missing_bills)
        self.state.stats['unanalyzed_bills'] = len(unanalyzed_bills)
        
        gap_analysis = {
            'status': 'complete',
            'congress_session': self.config.congress_session,
            'discovered_bills': len(discovered_bill_ids),
            'db_bills': len(db_bills),
            'db_analyzed_bills': len(db_analyzed_bills),
            'missing_bills': len(missing_bills),
            'unanalyzed_bills': len(unanalyzed_bills),
            'missing_bill_samples': list(missing_bills)[:10],
            'unanalyzed_bill_samples': [bill.get_bill_identifier() for bill in unanalyzed_bills[:10]]
        }
        
        logger.info("Gap Analysis Results:")
        logger.info(f"  Total bills discovered: {gap_analysis['discovered_bills']}")
        logger.info(f"  Bills in database: {gap_analysis['db_bills']}")
        logger.info(f"  Bills with analysis: {gap_analysis['db_analyzed_bills']}")
        logger.info(f"  Missing from database: {gap_analysis['missing_bills']}")
        logger.info(f"  Missing analysis: {gap_analysis['unanalyzed_bills']}")
        
        return gap_analysis
    
    def discover_bills(self, max_bills: int = None) -> bool:
        """
        Discover all bills for the target congress session.
        
        Args:
            max_bills: Maximum number of bills to discover (None for all)
            
        Returns:
            bool: True if discovery completed successfully
        """
        logger.info(f"Starting bill discovery for Congress {self.config.congress_session}")
        
        if max_bills is None:
            max_bills = self.config.max_bills_per_session
        
        self.state.status = BackfillStatus.DISCOVERING.value
        self._save_state()
        
        # Use Congress API pagination to discover all bills
        offset = self.state.discovery_offset
        limit = min(250, self.config.discovery_limit)  # API max per request
        bills_found = 0
        
        try:
            while bills_found < max_bills:
                logger.info(f"Discovering bills: offset={offset}, limit={limit}")
                
                # Make API request
                params = {
                    'limit': limit,
                    'offset': offset,
                    'sort': 'introducedDate+desc'
                }
                
                endpoint = f"/bill/{self.config.congress_session}"
                data = self.congress_api._make_request(endpoint, params)
                
                if not data or 'bills' not in data:
                    logger.warning(f"No bills data received at offset {offset}")
                    break
                
                bill_list = data['bills']
                if not bill_list:
                    logger.info("No more bills to discover")
                    break
                
                # Process discovered bills
                for bill_summary in bill_list:
                    try:
                        bill_info = self._extract_bill_info(bill_summary)
                        if bill_info:
                            self.state.bills_discovered.append(bill_info)
                            bills_found += 1
                            
                            if bills_found >= max_bills:
                                break
                                
                    except Exception as e:
                        logger.error(f"Error processing discovered bill: {e}")
                        continue
                
                self.state.total_bills_discovered = len(self.state.bills_discovered)
                self.state.discovery_offset = offset + limit
                
                # Save state periodically
                if len(self.state.bills_discovered) % 50 == 0:
                    self._save_state()
                    logger.info(f"Discovery progress: {len(self.state.bills_discovered)} bills found")
                
                # If we got fewer bills than the limit, we've reached the end
                if len(bill_list) < limit:
                    logger.info("Reached end of available bills")
                    break
                
                offset += limit
                
                # Rate limiting
                time.sleep(self.config.congress_api_delay)
        
        except Exception as e:
            logger.error(f"Error during bill discovery: {e}")
            self.state.status = BackfillStatus.ERROR.value
            self.state.errors.append({
                'timestamp': datetime.now().isoformat(),
                'type': 'discovery_error',
                'message': str(e)
            })
            self._save_state()
            return False
        
        # Mark discovery as complete
        self.state.discovery_complete = True
        self.state.total_bills_discovered = len(self.state.bills_discovered)
        
        logger.info(f"Bill discovery completed: {self.state.total_bills_discovered} bills found")
        self._save_state()
        return True
    
    def _extract_bill_info(self, bill_summary: Dict) -> Optional[Dict]:
        """Extract basic bill information from Congress API summary"""
        try:
            congress = bill_summary.get('congress')
            bill_type = bill_summary.get('type', '').lower()
            bill_number = bill_summary.get('number')
            
            if not all([congress, bill_type, bill_number]):
                return None
            
            identifier = f"{congress}-{bill_type.upper()}{bill_number}"
            
            bill_info = {
                'identifier': identifier,
                'congress': congress,
                'bill_type': bill_type,
                'bill_number': bill_number,
                'title': bill_summary.get('title', ''),
                'url': bill_summary.get('url', ''),
                'introduced_date': bill_summary.get('introducedDate'),
                'update_date': bill_summary.get('updateDate'),
                'latest_action': bill_summary.get('latestAction', {}).get('text', '')
            }
            
            return bill_info
            
        except Exception as e:
            logger.error(f"Error extracting bill info: {e}")
            return None
    
    def start_backfill(self, resume: bool = True) -> bool:
        """
        Start the backfill process.
        
        Args:
            resume: Whether to resume from previous state
            
        Returns:
            bool: True if backfill completed successfully
        """
        logger.info("Starting backfill process")
        
        # Check if we should resume or start fresh
        if not resume or self.state.status == BackfillStatus.NOT_STARTED.value:
            logger.info("Starting fresh backfill")
            self.state = BackfillState(
                congress_session=self.config.congress_session,
                status=BackfillStatus.NOT_STARTED.value,
                processing_mode=self.config.processing_mode.value,
                start_time=datetime.now().isoformat()
            )
        
        try:
            # Step 1: Discovery (if needed)
            if not self.state.discovery_complete:
                logger.info("Running bill discovery...")
                if not self.discover_bills():
                    return False
            
            # Step 2: Gap analysis
            logger.info("Running gap analysis...")
            gap_analysis = self.analyze_gaps()
            
            # Step 3: Process bills based on mode
            if self.config.processing_mode == ProcessingMode.DISCOVERY_ONLY:
                logger.info("Discovery-only mode: skipping processing")
                self.state.status = BackfillStatus.COMPLETED.value
                self._save_state()
                return True
            
            # Step 4: Start processing
            return self._process_bills(gap_analysis)
            
        except Exception as e:
            logger.error(f"Backfill failed: {e}")
            self.state.status = BackfillStatus.ERROR.value
            self.state.errors.append({
                'timestamp': datetime.now().isoformat(),
                'type': 'backfill_error',
                'message': str(e)
            })
            self._save_state()
            return False
    
    def _process_bills(self, gap_analysis: Dict) -> bool:
        """Process bills based on the selected mode"""
        logger.info("Starting bill processing...")
        
        self.state.status = BackfillStatus.PROCESSING.value
        self._save_state()
        
        # Determine which bills to process
        bills_to_process = []
        
        if self.config.processing_mode == ProcessingMode.GAPS_ONLY:
            # Only process missing bills and unanalyzed bills
            with app.app_context():
                db_bills = Bill.query.filter_by(congress=self.config.congress_session).all()
                db_bill_ids = set(bill.get_bill_identifier() for bill in db_bills)
                
                # Add missing bills
                for bill_info in self.state.bills_discovered:
                    if bill_info['identifier'] not in db_bill_ids:
                        bills_to_process.append(bill_info)
                
                # Add unanalyzed bills
                unanalyzed_bills = [bill for bill in db_bills if not bill.ai_analysis]
                for bill in unanalyzed_bills:
                    bill_info = {
                        'identifier': bill.get_bill_identifier(),
                        'congress': bill.congress,
                        'bill_type': bill.bill_type,
                        'bill_number': bill.bill_number,
                        'title': bill.title,
                        'existing_in_db': True
                    }
                    bills_to_process.append(bill_info)
        else:
            # Process all discovered bills
            bills_to_process = self.state.bills_discovered
        
        logger.info(f"Processing {len(bills_to_process)} bills")
        
        # Process in batches
        return self._process_bills_batch(bills_to_process)
    
    def _process_bills_batch(self, bills_to_process: List[Dict]) -> bool:
        """Process bills in batches with rate limiting"""
        batch_size = self.config.batch_size
        total_bills = len(bills_to_process)
        
        for i in range(0, total_bills, batch_size):
            batch = bills_to_process[i:i + batch_size]
            batch_num = i // batch_size + 1
            
            logger.info(f"Processing batch {batch_num}: bills {i+1}-{min(i+batch_size, total_bills)} of {total_bills}")
            
            # Check AI quota before processing batch
            quota_info = self.ai_analyzer.get_quota_info()
            if quota_info['status']['is_at_limit']:
                logger.warning("AI API quota limit reached")
                if self.config.auto_pause_on_quota:
                    logger.info("Auto-pausing due to quota limit")
                    self.state.status = BackfillStatus.PAUSED.value
                    self._save_state()
                    return False
            
            # Process each bill in the batch
            for bill_info in batch:
                try:
                    success = self._process_single_bill(bill_info)
                    if success:
                        self.state.bills_processed += 1
                        if 'analyzed' in str(success).lower():
                            self.state.bills_analyzed += 1
                    else:
                        self.state.bills_failed += 1
                        
                    self.state.last_processed_bill = bill_info['identifier']
                    
                    # Rate limiting between bills
                    time.sleep(self.config.ai_api_delay)
                    
                except Exception as e:
                    logger.error(f"Error processing bill {bill_info['identifier']}: {e}")
                    self.state.bills_failed += 1
                    self.state.errors.append({
                        'timestamp': datetime.now().isoformat(),
                        'type': 'processing_error',
                        'bill_id': bill_info['identifier'],
                        'message': str(e)
                    })
            
            self.state.current_batch = batch_num
            
            # Save state after each batch
            if batch_num % self.config.save_state_frequency == 0:
                self._save_state()
                logger.info(f"Progress: {self.state.bills_processed} processed, {self.state.bills_analyzed} analyzed, {self.state.bills_failed} failed")
        
        # Mark as completed
        self.state.status = BackfillStatus.COMPLETED.value
        self._save_state()
        
        logger.info("Backfill processing completed!")
        logger.info(f"Final stats: {self.state.bills_processed} processed, {self.state.bills_analyzed} analyzed, {self.state.bills_failed} failed")
        
        return True
    
    def _process_single_bill(self, bill_info: Dict) -> bool:
        """Process a single bill: fetch data, analyze, and store"""
        identifier = bill_info['identifier']
        logger.debug(f"Processing bill: {identifier}")
        
        try:
            with app.app_context():
                # Check if bill already exists
                existing_bill = Bill.query.filter_by(
                    congress=bill_info['congress'],
                    bill_type=bill_info['bill_type'],
                    bill_number=bill_info['bill_number']
                ).first()
                
                if existing_bill and existing_bill.ai_analysis:
                    logger.debug(f"Bill {identifier} already analyzed, skipping")
                    return "already_analyzed"
                
                # Fetch full bill data from Congress API
                if not bill_info.get('existing_in_db'):
                    bill_data = self.congress_api.get_bill_details(
                        bill_info['congress'],
                        bill_info['bill_type'],
                        bill_info['bill_number']
                    )
                    
                    if not bill_data:
                        logger.warning(f"Failed to fetch bill data for {identifier}")
                        return False
                    
                    # Process bill data into database
                    bill = self.bill_processor.process_bill_data(bill_data)
                    if not bill:
                        logger.warning(f"Failed to process bill data for {identifier}")
                        return False
                else:
                    bill = existing_bill
                
                # Perform AI analysis if we have bill text
                if bill and not bill.ai_analysis:
                    # Fetch full text from Congress API (like workflow orchestrator does)
                    logger.debug(f"Fetching full text for analysis: {identifier}")
                    full_text = self.congress_api.get_bill_text(
                        bill.congress, 
                        bill.bill_type, 
                        bill.bill_number
                    )
                    
                    if not full_text:
                        # Fallback to summary/title if full text unavailable
                        logger.debug(f"No full text available for {identifier}, using summary")
                        bill_text = bill.summary or bill.title or "No text available"
                        # Limit fallback text size for analysis
                        if len(bill_text) > 2000:
                            bill_text = bill_text[:2000] + "..."
                    else:
                        bill_text = full_text
                        logger.debug(f"Using full text for analysis: {len(bill_text):,} characters")
                    
                    analysis = self.ai_analyzer.analyze_bill(bill_text, bill.title)
                    
                    if analysis:
                        # Store analysis
                        bill.set_ai_analysis(analysis)
                        
                        # Create category mappings
                        self._create_category_mappings(bill, analysis)
                        
                        db.session.commit()
                        logger.debug(f"Successfully analyzed bill {identifier}")
                        return "analyzed"
                    else:
                        logger.warning(f"AI analysis failed for {identifier}")
                        return "analysis_failed"
                
                return "processed"
                
        except Exception as e:
            logger.error(f"Error processing bill {identifier}: {e}")
            return False
    
    def _create_category_mappings(self, bill: Bill, analysis: Dict):
        """Create category mappings from analysis results"""
        # Check for categories in policy_implications
        categories = []
        if 'policy_implications' in analysis and 'categories' in analysis['policy_implications']:
            categories = analysis['policy_implications']['categories']
        elif 'categories' in analysis:
            categories = analysis['categories']
        
        if not categories:
            logger.debug(f"No categories found in analysis for bill {bill.get_bill_identifier()}")
            return
        
        logger.debug(f"Creating category mappings for {len(categories)} categories")
        
        for category_info in categories:
            # Handle different category formats
            category_name = category_info.get('area', category_info.get('name', '')).lower()
            
            # Convert impact_level to relevance score
            impact_level = category_info.get('impact_level', 'medium')
            if impact_level == 'high':
                relevance = 0.8
            elif impact_level == 'medium':
                relevance = 0.6
            elif impact_level == 'low':
                relevance = 0.4
            else:
                relevance = float(category_info.get('relevance', 0.5))
            
            # Get sneakiness score from analysis
            sneakiness = float(category_info.get('sneakiness_score', category_info.get('sneakiness', 0.0)))
            
            logger.debug(f"Processing category: {category_name} with relevance {relevance}")
            
            if relevance > 0.1:  # Only significant relevance
                # Try to find matching policy category by name conversion
                policy_category = self._find_matching_policy_category(category_name)
                
                if policy_category:
                    # Check if mapping already exists
                    existing_mapping = BillCategoryMapping.query.filter_by(
                        bill_id=bill.id,
                        policy_category_id=policy_category.id
                    ).first()
                    
                    if not existing_mapping:
                        mapping = BillCategoryMapping(
                            bill_id=bill.id,
                            policy_category_id=policy_category.id,
                            relevance_score=relevance,
                            sneakiness_score=sneakiness
                        )
                        
                        # Store the category-specific analysis
                        if 'description' in category_info:
                            analysis_data = {
                                'analysis': category_info['description'],
                                'impact_level': category_info.get('impact_level', 'unknown'),
                                'area': category_info.get('area', category_name),
                                'sneakiness_score': sneakiness
                            }
                            
                            # Add sneakiness explanation if available
                            if 'sneakiness_explanation' in category_info:
                                analysis_data['sneakiness_explanation'] = category_info['sneakiness_explanation']
                            
                            mapping.set_category_analysis(analysis_data)
                        
                        db.session.add(mapping)
                        logger.debug(f"Created mapping: {bill.get_bill_identifier()} -> {policy_category.display_name}")
                    else:
                        logger.debug(f"Mapping already exists: {bill.get_bill_identifier()} -> {policy_category.display_name}")
                else:
                    logger.warning(f"No matching policy category found for: {category_name}")
    
    def _find_matching_policy_category(self, category_name: str) -> Optional['PolicyCategory']:
        """Find matching policy category with flexible name matching"""
        category_name = category_name.lower().strip()
        
        # Direct name match
        policy_category = PolicyCategory.query.filter_by(name=category_name.replace(' ', '_').replace('&', 'and')).first()
        if policy_category:
            return policy_category
        
        # Mapping of AI category names to database names
        category_mappings = {
            'public lands and natural resources': 'public_lands_and_natural_resources',
            'native american affairs': 'native_american_affairs', 
            'economic development': 'economic_development',
            'government operations': 'government_operations_and_politics',
            'social services and welfare': 'social_welfare',
            'social security': 'social_security_and_retirement',
            'budget and fiscal policy': 'budget_and_fiscal_policy',
            'healthcare': 'healthcare',
            'education': 'education',
            'environment': 'environmental_protection',
            'transportation': 'transportation',
            'energy': 'energy',
            'defense': 'defense_and_national_security',
            'immigration': 'immigration',
            'taxation': 'taxation',
            'housing': 'housing_and_urban_development',
            'labor': 'labor_and_employment',
            'agriculture': 'agriculture_and_food',
            'technology': 'communications_and_technology',
            'civil rights': 'civil_rights_and_liberties'
        }
        
        if category_name in category_mappings:
            return PolicyCategory.query.filter_by(name=category_mappings[category_name]).first()
        
        # Partial match search
        for policy_cat in PolicyCategory.query.all():
            if category_name in policy_cat.name or policy_cat.name in category_name:
                return policy_cat
        
        return None
    
    def get_status(self) -> Dict:
        """Get current backfill status and progress"""
        return {
            'congress_session': self.state.congress_session,
            'status': self.state.status,
            'processing_mode': self.state.processing_mode,
            'start_time': self.state.start_time,
            'last_update': self.state.last_update,
            'discovery': {
                'complete': self.state.discovery_complete,
                'total_discovered': self.state.total_bills_discovered,
                'offset': self.state.discovery_offset
            },
            'processing': {
                'bills_processed': self.state.bills_processed,
                'bills_analyzed': self.state.bills_analyzed,
                'bills_failed': self.state.bills_failed,
                'current_batch': self.state.current_batch,
                'last_processed': self.state.last_processed_bill
            },
            'errors': {
                'count': len(self.state.errors),
                'api_quota_hits': self.state.api_quota_hits,
                'recent_errors': self.state.errors[-5:] if self.state.errors else []
            },
            'stats': self.state.stats
        }
    
    def pause(self):
        """Pause the backfill process"""
        logger.info("Pausing backfill process")
        self.state.status = BackfillStatus.PAUSED.value
        self._save_state()
    
    def resume(self):
        """Resume the backfill process"""
        logger.info("Resuming backfill process")
        return self.start_backfill(resume=True)
    
    def reset(self):
        """Reset the backfill state (start fresh)"""
        logger.info("Resetting backfill state")
        if self.state_file.exists():
            self.state_file.unlink()
        self.state = BackfillState(
            congress_session=self.config.congress_session,
            status=BackfillStatus.NOT_STARTED.value,
            processing_mode=self.config.processing_mode.value
        )
        self._save_state()


def main():
    """CLI interface for backfill orchestrator"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Backfill Congressional Data")
    parser.add_argument('--congress', type=int, default=119, help='Congress session number')
    parser.add_argument('--mode', choices=['discovery', 'full', 'gaps'], default='full',
                       help='Processing mode')
    parser.add_argument('--batch-size', type=int, default=10, help='Batch size for processing')
    parser.add_argument('--max-bills', type=int, default=1000, help='Maximum bills to process')
    parser.add_argument('--resume', action='store_true', help='Resume from previous state')
    parser.add_argument('--reset', action='store_true', help='Reset state and start fresh')
    parser.add_argument('--status', action='store_true', help='Show current status')
    parser.add_argument('--analyze-gaps', action='store_true', help='Run gap analysis only')
    
    args = parser.parse_args()
    
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create config
    mode_map = {
        'discovery': ProcessingMode.DISCOVERY_ONLY,
        'full': ProcessingMode.FULL_PROCESSING,
        'gaps': ProcessingMode.GAPS_ONLY
    }
    
    config = BackfillConfig(
        congress_session=args.congress,
        processing_mode=mode_map[args.mode],
        batch_size=args.batch_size,
        max_bills_per_session=args.max_bills
    )
    
    # Create orchestrator
    orchestrator = BackfillOrchestrator(config)
    
    # Handle commands
    if args.reset:
        orchestrator.reset()
        print("State reset successfully")
        return
    
    if args.status:
        status = orchestrator.get_status()
        print(json.dumps(status, indent=2))
        return
    
    if args.analyze_gaps:
        gaps = orchestrator.analyze_gaps()
        print(json.dumps(gaps, indent=2))
        return
    
    # Start backfill
    print(f"Starting backfill for Congress {args.congress} in {args.mode} mode")
    success = orchestrator.start_backfill(resume=args.resume)
    
    if success:
        print("Backfill completed successfully!")
    else:
        print("Backfill failed or was paused")
    
    # Show final status
    status = orchestrator.get_status()
    print("\nFinal Status:")
    print(json.dumps(status, indent=2))


if __name__ == "__main__":
    main()