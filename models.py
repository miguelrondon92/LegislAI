from app import db
from datetime import datetime
from sqlalchemy import JSON
import json
import logging
import time
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/notification.log'),
        logging.StreamHandler()
    ],
    force=True
)

class PolicyCategory(db.Model):
    """Model for policy categories that users can subscribe to"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    display_name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    color = db.Column(db.String(7), default='#007bff')  # Hex color code
    icon = db.Column(db.String(50))  # Icon class or name
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    user_subscriptions = db.relationship('UserPolicySubscription', backref='policy_category', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<PolicyCategory {self.name}>'

class UserPolicySubscription(db.Model):
    """Model for user subscriptions to policy categories"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    policy_category_id = db.Column(db.Integer, db.ForeignKey('policy_category.id'), nullable=False)
    
    # Subscription preferences
    interest_level = db.Column(db.Float, default=0.5)  # 0.0 to 1.0
    notification_enabled = db.Column(db.Boolean, default=True)
    email_notifications = db.Column(db.Boolean, default=True)
    in_app_notifications = db.Column(db.Boolean, default=True)
    
    # Metadata
    subscribed_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_activity = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Unique constraint to prevent duplicate subscriptions
    __table_args__ = (
        db.UniqueConstraint('user_id', 'policy_category_id', name='uq_user_policy_subscription'),
    )
    
    def __repr__(self):
        return f'<UserPolicySubscription {self.user_id} -> {self.policy_category_id}>'

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

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Profile information
    first_name = db.Column(db.String(50))
    last_name = db.Column(db.String(50))
    organization = db.Column(db.String(100))
    role = db.Column(db.String(100))
    location = db.Column(db.String(100))
    
    # User policy preferences stored as JSON (legacy, use subscriptions instead)
    policy_preferences = db.Column(db.Text, default='{}')
    
    # Alert preferences
    alert_frequency = db.Column(db.String(20), default='weekly')  # daily, weekly, monthly
    alert_enabled = db.Column(db.Boolean, default=True)
    
    # Account status
    is_active = db.Column(db.Boolean, default=True)
    email_verified = db.Column(db.Boolean, default=False)
    verification_token = db.Column(db.String(100))
    
    # Relationships
    alerts = db.relationship('Alert', backref='user', lazy=True, cascade='all, delete-orphan')
    watchlists = db.relationship('WatchlistItem', backref='user', lazy=True, cascade='all, delete-orphan')
    alignment_scores = db.relationship('UserBillAlignment', backref='user', lazy=True, cascade='all, delete-orphan')
    policy_subscriptions = db.relationship('UserPolicySubscription', backref='user', lazy=True, cascade='all, delete-orphan')
    
    def set_password(self, password):
        """Set password hash"""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Check password against hash"""
        return check_password_hash(self.password_hash, password)
    
    def get_full_name(self):
        """Get user's full name"""
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.username
    
    def get_policy_preferences(self):
        """Get policy preferences as dictionary (legacy method)"""
        try:
            return json.loads(self.policy_preferences) if self.policy_preferences else {}
        except:
            return {}
    
    def set_policy_preferences(self, preferences):
        """Set policy preferences from dictionary (legacy method)"""
        self.policy_preferences = json.dumps(preferences)
    
    def get_subscribed_categories(self):
        """Get list of subscribed policy categories"""
        return [sub.policy_category for sub in self.policy_subscriptions if sub.notification_enabled]
    
    def get_category_interest_level(self, category_id):
        """Get user's interest level for a specific category"""
        subscription = UserPolicySubscription.query.filter_by(
            user_id=self.id, 
            policy_category_id=category_id
        ).first()
        return subscription.interest_level if subscription else 0.0
    
    def subscribe_to_category(self, category_id, interest_level=0.5, notifications=True):
        """Subscribe to a policy category"""
        existing = UserPolicySubscription.query.filter_by(
            user_id=self.id,
            policy_category_id=category_id
        ).first()
        
        if existing:
            existing.interest_level = interest_level
            existing.notification_enabled = notifications
            existing.last_activity = datetime.utcnow()
        else:
            subscription = UserPolicySubscription(
                user_id=self.id,
                policy_category_id=category_id,
                interest_level=interest_level,
                notification_enabled=notifications
            )
            db.session.add(subscription)
    
    def unsubscribe_from_category(self, category_id):
        """Unsubscribe from a policy category"""
        subscription = UserPolicySubscription.query.filter_by(
            user_id=self.id,
            policy_category_id=category_id
        ).first()
        
        if subscription:
            db.session.delete(subscription)
    
    def is_subscribed_to_category(self, category_id):
        """Check if user is subscribed to a category"""
        return UserPolicySubscription.query.filter_by(
            user_id=self.id,
            policy_category_id=category_id,
            notification_enabled=True
        ).first() is not None

