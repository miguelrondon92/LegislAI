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

# Check for production mode early and load environment before any other imports
if '--prod' in sys.argv:
    from dotenv import load_dotenv
    production_env_path = Path(__file__).parent.parent / "config" / "production.env"
    if production_env_path.exists():
        load_dotenv(production_env_path, override=True)
        print(f"🔧 Early production environment loaded from {production_env_path}")

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app import app, db
from db_models import Bill, BillCategoryMapping, PolicyCategory
from services.congress_api import get_shared_congress_api
from services.enhanced_ai_analyzer import get_shared_ai_analyzer
from services.bill_processor import BillProcessor
from services import bill_sync
from services import bill_work_lease

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
                'not_display_ready_bills': 0,
                'visited': 0,
                'ingested': 0,
                'refreshed_only': 0,
                'skipped_fresh': 0,
                'window_start': 0,
                'window_size': 0,
                'catalog_next_index': 0,
            }

@dataclass
class BackfillConfig:
    """Configuration for backfill operations"""
    congress_session: int = 119
    processing_mode: ProcessingMode = ProcessingMode.FULL_PROCESSING
    batch_size: int = 1
    # Window size N for catalog runs (None = no cap / page until API end)
    max_bills_per_session: Optional[int] = None
    # Explicit 0-based catalog start; None → use cursor when continue_from_cursor
    start_index: Optional[int] = None
    continue_from_cursor: bool = True
    congress_api_delay: float = 3.6  # Rate limit for Congress API
    ai_api_delay: float = 4.0  # Rate limit for AI API
    auto_pause_on_quota: bool = True
    save_state_frequency: int = 5  # Save state every N bills
    discovery_limit: int = 250  # Page size for Congress list API
    retry_failed: bool = True
    max_retries: int = 3

