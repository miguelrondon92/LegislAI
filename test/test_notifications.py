from app import app, db, mail
from db_models import User, Bill, Alert
from services.notification_service import NotificationService
from services.notification_scheduler import NotificationScheduler
from datetime import datetime
import time
import logging
from flask_mail import Message
import os

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/notification_test.log'),
        logging.StreamHandler()
    ],
    force=True  # Ensure this overrides previous logging configs
)
logger = logging.getLogger(__name__)

def create_test_data():
    """Create test user and bill data"""
    try:
        # Create test user with unique identifier
        timestamp = int(time.time())
        test_user = User(
            username=f"test_user_{timestamp}",
            email=f"test_{timestamp}@example.com",
            alert_enabled=True,
            alert_frequency="daily"
        )
        db.session.add(test_user)
        db.session.commit()
        logger.info(f"Created test user: {test_user.username} with email: {test_user.email}")

        # Create test bill
        test_bill = Bill(
            congress=118,
            bill_type="hjres",
            bill_number=87,
            title="Disapproving the rule submitted by the Environmental Protection Agency relating to 'Control of Air Pollution from New Motor Vehicles: Heavy-Duty Engine and Vehicle Standards'",
            summary="A bill to disapprove of the EPA rule allowing California to set stricter pollution standards for heavy-duty vehicles.",
            introduced_date=datetime.utcnow(),
            last_action_date=datetime.utcnow(),
            status="Introduced",
            sponsor_name="Test Sponsor",
            sponsor_party="R",
            sponsor_state="CA"
        )
        db.session.add(test_bill)
        db.session.commit()
        logger.info(f"Created test bill: {test_bill.get_bill_identifier()}")

        # Set AI analysis
        analysis = {
            "key_points": [
                "Congress is attempting to block EPA's rule allowing California to set stricter pollution standards for heavy-duty vehicles",
                "The bill would prevent California from implementing its own emissions standards",
                "This could impact vehicle manufacturers, the environment, and public health"
            ],
            "impact_analysis": "This bill could lead to less stringent pollution controls and create uncertainty for vehicle manufacturers. It may also set a precedent for Congress to block other EPA regulations in the future.",
            "stakeholders": {
                "winners": ["Vehicle Manufacturers"],
                "losers": ["California", "Environment", "Public Health"],
                "impacts": {
                    "Vehicle Manufacturers": "May face less stringent requirements",
                    "California": "Cannot implement stricter standards",
                    "Environment": "Could see increased pollution"
                }
            }
        }
        test_bill.set_ai_analysis(analysis)
        db.session.commit()
        logger.info("Set AI analysis for test bill")

        # Create a dummy bill for development notification
        dummy_bill = Bill(
            congress=999,
            bill_type="test",
            bill_number=1,
            title="Dummy Bill for Notification Testing",
            summary="This is a dummy bill used for development notification testing.",
            introduced_date=datetime.utcnow(),
            last_action_date=datetime.utcnow(),
            status="Testing",
            sponsor_name="Dev Tester",
            sponsor_party="N",
            sponsor_state="NA"
        )
        db.session.add(dummy_bill)
        db.session.commit()
        logger.info(f"Created dummy bill for test notification: {dummy_bill.get_bill_identifier()}")

        # Create a test alert for the test user with a simple string message, using the actual test_bill
        test_alert = Alert(
            user_id=test_user.id,
            bill_id=test_bill.id,
            alert_type="test",
            title="Test Notification",
            message="This is a test notification message for development purposes.",
            priority="low"
        )
        db.session.add(test_alert)
        db.session.commit()
        logger.info(f"Created test alert for user {test_user.email} with actual bill {test_bill.get_bill_identifier()}")

        return test_user, test_bill

    except Exception as e:
        logger.error(f"Error creating test data: {str(e)}")
        db.session.rollback()
        raise

def test_notification():
    """Test the notification system using the NotificationScheduler"""
    try:
        with app.app_context():
            # Create test data
            test_user, test_bill = create_test_data()
            logger.info(f"Created test data - User: {test_user.username}, Bill: {test_bill.get_bill_identifier()}")

            # Use the NotificationScheduler to send notifications
            scheduler = NotificationScheduler()
            logger.info("Triggering NotificationScheduler to send notifications...")
            scheduler._send_notifications()  # Directly call the method for testing
            logger.info("NotificationScheduler sent notifications.")

            print("Test completed! Check notification_test.log for details.")

    except Exception as e:
        logger.error(f"Error in test_notification: {str(e)}")
        raise

def send_simple_test_email():
    """Send a simple test email to verify mail delivery with ai_summary.txt content."""
    with app.app_context():
        test_recipient = os.environ.get('TEST_EMAIL', 'your@email.com')
        # Read the summary from ai_summary.txt
        try:
            with open('ai_summary.txt', 'r') as f:
                summary_text = f.read()
        except Exception as e:
            logger.error(f"Failed to read ai_summary.txt: {str(e)}")
            summary_text = "[Could not read ai_summary.txt]"
        msg = Message(
            subject="LegislAI Test Email: AI Summary",
            recipients=[test_recipient],
            body=summary_text,
            sender=os.environ.get('MAIL_DEFAULT_SENDER', 'noreply@legislai.com')
        )
        logger.info(f"Sending simple test email to: {test_recipient}")
        try:
            mail.send(msg)
            logger.info("Simple test email sent successfully.")
            print("Simple test email sent successfully.")
        except Exception as e:
            logger.error(f"Failed to send simple test email: {str(e)}")
            print(f"Failed to send simple test email: {str(e)}")

if __name__ == "__main__":
    test_notification()
    send_simple_test_email() 