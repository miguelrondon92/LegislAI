from datetime import datetime, timedelta
from sqlalchemy import and_
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
                from db_models import Bill
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
        from db_models import User
        active_users = User.query.filter_by(alert_enabled=True).all()
        
        users_to_notify = []
        for user in active_users:
            if self._should_notify_user(user, bill):
                users_to_notify.append(user)
                
        return users_to_notify

    def _should_notify_user(self, user, bill):
        """Determine if a user should be notified about this bill."""
        # Check if user has this bill in their watchlist
        from db_models import WatchlistItem
        watchlist_match = WatchlistItem.query.filter_by(
            user_id=user.id,
            bill_id=bill.id
        ).first()
        
        if watchlist_match:
            return True

        # Check user's policy subscriptions against bill's category mappings (new database structure)
        from db_models import UserPolicySubscription, BillCategoryMapping, PolicyCategory
        
        # Get user's active policy subscriptions
        user_subscriptions = UserPolicySubscription.query.filter_by(
            user_id=user.id,
            notification_enabled=True
        ).all()
        
        if not user_subscriptions:
            return False
        
        # Get bill's category mappings
        bill_categories = BillCategoryMapping.query.filter_by(bill_id=bill.id).all()
        
        if not bill_categories:
            return False
        
        # Check for matches between user subscriptions and bill categories
        for subscription in user_subscriptions:
            for bill_category in bill_categories:
                if (subscription.policy_category_id == bill_category.policy_category_id and 
                    subscription.interest_level >= 0.5 and  # User has medium+ interest
                    bill_category.relevance_score >= 0.6):  # Bill has significant relevance to this category
                    return True

        return False

    def _create_notification(self, user, bill):
        """Create a notification for a user about a bill."""
        # Get AI analysis (try new structure first, then fallback)
        analysis = None
        active_analysis = bill.get_active_ai_analysis()
        if active_analysis:
            analysis = active_analysis.get_analysis_data()
        else:
            analysis = bill.get_ai_analysis()  # Fallback to old structure
        
        # Determine alert priority based on bill characteristics
        priority = 'medium'
        
        # Check for high-risk hidden provisions
        if bill.has_high_risk_provisions():
            priority = 'high'
        
        # Check complexity score
        complexity_score = bill.get_complexity_score_new()
        if complexity_score and complexity_score > 0.8:
            priority = 'high'
        
        # Check user interest level for matched categories
        user_max_interest = self._get_user_max_interest_for_bill(user, bill)
        if user_max_interest and user_max_interest >= 0.8:
            priority = 'high'
        
        # Create notification title
        bill_id = bill.get_bill_identifier()
        title = f"New Analysis: {bill_id}"
        
        if priority == 'high':
            title = f"🚨 High Priority: {bill_id}"
        
        # Create notification message
        message = self._generate_notification_message(bill, analysis, user)
        
        # Create alert
        from db_models import Alert
        alert = Alert(
            user_id=user.id,
            bill_id=bill.id,
            alert_type='new_analysis',
            title=title,
            message=message,
            priority=priority
        )
        
        db.session.add(alert)

    def _get_user_max_interest_for_bill(self, user, bill):
        """Get the user's maximum interest level for categories related to this bill."""
        from db_models import UserPolicySubscription, BillCategoryMapping
        
        # Get bill's category mappings
        bill_categories = BillCategoryMapping.query.filter_by(bill_id=bill.id).all()
        
        if not bill_categories:
            return 0.0
        
        max_interest = 0.0
        for bill_category in bill_categories:
            subscription = UserPolicySubscription.query.filter_by(
                user_id=user.id,
                policy_category_id=bill_category.policy_category_id
            ).first()
            
            if subscription and subscription.interest_level > max_interest:
                max_interest = subscription.interest_level
        
        return max_interest

    def _generate_notification_message(self, bill, analysis, user):
        """Generate a notification message from the bill analysis."""
        message_parts = []
        
        # Add bill identifier and title
        message_parts.append(f"Bill: {bill.get_bill_identifier()}")
        if bill.title:
            message_parts.append(f"Title: {bill.title[:100]}...")
        
        # Add why this bill is relevant to the user
        relevant_categories = self._get_relevant_categories_for_user(user, bill)
        if relevant_categories:
            category_names = [cat.display_name for cat in relevant_categories]
            message_parts.append(f"\nRelevant to your interests: {', '.join(category_names[:3])}")
        
        # Add summary if available (use new structure first)
        summary_text = bill.get_summary_text()
        if summary_text:
            message_parts.append(f"\nSummary: {summary_text[:200]}...")
        
        # Add key insights from AI analysis
        if analysis:
            # Complexity and controversy scores
            complexity_score = bill.get_complexity_score_new()
            if complexity_score:
                complexity_percent = int(complexity_score * 100)
                message_parts.append(f"\nComplexity: {complexity_percent}/100")
            
            # Hidden provisions warning
            hidden_provisions_count = bill.get_hidden_provisions_count()
            if hidden_provisions_count['high'] > 0:
                message_parts.append(f"\n🚨 {hidden_provisions_count['high']} high-risk hidden provisions detected!")
            elif hidden_provisions_count['medium'] > 0:
                message_parts.append(f"\n⚠️ {hidden_provisions_count['medium']} medium-risk provisions found")
            
            # Key stakeholders
            if 'stakeholders' in analysis and 'primary_affected' in analysis['stakeholders']:
                stakeholders = analysis['stakeholders']['primary_affected'][:2]  # Top 2
                if stakeholders:
                    message_parts.append(f"\nPrimary stakeholders: {', '.join(stakeholders)}")
        
        return "\n".join(message_parts)

    def _get_relevant_categories_for_user(self, user, bill):
        """Get policy categories that are relevant to both the user and the bill."""
        from db_models import UserPolicySubscription, BillCategoryMapping, PolicyCategory
        
        # Get user's subscribed categories
        user_categories = UserPolicySubscription.query.filter_by(
            user_id=user.id,
            notification_enabled=True
        ).all()
        
        # Get bill's categories
        bill_categories = BillCategoryMapping.query.filter_by(bill_id=bill.id).all()
        
        # Find overlap
        relevant_categories = []
        for user_sub in user_categories:
            for bill_cat in bill_categories:
                if (user_sub.policy_category_id == bill_cat.policy_category_id and
                    user_sub.interest_level >= 0.5):
                    category = PolicyCategory.query.get(user_sub.policy_category_id)
                    if category:
                        relevant_categories.append(category)
        
        return relevant_categories

    def send_pending_notifications(self):
        """Send all pending notifications based on user alert frequency preferences."""
        try:
            with app.app_context():
                # Get all unread alerts
                from db_models import Alert
                unread_alerts = Alert.query.filter_by(is_read=False).all()
                
                # Group alerts by user
                user_alerts = {}
                for alert in unread_alerts:
                    if alert.user_id not in user_alerts:
                        user_alerts[alert.user_id] = []
                    user_alerts[alert.user_id].append(alert)
                
                # Process alerts for each user based on their frequency preference
                for user_id, alerts in user_alerts.items():
                    from db_models import User
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
        from db_models import Alert
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
        """Send enhanced notifications to a user via email with robust content and links."""
        try:
            with app.app_context():
                # Create enhanced email subject
                high_priority_count = sum(1 for alert in alerts if alert.priority == 'high')
                if high_priority_count > 0:
                    subject = f"🚨 LegislAI: {high_priority_count} High Priority Bill{'s' if high_priority_count != 1 else ''} + {len(alerts) - high_priority_count} More"
                else:
                    subject = f"📬 LegislAI: {len(alerts)} New Bill Analysis{'es' if len(alerts) > 1 else ''} Matching Your Interests"
                
                # Get user's subscription info for context
                user_subscription_info = self._get_user_subscription_summary(user)
                
                # Create enhanced email body
                body_parts = [
                    f"Hello {user.get_full_name()},",
                    "",
                    f"🎯 You have {len(alerts)} new legislative analysis{'es' if len(alerts) > 1 else ''} matching your policy interests!",
                    ""
                ]
                
                # Add high priority alerts first
                high_priority_alerts = [a for a in alerts if a.priority == 'high']
                medium_priority_alerts = [a for a in alerts if a.priority != 'high']
                
                if high_priority_alerts:
                    body_parts.extend([
                        "🚨 HIGH PRIORITY ALERTS",
                        "=" * 40,
                        ""
                    ])
                    
                    for alert in high_priority_alerts:
                        bill_content = self._generate_enhanced_bill_email_content(alert.bill, user, alert)
                        body_parts.extend(bill_content)
                        body_parts.append("")
                
                if medium_priority_alerts:
                    if high_priority_alerts:
                        body_parts.extend([
                            "📋 ADDITIONAL ALERTS",
                            "=" * 40,
                            ""
                        ])
                    
                    for alert in medium_priority_alerts:
                        bill_content = self._generate_enhanced_bill_email_content(alert.bill, user, alert)
                        body_parts.extend(bill_content)
                        body_parts.append("")
                
                # Add subscription context
                body_parts.extend([
                    "📂 YOUR ACTIVE SUBSCRIPTIONS",
                    "=" * 40,
                    user_subscription_info,
                    ""
                ])
                
                # Add robust footer with multiple links
                base_url = current_app.config.get('BASE_URL', 'http://localhost:5000')
                body_parts.extend([
                    "🔗 QUICK ACTIONS",
                    "=" * 40,
                    f"📊 View Dashboard: {base_url}/",
                    f"🔍 Search Bills: {base_url}/bill_search",
                    f"🔔 Manage Alerts: {base_url}/alerts",
                    f"⚙️ Update Preferences: {base_url}/profile",
                    f"👤 Edit Profile: {base_url}/auth/profile",
                    "",
                    "📱 MOBILE ACCESS",
                    f"Access LegislAI on any device: {base_url}",
                    "",
                    "📧 EMAIL PREFERENCES",
                    f"Current frequency: {user.alert_frequency.title()}",
                    f"Change frequency: {base_url}/profile",
                    "",
                    "❓ NEED HELP?",
                    "Reply to this email or visit our help section for support.",
                    "",
                    "🏛️ ABOUT LEGISLAI",
                    "LegislAI uses advanced AI to analyze U.S. legislation and identify",
                    "bills that match your policy interests. Our system detects hidden",
                    "provisions, complexity scores, and stakeholder impacts to keep",
                    "you informed about legislation that matters to you.",
                    "",
                    "Best regards,",
                    "The LegislAI Team",
                    "",
                    "---",
                    f"This email was sent to {user.email} because you have active",
                    "LegislAI notification subscriptions. You can unsubscribe or modify",
                    f"your preferences at: {base_url}/profile",
                    "",
                    f"© 2025 LegislAI - Legislative Intelligence Platform"
                ])
                
                # Create and send email with both plain text and HTML
                email_body = "\n".join(body_parts)
                html_body = self._convert_to_html_email(body_parts, user, alerts, base_url)
                
                msg = Message(
                    subject=subject,
                    recipients=[user.email],
                    body=email_body,
                    html=html_body,
                    sender=os.environ.get('MAIL_DEFAULT_SENDER', 'noreply@legislai.com')
                )
                
                mail.send(msg)
                
                # Mark alerts as read
                for alert in alerts:
                    alert.is_read = True
                
                self.logger.info(f"Sent enhanced notification email with {len(alerts)} alerts to user {user.email}")
            
        except Exception as e:
            self.logger.error(f"Error sending email to user {user.id}: {str(e)}")
            raise 

    def _get_user_subscription_summary(self, user):
        """Get a summary of user's active policy subscriptions"""
        try:
            from db_models import UserPolicySubscription, PolicyCategory
            
            subscriptions = UserPolicySubscription.query.filter_by(
                user_id=user.id,
                notification_enabled=True
            ).all()
            
            if not subscriptions:
                return "No active subscriptions"
            
            summary_lines = []
            for sub in subscriptions:
                category = PolicyCategory.query.get(sub.policy_category_id)
                if category:
                    interest_label = self._get_interest_level_label(sub.interest_level)
                    summary_lines.append(f"• {category.display_name}: {interest_label}")
            
            return "\n".join(summary_lines)
            
        except Exception as e:
            self.logger.error(f"Error getting subscription summary: {e}")
            return "Unable to load subscription information"
    
    def _get_interest_level_label(self, interest_level):
        """Convert interest level to human-readable label"""
        if interest_level >= 8.0:
            return "🔥 Very High Interest"
        elif interest_level >= 6.0:
            return "🔥 High Interest"
        elif interest_level >= 4.0:
            return "📊 Medium Interest"
        elif interest_level >= 2.0:
            return "📉 Low Interest"
        else:
            return "📋 Minimal Interest"
    
    def _generate_enhanced_bill_email_content(self, bill, user, alert):
        """Generate enhanced email content for a specific bill"""
        try:
            content_lines = []
            
            # Bill header with direct link
            base_url = current_app.config.get('BASE_URL', 'http://localhost:5000')
            bill_url = f"{base_url}/bill/{bill.congress}/{bill.bill_type}/{bill.bill_number}"
            
            content_lines.extend([
                f"📄 BILL: {bill.get_bill_identifier()}",
                f"🔗 Direct Link: {bill_url}",
                f"📝 Title: {bill.title}",
                ""
            ])
            
            # Why this is relevant to the user
            relevant_categories = self._get_relevant_categories_for_user(user, bill)
            if relevant_categories:
                category_names = [cat.display_name for cat in relevant_categories[:2]]  # Show top 2
                user_interest = self._get_user_max_interest_for_bill(user, bill)
                content_lines.extend([
                    f"🎯 Relevant to: {', '.join(category_names)}",
                    f"💯 Your interest level: {self._get_interest_level_label(user_interest)}",
                    ""
                ])
            
            # Key bill insights
            content_lines.append("📊 KEY INSIGHTS:")
            
            # Complexity score
            complexity_score = bill.get_complexity_score_new()
            if complexity_score:
                complexity_percent = int(complexity_score * 100)
                content_lines.append(f"   📈 Complexity: {complexity_percent}/100")
            
            # Hidden provisions
            hidden_provisions_count = bill.get_hidden_provisions_count()
            if hidden_provisions_count['high'] > 0:
                content_lines.append(f"   🚨 {hidden_provisions_count['high']} high-risk hidden provisions detected!")
            elif hidden_provisions_count['medium'] > 0:
                content_lines.append(f"   ⚠️ {hidden_provisions_count['medium']} medium-risk provisions found")
            elif hidden_provisions_count['total'] > 0:
                content_lines.append(f"   ℹ️ {hidden_provisions_count['total']} provisions flagged for review")
            else:
                content_lines.append("   ✅ No concerning hidden provisions detected")
            
            # Bill status and sponsor
            content_lines.extend([
                f"   🏛️ Status: {bill.status}",
                f"   👤 Sponsor: {bill.sponsor_name} ({bill.sponsor_party})"
            ])
            
            # Summary
            summary_text = bill.get_summary_text()
            if summary_text:
                # Truncate summary for email
                summary_preview = summary_text[:300] + "..." if len(summary_text) > 300 else summary_text
                content_lines.extend([
                    "",
                    "📝 SUMMARY:",
                    summary_preview
                ])
            
            # Get AI analysis for stakeholders
            analysis = None
            active_analysis = bill.get_active_ai_analysis()
            if active_analysis:
                analysis = active_analysis.get_analysis_data()
            else:
                analysis = bill.get_ai_analysis()  # Fallback
            
            if analysis and 'stakeholders' in analysis:
                stakeholders = analysis['stakeholders']
                if 'primary_affected' in stakeholders:
                    affected_parties = stakeholders['primary_affected'][:3]  # Top 3
                    if affected_parties:
                        content_lines.extend([
                            "",
                            "👥 KEY STAKEHOLDERS:",
                            "   " + ", ".join(affected_parties)
                        ])
            
            # Action items
            content_lines.extend([
                "",
                "🔗 ACTIONS:",
                f"   📖 Read full analysis: {bill_url}",
                f"   👀 Add to watchlist: {bill_url}#watchlist",
                f"   📤 Share this bill: {bill_url}#share"
            ])
            
            return content_lines
            
        except Exception as e:
            self.logger.error(f"Error generating bill email content: {e}")
            return [
                f"📄 BILL: {bill.get_bill_identifier()}",
                f"📝 Title: {bill.title}",
                f"🔗 View details: {base_url}/bill/{bill.congress}/{bill.bill_type}/{bill.bill_number}",
                "",
                "⚠️ Unable to load detailed analysis - please visit the link above for full information."
            ]
    
    def _convert_to_html_email(self, body_parts, user, alerts, base_url):
        """Convert plain text email to HTML format"""
        try:
            html_parts = [
                "<!DOCTYPE html>",
                "<html>",
                "<head>",
                "    <meta charset='utf-8'>",
                "    <title>LegislAI Notification</title>",
                "    <style>",
                "        body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px; }",
                "        .header { background: #2c3e50; color: white; padding: 20px; border-radius: 5px; margin-bottom: 20px; }",
                "        .alert-high { border-left: 4px solid #e74c3c; padding-left: 15px; margin: 15px 0; }",
                "        .alert-medium { border-left: 4px solid #f39c12; padding-left: 15px; margin: 15px 0; }",
                "        .bill-section { background: #f8f9fa; padding: 15px; border-radius: 5px; margin: 15px 0; }",
                "        .quick-actions { background: #e8f4f8; padding: 15px; border-radius: 5px; margin: 15px 0; }",
                "        .subscription-info { background: #f0f8ff; padding: 15px; border-radius: 5px; margin: 15px 0; }",
                "        a { color: #3498db; text-decoration: none; }",
                "        a:hover { text-decoration: underline; }",
                "        .button { background: #3498db; color: white; padding: 10px 20px; border-radius: 5px; display: inline-block; margin: 5px; }",
                "        .footer { border-top: 1px solid #ddd; padding-top: 20px; margin-top: 30px; font-size: 12px; color: #666; }",
                "    </style>",
                "</head>",
                "<body>",
                f"    <div class='header'>",
                f"        <h1>🏛️ LegislAI Notification</h1>",
                f"        <p>Legislative Intelligence for {user.get_full_name()}</p>",
                f"    </div>"
            ]
            
            # Convert body content to HTML
            in_bill_section = False
            for line in body_parts:
                line = line.strip()
                
                if line.startswith("🚨 HIGH PRIORITY"):
                    html_parts.append("    <div class='alert-high'>")
                    html_parts.append(f"        <h2>{line}</h2>")
                elif line.startswith("📋 ADDITIONAL"):
                    html_parts.append("    <div class='alert-medium'>")
                    html_parts.append(f"        <h2>{line}</h2>")
                elif line.startswith("📄 BILL:"):
                    if in_bill_section:
                        html_parts.append("    </div>")
                    html_parts.append("    <div class='bill-section'>")
                    html_parts.append(f"        <h3>{line}</h3>")
                    in_bill_section = True
                elif line.startswith("🔗 QUICK ACTIONS"):
                    if in_bill_section:
                        html_parts.append("    </div>")
                        in_bill_section = False
                    html_parts.append("    <div class='quick-actions'>")
                    html_parts.append(f"        <h3>{line}</h3>")
                elif line.startswith("📂 YOUR ACTIVE"):
                    html_parts.append("    <div class='subscription-info'>")
                    html_parts.append(f"        <h3>{line}</h3>")
                elif "http" in line and (":" in line):
                    # Convert URLs to clickable links
                    parts = line.split(": ", 1)
                    if len(parts) == 2:
                        label, url = parts
                        html_parts.append(f"        <p>{label}: <a href='{url}' class='button'>{url}</a></p>")
                    else:
                        html_parts.append(f"        <p><a href='{line}'>{line}</a></p>")
                elif line.startswith("---"):
                    html_parts.append("    <div class='footer'>")
                elif line == "":
                    html_parts.append("        <br>")
                else:
                    html_parts.append(f"        <p>{line}</p>")
            
            if in_bill_section:
                html_parts.append("    </div>")
            
            html_parts.extend([
                "    </div>",
                "</body>",
                "</html>"
            ])
            
            return "\n".join(html_parts)
            
        except Exception as e:
            self.logger.error(f"Error converting to HTML: {e}")
            # Fallback to plain text
            return "<pre>" + "\n".join(body_parts) + "</pre>"