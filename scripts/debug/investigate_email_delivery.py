#!/usr/bin/env python3
"""
Investigate why migron didn't actually receive the email and fix email delivery
"""

import sys
import os
import logging

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

def investigate_email_configuration():
    """Investigate the current email configuration"""
    try:
        from app import app
        import os
        
        with app.app_context():
            logger.info("🔍 Investigating email configuration...")
            
            # Check Flask app config
            logger.info("📧 Flask Email Configuration:")
            logger.info(f"   MAIL_SERVER: {app.config.get('MAIL_SERVER', 'Not set')}")
            logger.info(f"   MAIL_PORT: {app.config.get('MAIL_PORT', 'Not set')}")
            logger.info(f"   MAIL_USERNAME: {app.config.get('MAIL_USERNAME', 'Not set')}")
            logger.info(f"   MAIL_USE_TLS: {app.config.get('MAIL_USE_TLS', 'Not set')}")
            logger.info(f"   MAIL_USE_SSL: {app.config.get('MAIL_USE_SSL', 'Not set')}")
            
            # Check environment variables
            logger.info("\n🌍 Environment Variables:")
            mail_vars = ['MAIL_SERVER', 'MAIL_PORT', 'MAIL_USERNAME', 'MAIL_PASSWORD', 'MAIL_DEFAULT_SENDER']
            for var in mail_vars:
                value = os.environ.get(var, 'Not set')
                if var == 'MAIL_PASSWORD':
                    value = '***Set***' if value != 'Not set' else 'Not set'
                logger.info(f"   {var}: {value}")
            
            # Identify the email service
            mail_server = app.config.get('MAIL_SERVER', '')
            if 'mailtrap' in mail_server.lower():
                logger.info("\n📮 EMAIL SERVICE: Mailtrap (Development/Testing)")
                logger.info("   ⚠️  Mailtrap captures emails for testing - they don't reach real inboxes!")
                logger.info("   🔍 To see emails, check: https://mailtrap.io/inboxes")
                logger.info("   📧 Emails are stored in Mailtrap inbox, not delivered to miguelrondon92@gmail.com")
                return 'mailtrap'
            elif 'gmail' in mail_server.lower():
                logger.info("\n📮 EMAIL SERVICE: Gmail")
                return 'gmail'
            elif 'sendgrid' in mail_server.lower():
                logger.info("\n📮 EMAIL SERVICE: SendGrid")
                return 'sendgrid'
            else:
                logger.info(f"\n📮 EMAIL SERVICE: {mail_server}")
                return 'other'
                
    except Exception as e:
        logger.error(f"❌ Error investigating email config: {e}")
        return None

def check_mailtrap_inbox():
    """Provide instructions for checking Mailtrap inbox"""
    logger.info("📮 MAILTRAP INBOX CHECK INSTRUCTIONS:")
    logger.info("=" * 60)
    logger.info("1. Go to: https://mailtrap.io/")
    logger.info("2. Log in to your Mailtrap account")
    logger.info("3. Navigate to 'Email Testing' → 'Inboxes'")
    logger.info("4. Look for emails sent to 'miguelrondon92@gmail.com'")
    logger.info("5. The test emails should be captured there")
    logger.info("")
    logger.info("🔧 TO SET UP REAL EMAIL DELIVERY:")
    logger.info("Option 1: Use Gmail SMTP")
    logger.info("   - MAIL_SERVER=smtp.gmail.com")
    logger.info("   - MAIL_PORT=587")
    logger.info("   - MAIL_USE_TLS=True")
    logger.info("   - Use app password for MAIL_PASSWORD")
    logger.info("")
    logger.info("Option 2: Use SendGrid")
    logger.info("   - MAIL_SERVER=smtp.sendgrid.net")
    logger.info("   - MAIL_PORT=587")
    logger.info("   - MAIL_USERNAME=apikey")
    logger.info("   - MAIL_PASSWORD=<your_sendgrid_api_key>")

