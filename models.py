from app import db
from datetime import datetime
from sqlalchemy import JSON
import json
import logging
import time

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/notification.log'),
        logging.StreamHandler()
    ],
    force=True
)

class UserBillAlignment(db.Model):
    """Model for storing user-bill alignment scores"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    bill_id = db.Column(db.Integer, db.ForeignKey('bill.id'), nullable=False)
    
    # Alignment scores
    overall_score = db.Column(db.Float)
    policy_score = db.Column(db.Float)
    impact_score = db.Column(db.Float)
    
    # Analysis metadata
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Additional analysis data stored as JSON
    analysis_details = db.Column(db.Text)
    
    def get_analysis_details(self):
        """Get analysis details as dictionary"""
        try:
            return json.loads(self.analysis_details) if self.analysis_details else {}
        except:
            return {}
    
    def set_analysis_details(self, details):
        """Set analysis details from dictionary"""
        self.analysis_details = json.dumps(details)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # User policy preferences stored as JSON
    policy_preferences = db.Column(db.Text, default='{}')
    
    # Alert preferences
    alert_frequency = db.Column(db.String(20), default='weekly')  # daily, weekly, monthly
    alert_enabled = db.Column(db.Boolean, default=True)
    
    # Relationships
    alerts = db.relationship('Alert', backref='user', lazy=True, cascade='all, delete-orphan')
    watchlists = db.relationship('WatchlistItem', backref='user', lazy=True, cascade='all, delete-orphan')
    alignment_scores = db.relationship('UserBillAlignment', backref='user', lazy=True, cascade='all, delete-orphan')
    
    def get_policy_preferences(self):
        """Get policy preferences as dictionary"""
        try:
            return json.loads(self.policy_preferences) if self.policy_preferences else {}
        except:
            return {}
    
    def set_policy_preferences(self, preferences):
        """Set policy preferences from dictionary"""
        self.policy_preferences = json.dumps(preferences)

class Bill(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    congress = db.Column(db.Integer, nullable=False)
    bill_type = db.Column(db.String(10), nullable=False)  # hr, s, hjres, sjres, etc.
    bill_number = db.Column(db.Integer, nullable=False)
    title = db.Column(db.Text)
    summary = db.Column(db.Text)
    full_text = db.Column(db.Text)
    
    # Bill metadata
    introduced_date = db.Column(db.DateTime)
    last_action_date = db.Column(db.DateTime)
    status = db.Column(db.String(50))
    sponsor_name = db.Column(db.String(100))
    sponsor_party = db.Column(db.String(20))
    sponsor_state = db.Column(db.String(5))
    
    # Congress API data
    congress_api_url = db.Column(db.String(200))
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Analysis results stored as JSON
    ai_analysis = db.Column(db.Text)
    policy_categories = db.Column(db.Text)
    stakeholder_analysis = db.Column(db.Text)
    complexity_score = db.Column(db.Float)
    
    # Relationships
    alerts = db.relationship('Alert', backref='bill', lazy=True)
    watchlists = db.relationship('WatchlistItem', backref='bill', lazy=True)
    user_alignments = db.relationship('UserBillAlignment', backref='bill', lazy=True, cascade='all, delete-orphan')
    
    # Unique constraint to ensure bills are unique by congress, bill_type, and bill_number
    __table_args__ = (
        db.UniqueConstraint('congress', 'bill_type', 'bill_number', name='uq_bill_congress_type_number'),
    )
    
    def get_bill_identifier(self):
        """Get standard bill identifier like HR-1234"""
        return f"{self.bill_type.upper()}-{self.bill_number}"
    
    def get_ai_analysis(self):
        """Get AI analysis as dictionary"""
        try:
            return json.loads(self.ai_analysis) if self.ai_analysis else {}
        except:
            return {}
    
    def set_ai_analysis(self, analysis):
        """Set AI analysis from dictionary"""
        self.ai_analysis = json.dumps(analysis)
    
    def get_policy_categories(self):
        """Get policy categories as dictionary"""
        try:
            return json.loads(self.policy_categories) if self.policy_categories else {}
        except:
            return {}
    
    def set_policy_categories(self, categories):
        """Set policy categories from dictionary"""
        self.policy_categories = json.dumps(categories)

class Alert(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    bill_id = db.Column(db.Integer, db.ForeignKey('bill.id'), nullable=False)
    
    alert_type = db.Column(db.String(50), nullable=False)  # 'alignment', 'conflict', 'new_bill', 'status_change'
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text)
    alignment_score = db.Column(db.Float)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_read = db.Column(db.Boolean, default=False)
    priority = db.Column(db.String(20), default='medium')  # low, medium, high, critical

class WatchlistItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    bill_id = db.Column(db.Integer, db.ForeignKey('bill.id'), nullable=False)
    
    # Search criteria that created this watchlist item
    keywords = db.Column(db.String(200))
    policy_area = db.Column(db.String(50))
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_checked = db.Column(db.DateTime, default=datetime.utcnow)

def create_test_data():
    """Create test user and bill data"""
    # Create test user with unique email
    timestamp = int(time.time())
    test_user = User(
        username=f"test_user_{timestamp}",
        email=f"test_{timestamp}@example.com",
        alert_enabled=True,
        alert_frequency="daily"
    )
    db.session.add(test_user)
    db.session.commit()

    # Rest of the function remains the same...
