import os
import logging
from pathlib import Path

# Load environment variables from .env next to this file (not cwd-dependent)
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent / ".env")

from flask import Flask
from flask_mail import Mail
from flask_migrate import Migrate
from flask_login import LoginManager
from werkzeug.middleware.proxy_fix import ProxyFix

# Configure logging based on environment
log_level = os.environ.get('LOG_LEVEL', 'INFO').upper()
numeric_level = getattr(logging, log_level, logging.INFO)
logging.basicConfig(
    level=numeric_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
# Create the app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "dev-secret-key-change-in-production")
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)  # needed for url_for to generate with https

# Configure Flask app based on environment
app.config['DEBUG'] = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
app.config['TESTING'] = os.environ.get('FLASK_TESTING', 'False').lower() == 'true'

# Configure the database, relative to the app instance folder
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///legislative_analysis.db")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}

# Configure email settings
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 2525))
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'true').lower() == 'true'
app.config['MAIL_USE_SSL'] = os.environ.get('MAIL_USE_SSL', 'false').lower() == 'true'

# Import db from db_models and initialize extensions
from db_models import db

migrate = Migrate()
mail = Mail()
login_manager = LoginManager()

# Initialize the app with the extensions
db.init_app(app)
migrate.init_app(app, db)
mail.init_app(app)
login_manager.init_app(app)

# Configure Flask-Login
login_manager.login_view = 'auth.signin'
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'info'

# Register custom template filters
from utils.text_processing import clean_bill_summary

@app.template_filter('clean_summary')
def clean_summary_filter(text):
    """Template filter to clean bill summary text"""
    return clean_bill_summary(text)

@login_manager.user_loader
def load_user(user_id):
    from db_models import User
    return User.query.get(int(user_id))

with app.app_context():
    # Import db_models to ensure tables are created
    import db_models  # noqa: F401
    
    db.create_all()

# Import and register blueprints outside app context
from auth import auth
app.register_blueprint(auth, url_prefix='/auth')

# Import routes to register them
import routes  # noqa: F401

# Import and start notification scheduler
from services.notification_scheduler import start_notification_scheduler
#start_notification_scheduler()

print("Database URI:", app.config["SQLALCHEMY_DATABASE_URI"])

# Register cleanup on app shutdown
@app.teardown_appcontext
def shutdown_notification_scheduler(exception=None):
    from services.notification_scheduler import stop_notification_scheduler
    stop_notification_scheduler()
