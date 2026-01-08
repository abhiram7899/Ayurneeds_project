import os
import google.generativeai as genai
import json
import PIL.Image
import io
import re

# 1. Configure API Key
API_KEY = os.getenv("GOOGLE_API_KEY")

if not API_KEY:
    print("❌ ERROR: GOOGLE_API_KEY is missing!")
else:
    genai.configure(api_key=API_KEY)

def analyze_prescription(image_bytes):
    try:
        print("🔍 AI Engine: Starting analysis...")
        image_stream = io.BytesIO(image_bytes)
        img = PIL.Image.open(image_stream)
        
        # 2. Try 'gemini-1.5-flash' first (Fastest/Newest)
        model_name = 'gemini-1.5-flash'
        
        try:
            model = genai.GenerativeModel(model_name)
            response = generate_response(model, img)
        except Exception as e:
            print(f"⚠️ {model_name} failed ({e}). Switching to 'gemini-1.5-flash-latest'...")
            # Fallback 1
            model = genai.GenerativeModel('gemini-1.5-flash-latest')
            response = generate_response(model, img)

        raw_text = response.text.strip()
        print(f"✅ AI Raw Response: {raw_text}") 

        # 3. Clean and Extract JSON
        match = re.search(r'\[.*\]', raw_text, re.DOTALL)
        if match:
            return json.loads(match.group())
        else:
            return []

    except Exception as e:
        print(f"❌ AI CRASH: {e}")
        return []

def generate_response(model, img):
    prompt = (
        "You are a pharmacist. Extract all medicine names from this image. "
        "Return ONLY a JSON list of strings. Example: [\"Dolo 650\", \"Pan 40\"]. "
        "Do not use markdown."
    )
    return model.generate_content([prompt, img])