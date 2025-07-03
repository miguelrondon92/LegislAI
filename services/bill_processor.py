import logging
import json
import os
from datetime import datetime
from app import db
from models import Bill, User, Alert, BillAction
from services.ai_analyzer import AIAnalyzer
from services.congress_api import CongressAPI
from utils.text_processing import clean_bill_text, extract_sections

class BillProcessor:
    """Service for processing bill data and generating user alerts"""
    
    def __init__(self):
        self.ai_analyzer = AIAnalyzer()
        self.congress_api = CongressAPI()
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
        Process raw bill data from Congress API and save to database
        Returns the processed Bill object
        """
        try:
            # Extract basic bill information
            congress = bill_data.get('congress')
            bill_type = bill_data.get('type', '').lower()
            bill_number = bill_data.get('number')
            title = bill_data.get('title', '')
            
            if not all([congress, bill_type, bill_number]):
                logging.error("Missing required bill data fields")
                return None
            
            # Check if bill already exists
            existing_bill = Bill.query.filter_by(
                congress=congress,
                bill_type=bill_type,
                bill_number=bill_number
            ).first()
            
            if existing_bill:
                # Update existing bill
                bill = existing_bill
            else:
                # Create new bill
                bill = Bill(
                    congress=congress,
                    bill_type=bill_type,
                    bill_number=bill_number
                )
                db.session.add(bill)
                
                # Add to seen items for new bills
                bill_identifier = f"{bill_type.upper()}.{bill_number}"
                self.add_to_seen_items(bill_identifier)
            
            # Update bill fields
            bill.title = title
            bill.last_updated = datetime.utcnow()
            
            # Extract sponsor information
            sponsors = bill_data.get('sponsors', [])
            if sponsors:
                sponsor = sponsors[0]  # Primary sponsor
                bill.sponsor_name = f"{sponsor.get('firstName', '')} {sponsor.get('lastName', '')}".strip()
                bill.sponsor_party = sponsor.get('party')
                bill.sponsor_state = sponsor.get('state')
            
            # Extract dates
            introduced_date = bill_data.get('introducedDate')
            if introduced_date:
                try:
                    bill.introduced_date = datetime.fromisoformat(introduced_date.replace('Z', '+00:00')).replace(tzinfo=None)
                except:
                    pass
            
            # Extract latest action
            actions = bill_data.get('actions', {})
            if actions and 'actions' in actions:
                action_list = actions['actions']
                if action_list:
                    latest_action = action_list[0]
                    bill.status = latest_action.get('text', '')
                    action_date = latest_action.get('actionDate')
                    if action_date:
                        try:
                            bill.last_action_date = datetime.fromisoformat(action_date + 'T00:00:00')
                        except:
                            pass
                    
                    # Process and store all actions
                    self._process_bill_actions(bill, action_list)
            
            # Set Congress API URL
            bill.congress_api_url = f"https://api.congress.gov/v3/bill/{congress}/{bill_type}/{bill_number}"
            
            # Extract summary from first section if not already present and full text is available
            if not bill.summary:
                full_text = bill_data.get('full_text')
                if full_text:
                    # Clean and process the text
                    cleaned_text = clean_bill_text(full_text)
                    sections = extract_sections(cleaned_text)
                    if sections:
                        # Use first section as summary, limited to 500 chars
                        bill.summary = sections[0][:500] + "..." if len(sections[0]) > 500 else sections[0]
            
            # Commit to database
            db.session.commit()
            
            # Perform AI analysis if full text is available and not already analyzed
            full_text = bill_data.get('full_text')
            if full_text and not bill.get_ai_analysis():
                try:
                    # Clean and process the text for analysis
                    cleaned_text = clean_bill_text(full_text)
                    
                    # Check if AI analyzer is available
                    if not self.ai_analyzer.client:
                        logging.warning(f"AI analyzer not available for bill {bill.get_bill_identifier()}. Skipping AI analysis.")
                        return bill
                    
                    # Pass the bill object to the analyzer
                    analysis = self.ai_analyzer.analyze_bill(bill)
                    
                    # Only save analysis if it's valid and not empty
                    if analysis and isinstance(analysis, dict) and len(analysis) > 0:
                        # Check if analysis contains actual data (not just error messages)
                        has_valid_data = False
                        for key, value in analysis.items():
                            if value and value != "Unknown" and value != "Unable to generate summary due to technical error":
                                if isinstance(value, list) and len(value) > 0:
                                    has_valid_data = True
                                    break
                                elif isinstance(value, dict) and len(value) > 0:
                                    has_valid_data = True
                                    break
                                elif isinstance(value, str) and len(value) > 10:
                                    has_valid_data = True
                                    break
                                elif isinstance(value, (int, float)) and value != 0:
                                    has_valid_data = True
                                    break
                        
                        if has_valid_data:
                            bill.set_ai_analysis(analysis)
                            
                            # Extract complexity score
                            complexity_assessment = analysis.get('complexity_assessment', {})
                            if isinstance(complexity_assessment, dict):
                                complexity_score = complexity_assessment.get('complexity_score', 0)
                                if isinstance(complexity_score, (int, float)):
                                    bill.complexity_score = float(complexity_score)
                            
                            # Store policy categories
                            policy_implications = analysis.get('policy_implications', {})
                            if policy_implications and isinstance(policy_implications, dict):
                                bill.set_policy_categories(policy_implications)
                            
                            db.session.commit()
                            logging.info(f"Successfully performed AI analysis for bill {bill.get_bill_identifier()}")
                        else:
                            logging.warning(f"AI analysis returned empty or error data for bill {bill.get_bill_identifier()}. Not saving to database.")
                    else:
                        logging.warning(f"No valid AI analysis returned for bill {bill.get_bill_identifier()}")
                        
                except Exception as e:
                    logging.error(f"Error in AI analysis for bill {bill.get_bill_identifier()}: {str(e)}")
                    # Don't save error data to database
            
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
