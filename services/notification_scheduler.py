import schedule
import time
import threading
import logging
import os
from .notification_service import NotificationService
from app import app

logger = logging.getLogger(__name__)

class NotificationScheduler:
    """Scheduler for sending notifications based on user preferences"""
    
    def __init__(self):
        self.notification_service = NotificationService()
        self.scheduler_thread = None
        self.is_running = False
        self.notifications_enabled = self._should_enable_notifications()
    
    def _should_enable_notifications(self):
        """Check if notifications should be enabled based on environment"""
        flask_env = os.environ.get('FLASK_ENV', 'production').lower()
        notifications_enabled = os.environ.get('NOTIFICATIONS_ENABLED', 'false').lower() == 'true'
        
        # Enable notifications in development or if explicitly enabled
        if flask_env == 'development':
            return True
        elif notifications_enabled:
            return True
        else:
            logger.info("Notification scheduler disabled in production environment")
            return False

    def start(self):
        """Start the notification scheduler"""
        if not self.notifications_enabled:
            logger.info("Notification scheduler start skipped - notifications disabled")
            return
            
        if self.is_running:
            logger.warning("Notification scheduler is already running")
            return

        self.is_running = True
        self.scheduler_thread = threading.Thread(target=self._run_scheduler)
        self.scheduler_thread.daemon = True
        self.scheduler_thread.start()
        logger.info("Notification scheduler started")

    def stop(self):
        """Stop the notification scheduler"""
        if not self.is_running:
            return

        self.is_running = False
        if self.scheduler_thread and threading.current_thread() != self.scheduler_thread:
            self.scheduler_thread.join()
        logger.info("Notification scheduler stopped")

    def _run_scheduler(self):
        """Run the scheduler loop"""
        # Schedule daily notification check
        schedule.every().day.at("09:00").do(self._send_notifications)
        
        # Run immediately on startup
        self._send_notifications()
        
        while self.is_running:
            schedule.run_pending()
            time.sleep(60)  # Check every minute

    def _send_notifications(self):
        """Send pending notifications"""
        try:
            logger.info("Starting notification delivery")
            with app.app_context():
                self.notification_service.send_pending_notifications()
            logger.info("Completed notification delivery")
        except Exception as e:
            logger.error(f"Error sending notifications: {str(e)}")

# Create a singleton instance
notification_scheduler = NotificationScheduler()

def start_notification_scheduler():
    """Start the notification scheduler"""
    notification_scheduler.start()

def stop_notification_scheduler():
    """Stop the notification scheduler"""
    notification_scheduler.stop() 