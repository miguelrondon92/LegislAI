"""
Workflow Orchestrator for Legislative Analysis Platform

Coordinates the complete workflow with two main goals:
1. Store AI analysis in the database
2. Push alerts to users based on their preferences

Supports both RSS monitoring and backfilling from previous bills.
"""

import logging
import time
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set
from dataclasses import dataclass
from enum import Enum
import json

from app import app, db
from models import Bill, BillAction, User, Alert, UserBillAlignment, PolicyCategory, UserPolicySubscription
from services.rss_monitoring import PersistentRSSMonitor
from services.bill_processor import BillProcessor
from services.ai_analyzer import AIAnalyzer
from services.notification_service import NotificationService
from services.congress_api import CongressAPI

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
        self.ai_analyzer = AIAnalyzer()
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
            'backfill_items_processed': 0
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
                # Find bills without AI analysis
                bills_without_analysis = Bill.query.filter(
                    (Bill.ai_analysis.is_(None)) | (Bill.ai_analysis == '')
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
        """Process a single workflow item through the complete pipeline"""
        try:
            self.logger.info(f"Processing workflow item: {item.bill_identifier} (source: {item.source})")
            item.status = WorkflowStatus.PROCESSING
            item.processing_started = datetime.utcnow()
            
            # Step 1: Fetch and store bill data (if not already in database)
            bill = self._fetch_and_store_bill(item)
            if not bill:
                item.status = WorkflowStatus.FAILED
                item.error_message = "Failed to fetch bill data"
                return
            
            item.bill_id = bill.id
            self.stats['bills_processed'] += 1
            
            # Step 2: Perform AI analysis and store in database
            analysis_success = self._perform_ai_analysis(bill)
            if analysis_success:
                item.analysis_completed = True
                self.stats['bills_analyzed'] += 1
                
                # Step 3: Generate user alerts based on preferences
                alerts_generated = self._generate_user_alerts(bill)
                if alerts_generated:
                    item.alerts_generated = True
                    self.stats['alerts_generated'] += alerts_generated
            
            # Mark as completed
            item.status = WorkflowStatus.COMPLETED
            item.processing_completed = datetime.utcnow()
            
            self.logger.info(f"Completed processing: {item.bill_identifier}")
            
        except Exception as e:
            self.logger.error(f"Error processing workflow item {item.bill_identifier}: {e}")
            item.status = WorkflowStatus.FAILED
            item.error_message = str(e)
            self.stats['errors'] += 1
    
    def _fetch_and_store_bill(self, item: WorkflowItem) -> Optional[Bill]:
        """Fetch bill data from Congress API and store in database"""
        try:
            # If bill_id is already set (backfill case), return existing bill
            if item.bill_id:
                bill = Bill.query.get(item.bill_id)
                if bill:
                    self.logger.info(f"Using existing bill: {item.bill_identifier}")
                    return bill
            
            # Check if bill already exists
            existing_bill = Bill.query.filter_by(
                congress=item.congress,
                bill_type=item.bill_type,
                bill_number=item.bill_number
            ).first()
            
            if existing_bill:
                self.logger.info(f"Bill already exists: {item.bill_identifier}")
                return existing_bill
            
            # Fetch bill data from Congress API
            bill_data = self.congress_api.get_bill_details(
                item.congress, 
                item.bill_type, 
                item.bill_number
            )
            
            if not bill_data:
                self.logger.warning(f"Could not fetch bill data: {item.bill_identifier}")
                return None
            
            # Process and store bill
            bill = self.bill_processor.process_bill_data(bill_data)
            
            if bill:
                self.logger.info(f"Stored new bill: {item.bill_identifier}")
                return bill
            else:
                self.logger.error(f"Failed to process bill: {item.bill_identifier}")
                return None
                
        except Exception as e:
            self.logger.error(f"Error fetching/storing bill {item.bill_identifier}: {e}")
            return None
    
    def _perform_ai_analysis(self, bill: Bill) -> bool:
        """Perform AI analysis on the bill and store in database"""
        try:
            # Check if analysis already exists
            if bill.get_ai_analysis():
                self.logger.info(f"AI analysis already exists for: {bill.get_bill_identifier()}")
                return True
            
            # Get full text for analysis
            full_text = bill.get_full_text()
            if not full_text:
                self.logger.warning(f"No full text available for analysis: {bill.get_bill_identifier()}")
                return False
            
            # Perform analysis
            analysis = self.ai_analyzer.analyze_bill(full_text, bill.title)
            if analysis:
                # Store analysis in database
                bill.set_ai_analysis(analysis)
                
                # Store policy categories if available
                if 'policy_implications' in analysis:
                    policy_data = analysis['policy_implications']
                    if 'categories' in policy_data:
                        self._store_policy_categories(bill, policy_data['categories'])
                
                db.session.commit()
                self.logger.info(f"AI analysis completed and stored for: {bill.get_bill_identifier()}")
                return True
            else:
                self.logger.error(f"AI analysis failed for: {bill.get_bill_identifier()}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error performing AI analysis for {bill.get_bill_identifier()}: {e}")
            return False
    
    def _store_policy_categories(self, bill: Bill, categories: List[Dict]):
        """Store policy category mappings for the bill"""
        try:
            from models import BillCategoryMapping, PolicyCategory
            
            for category_data in categories:
                area = category_data.get('area')
                if not area:
                    continue
                
                # Find or create policy category
                policy_category = PolicyCategory.query.filter_by(name=area).first()
                if not policy_category:
                    # Create new policy category
                    policy_category = PolicyCategory(
                        name=area,
                        description=f"Policy area: {area}",
                        parent_id=None
                    )
                    db.session.add(policy_category)
                    db.session.flush()  # Get the ID
                
                # Create or update category mapping
                mapping = BillCategoryMapping.query.filter_by(
                    bill_id=bill.id,
                    policy_category_id=policy_category.id
                ).first()
                
                if not mapping:
                    mapping = BillCategoryMapping(
                        bill_id=bill.id,
                        policy_category_id=policy_category.id,
                        relevance_score=0.8,  # Default score
                        category_specific_analysis=json.dumps(category_data)
                    )
                    db.session.add(mapping)
                
        except Exception as e:
            self.logger.error(f"Error storing policy categories: {e}")
    
    def _generate_user_alerts(self, bill: Bill) -> int:
        """Generate alerts for users based on their preferences"""
        try:
            alerts_created = 0
            
            # Get all users with alert preferences enabled
            users = User.query.filter_by(alert_enabled=True).all()
            
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
                    
                    db.session.add(alert)
                    alerts_created += 1
            
            if alerts_created > 0:
                db.session.commit()
                self.logger.info(f"Created {alerts_created} alerts for bill {bill.get_bill_identifier()}")
            
            return alerts_created
            
        except Exception as e:
            self.logger.error(f"Error generating alerts for bill {bill.get_bill_identifier()}: {e}")
            db.session.rollback()
            return 0
    
    def _should_alert_user(self, user: User, bill: Bill) -> tuple[bool, Dict]:
        """Determine if a user should be alerted about a bill and create alert data"""
        try:
            # Get user's policy subscriptions
            user_subscriptions = UserPolicySubscription.query.filter_by(
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
                policy_category = PolicyCategory.query.get(subscription.policy_category_id)
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
    
    def get_workflow_status(self) -> Dict:
        """Get current workflow status and statistics"""
        return {
            'is_running': self.is_running,
            'queue_size': len(self.workflow_queue),
            'statistics': self.stats.copy(),
            'last_run': self.stats['last_run'].isoformat() if self.stats['last_run'] else None
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
                'error_message': item.error_message
            }
            for item in self.workflow_queue[-limit:]
        ]

# Global workflow orchestrator instance
workflow_orchestrator = WorkflowOrchestrator()

def start_workflow_service(enable_rss=True, enable_backfill=False):
    """Start the workflow service"""
    with app.app_context():
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