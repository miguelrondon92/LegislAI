from flask.cli import FlaskGroup
from app import app, db
from flask_migrate import Migrate

cli = FlaskGroup(app)
migrate = Migrate(app, db)

if __name__ == '__main__':
    cli() 