class BackfillOrchestrator:
    """
    Main orchestrator for backfilling congressional data.
    
    This class coordinates the discovery and processing of bills from Congress API,
    manages state persistence, and handles rate limiting across multiple APIs.
    """
    
    def __init__(self, config: BackfillConfig = None, *, state_file: Path = None):
        self.config = config or BackfillConfig()
        # Allow callers (--prod) to set state_file BEFORE load so we don't inherit the wrong file
        if state_file is not None:
            self.state_file = Path(state_file)
        else:
            self.state_file = Path("logs") / f"backfill_state_{self.config.congress_session}.json"
        self.state_file.parent.mkdir(exist_ok=True)
        
        # Initialize services — shared Congress + Gemini so spacing/budget are process-wide
        self.congress_api = get_shared_congress_api()
        self.ai_analyzer = get_shared_ai_analyzer()
        self.bill_processor = BillProcessor(
            congress_api=self.congress_api, ai_analyzer=self.ai_analyzer
        )
        self._analysis_holder = bill_work_lease.default_holder("backfill")
        
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

    def _get_or_create_catalog_state(self):
        """Load per-congress catalog cursor; reset if sort_key mismatches."""
        from app import db
        from db_models import BackfillCatalogState

        sort_key = BackfillCatalogState.SORT_INTRODUCED_ASC
        row = BackfillCatalogState.query.get(self.config.congress_session)
        if row is None:
            row = BackfillCatalogState(
                congress=self.config.congress_session,
                sort_key=sort_key,
                next_index=0,
                updated_at=datetime.utcnow(),
            )
            db.session.add(row)
            db.session.commit()
            return row
        if row.sort_key != sort_key:
            logger.warning(
                "Catalog sort_key mismatch (%s != %s); resetting next_index to 0",
                row.sort_key,
                sort_key,
            )
            row.sort_key = sort_key
            row.next_index = 0
            row.updated_at = datetime.utcnow()
            db.session.commit()
        return row

    def _resolve_start_index(self) -> int:
        if self.config.start_index is not None:
            return max(0, int(self.config.start_index))
        if self.config.continue_from_cursor:
            with app.app_context():
                return int(self._get_or_create_catalog_state().next_index or 0)
        return 0

    def _advance_catalog_cursor(self, next_index: int) -> None:
        from app import db

        with app.app_context():
            row = self._get_or_create_catalog_state()
            row.next_index = max(0, int(next_index))
            row.updated_at = datetime.utcnow()
            db.session.commit()
            self.state.stats["catalog_next_index"] = row.next_index

    def fetch_catalog_window(self, start_index: int, count: int) -> List[Dict]:
        """
        Fetch up to `count` bills from the Congress catalog starting at
        0-based `start_index`, ordered by introducedDate ascending.
        """
        from db_models import BackfillCatalogState

        if count is None or count < 1:
            count = 10**9
        start_index = max(0, int(start_index))
        sort_key = BackfillCatalogState.SORT_INTRODUCED_ASC
        page_size = min(250, self.config.discovery_limit or 250)
        offset = start_index
        collected: List[Dict] = []

        logger.info(
            "Fetching catalog window congress=%s start=%s count=%s sort=%s",
            self.config.congress_session,
            start_index,
            count if count < 10**9 else "all",
            sort_key,
        )
        self.state.status = BackfillStatus.DISCOVERING.value
        self._save_state()

        while len(collected) < count:
            limit = min(page_size, count - len(collected))
            params = {
                "limit": limit,
                "offset": offset,
                "sort": sort_key,
            }
            endpoint = f"/bill/{self.config.congress_session}"
            data = self.congress_api._make_request(endpoint, params)
            if not data or "bills" not in data:
                logger.warning("No bills data at offset %s", offset)
                break
            bill_list = data.get("bills") or []
            if not bill_list:
                logger.info("Catalog exhausted at offset %s", offset)
                break
            added_this_page = 0
            for bill_summary in bill_list:
                if len(collected) >= count:
                    break
                try:
                    bill_info = self._extract_bill_info(bill_summary)
                    if bill_info:
                        bill_info["catalog_index"] = start_index + len(collected)
                        collected.append(bill_info)
                        added_this_page += 1
                except Exception as e:
                    logger.error("Error extracting bill in window: %s", e)
            if len(collected) >= count:
                break
            if added_this_page == 0 or len(bill_list) < limit:
                break
            offset += limit
            time.sleep(self.config.congress_api_delay)

        self.state.bills_discovered = collected
        self.state.total_bills_discovered = len(collected)
        self.state.discovery_offset = start_index + len(collected)
        # Window runs are not "whole congress discovered"
        self.state.discovery_complete = False
        self.state.stats["window_start"] = start_index
        self.state.stats["window_size"] = len(collected)
        self.state.stats["session_total_bills"] = len(collected)
        self._save_state()
        logger.info(
            "Catalog window ready: %s bills (indexes %s..%s)",
            len(collected),
            start_index,
            start_index + max(len(collected) - 1, 0) if collected else start_index,
        )
        return collected
    
    def analyze_gaps(self) -> Dict:
        """
        Analyze what bills exist vs. what's in our database.
        
        Returns:
            Dict with gap analysis results
        """
        logger.info("Starting gap analysis...")
        
        with app.app_context():
            # Get database statistics — all ORM access stays inside this context
            db_bills = Bill.query.filter_by(congress=self.config.congress_session).all()
            db_bill_ids = set(bill.get_bill_identifier() for bill in db_bills)
            db_analyzed_bills = [
                bill for bill in db_bills if bill.get_active_ai_analysis()
            ]
            db_display_ready_bills = [bill for bill in db_bills if bill.display_ready]
            db_not_display_ready_bills = [bill for bill in db_bills if not bill.display_ready]

            n_db = len(db_bills)
            n_analyzed = len(db_analyzed_bills)
            n_ready = len(db_display_ready_bills)
            n_not_ready = len(db_not_display_ready_bills)
            
            self.state.stats['db_existing_bills'] = n_db
            self.state.stats['db_analyzed_bills'] = n_analyzed
            self.state.stats['display_ready_bills'] = n_ready
            self.state.stats['not_display_ready_bills'] = n_not_ready
            
            # For analysis-only mode, track display-ready progress
            if self.config.processing_mode == ProcessingMode.ANALYSIS_ONLY:
                self.state.display_ready_start_count = n_ready
                self.state.display_ready_goal_count = n_db  # Goal: all bills display-ready
            
            logger.info(f"Database has {n_db} bills from Congress {self.config.congress_session}")
            logger.info(f"Of those, {n_analyzed} have AI analysis")
            logger.info(f"Display-ready bills: {n_ready}")
            logger.info(f"Not display-ready: {n_not_ready}")
        
            # Need discovery data unless analysis-only or we already have a window list
            if (
                not self.state.discovery_complete
                and not self.state.bills_discovered
                and self.config.processing_mode != ProcessingMode.ANALYSIS_ONLY
            ):
                logger.info("No discovery data available. Need to run discovery first.")
                return {
                    'status': 'discovery_needed',
                    'db_bills': n_db,
                    'db_analyzed_bills': n_analyzed,
                    'discovered_bills': 0,
                    'missing_bills': 'unknown',
                    'unanalyzed_bills': n_db - n_analyzed
                }
        
            # Compare discovered bills vs database (skip for analysis-only mode)
            if self.config.processing_mode == ProcessingMode.ANALYSIS_ONLY:
                # For analysis-only mode, we only work with existing bills
                discovered_bill_ids = set()
                missing_bills = set()
                unanalyzed_bill_ids = [
                    bill.get_bill_identifier()
                    for bill in db_bills
                    if not bill.get_active_ai_analysis()
                ]
            
                self.state.stats['session_total_bills'] = n_db  # Use DB bills as total
                self.state.stats['missing_bills'] = 0  # No missing bills in analysis-only mode
                self.state.stats['unanalyzed_bills'] = len(unanalyzed_bill_ids)
            else:
                discovered_bill_ids = set(bill['identifier'] for bill in self.state.bills_discovered)
                missing_bills = discovered_bill_ids - db_bill_ids
                unanalyzed_bill_ids = [
                    bill.get_bill_identifier()
                    for bill in db_bills
                    if not bill.get_active_ai_analysis()
                ]
            
                self.state.stats['session_total_bills'] = len(discovered_bill_ids)
                self.state.stats['missing_bills'] = len(missing_bills)
                self.state.stats['unanalyzed_bills'] = len(unanalyzed_bill_ids)
        
            gap_analysis = {
                'status': 'complete',
                'congress_session': self.config.congress_session,
                'discovered_bills': len(discovered_bill_ids),
                'db_bills': n_db,
                'db_analyzed_bills': n_analyzed,
                'db_display_ready_bills': n_ready,
                'db_not_display_ready_bills': n_not_ready,
                'missing_bills': len(missing_bills),
                'unanalyzed_bills': len(unanalyzed_bill_ids),
                'missing_bill_samples': list(missing_bills)[:10],
                'unanalyzed_bill_samples': unanalyzed_bill_ids[:10],
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
                pct = (n_ready / n_db * 100) if n_db else 0.0
                logger.info(f"🎯 Analysis-Only Mode Goal: Get all {n_db} bills to display-ready state")
                logger.info(f"📊 Current progress: {n_ready}/{n_db} bills display-ready ({pct:.1f}%)")
        
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
        if max_bills is None:
            # No configured cap — keep paging until the API is exhausted
            max_bills = 10**9
        else:
            max_bills = int(max_bills)
        
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
                    'sort': 'introducedDate+asc'
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
            resume: Whether to resume JSON run state (legacy pause). Catalog
                position uses continue_from_cursor / start_index on config.
            
        Returns:
            bool: True if backfill completed successfully
        """
        logger.info("Starting backfill process")
        
        # Check if we should resume or start fresh (JSON counters / pause)
        if not resume or self.state.status == BackfillStatus.NOT_STARTED.value:
            logger.info("Starting fresh backfill run state")
            self.state = BackfillState(
                congress_session=self.config.congress_session,
                status=BackfillStatus.NOT_STARTED.value,
                processing_mode=self.config.processing_mode.value,
                start_time=datetime.now().isoformat()
            )
        else:
            # Always reflect the mode chosen for this invocation
            self.state.processing_mode = self.config.processing_mode.value
        
        try:
            mode = self.config.processing_mode

            # Full processing: catalog window from cursor / start_index
            if mode == ProcessingMode.FULL_PROCESSING:
                start_index = self._resolve_start_index()
                window_n = self.config.max_bills_per_session
                if window_n is None:
                    window_n = 10**9
                logger.info(
                    "Full processing window start_index=%s max=%s continue_cursor=%s",
                    start_index,
                    window_n if window_n < 10**9 else "all",
                    self.config.continue_from_cursor,
                )
                window = self.fetch_catalog_window(start_index, int(window_n))
                if not window:
                    logger.info("Empty catalog window — nothing to process")
                    self.state.status = BackfillStatus.COMPLETED.value
                    self._save_state()
                    return True
                gap_analysis = self.analyze_gaps()
                ok = self._process_bills(gap_analysis)
                if ok and self.state.status != BackfillStatus.PAUSED.value:
                    self._advance_catalog_cursor(start_index + len(window))
                return ok

            # Step 1: Discovery (if needed, skip for analysis-only mode)
            if not self.state.discovery_complete and mode != ProcessingMode.ANALYSIS_ONLY:
                logger.info("Running bill discovery...")
                if not self.discover_bills():
                    return False
            elif mode == ProcessingMode.ANALYSIS_ONLY:
                logger.info("Skipping discovery phase for analysis-only mode")
                self.state.discovery_complete = True  # Mark as complete to skip future checks
            
            # Step 2: Gap analysis
            logger.info("Running gap analysis...")
            gap_analysis = self.analyze_gaps()
            
            # Step 3: Process bills based on mode
            if mode == ProcessingMode.DISCOVERY_ONLY:
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
                
                # Add unanalyzed bills (new AIAnalysis table, not legacy column)
                unanalyzed_bills = [
                    bill for bill in db_bills if not bill.get_active_ai_analysis()
                ]
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
        
        # Optional cap (UI / CLI max_bills) — applies after mode selection so
        # analysis-only and full_processing both respect a smoke-test limit.
        limit = self.config.max_bills_per_session
        if limit is not None and limit > 0 and len(bills_to_process) > limit:
            logger.info(
                f"Limiting processing to {limit} of {len(bills_to_process)} bills "
                f"(max_bills_per_session)"
            )
            bills_to_process = bills_to_process[:limit]

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
            if self.state.status == BackfillStatus.PAUSED.value:
                logger.info("Backfill paused — skipping remaining batches")
                self._save_state()
                return False

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
                # Honor pause/stop from web UI or auto-pause
                if self.state.status == BackfillStatus.PAUSED.value:
                    logger.info("Backfill paused — stopping batch processing")
                    self._save_state()
                    return False

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
                    if success == "lease_deferred":
                        logger.info(
                            f"Deferred {bill_info['identifier']} (analyze lease held)"
                        )
                        try:
                            from services.pipeline_activity_log import (
                                get_backfill_activity_log,
                            )

                            get_backfill_activity_log().append(
                                "Analyze lease held — deferred",
                                level="info",
                                bill_identifier=bill_info.get("identifier"),
                            )
                        except Exception:
                            pass
                        continue
                    if success:
                        self.state.bills_processed += 1
                        self.state.stats['visited'] = self.state.stats.get('visited', 0) + 1
                        # Count only fresh analyses — not "already_analyzed"
                        if success == "analyzed":
                            self.state.bills_analyzed += 1
                        elif success == "skipped_fresh":
                            self.state.stats['skipped_fresh'] = (
                                self.state.stats.get('skipped_fresh', 0) + 1
                            )
                        elif success == "refreshed_only":
                            self.state.stats['refreshed_only'] = (
                                self.state.stats.get('refreshed_only', 0) + 1
                            )
                        elif success in ("ingested", "complete"):
                            self.state.stats['ingested'] = (
                                self.state.stats.get('ingested', 0) + 1
                            )
                        
                        # Check if bill became display-ready after processing
                        if self.config.processing_mode == ProcessingMode.ANALYSIS_ONLY and not was_display_ready:
                            with app.app_context():
                                existing_bill = Bill.query.filter_by(
                                    congress=bill_info['congress'],
                                    bill_type=bill_info['bill_type'],
                                    bill_number=bill_info['bill_number']
                                ).first()
                                if existing_bill and existing_bill.display_ready:
                                    # Already counted in _process_single_bill when analysis succeeds
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
        """Process a single bill via shared bill_sync + EnhancedAIAnalyzer."""
        identifier = bill_info['identifier']
        logger.debug(f"Processing bill: {identifier}")
        
        try:
            with app.app_context():
                from app import db

                existing_bill = bill_sync.resolve_active_bill(
                    bill_info['congress'],
                    bill_info['bill_type'],
                    bill_info['bill_number'],
                )
                list_update = bill_info.get('update_date')
                
                # In analysis-only mode, check if bill is already display-ready
                if self.config.processing_mode == ProcessingMode.ANALYSIS_ONLY:
                    if existing_bill and existing_bill.display_ready:
                        logger.debug(f"Bill {identifier} already display-ready, skipping")
                        return "already_ready"
                    allow_ingest = False
                    do_refresh = (
                        bill_sync.should_refresh_for_backfill(existing_bill)
                        if existing_bill
                        else True
                    )
                else:
                    # Full / gaps: content ingest only when shared marker says stale
                    allow_ingest = bill_sync.content_may_be_stale(
                        existing_bill, list_update
                    )
                    do_refresh = (
                        bill_sync.should_refresh_for_backfill(existing_bill)
                        if existing_bill
                        else True
                    )

                result = bill_sync.sync_bill(
                    bill_info['congress'],
                    bill_info['bill_type'],
                    bill_info['bill_number'],
                    reason=f"backfill:{self.config.processing_mode.value}",
                    refresh_activity_flag=do_refresh,
                    allow_content_ingest=allow_ingest,
                    congress_update_date=list_update,
                    congress_api=self.congress_api,
                    bill_processor=self.bill_processor,
                )
                bill = result.bill
                if not bill:
                    logger.warning(f"Failed to sync bill {identifier}")
                    return False

                # Catalog walk marker (not used for content staleness)
                try:
                    bill.backfill_last_visited_at = datetime.utcnow()
                    db.session.commit()
                except Exception:
                    try:
                        db.session.rollback()
                    except Exception:
                        pass
                
                # Perform analysis based on mode and what's needed
                if self.config.processing_mode == ProcessingMode.ANALYSIS_ONLY:
                    missing_components = bill_info.get('missing_components', [])
                    logger.debug(f"Bill {identifier} missing components: {missing_components}")
                    needs_analysis = 'ai_analysis' in missing_components
                    needs_categories = 'categories' in missing_components
                    if not needs_analysis and not needs_categories:
                        logger.debug(f"Bill {identifier} already has required analysis components")
                        return "components_complete"
                else:
                    needs_analysis = result.needs_analysis or result.needs_resume
                    needs_categories = False
                
                if (self.config.processing_mode == ProcessingMode.ANALYSIS_ONLY and (needs_analysis or needs_categories)) or \
                   (self.config.processing_mode != ProcessingMode.ANALYSIS_ONLY and needs_analysis):
                    import time
                    
                    logger.debug(f"Starting comprehensive AI analysis for {identifier}")
                    
                    full_text = bill.get_full_text()
                    if not full_text:
                        logger.warning(f"No full text available for analysis: {identifier}")
                        return "no_text"

                    if not bill_work_lease.try_acquire(
                        bill.id,
                        bill_work_lease.KIND_ANALYZE,
                        self._analysis_holder,
                    ):
                        logger.info(
                            f"Analyze lease held for {identifier}; deferring"
                        )
                        return "lease_deferred"
                    
                    text_length = len(full_text)
                    start_time = time.time()
                    
                    logger.info(
                        f"Starting enhanced AI analysis for {identifier} "
                        f"(text length: {text_length:,} characters)"
                    )
                    model_name = getattr(self.ai_analyzer, "model_name", None)
                    try:
                        from services.pipeline_activity_log import (
                            get_backfill_activity_log,
                        )
                        from services.ops_alert_service import (
                            CONTINUATION_FINISHED,
                            CONTINUATION_QUEUED,
                            EMPTY_RESULT,
                            notify_gemini_failure,
                        )

                        get_backfill_activity_log().append(
                            f"Starting AI analysis ({text_length:,} chars)",
                            level="info",
                            bill_identifier=identifier,
                        )
                        notify_gemini_failure(
                            CONTINUATION_QUEUED,
                            f"Backfill analysis queued for {identifier}",
                            severity="info",
                            bill_identifier=identifier,
                            bill_id=bill.id,
                            provider_model=model_name,
                            source="backfill",
                            extra={"event": "queued", "pipeline": "backfill"},
                        )
                    except Exception:
                        pass

                    try:
                        # Analyzer persists AIAnalysis/Summary/categories/hidden provisions/display_ready
                        analysis = self.ai_analyzer.analyze_bill(
                            bill, bill.title, allow_budget_waits=True
                        )
                    finally:
                        bill_work_lease.release(
                            bill.id,
                            bill_work_lease.KIND_ANALYZE,
                            self._analysis_holder,
                        )
                    
                    processing_time = time.time() - start_time
                    
                    if analysis:
                        logger.info(f"✅ Enhanced AI analysis completed for: {identifier}")
                        chunks_analyzed = analysis.get('chunks_analyzed', 0)
                        analysis_method = analysis.get('analysis_method', 'enhanced_backfill')
                        is_partial = bool(analysis.get("is_partial"))
                        
                        logger.info(f"  📊 Method: {analysis_method}")
                        logger.info(f"  🔧 Chunks analyzed: {chunks_analyzed}")
                        logger.info(f"  📝 Text processed: {text_length:,} characters")
                        logger.info(f"  ⏱️ Processing time: {processing_time:.2f} seconds")

                        try:
                            from services.pipeline_activity_log import (
                                get_backfill_activity_log,
                            )
                            from services.ops_alert_service import (
                                CONTINUATION_FINISHED,
                                notify_gemini_failure,
                            )

                            get_backfill_activity_log().append(
                                f"Analysis complete ({analysis_method}"
                                f"{', partial' if is_partial else ''})",
                                level="warning" if is_partial else "info",
                                bill_identifier=identifier,
                            )
                            notify_gemini_failure(
                                CONTINUATION_FINISHED,
                                f"Backfill analysis finished for {identifier}"
                                + (" (partial)" if is_partial else ""),
                                severity="warning" if is_partial else "info",
                                bill_identifier=identifier,
                                bill_id=bill.id,
                                provider_model=model_name,
                                source="backfill",
                                completion_percentage=analysis.get(
                                    "completion_percentage"
                                ),
                                extra={
                                    "event": "finished",
                                    "pipeline": "backfill",
                                    "is_partial": is_partial,
                                },
                            )
                        except Exception:
                            pass
                        
                        # bills_analyzed is incremented by the batch loop when
                        # this returns "analyzed" (avoid double-counting).
                        if bill.display_ready:
                            self.state.bills_made_display_ready += 1
                        return "analyzed"
                    else:
                        logger.warning(f"Analysis returned empty for {identifier}")
                        try:
                            from services.pipeline_activity_log import (
                                get_backfill_activity_log,
                            )
                            from services.ops_alert_service import (
                                EMPTY_RESULT,
                                notify_gemini_failure,
                            )

                            get_backfill_activity_log().append(
                                "Analysis returned empty",
                                level="error",
                                bill_identifier=identifier,
                            )
                            notify_gemini_failure(
                                EMPTY_RESULT,
                                f"Backfill analysis empty for {identifier}",
                                severity="error",
                                bill_identifier=identifier,
                                bill_id=bill.id,
                                provider_model=model_name,
                                source="backfill",
                                extra={"event": "finished", "pipeline": "backfill"},
                            )
                        except Exception:
                            pass
                        return "analysis_empty"
                
                elif self.config.processing_mode == ProcessingMode.ANALYSIS_ONLY and needs_categories:
                    active_analysis = bill.get_active_ai_analysis()
                    if active_analysis:
                        analysis_data = active_analysis.get_analysis_data()
                        if analysis_data and 'policy_implications' in analysis_data:
                            policy_data = analysis_data['policy_implications']
                            if 'categories' in policy_data:
                                self.ai_analyzer._store_policy_categories(
                                    bill, policy_data['categories'], analysis_data
                                )
                                logger.debug(f"Created category mappings for {identifier}")
                                return "categories_added"
                    logger.debug(f"No usable policy data found for {identifier}, needs full analysis")
                    return "needs_full_analysis"
                
                else:
                    if result.created or allow_ingest:
                        return "ingested"
                    if result.actions_added or result.status_changed:
                        return "refreshed_only"
                    return "skipped_fresh"
                
        except Exception as e:
            logger.error(f"Error processing bill {identifier}: {e}")
            return False
    
    def get_status(self) -> Dict:
        """Get current backfill status and progress"""
        catalog = {}
        try:
            with app.app_context():
                row = self._get_or_create_catalog_state()
                catalog = {
                    "next_index": row.next_index,
                    "sort_key": row.sort_key,
                    "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                }
        except Exception as e:
            catalog = {"error": str(e)}

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
            'catalog': catalog,
            'window': {
                'start': self.state.stats.get('window_start'),
                'size': self.state.stats.get('window_size'),
            },
            'processing': {
                'bills_processed': self.state.bills_processed,
                'bills_analyzed': self.state.bills_analyzed,
                'bills_failed': self.state.bills_failed,
                'visited': self.state.stats.get('visited', 0),
                'skipped_fresh': self.state.stats.get('skipped_fresh', 0),
                'refreshed_only': self.state.stats.get('refreshed_only', 0),
                'ingested': self.state.stats.get('ingested', 0),
                'current_batch': self.state.current_batch,
                'last_processed': self.state.last_processed_bill
            },
            'errors': {
                'count': len(self.state.errors),
                'api_quota_hits': self.state.api_quota_hits,
                'recent_errors': self.state.errors[-5:] if self.state.errors else []
            },
            'stats': self.state.stats,
            'max_bills_per_session': self.config.max_bills_per_session,
            'start_index': self.config.start_index,
            'continue_from_cursor': self.config.continue_from_cursor,
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


def _configure_production_environment():
    """Configure production environment settings"""
    # Load production environment variables
    from dotenv import load_dotenv
    
    # Try to load production.env first, then fallback to .env
    production_env_path = Path(__file__).parent.parent / "config" / "production.env"
    if production_env_path.exists():
        load_dotenv(production_env_path, override=True)  # Override existing env vars
        logger.info(f"Loaded production configuration from {production_env_path}")
    else:
        load_dotenv()  # Load from .env as fallback
        logger.info("Loaded configuration from .env file")
    
    # Validate required production environment variables
    required_vars = ['DATABASE_URL', 'GEMINI_API_KEY']
    missing_vars = []
    
    for var in required_vars:
        if not os.environ.get(var):
            missing_vars.append(var)
    
    if missing_vars:
        raise ValueError(f"Missing required production environment variables: {', '.join(missing_vars)}")
    
    # Verify we're using PostgreSQL
    database_url = os.environ.get('DATABASE_URL', '')
    if not database_url.startswith('postgresql://') and not database_url.startswith('postgres://'):
        logger.warning(f"Production mode expects PostgreSQL database, but DATABASE_URL is: {database_url[:20]}...")
    
    logger.info("✅ Production environment configuration validated")
    logger.info(f"✅ Production DATABASE_URL loaded: {database_url[:50]}...")


def _update_app_for_production():
    """Update Flask app configuration for production database"""
    # Override the database URL for production
    production_db_url = os.environ.get('DATABASE_URL')
    if production_db_url:
        app.config['SQLALCHEMY_DATABASE_URI'] = production_db_url
        logger.info(f"🔧 Updated database URL for production: {production_db_url[:30]}...")
        
        # Configure production-specific database settings
        app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
            "pool_recycle": 300,
            "pool_pre_ping": True,
            "pool_size": 10,  # Production pool size
            "max_overflow": 20,  # Production overflow
            "echo": False  # Disable SQL logging in production
        }
        
        # Note: Don't re-initialize db as it's already initialized in app.py
        logger.info("🔧 Database configuration updated for production")


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
    parser.add_argument('--prod', action='store_true', help='Run in production mode with PostgreSQL database')
    
    args = parser.parse_args()
    
    # Configure production environment if --prod flag is used
    if args.prod:
        _configure_production_environment()
        _update_app_for_production()
        print("🔧 Production mode enabled - using PostgreSQL database")
    
    # Production safety confirmation for destructive operations
    if args.prod and args.reset:
        response = input("⚠️  WARNING: You are about to reset backfill state in PRODUCTION mode. Type 'CONFIRM' to proceed: ")
        if response != 'CONFIRM':
            print("❌ Operation cancelled")
            return
    
    # Set up logging with production-appropriate level
    log_level = logging.WARNING if args.prod else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    if args.prod:
        logger.info("🚀 Starting backfill orchestrator in PRODUCTION mode")
        logger.info(f"📊 Database: {os.environ.get('DATABASE_URL', 'Unknown')[:50]}...")
        logger.info(f"🔑 API Key: {'✅ Configured' if os.environ.get('GEMINI_API_KEY') else '❌ Missing'}")
    
    # Create config with production-optimized settings
    mode_map = {
        'discovery': ProcessingMode.DISCOVERY_ONLY,
        'full': ProcessingMode.FULL_PROCESSING,
        'gaps': ProcessingMode.GAPS_ONLY,
        'analysis-only': ProcessingMode.ANALYSIS_ONLY
    }
    
    # Production-specific configuration adjustments
    production_config_overrides = {}
    if args.prod:
        production_config_overrides.update({
            'congress_api_delay': 2.0,  # Slightly faster for production with better infrastructure
            'ai_api_delay': 3.0,  # Slightly faster for production
            'save_state_frequency': 10,  # Save state more frequently in production
        })
    
    config = BackfillConfig(
        congress_session=args.congress,
        processing_mode=mode_map[args.mode],
        batch_size=args.batch_size,
        max_bills_per_session=args.max_bills,
        **production_config_overrides
    )
    
    # Create orchestrator — set prod state file BEFORE __init__ loads state
    if args.prod:
        state_file = Path("logs") / f"backfill_state_prod_{config.congress_session}.json"
        logger.info(f"📁 Using production state file: {state_file}")
        orchestrator = BackfillOrchestrator(config, state_file=state_file)
    else:
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
    
    # Start backfill with production-specific messaging
    environment = "PRODUCTION" if args.prod else "DEVELOPMENT"
    print(f"🚀 Starting backfill for Congress {args.congress} in {args.mode} mode ({environment} environment)")
    
    if args.prod:
        print("📊 Production Configuration:")
        print(f"   • Database: PostgreSQL")
        print(f"   • Batch size: {args.batch_size}")
        print(f"   • Congress API delay: {config.congress_api_delay}s")
        print(f"   • AI API delay: {config.ai_api_delay}s")
        print(f"   • State file: backfill_state_prod_{args.congress}.json")
    
    success = orchestrator.start_backfill(resume=args.resume)
    
    if success:
        completion_msg = "✅ Backfill completed successfully!"
        if args.prod:
            completion_msg += " (PRODUCTION mode)"
        print(completion_msg)
    else:
        failure_msg = "❌ Backfill failed or was paused"
        if args.prod:
            failure_msg += " (PRODUCTION mode)"
        print(failure_msg)
    
    # Show final status
    status = orchestrator.get_status()
    print(f"\n📋 Final Status ({environment}):")
    print(json.dumps(status, indent=2))


if __name__ == "__main__":
    main()