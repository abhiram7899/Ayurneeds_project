import os
import json
import requests
import base64
import re

API_KEY = os.getenv("GOOGLE_API_KEY")

def get_available_model():
    """Asks Google which models are enabled for this API Key"""
    try:
        # 1. Ask Google for the list
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={API_KEY}"
        response = requests.get(url)
        data = response.json()
        
        if "models" not in data:
            return "gemini-2.5-flash" # Default fallback

        # 2. Priority List (Updated for YOUR specific account)
        # We now prioritize the 2.5 and 2.0 models you actually have access to.
        priority_order = [
            "gemini-2.5-flash",       # ✅ Your best model
            "gemini-2.0-flash",       # ✅ Backup
            "gemini-2.5-pro",         # ✅ Slow but smart
            "gemini-2.0-flash-lite",  # ✅ Super fast
            "gemini-1.5-flash"        # ❌ (Old, likely missing)
        ]
        
        # Clean up the names (remove "models/" prefix)
        available_names = [m['name'].replace("models/", "") for m in data['models']]
        
        # 3. Find the best match
        for p in priority_order:
            if p in available_names:
                print(f"✅ Auto-Selected Model: {p}")
                return p
                
        # 4. Fallback: Pick the first model that is NOT an 'embedding' or 'aqa' model
        for name in available_names:
            if "embedding" not in name and "aqa" not in name:
                print(f"⚠️ Specific match failed. Using generic fallback: {name}")
                return name
            
        return "gemini-2.5-flash"

    except Exception as e:
        print(f"⚠️ Model Discovery Failed: {e}")
        return "gemini-2.5-flash" 

def analyze_prescription(image_bytes):
    if not API_KEY:
        print("❌ CRITICAL: No API Key found.")
        return []

    try:
        model_name = get_available_model()
        print(f"🔍 AI Engine: Sending Request to {model_name}...")

        image_b64 = base64.b64encode(image_bytes).decode('utf-8')

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={API_KEY}"
        
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

        response = requests.post(url, headers=headers, json=payload)
        
        if response.status_code != 200:
            print(f"❌ Google API Error: {response.text}")
            return []

        result = response.json()
        try:
            # Handle different response structures if 2.5 behaves differently
            if 'candidates' in result:
                raw_text = result['candidates'][0]['content']['parts'][0]['text']
                print(f"✅ AI Raw Response: {raw_text}")
                
                match = re.search(r'\[.*\]', raw_text, re.DOTALL)
                if match:
                    return json.loads(match.group())
            return []
        except Exception as e:
            print(f"⚠️ Parsing Error: {e}")
            return []

    except Exception as e:
        print(f"❌ Server Crash: {e}")
        return []