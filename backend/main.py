# main.py
from fastapi import FastAPI, File, UploadFile, Form, Depends, HTTPException, Body
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime
from sqlalchemy.orm import Session, relationship
from typing import List, Optional
from pydantic import BaseModel
import datetime
import os
import json
import requests
import uuid
from thefuzz import process 
from dotenv import load_dotenv

# 🚨 LOAD ENV VARS FIRST
load_dotenv()

# ✅ IMPORT LOCAL MODULES
import ai_engine
from database import engine, SessionLocal, Base, get_db

# ==========================================
# ⚙️ CONFIGURATION
# ==========================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123") 

# LIVE URLs (Update if needed)
RENDER_BACKEND_URL = "https://ayurneeds-project.vercel.app"
LIVE_WEBSITE_URL = "https://ayurneeds.com"

# ==========================================
# 🗄️ DATABASE MODELS
# ==========================================
class Doctor(Base):
    __tablename__ = "doctors"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    uuid_code = Column(String, unique=True, index=True)
    phone = Column(String, nullable=True)
    clinic_address = Column(String, nullable=True)

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

# Create Tables
if engine:
    Base.metadata.create_all(bind=engine)

# ==========================================
# 🚀 FASTAPI APP SETUP
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
    name: str; phone: str; clinic_address: str

class LoginRequest(BaseModel):
    phone: str

class AdminLoginRequest(BaseModel):
    password: str

class OrderConfirm(BaseModel):
    patient_name: str; address_line: str; pincode: str; landmark: str
    payment_mode: str; phone: Optional[str] = None; final_medicines: List[dict] 

class ContactForm(BaseModel): 
    name: str; phone: str; email: str; message: str

