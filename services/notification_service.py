from datetime import datetime, timedelta
from sqlalchemy import and_
from models import User, Bill, Alert, WatchlistItem
from app import db, mail, app
from flask_mail import Message
from flask import current_app
import logging
import os

logger = logging.getLogger(__name__)

class NotificationService:
    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def process_new_bill_analysis(self, bill_id):
        """Process a newly analyzed bill and create notifications for relevant users."""
        try:
            with app.app_context():
                bill = Bill.query.get(bill_id)
                if not bill:
                    self.logger.error(f"Bill {bill_id} not found")
                    return

                # Get users who should be notified based on their preferences
                users_to_notify = self._get_users_to_notify(bill)
                
                for user in users_to_notify:
                    self._create_notification(user, bill)

                db.session.commit()
                self.logger.info(f"Processed notifications for bill {bill.get_bill_identifier()}")
            
        except Exception as e:
            self.logger.error(f"Error processing bill {bill_id}: {str(e)}")
            db.session.rollback()

    def _get_users_to_notify(self, bill):
        """Get users who should be notified about this bill based on their preferences."""
        # Get users with active alerts
        active_users = User.query.filter_by(alert_enabled=True).all()
        
        users_to_notify = []
        for user in active_users:
            if self._should_notify_user(user, bill):
                users_to_notify.append(user)
                
        return users_to_notify

    def _should_notify_user(self, user, bill):
        """Determine if a user should be notified about this bill."""
        # Check if user has this bill in their watchlist
        watchlist_match = WatchlistItem.query.filter_by(
            user_id=user.id,
            bill_id=bill.id
        ).first()
        
        if watchlist_match:
            return True

        # Check user's policy preferences against bill's categories
        user_preferences = user.get_policy_preferences()
        bill_categories = bill.get_policy_categories()
        
        # If user has preferences and bill has categories, check for matches
        if user_preferences and bill_categories:
            for category, score in user_preferences.items():
                if category in bill_categories and score > 0.5:  # Threshold for interest
                    return True

        return False

    def _create_notification(self, user, bill):
        """Create a notification for a user about a bill."""
        # Get AI analysis
        analysis = bill.get_ai_analysis()
        
        # Create notification title
        title = f"New Analysis: {bill.get_bill_identifier()} - {bill.title[:50]}..."
        
        # Create notification message
        message = self._generate_notification_message(bill, analysis)
        
        # Create alert
        alert = Alert(
            user_id=user.id,
            bill_id=bill.id,
            alert_type='new_analysis',
            title=title,
            message=message,
            priority='medium'
        )
        
        db.session.add(alert)

    def _generate_notification_message(self, bill, analysis):
        """Generate a notification message from the bill analysis."""
        message_parts = []
        
        # Add bill identifier and title
        message_parts.append(f"Bill: {bill.get_bill_identifier()}")
        message_parts.append(f"Title: {bill.title}")
        
        # Add summary if available
        if bill.summary:
            message_parts.append(f"\nSummary: {bill.summary[:200]}...")
        
        # Add key points from AI analysis
        if analysis:
            if 'key_points' in analysis:
                message_parts.append("\nKey Points:")
                for point in analysis['key_points'][:3]:  # Limit to top 3 points
                    message_parts.append(f"• {point}")
            
            if 'impact_analysis' in analysis:
                message_parts.append(f"\nImpact: {analysis['impact_analysis'][:150]}...")
        
        return "\n".join(message_parts)

    def send_pending_notifications(self):
        """Send all pending notifications based on user alert frequency preferences."""
        try:
            with app.app_context():
                # Get all unread alerts
                unread_alerts = Alert.query.filter_by(is_read=False).all()
                
                # Group alerts by user
                user_alerts = {}
                for alert in unread_alerts:
                    if alert.user_id not in user_alerts:
                        user_alerts[alert.user_id] = []
                    user_alerts[alert.user_id].append(alert)
                
                # Process alerts for each user based on their frequency preference
                for user_id, alerts in user_alerts.items():
                    user = User.query.get(user_id)
                    if not user or not user.alert_enabled:
                        continue
                    
                    # Check if it's time to send alerts based on user's frequency
                    if self._should_send_alerts(user):
                        self._send_user_notifications(user, alerts)
                        
                db.session.commit()
            
        except Exception as e:
            self.logger.error(f"Error sending notifications: {str(e)}")
            db.session.rollback()

    def _should_send_alerts(self, user):
        """Determine if it's time to send alerts based on user's frequency preference."""
        last_alert = Alert.query.filter_by(user_id=user.id).order_by(Alert.created_at.desc()).first()
        
        if not last_alert:
            return True
            
        now = datetime.utcnow()
        time_since_last = now - last_alert.created_at
        
        if user.alert_frequency == 'daily':
            return time_since_last >= timedelta(days=1)
        elif user.alert_frequency == 'weekly':
            return time_since_last >= timedelta(weeks=1)
        elif user.alert_frequency == 'monthly':
            return time_since_last >= timedelta(days=30)
            
        return False

    def _send_user_notifications(self, user, alerts):
        """Send notifications to a user via email."""
        try:
            with app.app_context():
                # Create email subject
                subject = f"LegislAI Updates: {len(alerts)} New Bill Analysis{'es' if len(alerts) > 1 else ''}"
                
                # Create email body
                body_parts = [
                    f"Hello {user.username},",
                    f"\nYou have {len(alerts)} new bill analysis{'es' if len(alerts) > 1 else ''} to review:",
                    "\n" + "="*50 + "\n"
                ]
                
                # Add each alert to the email
                for alert in alerts:
                    body_parts.extend([
                        f"Bill: {alert.bill.get_bill_identifier()}",
                        f"Title: {alert.title}",
                        f"\n{alert.message}",
                        "\n" + "="*50 + "\n"
                    ])
                
                # Add footer
                body_parts.extend([
                    "\nYou can view more details and manage your preferences at:",
                    f"{current_app.config.get('BASE_URL', 'https://legislai.com')}/dashboard",
                    "\nBest regards,",
                    "The LegislAI Team"
                ])
                
                # Create and send email
                msg = Message(
                    subject=subject,
                    recipients=[user.email],
                    body="\n".join(body_parts),
                    sender=os.environ.get('MAIL_DEFAULT_SENDER', 'noreply@legislai.com')
                )
                
                mail.send(msg)
                
                # Mark alerts as read
                for alert in alerts:
                    alert.is_read = True
                
                self.logger.info(f"Sent {len(alerts)} notifications to user {user.id}")
            
        except Exception as e:
            self.logger.error(f"Error sending email to user {user.id}: {str(e)}")
            raise 