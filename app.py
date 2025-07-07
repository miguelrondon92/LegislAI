import os
import logging

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail
from flask_migrate import Migrate
from flask_login import LoginManager
from sqlalchemy.orm import DeclarativeBase
from werkzeug.middleware.proxy_fix import ProxyFix

# Configure logging for debugging
logging.basicConfig(level=logging.DEBUG)

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)
migrate = Migrate()
mail = Mail()
login_manager = LoginManager()

# Create the app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "dev-secret-key-change-in-production")
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)  # needed for url_for to generate with https

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

# Initialize the app with the extensions
db.init_app(app)
migrate.init_app(app, db)
mail.init_app(app)
login_manager.init_app(app)

# Configure Flask-Login
login_manager.login_view = 'auth.signin'
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'info'

@login_manager.user_loader
def load_user(user_id):
    from db_models import User
    return User.query.get(int(user_id))

with app.app_context():
    # Import db_models to ensure tables are created
    import db_models  # noqa: F401
    
    # Import and register blueprints
    from auth import auth
    app.register_blueprint(auth, url_prefix='/auth')
    
    # Import routes to register them
    import routes  # noqa: F401
    
    # Import and start notification scheduler
    from services.notification_scheduler import start_notification_scheduler
    #start_notification_scheduler()
    
    db.create_all()

    print("Database URI:", app.config["SQLALCHEMY_DATABASE_URI"])

# Register cleanup on app shutdown
@app.teardown_appcontext
def shutdown_notification_scheduler(exception=None):
    from services.notification_scheduler import stop_notification_scheduler
    stop_notification_scheduler()
