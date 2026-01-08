from fastapi import FastAPI, File, UploadFile, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, Integer, String, Text, ForeignKey, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from typing import List, Optional
from pydantic import BaseModel
import datetime
import shutil
import os
import json
import requests
import uuid
from thefuzz import process 

# IMPORT YOUR AI ENGINE
import ai_engine

# ==========================================
# ⚙️ CONFIGURATION
# ==========================================
# 🔴 DATABASE
# ✅ FIX 1: Username is 'postgres.peutakneeduffikaovvz' (Not just 'postgres')
# ✅ FIX 2: Added '?sslmode=require' at the end
SQLALCHEMY_DATABASE_URL = "postgresql://postgres.peutakneeduffikaovvz:Ayurneeds2026Project@aws-0-ap-south-1.pooler.supabase.com:6543/postgres?sslmode=require"
# 🔴 TELEGRAM KEYS
TELEGRAM_BOT_TOKEN = "8593706542:AAG_EsJxPZiqLQddiMgAlhSinxtaJO-hswI"
TELEGRAM_CHAT_ID = "6293824721"

# 🔴 LIVE SERVER URLS
RENDER_BACKEND_URL = "https://ayurneeds-project.vercel.app"
LIVE_WEBSITE_URL = "https://www.ayurneeds.com"

# ✅ Vercel Fix: Use the temporary directory
import tempfile

UPLOAD_DIR = tempfile.gettempdir()
# No need to makedirs, /tmp always exists

# ==========================================
# 🗄️ DATABASE SETUP
# ==========================================
engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- 1. Doctor Model ---
class Doctor(Base):
    __tablename__ = "doctors"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    uuid_code = Column(String, unique=True, index=True)
    phone = Column(String, nullable=True)
    clinic_address = Column(String, nullable=True)

# --- 2. Prescription Model ---
class Prescription(Base):
    __tablename__ = "prescriptions"
    id = Column(Integer, primary_key=True, index=True)
    doctor_id = Column(Integer, ForeignKey("doctors.id"))
    patient_phone = Column(String)
    image_url = Column(String)
    extracted_medicines = Column(Text)
    
    # Patient Order Fields
    patient_name = Column(String, nullable=True)
    address = Column(String, nullable=True) 
    payment_mode = Column(String, nullable=True)
    status = Column(String, default="Pending Approval")
    total_amount = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    doctor = relationship("Doctor")

# --- 3. Pharmacy Inventory Models ---
class Pharmacy(Base):
    __tablename__ = "pharmacies"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    location = Column(String)

class PharmacyStock(Base):
    __tablename__ = "pharmacy_stock"
    id = Column(Integer, primary_key=True, index=True)
    pharmacy_id = Column(Integer, ForeignKey("pharmacies.id"))
    medicine_name = Column(String)
    qty = Column(Integer)
    price = Column(Integer)
    image_url = Column(String, default="default.jpg") 
    
    pharmacy = relationship("Pharmacy")

class CompletedOrder(Base):
    __tablename__ = "completed_orders"
    id = Column(Integer, primary_key=True, index=True)
    original_pres_id = Column(Integer)
    customer_name = Column(String)
    phone_number = Column(String)
    address = Column(String)
    medicines_json = Column(Text)
    total_amount = Column(Integer)
    transaction_id = Column(String)
    order_date = Column(DateTime, default=datetime.datetime.utcnow)

# Create all tables
Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ==========================================
# 🚀 FASTAPI APP
# ==========================================
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Input Models ---
class DoctorCreate(BaseModel):
    name: str
    phone: str
    clinic_address: str

class LoginRequest(BaseModel):
    phone: str

class OrderConfirm(BaseModel):
    patient_name: str
    address_line: str
    pincode: str
    landmark: str
    payment_mode: str
    phone: Optional[str] = None
    final_medicines: List[dict] 

class ContactForm(BaseModel): 
    name: str
    phone: str
    email: str
    message: str