# --- Helpers ---
def send_telegram_alert(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID: return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        # 🛡️ FIX: Disable web preview so Telegram doesn't auto-click links
        requests.post(url, data={
            "chat_id": TELEGRAM_CHAT_ID, 
            "text": message, 
            "parse_mode": "Markdown",
            "disable_web_page_preview": True 
        })
    except Exception as e: print(f"Telegram Error: {e}")

def check_real_stock(medicines, db: Session):
    report = []
    try:
        all_stock = db.query(PharmacyStock).all()
        stock_map = {item.medicine_name: item for item in all_stock}
        stock_names = list(stock_map.keys())

        for med in medicines:
            med_name = med.get('name', '')
            best_match, score = process.extractOne(med_name, stock_names) if stock_names else (None, 0)
            
            if score > 80:
                stock = stock_map[best_match]
                report.append(f"✅ {med_name} (Matched: {stock.medicine_name}): Found at {stock.pharmacy.name} (Qty: {stock.qty})")
            else:
                report.append(f"❌ {med_name}: Out of Stock / Unknown")
    except Exception as e: report.append(f"Stock Error: {str(e)}")
    return "\n".join(report)

# ==========================================
# 📡 API ENDPOINTS
# ==========================================

@app.get("/")
def home():
    return {"message": "Ayurneeds Backend Running Live (Secured)"}

@app.post("/admin/login")
def admin_login(data: AdminLoginRequest):
    if data.password == ADMIN_PASSWORD:
        return {"status": "success", "token": "access_granted"}
    raise HTTPException(status_code=401, detail="Invalid Password")

# 1. REGISTER DOCTOR
@app.post("/register-doctor/")
def register_doctor(doctor: DoctorCreate, db: Session = Depends(get_db)):
    new_uuid = str(uuid.uuid4())
    new_doc = Doctor(name=doctor.name, uuid_code=new_uuid, phone=doctor.phone, clinic_address=doctor.clinic_address)
    db.add(new_doc); db.commit()
    return {"status": "success", "unique_uuid": new_uuid}

# 2. DOCTOR UPLOAD
@app.post("/upload-prescription/{doctor_uuid}")
async def upload_prescription(
    doctor_uuid: str, file: UploadFile = File(None), 
    manual_phone: str = Form(...), manual_medicines: str = Form("[]"), 
    db: Session = Depends(get_db)
):
    doctor = db.query(Doctor).filter(Doctor.uuid_code == doctor_uuid).first()
    if not doctor: raise HTTPException(404, "Invalid Doctor Link")
    
    filename = file.filename if file else "manual_entry"
    ai_results = []
    
    if file:
        try:
            contents = await file.read()
            ai_results = ai_engine.analyze_prescription(contents)
        except Exception as e: print(f"Upload Error: {e}")

    try: manual = [{"name": m, "qty": "Standard"} for m in json.loads(manual_medicines)]
    except: manual = []

    ai_formatted = [{"name": m, "qty": "Standard"} for m in ai_results] if isinstance(ai_results, list) else []
    final_list = ai_formatted + manual
    
    if not final_list: raise HTTPException(400, "No medicines found.")

    new_pres = Prescription(
        doctor_id=doctor.id, patient_phone=manual_phone.replace(" ", "").strip(),
        image_url=filename, extracted_medicines=json.dumps(final_list), 
        status="Pending Approval"
    )
    db.add(new_pres); db.commit(); db.refresh(new_pres)

    med_names = ", ".join([m['name'] for m in final_list])
    msg1 = f"🤖 *Prescription Received*\n📄 ID: {new_pres.id}\n👨‍⚕️ Dr. {doctor.name}\n💊 Medicines:\n{med_names}"
    send_telegram_alert(msg1)

    stock_report = check_real_stock(final_list, db)
    # Link goes to Decision Page (Safe)
    confirm_link = f"{RENDER_BACKEND_URL}/admin/decision-page/{new_pres.id}"
    msg2 = f"🏪 *Pharmacy Stock Report*\n\n{stock_report}\n\n👇 *ACTION REQUIRED*\n[Click to Verify Stock]({confirm_link})"
    send_telegram_alert(msg2)
    
    return {"status": "success", "medicines": [m['name'] for m in final_list]}

# 🆕 INTERMEDIARY DECISION PAGE (Prevents Auto-Click)
@app.get("/admin/decision-page/{pres_id}", response_class=HTMLResponse)
def decision_page(pres_id: int, db: Session = Depends(get_db)):
    pres = db.query(Prescription).filter(Prescription.id == pres_id).first()
    if not pres: return "Order not found"
    
    return f"""
    <html>
    <head><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>body{{font-family:sans-serif;padding:20px;text-align:center;background:#f4f4f4;}} .card{{background:white;padding:30px;border-radius:15px;max-width:500px;margin:auto;}} .btn{{display:block;padding:15px;margin:10px 0;border-radius:8px;text-decoration:none;color:white;font-weight:bold;}} .approve{{background:#27ae60;}} .decline{{background:#c0392b;}}</style>
    </head>
    <body>
        <div class="card">
            <h2>🛡️ Admin Decision</h2>
            <p><strong>Order ID:</strong> #{pres.id}</p>
            <p><strong>Status:</strong> {pres.status}</p>
            <hr>
            <a href="{RENDER_BACKEND_URL}/admin/approve/{pres_id}" class="btn approve">✅ Approve & Notify Patient</a>
        </div>
    </body>
    </html>
    """

# 3. ADMIN APPROVE (ACTION)
@app.get("/admin/approve/{pres_id}", response_class=HTMLResponse)
def approve_prescription(pres_id: int, db: Session = Depends(get_db)):
    pres = db.query(Prescription).filter(Prescription.id == pres_id).first()
    if not pres: return "<h1>Error: Prescription Not Found</h1>"
    
    pres.status = "Approved"
    db.commit()

    patient_link = f"{LIVE_WEBSITE_URL}/patient_login.html?id={pres.id}"
    phone = pres.patient_phone.replace(" ", "").replace("-", "")
    if len(phone) == 10: phone = "91" + phone 
    
    whatsapp_url = f"https://wa.me/{phone}?text=Hello {pres.patient_name or 'Customer'}, your prescription is ready! Click here: {patient_link}"

    return f"""<html><body style="text-align:center; padding:50px;">
    <h1 style="color:green">✅ Approved!</h1><p>Status updated.</p>
    <a href="{whatsapp_url}" style="background:#25D366; color:white; padding:15px; text-decoration:none; border-radius:5px;">👉 Send on WhatsApp</a>
    </body></html>"""

# 4. PATIENT LOGIN
@app.post("/verify-patient/{pres_id}")
def verify_patient(pres_id: int, login: LoginRequest, db: Session = Depends(get_db)):
    pres = db.query(Prescription).filter(Prescription.id == pres_id).first()
    if pres and pres.patient_phone == login.phone.strip(): return {"status": "success"}
    raise HTTPException(401, "Phone mismatch")

# 5. GET DATA
@app.get("/get-prescription/{pres_id}")
def get_data(pres_id: int, db: Session = Depends(get_db)):
    pres = db.query(Prescription).filter(Prescription.id == pres_id).first()
    if not pres: raise HTTPException(404, "Not Found")
    
    raw_medicines = json.loads(pres.extracted_medicines)
    final_bill = []
    grand_total = 0
    
    # Simple stock check logic
    try:
        all_stock = db.query(PharmacyStock).all()
        stock_map = {item.medicine_name: item for item in all_stock}
        stock_names = list(stock_map.keys())
    except: stock_names = []

    for med in raw_medicines:
        written_name = med.get('name')
        qty = 1
        best_match, score = process.extractOne(written_name, stock_names) if stock_names else (None, 0)
        
        if score > 60:
            matched = stock_map[best_match]
            price = matched.price; final_name = matched.medicine_name; status = "Found"
        else:
            price = 0; final_name = written_name; status = "Not Found"

        total = price * qty; grand_total += total
        final_bill.append({"name": final_name, "original_name": written_name, "qty": qty, "price": price, "total": total, "status": status})

    return {"doctor": pres.doctor.name if pres.doctor else "Store", "medicines": final_bill, "grand_total": grand_total, "status": pres.status}

# 6. REQUEST ORDER (Patient Dashboard)
@app.post("/confirm-order/{pres_id}")
def confirm_order(pres_id: int, order: OrderConfirm, db: Session = Depends(get_db)):
    pres = db.query(Prescription).filter(Prescription.id == pres_id).first()
    if not pres: raise HTTPException(404, "Not Found")

    pres.status = "Verifying Payment" # 👈 IMPORTANT: Resets status
    pres.patient_name = order.patient_name
    pres.address = f"{order.address_line}, {order.landmark}, Pin: {order.pincode}"
    pres.payment_mode = order.payment_mode 
    pres.extracted_medicines = json.dumps(order.final_medicines)
    pres.total_amount = sum(item['price'] * item['qty'] for item in order.final_medicines)
    db.commit()

    # Link to DECISION PAGE, not action
    decision_link = f"{RENDER_BACKEND_URL}/admin/payment-decision/{pres_id}"
    
    med_text = ", ".join([f"{m['name']} (x{m['qty']})" for m in order.final_medicines])
    msg = (f"💰 *PAYMENT VERIFICATION*\n👤 {order.patient_name}\n💵 ₹{pres.total_amount}\n🆔 {order.payment_mode}\n"
           f"👇 *Click to Verify:*\n[Open Admin Decision Page]({decision_link})")
    send_telegram_alert(msg)
    return {"status": "pending_verification"}   

# 🆕 PAYMENT DECISION PAGE (Prevents Auto-Click)
@app.get("/admin/payment-decision/{pres_id}", response_class=HTMLResponse)
def payment_decision_page(pres_id: int, db: Session = Depends(get_db)):
    pres = db.query(Prescription).filter(Prescription.id == pres_id).first()
    
    return f"""
    <html>
    <head><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>body{{font-family:sans-serif;padding:20px;text-align:center;background:#f4f4f4;}} .card{{background:white;padding:30px;border-radius:15px;max-width:500px;margin:auto;}} .btn{{display:block;padding:15px;margin:10px 0;border-radius:8px;text-decoration:none;color:white;font-weight:bold;}} .approve{{background:#27ae60;}} .decline{{background:#c0392b;}}</style>
    </head>
    <body>
        <div class="card">
            <h2>💰 Payment Verification</h2>
            <p><strong>Customer:</strong> {pres.patient_name}</p>
            <p><strong>Amount:</strong> ₹{pres.total_amount}</p>
            <p><strong>Txn ID:</strong> {pres.payment_mode}</p>
            <hr>
            <p>Please check your Bank App. If money received:</p>
            <a href="{RENDER_BACKEND_URL}/admin/payment-action/{pres_id}/approve" class="btn approve">✅ Yes, Approve Order</a>
            <a href="{RENDER_BACKEND_URL}/admin/payment-action/{pres_id}/decline" class="btn decline">❌ No, Decline</a>
        </div>
    </body>
    </html>
    """

# 7. DROPDOWN LIST
@app.get("/doctor/medicine-list")
def get_master_medicine_list(db: Session = Depends(get_db)):
    results = db.query(PharmacyStock.medicine_name).distinct().all()
    return [row.medicine_name for row in results]

# 8. STORE CATALOG
@app.get("/store/all-medicines")
def get_store_inventory(db: Session = Depends(get_db)):
    stocks = db.query(PharmacyStock).filter(PharmacyStock.price > 0).all()
    return [{"name": i.medicine_name, "price": i.price, "image": i.image_url, "pharmacy": i.pharmacy.name} for i in stocks]

# 9. CONTACT FORM
@app.post("/contact-us")
def submit_contact_form(form: ContactForm):
    send_telegram_alert(f"📩 *Contact*\n{form.name}\n{form.phone}\n{form.message}")
    return {"status": "success"}

# 10. ADMIN PAYMENT ACTION (ACTUAL LOGIC)
@app.get("/admin/payment-action/{pres_id}/{action}", response_class=HTMLResponse)
def admin_payment_action(pres_id: int, action: str, db: Session = Depends(get_db)):
    pres = db.query(Prescription).filter(Prescription.id == pres_id).first()
    if not pres: return "Order not found"

    if action == "approve":
        pres.status = "Ordered"
        existing = db.query(CompletedOrder).filter(CompletedOrder.original_pres_id == pres.id).first()
        if not existing:
            new_sale = CompletedOrder(
                original_pres_id = pres.id, customer_name = pres.patient_name,
                phone_number = pres.patient_phone, address = pres.address,
                medicines_json = pres.extracted_medicines, total_amount = pres.total_amount,
                transaction_id = pres.payment_mode
            )
            db.add(new_sale)
        message, color = "✅ Payment Approved & Saved!", "green"
    else:
        pres.status = "Payment Failed"
        message, color = "❌ Payment Declined.", "red"
    
    db.commit()
    return f"<html><body style='text-align:center; padding:50px;'><h1 style='color:{color}'>{message}</h1><p>You can close this window.</p></body></html>"

# 11. CHECK STATUS
@app.get("/check-order-status/{pres_id}")
def check_status(pres_id: int, db: Session = Depends(get_db)):
    pres = db.query(Prescription).filter(Prescription.id == pres_id).first()
    return {"status": pres.status if pres else "error"}

# 12. STORE CHECKOUT
@app.post("/store/checkout")
def store_checkout(order: OrderConfirm, db: Session = Depends(get_db)):
    dummy_doc = db.query(Doctor).filter(Doctor.uuid_code == "store_admin").first()
    if not dummy_doc: 
        dummy_doc = Doctor(name="Online Store", uuid_code="store_admin", phone="000", clinic_address="Online")
        db.add(dummy_doc); db.commit()

    full_address = f"{order.address_line}, {order.landmark}, Pin: {order.pincode}"
    bill_total = sum(item['price'] * item['qty'] for item in order.final_medicines)

    new_order = Prescription(
        doctor_id=dummy_doc.id, patient_name=order.patient_name,
        patient_phone=order.phone, address=full_address,
        payment_mode=order.payment_mode, extracted_medicines=json.dumps(order.final_medicines),
        total_amount=bill_total, status="Verifying Payment", # 👈 EXPLICIT STATUS
        image_url="STORE_PURCHASE", created_at=datetime.datetime.utcnow()
    )
    db.add(new_order); db.commit(); db.refresh(new_order)

    # Link to DECISION PAGE
    decision_link = f"{RENDER_BACKEND_URL}/admin/payment-decision/{new_order.id}"
    med_text = ", ".join([f"{m['name']} (x{m['qty']})" for m in order.final_medicines])
    
    msg = (f"🛒 *NEW STORE ORDER*\n👤 {order.patient_name}\n💵 ₹{bill_total}\n🆔 {order.payment_mode}\n"
           f"👇 *Click to Verify:*\n[Open Admin Decision Page]({decision_link})")
    send_telegram_alert(msg)
    return {"status": "pending_verification", "order_id": new_order.id}