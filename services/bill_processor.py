import logging
from datetime import datetime
from app import db
from models import Bill, User, Alert
from services.ai_analysis import AIAnalyzer
from utils.text_processing import clean_bill_text, extract_sections

class BillProcessor:
    """Service for processing bill data and generating user alerts"""
    
    def __init__(self):
        self.ai_analyzer = AIAnalyzer()
    
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
            
            # Process full text if available
            full_text = bill_data.get('full_text')
            if full_text:
                # Clean and process the text
                cleaned_text = clean_bill_text(full_text)
                bill.full_text = cleaned_text
                
                # Extract summary from first section if not already present
                if not bill.summary:
                    sections = extract_sections(cleaned_text)
                    if sections:
                        # Use first section as summary, limited to 500 chars
                        bill.summary = sections[0][:500] + "..." if len(sections[0]) > 500 else sections[0]
            
            # Set Congress API URL
            bill.congress_api_url = f"https://api.congress.gov/v3/bill/{congress}/{bill_type}/{bill_number}"
            
            # Commit to database
            db.session.commit()
            
            # Perform AI analysis if full text is available and not already analyzed
            if bill.full_text and not bill.get_ai_analysis():
                try:
                    analysis = self.ai_analyzer.analyze_bill(bill.full_text, bill.title)
                    if analysis:
                        bill.set_ai_analysis(analysis)
                        
                        # Extract complexity score
                        complexity_assessment = analysis.get('complexity_assessment', {})
                        complexity_score = complexity_assessment.get('complexity_score', 0)
                        if isinstance(complexity_score, (int, float)):
                            bill.complexity_score = float(complexity_score)
                        
                        # Store policy categories
                        policy_implications = analysis.get('policy_implications', {})
                        bill.set_policy_categories(policy_implications)
                        
                        db.session.commit()
                        
                except Exception as e:
                    logging.error(f"Error in AI analysis for bill {bill.get_bill_identifier()}: {str(e)}")
            
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
