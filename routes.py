from flask import render_template, request, redirect, url_for, flash, jsonify, session
from flask_login import login_required, current_user
from app import app, db
from db_models import Bill, User, Alert, PolicyCategory, UserPolicySubscription, BillCategoryMapping, BillAction
import logging
from datetime import datetime
from services.congress_api import CongressAPI
from services.ai_analysis import AIAnalyzer
from services.bill_processor import BillProcessor

# Initialize services
congress_api = CongressAPI()
ai_analyzer = AIAnalyzer()
bill_processor = BillProcessor()

@app.route('/')
def index():
    """Main dashboard showing recent bills and user alerts"""
    # Get recent bills - only show latest version of each unique bill
    recent_bills = _get_unique_recent_bills(limit=10)
    
    # Get user alerts if user is authenticated
    alerts = []
    if current_user.is_authenticated:
        alerts = Alert.query.filter_by(user_id=current_user.id, is_read=False)\
                           .order_by(Alert.created_at.desc()).limit(5).all()
    
    return render_template('index.html', recent_bills=recent_bills, alerts=alerts)

@app.route('/bill_search', methods=['GET', 'POST'])
def bill_search():
    """Search for bills using various criteria with enhanced search types"""
    bills = []
    error_message = None
    search_query = ""
    search_type = "bill_number"
    congress = 119  # Default to current congress (119th)
    
    if request.method == 'POST':
        search_query = request.form.get('search_query', '').strip()
        search_type = request.form.get('search_type', 'bill_number')
        congress = int(request.form.get('congress', 119))
        
        if search_query:
            try:
                if search_type == 'bill_number':
                    # Search by specific bill number - check database first
                    bill = _get_or_fetch_bill_by_number(search_query, congress)
                    if bill:
                        bills = [bill]
                    else:
                        error_message = f"Bill '{search_query}' not found"
                        
                elif search_type == 'keyword':
                    # Search by keywords - hybrid approach
                    bills = _search_bills_hybrid(search_query, 'keyword', limit=20)
                    if not bills:
                        error_message = f"No bills found matching keywords '{search_query}'"
                        
                elif search_type == 'sponsor':
                    # Search by sponsor name - hybrid approach
                    bills = _search_bills_hybrid(search_query, 'sponsor', limit=20)
                    if not bills:
                        error_message = f"No bills found with sponsor '{search_query}'"
                        
            except Exception as e:
                logging.error(f"Error in bill search ({search_type}): {str(e)}")
                error_message = "An error occurred while searching for bills. Please try again."
    
    return render_template('bill_search.html', bills=bills, error_message=error_message, 
                         search_query=search_query, search_type=search_type, congress=congress)

def _get_or_fetch_bill_by_number(search_query, congress):
    """Get bill by number - check database first, fetch from API if needed"""
    try:
        # Parse the bill identifier to get congress, type, and number
        bill_parts = _parse_bill_identifier(search_query)
        if not bill_parts:
            return None
            
        bill_congress, bill_type, bill_number = bill_parts
        
        # Check if bill exists in database
        existing_bill = Bill.query.filter_by(
            congress=bill_congress,
            bill_type=bill_type, 
            bill_number=bill_number
        ).first()
        
        if existing_bill:
            logging.info(f"Found existing bill in database: {existing_bill.get_bill_identifier()}")
            
            # Check if we need to update actions (simple check - could be enhanced)
            if not existing_bill.actions:
                logging.info("No actions found, fetching from API...")
                fetch_bill_actions_from_api(existing_bill)
            
            # If no AI analysis, trigger it (check new table structure)
            if not existing_bill.get_active_ai_analysis() and not existing_bill.ai_analysis:
                logging.info("No AI analysis found, performing analysis...")
                _perform_analysis_if_needed(existing_bill)
            
            return existing_bill
        else:
            # Bill not in database, fetch from Congress API
            logging.info(f"Bill not in database, fetching from Congress API: {search_query}")
            bill_data = congress_api.get_bill_by_number(search_query)
            if bill_data:
                bill = bill_processor.process_bill_data(bill_data)
                if bill:
                    # Perform analysis on new bill
                    _perform_analysis_if_needed(bill)
                return bill
            return None
            
    except Exception as e:
        logging.error(f"Error in _get_or_fetch_bill_by_number: {e}")
        return None

