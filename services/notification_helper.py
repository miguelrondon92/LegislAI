"""
Notification helper to avoid circular import issues.
This module provides a simple interface for triggering notifications
without requiring direct imports of the NotificationService.
"""
import logging
from typing import Optional
import threading

logger = logging.getLogger(__name__)

def trigger_bill_analysis_notification(bill_id: int) -> None:
    """
    Trigger notification for a newly analyzed bill.
    This function avoids circular imports by delaying the import
    until the function is called.
    
    Args:
        bill_id: The ID of the bill that was just analyzed
    """
    try:
        # Import here to avoid circular imports
        from services.notification_service import NotificationService
        
        # Create notification service instance
        notification_service = NotificationService()
        
        # Process notifications for the bill
        notification_service.process_new_bill_analysis(bill_id)
        
        logger.info(f"Triggered notifications for bill ID: {bill_id}")
        
    except Exception as e:
        logger.error(f"Error triggering notifications for bill {bill_id}: {str(e)}")
        # Don't raise the exception as this shouldn't break the main analysis flow

def trigger_bill_analysis_notification_async(bill_id: int) -> None:
    """
    Trigger notification for a newly analyzed bill asynchronously.
    This runs in a separate thread to avoid blocking the main analysis process.
    
    Args:
        bill_id: The ID of the bill that was just analyzed
    """
    def _async_notification():
        trigger_bill_analysis_notification(bill_id)
    
    try:
        # Run notification in a separate thread
        thread = threading.Thread(
            target=_async_notification,
            name=f"NotificationThread-Bill-{bill_id}"
        )
        thread.daemon = True  # Don't prevent program exit
        thread.start()
        
        logger.info(f"Started async notification thread for bill ID: {bill_id}")
        
    except Exception as e:
        logger.error(f"Error starting async notification for bill {bill_id}: {str(e)}")
        # Fallback to synchronous notification
        trigger_bill_analysis_notification(bill_id)

def trigger_high_risk_bill_notification(bill_id: int, risk_score: float) -> None:
    """
    Trigger special notification for high-risk bills with hidden provisions.
    
    Args:
        bill_id: The ID of the bill that was analyzed
        risk_score: The overall risk score of the bill
    """
    try:
        # Import here to avoid circular imports
        from services.notification_service import NotificationService
        from db_models import Bill, Alert, User
        
        # Only notify for truly high-risk bills
        if risk_score < 0.7:
            return
            
        # Get the bill
        bill = Bill.query.get(bill_id)
        if not bill:
            logger.warning(f"Bill {bill_id} not found for high-risk notification")
            return
        
        # Get all users with alert enabled
        users = User.query.filter_by(alert_enabled=True).all()
        
        notification_service = NotificationService()
        
        for user in users:
            # Create high-priority alert for high-risk bills
            if notification_service._should_notify_user(user, bill):
                # Create special high-risk alert
                alert = Alert(
                    user_id=user.id,
                    bill_id=bill.id,
                    alert_type='high_risk_bill',
                    title=f"🚨 HIGH RISK: {bill.get_bill_identifier()}",
                    message=f"This bill has a high risk score ({risk_score:.2f}) with potentially concerning hidden provisions. Review recommended.",
                    priority='high'
                )
                
                from app import db
                db.session.add(alert)
        
        from app import db
        db.session.commit()
        
        logger.info(f"Triggered high-risk notifications for bill {bill_id} (risk: {risk_score:.2f})")
        
    except Exception as e:
        logger.error(f"Error triggering high-risk notifications for bill {bill_id}: {str(e)}")