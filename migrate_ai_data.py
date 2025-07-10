#!/usr/bin/env python3
"""
Manual data migration script to move AI analysis and summary data 
from Bill table to new AIAnalysis and Summary tables
"""

import json
from datetime import datetime
from app import app, db
from db_models import Bill, AIAnalysis, Summary

def migrate_data():
    """Migrate existing AI analysis and summary data to new tables"""
    
    with app.app_context():
        print("Starting data migration...")
        
        # Get all bills with AI analysis or summary data
        bills = Bill.query.filter(
            (Bill.ai_analysis.isnot(None)) | (Bill.summary.isnot(None))
        ).all()
        
        print(f"Found {len(bills)} bills with analysis or summary data")
        
        migrated_analysis = 0
        migrated_summaries = 0
        
        for bill in bills:
            print(f"Processing bill {bill.id}: {bill.get_bill_identifier()}")
            
            # Migrate AI Analysis
            if bill.ai_analysis:
                try:
                    # Parse existing analysis
                    analysis_data = json.loads(bill.ai_analysis)
                    
                    # Extract complexity and controversy scores
                    complexity_score = bill.complexity_score
                    controversy_score = None
                    
                    if isinstance(analysis_data, dict):
                        complexity_assessment = analysis_data.get('complexity_assessment', {})
                        if isinstance(complexity_assessment, dict):
                            if complexity_score is None:
                                complexity_score = complexity_assessment.get('complexity_score')
                        controversy_score = analysis_data.get('controversy_score', 0.0)
                    
                    # Create AIAnalysis record
                    ai_analysis = AIAnalysis(
                        bill_id=bill.id,
                        analysis_data=bill.ai_analysis,
                        complexity_score=complexity_score,
                        controversy_score=controversy_score,
                        analysis_method='migrated',
                        analysis_version=1,
                        active=True,
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow()
                    )
                    
                    db.session.add(ai_analysis)
                    migrated_analysis += 1
                    
                    # Extract and migrate summary data
                    summary_data = analysis_data.get('summary', {}) if isinstance(analysis_data, dict) else {}
                    
                    if summary_data or bill.summary:
                        main_summary = summary_data.get('main_summary') if isinstance(summary_data, dict) else None
                        plain_language = summary_data.get('plain_language_explanation') if isinstance(summary_data, dict) else None
                        key_provisions = summary_data.get('key_provisions', []) if isinstance(summary_data, dict) else []
                        funding = summary_data.get('funding_amounts') if isinstance(summary_data, dict) else None
                        timeline = summary_data.get('implementation_timeline') if isinstance(summary_data, dict) else None
                        
                        # Use summary_text from bill table as fallback
                        final_summary = main_summary or bill.summary
                        
                        if final_summary:
                            summary = Summary(
                                bill_id=bill.id,
                                summary_text=final_summary,
                                plain_language_summary=plain_language,
                                key_provisions=json.dumps(key_provisions) if key_provisions else None,
                                funding_amounts=funding,
                                implementation_timeline=timeline,
                                summary_type='migrated',
                                summary_version=1,
                                active=True,
                                created_at=datetime.utcnow(),
                                updated_at=datetime.utcnow()
                            )
                            
                            db.session.add(summary)
                            migrated_summaries += 1
                    
                except json.JSONDecodeError:
                    print(f"Warning: Could not parse AI analysis JSON for bill {bill.id}")
                    continue
            
            # Migrate summary if no AI analysis but summary exists
            elif bill.summary:
                summary = Summary(
                    bill_id=bill.id,
                    summary_text=bill.summary,
                    summary_type='congressional',
                    summary_version=1,
                    active=True,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                
                db.session.add(summary)
                migrated_summaries += 1
        
        # Commit all changes
        try:
            db.session.commit()
            print(f"\nMigration completed successfully!")
            print(f"Migrated {migrated_analysis} AI analyses")
            print(f"Migrated {migrated_summaries} summaries")
            
            # Verify the migration
            print("\nVerification:")
            print(f"Total AIAnalysis records: {AIAnalysis.query.count()}")
            print(f"Total Summary records: {Summary.query.count()}")
            print(f"Active AIAnalysis records: {AIAnalysis.query.filter_by(active=True).count()}")
            print(f"Active Summary records: {Summary.query.filter_by(active=True).count()}")
            
        except Exception as e:
            db.session.rollback()
            print(f"Error during migration: {e}")
            raise

if __name__ == '__main__':
    migrate_data()