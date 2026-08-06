"""
Workflow Orchestrator for Legislative Analysis Platform

This file is now Flask-independent and uses a plain SQLAlchemy session for all DB/model access.
- RSS monitoring, bill fetching, and analysis can run as a standalone service.
- User subscriptions and alert delivery remain in the Flask app.
- All DB/model access is via a plain SQLAlchemy session (not Flask-SQLAlchemy).
"""

import logging
import time
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set
from dataclasses import dataclass
from enum import Enum
import json

from db_models import Bill, BillAction, User, Alert, UserBillAlignment, PolicyCategory, UserPolicySubscription
from services.rss_monitoring import PersistentRSSMonitor
from services.enhanced_ai_analyzer import get_shared_ai_analyzer
from services.congress_api import get_shared_congress_api
from services import bill_sync
from services import bill_work_lease
from services.database_session import get_db_session, get_global_session

# Use the independent database session
session = get_global_session()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/workflow.log'),
        logging.StreamHandler()
    ]
)

class WorkflowStatus(Enum):
    """Workflow status enumeration"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"

@dataclass
class WorkflowItem:
    """Represents a single workflow item"""
    bill_identifier: str
    congress: int
    bill_type: str
    bill_number: int
    title: str
    source: str  # 'rss' or 'backfill'
    discovered_at: datetime
    status: WorkflowStatus
    bill_id: Optional[int] = None
    analysis_completed: bool = False
    alerts_generated: bool = False
    error_message: Optional[str] = None
    processing_started: Optional[datetime] = None
    processing_completed: Optional[datetime] = None
    # Enhanced chunked analysis metadata
    text_length: Optional[int] = None
    chunks_analyzed: Optional[int] = None
    analysis_method: Optional[str] = None
    processing_time: Optional[float] = None
    # SyncResult flags — gate notifications on real changes
    sync_created: bool = False
    sync_actions_added: int = 0
    sync_status_changed: bool = False
    analysis_ran: bool = False

class WorkflowOrchestrator:
    """
    Main orchestrator for the legislative analysis workflow
    Focuses on two main goals:
    1. Store AI analysis in the database
    2. Push alerts to users based on their preferences
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.rss_monitor = PersistentRSSMonitor()
        self.ai_analyzer = get_shared_ai_analyzer()
        # Use notification helper to avoid circular imports
        self.notification_service = None  # Will use notification_helper instead
        self.congress_api = get_shared_congress_api()
        self._analysis_holder = bill_work_lease.default_holder("workflow")
        
        # Workflow state
        self.workflow_queue: List[WorkflowItem] = []
        self.processing_lock = threading.Lock()
        self.is_running = False
        # Bill-level queue dedupe (RSS entry ids alone can enqueue the same bill twice)
        self._queued_bill_keys: Set[str] = set()
        
        # Statistics
        self.stats = {
            'bills_discovered': 0,
            'bills_processed': 0,
            'bills_analyzed': 0,
            'alerts_generated': 0,
            'errors': 0,
            'last_run': None,
            'rss_items_processed': 0,
            'backfill_items_processed': 0,
            # Rate limiting tracking
            'rate_limit_hits': 0,
            'last_rate_limit_time': None,
            'workflow_stopped_due_to_rate_limit': False,
            # Enhanced chunked analysis statistics
            'total_chunks_analyzed': 0,
            'total_text_processed': 0,
            'chunked_analysis_count': 0,
            'truncated_analysis_count': 0,
            'analysis_methods': {
                'chunked': 0,
                'truncated': 0,
                'unknown': 0
            },
            'processing_times': {
                'total_analysis_time': 0.0,
                'average_analysis_time': 0.0,
                'fastest_analysis': float('inf'),
                'slowest_analysis': 0.0
            },
            # Hidden provision detection statistics
            'hidden_provisions_detected': 0,
            'suspicious_chunks_found': 0,
            'anomalies_detected': 0,
            'cross_references_analyzed': 0,
            'high_risk_bills': 0,
            'medium_risk_bills': 0,
            'low_risk_bills': 0,
            'hidden_detection_methods': {
                'pattern_based': 0,
                'ai_analysis': 0,
                'cross_chunk': 0,
                'anomaly_detection': 0
            }
        }
    
    def start_workflow(self, check_interval: int = 300, enable_rss: bool = True, enable_backfill: bool = False):
        """
        Start the complete workflow monitoring
        
        Args:
            check_interval: Seconds between RSS checks
            enable_rss: Whether to enable RSS monitoring
            enable_backfill: Whether to enable backfilling from previous bills
        """
        self.logger.info("Starting Legislative Analysis Workflow")
        self.logger.info(f"RSS Monitoring: {'Enabled' if enable_rss else 'Disabled'}")
        self.logger.info(f"Backfill Processing: {'Enabled' if enable_backfill else 'Disabled'}")
        
        # Reset rate limit state when starting
        if self.stats['workflow_stopped_due_to_rate_limit']:
            self.logger.info("🔄 Resetting rate limit state for new workflow run")
            self.reset_rate_limit_state()
        
        self.is_running = True
        
        # Start RSS monitoring if enabled
        if enable_rss:
            def rss_callback(item: Dict):
                """Callback for new RSS items"""
                self._handle_new_rss_item(item)
            
            rss_thread = threading.Thread(
                target=self._run_rss_monitoring,
                args=(rss_callback, check_interval),
                daemon=True
            )
            rss_thread.start()
            self.logger.info("RSS monitoring thread started")
        
        # Start backfill processing if enabled
        if enable_backfill:
            backfill_thread = threading.Thread(
                target=self._run_backfill_processor,
                daemon=True
            )
            backfill_thread.start()
            self.logger.info("Backfill processing thread started")
        
        # Start workflow processing in main thread
        self._run_workflow_processor()
    
    def _run_rss_monitoring(self, callback, check_interval: int):
        """Run RSS monitoring in a separate thread"""
        try:
            self.rss_monitor.monitor_feeds(
                keywords=['bill', 'legislation', 'act', 'resolution'],
                callback=callback,
                check_interval=check_interval
            )
        except Exception as e:
            self.logger.error(f"RSS monitoring error: {e}")
    
    def _run_backfill_processor(self):
        """Process existing bills that don't have AI analysis"""
        self.logger.info("Starting backfill processor")
        
        while self.is_running:
            try:
                # Find bills without AI analysis via shared bill_sync helper
                bills_without_analysis = bill_sync.get_bills_without_analysis(limit=10)
                
                for bill in bills_without_analysis:
                    if not self.is_running:
                        break
                    
                    bill_key = f"{bill.congress}-{bill.bill_type}-{bill.bill_number}"
                    with self.processing_lock:
                        if bill_key in self._queued_bill_keys:
                            continue
                    
                    # Create workflow item for backfill
                    workflow_item = WorkflowItem(
                        bill_identifier=bill.get_bill_identifier(),
                        congress=bill.congress,
                        bill_type=bill.bill_type,
                        bill_number=bill.bill_number,
                        title=bill.title or f"Bill {bill.get_bill_identifier()}",
                        source='backfill',
                        discovered_at=datetime.utcnow(),
                        status=WorkflowStatus.PENDING,
                        bill_id=bill.id
                    )
                    
                    # Add to processing queue
                    with self.processing_lock:
                        self._queued_bill_keys.add(bill_key)
                        self.workflow_queue.append(workflow_item)
                    
                    self.stats['bills_discovered'] += 1
                    self.stats['backfill_items_processed'] += 1
                    self.logger.info(f"Added bill to backfill queue: {workflow_item.bill_identifier}")
                
                # Sleep before next backfill cycle
                time.sleep(300)  # Check every 5 minutes
                
            except Exception as e:
                self.logger.error(f"Backfill processing error: {e}")
                time.sleep(300)
    
    def _run_workflow_processor(self):
        """Main workflow processing loop"""
        self.logger.info("Starting workflow processor")
        
        while self.is_running:
            try:
                with self.processing_lock:
                    # Process items in queue
                    items_to_process = self.workflow_queue.copy()
                    self.workflow_queue.clear()
                
                for item in items_to_process:
                    self._process_workflow_item(item)
                
                # Update statistics
                self.stats['last_run'] = datetime.utcnow()
                
                # Sleep before next processing cycle
                time.sleep(60)  # Process every minute
                
            except Exception as e:
                self.logger.error(f"Workflow processing error: {e}")
                time.sleep(60)
    
    def _handle_new_rss_item(self, item: Dict):
        """Handle new RSS item discovery"""
        try:
            # Extract bill information from RSS item
            bill_info = self._extract_bill_info(item)
            if not bill_info:
                return

            bill_key = (
                f"{bill_info['congress']}-{bill_info['bill_type']}-"
                f"{bill_info['bill_number']}"
            )
            with self.processing_lock:
                if bill_key in self._queued_bill_keys:
                    self.logger.info(
                        "Skipping duplicate queue entry for %s", bill_key
                    )
                    return

            discovered_at = datetime.utcnow()
            published = item.get("published") or item.get("discovered_at")
            if published:
                try:
                    # email.utils handles common RSS date formats
                    from email.utils import parsedate_to_datetime

                    discovered_at = parsedate_to_datetime(published).replace(
                        tzinfo=None
                    )
                except Exception:
                    try:
                        discovered_at = datetime.fromisoformat(
                            str(published).replace("Z", "+00:00")
                        ).replace(tzinfo=None)
                    except Exception:
                        discovered_at = datetime.utcnow()
            
            # Create workflow item
            workflow_item = WorkflowItem(
                bill_identifier=bill_info['identifier'],
                congress=bill_info['congress'],
                bill_type=bill_info['bill_type'],
                bill_number=bill_info['bill_number'],
                title=item['title'],
                source='rss',
                discovered_at=discovered_at,
                status=WorkflowStatus.PENDING
            )
            
            # Add to processing queue
            with self.processing_lock:
                self._queued_bill_keys.add(bill_key)
                self.workflow_queue.append(workflow_item)
            
            self.stats['bills_discovered'] += 1
            self.stats['rss_items_processed'] += 1
            self.logger.info(f"Added RSS bill to workflow: {workflow_item.bill_identifier}")
            
        except Exception as e:
            self.logger.error(f"Error handling RSS item: {e}")
            self.stats['errors'] += 1
    
    def _extract_bill_info(self, item: Dict) -> Optional[Dict]:
        """Extract bill information from RSS item (all eight Congress bill types)."""
        try:
            import re

            title = item.get('title') or ''
            link = item.get('link') or ''

            # Prefer congress.gov URL path: /bill/{congress}/{type-slug}/{number}
            slug_to_type = {v: k for k, v in Bill._CONGRESS_GOV_TYPE_SLUGS.items()}
            url_match = re.search(
                r'/bill/(\d+)(?:th|st|nd|rd)?-?congress/([a-z-]+)/(\d+)',
                link,
                re.IGNORECASE,
            )
            if url_match:
                congress = int(url_match.group(1))
                slug = url_match.group(2).lower()
                bill_number = int(url_match.group(3))
                bill_type = slug_to_type.get(slug)
                if bill_type:
                    return {
                        'identifier': f"{congress}-{bill_type.upper()}{bill_number}",
                        'congress': congress,
                        'bill_type': bill_type,
                        'bill_number': bill_number,
                    }

            # Title patterns — longest prefixes first to avoid HR matching H.Res
            title_patterns = [
                (r'\bH\.?\s*Con\.?\s*Res\.?\s*(\d+)', 'hconres'),
                (r'\bS\.?\s*Con\.?\s*Res\.?\s*(\d+)', 'sconres'),
                (r'\bH\.?\s*J\.?\s*Res\.?\s*(\d+)', 'hjres'),
                (r'\bS\.?\s*J\.?\s*Res\.?\s*(\d+)', 'sjres'),
                (r'\bH\.?\s*Res\.?\s*(\d+)', 'hres'),
                (r'\bS\.?\s*Res\.?\s*(\d+)', 'sres'),
                (r'\bH\.?\s*R\.?\s*(\d+)', 'hr'),
                (r'\bS\.?\s*(\d+)\b', 's'),
            ]
            bill_type = None
            bill_number = None
            for pattern, btype in title_patterns:
                match = re.search(pattern, title, re.IGNORECASE)
                if match:
                    bill_type = btype
                    bill_number = int(match.group(1))
                    break

            if not bill_type or bill_number is None:
                return None

            congress_match = re.search(r'/bill/(\d+)', link)
            congress = int(congress_match.group(1)) if congress_match else 119

            return {
                'identifier': f"{congress}-{bill_type.upper()}{bill_number}",
                'congress': congress,
                'bill_type': bill_type,
                'bill_number': bill_number,
            }
            
        except Exception as e:
            self.logger.error(f"Error extracting bill info: {e}")
            return None
    
    def _process_workflow_item(self, item: WorkflowItem):
        print(f"[DEBUG] Entered _process_workflow_item for: {item.bill_identifier}")
        self.logger.info(f"[DEBUG] Entered _process_workflow_item for: {item.bill_identifier}")
        bill_key = f"{item.congress}-{item.bill_type}-{item.bill_number}"
        try:
            self.logger.info(f"Processing workflow item: {item.bill_identifier} (source: {item.source})")
            item.status = WorkflowStatus.PROCESSING
            item.processing_started = datetime.utcnow()
            # Step 1: Shared sync — refresh activity for existing bills; ingest if missing
            bill = self._fetch_and_store_bill(item)
            if not bill:
                print(f"[DEBUG] _fetch_and_store_bill returned None for: {item.bill_identifier}")
                self.logger.info(f"[DEBUG] _fetch_and_store_bill returned None for: {item.bill_identifier}")
                item.status = WorkflowStatus.FAILED
                item.error_message = "Failed to fetch bill data"
                return
            print(f"[DEBUG] _fetch_and_store_bill returned bill for: {item.bill_identifier}")
            item.bill_id = bill.id
            self.stats['bills_processed'] += 1
            # Step 2: Perform AI analysis when needed (skip if already complete)
            analysis_success, analysis_metadata, analysis_ran = self._perform_ai_analysis(bill)
            item.analysis_ran = analysis_ran
            if analysis_success:
                item.analysis_completed = True
                if analysis_ran:
                    self.stats['bills_analyzed'] += 1
                # Store chunked analysis metadata
                if analysis_metadata:
                    item.text_length = analysis_metadata.get('text_length')
                    item.chunks_analyzed = analysis_metadata.get('chunks_analyzed')
                    item.analysis_method = analysis_metadata.get('analysis_method')
                    item.processing_time = analysis_metadata.get('processing_time')
                # Step 3: Notify only on real changes (new bill, new actions, or newly run analysis)
                should_notify = (
                    item.sync_created
                    or item.sync_actions_added > 0
                    or item.sync_status_changed
                    or analysis_ran
                )
                if should_notify:
                    try:
                        from services.notification_helper import trigger_bill_analysis_notification
                        trigger_bill_analysis_notification(bill.id)
                        item.alerts_generated = True
                        self.stats['alerts_generated'] += 1
                        self.logger.info(f"Triggered notifications for bill {bill.get_bill_identifier()}")
                    except Exception as e:
                        self.logger.warning(f"Could not trigger notifications for bill {bill.get_bill_identifier()}: {e}")
                        alerts_generated = self._generate_user_alerts(bill)
                        if alerts_generated:
                            item.alerts_generated = True
                            self.stats['alerts_generated'] += alerts_generated
                else:
                    self.logger.info(
                        "Skipping notifications for unchanged bill %s",
                        bill.get_bill_identifier(),
                    )
            # Mark as completed
            item.status = WorkflowStatus.COMPLETED
            item.processing_completed = datetime.utcnow()
            self.logger.info(f"Completed processing: {item.bill_identifier}")
            print(f"[DEBUG] Completed processing: {item.bill_identifier}")
        except Exception as e:
            print(f"[DEBUG] Exception in _process_workflow_item for {item.bill_identifier}: {e}")
            self.logger.error(f"Error processing workflow item {item.bill_identifier}: {e}")
            item.status = WorkflowStatus.FAILED
            item.error_message = str(e)
            self.stats['errors'] += 1
        finally:
            with self.processing_lock:
                self._queued_bill_keys.discard(bill_key)
    
    def _fetch_and_store_bill(self, item: WorkflowItem) -> Optional[Bill]:
        print(f"[DEBUG] Entered _fetch_and_store_bill for: {item.bill_identifier}")
        self.logger.info(f"[DEBUG] Entered _fetch_and_store_bill for: {item.bill_identifier}")
        try:
            from app import app

            with app.app_context():
                # RSS always refreshes activity; backfill uses content ingest when needed
                allow_content = item.source == 'backfill' and item.bill_id is None
                result = bill_sync.sync_bill(
                    item.congress,
                    item.bill_type,
                    item.bill_number,
                    reason=f"workflow:{item.source}",
                    refresh_activity_flag=True,
                    allow_content_ingest=allow_content,
                    congress_api=self.congress_api,
                )
                item.sync_created = result.created
                item.sync_actions_added = result.actions_added
                item.sync_status_changed = result.status_changed
                if result.bill:
                    print(
                        f"[DEBUG] sync_bill ok for {item.bill_identifier} "
                        f"(created={result.created}, actions+={result.actions_added})"
                    )
                    self.logger.info(
                        "sync_bill %s created=%s actions_added=%s status_changed=%s",
                        item.bill_identifier,
                        result.created,
                        result.actions_added,
                        result.status_changed,
                    )
                    return result.bill
                print(f"[DEBUG] sync_bill returned no bill for: {item.bill_identifier}")
                self.logger.warning(f"sync_bill returned no bill for: {item.bill_identifier}")
                return None
        except Exception as e:
            print(f"[DEBUG] Exception in _fetch_and_store_bill for {item.bill_identifier}: {e}")
            self.logger.error(f"Error fetching/storing bill {item.bill_identifier}: {e}")
            return None
    
    def _perform_ai_analysis(self, bill: Bill) -> tuple:
        """
        Perform AI analysis on the bill via EnhancedAIAnalyzer.
        Returns (success, metadata_dict_or_None, analysis_ran).
        analysis_ran is False when skipped because analysis already complete.
        """
        import time
        print(f"[DEBUG] Entered _perform_ai_analysis for bill: {bill.get_bill_identifier()}")
        self.logger.info(f"[DEBUG] Entered _perform_ai_analysis for bill: {bill.get_bill_identifier()}")
        lease_held = False
        try:
            from app import app

            with app.app_context():
                # Re-bind bill in this app context
                bill = Bill.query.get(bill.id) or bill
                active_analysis = bill.get_active_ai_analysis()
                if active_analysis:
                    data = (
                        active_analysis.get_analysis_data()
                        if hasattr(active_analysis, "get_analysis_data")
                        else None
                    )
                    # Resume Tier B partials; otherwise skip core but heal enrichments
                    needs_resume = bill_sync._tier_b_needs_resume_local(data)
                    if not needs_resume:
                        print(f"[DEBUG] Skipping: AI analysis already exists for {bill.get_bill_identifier()}")
                        self.logger.info(f"Skipping: AI analysis already exists for {bill.get_bill_identifier()}")
                        try:
                            from services.enrichment_queue import maybe_queue_enrichments

                            maybe_queue_enrichments(
                                bill,
                                data if isinstance(data, dict) else None,
                                source="rss",
                                analyzer=self.ai_analyzer,
                            )
                        except Exception as enrich_err:
                            self.logger.warning(
                                f"Failed to queue enrichments for "
                                f"{bill.get_bill_identifier()}: {enrich_err}"
                            )
                        return True, None, False
                # Check if workflow has been stopped due to rate limiting
                if not self.is_running:
                    print(f"[DEBUG] Skipping: Workflow stopped due to rate limiting for {bill.get_bill_identifier()}")
                    self.logger.info(f"Skipping: Workflow stopped due to rate limiting for {bill.get_bill_identifier()}")
                    return False, None, False

                # Cross-ingestor lease — skip Gemini if search/backfill already holds it
                if not bill_work_lease.try_acquire(
                    bill.id,
                    bill_work_lease.KIND_ANALYZE,
                    self._analysis_holder,
                ):
                    self.logger.info(
                        f"Skipping: analyze lease held for {bill.get_bill_identifier()}"
                    )
                    try:
                        from services.pipeline_activity_log import get_rss_activity_log

                        get_rss_activity_log().append(
                            "Analyze lease held — skipped",
                            level="info",
                            bill_identifier=bill.get_bill_identifier(),
                        )
                    except Exception:
                        pass
                    return False, {"skipped_reason": "lease_held"}, False
                lease_held = True

                # Check AI analyzer rate limit status with detailed quota info
                quota_info = self.ai_analyzer.get_quota_info()
                if quota_info['status']['is_at_limit']:
                    print(f"[DEBUG] Skipping: AI analyzer at rate limit for {bill.get_bill_identifier()}")
                    self.logger.info(f"Skipping: AI analyzer at rate limit for {bill.get_bill_identifier()}")
                    return False, None, False
                if quota_info['status']['is_approaching_limit']:
                    print(f"[DEBUG] Skipping: AI analyzer very close to rate limit for {bill.get_bill_identifier()}")
                    self.logger.info(f"Skipping: AI analyzer very close to rate limit for {bill.get_bill_identifier()}")
                    return False, None, False

                # Prefer persisted full text
                full_text = bill.get_full_text(fetch_if_missing=True, persist=True)
                if not full_text:
                    print(f"[DEBUG] No full text available for analysis: {bill.get_bill_identifier()} (skipping)")
                    self.logger.info(f"No full text available for analysis: {bill.get_bill_identifier()} (skipping)")
                    return False, None, False
                
                start_time = time.time()
                text_length = len(full_text)
                ident = bill.get_bill_identifier()
                model_name = getattr(self.ai_analyzer, "model_name", None)

                self.logger.info(
                    f"Starting AI analysis for {ident} "
                    f"(text length: {text_length:,} characters)"
                )
                try:
                    from services.pipeline_activity_log import get_rss_activity_log
                    from services.ops_alert_service import (
                        CONTINUATION_FINISHED,
                        CONTINUATION_QUEUED,
                        EMPTY_RESULT,
                        QUOTA_EXHAUSTED,
                        UNKNOWN,
                        notify_gemini_failure,
                    )

                    get_rss_activity_log().append(
                        f"Starting AI analysis ({text_length:,} chars)",
                        level="info",
                        bill_identifier=ident,
                    )
                    notify_gemini_failure(
                        CONTINUATION_QUEUED,
                        f"RSS analysis queued for {ident}",
                        severity="info",
                        bill_identifier=ident,
                        bill_id=bill.id,
                        provider_model=model_name,
                        source="rss",
                        extra={"event": "queued", "pipeline": "rss"},
                    )
                except Exception:
                    pass
                
                # Pass Bill object so analyzer persists AIAnalysis/Summary/categories/display_ready
                analysis = self.ai_analyzer.analyze_bill(
                    bill,
                    bill.title,
                    allow_budget_waits=True,
                )
                
                processing_time = time.time() - start_time
                
                if analysis:
                    print(f"[DEBUG] AI analysis completed and stored for {ident}")
                    self.logger.info(f"AI analysis completed and stored for {ident}")
                    
                    chunks_analyzed = analysis.get('chunks_analyzed', 0)
                    analysis_method = analysis.get('analysis_method', 'unknown')
                    is_partial = bool(analysis.get("is_partial"))
                    
                    self._update_analysis_statistics(
                        text_length=text_length,
                        chunks_analyzed=chunks_analyzed,
                        analysis_method=analysis_method,
                        processing_time=processing_time,
                        analysis_results=analysis
                    )
                    
                    self.logger.info(f"✅ AI analysis completed for: {ident}")
                    metadata = {
                        'text_length': text_length,
                        'chunks_analyzed': chunks_analyzed,
                        'analysis_method': analysis_method,
                        'processing_time': processing_time
                    }
                    try:
                        from services.pipeline_activity_log import get_rss_activity_log
                        from services.ops_alert_service import (
                            CONTINUATION_FINISHED,
                            notify_gemini_failure,
                        )

                        get_rss_activity_log().append(
                            f"Analysis complete ({analysis_method}"
                            f"{', partial' if is_partial else ''})",
                            level="warning" if is_partial else "info",
                            bill_identifier=ident,
                        )
                        notify_gemini_failure(
                            CONTINUATION_FINISHED,
                            f"RSS analysis finished for {ident}"
                            + (" (partial)" if is_partial else ""),
                            severity="warning" if is_partial else "info",
                            bill_identifier=ident,
                            bill_id=bill.id,
                            provider_model=model_name,
                            source="rss",
                            completion_percentage=analysis.get("completion_percentage"),
                            extra={
                                "event": "finished",
                                "pipeline": "rss",
                                "is_partial": is_partial,
                                "analysis_method": analysis_method,
                            },
                        )
                    except Exception:
                        pass
                    if not is_partial:
                        try:
                            from services.enrichment_queue import maybe_queue_enrichments

                            maybe_queue_enrichments(
                                bill,
                                analysis if isinstance(analysis, dict) else None,
                                source="rss",
                                analyzer=self.ai_analyzer,
                                is_partial=False,
                            )
                        except Exception as enrich_err:
                            self.logger.warning(
                                f"Failed to queue enrichments for {ident}: {enrich_err}"
                            )
                    return True, metadata, True
                else:
                    print(f"[DEBUG] AI analysis returned None for {ident}")
                    self.logger.warning(f"AI analysis returned None for {ident}")
                    try:
                        from services.pipeline_activity_log import get_rss_activity_log
                        from services.ops_alert_service import (
                            EMPTY_RESULT,
                            QUOTA_EXHAUSTED,
                            notify_gemini_failure,
                        )

                        get_rss_activity_log().append(
                            "Analysis returned empty",
                            level="error",
                            bill_identifier=ident,
                        )
                        quota_info = self.ai_analyzer.get_quota_info()
                        fc = (
                            QUOTA_EXHAUSTED
                            if quota_info["status"]["is_at_limit"]
                            else EMPTY_RESULT
                        )
                        notify_gemini_failure(
                            fc,
                            f"RSS analysis empty for {ident}",
                            severity="error",
                            bill_identifier=ident,
                            bill_id=bill.id,
                            provider_model=model_name,
                            source="rss",
                            extra={"event": "finished", "pipeline": "rss"},
                        )
                    except Exception:
                        pass
                    # Check if it's due to rate limiting
                    quota_info = self.ai_analyzer.get_quota_info()
                    if quota_info['status']['is_at_limit']:
                        self.logger.error("Rate limit detected after analysis failure. Stopping workflow.")
                        self.stats['rate_limit_hits'] += 1
                        self.stats['last_rate_limit_time'] = datetime.utcnow()
                        self.stats['workflow_stopped_due_to_rate_limit'] = True
                        self.is_running = False
                        return False, None, False
                    return False, None, False
        except Exception as e:
            print(f"[DEBUG] Exception in _perform_ai_analysis for {bill.get_bill_identifier()}: {e}")
            self.logger.error(f"Error performing AI analysis for {bill.get_bill_identifier()}: {e}")
            try:
                from services.pipeline_activity_log import get_rss_activity_log
                from services.ops_alert_service import UNKNOWN, notify_gemini_failure

                ident = bill.get_bill_identifier()
                get_rss_activity_log().append(
                    f"Analysis error: {type(e).__name__}",
                    level="error",
                    bill_identifier=ident,
                )
                notify_gemini_failure(
                    UNKNOWN,
                    f"RSS analysis error: {type(e).__name__}",
                    severity="error",
                    bill_identifier=ident,
                    bill_id=getattr(bill, "id", None),
                    provider_model=getattr(self.ai_analyzer, "model_name", None),
                    source="rss",
                    extra={"event": "finished", "pipeline": "rss", "error": type(e).__name__},
                )
            except Exception:
                pass
            return False, None, False
        finally:
            if lease_held:
                try:
                    from app import app
                    with app.app_context():
                        bill_work_lease.release(
                            getattr(bill, "id", None),
                            bill_work_lease.KIND_ANALYZE,
                            self._analysis_holder,
                        )
                except Exception as release_err:
                    self.logger.warning(f"Failed to release analyze lease: {release_err}")
    
    
    def _update_analysis_statistics(self, text_length: int, chunks_analyzed: int, 
                                  analysis_method: str, processing_time: float, analysis_results: Dict = None):
        """Update statistics with analysis performance data and hidden provision detection metrics"""
        try:
            # Update basic statistics
            self.stats['total_chunks_analyzed'] += chunks_analyzed
            self.stats['total_text_processed'] += text_length
            
            # Update analysis method counts
            if analysis_method in self.stats['analysis_methods']:
                self.stats['analysis_methods'][analysis_method] += 1
            else:
                self.stats['analysis_methods']['unknown'] += 1
            
            # Update processing time statistics
            times = self.stats['processing_times']
            times['total_analysis_time'] += processing_time
            
            # Update fastest/slowest times
            if processing_time < times['fastest_analysis']:
                times['fastest_analysis'] = processing_time
            if processing_time > times['slowest_analysis']:
                times['slowest_analysis'] = processing_time
            
            # Calculate average processing time
            total_analyses = self.stats['bills_analyzed']
            if total_analyses > 0:
                times['average_analysis_time'] = times['total_analysis_time'] / total_analyses
            
            # Update hidden provision detection statistics
            if analysis_results:
                self._update_hidden_detection_statistics(analysis_results)
            
        except Exception as e:
            self.logger.error(f"Error updating analysis statistics: {e}")
    
    def _update_hidden_detection_statistics(self, analysis_results: Dict):
        """Update statistics for hidden provision detection"""
        try:
            # Hidden provisions detection
            if 'hidden_provisions' in analysis_results:
                hidden_data = analysis_results['hidden_provisions']
                self.stats['hidden_provisions_detected'] += len(hidden_data.get('detected_provisions', []))
                self.stats['suspicious_chunks_found'] += hidden_data.get('total_suspicious_chunks', 0)
                self.stats['hidden_detection_methods']['ai_analysis'] += 1
                
                # Track risk levels
                overall_risk = hidden_data.get('overall_hidden_risk_score', 0.0)
                if overall_risk >= 0.7:
                    self.stats['high_risk_bills'] += 1
                elif overall_risk >= 0.4:
                    self.stats['medium_risk_bills'] += 1
                else:
                    self.stats['low_risk_bills'] += 1
            
            # Anomaly detection
            if 'anomalies' in analysis_results:
                anomalies_data = analysis_results['anomalies']
                self.stats['anomalies_detected'] += len(anomalies_data.get('detected_anomalies', []))
                self.stats['hidden_detection_methods']['anomaly_detection'] += 1
            
            # Cross-reference analysis
            if 'cross_references' in analysis_results:
                cross_ref_data = analysis_results['cross_references']
                self.stats['cross_references_analyzed'] += len(cross_ref_data.get('cross_references_found', []))
                self.stats['hidden_detection_methods']['cross_chunk'] += 1
            
            # Suspicious language detection
            if 'suspicious_language' in analysis_results:
                suspicious_data = analysis_results['suspicious_language']
                if suspicious_data.get('pattern_based_findings'):
                    self.stats['hidden_detection_methods']['pattern_based'] += 1
                if suspicious_data.get('ai_analysis'):
                    self.stats['hidden_detection_methods']['ai_analysis'] += 1
            
        except Exception as e:
            self.logger.error(f"Error updating hidden detection statistics: {e}")
    
    def _generate_user_alerts(self, bill: Bill) -> int:
        """Generate alerts for users based on their preferences"""
        try:
            alerts_created = 0
            
            # Get all users with alert preferences enabled
            users = session.query(User).filter_by(alert_enabled=True).all()
            
            for user in users:
                # Check if user should be alerted about this bill
                should_alert, alert_data = self._should_alert_user(user, bill)
                
                if should_alert:
                    # Create alert
                    alert = Alert(
                        user_id=user.id,
                        bill_id=bill.id,
                        alert_type=alert_data['type'],
                        title=alert_data['title'],
                        message=alert_data['message'],
                        alignment_score=alert_data.get('alignment_score'),
                        priority=alert_data.get('priority', 'medium')
                    )
                    
                    session.add(alert)
                    alerts_created += 1
            
            if alerts_created > 0:
                session.commit()
                self.logger.info(f"Created {alerts_created} alerts for bill {bill.get_bill_identifier()}")
            
            return alerts_created
            
        except Exception as e:
            self.logger.error(f"Error generating alerts for bill {bill.get_bill_identifier()}: {e}")
            session.rollback()
            return 0
    
    def _should_alert_user(self, user: User, bill: Bill) -> tuple[bool, Dict]:
        """Determine if a user should be alerted about a bill and create alert data"""
        try:
            # Get user's policy subscriptions
            user_subscriptions = session.query(UserPolicySubscription).filter_by(
                user_id=user.id,
                notification_enabled=True
            ).all()
            
            if not user_subscriptions:
                return False, {}
            
            # Get bill's policy categories
            bill_analysis = bill.get_ai_analysis()
            if not bill_analysis or 'policy_implications' not in bill_analysis:
                return False, {}
            
            policy_data = bill_analysis['policy_implications']
            bill_categories = [cat.get('area') for cat in policy_data.get('categories', [])]
            
            # Check for matches between user subscriptions and bill categories
            for subscription in user_subscriptions:
                policy_category = session.query(PolicyCategory).get(subscription.policy_category_id)
                if not policy_category:
                    continue
                
                if policy_category.name in bill_categories:
                    # Calculate alignment score
                    alignment_score = self._calculate_alignment_score(user, bill, subscription)
                    
                    # Create alert data
                    alert_data = {
                        'type': 'policy_match',
                        'title': f"New Bill Matches Your Interests: {bill.get_bill_identifier()}",
                        'message': f"'{bill.title[:100]}...' relates to {policy_category.name}",
                        'alignment_score': alignment_score,
                        'priority': 'high' if abs(alignment_score) > 70 else 'medium'
                    }
                    
                    return True, alert_data
            
            return False, {}
            
        except Exception as e:
            self.logger.error(f"Error checking if user should be alerted: {e}")
            return False, {}
    
    def _calculate_alignment_score(self, user: User, bill: Bill, subscription: UserPolicySubscription) -> float:
        """Calculate alignment score between user and bill"""
        try:
            # Simple scoring based on subscription interest level
            base_score = subscription.interest_level * 100
            
            # Add some randomness for now (in production, use more sophisticated scoring)
            import random
            variation = random.uniform(-20, 20)
            
            return max(-100, min(100, base_score + variation))
            
        except Exception as e:
            self.logger.error(f"Error calculating alignment score: {e}")
            return 0.0
    
    def stop_workflow(self):
        """Stop the workflow"""
        self.logger.info("Stopping Legislative Analysis Workflow")
        self.is_running = False
    
    def reset_rate_limit_state(self):
        """Reset rate limit state when restarting workflow"""
        self.logger.info("Resetting rate limit state")
        self.stats['workflow_stopped_due_to_rate_limit'] = False
        self.logger.info("✅ Rate limit state reset - workflow can be restarted")
    
    def reset_chunked_analysis_stats(self):
        """Reset chunked analysis statistics"""
        self.logger.info("Resetting chunked analysis statistics")
        
        # Reset chunked analysis specific stats
        self.stats['total_chunks_analyzed'] = 0
        self.stats['total_text_processed'] = 0
        self.stats['chunked_analysis_count'] = 0
        self.stats['truncated_analysis_count'] = 0
        self.stats['analysis_methods'] = {
            'chunked': 0,
            'truncated': 0,
            'unknown': 0
        }
        self.stats['processing_times'] = {
            'total_analysis_time': 0.0,
            'average_analysis_time': 0.0,
            'fastest_analysis': float('inf'),
            'slowest_analysis': 0.0
        }
        
        self.logger.info("✅ Chunked analysis statistics reset")
    
    def get_chunked_analysis_performance_summary(self) -> str:
        """Get a human-readable summary of chunked analysis performance"""
        stats = self.stats
        
        if stats['bills_analyzed'] == 0:
            return "No bills have been analyzed yet."
        
        total_chunks = stats['total_chunks_analyzed']
        total_text = stats['total_text_processed']
        total_time = stats['processing_times']['total_analysis_time']
        avg_chunks = total_chunks / stats['bills_analyzed']
        avg_text = total_text / stats['bills_analyzed']
        avg_time = total_time / stats['bills_analyzed']
        processing_speed = total_text / total_time if total_time > 0 else 0
        
        summary = f"""
🎯 Chunked Analysis Performance Summary

📊 Overview:
   • Bills analyzed: {stats['bills_analyzed']}
   • Total chunks processed: {total_chunks:,}
   • Total text processed: {total_text:,} characters
   • Total processing time: {total_time:.2f} seconds

⚡ Performance:
   • Average chunks per bill: {avg_chunks:.1f}
   • Average text length: {avg_text:,.0f} characters
   • Average processing time: {avg_time:.2f} seconds
   • Processing speed: {processing_speed:,.0f} characters/second

🏆 Records:
   • Fastest analysis: {stats['processing_times']['fastest_analysis']:.2f}s
   • Slowest analysis: {stats['processing_times']['slowest_analysis']:.2f}s

📈 Success Rates:
   • Analysis success rate: {stats.get('analysis_success_rate', 0):.1f}%
   • Error rate: {stats.get('error_rate', 0):.1f}%
"""
        
        return summary
    
    def get_workflow_status(self) -> Dict:
        """Get current workflow status and statistics"""
        # Calculate additional derived statistics
        stats = self.stats.copy()
        
        # Calculate average chunks per bill
        if stats['bills_analyzed'] > 0:
            stats['average_chunks_per_bill'] = stats['total_chunks_analyzed'] / stats['bills_analyzed']
            stats['average_text_length'] = stats['total_text_processed'] / stats['bills_analyzed']
        else:
            stats['average_chunks_per_bill'] = 0
            stats['average_text_length'] = 0
        
        # Format processing times
        if stats['processing_times']['fastest_analysis'] == float('inf'):
            stats['processing_times']['fastest_analysis'] = 0
        
        # Calculate success rates
        total_processed = stats['bills_processed']
        if total_processed > 0:
            stats['analysis_success_rate'] = (stats['bills_analyzed'] / total_processed) * 100
            stats['error_rate'] = (stats['errors'] / total_processed) * 100
        else:
            stats['analysis_success_rate'] = 0
            stats['error_rate'] = 0
        
        return {
            'is_running': self.is_running,
            'queue_size': len(self.workflow_queue),
            'statistics': stats,
            'last_run': self.stats['last_run'].isoformat() if self.stats['last_run'] else None,
            'rate_limiting': {
                'rate_limit_hits': stats['rate_limit_hits'],
                'last_rate_limit_time': stats['last_rate_limit_time'].isoformat() if stats['last_rate_limit_time'] else None,
                'workflow_stopped_due_to_rate_limit': stats['workflow_stopped_due_to_rate_limit'],
                'status': 'stopped_due_to_rate_limit' if stats['workflow_stopped_due_to_rate_limit'] else 'normal',
                'ai_analyzer_status': self.ai_analyzer.get_rate_limit_status() if hasattr(self, 'ai_analyzer') else None,
                'ai_quota_info': self.ai_analyzer.get_quota_info() if hasattr(self, 'ai_analyzer') else None
            },
            'chunked_analysis_summary': {
                'total_chunks_processed': stats['total_chunks_analyzed'],
                'total_text_processed': f"{stats['total_text_processed']:,} characters",
                'average_chunks_per_bill': f"{stats['average_chunks_per_bill']:.1f}",
                'analysis_methods': stats['analysis_methods'],
                'processing_performance': {
                    'average_time': f"{stats['processing_times']['average_analysis_time']:.2f}s",
                    'fastest_time': f"{stats['processing_times']['fastest_analysis']:.2f}s",
                    'slowest_time': f"{stats['processing_times']['slowest_analysis']:.2f}s",
                    'total_time': f"{stats['processing_times']['total_analysis_time']:.2f}s"
                }
            }
        }
    
    def get_chunked_analysis_stats(self) -> Dict:
        """Get detailed chunked analysis statistics"""
        stats = self.stats
        
        # Calculate performance metrics
        total_analyses = stats['bills_analyzed']
        if total_analyses > 0:
            avg_chunks = stats['total_chunks_analyzed'] / total_analyses
            avg_text_length = stats['total_text_processed'] / total_analyses
            avg_processing_time = stats['processing_times']['total_analysis_time'] / total_analyses
            avg_processing_speed = stats['total_text_processed'] / stats['processing_times']['total_analysis_time']
        else:
            avg_chunks = 0
            avg_text_length = 0
            avg_processing_time = 0
            avg_processing_speed = 0
        
        return {
            'overview': {
                'total_bills_analyzed': total_analyses,
                'total_chunks_processed': stats['total_chunks_analyzed'],
                'total_text_processed': f"{stats['total_text_processed']:,} characters",
                'total_processing_time': f"{stats['processing_times']['total_analysis_time']:.2f} seconds"
            },
            'performance': {
                'average_chunks_per_bill': f"{avg_chunks:.1f}",
                'average_text_length': f"{avg_text_length:,.0f} characters",
                'average_processing_time': f"{avg_processing_time:.2f} seconds",
                'average_processing_speed': f"{avg_processing_speed:,.0f} chars/sec",
                'fastest_analysis': f"{stats['processing_times']['fastest_analysis']:.2f} seconds",
                'slowest_analysis': f"{stats['processing_times']['slowest_analysis']:.2f} seconds"
            },
            'analysis_methods': stats['analysis_methods'],
            'success_rates': {
                'analysis_success_rate': f"{stats.get('analysis_success_rate', 0):.1f}%",
                'error_rate': f"{stats.get('error_rate', 0):.1f}%"
            }
        }
    
    def get_hidden_detection_stats(self) -> Dict:
        """Get detailed hidden provision detection statistics"""
        stats = self.stats
        
        # Calculate risk distribution percentages
        total_risk_bills = stats['high_risk_bills'] + stats['medium_risk_bills'] + stats['low_risk_bills']
        if total_risk_bills > 0:
            high_risk_pct = (stats['high_risk_bills'] / total_risk_bills) * 100
            medium_risk_pct = (stats['medium_risk_bills'] / total_risk_bills) * 100
            low_risk_pct = (stats['low_risk_bills'] / total_risk_bills) * 100
        else:
            high_risk_pct = 0
            medium_risk_pct = 0
            low_risk_pct = 0
        
        return {
            'overview': {
                'total_bills_analyzed': stats['bills_analyzed'],
                'hidden_provisions_detected': stats['hidden_provisions_detected'],
                'suspicious_chunks_found': stats['suspicious_chunks_found'],
                'anomalies_detected': stats['anomalies_detected'],
                'cross_references_analyzed': stats['cross_references_analyzed']
            },
            'risk_distribution': {
                'high_risk_bills': {
                    'count': stats['high_risk_bills'],
                    'percentage': f"{high_risk_pct:.1f}%"
                },
                'medium_risk_bills': {
                    'count': stats['medium_risk_bills'],
                    'percentage': f"{medium_risk_pct:.1f}%"
                },
                'low_risk_bills': {
                    'count': stats['low_risk_bills'],
                    'percentage': f"{low_risk_pct:.1f}%"
                }
            },
            'detection_methods': {
                'pattern_based_detection': stats['hidden_detection_methods']['pattern_based'],
                'ai_analysis_detection': stats['hidden_detection_methods']['ai_analysis'],
                'cross_chunk_analysis': stats['hidden_detection_methods']['cross_chunk'],
                'anomaly_detection': stats['hidden_detection_methods']['anomaly_detection']
            },
            'effectiveness': {
                'detection_rate': f"{(stats['hidden_provisions_detected'] / max(stats['bills_analyzed'], 1)) * 100:.1f}%",
                'suspicious_chunks_per_bill': f"{stats['suspicious_chunks_found'] / max(stats['bills_analyzed'], 1):.1f}",
                'anomalies_per_bill': f"{stats['anomalies_detected'] / max(stats['bills_analyzed'], 1):.1f}"
            }
        }
    
    def get_recent_workflow_items(self, limit: int = 10) -> List[Dict]:
        """Get recent workflow items for monitoring"""
        return [
            {
                'bill_identifier': item.bill_identifier,
                'source': item.source,
                'status': item.status.value,
                'discovered_at': item.discovered_at.isoformat(),
                'processing_started': item.processing_started.isoformat() if item.processing_started else None,
                'processing_completed': item.processing_completed.isoformat() if item.processing_completed else None,
                'analysis_completed': item.analysis_completed,
                'alerts_generated': item.alerts_generated,
                'error_message': item.error_message,
                # Enhanced chunked analysis metadata
                'chunked_analysis': {
                    'text_length': item.text_length,
                    'chunks_analyzed': item.chunks_analyzed,
                    'analysis_method': item.analysis_method,
                    'processing_time': item.processing_time
                } if item.analysis_completed else None
            }
            for item in self.workflow_queue[-limit:]
        ]
    
    def start_workflow_web(self):
        """Start workflow in a background thread for web interface"""
        if self.is_running:
            return {'status': 'already_running', 'message': 'RSS pipeline is already running'}
        
        try:
            # Start workflow in a separate thread so web request doesn't hang
            def workflow_thread():
                self.start_workflow(
                    check_interval=60,  # Check every minute for web interface
                    enable_rss=True,
                    enable_backfill=False  # Don't enable backfill from web to avoid heavy load
                )
            
            import threading
            self.workflow_thread = threading.Thread(target=workflow_thread, daemon=True)
            self.workflow_thread.start()
            
            self.logger.info("RSS pipeline started from web interface")
            try:
                from services.pipeline_activity_log import get_rss_activity_log

                get_rss_activity_log().append("RSS pipeline started", level="info")
            except Exception:
                pass
            return {'status': 'success', 'message': 'RSS pipeline started successfully'}
            
        except Exception as e:
            self.logger.error(f"Error starting workflow from web: {e}")
            return {'status': 'error', 'message': str(e)}
    
    def stop_workflow_web(self):
        """Stop workflow for web interface"""
        try:
            self.is_running = False
            self.logger.info("RSS pipeline stopped from web interface")
            try:
                from services.pipeline_activity_log import get_rss_activity_log

                get_rss_activity_log().append("RSS pipeline stop requested", level="warning")
            except Exception:
                pass
            return {'status': 'success', 'message': 'RSS pipeline stopped successfully'}
        except Exception as e:
            self.logger.error(f"Error stopping workflow from web: {e}")
            return {'status': 'error', 'message': str(e)}
    

