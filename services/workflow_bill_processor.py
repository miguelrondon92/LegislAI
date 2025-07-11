"""
Workflow Bill Processor

A version of BillProcessor that doesn't depend on app.py, designed specifically
for use in the workflow orchestrator and admin microservice.
"""

import logging
import json
import os
from datetime import datetime
from services.database_session import get_db_session
from services.enhanced_ai_analyzer import EnhancedAIAnalyzer
from services.congress_api import CongressAPI
from utils.text_processing import clean_bill_text, extract_sections

# Import models directly (not from app)
from db_models import Bill, BillAction, AIAnalysis, Summary

class WorkflowBillProcessor:
    """
    Bill processor for workflow operations.
    Uses independent database session to avoid circular imports.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.congress_api = CongressAPI()
        self.ai_analyzer = EnhancedAIAnalyzer()
    
    def process_bill_data(self, bill_data):
        """
        Process bill data from Congress API and store in database.
        
        Args:
            bill_data: Dictionary containing bill data from Congress API
            
        Returns:
            Bill object if successful, None otherwise
        """
        try:
            with get_db_session() as session:
                # Extract bill information
                congress = bill_data.get('congress')
                bill_type = bill_data.get('type', '').lower()
                bill_number = bill_data.get('number')
                
                if not all([congress, bill_type, bill_number]):
                    self.logger.error(f"Missing required bill data: {bill_data}")
                    return None
                
                # Check if bill already exists
                existing_bill = session.query(Bill).filter_by(
                    congress=congress,
                    bill_type=bill_type,
                    bill_number=bill_number
                ).first()
                
                if existing_bill:
                    self.logger.info(f"Bill already exists: {existing_bill.get_bill_identifier()}")
                    return existing_bill
                
                # Create new bill
                bill = Bill(
                    congress=congress,
                    bill_type=bill_type,
                    bill_number=bill_number,
                    title=bill_data.get('title', ''),
                    summary=bill_data.get('summary', ''),
                    sponsor_name=self._extract_sponsor_name(bill_data),
                    sponsor_party=self._extract_sponsor_party(bill_data),
                    sponsor_state=self._extract_sponsor_state(bill_data),
                    introduced_date=self._parse_date(bill_data.get('introducedDate')),
                    last_action_date=self._parse_date(bill_data.get('latestAction', {}).get('actionDate')),
                    last_action_text=bill_data.get('latestAction', {}).get('text', ''),
                    bill_text_url=self._extract_text_url(bill_data),
                    active=True,
                    created_at=datetime.utcnow(),
                    last_updated=datetime.utcnow()
                )
                
                session.add(bill)
                session.flush()  # Get the bill ID
                
                # Process actions if available
                if 'actions' in bill_data:
                    self._process_bill_actions(session, bill, bill_data['actions'])
                
                self.logger.info(f"Successfully processed bill: {bill.get_bill_identifier()}")
                return bill
                
        except Exception as e:
            self.logger.error(f"Error processing bill data: {e}")
            return None
    
    def _extract_sponsor_name(self, bill_data):
        """Extract sponsor name from bill data"""
        sponsors = bill_data.get('sponsors', [])
        if sponsors and len(sponsors) > 0:
            sponsor = sponsors[0]
            first_name = sponsor.get('firstName', '')
            last_name = sponsor.get('lastName', '')
            return f"{first_name} {last_name}".strip()
        return ''
    
    def _extract_sponsor_party(self, bill_data):
        """Extract sponsor party from bill data"""
        sponsors = bill_data.get('sponsors', [])
        if sponsors and len(sponsors) > 0:
            return sponsors[0].get('party', '')
        return ''
    
    def _extract_sponsor_state(self, bill_data):
        """Extract sponsor state from bill data"""
        sponsors = bill_data.get('sponsors', [])
        if sponsors and len(sponsors) > 0:
            return sponsors[0].get('state', '')
        return ''
    
    def _parse_date(self, date_str):
        """Parse date string to datetime object"""
        if not date_str:
            return None
        try:
            return datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            return None
    
    def _extract_text_url(self, bill_data):
        """Extract bill text URL from bill data"""
        text_versions = bill_data.get('textVersions', [])
        if text_versions and len(text_versions) > 0:
            formats = text_versions[0].get('formats', [])
            for fmt in formats:
                if fmt.get('type') == 'Formatted Text':
                    return fmt.get('url', '')
        return ''
    
    def _process_bill_actions(self, session, bill, actions_data):
        """Process and store bill actions"""
        try:
            for action_data in actions_data:
                action_date = self._parse_date(action_data.get('actionDate'))
                
                action = BillAction(
                    bill_id=bill.id,
                    action_date=action_date or datetime.utcnow(),
                    action_type=action_data.get('type', 'Unknown'),
                    action_text=action_data.get('text', ''),
                    action_description=action_data.get('description', ''),
                    source_system=action_data.get('sourceSystem', {}).get('code', ''),
                    source_system_name=action_data.get('sourceSystem', {}).get('name', '')
                )
                
                session.add(action)
            
            self.logger.info(f"Processed {len(actions_data)} actions for bill {bill.get_bill_identifier()}")
            
        except Exception as e:
            self.logger.error(f"Error processing bill actions: {e}")
    
    def get_bill_by_identifier(self, congress, bill_type, bill_number):
        """
        Get a bill by its identifier.
        
        Args:
            congress: Congress number
            bill_type: Bill type (e.g., 'hr', 's')
            bill_number: Bill number
            
        Returns:
            Bill object if found, None otherwise
        """
        try:
            with get_db_session() as session:
                return session.query(Bill).filter_by(
                    congress=congress,
                    bill_type=bill_type.lower(),
                    bill_number=bill_number
                ).first()
        except Exception as e:
            self.logger.error(f"Error getting bill by identifier: {e}")
            return None
    
    def get_bills_without_analysis(self, limit=10):
        """
        Get bills that don't have AI analysis yet.
        
        Args:
            limit: Maximum number of bills to return
            
        Returns:
            List of Bill objects
        """
        try:
            with get_db_session() as session:
                # Find bills without analysis in the AIAnalysis table
                bills_without_analysis = session.query(Bill).filter(
                    ~Bill.id.in_(
                        session.query(AIAnalysis.bill_id).filter(AIAnalysis.active == True)
                    )
                ).limit(limit).all()
                
                # If no bills without new analysis, check old analysis field
                if not bills_without_analysis:
                    bills_without_analysis = session.query(Bill).filter(
                        Bill.ai_analysis.is_(None)
                    ).limit(limit).all()
                
                return bills_without_analysis
        except Exception as e:
            self.logger.error(f"Error getting bills without analysis: {e}")
            return []