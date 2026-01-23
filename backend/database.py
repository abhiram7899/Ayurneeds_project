# database.py
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

# 1. Load secrets immediately
load_dotenv()

# 2. Get the Database URL
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL")

# 3. Safety Check: If URL is missing, print error but don't crash the import
if not SQLALCHEMY_DATABASE_URL:
    print("❌ CRITICAL ERROR: DATABASE_URL is missing from .env file!")
    # We set a dummy URL so the app can at least start and show the error log
    SQLALCHEMY_DATABASE_URL = "sqlite:///./error_fallback.db"

# 4. Create the Database Engine
try:
    # 'pool_pre_ping=True' helps prevent connection drops
    engine = create_engine(SQLALCHEMY_DATABASE_URL, pool_pre_ping=True)
    
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base = declarative_base()
    print("✅ Database engine initialized successfully.")

except Exception as e:
    print(f"❌ Database Connection Failed: {e}")
    # Create a dummy Base to prevent 'NameError' in main.py
    Base = declarative_base()
    SessionLocal = None 
    engine = None

def get_db():
    if SessionLocal is None:
        raise Exception("Database not connected")
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()