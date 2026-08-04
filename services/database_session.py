"""
Independent Database Session for Workflow Services

This module provides a database session that's independent of the Flask app context,
allowing workflow services to run without circular import issues.
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from contextlib import contextmanager

# Database configuration
DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///instance/legislative_analysis.db')

# Create engine and session factory
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@contextmanager
def get_db_session():
    """
    Context manager for database sessions.
    Automatically handles session cleanup and rollback on errors.
    
    Usage:
        with get_db_session() as session:
            # Use session here
            bill = session.query(Bill).first()
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

def create_db_session():
    """
    Create a new database session.
    Caller is responsible for closing the session.
    
    Returns:
        SQLAlchemy session
    """
    return SessionLocal()

# For backward compatibility, create a global session instance
# This is used by the WorkflowOrchestrator which was already designed to use a single session
global_session = SessionLocal()

def get_global_session():
    """Get the global session instance (for backward compatibility)"""
    return global_session

def close_global_session():
    """Close the global session"""
    global global_session
    if global_session:
        global_session.close()
        global_session = SessionLocal()