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

# 🚨 CRITICAL FIX: Load Environment Variables BEFORE local imports
load_dotenv()

# ✅ NOW import local modules (since they depend on env vars)
import ai_engine
from database import engine, SessionLocal, Base, get_db

# ==========================================
# ⚙️ CONFIGURATION
# ==========================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123") # Default fallback

# Live URLs (Update these if your domain changes)
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

# Create Tables (Safely)
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
    name: str
    phone: str
    clinic_address: str

class LoginRequest(BaseModel):
    phone: str

class AdminLoginRequest(BaseModel):
    password: str

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

# --- Helpers ---
def send_telegram_alert(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram keys missing in .env")
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": message})
    except Exception as e:
        print(f"Telegram Error: {e}")

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
    except Exception as e:
        report.append(f"Stock Check Error: {str(e)}")
            
    return "\n".join(report)

# ==========================================
# 📡 API ENDPOINTS
# ==========================================

@app.get("/")
def home():
    return {"message": "Ayurneeds Backend Running Live (Secured)"}

# 🔐 SECURE ADMIN LOGIN
@app.post("/admin/login")
def admin_login(data: AdminLoginRequest):
    if data.password == ADMIN_PASSWORD:
        return {"status": "success", "token": "access_granted"}
    else:
        raise HTTPException(status_code=401, detail="Invalid Password")

# 1. REGISTER DOCTOR
@app.post("/register-doctor/")
def register_doctor(doctor: DoctorCreate, db: Session = Depends(get_db)):
    new_uuid = str(uuid.uuid4())
    new_doc = Doctor(
        name=doctor.name, uuid_code=new_uuid,
        phone=doctor.phone, clinic_address=doctor.clinic_address
    )
    db.add(new_doc)
    db.commit()
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
    
    filename = "manual_entry"
    ai_results = []
    
    if file:
        filename = file.filename
        try:
            contents = await file.read()
            ai_results = ai_engine.analyze_prescription(contents)
        except Exception as e:
            print(f"Upload Error: {e}")

    try: 
        manual = [{"name": m, "qty": "Standard"} for m in json.loads(manual_medicines)]
    except: 
        manual = []

    ai_formatted = [{"name": m, "qty": "Standard"} for m in ai_results] if isinstance(ai_results, list) else []
    final_list = ai_formatted + manual
    
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

    # Alerts
    med_names = ", ".join([m['name'] for m in final_list])
    msg1 = f"🤖 *Prescription Received*\n📄 ID: {new_pres.id}\n👨‍⚕️ Dr. {doctor.name}\n💊 Medicines:\n{med_names}"
    send_telegram_alert(msg1)

    stock_report = check_real_stock(final_list, db)
    confirm_link = f"{RENDER_BACKEND_URL}/admin/approve/{new_pres.id}"
    msg2 = f"🏪 *Pharmacy Stock Report*\n\n{stock_report}\n\n👇 *ACTION REQUIRED*\nClick to Confirm & Notify Patient:\n{confirm_link}"
    send_telegram_alert(msg2)
    
    return {"status": "success", "medicines": [m['name'] for m in final_list]}

# 3. ADMIN APPROVE
@app.get("/admin/approve/{pres_id}", response_class=HTMLResponse)
def approve_prescription(pres_id: int, db: Session = Depends(get_db)):
    pres = db.query(Prescription).filter(Prescription.id == pres_id).first()
    if not pres: return "<h1>Error: Prescription Not Found</h1>"
    
    pres.status = "Approved"
    db.commit()

    patient_link = f"{LIVE_WEBSITE_URL}/patient_login.html?id={pres.id}"
    phone = pres.patient_phone.replace(" ", "").replace("-", "")
    if len(phone) == 10: phone = "91" + phone 

    message = f"Hello {pres.patient_name or 'Customer'}, your prescription is ready! ✅%0a%0aClick here to confirm delivery:%0a{patient_link}"
    whatsapp_url = f"https://wa.me/{phone}?text={message}"

    return f"""
    <html>
        <head><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
        <body style="font-family:sans-serif; text-align:center; padding:20px;">
            <div style="padding:30px; border:1px solid #ddd; border-radius:10px;">
                <h1 style="color:#27ae60;">✅ Approved!</h1>
                <p>Prescription #{pres.id} is confirmed.</p>
                <a href="{whatsapp_url}" style="background:#25D366; color:white; padding:15px; text-decoration:none; display:block; border-radius:5px;">👉 Send on WhatsApp</a>
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
        return {"status": "success"}
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
        qty = 1 # Simplified qty logic for robustness
        
        best_match, score = process.extractOne(written_name, stock_names) if stock_names else (None, 0)
        
        if score > 60:
            matched_stock = stock_map[best_match]
            price = matched_stock.price
            final_name = matched_stock.medicine_name 
            match_status = "Found"
        else:
            price = 0
            final_name = written_name 
            match_status = "Not Found"

        total_cost = price * qty
        grand_total += total_cost

        final_bill.append({
            "name": final_name, "original_name": written_name,
            "qty": qty, "price": price, "total": total_cost, "status": match_status
        })

    return {
        "doctor": pres.doctor.name if pres.doctor else "Store",
        "medicines": final_bill, "grand_total": grand_total, "status": pres.status
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

    approve_link = f"{RENDER_BACKEND_URL}/admin/payment-action/{pres_id}/approve"
    decline_link = f"{RENDER_BACKEND_URL}/admin/payment-action/{pres_id}/decline"

    med_text = ", ".join([f"{m['name']} (x{m['qty']})" for m in order.final_medicines])
    msg = (
        f"💰 *PAYMENT VERIFICATION NEEDED*\n👤 {order.patient_name}\n"
        f"💵 Total: ₹{bill_total}\n🆔 Txn: {order.payment_mode}\n💊 Items: {med_text}\n"
        f"👇 *Check Bank App & Decide:*\n✅ [APPROVE]({approve_link})\n❌ [DECLINE]({decline_link})"
    )
    send_telegram_alert(msg)
    return {"status": "pending_verification"}   

# 7. DROPDOWN LIST
@app.get("/doctor/medicine-list")
def get_master_medicine_list(db: Session = Depends(get_db)):
    results = db.query(PharmacyStock.medicine_name).distinct().all()
    return [row.medicine_name for row in results]

# 8. STORE CATALOG
@app.get("/store/all-medicines")
def get_store_inventory(db: Session = Depends(get_db)):
    stocks = db.query(PharmacyStock).filter(PharmacyStock.price > 0).all()
    return [{
        "name": item.medicine_name, "price": item.price,
        "image": item.image_url, "pharmacy": item.pharmacy.name
    } for item in stocks]

# 9. CONTACT FORM
@app.post("/contact-us")
def submit_contact_form(form: ContactForm):
    msg = f"📩 *New Inquiry*\nName: {form.name}\nPhone: {form.phone}\nMsg: {form.message}"
    send_telegram_alert(msg)
    return {"status": "success"}

# 10. ADMIN PAYMENT ACTIONS
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
        message, color = "✅ Payment Approved!", "green"
    else:
        pres.status = "Payment Failed"
        message, color = "❌ Payment Declined.", "red"
    
    db.commit()
    return f"<html><body style='text-align:center; padding:50px;'><h1 style='color:{color}'>{message}</h1></body></html>"

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
        db.add(dummy_doc)
        db.commit()

    full_address = f"{order.address_line}, {order.landmark}, Pin: {order.pincode}"
    bill_total = sum(item['price'] * item['qty'] for item in order.final_medicines)

    new_order = Prescription(
        doctor_id=dummy_doc.id, patient_name=order.patient_name,
        patient_phone=order.phone, address=full_address,
        payment_mode=order.payment_mode, extracted_medicines=json.dumps(order.final_medicines),
        total_amount=bill_total, status="Verifying Payment",
        image_url="STORE_PURCHASE", created_at=datetime.datetime.utcnow()
    )
    db.add(new_order)
    db.commit()
    db.refresh(new_order)

    approve_link = f"{RENDER_BACKEND_URL}/admin/payment-action/{new_order.id}/approve"
    decline_link = f"{RENDER_BACKEND_URL}/admin/payment-action/{new_order.id}/decline"

    med_text = ", ".join([f"{m['name']} (x{m['qty']})" for m in order.final_medicines])
    msg = (
        f"🛒 *NEW STORE ORDER*\n👤 {order.patient_name}\n"
        f"💵 Total: ₹{bill_total}\n🆔 Txn: {order.payment_mode}\n"
        f"👇 *Verify & Decide:*\n✅ [APPROVE]({approve_link})\n❌ [DECLINE]({decline_link})"
    )
    send_telegram_alert(msg)
    return {"status": "pending_verification", "order_id": new_order.id}