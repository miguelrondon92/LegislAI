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
    
    # New methods for AIAnalysis and Summary relationships
    def get_active_ai_analysis(self):
        """Get the active AI analysis for this bill"""
        return AIAnalysis.get_active_for_bill(self.id)
    
    def get_active_summary(self):
        """Get the active summary for this bill"""
        return Summary.get_active_for_bill(self.id)
    
    def get_ai_analysis_new(self):
        """New method to get AI analysis from AIAnalysis table"""
        analysis = self.get_active_ai_analysis()
        return analysis.get_analysis_data() if analysis else None
    
    def get_complexity_score_new(self):
        """Get complexity score from AIAnalysis table (0-1 scale for template compatibility)"""
        analysis = self.get_active_ai_analysis()
        if analysis:
            # First try to get from analysis_data JSON (which has 0-100 scale)
            analysis_data = analysis.get_analysis_data()
            if analysis_data and 'complexity_assessment' in analysis_data:
                complexity_data = analysis_data['complexity_assessment']
                if 'complexity_score' in complexity_data:
                    # Convert from 0-100 scale to 0-1 scale for template compatibility
                    return complexity_data['complexity_score'] / 100.0
            
            # Fallback to complexity_score field (already 0-1 scale)
            return analysis.complexity_score
        return None
    
    def get_controversy_score_new(self):
        """Get controversy score from AIAnalysis table"""
        analysis = self.get_active_ai_analysis()
        return analysis.controversy_score if analysis else None
    
    def get_summary_text(self):
        """Get summary text from Summary table"""
        summary = self.get_active_summary()
        return summary.summary_text if summary else self.summary  # Fallback to old field
    
    def get_plain_language_summary(self):
        """Get plain language summary from Summary table"""
        summary = self.get_active_summary()
        return summary.plain_language_summary if summary else None
    
    def get_key_provisions_new(self):
        """Get key provisions from Summary table"""
        summary = self.get_active_summary()
        return summary.get_key_provisions() if summary else []
    
    def create_new_analysis_version(self, analysis_data, complexity_score=None, controversy_score=None, 
                                   analysis_method='chunked', chunks_analyzed=None, processing_time=None):
        """Create a new version of AI analysis"""
        # Get the next version number
        latest_analysis = AIAnalysis.query.filter_by(bill_id=self.id).order_by(AIAnalysis.analysis_version.desc()).first()
        next_version = (latest_analysis.analysis_version + 1) if latest_analysis else 1
        
        # Create new analysis
        new_analysis = AIAnalysis(
            bill_id=self.id,
            analysis_version=next_version,
            complexity_score=complexity_score,
            controversy_score=controversy_score,
            analysis_method=analysis_method,
            chunks_analyzed=chunks_analyzed,
            processing_time=processing_time,
            active=True
        )
        new_analysis.set_analysis_data(analysis_data)
        
        # Deactivate previous versions
        AIAnalysis.query.filter_by(bill_id=self.id).update({'active': False})
        
        # Add and commit
        db.session.add(new_analysis)
        db.session.commit()
        
        return new_analysis
    
    def create_new_summary_version(self, summary_text, plain_language_summary=None, 
                                  key_provisions=None, funding_amounts=None, 
                                  implementation_timeline=None, summary_type='ai_generated'):
        """Create a new version of summary"""
        # Get the next version number
        latest_summary = Summary.query.filter_by(bill_id=self.id).order_by(Summary.summary_version.desc()).first()
        next_version = (latest_summary.summary_version + 1) if latest_summary else 1
        
        # Create new summary
        new_summary = Summary(
            bill_id=self.id,
            summary_version=next_version,
            summary_text=summary_text,
            plain_language_summary=plain_language_summary,
            funding_amounts=funding_amounts,
            implementation_timeline=implementation_timeline,
            summary_type=summary_type,
            active=True
        )
        
        if key_provisions:
            new_summary.set_key_provisions(key_provisions)
        
        # Deactivate previous versions
        Summary.query.filter_by(bill_id=self.id).update({'active': False})
        
        # Add and commit
        db.session.add(new_summary)
        db.session.commit()
        
        return new_summary

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