def _search_bills_hybrid(search_query, search_type, limit=20):
    """Hybrid search - use database when possible, fetch from API when needed"""
    bills = []
    
    try:
        # First, search our database for existing bills
        if search_type == 'keyword':
            # Search database bills by title/summary
            db_bills = Bill.query.filter(
                Bill.title.contains(search_query) | 
                Bill.summary.contains(search_query)
            ).limit(limit//2).all()  # Get half from database
        else:  # sponsor search
            # Search database bills by sponsor
            db_bills = Bill.query.filter(
                Bill.sponsor_name.contains(search_query)
            ).limit(limit//2).all()
        
        logging.info(f"Found {len(db_bills)} bills in database for {search_type} search: '{search_query}'")
        bills.extend(db_bills)
        
        # If we don't have enough results, supplement with API search
        if len(bills) < limit:
            remaining_limit = limit - len(bills)
            logging.info(f"Fetching {remaining_limit} additional bills from Congress API")
            
            if search_type == 'keyword':
                api_bills_data = congress_api.search_bills(search_query, limit=remaining_limit)
            else:  # sponsor
                api_bills_data = congress_api.search_bills_by_sponsor(search_query, limit=remaining_limit)
            
            if api_bills_data:
                # Get identifiers of bills we already have to avoid duplicates
                existing_identifiers = set(bill.get_bill_identifier() for bill in bills)
                
                for bill_data in api_bills_data:
                    # Check if we already have this bill
                    bill_id = f"{bill_data.get('congress', '')}-{bill_data.get('type', '').upper()}{bill_data.get('number', '')}"
                    
                    if bill_id not in existing_identifiers:
                        # Check database first before processing
                        existing_bill = _check_bill_in_database(bill_data)
                        if existing_bill:
                            bills.append(existing_bill)
                        else:
                            # Process new bill from API
                            bill = bill_processor.process_bill_data(bill_data)
                            if bill:
                                _perform_analysis_if_needed(bill)
                                bills.append(bill)
                    
                    if len(bills) >= limit:
                        break
        
        logging.info(f"Returning {len(bills)} total bills for {search_type} search")
        return bills[:limit]  # Ensure we don't exceed limit
        
    except Exception as e:
        logging.error(f"Error in _search_bills_hybrid: {e}")
        return bills  # Return what we have so far

def _parse_bill_identifier(search_query):
    """Parse bill identifier to extract congress, type, and number"""
    try:
        # Use the same logic as Congress API
        parts = search_query.upper().replace('-', '').replace(' ', '').replace('.', '')
        
        if parts.startswith('HR') and not parts.startswith('HRES'):
            bill_type = 'hr'
            bill_number = int(parts[2:])
        elif parts.startswith('S') and not parts.startswith('SJRES') and not parts.startswith('SRES'):
            bill_type = 's'
            bill_number = int(parts[1:])
        else:
            # Handle other bill types if needed
            return None
        
        # Default to current congress if not specified
        return 119, bill_type, bill_number
        
    except (ValueError, IndexError):
        return None

def _check_bill_in_database(bill_data):
    """Check if a bill from API data already exists in database"""
    try:
        congress = bill_data.get('congress')
        bill_type = bill_data.get('type', '').lower()
        bill_number = bill_data.get('number')
        
        if congress and bill_type and bill_number:
            return Bill.query.filter_by(
                congress=congress,
                bill_type=bill_type,
                bill_number=bill_number
            ).first()
    except Exception:
        pass
    return None

def _perform_analysis_if_needed(bill):
    """Perform AI analysis on bill if not already done"""
    try:
        if not bill.ai_analysis:
            logging.info(f"Performing AI analysis for {bill.get_bill_identifier()}")
            # Get full text for analysis
            full_text = bill.get_full_text()
            if full_text:
                analysis = ai_analyzer.analyze_bill(full_text, bill.title)
                if analysis:
                    bill.set_ai_analysis(analysis)
                    db.session.commit()
                    logging.info(f"AI analysis completed for {bill.get_bill_identifier()}")
    except Exception as e:
        logging.error(f"Error performing analysis for {bill.get_bill_identifier()}: {e}")

def _get_unique_recent_bills(limit=10):
    """Get recent bills, using first record found for each unique bill (same logic as bill detail page)"""
    try:
        # Get all bills ordered by last_updated desc
        all_bills = Bill.query.order_by(Bill.last_updated.desc()).limit(limit*3).all()
        
        # Use a dictionary to keep track of unique bills (first version found)
        unique_bills = {}
        bill_keys_seen = set()
        
        for bill in all_bills:
            # Create unique key based on congress, type, and number
            bill_key = f"{bill.congress}-{bill.bill_type}-{bill.bill_number}"
            
            # Only keep the first version of each unique bill (same as .first() logic)
            if bill_key not in bill_keys_seen:
                # Use the same logic as bill detail page: get first record for this bill
                first_bill = Bill.query.filter_by(
                    congress=bill.congress,
                    bill_type=bill.bill_type,
                    bill_number=bill.bill_number
                ).first()
                unique_bills[bill_key] = first_bill
                bill_keys_seen.add(bill_key)
            
            # Stop once we have enough unique bills
            if len(unique_bills) >= limit:
                break
        
        # Return the unique bills sorted by last_updated desc
        result_bills = list(unique_bills.values())
        result_bills.sort(key=lambda b: b.last_updated, reverse=True)
        
        logging.info(f"Returning {len(result_bills)} unique recent bills (first record for each bill)")
        return result_bills[:limit]
        
    except Exception as e:
        logging.error(f"Error getting unique recent bills: {e}")
        # Fallback to active bills only
        return Bill.query.filter_by(active=True).order_by(Bill.last_updated.desc()).limit(limit).all()

def fetch_bill_actions_from_api(bill):
    """Fetch and store bill actions from Congress API"""
    try:
        if not bill.actions:  # Only fetch if no actions exist
            actions_data = congress_api.get_bill_actions(bill.congress, bill.bill_type, bill.bill_number)
            if actions_data and 'actions' in actions_data:
                for action_info in actions_data['actions']:
                    # Parse action data
                    action_date = None
                    if action_info.get('actionDate'):
                        try:
                            action_date = datetime.strptime(action_info['actionDate'], '%Y-%m-%d')
                        except:
                            pass
                    
                    action = BillAction(
                        bill_id=bill.id,
                        action_date=action_date or datetime.utcnow(),
                        action_type=action_info.get('type', 'Unknown'),
                        action_text=action_info.get('text', ''),
                        action_description=action_info.get('description', ''),
                        source_system=action_info.get('sourceSystem', {}).get('code', ''),
                        source_system_name=action_info.get('sourceSystem', {}).get('name', '')
                    )
                    db.session.add(action)
                
                db.session.commit()
                logging.info(f"Fetched {len(actions_data['actions'])} actions for bill {bill.get_bill_identifier()}")
    except Exception as e:
        logging.error(f"Error fetching bill actions: {str(e)}")

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
    
    # Fetch bill actions if not already present
    fetch_bill_actions_from_api(bill)
    
    # Perform AI analysis if not already done (check new table structure)
    analysis = bill.get_ai_analysis_new() or bill.get_ai_analysis()
    if not analysis:
        try:
            # Fetch full text from API for analysis
            full_text = bill.get_full_text()
            if full_text:
                analysis = ai_analyzer.analyze_bill(full_text, bill.title)
                bill.set_ai_analysis(analysis)
                db.session.commit()
            else:
                analysis = {"error": "Unable to fetch bill text for analysis"}
        except Exception as e:
            logging.error(f"Error in AI analysis: {str(e)}")
            analysis = {"error": "Unable to perform AI analysis at this time"}
    
    # Calculate user alignment score if user is logged in
    alignment_score = None
    user_analysis = None
    if current_user.is_authenticated:
        user_prefs = current_user.get_policy_preferences()
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
    
    # Get bill actions (refresh from database after potential fetch)
    bill_actions = bill.actions
    
    return render_template('bill_analysis.html', 
                         bill=bill, 
                         analysis=analysis,
                         alignment_score=alignment_score,
                         user_analysis=user_analysis,
                         bill_actions=bill_actions)

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
@login_required
def alerts():
    """Display user alerts and notifications"""
    # Get all alerts for the user
    alerts = Alert.query.filter_by(user_id=current_user.id)\
                       .order_by(Alert.created_at.desc()).all()
    
    return render_template('alerts.html', alerts=alerts)

@app.route('/mark_alert_read/<int:alert_id>')
@login_required
def mark_alert_read(alert_id):
    """Mark an alert as read"""
    alert = Alert.query.filter_by(id=alert_id, user_id=current_user.id).first()
    if alert:
        alert.is_read = True
        db.session.commit()
        flash('Alert marked as read', 'success')
    else:
        flash('Alert not found', 'error')
    
    return redirect(url_for('alerts'))

@app.route('/add_to_watchlist/<int:bill_id>')
@login_required
def add_to_watchlist(bill_id):
    """Add a bill to user's watchlist"""
    bill = Bill.query.get(bill_id)
    if not bill:
        flash('Bill not found', 'error')
        return redirect(url_for('bill_search'))
    
    # Check if already in watchlist
    existing = WatchlistItem.query.filter_by(
        user_id=current_user.id, 
        bill_id=bill_id
    ).first()
    
    if existing:
        flash('Bill is already in your watchlist', 'info')
    else:
        watchlist_item = WatchlistItem(
            user_id=current_user.id,
            bill_id=bill_id
        )
        db.session.add(watchlist_item)
        db.session.commit()
        flash('Bill added to watchlist', 'success')
    
    return redirect(url_for('bill_analysis', 
                          congress=bill.congress, 
                          bill_type=bill.bill_type, 
                          bill_number=bill.bill_number))

@app.route('/api/generate_alerts')
@login_required
def generate_alerts():
    """Generate alerts for the current user based on their policy preferences"""
    try:
        # This would typically be called by a background job
        # For now, just return a success message
        return jsonify({'status': 'success', 'message': 'Alerts generation initiated'})
    except Exception as e:
        logging.error(f"Error generating alerts: {str(e)}")
        return jsonify({'status': 'error', 'message': 'Failed to generate alerts'}), 500

@app.route('/api/bill/<int:congress>/<bill_type>/<int:bill_number>/text')
def get_bill_text(congress, bill_type, bill_number):
    """API endpoint to get bill text"""
    try:
        bill = Bill.query.filter_by(
            congress=congress, 
            bill_type=bill_type.lower(), 
            bill_number=bill_number
        ).first()
        
        if not bill:
            return jsonify({'error': 'Bill not found'}), 404
        
        full_text = bill.get_full_text()
        if not full_text:
            return jsonify({'error': 'Bill text not available'}), 404
        
        return jsonify({
            'congress': congress,
            'bill_type': bill_type,
            'bill_number': bill_number,
            'title': bill.title,
            'text': full_text
        })
        
    except Exception as e:
        logging.error(f"Error getting bill text: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/workflow/start', methods=['POST'])
@login_required
def start_workflow():
    """Start the bill processing workflow"""
    try:
        from services.workflow_orchestrator import WorkflowOrchestrator
        orchestrator = WorkflowOrchestrator()
        orchestrator.start_workflow()
        return jsonify({'status': 'success', 'message': 'Workflow started'})
    except Exception as e:
        logging.error(f"Error starting workflow: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/workflow/stop', methods=['POST'])
@login_required
def stop_workflow():
    """Stop the bill processing workflow"""
    try:
        from services.workflow_orchestrator import WorkflowOrchestrator
        orchestrator = WorkflowOrchestrator()
        orchestrator.stop_workflow()
        return jsonify({'status': 'success', 'message': 'Workflow stopped'})
    except Exception as e:
        logging.error(f"Error stopping workflow: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/workflow/status')
@login_required
def get_workflow_status():
    """Get the current workflow status"""
    try:
        from services.workflow_orchestrator import WorkflowOrchestrator
        orchestrator = WorkflowOrchestrator()
        status = orchestrator.get_status()
        return jsonify(status)
    except Exception as e:
        logging.error(f"Error getting workflow status: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/workflow/recent')
@login_required
def get_recent_workflow_items():
    """Get recent workflow items"""
    try:
        from services.workflow_orchestrator import WorkflowOrchestrator
        orchestrator = WorkflowOrchestrator()
        items = orchestrator.get_recent_items()
        return jsonify({'items': items})
    except Exception as e:
        logging.error(f"Error getting recent workflow items: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/workflow')
@login_required
def workflow_dashboard():
    """Workflow dashboard for monitoring bill processing"""
    return render_template('workflow_dashboard.html')

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(e):
    return render_template('500.html'), 500