def dry_run_sneakiness_mapping(categories, analysis):
    """Dry run the sneakiness mapping logic without writing to the database."""
    import re
    sneakiness_by_category = {}
    if analysis and 'hidden_provisions' in analysis:
        hidden_provisions = analysis['hidden_provisions'].get('detected_provisions', [])
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
    # Print results
    print("Sneakiness mapping (dry run):")
    for cat in categories:
        area = cat.get('area', '')
        score = sneakiness_by_category.get(area, 0.0)
        print(f"  - {area}: {score}")

# Lazy global — avoid constructing analyzer/RSS on import (breaks unit tests / SQLite locks)
_workflow_orchestrator = None


def _get_module_orchestrator():
    global _workflow_orchestrator
    if _workflow_orchestrator is None:
        _workflow_orchestrator = WorkflowOrchestrator()
    return _workflow_orchestrator


def start_workflow_service(enable_rss=True, enable_backfill=False):
    """Start the workflow service (no Flask app context required)"""
    _get_module_orchestrator().start_workflow(
        enable_rss=enable_rss,
        enable_backfill=enable_backfill
    )

def stop_workflow_service():
    """Stop the workflow service"""
    _get_module_orchestrator().stop_workflow()

def get_workflow_status():
    """Get workflow status"""
    return _get_module_orchestrator().get_workflow_status()

# Back-compat alias used by some scripts/docs
def __getattr__(name):
    if name == "workflow_orchestrator":
        return _get_module_orchestrator()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

if __name__ == "__main__":
    from db_models import Bill
    bill = session.query(Bill).order_by(Bill.id.desc()).first()
    if not bill:
        print("No bills found in the database.")
    else:
        analysis = bill.get_ai_analysis()
        categories = []
        if analysis and 'policy_implications' in analysis and 'categories' in analysis['policy_implications']:
            categories = analysis['policy_implications']['categories']
        else:
            print("No policy categories found in AI analysis.")
        if categories:
            print(f"Testing sneakiness mapping for bill: {bill.get_bill_identifier()} - {bill.title}")
            dry_run_sneakiness_mapping(categories, analysis)
        else:
            print("No categories to test.") 