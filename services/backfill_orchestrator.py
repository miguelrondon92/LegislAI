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
    ANALYSIS_ONLY = "analysis_only"  # Get existing bills to display-ready state, don't add new ones

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
    
    # Display-ready tracking (for analysis-only mode)
    display_ready_start_count: int = 0
    display_ready_goal_count: int = 0
    bills_made_display_ready: int = 0
    
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
                'unanalyzed_bills': 0,
                'display_ready_bills': 0,
                'not_display_ready_bills': 0
            }

@dataclass
class BackfillConfig:
    """Configuration for backfill operations"""
    congress_session: int = 119
    processing_mode: ProcessingMode = ProcessingMode.FULL_PROCESSING
    batch_size: int = 1
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
            db_display_ready_bills = [bill for bill in db_bills if bill.display_ready]
            db_not_display_ready_bills = [bill for bill in db_bills if not bill.display_ready]
            
            self.state.stats['db_existing_bills'] = len(db_bills)
            self.state.stats['db_analyzed_bills'] = len(db_analyzed_bills)
            self.state.stats['display_ready_bills'] = len(db_display_ready_bills)
            self.state.stats['not_display_ready_bills'] = len(db_not_display_ready_bills)
            
            # For analysis-only mode, track display-ready progress
            if self.config.processing_mode == ProcessingMode.ANALYSIS_ONLY:
                self.state.display_ready_start_count = len(db_display_ready_bills)
                self.state.display_ready_goal_count = len(db_bills)  # Goal: all bills display-ready
            
            logger.info(f"Database has {len(db_bills)} bills from Congress {self.config.congress_session}")
            logger.info(f"Of those, {len(db_analyzed_bills)} have AI analysis")
            logger.info(f"Display-ready bills: {len(db_display_ready_bills)}")
            logger.info(f"Not display-ready: {len(db_not_display_ready_bills)}")
        
        # If we haven't discovered bills yet, we need to do discovery first
        # Exception: analysis-only mode doesn't need discovery since it only works with existing bills
        if not self.state.discovery_complete and self.config.processing_mode != ProcessingMode.ANALYSIS_ONLY:
            logger.info("No discovery data available. Need to run discovery first.")
            return {
                'status': 'discovery_needed',
                'db_bills': len(db_bills),
                'db_analyzed_bills': len(db_analyzed_bills),
                'discovered_bills': 0,
                'missing_bills': 'unknown',
                'unanalyzed_bills': len(db_bills) - len(db_analyzed_bills)
            }
        
        # Compare discovered bills vs database (skip for analysis-only mode)
        if self.config.processing_mode == ProcessingMode.ANALYSIS_ONLY:
            # For analysis-only mode, we only work with existing bills
            discovered_bill_ids = set()
            missing_bills = set()
            unanalyzed_bills = [bill for bill in db_bills if not bill.ai_analysis]
            
            self.state.stats['session_total_bills'] = len(db_bills)  # Use DB bills as total
            self.state.stats['missing_bills'] = 0  # No missing bills in analysis-only mode
            self.state.stats['unanalyzed_bills'] = len(unanalyzed_bills)
        else:
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
            'db_display_ready_bills': len(db_display_ready_bills),
            'db_not_display_ready_bills': len(db_not_display_ready_bills),
            'missing_bills': len(missing_bills),
            'unanalyzed_bills': len(unanalyzed_bills),
            'missing_bill_samples': list(missing_bills)[:10],
            'unanalyzed_bill_samples': [bill.get_bill_identifier() for bill in unanalyzed_bills[:10]]
        }
        
        logger.info("Gap Analysis Results:")
        logger.info(f"  Total bills discovered: {gap_analysis['discovered_bills']}")
        logger.info(f"  Bills in database: {gap_analysis['db_bills']}")
        logger.info(f"  Bills with analysis: {gap_analysis['db_analyzed_bills']}")
        logger.info(f"  Display-ready bills: {gap_analysis['db_display_ready_bills']}")
        logger.info(f"  Not display-ready: {gap_analysis['db_not_display_ready_bills']}")
        logger.info(f"  Missing from database: {gap_analysis['missing_bills']}")
        logger.info(f"  Missing analysis: {gap_analysis['unanalyzed_bills']}")
        
        # Special logging for analysis-only mode
        if self.config.processing_mode == ProcessingMode.ANALYSIS_ONLY:
            logger.info(f"🎯 Analysis-Only Mode Goal: Get all {len(db_bills)} bills to display-ready state")
            logger.info(f"📊 Current progress: {len(db_display_ready_bills)}/{len(db_bills)} bills display-ready ({len(db_display_ready_bills)/len(db_bills)*100:.1f}%)")
        
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
            # Step 1: Discovery (if needed, skip for analysis-only mode)
            if not self.state.discovery_complete and self.config.processing_mode != ProcessingMode.ANALYSIS_ONLY:
                logger.info("Running bill discovery...")
                if not self.discover_bills():
                    return False
            elif self.config.processing_mode == ProcessingMode.ANALYSIS_ONLY:
                logger.info("Skipping discovery phase for analysis-only mode")
                self.state.discovery_complete = True  # Mark as complete to skip future checks
            
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
        elif self.config.processing_mode == ProcessingMode.ANALYSIS_ONLY:
            # Focus on getting bills to display-ready state (don't add new bills)
            with app.app_context():
                db_bills = Bill.query.filter_by(congress=self.config.congress_session).all()
                
                # Target bills that are not display-ready
                not_display_ready_bills = [bill for bill in db_bills if not bill.display_ready]
                logger.info(f"Found {len(not_display_ready_bills)} bills not ready for display")
                
                # Log analysis of what's missing for display-ready status
                missing_analysis_count = 0
                missing_complexity_count = 0
                missing_summary_count = 0
                missing_categories_count = 0
                
                for bill in not_display_ready_bills:
                    # Check what each bill is missing
                    reasons = []
                    if not bill.title or not bill.summary:
                        reasons.append("basic_data")
                    
                    ai_analysis = bill.get_active_ai_analysis()
                    if not ai_analysis:
                        reasons.append("ai_analysis")
                        missing_analysis_count += 1
                    elif ai_analysis.complexity_score is None:
                        reasons.append("complexity_score")
                        missing_complexity_count += 1
                    
                    summary = bill.get_active_summary()
                    if not summary or not summary.summary_text:
                        reasons.append("summary")
                        missing_summary_count += 1
                    
                    from db_models import BillCategoryMapping
                    categories = db.session.query(BillCategoryMapping).filter_by(bill_id=bill.id).first()
                    if not categories:
                        reasons.append("categories")
                        missing_categories_count += 1
                    
                    bill_info = {
                        'identifier': bill.get_bill_identifier(),
                        'congress': bill.congress,
                        'bill_type': bill.bill_type,
                        'bill_number': bill.bill_number,
                        'title': bill.title,
                        'existing_in_db': True,
                        'missing_components': reasons
                    }
                    bills_to_process.append(bill_info)
                
                logger.info(f"Display-ready analysis breakdown:")
                logger.info(f"  Missing AI analysis: {missing_analysis_count}")
                logger.info(f"  Missing complexity score: {missing_complexity_count}")
                logger.info(f"  Missing summary: {missing_summary_count}")
                logger.info(f"  Missing categories: {missing_categories_count}")
                logger.info(f"  Total bills to process: {len(bills_to_process)}")
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
                    # Check if bill was display-ready before processing
                    was_display_ready = False
                    if self.config.processing_mode == ProcessingMode.ANALYSIS_ONLY:
                        with app.app_context():
                            existing_bill = Bill.query.filter_by(
                                congress=bill_info['congress'],
                                bill_type=bill_info['bill_type'],
                                bill_number=bill_info['bill_number']
                            ).first()
                            if existing_bill:
                                was_display_ready = existing_bill.display_ready
                    
                    success = self._process_single_bill(bill_info)
                    if success:
                        self.state.bills_processed += 1
                        if 'analyzed' in str(success).lower():
                            self.state.bills_analyzed += 1
                        
                        # Check if bill became display-ready after processing
                        if self.config.processing_mode == ProcessingMode.ANALYSIS_ONLY and not was_display_ready:
                            with app.app_context():
                                existing_bill = Bill.query.filter_by(
                                    congress=bill_info['congress'],
                                    bill_type=bill_info['bill_type'],
                                    bill_number=bill_info['bill_number']
                                ).first()
                                if existing_bill and existing_bill.display_ready:
                                    self.state.bills_made_display_ready += 1
                                    logger.info(f"✅ {bill_info['identifier']} is now display-ready!")
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
                if self.config.processing_mode == ProcessingMode.ANALYSIS_ONLY:
                    current_display_ready = self.state.display_ready_start_count + self.state.bills_made_display_ready
                    progress_pct = (current_display_ready / self.state.display_ready_goal_count * 100) if self.state.display_ready_goal_count > 0 else 0
                    logger.info(f"Progress: {self.state.bills_processed} processed, {self.state.bills_analyzed} analyzed, {self.state.bills_failed} failed")
                    logger.info(f"📊 Display-ready progress: {current_display_ready}/{self.state.display_ready_goal_count} ({progress_pct:.1f}%) - {self.state.bills_made_display_ready} made display-ready this session")
                else:
                    logger.info(f"Progress: {self.state.bills_processed} processed, {self.state.bills_analyzed} analyzed, {self.state.bills_failed} failed")
        
        # Mark as completed
        self.state.status = BackfillStatus.COMPLETED.value
        self._save_state()
        
        logger.info("Backfill processing completed!")
        logger.info(f"Final stats: {self.state.bills_processed} processed, {self.state.bills_analyzed} analyzed, {self.state.bills_failed} failed")
        
        # Special completion summary for analysis-only mode
        if self.config.processing_mode == ProcessingMode.ANALYSIS_ONLY:
            final_display_ready = self.state.display_ready_start_count + self.state.bills_made_display_ready
            final_progress_pct = (final_display_ready / self.state.display_ready_goal_count * 100) if self.state.display_ready_goal_count > 0 else 0
            logger.info("🎯 Analysis-Only Mode Results:")
            logger.info(f"   Started with: {self.state.display_ready_start_count} display-ready bills")
            logger.info(f"   Made display-ready: {self.state.bills_made_display_ready} bills")
            logger.info(f"   Final count: {final_display_ready}/{self.state.display_ready_goal_count} bills display-ready ({final_progress_pct:.1f}%)")
            
            if final_display_ready == self.state.display_ready_goal_count:
                logger.info("🎉 SUCCESS: All bills are now display-ready!")
            else:
                remaining = self.state.display_ready_goal_count - final_display_ready
                logger.info(f"📋 {remaining} bills still need work to become display-ready")
        
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
                
                # In analysis-only mode, check if bill is already display-ready instead of just analyzed
                if self.config.processing_mode == ProcessingMode.ANALYSIS_ONLY:
                    if existing_bill and existing_bill.display_ready:
                        logger.debug(f"Bill {identifier} already display-ready, skipping")
                        return "already_ready"
                else:
                    # For other modes, skip if already analyzed
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
                
                # Perform analysis based on mode and what's needed
                if bill:
                    # For analysis-only mode, check what specific components are missing
                    if self.config.processing_mode == ProcessingMode.ANALYSIS_ONLY:
                        missing_components = bill_info.get('missing_components', [])
                        logger.debug(f"Bill {identifier} missing components: {missing_components}")
                        
                        # Only perform analysis if specific components are missing
                        needs_analysis = 'ai_analysis' in missing_components
                        needs_categories = 'categories' in missing_components
                        
                        if not needs_analysis and not needs_categories:
                            logger.debug(f"Bill {identifier} already has required analysis components")
                            return "components_complete"
                    else:
                        # For other modes, check both old and new analysis structures
                        has_old_analysis = bool(bill.ai_analysis)
                        has_new_analysis = bool(bill.get_active_ai_analysis()) if hasattr(bill, 'get_active_ai_analysis') else False
                        needs_analysis = not has_old_analysis and not has_new_analysis
                    
                    # Perform analysis if needed
                    if (self.config.processing_mode == ProcessingMode.ANALYSIS_ONLY and (needs_analysis or needs_categories)) or \
                       (self.config.processing_mode != ProcessingMode.ANALYSIS_ONLY and needs_analysis):
                        import time
                        
                        logger.debug(f"Starting comprehensive AI analysis for {identifier}")
                        
                        # Get full text for analysis
                        full_text = bill.get_full_text()
                        if not full_text:
                            # Fallback to Congress API text fetch
                            logger.debug(f"Fetching full text from API for analysis: {identifier}")
                            full_text = self.congress_api.get_bill_text(
                                bill.congress, 
                                bill.bill_type, 
                                bill.bill_number
                            )
                        
                        if not full_text:
                            logger.warning(f"No full text available for analysis: {identifier}")
                            return "no_text"
                        
                        text_length = len(full_text)
                        start_time = time.time()
                        
                        logger.info(f"Starting enhanced AI analysis for {identifier} "
                                   f"(text length: {text_length:,} characters)")
                        
                        # Perform comprehensive analysis using EnhancedAIAnalyzer
                        # This includes: summary, policy implications, stakeholders, complexity, controversy,
                        # hidden provisions, anomalies, suspicious language, cross-references, risk scoring
                        analysis = self.ai_analyzer.analyze_bill(bill, bill.title)
                        
                        processing_time = time.time() - start_time
                        
                        if analysis:
                            # The EnhancedAIAnalyzer automatically handles new database structure creation
                            logger.info(f"✅ Enhanced AI analysis completed for: {identifier}")
                            
                            # Store policy categories with sneakiness scoring (equivalent to workflow orchestrator)
                            if 'policy_implications' in analysis:
                                policy_data = analysis['policy_implications']
                                # Check for legacy categories format or new category_breakdown format
                                categories = policy_data.get('categories', [])
                                if not categories and 'category_breakdown' in policy_data:
                                    # Convert new format to legacy format for category storage
                                    categories = []
                                    for cat_name, cat_data in policy_data['category_breakdown'].items():
                                        categories.append({
                                            'area': cat_name,
                                            'impact_level': 'high' if cat_data.get('relevance_score', 0) >= 0.7 else 'medium',
                                            'analysis': cat_data.get('reasoning', '')
                                        })
                                
                                if categories:
                                    self._create_category_mappings_with_sneakiness(bill, categories, analysis)
                            
                            # Store hidden provisions with detailed reasoning
                            if 'hidden_provisions' in analysis:
                                self._store_hidden_provisions(bill, analysis['hidden_provisions'], analysis)
                            
                            # Log comprehensive analysis information (same as workflow orchestrator)
                            chunks_analyzed = analysis.get('chunks_analyzed', 0)
                            analysis_method = analysis.get('analysis_method', 'enhanced_backfill')
                            
                            logger.info(f"  📊 Method: {analysis_method}")
                            logger.info(f"  🔧 Chunks analyzed: {chunks_analyzed}")
                            logger.info(f"  📝 Text processed: {text_length:,} characters")
                            logger.info(f"  ⏱️ Processing time: {processing_time:.2f} seconds")
                            if processing_time > 0:
                                logger.info(f"  🚀 Processing speed: {text_length/processing_time:,.0f} chars/sec")
                            
                            # Log analysis components
                            if 'summary' in analysis:
                                logger.info(f"  📝 Summary generated")
                            if 'policy_implications' in analysis:
                                policy_data = analysis['policy_implications']
                                primary_area = policy_data.get('primary_category') or policy_data.get('primary_policy_area', 'Unknown')
                                logger.info(f"  🎯 Primary policy area: {primary_area}")
                            if 'stakeholders' in analysis:
                                logger.info(f"  👥 Stakeholder analysis completed")
                            if 'hidden_provisions' in analysis:
                                hidden_data = analysis['hidden_provisions']
                                if isinstance(hidden_data, dict):
                                    provisions_count = len(hidden_data.get('detected_provisions', []))
                                    risk_score = hidden_data.get('overall_hidden_risk_score', 0)
                                    logger.info(f"  🕵️ Hidden provisions: {provisions_count} detected, risk: {risk_score:.2f}")
                            if 'complexity_assessment' in analysis:
                                complexity_data = analysis['complexity_assessment']
                                if isinstance(complexity_data, dict):
                                    complexity_score = complexity_data.get('complexity_score', 0)
                                    logger.info(f"  🧮 Complexity score: {complexity_score:.2f}")
                            if 'controversy_score' in analysis:
                                controversy_score = analysis.get('controversy_score', 0)
                                logger.info(f"  ⚡ Controversy score: {controversy_score:.2f}")
                            if 'overall_risk_score' in analysis:
                                risk_score = analysis.get('overall_risk_score', 0)
                                logger.info(f"  🚨 Overall risk score: {risk_score:.2f}")
                            
                            # Also set old field for backward compatibility
                            bill.set_ai_analysis(analysis)
                            db.session.commit()
                            
                            logger.debug(f"Successfully completed comprehensive analysis for {identifier}")
                            return "analyzed"
                        else:
                            logger.warning(f"AI analysis failed for {identifier}")
                            return "analysis_failed"
                    
                    # Handle case where bill only needs category mappings (analysis-only mode)
                    elif self.config.processing_mode == ProcessingMode.ANALYSIS_ONLY and needs_categories and not needs_analysis:
                        logger.debug(f"Bill {identifier} needs category mappings only")
                        
                        # Get existing analysis to extract categories
                        active_analysis = bill.get_active_ai_analysis()
                        if active_analysis:
                            analysis_data = active_analysis.get_analysis_data()
                            if analysis_data and 'policy_implications' in analysis_data:
                                policy_data = analysis_data['policy_implications']
                                if 'categories' in policy_data:
                                    # Store category mappings using enhanced AI analyzer method
                                    self.ai_analyzer._store_policy_categories(bill, policy_data['categories'], analysis_data)
                                    logger.debug(f"Created category mappings for {identifier}")
                                    return "categories_added"
                        
                        # Fallback: if no usable analysis data, we need full analysis
                        logger.debug(f"No usable policy data found for {identifier}, needs full analysis")
                        return "needs_full_analysis"
                    
                    else:
                        logger.debug(f"Bill {identifier} processing complete")
                        return "complete"
                
                return "processed"
                
        except Exception as e:
            logger.error(f"Error processing bill {identifier}: {e}")
            return False
    
    def _create_category_mappings_with_sneakiness(self, bill: Bill, categories: List[Dict], analysis: Dict = None):
        """Store policy category mappings for the bill, including sneakiness score per category"""
        try:
            import re
            import json
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
                area = category_data.get('area')
                if not area:
                    continue
                try:
                    # Find or create policy category
                    policy_category = PolicyCategory.query.filter_by(name=area).first()
                    if not policy_category:
                        policy_category = PolicyCategory(
                            name=area,
                            display_name=area.title(),
                            description=f"Policy area: {area}",
                            color='#007bff',
                            icon='policy',
                            is_active=True
                        )
                        db.session.add(policy_category)
                        db.session.flush()
                        logger.info(f"Created new policy category: {area}")
                    
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
                        score = 0.8
                    
                    sneakiness_score = sneakiness_by_category.get(area, 0.0)
                    
                    # Extract section reference and title information
                    section_reference = None
                    if 'section' in category_data:
                        section_ref = category_data['section']
                    elif 'reasoning' in category_data:
                        # Try to extract section info from reasoning text
                        reasoning = category_data['reasoning']
                        import re
                        section_match = re.search(r'[Ss]ection\s+(\d+[\w\-\.]*)', reasoning)
                        if section_match:
                            section_reference = f"Section {section_match.group(1)}"
                    
                    # Include title in section reference if available
                    if category_data.get('title') and section_reference:
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
                
                # Update display_ready status after policy categories are stored
                if hasattr(bill, 'update_display_ready_status'):
                    status_changed = bill.update_display_ready_status()
                    if status_changed:
                        logger.info(f"Bill {bill.get_bill_identifier()} is now display ready")
            else:
                logger.warning(f"No new policy category mappings were stored for {bill.get_bill_identifier()}")
                
        except Exception as e:
            logger.error(f"Error storing policy categories for {bill.get_bill_identifier()}: {e}")
            db.session.rollback()
    
    def _store_hidden_provisions(self, bill: Bill, hidden_provisions_data: Dict, full_analysis: Dict):
        """Store detected hidden provisions with detailed reasoning in the database"""
        try:
            from db_models import HiddenProvision
            
            # Clear existing hidden provisions for this bill
            with app.app_context():
                existing_provisions = HiddenProvision.query.filter_by(bill_id=bill.id).all()
                for provision in existing_provisions:
                    db.session.delete(provision)
                
                provisions_stored = 0
                detected_provisions = hidden_provisions_data.get('detected_provisions', [])
                
                # Get analysis version to link provisions to specific analysis
                analysis_version = 1
                if hasattr(bill, 'get_active_ai_analysis'):
                    ai_analysis = bill.get_active_ai_analysis()
                    if ai_analysis:
                        analysis_version = ai_analysis.analysis_version
                
                logger.info(f"Processing {len(detected_provisions)} hidden provisions for {bill.get_bill_identifier()}")
                
                for provision_data in detected_provisions:
                    try:
                        # Extract provision details
                        suspicious_provisions = provision_data.get('suspicious_provisions', [])
                        chunk_index = provision_data.get('chunk_index', 0)
                        chunk_type = provision_data.get('chunk_type', 'unknown')
                        overall_assessment = provision_data.get('overall_assessment', '')
                        risk_level = provision_data.get('risk_level', 'low')
                        confidence_score = provision_data.get('confidence_score', 0.0)
                        
                        # Create a provision record for each suspicious provision found
                        for suspicious_provision in suspicious_provisions:
                            provision = HiddenProvision(
                                bill_id=bill.id,
                                provision_type=suspicious_provision.get('type', 'Unknown'),
                                provision_text=suspicious_provision.get('text', '')[:2000],  # Limit text length
                                risk_level=risk_level,
                                confidence_score=confidence_score,
                                potential_impact=suspicious_provision.get('potential_impact', ''),
                                recommendation=suspicious_provision.get('recommendation', ''),
                                overall_assessment=overall_assessment,
                                chunk_index=chunk_index,
                                chunk_type=chunk_type,
                                analysis_version=analysis_version,
                                detection_method='ai_enhanced'
                            )
                            
                            # Store risk factors as JSON
                            risk_factors = suspicious_provision.get('risk_factors', [])
                            provision.set_risk_factors(risk_factors)
                            
                            db.session.add(provision)
                            provisions_stored += 1
                            
                            logger.debug(f"Stored hidden provision: {provision.provision_type} "
                                       f"(risk: {risk_level}, confidence: {confidence_score:.2f})")
                        
                    except Exception as provision_error:
                        logger.error(f"Error processing individual provision: {provision_error}")
                        continue
                
                if provisions_stored > 0:
                    db.session.commit()
                    logger.info(f"✅ Successfully stored {provisions_stored} hidden provisions for {bill.get_bill_identifier()}")
                    
                    # Log summary of risk levels
                    risk_summary = {}
                    for provision_data in detected_provisions:
                        risk_level = provision_data.get('risk_level', 'low')
                        risk_summary[risk_level] = risk_summary.get(risk_level, 0) + len(provision_data.get('suspicious_provisions', []))
                    
                    if risk_summary:
                        summary_str = ", ".join([f"{count} {level}" for level, count in risk_summary.items()])
                        logger.info(f"   📊 Risk distribution: {summary_str}")
                        
                        # Log high-risk provisions for immediate attention
                        high_risk_count = risk_summary.get('high', 0)
                        if high_risk_count > 0:
                            logger.warning(f"   ⚠️ {high_risk_count} HIGH-RISK provisions detected - requires immediate review")
                else:
                    logger.info(f"No hidden provisions to store for {bill.get_bill_identifier()}")
                    
        except Exception as e:
            logger.error(f"Error storing hidden provisions for {bill.get_bill_identifier()}: {e}")
            db.session.rollback()

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
    parser.add_argument('--mode', choices=['discovery', 'full', 'gaps', 'analysis-only'], default='full',
                       help='Processing mode')
    parser.add_argument('--batch-size', type=int, default=1, help='Batch size for processing (default: 1 for careful, API-friendly processing)')
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
        'gaps': ProcessingMode.GAPS_ONLY,
        'analysis-only': ProcessingMode.ANALYSIS_ONLY
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