def test_real_email_delivery():
    """Test sending email with real delivery service"""
    try:
        from app import app, mail
        from flask_mail import Message
        from db_models import User
        import os
        
        logger.info("📧 Testing real email delivery setup...")
        
        # Check if we can set up Gmail delivery
        gmail_user = os.environ.get('GMAIL_USERNAME')
        gmail_password = os.environ.get('GMAIL_APP_PASSWORD')
        
        if gmail_user and gmail_password:
            logger.info("🔧 Configuring Gmail delivery...")
            
            with app.app_context():
                # Temporarily override email config for real delivery
                app.config['MAIL_SERVER'] = 'smtp.gmail.com'
                app.config['MAIL_PORT'] = 587
                app.config['MAIL_USE_TLS'] = True
                app.config['MAIL_USE_SSL'] = False
                app.config['MAIL_USERNAME'] = gmail_user
                app.config['MAIL_PASSWORD'] = gmail_password
                
                # Reinitialize mail with new config
                mail.init_app(app)
                
                # Get migron user
                migron = User.query.filter_by(username='migron').first()
                if not migron:
                    logger.error("❌ User 'migron' not found")
                    return False
                
                logger.info(f"📤 Sending REAL email to {migron.email}...")
                
                msg = Message(
                    subject="🎉 LegislAI Real Email Test - You Should Receive This!",
                    recipients=[migron.email],
                    body=f"""
Hello {migron.get_full_name()},

🎉 SUCCESS! This email was sent using real email delivery (Gmail SMTP).

If you're reading this, it means:
✅ The LegislAI notification system is working
✅ Real email delivery is properly configured
✅ You will receive actual notifications for bills matching your interests

Your current policy subscriptions:
• Communications and Technology (Interest: Very High)
• Budget and Fiscal Policy (Interest: Very High)
• Civil Rights and Liberties (Interest: Very High)
• Criminal Justice and Law Enforcement (Interest: High)
• Native American Affairs (Interest: Medium)

You should now receive real email notifications when relevant bills are analyzed!

Best regards,
LegislAI Development Team

---
This is a real email sent from the LegislAI notification system.
Time sent: {datetime.utcnow()}
                    """,
                    sender=gmail_user
                )
                
                mail.send(msg)
                logger.info("✅ REAL email sent successfully!")
                logger.info(f"📧 Check {migron.email} for the email")
                return True
                
        else:
            logger.warning("⚠️ Gmail credentials not found in environment")
            logger.info("🔧 To set up real email delivery, add these environment variables:")
            logger.info("   export GMAIL_USERNAME=your-email@gmail.com")
            logger.info("   export GMAIL_APP_PASSWORD=your-app-password")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error testing real email delivery: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False

def setup_notification_scheduler_test():
    """Test the notification scheduler for actual email delivery"""
    try:
        from app import app, db
        from services.notification_service import NotificationService
        from db_models import User, Alert
        
        with app.app_context():
            logger.info("📅 Testing notification scheduler for real email delivery...")
            
            # Get migron
            migron = User.query.filter_by(username='migron').first()
            if not migron:
                logger.error("❌ User 'migron' not found")
                return False
            
            # Check if user has unread alerts
            unread_alerts = Alert.query.filter_by(user_id=migron.id, is_read=False).all()
            logger.info(f"📬 User has {len(unread_alerts)} unread alerts")
            
            if unread_alerts:
                logger.info("📤 Testing send_pending_notifications()...")
                
                notification_service = NotificationService()
                notification_service.send_pending_notifications()
                
                logger.info("✅ Notification scheduler test completed")
                logger.info(f"📧 Check {migron.email} for notification digest email")
                return True
            else:
                logger.info("ℹ️ No unread alerts to send")
                return True
                
    except Exception as e:
        logger.error(f"❌ Error testing notification scheduler: {e}")
        return False

def main():
    """Main investigation function"""
    logger.info("🔍 Investigating Email Delivery Issue")
    logger.info("=" * 80)
    
    # Step 1: Investigate current configuration
    email_service = investigate_email_configuration()
    
    logger.info("\n" + "=" * 80)
    
    # Step 2: Handle different email services
    if email_service == 'mailtrap':
        logger.info("📮 REASON: Using Mailtrap (testing service)")
        logger.info("💡 Mailtrap captures emails for testing - they don't reach real inboxes!")
        
        check_mailtrap_inbox()
        
        logger.info("\n" + "=" * 80)
        
        # Step 3: Test real email delivery
        logger.info("🔧 Attempting to set up real email delivery...")
        real_email_success = test_real_email_delivery()
        
        if real_email_success:
            logger.info("\n📅 Testing notification scheduler with real delivery...")
            scheduler_success = setup_notification_scheduler_test()
        
    else:
        logger.info("📧 Email service appears to be configured for real delivery")
        
        # Test the scheduler
        scheduler_success = setup_notification_scheduler_test()
    
    logger.info("\n" + "=" * 80)
    logger.info("📊 INVESTIGATION RESULTS:")
    
    if email_service == 'mailtrap':
        logger.info("   Current setup: 📮 Mailtrap (testing only)")
        logger.info("   Real delivery: 🔧 Needs configuration")
        logger.info("   Action needed: ⚙️ Set up Gmail/SendGrid for production")
    else:
        logger.info("   Current setup: ✅ Real email delivery configured")
        logger.info("   Status: 📧 Should reach user's inbox")
    
    logger.info("\n🎯 NEXT STEPS FOR MIGRON:")
    logger.info("1. Check spam/junk folder in Gmail")
    logger.info("2. If using Mailtrap, check https://mailtrap.io/inboxes")
    logger.info("3. For production, configure real SMTP service")

if __name__ == "__main__":
    import datetime
    main()