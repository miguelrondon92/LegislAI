from datetime import datetime
from sqlalchemy import JSON
import json
import logging
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)

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
    status = db.Column(db.String(500))
    sponsor_name = db.Column(db.String(100))
    sponsor_party = db.Column(db.String(20))
    sponsor_state = db.Column(db.String(5))
    congress_api_url = db.Column(db.String(200))
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)
    ai_analysis = db.Column(db.Text)
    policy_categories = db.Column(db.Text)
    stakeholder_analysis = db.Column(db.Text)
    complexity_score = db.Column(db.Float)
    full_text = db.Column(db.Text, nullable=True)
    full_text_fetched_at = db.Column(db.DateTime, nullable=True)
    content_hash = db.Column(db.String(64), nullable=True)
    version = db.Column(db.Integer, nullable=False, default=1)
    active = db.Column(db.Boolean, nullable=False, default=True)
    display_ready = db.Column(db.Boolean, nullable=False, default=False)
    alerts = db.relationship('Alert', backref='bill', lazy=True)
    watchlists = db.relationship('WatchlistItem', backref='bill', lazy=True)
    user_alignments = db.relationship('UserBillAlignment', backref='bill', lazy=True, cascade='all, delete-orphan')
    actions = db.relationship('BillAction', backref='bill', lazy=True, cascade='all, delete-orphan', order_by='BillAction.action_date.desc()')
    def get_bill_identifier(self):
        return f"{self.congress}-{self.bill_type.upper()}{self.bill_number}"

    @staticmethod
    def _congress_ordinal(congress):
        """English ordinal suffix for a congress number (119 → '119th')."""
        n = int(congress)
        if 11 <= (n % 100) <= 13:
            suffix = 'th'
        else:
            suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')
        return f"{n}{suffix}"

    _CONGRESS_GOV_TYPE_SLUGS = {
        'hr': 'house-bill',
        's': 'senate-bill',
        'hjres': 'house-joint-resolution',
        'sjres': 'senate-joint-resolution',
        'hres': 'house-resolution',
        'sres': 'senate-resolution',
        'hconres': 'house-concurrent-resolution',
        'sconres': 'senate-concurrent-resolution',
    }

    def get_congress_gov_url(self):
        """Public congress.gov bill page URL (not the API endpoint)."""
        if self.congress is None or self.bill_number is None or not self.bill_type:
            return None
        slug = self._CONGRESS_GOV_TYPE_SLUGS.get(self.bill_type.lower().strip())
        if not slug:
            return None
        ordinal = self._congress_ordinal(self.congress)
        return (
            f"https://www.congress.gov/bill/{ordinal}-congress/{slug}/{int(self.bill_number)}"
        )

    def get_full_text(self, *, fetch_if_missing=True, persist=True):
        """Return persisted full text, optionally fetching once from Congress and storing it."""
        if self.full_text:
            return self.full_text

        if not fetch_if_missing:
            return self.summary or ''

        try:
            from services.congress_api import get_shared_congress_api

            congress_api = get_shared_congress_api()
            full_text = congress_api.get_bill_text(self.congress, self.bill_type, self.bill_number)

            if full_text:
                logging.info(
                    f"Successfully fetched {len(full_text)} characters for {self.get_bill_identifier()}"
                )
                if persist:
                    self.full_text = full_text
                    self.full_text_fetched_at = datetime.utcnow()
                    try:
                        import hashlib
                        content = (self.title or '') + (self.summary or '') + (full_text or '')
                        self.content_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()
                    except Exception:
                        pass
                    try:
                        db.session.add(self)
                        db.session.commit()
                    except Exception as commit_err:
                        logging.warning(
                            f"Could not persist full text for {self.get_bill_identifier()}: {commit_err}"
                        )
                        db.session.rollback()
                return full_text

            logging.warning(f"No full text available for {self.get_bill_identifier()}, returning summary")
            return self.summary or ''

        except Exception as e:
            logging.error(f"Error fetching full text for {self.get_bill_identifier()}: {e}")
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
        """Get complexity score from AIAnalysis (0-1 scale for template compatibility)."""
        analysis = self.get_active_ai_analysis()
        if not analysis:
            return None

        analysis_data = analysis.get_analysis_data()
        if analysis_data and isinstance(analysis_data.get("complexity_assessment"), dict):
            raw = analysis_data["complexity_assessment"].get("complexity_score")
            if raw is not None:
                try:
                    score = float(raw)
                except (TypeError, ValueError):
                    score = None
                if score is not None:
                    # Analyzer contract is 0.0–1.0; legacy rows may use 0–100
                    if score > 1.0:
                        return score / 100.0
                    return score

        # Fallback to column (already 0-1)
        return analysis.complexity_score
    
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
                                   analysis_method='chunked', chunks_analyzed=None, processing_time=None,
                                   provider_model=None):
        """Create a new version of AI analysis"""
        from utils.constants import GEMINI_MODEL

        # Get the next version number
        latest_analysis = AIAnalysis.query.filter_by(bill_id=self.id).order_by(AIAnalysis.analysis_version.desc()).first()
        next_version = (latest_analysis.analysis_version + 1) if latest_analysis else 1

        model = provider_model
        if not model and isinstance(analysis_data, dict):
            model = analysis_data.get('provider_model') or analysis_data.get('model')
        if not model:
            model = GEMINI_MODEL
        
        # Create new analysis
        new_analysis = AIAnalysis(
            bill_id=self.id,
            analysis_version=next_version,
            complexity_score=complexity_score,
            controversy_score=controversy_score,
            analysis_method=analysis_method,
            chunks_analyzed=chunks_analyzed,
            processing_time=processing_time,
            provider_model=model,
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
                                  implementation_timeline=None, summary_type='ai_generated',
                                  provider_model=None):
        """Create a new version of summary"""
        from utils.constants import GEMINI_MODEL

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
            provider_model=provider_model or GEMINI_MODEL,
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
    
    # Hidden Provisions helper methods
    def get_hidden_provisions(self, risk_level=None):
        """Get hidden provisions for this bill, optionally filtered by risk level"""
        # Import here to avoid circular imports
        query = db.session.query(HiddenProvision).filter_by(bill_id=self.id)
        if risk_level:
            query = query.filter_by(risk_level=risk_level)
        return query.order_by(HiddenProvision.confidence_score.desc()).all()
    
    def get_hidden_provisions_count(self):
        """Get count of hidden provisions by risk level"""
        provisions = db.session.query(HiddenProvision).filter_by(bill_id=self.id).all()
        count = {'low': 0, 'medium': 0, 'high': 0, 'total': len(provisions)}
        for provision in provisions:
            count[provision.risk_level] = count.get(provision.risk_level, 0) + 1
        return count
    
    def has_high_risk_provisions(self):
        """Check if this bill has any high-risk hidden provisions"""
        return db.session.query(HiddenProvision).filter_by(bill_id=self.id, risk_level='high').count() > 0
    
    def get_overall_hidden_risk_score(self):
        """Calculate overall risk score from all hidden provisions"""
        provisions = db.session.query(HiddenProvision).filter_by(bill_id=self.id).all()
        if not provisions:
            return 0.0
        
        total_score = sum(provision.get_risk_score() for provision in provisions)
        return min(total_score / len(provisions), 1.0)  # Normalize to 0-1 scale
    
    def is_analysis_complete(self):
        """Check if bill has complete analysis for display"""
        # Required components for complete analysis:
        # 1. Basic bill data (title, summary)
        # 2. AI Analysis with complexity score
        # 3. Summary data
        # 4. Policy categorization
        
        # Check basic bill data
        if not self.title or not self.summary:
            return False
        
        # Check AI Analysis
        ai_analysis = self.get_active_ai_analysis()
        if not ai_analysis:
            return False
        
        # Check if complexity score exists (not None)
        if ai_analysis.complexity_score is None:
            return False
        
        # Check if summary exists
        summary = self.get_active_summary()
        if not summary or not summary.summary_text:
            return False
        
        # Check policy categorization
        categories = db.session.query(BillCategoryMapping).filter_by(bill_id=self.id).first()
        if not categories:
            return False
        
        return True
    
    def update_display_ready_status(self):
        """Update the display_ready flag based on analysis completeness"""
        old_status = self.display_ready
        new_status = self.is_analysis_complete()
        
        if old_status != new_status:
            self.display_ready = new_status
            db.session.commit()
            return True  # Status changed
        
        return False  # No change

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
    
    def get_formatted_action_type(self):
        """Return properly formatted action type for display"""
        # Dictionary mapping of concatenated action types to properly formatted versions
        action_type_mappings = {
            'BecameLaw': 'Became Law',
            'IntroReferral': 'Intro Referral',
            'NotUsed': 'Not Used',
            'ResolvingDifferences': 'Resolving Differences',
            'Committee': 'Committee',
            'Floor': 'Floor',
            'President': 'President',
            'Calendars': 'Calendars'
        }
        
        # Return mapped value if exists, otherwise apply title() to the original
        return action_type_mappings.get(self.action_type, self.action_type.title())
    
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
    provider_model = db.Column(db.String(80), nullable=True, index=True)  # Gemini model at write time
    
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
    provider_model = db.Column(db.String(80), nullable=True, index=True)  # Gemini model at write time
    
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

