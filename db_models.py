from app import db
from datetime import datetime
from sqlalchemy import JSON
import json
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin

class PolicyCategory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    display_name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    color = db.Column(db.String(7), default='#007bff')
    icon = db.Column(db.String(50))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_subscriptions = db.relationship('UserPolicySubscription', backref='policy_category', lazy=True, cascade='all, delete-orphan')
    def __repr__(self):
        return f'<PolicyCategory {self.name}>'

class UserPolicySubscription(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    policy_category_id = db.Column(db.Integer, db.ForeignKey('policy_category.id'), nullable=False)
    interest_level = db.Column(db.Float, default=0.5)
    notification_enabled = db.Column(db.Boolean, default=True)
    email_notifications = db.Column(db.Boolean, default=True)
    in_app_notifications = db.Column(db.Boolean, default=True)
    subscribed_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_activity = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (
        db.UniqueConstraint('user_id', 'policy_category_id', name='uq_user_policy_subscription'),
    )
    def __repr__(self):
        return f'<UserPolicySubscription {self.user_id} -> {self.policy_category_id}>'

class UserBillAlignment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    bill_id = db.Column(db.Integer, db.ForeignKey('bill.id'), nullable=False)
    overall_score = db.Column(db.Float)
    policy_score = db.Column(db.Float)
    impact_score = db.Column(db.Float)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    analysis_details = db.Column(db.Text)
    def get_analysis_details(self):
        try:
            return json.loads(self.analysis_details) if self.analysis_details else {}
        except:
            return {}
    def set_analysis_details(self, details):
        self.analysis_details = json.dumps(details)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    first_name = db.Column(db.String(50))
    last_name = db.Column(db.String(50))
    organization = db.Column(db.String(100))
    role = db.Column(db.String(100))
    location = db.Column(db.String(100))
    policy_preferences = db.Column(db.Text, default='{}')
    alert_frequency = db.Column(db.String(20), default='weekly')
    alert_enabled = db.Column(db.Boolean, default=True)
    is_active = db.Column(db.Boolean, default=True)
    email_verified = db.Column(db.Boolean, default=False)
    verification_token = db.Column(db.String(100))
    alerts = db.relationship('Alert', backref='user', lazy=True, cascade='all, delete-orphan')
    watchlists = db.relationship('WatchlistItem', backref='user', lazy=True, cascade='all, delete-orphan')
    alignment_scores = db.relationship('UserBillAlignment', backref='user', lazy=True, cascade='all, delete-orphan')
    policy_subscriptions = db.relationship('UserPolicySubscription', backref='user', lazy=True, cascade='all, delete-orphan')
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    def get_full_name(self):
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.username
    def get_policy_preferences(self):
        try:
            return json.loads(self.policy_preferences) if self.policy_preferences else {}
        except:
            return {}
    def set_policy_preferences(self, preferences):
        self.policy_preferences = json.dumps(preferences)
    def get_subscribed_categories(self):
        return [sub.policy_category for sub in self.policy_subscriptions if sub.notification_enabled]
    def get_category_interest_level(self, category_id):
        subscription = UserPolicySubscription.query.filter_by(
            user_id=self.id, 
            policy_category_id=category_id
        ).first()
        return subscription.interest_level if subscription else 0.0
    def subscribe_to_category(self, category_id, interest_level=0.5, notifications=True):
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
        subscription = UserPolicySubscription.query.filter_by(
            user_id=self.id,
            policy_category_id=category_id
        ).first()
        if subscription:
            db.session.delete(subscription)
    def is_subscribed_to_category(self, category_id):
        return UserPolicySubscription.query.filter_by(
            user_id=self.id,
            policy_category_id=category_id,
            notification_enabled=True
        ).first() is not None

class Bill(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    congress = db.Column(db.Integer, nullable=False)
    bill_type = db.Column(db.String(10), nullable=False)
    bill_number = db.Column(db.Integer, nullable=False)
    title = db.Column(db.Text)
    summary = db.Column(db.Text)
    introduced_date = db.Column(db.DateTime)
    last_action_date = db.Column(db.DateTime)
    status = db.Column(db.String(50))
    sponsor_name = db.Column(db.String(100))
    sponsor_party = db.Column(db.String(20))
    sponsor_state = db.Column(db.String(5))
    congress_api_url = db.Column(db.String(200))
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)
    ai_analysis = db.Column(db.Text)
    policy_categories = db.Column(db.Text)
    stakeholder_analysis = db.Column(db.Text)
    complexity_score = db.Column(db.Float)
    version = db.Column(db.Integer, nullable=False, default=1)
    active = db.Column(db.Boolean, nullable=False, default=True)
    alerts = db.relationship('Alert', backref='bill', lazy=True)
    watchlists = db.relationship('WatchlistItem', backref='bill', lazy=True)
    user_alignments = db.relationship('UserBillAlignment', backref='bill', lazy=True, cascade='all, delete-orphan')
    actions = db.relationship('BillAction', backref='bill', lazy=True, cascade='all, delete-orphan', order_by='BillAction.action_date.desc()')
    def get_bill_identifier(self):
        return f"{self.congress}-{self.bill_type.upper()}{self.bill_number}"
    def get_full_text(self):
        """Get full text from Congress API (not stored in database)"""
        # This method is kept for compatibility but should not be used
        # The workflow orchestrator now fetches text directly from Congress API
        return self.summary or ''
    def get_ai_analysis(self):
        try:
            return json.loads(self.ai_analysis) if self.ai_analysis else None
        except:
            return None
    def set_ai_analysis(self, analysis):
        self.ai_analysis = json.dumps(analysis)
    def get_policy_categories(self):
        try:
            return json.loads(self.policy_categories) if self.policy_categories else []
        except:
            return []
    def set_policy_categories(self, categories):
        self.policy_categories = json.dumps(categories)

class Alert(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    bill_id = db.Column(db.Integer, db.ForeignKey('bill.id'), nullable=False)
    alert_type = db.Column(db.String(50), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text)
    alignment_score = db.Column(db.Float)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_read = db.Column(db.Boolean, default=False)
    priority = db.Column(db.String(20), default='medium')

class WatchlistItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    bill_id = db.Column(db.Integer, db.ForeignKey('bill.id'), nullable=False)
    keywords = db.Column(db.String(200))
    policy_area = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_checked = db.Column(db.DateTime, default=datetime.utcnow)

class BillAction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    bill_id = db.Column(db.Integer, db.ForeignKey('bill.id'), nullable=False)
    action_date = db.Column(db.DateTime, nullable=False)
    action_type = db.Column(db.String(100), nullable=False)
    action_text = db.Column(db.Text, nullable=False)
    action_description = db.Column(db.Text, nullable=True)
    source_system = db.Column(db.String(100), nullable=True)
    source_system_name = db.Column(db.String(100), nullable=True)
    recorded_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    def get_formatted_date(self):
        """Return formatted date for display"""
        if self.action_date:
            return self.action_date.strftime('%B %d, %Y')
        return 'Unknown Date'
    
    def get_short_date(self):
        """Return short formatted date"""
        if self.action_date:
            return self.action_date.strftime('%m/%d/%Y')
        return 'Unknown'
    
    def get_action_icon(self):
        """Return appropriate icon for action type"""
        action_icons = {
            'introduced': 'file-plus',
            'referred': 'arrow-right',
            'reported': 'check-circle',
            'passed': 'thumbs-up',
            'failed': 'thumbs-down',
            'enacted': 'award',
            'signed': 'pen-tool',
            'vetoed': 'x-circle',
            'committee': 'users',
            'floor': 'home',
            'amendment': 'edit-3',
            'vote': 'check-square'
        }
        
        action_type_lower = self.action_type.lower()
        for key, icon in action_icons.items():
            if key in action_type_lower:
                return icon
        return 'clock'  # default icon
    
    def get_action_color(self):
        """Return appropriate color class for action type"""
        action_type_lower = self.action_type.lower()
        
        if any(word in action_type_lower for word in ['passed', 'enacted', 'signed', 'approved']):
            return 'success'
        elif any(word in action_type_lower for word in ['failed', 'rejected', 'vetoed']):
            return 'danger'
        elif any(word in action_type_lower for word in ['referred', 'committee', 'reported']):
            return 'info'
        elif any(word in action_type_lower for word in ['introduced', 'amendment']):
            return 'primary'
        else:
            return 'secondary'
    
    def __repr__(self):
        return f'<BillAction {self.action_type} on {self.action_date}>'

class BillCategoryMapping(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    bill_id = db.Column(db.Integer, db.ForeignKey('bill.id'), nullable=False)
    policy_category_id = db.Column(db.Integer, db.ForeignKey('policy_category.id'), nullable=False)
    category_specific_analysis = db.Column(db.Text)
    relevance_score = db.Column(db.Float, nullable=False, default=0.0)
    sneakiness_score = db.Column(db.Float, nullable=False, default=0.0)
    section_reference = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    bill = db.relationship('Bill', backref='category_mappings', lazy=True)
    policy_category = db.relationship('PolicyCategory', backref='bill_mappings', lazy=True)
    __table_args__ = (
        db.UniqueConstraint('bill_id', 'policy_category_id', name='uq_bill_category_mapping'),
    )
    def get_category_analysis(self):
        try:
            return json.loads(self.category_specific_analysis) if self.category_specific_analysis else {}
        except:
            return {}
    def set_category_analysis(self, analysis):
        self.category_specific_analysis = json.dumps(analysis)
    def __repr__(self):
        return f'<BillCategoryMapping {self.bill_id} -> {self.policy_category_id}>' 