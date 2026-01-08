# backend/models.py
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from database import Base
import uuid
import datetime

# 1. Doctor Table
class Doctor(Base):
    __tablename__ = "doctors"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    phone = Column(String, unique=True, index=True)
    clinic_address = Column(String)
    
    # Auto-generate a unique link code (e.g., 550e8400-e29b...)
    uuid_code = Column(String, unique=True, default=lambda: str(uuid.uuid4()))

# 2. Pharmacy Table
class Pharmacy(Base):
    __tablename__ = "pharmacies"

    id = Column(Integer, primary_key=True, index=True)
    store_name = Column(String, index=True)
    phone = Column(String)
    
    # We store the inventory list as a simple Text/String (JSON format)
    # Example: '{"Ashwagandha": 10, "Triphala": 5}'
    inventory_data = Column(String, default="{}")

# 3. Prescription Table (For Patient App & Order History)
class Prescription(Base):
    __tablename__ = "prescriptions"

    id = Column(Integer, primary_key=True, index=True)
    
    # Link to the Doctor who uploaded it
    doctor_id = Column(Integer, ForeignKey("doctors.id"))
    
    # The patient's phone number (used for Login)
    patient_phone = Column(String, index=True)
    
    # Name of the image file stored in 'uploads' folder
    image_url = Column(String)
    
    # List of medicines found by AI (stored as JSON string)
    # Example: '["Ashwagandha", "Brahmi"]'
    extracted_medicines = Column(String) 
    
    # Order Status (Pending, Ready to Order, Completed)
    status = Column(String, default="Pending")
    
    # Timestamp
    created_at = Column(DateTime, default=datetime.datetime.utcnow)