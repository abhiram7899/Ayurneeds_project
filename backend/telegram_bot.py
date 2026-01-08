import requests

# ✅ I cleaned the formatting here.
# NOTE: This token was visible in your error. After testing, you should generate a new one for security.
BOT_TOKEN = "8593706542:AAG_EsJxPZiqLQddiMgAlhSinxtaJO-hswI"

# 🔴 PLEASE PASTE YOUR CHAT ID HERE (Keep the quotes!)
CHAT_ID = "6293824721" 

def send_message(text):
    # This URL string must be clean (no brackets, no spaces)
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    
    payload = {
        "chat_id": CHAT_ID, 
        "text": text, 
        "parse_mode": "Markdown"
    }
    
    try:
        response = requests.post(url, json=payload)
        # Check if Telegram actually accepted it
        if not response.ok:
            print(f"Telegram Error Response: {response.text}")
    except Exception as e:
        print(f"Connection Error: {e}")

def send_stock_alert(doctor_name, medicine_found, store_name, stock_count):
    msg = (
        f"✅ *Stock Match Found!*\n\n"
        f"💊 *Med:* {medicine_found}\n"
        f"🏥 *Store:* {store_name}\n"
        f"📦 *Qty:* {stock_count}\n"
    )
    send_message(msg)