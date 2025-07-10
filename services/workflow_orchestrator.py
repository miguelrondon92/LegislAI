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

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from db_models import Bill, BillAction, User, Alert, UserBillAlignment, PolicyCategory, UserPolicySubscription
from services.rss_monitoring import PersistentRSSMonitor
from services.bill_processor import BillProcessor
from services.enhanced_ai_analyzer import EnhancedAIAnalyzer
from services.notification_service import NotificationService
from services.congress_api import CongressAPI

# Set up SQLAlchemy engine and session (update path if needed)
engine = create_engine('sqlite:///instance/legislative_analysis.db')
Session = sessionmaker(bind=engine)
session = Session()

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
        self.bill_processor = BillProcessor()
        self.ai_analyzer = EnhancedAIAnalyzer()
        self.notification_service = NotificationService()
        self.congress_api = CongressAPI()
        
        # Workflow state
        self.workflow_queue: List[WorkflowItem] = []
        self.processing_lock = threading.Lock()
        self.is_running = False
        
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
                # Find bills without AI analysis (check both old and new tables)
                from db_models import AIAnalysis
                bills_without_analysis = session.query(Bill).outerjoin(AIAnalysis).filter(
                    ((Bill.ai_analysis.is_(None)) | (Bill.ai_analysis == '')) &
                    (AIAnalysis.id.is_(None))
                ).limit(10).all()  # Process 10 at a time
                
                for bill in bills_without_analysis:
                    if not self.is_running:
                        break
                    
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
            
            # Create workflow item
            workflow_item = WorkflowItem(
                bill_identifier=bill_info['identifier'],
                congress=bill_info['congress'],
                bill_type=bill_info['bill_type'],
                bill_number=bill_info['bill_number'],
                title=item['title'],
                source='rss',
                discovered_at=datetime.utcnow(),
                status=WorkflowStatus.PENDING
            )
            
            # Add to processing queue
            with self.processing_lock:
                self.workflow_queue.append(workflow_item)
            
            self.stats['bills_discovered'] += 1
            self.stats['rss_items_processed'] += 1
            self.logger.info(f"Added RSS bill to workflow: {workflow_item.bill_identifier}")
            
        except Exception as e:
            self.logger.error(f"Error handling RSS item: {e}")
            self.stats['errors'] += 1
    
    def _extract_bill_info(self, item: Dict) -> Optional[Dict]:
        """Extract bill information from RSS item"""
        try:
            title = item['title']
            link = item['link']
            
            # Try to extract bill info from title or link
            import re
            
            # Pattern for bill identifiers
            bill_pattern = r'([HS]\.?R?\.?\s*(\d+))'
            match = re.search(bill_pattern, title, re.IGNORECASE)
            
            if match:
                bill_identifier = match.group(1)
                bill_number = int(match.group(2))
                
                # Determine bill type and congress
                if 'H.R.' in bill_identifier or 'HR' in bill_identifier:
                    bill_type = 'hr'
                elif 'S.' in bill_identifier or 'S' in bill_identifier:
                    bill_type = 's'
                else:
                    return None
                
                # Extract congress from link or use current
                congress_match = re.search(r'/bill/(\d+)/', link)
                congress = int(congress_match.group(1)) if congress_match else 119  # Default to current
                
                return {
                    'identifier': bill_identifier,
                    'congress': congress,
                    'bill_type': bill_type,
                    'bill_number': bill_number
                }
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error extracting bill info: {e}")
            return None
    
    def _process_workflow_item(self, item: WorkflowItem):
        print(f"[DEBUG] Entered _process_workflow_item for: {item.bill_identifier}")
        self.logger.info(f"[DEBUG] Entered _process_workflow_item for: {item.bill_identifier}")
        try:
            self.logger.info(f"Processing workflow item: {item.bill_identifier} (source: {item.source})")
            item.status = WorkflowStatus.PROCESSING
            item.processing_started = datetime.utcnow()
            # Step 1: Fetch and store bill data (if not already in database)
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
            # Step 2: Perform AI analysis and store in database
            analysis_success, analysis_metadata = self._perform_ai_analysis(bill)
            if analysis_success:
                item.analysis_completed = True
                self.stats['bills_analyzed'] += 1
                # Store chunked analysis metadata
                if analysis_metadata:
                    item.text_length = analysis_metadata.get('text_length')
                    item.chunks_analyzed = analysis_metadata.get('chunks_analyzed')
                    item.analysis_method = analysis_metadata.get('analysis_method')
                    item.processing_time = analysis_metadata.get('processing_time')
                # Step 3: Generate user alerts based on preferences
                alerts_generated = self._generate_user_alerts(bill)
                if alerts_generated:
                    item.alerts_generated = True
                    self.stats['alerts_generated'] += alerts_generated
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
    
    def _fetch_and_store_bill(self, item: WorkflowItem) -> Optional[Bill]:
        print(f"[DEBUG] Entered _fetch_and_store_bill for: {item.bill_identifier}")
        self.logger.info(f"[DEBUG] Entered _fetch_and_store_bill for: {item.bill_identifier}")
        try:
            # If bill_id is already set (backfill case), return existing bill
            if item.bill_id:
                bill = session.query(Bill).get(item.bill_id)
                if bill:
                    print(f"[DEBUG] Using existing bill: {item.bill_identifier}")
                    self.logger.info(f"[DEBUG] Using existing bill: {item.bill_identifier}")
                    return bill
            # Check if bill already exists
            existing_bill = session.query(Bill).filter_by(
                congress=item.congress,
                bill_type=item.bill_type,
                bill_number=item.bill_number
            ).first()
            if existing_bill:
                print(f"[DEBUG] Bill already exists: {item.bill_identifier}")
                self.logger.info(f"[DEBUG] Bill already exists: {item.bill_identifier}")
                return existing_bill
            # Fetch bill data from Congress API
            bill_data = self.congress_api.get_bill_details(
                item.congress, 
                item.bill_type, 
                item.bill_number
            )
            if not bill_data:
                print(f"[DEBUG] Could not fetch bill data: {item.bill_identifier}")
                self.logger.warning(f"[DEBUG] Could not fetch bill data: {item.bill_identifier}")
                return None
            # Process and store bill
            bill = self.bill_processor.process_bill_data(bill_data)
            if bill:
                print(f"[DEBUG] Stored new bill: {item.bill_identifier}")
                self.logger.info(f"[DEBUG] Stored new bill: {item.bill_identifier}")
                return bill
            else:
                print(f"[DEBUG] Failed to process bill: {item.bill_identifier}")
                self.logger.error(f"[DEBUG] Failed to process bill: {item.bill_identifier}")
                return None
        except Exception as e:
            print(f"[DEBUG] Exception in _fetch_and_store_bill for {item.bill_identifier}: {e}")
            self.logger.error(f"Error fetching/storing bill {item.bill_identifier}: {e}")
            return None
    
    def _perform_ai_analysis(self, bill: Bill) -> tuple[bool, Optional[Dict]]:
        """Perform AI analysis on the bill and store in database using chunked analysis"""
        import time
        print(f"[DEBUG] Entered _perform_ai_analysis for bill: {bill.get_bill_identifier()}")
        self.logger.info(f"[DEBUG] Entered _perform_ai_analysis for bill: {bill.get_bill_identifier()}")
        try:
            # Check if analysis already exists (use new table structure)
            if bill.get_active_ai_analysis() or bill.get_ai_analysis():
                print(f"[DEBUG] Skipping: AI analysis already exists for {bill.get_bill_identifier()}")
                self.logger.info(f"[DEBUG] Skipping: AI analysis already exists for {bill.get_bill_identifier()}")
                return True, None
            # Check if workflow has been stopped due to rate limiting
            if not self.is_running:
                print(f"[DEBUG] Skipping: Workflow stopped due to rate limiting for {bill.get_bill_identifier()}")
                self.logger.info(f"[DEBUG] Skipping: Workflow stopped due to rate limiting for {bill.get_bill_identifier()}")
                return False, None
            # Check AI analyzer rate limit status with detailed quota info
            quota_info = self.ai_analyzer.get_quota_info()
            if quota_info['status']['is_at_limit']:
                print(f"[DEBUG] Skipping: AI analyzer at rate limit for {bill.get_bill_identifier()}")
                self.logger.info(f"[DEBUG] Skipping: AI analyzer at rate limit for {bill.get_bill_identifier()}")
                return False, None
            if quota_info['status']['is_approaching_limit']:
                print(f"[DEBUG] Skipping: AI analyzer very close to rate limit for {bill.get_bill_identifier()}")
                self.logger.info(f"[DEBUG] Skipping: AI analyzer very close to rate limit for {bill.get_bill_identifier()}")
                return False, None
            # Warn if approaching rate limit
            if quota_info['current_usage']['percentage_used'] > 80:
                print(f"[DEBUG] Approaching AI rate limit for {bill.get_bill_identifier()}")
                self.logger.info(f"[DEBUG] Approaching AI rate limit for {bill.get_bill_identifier()}")
            # Log quota status for debugging
            print(f"[DEBUG] AI Quota: {quota_info['current_usage']['requests_this_minute']}/{quota_info['current_usage']['max_requests_per_minute']} used, {quota_info['current_usage']['safe_remaining_requests']} safe remaining")
            self.logger.info(f"[DEBUG] AI Quota: {quota_info['current_usage']['requests_this_minute']}/{quota_info['current_usage']['max_requests_per_minute']} used, {quota_info['current_usage']['safe_remaining_requests']} safe remaining")
            # Fetch full text from Congress API (not stored in database)
            print(f"[DEBUG] Fetching full text for analysis: {bill.get_bill_identifier()}")
            self.logger.info(f"[DEBUG] Fetching full text for analysis: {bill.get_bill_identifier()}")
            full_text = self.congress_api.get_bill_text(bill.congress, bill.bill_type, bill.bill_number)
            if not full_text:
                print(f"[DEBUG] No full text available for analysis: {bill.get_bill_identifier()} (skipping)")
                self.logger.info(f"[DEBUG] No full text available for analysis: {bill.get_bill_identifier()} (skipping)")
                return False, None
            
            # Track processing time
            start_time = time.time()
            text_length = len(full_text)
            
            self.logger.info(f"Starting chunked AI analysis for {bill.get_bill_identifier()} "
                           f"(text length: {text_length:,} characters)")
            
            # Perform chunked analysis
            analysis = self.ai_analyzer.analyze_bill(full_text, bill.title)
            
            # Calculate processing time
            processing_time = time.time() - start_time
            
            if analysis:
                # Analysis is now stored by the AI analyzer using new table structure
                # bill.set_ai_analysis(analysis)  # Legacy method - now handled by analyzer
                
                # Store policy categories if available
                if 'policy_implications' in analysis:
                    policy_data = analysis['policy_implications']
                    if 'categories' in policy_data:
                        self._store_policy_categories(bill, policy_data['categories'], analysis)
                
                # Extract analysis metadata
                chunks_analyzed = analysis.get('chunks_analyzed', 0)
                analysis_method = analysis.get('analysis_method', 'unknown')
                
                # Update statistics
                self._update_analysis_statistics(
                    text_length=text_length,
                    chunks_analyzed=chunks_analyzed,
                    analysis_method=analysis_method,
                    processing_time=processing_time,
                    analysis_results=analysis
                )
                
                # Log comprehensive analysis information
                self.logger.info(f"✅ Chunked AI analysis completed for: {bill.get_bill_identifier()}")
                self.logger.info(f"  📊 Method: {analysis_method}")
                self.logger.info(f"  🔧 Chunks analyzed: {chunks_analyzed}")
                self.logger.info(f"  📝 Text processed: {text_length:,} characters")
                self.logger.info(f"  ⏱️ Processing time: {processing_time:.2f} seconds")
                self.logger.info(f"  🚀 Processing speed: {text_length/processing_time:,.0f} chars/sec")
                
                # Log analysis components
                if 'summary' in analysis:
                    self.logger.info(f"  📝 Summary generated")
                if 'policy_implications' in analysis:
                    policy_data = analysis['policy_implications']
                    primary_area = policy_data.get('primary_policy_area', 'Unknown')
                    self.logger.info(f"  🎯 Primary policy area: {primary_area}")
                if 'stakeholders' in analysis:
                    stakeholders = analysis['stakeholders']
                    if isinstance(stakeholders, dict):
                        winners = len(stakeholders.get('winners', []))
                        losers = len(stakeholders.get('losers', []))
                        self.logger.info(f"  👥 Stakeholders: {winners} winners, {losers} losers")
                
                # Log hidden provision detection results
                if 'hidden_provisions' in analysis:
                    hidden_data = analysis['hidden_provisions']
                    suspicious_count = hidden_data.get('total_suspicious_chunks', 0)
                    risk_score = hidden_data.get('overall_hidden_risk_score', 0.0)
                    self.logger.info(f"  🔍 Hidden provisions: {suspicious_count} suspicious chunks, risk score: {risk_score:.2f}")
                
                if 'anomalies' in analysis:
                    anomalies_data = analysis['anomalies']
                    anomaly_count = len(anomalies_data.get('detected_anomalies', []))
                    self.logger.info(f"  ⚠️ Anomalies detected: {anomaly_count}")
                
                if 'suspicious_language' in analysis:
                    suspicious_data = analysis['suspicious_language']
                    pattern_findings = len(suspicious_data.get('pattern_based_findings', []))
                    self.logger.info(f"  🚨 Suspicious language: {pattern_findings} pattern matches")
                
                # Log overall risk score
                overall_risk = analysis.get('overall_risk_score', 0.0)
                if overall_risk > 0.5:
                    self.logger.warning(f"  ⚠️ HIGH RISK BILL - Overall risk score: {overall_risk:.2f}")
                elif overall_risk > 0.3:
                    self.logger.info(f"  ⚠️ MEDIUM RISK BILL - Overall risk score: {overall_risk:.2f}")
                else:
                    self.logger.info(f"  ✅ LOW RISK BILL - Overall risk score: {overall_risk:.2f}")
                
                # Prepare metadata for return
                analysis_metadata = {
                    'text_length': text_length,
                    'chunks_analyzed': chunks_analyzed,
                    'analysis_method': analysis_method,
                    'processing_time': processing_time
                }
                
                session.commit()
                return True, analysis_metadata
            else:
                # Check if this was due to rate limiting
                self.logger.warning(f"⚠️ AI analysis failed for: {bill.get_bill_identifier()} - likely due to rate limiting")
                
                # Track rate limiting for workflow management
                self.stats['rate_limit_hits'] += 1
                self.stats['last_rate_limit_time'] = datetime.utcnow()
                
                # Stop the workflow due to rate limiting
                self.logger.error(f"🚫 RATE LIMIT EXCEEDED - Stopping workflow to prevent API abuse")
                self.logger.error(f"   📊 Rate limit hits: {self.stats['rate_limit_hits']}")
                self.logger.error(f"   ⏰ Last rate limit: {self.stats['last_rate_limit_time'].strftime('%Y-%m-%d %H:%M:%S')}")
                self.logger.error(f"   💡 Workflow will need to be manually restarted when API quota resets")
                self.logger.error(f"   📋 Remaining bills will be processed in next workflow run")
                
                # Mark workflow as stopped due to rate limit
                self.stats['workflow_stopped_due_to_rate_limit'] = True
                
                # Stop the workflow
                self.stop_workflow()
                
                return False, None
                
        except Exception as e:
            self.logger.error(f"❌ Error performing AI analysis for {bill.get_bill_identifier()}: {e}")
            self.stats['errors'] += 1
            return False, None
    
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
    
    def _store_policy_categories(self, bill: Bill, categories: List[Dict], analysis: Dict = None):
        """Store policy category mappings for the bill, including sneakiness score per category"""
        try:
            from db_models import BillCategoryMapping, PolicyCategory
            import re
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
                    policy_category = session.query(PolicyCategory).filter_by(name=area).first()
                    if not policy_category:
                        policy_category = PolicyCategory(
                            name=area,
                            display_name=area.title(),
                            description=f"Policy area: {area}",
                            color='#007bff',
                            icon='policy',
                            is_active=True
                        )
                        session.add(policy_category)
                        session.flush()
                        self.logger.info(f"Created new policy category: {area}")
                    mapping = session.query(BillCategoryMapping).filter_by(
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
                    if not mapping:
                        mapping = BillCategoryMapping(
                            bill_id=bill.id,
                            policy_category_id=policy_category.id,
                            relevance_score=score,
                            category_specific_analysis=json.dumps(category_data),
                            sneakiness_score=sneakiness_score
                        )
                        session.add(mapping)
                        categories_stored += 1
                        self.logger.info(f"Created category mapping: {bill.get_bill_identifier()} -> {area} (score: {score}, sneakiness: {sneakiness_score})")
                    else:
                        mapping.category_specific_analysis = json.dumps(category_data)
                        mapping.last_updated = datetime.utcnow()
                        mapping.sneakiness_score = sneakiness_score
                        self.logger.info(f"Updated existing category mapping: {bill.get_bill_identifier()} -> {area} (sneakiness: {sneakiness_score})")
                except Exception as category_error:
                    self.logger.error(f"Error processing category '{area}': {category_error}")
                    continue
            if categories_stored > 0:
                session.commit()
                self.logger.info(f"Successfully stored {categories_stored} policy category mappings for {bill.get_bill_identifier()}")
            else:
                self.logger.warning(f"No policy category mappings were stored for {bill.get_bill_identifier()}")
        except Exception as e:
            self.logger.error(f"Error storing policy categories for {bill.get_bill_identifier()}: {e}")
            session.rollback()
    
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

# Global workflow orchestrator instance
workflow_orchestrator = WorkflowOrchestrator()

def start_workflow_service(enable_rss=True, enable_backfill=False):
    """Start the workflow service (no Flask app context required)"""
    workflow_orchestrator.start_workflow(
        enable_rss=enable_rss,
        enable_backfill=enable_backfill
    )

def stop_workflow_service():
    """Stop the workflow service"""
    workflow_orchestrator.stop_workflow()

def get_workflow_status():
    """Get workflow status"""
    return workflow_orchestrator.get_workflow_status()

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