class Bill(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    congress = db.Column(db.Integer, nullable=False)
    bill_type = db.Column(db.String(10), nullable=False)  # hr, s, hjres, sjres, etc.
    bill_number = db.Column(db.Integer, nullable=False)
    title = db.Column(db.Text)
    summary = db.Column(db.Text)
    
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
    actions = db.relationship('BillAction', backref='bill', lazy=True, cascade='all, delete-orphan', order_by='BillAction.action_date.desc()')
    
    # Unique constraint to ensure bills are unique by congress, bill_type, and bill_number
    __table_args__ = (
        db.UniqueConstraint('congress', 'bill_type', 'bill_number', name='uq_bill_congress_type_number'),
    )
    
    def get_bill_identifier(self):
        """Get standard bill identifier like HR-1234"""
        return f"{self.bill_type.upper()}-{self.bill_number}"
    
    def get_full_text(self):
        """Fetch full text from Congress API when needed"""
        if not self.congress_api_url:
            return None
        
        try:
            from services.congress_api import CongressAPI
            congress_api = CongressAPI()
            bill_data = congress_api.get_bill_details(self.congress, self.bill_type, self.bill_number)
            if bill_data and 'full_text' in bill_data:
                return bill_data['full_text']
        except Exception as e:
            logging.error(f"Error fetching full text for bill {self.get_bill_identifier()}: {str(e)}")
        
        return None
    
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

class BillAction(db.Model):
    """Model for storing bill actions with timestamps and descriptions"""
    id = db.Column(db.Integer, primary_key=True)
    bill_id = db.Column(db.Integer, db.ForeignKey('bill.id'), nullable=False)
    
    # Action details
    action_date = db.Column(db.DateTime, nullable=False)
    action_type = db.Column(db.String(100), nullable=False)  # e.g., 'introduced', 'referred', 'passed', 'enacted'
    action_text = db.Column(db.Text, nullable=False)  # The actual action text from Congress API
    action_description = db.Column(db.Text, nullable=True)  # Human-readable description
    
    # Source information
    source_system = db.Column(db.String(100), nullable=True)  # e.g., 'congress_api', 'manual'
    source_system_name = db.Column(db.String(100), nullable=True)  # e.g., 'Congress.gov', 'House Clerk'
    
    # Metadata
    recorded_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    def __repr__(self):
        return f'<BillAction {self.action_type} on {self.action_date}>'
    
    def get_formatted_date(self):
        """Get formatted action date"""
        return self.action_date.strftime('%B %d, %Y') if self.action_date else ''
    
    def get_action_summary(self):
        """Get a brief summary of the action"""
        if self.action_description:
            return self.action_description
        return self.action_text[:100] + "..." if len(self.action_text) > 100 else self.action_text

class BillCategoryMapping(db.Model):
    """Model for mapping bills to policy categories with AI analysis and relevance scores"""
    id = db.Column(db.Integer, primary_key=True)
    bill_id = db.Column(db.Integer, db.ForeignKey('bill.id'), nullable=False)
    policy_category_id = db.Column(db.Integer, db.ForeignKey('policy_category.id'), nullable=False)
    
    # AI analysis specific to this policy category
    category_specific_analysis = db.Column(db.Text)  # JSON stored as text
    
    # Relevance score (0.0 to 1.0) indicating how much this category pertains to the bill
    relevance_score = db.Column(db.Float, nullable=False, default=0.0)
    
    # Section reference (optional)
    section_reference = db.Column(db.String(200), nullable=True)  # e.g., 'Section 101', 'Title II', etc.
    
    # Analysis metadata
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    bill = db.relationship('Bill', backref='category_mappings', lazy=True)
    policy_category = db.relationship('PolicyCategory', backref='bill_mappings', lazy=True)
    
    # Unique constraint to prevent duplicate mappings
    __table_args__ = (
        db.UniqueConstraint('bill_id', 'policy_category_id', name='uq_bill_category_mapping'),
    )
    
    def get_category_analysis(self):
        """Get category-specific analysis as dictionary"""
        try:
            return json.loads(self.category_specific_analysis) if self.category_specific_analysis else {}
        except:
            return {}
    
    def set_category_analysis(self, analysis):
        """Set category-specific analysis from dictionary"""
        self.category_specific_analysis = json.dumps(analysis)
    
    def __repr__(self):
        return f'<BillCategoryMapping {self.bill_id} -> {self.policy_category_id} (score: {self.relevance_score})>'

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
