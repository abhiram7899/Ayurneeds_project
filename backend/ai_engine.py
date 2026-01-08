import os
import json
import requests
import base64
import re

API_KEY = os.getenv("GOOGLE_API_KEY")

def get_available_model():
    """Asks Google which models are enabled for this API Key"""
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={API_KEY}"
        response = requests.get(url)
        data = response.json()
        
        # 1. Debug: Print ALL available models to the Vercel Logs
        print(f"📋 AVAILABLE MODELS FOR THIS KEY: {json.dumps(data)}")
        
        if "models" not in data:
            return None

        # 2. Priority List (Try to find the best one that exists)
        # We prefer Flash (fast), then Pro (smart), then Vision (old reliable)
        priority_order = [
            "gemini-1.5-flash",
            "gemini-1.5-pro",
            "gemini-1.5-flash-latest",
            "gemini-1.0-pro-vision",
            "gemini-pro-vision"
        ]
        
        available_names = [m['name'].replace("models/", "") for m in data['models']]
        
        for p in priority_order:
            if p in available_names:
                print(f"✅ Auto-Selected Model: {p}")
                return p
                
        # 3. Fallback: Just pick the first one that supports generation
        if available_names:
            print(f"⚠️ specific match failed. Using fallback: {available_names[0]}")
            return available_names[0]
            
        return None
    except Exception as e:
        print(f"⚠️ Model Discovery Failed: {e}")
        return "gemini-1.5-flash" # Blind guess if discovery fails

def analyze_prescription(image_bytes):
    if not API_KEY:
        print("❌ CRITICAL: No API Key found.")
        return []

    try:
        # 1. Auto-Detect the correct model
        model_name = get_available_model()
        if not model_name:
            print("❌ Error: No AI models found for this API Key.")
            return []

        print(f"🔍 AI Engine: Sending Request to {model_name}...")

        image_b64 = base64.b64encode(image_bytes).decode('utf-8')

        # 2. Use the discovered model in the URL
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
            raw_text = result['candidates'][0]['content']['parts'][0]['text']
            print(f"✅ AI Raw Response: {raw_text}")
            
            match = re.search(r'\[.*\]', raw_text, re.DOTALL)
            if match:
                return json.loads(match.group())
            else:
                return []
        except Exception as e:
            print(f"⚠️ Parsing Error: {e}")
            return []

    except Exception as e:
        print(f"❌ Server Crash: {e}")
        return []