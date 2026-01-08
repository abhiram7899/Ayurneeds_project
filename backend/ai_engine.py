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
        print("🔍 AI Engine: Received image data in memory")
        
        # 2. Open image directly from memory (No file path needed)
        image_stream = io.BytesIO(image_bytes)
        img = PIL.Image.open(image_stream)
        
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        # 3. Strong Prompt
        prompt = (
            "You are a pharmacist. Extract all medicine names from this image. "
            "Return ONLY a JSON list of strings. Example: [\"Dolo 650\", \"Pan 40\"]. "
            "If no medicines are visible, return []. "
            "Do not use markdown."
        )
        
        response = model.generate_content([prompt, img])
        raw_text = response.text.strip()
        print(f"✅ AI Raw Response: {raw_text}") 

        # 4. Extract List using Regex
        match = re.search(r'\[.*\]', raw_text, re.DOTALL)
        if match:
            return json.loads(match.group())
        else:
            return []

    except Exception as e:
        print(f"❌ AI CRASH: {e}")
        return []