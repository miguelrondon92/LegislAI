from flask import render_template, request, redirect, url_for, flash, session, jsonify
from app import app, db
from models import User, Bill, Alert, WatchlistItem
# Import services with error handling
try:
    from services.congress_api import CongressAPI
    from services.ai_analysis import AIAnalyzer
    from services.bill_processor import BillProcessor
except ImportError as e:
    logging.warning(f"Service import error: {e}")
    # Create placeholder classes for development
    class CongressAPI:
        def get_bill_by_number(self, query): return None
        def search_bills(self, query): return []
        def search_bills_by_sponsor(self, query): return []
        def get_bill_details(self, congress, bill_type, number): return None
    
    class AIAnalyzer:
        def analyze_bill(self, text, title): return {}
        def calculate_alignment_score(self, analysis, prefs): return 0
        def generate_user_specific_analysis(self, analysis, prefs, score): return {}
    
    class BillProcessor:
        def process_bill_data(self, data): return None
        def generate_user_alerts(self): return []
import logging

# Initialize services
congress_api = CongressAPI()
ai_analyzer = AIAnalyzer()
bill_processor = BillProcessor()

@app.route('/')
def index():
    """Main dashboard showing recent bills and user alerts"""
    # Get recent bills
    recent_bills = Bill.query.order_by(Bill.last_updated.desc()).limit(10).all()
    
    # Get user alerts if user is in session
    alerts = []
    if 'user_id' in session:
        alerts = Alert.query.filter_by(user_id=session['user_id'], is_read=False)\
                           .order_by(Alert.created_at.desc()).limit(5).all()
    
    return render_template('index.html', recent_bills=recent_bills, alerts=alerts)

@app.route('/bill_search', methods=['GET', 'POST'])
def bill_search():
    """Search for bills using various criteria"""
    bills = []
    error_message = None
    
    if request.method == 'POST':
        try:
            search_type = request.form.get('search_type')
            search_query = request.form.get('search_query', '').strip()
            
            if not search_query:
                flash('Please enter a search term', 'warning')
                return render_template('search.html', bills=bills)
            
            if search_type == 'bill_number':
                # Search for specific bill number
                bill_data = congress_api.get_bill_by_number(search_query)
                if bill_data:
                    bill = bill_processor.process_bill_data(bill_data)
                    bills = [bill] if bill else []
                else:
                    error_message = f"Bill {search_query} not found"
            
            elif search_type == 'keyword':
                # Search bills by keyword
                bills_data = congress_api.search_bills(search_query)
                bills = []
                for bill_data in bills_data[:20]:  # Limit to 20 results
                    bill = bill_processor.process_bill_data(bill_data)
                    if bill:
                        bills.append(bill)
            
            elif search_type == 'sponsor':
                # Search by sponsor name
                bills_data = congress_api.search_bills_by_sponsor(search_query)
                bills = []
                for bill_data in bills_data[:20]:
                    bill = bill_processor.process_bill_data(bill_data)
                    if bill:
                        bills.append(bill)
            
            if not bills and not error_message:
                error_message = "No bills found matching your search criteria"
                
        except Exception as e:
            logging.error(f"Error in bill search: {str(e)}")
            error_message = "An error occurred while searching for bills. Please try again."
    
    return render_template('search.html', bills=bills, error_message=error_message)

@app.route('/bill/<int:congress>/<bill_type>/<int:bill_number>')
def bill_analysis(congress, bill_type, bill_number):
    """Display detailed analysis of a specific bill"""
    # Check if bill exists in database
    bill = Bill.query.filter_by(
        congress=congress, 
        bill_type=bill_type.lower(), 
        bill_number=bill_number
    ).first()
    
    if not bill:
        # Fetch from Congress API if not in database
        try:
            bill_data = congress_api.get_bill_details(congress, bill_type, bill_number)
            if bill_data:
                bill = bill_processor.process_bill_data(bill_data)
            else:
                flash('Bill not found', 'error')
                return redirect(url_for('bill_search'))
        except Exception as e:
            logging.error(f"Error fetching bill: {str(e)}")
            flash('Error loading bill details', 'error')
            return redirect(url_for('bill_search'))
    
    # Perform AI analysis if not already done
    analysis = bill.get_ai_analysis()
    if not analysis and bill.full_text:
        try:
            analysis = ai_analyzer.analyze_bill(bill.full_text, bill.title)
            bill.set_ai_analysis(analysis)
            db.session.commit()
        except Exception as e:
            logging.error(f"Error in AI analysis: {str(e)}")
            analysis = {"error": "Unable to perform AI analysis at this time"}
    
    # Calculate user alignment score if user is logged in
    alignment_score = None
    user_analysis = None
    if 'user_id' in session:
        user = User.query.get(session['user_id'])
        if user:
            user_prefs = user.get_policy_preferences()
            if user_prefs and analysis:
                try:
                    alignment_score = ai_analyzer.calculate_alignment_score(
                        analysis, user_prefs
                    )
                    user_analysis = ai_analyzer.generate_user_specific_analysis(
                        analysis, user_prefs, alignment_score
                    )
                except Exception as e:
                    logging.error(f"Error calculating alignment: {str(e)}")
    
    return render_template('bill_analysis.html', 
                         bill=bill, 
                         analysis=analysis,
                         alignment_score=alignment_score,
                         user_analysis=user_analysis)

