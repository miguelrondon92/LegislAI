"""Add AIAnalysis and Summary tables with versioning

Revision ID: d291c9c77bad
Revises: 7dfebb57eea7
Create Date: 2025-07-09 18:35:09.859329

"""
from alembic import op
import sqlalchemy as sa
import json


# revision identifiers, used by Alembic.
revision = 'd291c9c77bad'
down_revision = '7dfebb57eea7'
branch_labels = None
depends_on = None


def upgrade():
    # Drop the unique constraint from bill table
    with op.batch_alter_table('bill', schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f('uq_bill_congress_type_number_version'), type_='unique')

    # Create AIAnalysis table
    op.create_table('ai_analysis',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('bill_id', sa.Integer(), nullable=False),
        sa.Column('analysis_data', sa.Text(), nullable=True),
        sa.Column('complexity_score', sa.Float(), nullable=True),
        sa.Column('controversy_score', sa.Float(), nullable=True),
        sa.Column('analysis_method', sa.String(length=50), nullable=True),
        sa.Column('chunks_analyzed', sa.Integer(), nullable=True),
        sa.Column('processing_time', sa.Float(), nullable=True),
        sa.Column('analysis_version', sa.Integer(), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['bill_id'], ['bill.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('bill_id', 'analysis_version', name='uq_bill_analysis_version')
    )
    
    # Create indexes for AIAnalysis
    op.create_index('idx_bill_active_analysis', 'ai_analysis', ['bill_id', 'active'], unique=False)

    # Create Summary table
    op.create_table('summary',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('bill_id', sa.Integer(), nullable=False),
        sa.Column('summary_text', sa.Text(), nullable=True),
        sa.Column('plain_language_summary', sa.Text(), nullable=True),
        sa.Column('key_provisions', sa.Text(), nullable=True),
        sa.Column('funding_amounts', sa.String(length=500), nullable=True),
        sa.Column('implementation_timeline', sa.String(length=500), nullable=True),
        sa.Column('summary_type', sa.String(length=50), nullable=True),
        sa.Column('summary_version', sa.Integer(), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['bill_id'], ['bill.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('bill_id', 'summary_version', name='uq_bill_summary_version')
    )
    
    # Create indexes for Summary
    op.create_index('idx_bill_active_summary', 'summary', ['bill_id', 'active'], unique=False)
    
    # Migrate existing data
    migrate_existing_data()


def migrate_existing_data():
    """Migrate existing AI analysis and summary data to new tables"""
    
    # Get database connection
    connection = op.get_bind()
    
    # Get all bills with AI analysis data
    bills_result = connection.execute(
        sa.text("SELECT id, ai_analysis, complexity_score, summary FROM bill WHERE ai_analysis IS NOT NULL OR summary IS NOT NULL")
    )
    
    for bill_row in bills_result:
        bill_id = bill_row[0]
        ai_analysis_json = bill_row[1]
        complexity_score = bill_row[2]
        summary_text = bill_row[3]
        
        # Migrate AI Analysis data
        if ai_analysis_json:
            try:
                # Parse existing analysis
                analysis_data = json.loads(ai_analysis_json)
                
                # Extract complexity and controversy scores from analysis if not in bill table
                analysis_complexity = None
                analysis_controversy = None
                
                if isinstance(analysis_data, dict):
                    complexity_assessment = analysis_data.get('complexity_assessment', {})
                    if isinstance(complexity_assessment, dict):
                        analysis_complexity = complexity_assessment.get('complexity_score')
                    analysis_controversy = analysis_data.get('controversy_score', 0.0)
                
                # Use complexity from bill table if available, otherwise from analysis
                final_complexity = complexity_score if complexity_score is not None else analysis_complexity
                
                # Insert into AIAnalysis table
                connection.execute(
                    sa.text("""
                        INSERT INTO ai_analysis 
                        (bill_id, analysis_data, complexity_score, controversy_score, 
                         analysis_method, analysis_version, active, created_at, updated_at)
                        VALUES (:bill_id, :analysis_data, :complexity_score, :controversy_score,
                                'migrated', 1, true, datetime('now'), datetime('now'))
                    """),
                    {
                        'bill_id': bill_id,
                        'analysis_data': ai_analysis_json,
                        'complexity_score': final_complexity,
                        'controversy_score': analysis_controversy
                    }
                )
                
                # Extract summary data from analysis
                summary_data = analysis_data.get('summary', {}) if isinstance(analysis_data, dict) else {}
                
                # Create Summary record if we have summary data
                if summary_data or summary_text:
                    main_summary = summary_data.get('main_summary') if isinstance(summary_data, dict) else None
                    plain_language = summary_data.get('plain_language_explanation') if isinstance(summary_data, dict) else None
                    key_provisions = summary_data.get('key_provisions', []) if isinstance(summary_data, dict) else []
                    funding = summary_data.get('funding_amounts') if isinstance(summary_data, dict) else None
                    timeline = summary_data.get('implementation_timeline') if isinstance(summary_data, dict) else None
                    
                    # Use summary_text from bill table as fallback
                    final_summary = main_summary or summary_text
                    
                    if final_summary:
                        connection.execute(
                            sa.text("""
                                INSERT INTO summary 
                                (bill_id, summary_text, plain_language_summary, key_provisions,
                                 funding_amounts, implementation_timeline, summary_type, 
                                 summary_version, active, created_at, updated_at)
                                VALUES (:bill_id, :summary_text, :plain_language_summary, :key_provisions,
                                        :funding_amounts, :implementation_timeline, 'migrated',
                                        1, true, datetime('now'), datetime('now'))
                            """),
                            {
                                'bill_id': bill_id,
                                'summary_text': final_summary,
                                'plain_language_summary': plain_language,
                                'key_provisions': json.dumps(key_provisions) if key_provisions else None,
                                'funding_amounts': funding,
                                'implementation_timeline': timeline
                            }
                        )
                        
            except json.JSONDecodeError:
                print(f"Warning: Could not parse AI analysis JSON for bill {bill_id}")
                continue
        
        # Migrate summary if no AI analysis but summary exists
        elif summary_text:
            connection.execute(
                sa.text("""
                    INSERT INTO summary 
                    (bill_id, summary_text, summary_type, summary_version, active, created_at, updated_at)
                    VALUES (:bill_id, :summary_text, 'congressional', 1, true, datetime('now'), datetime('now'))
                """),
                {
                    'bill_id': bill_id,
                    'summary_text': summary_text
                }
            )
    
    print("Data migration completed successfully!")


def downgrade():
    # Drop new tables
    op.drop_index('idx_bill_active_summary', table_name='summary')
    op.drop_table('summary')
    op.drop_index('idx_bill_active_analysis', table_name='ai_analysis')
    op.drop_table('ai_analysis')
    
    # Restore the unique constraint on bill table
    with op.batch_alter_table('bill', schema=None) as batch_op:
        batch_op.create_unique_constraint(batch_op.f('uq_bill_congress_type_number_version'), ['congress', 'bill_type', 'bill_number', 'version'])
