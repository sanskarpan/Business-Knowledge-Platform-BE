"""
Database initialization script
Run this to set up the database tables
"""
import os
import sys
from sqlalchemy import create_engine
from app.database import Base
from app.models import User, Document, DocumentChunk, ChatSession, ChatMessage, SearchQuery, UserActivity
from app.config import settings

def init_database():
    """Initialize database with all tables"""
    try:
        print("Creating database tables...")
        engine = create_engine(settings.database_url)
        
        # Create all tables
        Base.metadata.create_all(bind=engine)
        
        print("Database tables created successfully!")
        print("Tables created:")
        for table_name in Base.metadata.tables.keys():
            print(f"  - {table_name}")
            
    except Exception as e:
        print(f"Error creating database: {e}")
        sys.exit(1)

if __name__ == "__main__":
    init_database()