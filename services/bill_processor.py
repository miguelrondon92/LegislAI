import logging
import json
import os
from datetime import datetime
from app import db
from services.enhanced_ai_analyzer import EnhancedAIAnalyzer
from services.congress_api import get_shared_congress_api
from utils.text_processing import clean_bill_text, extract_sections

class BillProcessor:
    """Service for processing bill data and generating user alerts"""
    
    def __init__(self, congress_api=None, ai_analyzer=None):
        self.ai_analyzer = ai_analyzer or EnhancedAIAnalyzer()
        self.congress_api = congress_api or get_shared_congress_api()
        self.seen_items_file = "seen_items.json"
    
    def read_seen_items(self):
        """Read bill items from seen_items.json"""
        try:
            if not os.path.exists(self.seen_items_file):
                logging.warning(f"Seen items file {self.seen_items_file} not found")
                return []
            
            with open(self.seen_items_file, 'r') as f:
                data = json.load(f)
                return data.get('seen_items', [])
                
        except Exception as e:
            logging.error(f"Error reading seen items: {str(e)}")
            return []
    
    def process_seen_items(self):
        """Process all bill items from seen_items.json"""
        try:
            seen_items = self.read_seen_items()
            if not seen_items:
                logging.info("No items found in seen_items.json")
                return []
            
            processed_bills = []
            logging.info(f"Processing {len(seen_items)} items from seen_items.json")
            
            for item in seen_items:
                try:
                    # Parse bill identifier (e.g., "H.Res.516")
                    bill_data = self.congress_api.get_bill_by_number(item)
                    if bill_data:
                        bill = self.process_bill_data(bill_data)
                        if bill:
                            processed_bills.append(bill)
                            logging.info(f"Successfully processed {item}")
                        else:
                            logging.warning(f"Failed to process bill data for {item}")
                    else:
                        logging.warning(f"Could not fetch bill data for {item}")
                        
                except Exception as e:
                    logging.error(f"Error processing item {item}: {str(e)}")
                    continue
            
            logging.info(f"Successfully processed {len(processed_bills)} out of {len(seen_items)} items")
            return processed_bills
            
        except Exception as e:
            logging.error(f"Error processing seen items: {str(e)}")
            return []
    
    def update_seen_items(self, new_items):
        """Update seen_items.json with new items"""
        try:
            current_items = self.read_seen_items()
            updated_items = list(set(current_items + new_items))  # Remove duplicates
            
            data = {
                "seen_items": updated_items,
                "last_updated": datetime.utcnow().isoformat()
            }
            
            with open(self.seen_items_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            logging.info(f"Updated seen_items.json with {len(new_items)} new items")
            
        except Exception as e:
            logging.error(f"Error updating seen items: {str(e)}")
    
    def add_to_seen_items(self, bill_identifier):
        """Add a bill identifier to seen_items.json"""
        try:
            current_items = self.read_seen_items()
            if bill_identifier not in current_items:
                self.update_seen_items([bill_identifier])
                logging.info(f"Added {bill_identifier} to seen_items.json")
            else:
                logging.info(f"{bill_identifier} already in seen_items.json")
                
        except Exception as e:
            logging.error(f"Error adding to seen items: {str(e)}")
    
    def process_bill_data(self, bill_data):
        """
        Process raw bill data from Congress API and save to database.
        Persists full text when present. Does NOT run Gemini analysis — callers
        must queue analysis asynchronously after ingest.
        Returns the processed Bill object
        """
        try:
            import hashlib
            # Extract basic bill information
            congress = bill_data.get('congress')
            bill_type = bill_data.get('type', '').lower()
            bill_number = bill_data.get('number')
            title = bill_data.get('title', '')
            summary = bill_data.get('summary', '')
            full_text = bill_data.get('full_text', '') or ''
            cleaned_text = clean_bill_text(full_text) if full_text else ''

            if not all([congress, bill_type, bill_number]):
                logging.error("Missing required bill data fields")
                return None

            # Fetch all versions of this bill
            from db_models import Bill
            bill_versions = Bill.query.filter_by(
                congress=congress,
                bill_type=bill_type,
                bill_number=bill_number
            ).order_by(Bill.version.desc()).all()

            latest_bill = bill_versions[0] if bill_versions else None
            is_new_version = False

            def bill_content_hash(title, summary, text):
                content = (title or '') + (summary or '') + (text or '')
                return hashlib.sha256(content.encode('utf-8')).hexdigest()

            text_for_hash = cleaned_text or full_text
            new_content_hash = bill_content_hash(title, summary, text_for_hash)
            if latest_bill:
                if latest_bill.content_hash:
                    latest_content_hash = latest_bill.content_hash
                else:
                    latest_content_hash = bill_content_hash(
                        latest_bill.title,
                        latest_bill.summary,
                        latest_bill.full_text or '',
                    )
            else:
                latest_content_hash = None

            if latest_bill:
                if new_content_hash != latest_content_hash:
                    # New version needed
                    is_new_version = True
                    # Deactivate all previous versions
                    for b in bill_versions:
                        b.active = False
                    db.session.commit()  # Commit deactivation before adding new version
                    new_version = latest_bill.version + 1
                else:
                    # No change — backfill stored text if we have it and row does not
                    if text_for_hash and not latest_bill.full_text:
                        latest_bill.full_text = text_for_hash
                        latest_bill.full_text_fetched_at = datetime.utcnow()
                        latest_bill.content_hash = new_content_hash
                    latest_bill.last_updated = datetime.utcnow()
                    db.session.commit()
                    return latest_bill
            else:
                # First version
                is_new_version = True
                new_version = 1

            if is_new_version:
                # Create new bill version
                bill = Bill(
                    congress=congress,
                    bill_type=bill_type,
                    bill_number=bill_number,
                    title=title,
                    summary=summary,
                    version=new_version,
                    active=True,
                    last_updated=datetime.utcnow(),
                )
                if text_for_hash:
                    bill.full_text = text_for_hash
                    bill.full_text_fetched_at = datetime.utcnow()
                    bill.content_hash = new_content_hash
                # Set sponsor info
                sponsors = bill_data.get('sponsors', [])
                if sponsors:
                    sponsor = sponsors[0]
                    bill.sponsor_name = f"{sponsor.get('firstName', '')} {sponsor.get('lastName', '')}".strip()
                    bill.sponsor_party = sponsor.get('party')
                    bill.sponsor_state = sponsor.get('state')
                # Set dates
                introduced_date = bill_data.get('introducedDate')
                if introduced_date:
                    try:
                        bill.introduced_date = datetime.fromisoformat(introduced_date.replace('Z', '+00:00')).replace(tzinfo=None)
                    except Exception:
                        pass
                # Set actions
                action_list = []
                actions = bill_data.get('actions', {})
                if actions and 'actions' in actions:
                    action_list = actions['actions'] or []
                    if action_list:
                        latest_action = action_list[0]
                        bill.status = latest_action.get('text', '')
                        action_date = latest_action.get('actionDate')
                        if action_date:
                            try:
                                bill.last_action_date = datetime.fromisoformat(action_date + 'T00:00:00')
                            except Exception:
                                pass
                # Set Congress API URL
                bill.congress_api_url = f"https://api.congress.gov/v3/bill/{congress}/{bill_type}/{bill_number}"
                # Set summary if not present
                if not bill.summary and text_for_hash:
                    sections = extract_sections(text_for_hash)
                    if sections:
                        bill.summary = sections[0][:500] + "..." if len(sections[0]) > 500 else sections[0]
                db.session.add(bill)
                db.session.commit()  # Commit bill first to get the ID
                
                # Now process actions after bill has been committed and has an ID
                self._process_bill_actions(bill, action_list)
                # AI analysis is intentionally not run here — callers queue async analysis.
                logging.info(
                    f"Ingested {bill.get_bill_identifier()} v{bill.version} "
                    f"(full_text={'yes' if bill.full_text else 'no'}); AI analysis deferred"
                )
                return bill
        except Exception as e:
            logging.error(f"Error processing bill data: {str(e)}")
            db.session.rollback()
            return None
    
    def generate_user_alerts(self):
        """
        Generate alerts for all users based on new bills and their preferences
        Returns list of users who received alerts
        """
        try:
            # Get all users with alert preferences enabled
            from db_models import User
            users = User.query.filter_by(alert_enabled=True).all()
            users_with_alerts = []
            
            # Get recently updated bills (last 7 days)
            from datetime import timedelta
            cutoff_date = datetime.utcnow() - timedelta(days=7)
            recent_bills = Bill.query.filter(Bill.last_updated >= cutoff_date).all()
            
            for user in users:
                user_preferences = user.get_policy_preferences()
                if not user_preferences:
                    continue  # Skip users without preferences
                
                alerts_created = 0
                
                for bill in recent_bills:
                    # Skip if we already have an alert for this user/bill combination
                    from db_models import Alert
                    existing_alert = Alert.query.filter_by(
                        user_id=user.id,
                        bill_id=bill.id
                    ).first()
                    
                    if existing_alert:
                        continue
                    
                    # Check if bill matches user interests
                    bill_analysis = bill.get_ai_analysis()
                    if not bill_analysis:
                        continue
                    
                    # Calculate alignment score
                    try:
                        alignment_score = self.ai_analyzer.calculate_alignment_score(
                            bill_analysis, user_preferences
                        )
                        
                        # Create alert if alignment is significant (positive or negative)
                        if abs(alignment_score) >= 30:  # Threshold for creating alerts
                            alert_type = 'alignment' if alignment_score > 0 else 'conflict'
                            priority = 'high' if abs(alignment_score) >= 70 else 'medium'
                            
                            # Generate alert message
                            bill_title = bill.title or f"Bill {bill.get_bill_identifier()}"
                            if alignment_score > 0:
                                title = f"Bill matches your interests: {bill.get_bill_identifier()}"
                                message = f"'{bill_title}' aligns with your policy preferences (Score: +{alignment_score:.0f})"
                            else:
                                title = f"Bill conflicts with your preferences: {bill.get_bill_identifier()}"
                                message = f"'{bill_title}' conflicts with your policy preferences (Score: {alignment_score:.0f})"
                            
                            # Create alert
                            alert = Alert(
                                user_id=user.id,
                                bill_id=bill.id,
                                alert_type=alert_type,
                                title=title,
                                message=message,
                                alignment_score=alignment_score,
                                priority=priority
                            )
                            
                            db.session.add(alert)
                            alerts_created += 1
                            
                    except Exception as e:
                        logging.error(f"Error calculating alignment for user {user.id}, bill {bill.id}: {str(e)}")
                        continue
                
                if alerts_created > 0:
                    users_with_alerts.append(user)
                    logging.info(f"Created {alerts_created} alerts for user {user.username}")
            
            db.session.commit()
            return users_with_alerts
            
        except Exception as e:
            logging.error(f"Error generating user alerts: {str(e)}")
            db.session.rollback()
            return []
    
    def create_specific_alert(self, user_id, bill_id, alert_type, title, message, alignment_score=None):
        """Create a specific alert for a user about a bill"""
        try:
            # Check if alert already exists
            from db_models import Alert
            existing_alert = Alert.query.filter_by(
                user_id=user_id,
                bill_id=bill_id,
                alert_type=alert_type
            ).first()
            
            if existing_alert:
                return existing_alert
            
            # Determine priority based on alignment score
            priority = 'medium'
            if alignment_score:
                if abs(alignment_score) >= 70:
                    priority = 'high'
                elif abs(alignment_score) >= 50:
                    priority = 'medium'
                else:
                    priority = 'low'
            
            alert = Alert(
                user_id=user_id,
                bill_id=bill_id,
                alert_type=alert_type,
                title=title,
                message=message,
                alignment_score=alignment_score,
                priority=priority
            )
            
            db.session.add(alert)
            db.session.commit()
            
            return alert
            
        except Exception as e:
            logging.error(f"Error creating alert: {str(e)}")
            db.session.rollback()
            return None
    
    def update_bill_status(self, bill_id):
        """Update a bill's status by fetching latest data from Congress API"""
        try:
            from db_models import Bill
            bill = Bill.query.get(bill_id)
            if not bill:
                return None
            
            # This would fetch updated data from Congress API
            # For now, just update the last_updated timestamp
            bill.last_updated = datetime.utcnow()
            db.session.commit()
            
            return bill
            
        except Exception as e:
            logging.error(f"Error updating bill status: {str(e)}")
            db.session.rollback()
            return None
    
    def analyze_bill_changes(self, old_text, new_text, bill_id):
        """Analyze changes between bill versions and create alerts if significant"""
        try:
            # This would use AI to analyze differences between bill versions
            # and create alerts for users watching this bill
            
            # For now, just log that a change was detected
            logging.info(f"Bill {bill_id} has been updated")
            
            # Could implement diff analysis and alert generation here
            return True
            
        except Exception as e:
            logging.error(f"Error analyzing bill changes: {str(e)}")
            return False
    
    def _process_bill_actions(self, bill, action_list):
        """Process and store bill actions from Congress API data"""
        try:
            for action_data in action_list:
                # Check if action already exists
                action_date = action_data.get('actionDate')
                action_text = action_data.get('text', '')
                
                if not action_date or not action_text:
                    continue
                
                # Parse action date
                try:
                    parsed_date = datetime.fromisoformat(action_date + 'T00:00:00')
                except:
                    continue
                
                # Check if this action already exists
                from db_models import BillAction
                existing_action = BillAction.query.filter_by(
                    bill_id=bill.id,
                    action_date=parsed_date,
                    action_text=action_text
                ).first()
                
                if existing_action:
                    continue  # Skip if already exists
                
                # Determine action type from text
                action_type = self._categorize_action_type(action_text)
                
                # Create action description
                action_description = self._generate_action_description(action_text, action_type)
                
                # Get source system info
                source_system = action_data.get('sourceSystem', {})
                source_system_name = source_system.get('name', 'Congress.gov') if source_system else 'Congress.gov'
                
                # Create new action
                bill_action = BillAction(
                    bill_id=bill.id,
                    action_date=parsed_date,
                    action_type=action_type,
                    action_text=action_text,
                    action_description=action_description,
                    source_system='congress_api',
                    source_system_name=source_system_name
                )
                
                db.session.add(bill_action)
                
            db.session.commit()
            logging.info(f"Processed {len(action_list)} actions for bill {bill.get_bill_identifier()}")
            
        except Exception as e:
            logging.error(f"Error processing bill actions: {str(e)}")
            db.session.rollback()
    
    def _categorize_action_type(self, action_text):
        """Categorize action text into action types"""
        action_text_lower = action_text.lower()
        
        # Define action type patterns
        action_patterns = {
            'introduced': ['introduced', 'introduction'],
            'referred': ['referred', 'referred to'],
            'reported': ['reported', 'reported by'],
            'passed': ['passed', 'agreed to', 'adopted'],
            'failed': ['failed', 'rejected', 'not agreed to'],
            'enacted': ['enacted', 'became law', 'signed'],
            'vetoed': ['vetoed', 'veto'],
            'amended': ['amended', 'amendment'],
            'scheduled': ['scheduled', 'placed on calendar'],
            'hearing': ['hearing', 'heard'],
            'markup': ['markup', 'marked up'],
            'conference': ['conference', 'conferees'],
            'resolved': ['resolved', 'resolution'],
            'withdrawn': ['withdrawn', 'withdrawal']
        }
        
        for action_type, patterns in action_patterns.items():
            if any(pattern in action_text_lower for pattern in patterns):
                return action_type
        
        return 'other'
    
    def _generate_action_description(self, action_text, action_type):
        """Generate a human-readable description of the action"""
        descriptions = {
            'introduced': 'Bill was introduced in Congress',
            'referred': 'Bill was referred to committee for review',
            'reported': 'Committee reported the bill favorably',
            'passed': 'Bill was passed by the chamber',
            'failed': 'Bill failed to pass',
            'enacted': 'Bill became law',
            'vetoed': 'Bill was vetoed by the President',
            'amended': 'Bill was amended',
            'scheduled': 'Bill was scheduled for consideration',
            'hearing': 'Public hearing was held on the bill',
            'markup': 'Committee marked up the bill',
            'conference': 'Conference committee was formed',
            'resolved': 'Differences between chambers were resolved',
            'withdrawn': 'Bill was withdrawn from consideration',
            'other': 'Other legislative action occurred'
        }
        
        return descriptions.get(action_type, 'Legislative action occurred')
