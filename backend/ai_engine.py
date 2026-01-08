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
        
        # 2. Try models in order: Flash -> Pro (Backup)
        # 'gemini-pro' is the stable model that works on older libraries
        models_to_try = ['gemini-1.5-flash', 'gemini-pro']
        
        response = None
        used_model = ""

        for model_name in models_to_try:
            try:
                print(f"👉 Attempting with model: {model_name}...")
                model = genai.GenerativeModel(model_name)
                response = generate_response(model, img)
                used_model = model_name
                print(f"✅ Success with {model_name}!")
                break # Stop loop if it works
            except Exception as e:
                print(f"⚠️ {model_name} failed. Error: {e}")
                continue # Try next model

        if not response:
            print("❌ All AI models failed.")
            return []

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