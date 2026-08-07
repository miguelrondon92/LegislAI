"""
Workflow Admin Microservice
A separate Flask app for administrative workflow management

This service runs on port 5001 and provides:
- Workflow dashboard (admin-only)
- Workflow control APIs (start/stop/status)
- Admin authentication
- Independent scaling and deployment

Access: http://localhost:5001
"""

from flask import Flask, render_template, request, jsonify, abort, redirect, url_for, session
from functools import wraps
import logging
import os
from datetime import datetime

# Import database models (shared with main app)
from db_models import db, Bill, User, Alert, PolicyCategory, UserPolicySubscription, BillCategoryMapping, BillAction, AIAnalysis, Summary

# Create Flask app for workflow admin
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('ADMIN_SECRET_KEY', 'admin-workflow-secret-key-change-in-production')

# Database configuration (shared with main app)
database_url = os.environ.get('DATABASE_URL', 'sqlite:///instance/legislative_analysis.db')
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize database
db.init_app(app)

# Global workflow orchestrator instance
workflow_orchestrator = None

def get_workflow_orchestrator():
    """Get the global workflow orchestrator instance"""
    global workflow_orchestrator
    if workflow_orchestrator is None:
        # Import here to avoid circular imports
        from services.workflow_orchestrator import WorkflowOrchestrator
        workflow_orchestrator = WorkflowOrchestrator()
    return workflow_orchestrator

# Admin authentication configuration
ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin123')  # Change in production!

def admin_required(f):
    """Decorator to require admin authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_authenticated'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    """Admin login page"""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['admin_authenticated'] = True
            return redirect(url_for('workflow_dashboard'))
        else:
            return render_template('admin/login.html', error='Invalid credentials')
    
    return render_template('admin/login.html')

@app.route('/admin/logout')
def admin_logout():
    """Admin logout"""
    session.pop('admin_authenticated', None)
    return redirect(url_for('admin_login'))

@app.route('/')
@admin_required
def index():
    """Redirect to workflow dashboard"""
    return redirect(url_for('workflow_dashboard'))

@app.route('/workflow')
@admin_required
def workflow_dashboard():
    """Workflow dashboard for monitoring bill processing"""
    return render_template('admin/workflow_dashboard.html')

# Workflow API Endpoints (migrated from main app)

@app.route('/api/workflow/start', methods=['POST'])
@admin_required
def start_workflow():
    """Start the bill processing workflow"""
    try:
        orchestrator = get_workflow_orchestrator()
        result = orchestrator.start_workflow_web()
        return jsonify(result)
    except Exception as e:
        logging.error(f"Error starting workflow: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/workflow/stop', methods=['POST'])
@admin_required
def stop_workflow():
    """Stop the bill processing workflow"""
    try:
        orchestrator = get_workflow_orchestrator()
        result = orchestrator.stop_workflow_web()
        return jsonify(result)
    except Exception as e:
        logging.error(f"Error stopping workflow: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/workflow/status')
@admin_required
def get_workflow_status():
    """Get the current workflow status"""
    try:
        orchestrator = get_workflow_orchestrator()
        status = orchestrator.get_workflow_status()
        return jsonify(status)
    except Exception as e:
        logging.error(f"Error getting workflow status: {str(e)}")
        return jsonify({
            'is_running': False,
            'queue_size': 0,
            'statistics': {
                'bills_discovered': 0,
                'bills_processed': 0,
                'bills_analyzed': 0,
                'alerts_generated': 0,
                'errors': 0
            },
            'last_run': None,
            'error_message': str(e)
        })

@app.route('/api/workflow/recent')
@admin_required
def get_recent_workflow_items():
    """Get recent workflow items"""
    try:
        orchestrator = get_workflow_orchestrator()
        limit = request.args.get('limit', 10, type=int)
        items = orchestrator.get_recent_workflow_items(limit)
        return jsonify({'items': items})
    except Exception as e:
        logging.error(f"Error getting recent workflow items: {str(e)}")
        return jsonify({'items': [], 'error_message': str(e)})

# Health check endpoint
@app.route('/health')
def health_check():
    """Health check for monitoring"""
    return jsonify({
        'status': 'healthy',
        'service': 'workflow-admin',
        'timestamp': datetime.utcnow().isoformat(),
        'version': '1.0.0'
    })

# Error handlers
@app.errorhandler(404)
def page_not_found(e):
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(500)
def internal_error(e):
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('logs/workflow_admin.log'),
            logging.StreamHandler()
        ]
    )
    
    print("🚀 Starting Workflow Admin Microservice")
    print(f"📊 Dashboard: http://localhost:5001/workflow")
    print(f"🔐 Login: http://localhost:5001/admin/login")
    print(f"💊 Health: http://localhost:5001/health")
    print(f"👤 Default admin: {ADMIN_USERNAME} / {ADMIN_PASSWORD}")
    print("⚠️  Change admin credentials in production!")
    
    app.run(host='0.0.0.0', port=5001, debug=True)