from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash
from app import db
from db_models import User, PolicyCategory, UserPolicySubscription
from utils.constants import FEDERAL_POLICY_CATEGORIES
import re

auth = Blueprint('auth', __name__)

def validate_email(email):
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def validate_password(password):
    """Validate password strength"""
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    if not re.search(r'[A-Z]', password):
        return False, "Password must contain at least one uppercase letter"
    if not re.search(r'[a-z]', password):
        return False, "Password must contain at least one lowercase letter"
    if not re.search(r'\d', password):
        return False, "Password must contain at least one number"
    return True, "Password is valid"

@auth.route('/signup', methods=['GET', 'POST'])
def signup():
    """User registration page"""
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        
        # Validation
        errors = []
        
        if not username:
            errors.append('Username is required')
        elif len(username) < 3:
            errors.append('Username must be at least 3 characters long')
        elif User.query.filter_by(username=username).first():
            errors.append('Username already exists')
        
        if not email:
            errors.append('Email is required')
        elif not validate_email(email):
            errors.append('Please enter a valid email address')
        elif User.query.filter_by(email=email).first():
            errors.append('Email already registered')
        
        if not password:
            errors.append('Password is required')
        else:
            is_valid, message = validate_password(password)
            if not is_valid:
                errors.append(message)
        
        if password != confirm_password:
            errors.append('Passwords do not match')
        
        if errors:
            for error in errors:
                flash(error, 'error')
            return render_template('auth/signup.html')
        
        # Create user
        try:
            user = User(
                username=username,
                email=email,
                first_name=first_name,
                last_name=last_name
            )
            user.set_password(password)
            
            db.session.add(user)
            db.session.commit()
            
            # Log in the user
            login_user(user)
            flash('Account created successfully! Welcome to LegislAI.', 'success')
            return redirect(url_for('policy_interests'))
            
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while creating your account. Please try again.', 'error')
            return render_template('auth/signup.html')
    
    return render_template('auth/signup.html')

@auth.route('/signin', methods=['GET', 'POST'])
def signin():
    """User login page"""
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username_or_email = request.form.get('username_or_email', '').strip()
        password = request.form.get('password', '')
        remember = request.form.get('remember', False)
        
        if not username_or_email or not password:
            flash('Please enter both username/email and password', 'error')
            return render_template('auth/signin.html')
        
        # Try to find user by username or email
        user = User.query.filter(
            (User.username == username_or_email) | (User.email == username_or_email)
        ).first()
        
        if user and user.check_password(password):
            if not user.is_active:
                flash('Your account has been deactivated. Please contact support.', 'error')
                return render_template('auth/signin.html')
            
            login_user(user, remember=remember)
            flash(f'Welcome back, {user.get_full_name()}!', 'success')
            
            # Redirect to next page if specified
            next_page = request.args.get('next')
            if next_page and next_page.startswith('/'):
                return redirect(next_page)
            return redirect(url_for('index'))
        else:
            flash('Invalid username/email or password', 'error')
    
    return render_template('auth/signin.html')

@auth.route('/signout')
@login_required
def signout():
    """User logout"""
    logout_user()
    flash('You have been signed out successfully.', 'info')
    return redirect(url_for('index'))

@auth.route('/policy-interests', methods=['GET', 'POST'])
@login_required
def policy_interests():
    """Policy interests subscription page"""
    # Get all policy categories
    categories = PolicyCategory.query.filter_by(is_active=True).all()
    
    # If no categories exist, create them from constants
    if not categories:
        for category_name in FEDERAL_POLICY_CATEGORIES:
            category = PolicyCategory(
                name=category_name.lower().replace(' ', '_'),
                display_name=category_name,
                description=f"Bills and legislation related to {category_name.lower()}",
                color='#007bff'
            )
            db.session.add(category)
        db.session.commit()
        categories = PolicyCategory.query.filter_by(is_active=True).all()
    
    if request.method == 'POST':
        try:
            # Get selected categories
            selected_categories = request.form.getlist('categories')
            interest_levels = {}
            
            # Get interest levels for selected categories
            for category in categories:
                interest_key = f'interest_{category.id}'
                if interest_key in request.form:
                    interest_levels[category.id] = float(request.form[interest_key])
            
            # Update user subscriptions
            for category in categories:
                if str(category.id) in selected_categories:
                    interest_level = interest_levels.get(category.id, 0.5)
                    current_user.subscribe_to_category(category.id, interest_level)
                else:
                    current_user.unsubscribe_from_category(category.id)
            
            db.session.commit()
            flash('Your policy interests have been updated successfully!', 'success')
            return redirect(url_for('index'))
            
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while updating your interests. Please try again.', 'error')
    
    # Get user's current subscriptions
    user_subscriptions = {}
    for subscription in current_user.policy_subscriptions:
        user_subscriptions[subscription.policy_category_id] = subscription.interest_level
    
    return render_template('auth/policy_interests.html', 
                         categories=categories, 
                         user_subscriptions=user_subscriptions)

@auth.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    """User profile management"""
    if request.method == 'POST':
        try:
            # Update profile information
            current_user.first_name = request.form.get('first_name', '').strip()
            current_user.last_name = request.form.get('last_name', '').strip()
            current_user.organization = request.form.get('organization', '').strip()
            current_user.role = request.form.get('role', '').strip()
            current_user.location = request.form.get('location', '').strip()
            
            # Update alert preferences
            current_user.alert_frequency = request.form.get('alert_frequency', 'weekly')
            current_user.alert_enabled = 'alert_enabled' in request.form
            
            db.session.commit()
            flash('Profile updated successfully!', 'success')
            
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while updating your profile. Please try again.', 'error')
        
        return redirect(url_for('auth.profile'))
    
    return render_template('auth/profile.html', user=current_user) 