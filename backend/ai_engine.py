import os
import json
import requests
import base64

# 1. Get API Key
API_KEY = os.getenv("GOOGLE_API_KEY")

def analyze_prescription(image_bytes):
    if not API_KEY:
        print("❌ CRITICAL: No API Key found.")
        return []

    try:
        print("🔍 AI Engine: Sending Direct HTTP Request to Google...")

        # 2. Convert image bytes to Base64 (Required for HTTP)
        # This turns the image into a text string the internet can handle
        image_b64 = base64.b64encode(image_bytes).decode('utf-8')

        # 3. Direct URL to Google (Bypassing the Python Library)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={API_KEY}"
        
        headers = {'Content-Type': 'application/json'}
        
        # 4. Construct the Payload
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

        # 5. Send the Request
        response = requests.post(url, headers=headers, json=payload)
        
        # 6. Check for Errors
        if response.status_code != 200:
            print(f"❌ Google API Error: {response.text}")
            return []

        # 7. Parse Response
        result = response.json()
        try:
            raw_text = result['candidates'][0]['content']['parts'][0]['text']
            print(f"✅ AI Raw Response: {raw_text}")
            
            # Extract JSON list
            import re
            match = re.search(r'\[.*\]', raw_text, re.DOTALL)
            if match:
                return json.loads(match.group())
            else:
                return []
        except KeyError:
            print("⚠️ AI Response format was unexpected.")
            return []

    except Exception as e:
        print(f"❌ Server Crash: {e}")
        return []