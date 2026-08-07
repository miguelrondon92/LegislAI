#!/usr/bin/env python3
"""
Minimal test server to check HR43 bill page
"""
import os
from dotenv import load_dotenv
load_dotenv()

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///legislative_analysis.db"
db = SQLAlchemy(model_class=Base)
db.init_app(app)

with app.app_context():
    # Import models after app setup
    import db_models
    
    @app.route('/bill/119/hr/43')
    def test_hr43():
        from flask import render_template
        
        # Get the bill
        bill = db_models.Bill.query.filter_by(congress=119, bill_type='hr', bill_number=43).first()
        if not bill:
            return "Bill not found"
        
        # Get actions
        bill_actions = db_models.BillAction.query.filter_by(bill_id=bill.id).order_by(
            db_models.BillAction.action_date.desc()
        ).all()
        
        # Get analysis if available
        analysis = None
        if bill.ai_analysis:
            import json
            analysis = json.loads(bill.ai_analysis)
        
        return render_template('bill_analysis.html', 
                             bill=bill, 
                             bill_actions=bill_actions,
                             analysis=analysis)

if __name__ == '__main__':
    app.run(debug=True, port=5001)