import os
import json
import requests
import base64
import re
import time

API_KEY = os.getenv("GOOGLE_API_KEY")

def analyze_prescription(image_bytes):
    if not API_KEY:
        print("❌ CRITICAL: No API Key found.")
        return []

    # ✅ PRIORITY LIST: If #1 is busy, we use #2, etc.
    # We derived this list from your successful logs!
    models_to_try = [
        "gemini-2.5-flash",       # First choice (Fastest)
        "gemini-2.0-flash",       # Backup 1
        "gemini-2.0-flash-lite",  # Backup 2 (Super light)
        "gemini-2.5-pro",         # Backup 3 (Slower but powerful)
        "gemini-1.5-flash"        # Old reliable (just in case)
    ]

    image_b64 = base64.b64encode(image_bytes).decode('utf-8')
    headers = {'Content-Type': 'application/json'}
    
    payload = {
        "contents": [{
            "parts": [
                {"text": "You are a pharmacist. Extract all medicine names from this image. Return ONLY a JSON list of strings. Example: [\"Dolo 650\", \"Pan 40\"]. Do not use markdown."},
                {
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": image_b64
                    }
                }
            ]
        }]
    }

    print(f"🔍 AI Engine: Starting robust analysis...")

    # 🔄 THE LOOP: Try models one by one
    for model_name in models_to_try:
        try:
            print(f"👉 Attempting with: {model_name}...")
            
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={API_KEY}"
            
            response = requests.post(url, headers=headers, json=payload)
            
            # 🛑 If Busy (503) or Rate Limited (429), CONTINUE to next model
            if response.status_code in [503, 429]:
                print(f"⚠️ {model_name} is overloaded/busy. Switching to next model...")
                continue 
            
            # 🛑 If other error (404, 400), print and try next just in case
            if response.status_code != 200:
                print(f"⚠️ {model_name} returned Error {response.status_code}: {response.text}")
                continue

            # ✅ SUCCESS! We got a 200 OK response
            result = response.json()
            if 'candidates' in result:
                raw_text = result['candidates'][0]['content']['parts'][0]['text']
                print(f"✅ Success with {model_name}! Response: {raw_text}")
                
                # Extract JSON
                match = re.search(r'\[.*\]', raw_text, re.DOTALL)
                if match:
                    return json.loads(match.group())
                else:
                    return [] # AI replied but no JSON found
            
        except Exception as e:
            print(f"⚠️ Crash with {model_name}: {e}")
            continue # Try next model

    print("❌ All AI models failed or were busy.")
    return []