class HiddenProvision(db.Model):
    """Hidden/sneaky provisions detected in bills"""
    id = db.Column(db.Integer, primary_key=True)
    bill_id = db.Column(db.Integer, db.ForeignKey('bill.id'), nullable=False)
    
    # Provision details
    provision_type = db.Column(db.String(200), nullable=False)  # Type of provision
    provision_text = db.Column(db.Text, nullable=False)  # Exact text or description
    risk_level = db.Column(db.String(20), nullable=False)  # low, medium, high
    confidence_score = db.Column(db.Float, nullable=False, default=0.0)  # 0.0-1.0
    
    # Reasoning and analysis
    risk_factors = db.Column(db.Text)  # JSON array of risk factors
    potential_impact = db.Column(db.Text)  # Description of potential impact
    recommendation = db.Column(db.Text)  # What to watch for
    overall_assessment = db.Column(db.Text)  # Brief assessment
    
    # Location and context
    chunk_index = db.Column(db.Integer)  # Which chunk this was found in
    chunk_type = db.Column(db.String(100))  # Type of chunk (section, subsection, etc.)
    section_reference = db.Column(db.String(200))  # Section reference if available
    
    # Analysis metadata
    analysis_version = db.Column(db.Integer, nullable=False, default=1)  # Links to AIAnalysis version
    detection_method = db.Column(db.String(50), default='ai_enhanced')  # How it was detected
    provider_model = db.Column(db.String(80), nullable=True, index=True)  # Gemini model at write time
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    bill = db.relationship('Bill', backref='hidden_provisions', lazy=True)
    
    # Indexes for better querying
    __table_args__ = (
        db.Index('idx_bill_risk_level', 'bill_id', 'risk_level'),
        db.Index('idx_risk_level_confidence', 'risk_level', 'confidence_score'),
    )
    
    def get_risk_factors(self):
        """Get parsed risk factors list"""
        try:
            return json.loads(self.risk_factors) if self.risk_factors else []
        except:
            return []
    
    def set_risk_factors(self, factors):
        """Set risk factors as JSON"""
        self.risk_factors = json.dumps(factors)
    
    def get_risk_score(self):
        """Calculate overall risk score"""
        risk_multipliers = {'low': 0.3, 'medium': 0.6, 'high': 1.0}
        base_risk = risk_multipliers.get(self.risk_level.lower(), 0.3)
        return base_risk * self.confidence_score
    
    def get_risk_color(self):
        """Get appropriate color class for risk level"""
        color_map = {
            'low': 'success',
            'medium': 'warning', 
            'high': 'danger'
        }
        return color_map.get(self.risk_level.lower(), 'secondary')
    
    def get_risk_icon(self):
        """Get appropriate icon for risk level"""
        icon_map = {
            'low': 'info',
            'medium': 'alert-triangle',
            'high': 'alert-circle'
        }
        return icon_map.get(self.risk_level.lower(), 'help-circle')
    
    def __repr__(self):
        return f'<HiddenProvision {self.bill_id} {self.provision_type} {self.risk_level}>'