# --- Helper: Telegram Alert ---
def send_telegram_alert(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": message})
    except:
        pass

# --- Helper: Real Stock Check ---
def check_real_stock(medicines, db: Session):
    report = []
    all_stock = db.query(PharmacyStock).all()
    stock_map = {item.medicine_name: item for item in all_stock}
    stock_names = list(stock_map.keys())

    for med in medicines:
        med_name = med.get('name', '')
        best_match, score = process.extractOne(med_name, stock_names)
        
        if score > 60:
            stock = stock_map[best_match]
            report.append(f"✅ {med_name} (Matched: {stock.medicine_name}): Found at {stock.pharmacy.name} (Qty: {stock.qty})")
        else:
            report.append(f"❌ {med_name}: Out of Stock / Unknown")
            
    return "\n".join(report)

# ==========================================
# 📡 ENDPOINTS
# ==========================================

@app.get("/")
def home():
    return {"message": "Ayurneeds Backend Running Live"}

# 1. REGISTER DOCTOR
@app.post("/register-doctor/")
def register_doctor(doctor: DoctorCreate, db: Session = Depends(get_db)):
    new_uuid = str(uuid.uuid4())
    
    new_doc = Doctor(
        name=doctor.name, 
        uuid_code=new_uuid,
        phone=doctor.phone,
        clinic_address=doctor.clinic_address
    )
    db.add(new_doc)
    db.commit()
    return {"status": "success", "unique_uuid": new_uuid}

# 2. DOCTOR UPLOAD
@app.post("/upload-prescription/{doctor_uuid}")
def upload_prescription(
    doctor_uuid: str, file: UploadFile = File(None), 
    manual_phone: str = Form(...), manual_medicines: str = Form("[]"), 
    db: Session = Depends(get_db)
):
    doctor = db.query(Doctor).filter(Doctor.uuid_code == doctor_uuid).first()
    if not doctor: raise HTTPException(404, "Invalid Doctor")
    
    filename = "manual"
    ai_results = []
    
    if file:
        filename = file.filename
        loc = f"{UPLOAD_DIR}/{filename}"
        with open(loc, "wb") as buffer: shutil.copyfileobj(file.file, buffer)
        try:
            analysis = ai_engine.analyze_prescription_image(loc)
            ai_results = analysis.get("medicines", [])
        except: ai_results = []

    try: 
        manual = [{"name": m, "qty": "Standard"} for m in json.loads(manual_medicines)]
    except: 
        manual = []

    final_list = ai_results + manual
    if not final_list: raise HTTPException(400, "No medicines found.")

    clean_phone = manual_phone.replace(" ", "").strip()

    new_pres = Prescription(
        doctor_id=doctor.id, patient_phone=clean_phone,
        image_url=filename, extracted_medicines=json.dumps(final_list), 
        status="Pending Approval"
    )
    db.add(new_pres)
    db.commit()
    db.refresh(new_pres)

    # --- TELEGRAM ALERTS ---
    med_names = ", ".join([m['name'] for m in final_list])
    msg1 = f"🤖 *Prescription Received*\n📄 ID: {new_pres.id}\n👨‍⚕️ Dr. {doctor.name}\n💊 Medicines:\n{med_names}"
    send_telegram_alert(msg1)

    stock_report = check_real_stock(final_list, db)
    # ✅ LINK TO RENDER BACKEND
    confirm_link = f"{RENDER_BACKEND_URL}/admin/approve/{new_pres.id}"
    
    msg2 = f"🏪 *Pharmacy Stock Report*\n\n{stock_report}\n\n👇 *ACTION REQUIRED*\nClick to Confirm & Notify Patient:\n{confirm_link}"
    send_telegram_alert(msg2)
    
    return {"status": "success", "medicines": [m['name'] for m in final_list], "matches": final_list}

# 3. ADMIN APPROVE -> OPEN WHATSAPP
@app.get("/admin/approve/{pres_id}", response_class=HTMLResponse)
def approve_prescription(pres_id: int, db: Session = Depends(get_db)):
    pres = db.query(Prescription).filter(Prescription.id == pres_id).first()
    if not pres: return "<h1>Error: Prescription Not Found</h1>"
    
    pres.status = "Approved"
    db.commit()

    # ✅ LINK TO LIVE WEBSITE
    patient_link = f"{LIVE_WEBSITE_URL}/patient_login.html?id={pres.id}"
    
    phone = pres.patient_phone.replace(" ", "").replace("-", "")
    if len(phone) == 10:
        phone = "91" + phone 

    message = f"Hello {pres.patient_name or 'Customer'}, your prescription is ready! ✅%0a%0aClick here to confirm your delivery address:%0a{patient_link}"
    whatsapp_url = f"https://wa.me/{phone}?text={message}"

    return f"""
    <html>
        <head>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body {{ font-family: sans-serif; text-align: center; padding: 20px; background-color: #f0f2f5; }}
                .card {{ background: white; padding: 30px; border-radius: 15px; box-shadow: 0 4px 10px rgba(0,0,0,0.1); max-width: 400px; margin: 0 auto; }}
                h1 {{ color: #27ae60; }}
                p {{ color: #555; font-size: 16px; }}
                .btn {{ 
                    display: block; width: 100%; padding: 15px; margin-top: 20px; 
                    background-color: #25D366; color: white; font-size: 18px; font-weight: bold; 
                    text-decoration: none; border-radius: 8px; box-sizing: border-box;
                }}
                .btn:hover {{ background-color: #1ebe57; }}
            </style>
        </head>
        <body>
            <div class="card">
                <h1>✅ Approved!</h1>
                <p>Prescription #{pres.id} is confirmed.</p>
                <p>Send the link to the patient now:</p>
                <a href="{whatsapp_url}" class="btn">👉 Send on WhatsApp</a>
                <br>
                <small style="color:#999;">Patient Phone: +{phone}</small>
            </div>
        </body>
    </html>
    """

# 4. PATIENT LOGIN
@app.post("/verify-patient/{pres_id}")
def verify_patient(pres_id: int, login: LoginRequest, db: Session = Depends(get_db)):
    pres = db.query(Prescription).filter(Prescription.id == pres_id).first()
    if not pres: raise HTTPException(404, "Prescription not found")

    if pres.patient_phone == login.phone.strip():
        return {"status": "success", "message": "Verified"}
    else:
        raise HTTPException(401, "Phone mismatch")

# 5. GET DATA
@app.get("/get-prescription/{pres_id}")
def get_data(pres_id: int, db: Session = Depends(get_db)):
    pres = db.query(Prescription).filter(Prescription.id == pres_id).first()
    if not pres: raise HTTPException(404, "Not Found")
    
    raw_medicines = json.loads(pres.extracted_medicines)
    final_bill = []
    grand_total = 0

    all_stock = db.query(PharmacyStock).all()
    stock_map = {item.medicine_name: item for item in all_stock}
    stock_names = list(stock_map.keys())

    for med in raw_medicines:
        written_name = med.get('name')
        try:
            raw_qty = str(med.get('qty', '1'))
            qty_number = int(''.join(filter(str.isdigit, raw_qty)))
            if qty_number == 0: qty_number = 1
        except:
            qty_number = 1

        best_match, score = process.extractOne(written_name, stock_names)
        
        if score > 60:
            matched_stock = stock_map[best_match]
            price = matched_stock.price
            final_name = matched_stock.medicine_name 
            match_status = "Found"
        else:
            price = 0
            final_name = written_name 
            match_status = "Not Found"

        total_cost = price * qty_number
        grand_total += total_cost

        final_bill.append({
            "name": final_name,
            "original_name": written_name,
            "qty": qty_number,
            "price": price,
            "total": total_cost,
            "status": match_status
        })

    return {
        "doctor": pres.doctor.name,
        "medicines": final_bill,
        "grand_total": grand_total,
        "status": pres.status
    }

# 6. REQUEST ORDER
@app.post("/confirm-order/{pres_id}")
def confirm_order(pres_id: int, order: OrderConfirm, db: Session = Depends(get_db)):
    pres = db.query(Prescription).filter(Prescription.id == pres_id).first()
    if not pres: raise HTTPException(404, "Not Found")

    full_address = f"{order.address_line}, {order.landmark}, Pin: {order.pincode}"

    bill_total = sum(item['price'] * item['qty'] for item in order.final_medicines)

    pres.patient_name = order.patient_name
    pres.address = full_address
    pres.payment_mode = order.payment_mode 
    pres.extracted_medicines = json.dumps(order.final_medicines)
    pres.total_amount = bill_total
    pres.status = "Verifying Payment"
    db.commit()

    # ✅ LINK TO RENDER
    approve_link = f"{RENDER_BACKEND_URL}/admin/payment-action/{pres_id}/approve"
    decline_link = f"{RENDER_BACKEND_URL}/admin/payment-action/{pres_id}/decline"

    med_text = ", ".join([f"{m['name']} (x{m['qty']})" for m in order.final_medicines])
    
    msg = (
        f"💰 *PAYMENT VERIFICATION NEEDED*\n"
        f"👤 {order.patient_name}\n"
        f"💵 Total Bill: ₹{bill_total}\n"
        f"🆔 Txn: {order.payment_mode}\n"
        f"💊 Items: {med_text}\n\n"
        f"👇 *Check Bank App & Decide:*\n"
        f"✅ [APPROVE ORDER]({approve_link})\n"
        f"❌ [DECLINE ORDER]({decline_link})"
    )
    send_telegram_alert(msg)

    return {"status": "pending_verification"}   

# 7. DROPDOWN LIST
@app.get("/doctor/medicine-list")
def get_master_medicine_list(db: Session = Depends(get_db)):
    results = db.query(PharmacyStock.medicine_name).distinct().all()
    clean_list = [row.medicine_name for row in results]
    return clean_list

# 8. STORE CATALOG
@app.get("/store/all-medicines")
def get_store_inventory(db: Session = Depends(get_db)):
    stocks = db.query(PharmacyStock).filter(PharmacyStock.price > 0).all()
    
    inventory = []
    for item in stocks:
        inventory.append({
            "name": item.medicine_name,
            "price": item.price,
            "image": item.image_url, 
            "pharmacy": item.pharmacy.name
        })
    return inventory

# 9. CONTACT FORM
@app.post("/contact-us")
def submit_contact_form(form: ContactForm):
    msg = f"📩 *New Contact Inquiry*\n\n👤 Name: {form.name}\n📞 Phone: {form.phone}\n📧 Email: {form.email}\n\n📝 Message:\n{form.message}"
    send_telegram_alert(msg)
    return {"status": "success"}

# 10. ADMIN PAYMENT ACTIONS
@app.get("/admin/payment-action/{pres_id}/{action}", response_class=HTMLResponse)
def admin_payment_action(pres_id: int, action: str, db: Session = Depends(get_db)):
    pres = db.query(Prescription).filter(Prescription.id == pres_id).first()
    if not pres: return "Order not found"

    if action == "approve":
        pres.status = "Ordered"
        
        existing_order = db.query(CompletedOrder).filter(CompletedOrder.original_pres_id == pres.id).first()
        
        if not existing_order:
            new_sale = CompletedOrder(
                original_pres_id = pres.id,
                customer_name = pres.patient_name,
                phone_number = pres.patient_phone,
                address = pres.address,
                medicines_json = pres.extracted_medicines,
                total_amount = pres.total_amount,
                transaction_id = pres.payment_mode
            )
            db.add(new_sale)
        
        message = "✅ Payment Approved! Data saved to Sales Database."
        color = "green"

    elif action == "decline":
        pres.status = "Payment Failed"
        message = "❌ Payment Declined. User notified."
        color = "red"
    
    db.commit()

    return f"""
    <html>
        <body style="text-align:center; font-family:sans-serif; padding:50px;">
            <h1 style="color:{color}">{message}</h1>
            <p>You can close this window.</p>
        </body>
    </html>
    """

# 11. CHECK STATUS
@app.get("/check-order-status/{pres_id}")
def check_status(pres_id: int, db: Session = Depends(get_db)):
    pres = db.query(Prescription).filter(Prescription.id == pres_id).first()
    if not pres: return {"status": "error"}
    return {"status": pres.status}

# 12. STORE CHECKOUT
@app.post("/store/checkout")
def store_checkout(order: OrderConfirm, db: Session = Depends(get_db)):
    dummy_doc = db.query(Doctor).first()
    if not dummy_doc: 
        dummy_doc = Doctor(name="Online Store", uuid_code="store_admin", phone="000", clinic_address="Online")
        db.add(dummy_doc)
        db.commit()

    full_address = f"{order.address_line}, {order.landmark}, Pin: {order.pincode}"

    bill_total = sum(item['price'] * item['qty'] for item in order.final_medicines)

    new_order = Prescription(
        doctor_id=dummy_doc.id,
        patient_name=order.patient_name,
        patient_phone=order.phone,
        address=full_address,
        payment_mode=order.payment_mode,
        extracted_medicines=json.dumps(order.final_medicines),
        total_amount=bill_total,
        status="Verifying Payment",
        image_url="STORE_PURCHASE", 
        created_at=datetime.datetime.utcnow()
    )
    db.add(new_order)
    db.commit()
    db.refresh(new_order)

    # ✅ LINK TO RENDER
    approve_link = f"{RENDER_BACKEND_URL}/admin/payment-action/{new_order.id}/approve"
    decline_link = f"{RENDER_BACKEND_URL}/admin/payment-action/{new_order.id}/decline"

    med_text = ", ".join([f"{m['name']} (x{m['qty']})" for m in order.final_medicines])
    
    msg = (
        f"🛒 *NEW STORE ORDER (Verifying)*\n"
        f"👤 {order.patient_name}\n"
        f"📞 {order.phone}\n"
        f"💵 Total Bill: ₹{bill_total}\n"
        f"🆔 Txn: {order.payment_mode}\n"
        f"📦 Items: {med_text}\n"
        f"🏠 Addr: {full_address}\n\n"
        f"👇 *Verify Payment & Decide:*\n"
        f"✅ [APPROVE ORDER]({approve_link})\n"
        f"❌ [DECLINE ORDER]({decline_link})"
    )
    send_telegram_alert(msg)

    return {"status": "pending_verification", "order_id": new_order.id}