@app.route('/profile', methods=['GET', 'POST'])
def profile():
    """User profile and policy preferences management"""
    if 'user_id' not in session:
        # Create a temporary user session for demo purposes
        session['user_id'] = 1
        user = User.query.get(1)
        if not user:
            user = User(username='demo_user', email='demo@example.com')
            db.session.add(user)
            db.session.commit()
            session['user_id'] = user.id
    
    user = User.query.get(session['user_id'])
    
    if request.method == 'POST':
        try:
            # Update policy preferences
            preferences = {}
            policy_areas = [
                'healthcare', 'environment', 'economy', 'education', 'defense',
                'immigration', 'civil_rights', 'technology', 'agriculture',
                'energy', 'transportation', 'housing', 'tax_policy',
                'foreign_policy', 'criminal_justice', 'social_services'
            ]
            
            for area in policy_areas:
                importance = request.form.get(f'{area}_importance', 'medium')
                stance = request.form.get(f'{area}_stance', 'neutral')
                preferences[area] = {
                    'importance': importance,
                    'stance': stance
                }
            
            user.set_policy_preferences(preferences)
            
            # Update alert preferences
            user.alert_frequency = request.form.get('alert_frequency', 'weekly')
            user.alert_enabled = 'alert_enabled' in request.form
            
            db.session.commit()
            flash('Profile updated successfully!', 'success')
            
        except Exception as e:
            logging.error(f"Error updating profile: {str(e)}")
            flash('Error updating profile. Please try again.', 'error')
        
        return redirect(url_for('profile'))
    
    current_preferences = user.get_policy_preferences()
    return render_template('profile.html', user=user, preferences=current_preferences)

@app.route('/alerts')
def alerts():
    """Display user alerts and notifications"""
    if 'user_id' not in session:
        flash('Please set up your profile first', 'info')
        return redirect(url_for('profile'))
    
    user = User.query.get(session['user_id'])
    
    # Get all alerts for the user
    all_alerts = Alert.query.filter_by(user_id=user.id)\
                           .order_by(Alert.created_at.desc()).all()
    
    # Separate read and unread alerts
    unread_alerts = [alert for alert in all_alerts if not alert.is_read]
    read_alerts = [alert for alert in all_alerts if alert.is_read]
    
    return render_template('alerts.html', 
                         unread_alerts=unread_alerts, 
                         read_alerts=read_alerts)

@app.route('/mark_alert_read/<int:alert_id>')
def mark_alert_read(alert_id):
    """Mark an alert as read"""
    alert = Alert.query.get_or_404(alert_id)
    
    # Check if alert belongs to current user
    if 'user_id' in session and alert.user_id == session['user_id']:
        alert.is_read = True
        db.session.commit()
    
    return redirect(url_for('alerts'))

@app.route('/add_to_watchlist/<int:bill_id>')
def add_to_watchlist(bill_id):
    """Add a bill to user's watchlist"""
    if 'user_id' not in session:
        flash('Please set up your profile first', 'info')
        return redirect(url_for('profile'))
    
    bill = Bill.query.get_or_404(bill_id)
    user_id = session['user_id']
    
    # Check if already in watchlist
    existing = WatchlistItem.query.filter_by(user_id=user_id, bill_id=bill_id).first()
    if not existing:
        watchlist_item = WatchlistItem(user_id=user_id, bill_id=bill_id)
        db.session.add(watchlist_item)
        db.session.commit()
        flash(f'Added {bill.get_bill_identifier()} to your watchlist', 'success')
    else:
        flash('Bill is already in your watchlist', 'info')
    
    return redirect(request.referrer or url_for('index'))

@app.route('/api/generate_alerts')
def generate_alerts():
    """API endpoint to generate alerts for all users based on new bills"""
    try:
        # This would typically be called by a background job
        users_with_alerts = bill_processor.generate_user_alerts()
        return jsonify({
            'success': True, 
            'users_processed': len(users_with_alerts),
            'message': f'Generated alerts for {len(users_with_alerts)} users'
        })
    except Exception as e:
        logging.error(f"Error generating alerts: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.errorhandler(404)
def page_not_found(e):
    return render_template('base.html'), 404

@app.errorhandler(500)
def internal_error(e):
    return render_template('base.html'), 500