class OpsAlert(db.Model):
    """Persisted programmer-facing ops alerts (e.g. Gemini failures)."""
    __tablename__ = 'ops_alert'

    id = db.Column(db.Integer, primary_key=True)
    failure_class = db.Column(db.String(50), nullable=False, index=True)
    severity = db.Column(db.String(20), nullable=False, default='error')
    message = db.Column(db.Text, nullable=False)
    bill_identifier = db.Column(db.String(50), nullable=True, index=True)
    bill_id = db.Column(db.Integer, db.ForeignKey('bill.id'), nullable=True)
    source = db.Column(db.String(50), nullable=False, default='analyzer')
    completion_percentage = db.Column(db.Float, nullable=True)
    provider_model = db.Column(db.String(80), nullable=True, index=True)
    extra_json = db.Column(db.Text, nullable=True)
    is_read = db.Column(db.Boolean, nullable=False, default=False, index=True)
    webhook_sent = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    bill = db.relationship('Bill', backref=db.backref('ops_alerts', lazy=True))

    def get_extra(self):
        try:
            return json.loads(self.extra_json) if self.extra_json else {}
        except Exception:
            return {}

    def set_extra(self, data):
        self.extra_json = json.dumps(data) if data is not None else None

    def __repr__(self):
        return f'<OpsAlert {self.id} {self.failure_class} bill={self.bill_identifier}>'