class AIAnalysis(db.Model):
    """AI analysis results for bills with versioning support"""
    id = db.Column(db.Integer, primary_key=True)
    bill_id = db.Column(db.Integer, db.ForeignKey('bill.id'), nullable=False)
    
    # Analysis data and results
    analysis_data = db.Column(db.Text)  # JSON stored analysis results
    complexity_score = db.Column(db.Float)  # Moved from Bill table
    controversy_score = db.Column(db.Float)
    
    # Analysis metadata
    analysis_method = db.Column(db.String(50), default='chunked')  # 'chunked', 'simple', 'enhanced'
    chunks_analyzed = db.Column(db.Integer)
    processing_time = db.Column(db.Float)  # Time in seconds
    
    # Versioning and status
    analysis_version = db.Column(db.Integer, nullable=False, default=1)
    active = db.Column(db.Boolean, nullable=False, default=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    bill = db.relationship('Bill', backref='ai_analyses', lazy=True)
    
    # Constraints
    __table_args__ = (
        db.UniqueConstraint('bill_id', 'analysis_version', name='uq_bill_analysis_version'),
        db.Index('idx_bill_active_analysis', 'bill_id', 'active'),
    )
    
    def get_analysis_data(self):
        """Get parsed analysis data"""
        try:
            return json.loads(self.analysis_data) if self.analysis_data else {}
        except:
            return {}
    
    def set_analysis_data(self, data):
        """Set analysis data as JSON"""
        self.analysis_data = json.dumps(data)
    
    @classmethod
    def get_active_for_bill(cls, bill_id):
        """Get active analysis for a bill"""
        return cls.query.filter_by(bill_id=bill_id, active=True).first()
    
    def deactivate_other_versions(self):
        """Deactivate other versions for this bill"""
        AIAnalysis.query.filter_by(bill_id=self.bill_id).filter(AIAnalysis.id != self.id).update({'active': False})
        db.session.commit()
    
    def __repr__(self):
        return f'<AIAnalysis {self.bill_id} v{self.analysis_version} active={self.active}>'

class Summary(db.Model):
    """Bill summaries with versioning support"""
    id = db.Column(db.Integer, primary_key=True)
    bill_id = db.Column(db.Integer, db.ForeignKey('bill.id'), nullable=False)
    
    # Summary content
    summary_text = db.Column(db.Text)  # Main summary
    plain_language_summary = db.Column(db.Text)  # Simplified explanation
    key_provisions = db.Column(db.Text)  # JSON list of key provisions
    funding_amounts = db.Column(db.String(500))  # Funding information
    implementation_timeline = db.Column(db.String(500))  # Timeline details
    
    # Summary metadata
    summary_type = db.Column(db.String(50), default='ai_generated')  # 'ai_generated', 'congressional', 'user_submitted'
    
    # Versioning and status
    summary_version = db.Column(db.Integer, nullable=False, default=1)
    active = db.Column(db.Boolean, nullable=False, default=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    bill = db.relationship('Bill', backref='summaries', lazy=True)
    
    # Constraints
    __table_args__ = (
        db.UniqueConstraint('bill_id', 'summary_version', name='uq_bill_summary_version'),
        db.Index('idx_bill_active_summary', 'bill_id', 'active'),
    )
    
    def get_key_provisions(self):
        """Get parsed key provisions"""
        try:
            return json.loads(self.key_provisions) if self.key_provisions else []
        except:
            return []
    
    def set_key_provisions(self, provisions):
        """Set key provisions as JSON"""
        self.key_provisions = json.dumps(provisions)
    
    @classmethod
    def get_active_for_bill(cls, bill_id):
        """Get active summary for a bill"""
        return cls.query.filter_by(bill_id=bill_id, active=True).first()
    
    def deactivate_other_versions(self):
        """Deactivate other versions for this bill"""
        Summary.query.filter_by(bill_id=self.bill_id).filter(Summary.id != self.id).update({'active': False})
        db.session.commit()
    
    def __repr__(self):
        return f'<Summary {self.bill_id} v{self.summary_version} active={self.active}>' 