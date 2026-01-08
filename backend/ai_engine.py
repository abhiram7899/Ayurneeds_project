# backend/ai_engine.py - UPDATED FOR GEMINI 2.0
import google.generativeai as genai
import json
import os
import re

# ======================================================
# 🔴 STEP 1: PASTE YOUR KEY INSIDE THE QUOTES BELOW
# ======================================================
# ✅ CORRECT: Reads from the secret vault
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

# Safety Check
if API_KEY == "PASTE_YOUR_REAL_API_KEY_HERE" or API_KEY == "":
    print("\n❌ CRITICAL ERROR: You forgot to paste your API Key in backend/ai_engine.py!")

# Configure the AI
genai.configure(api_key=API_KEY)

# The "Safety Net" alias
model = genai.GenerativeModel('gemini-flash-latest')

def analyze_prescription_image(image_path):
    print(f"🤖 AI Engine: Analyzing image at {image_path}...")
    
    try:
        # 1. Upload the file to Google
        myfile = genai.upload_file(image_path)

        # 2. The Prompt
        prompt = """
        You are an expert Pharmacist. Analyze this prescription image.
        Extract every medicine name you can read.
        
        Rules:
        1. "name": The clear name of the medicine.
        2. "qty": The dosage/quantity (e.g., "1 strip", "500mg"). If unclear, use "Standard".
        3. If the image is handwritten, try your best to read it.
        
        Return ONLY valid JSON in this exact format:
        {
            "medicines": [
                {"name": "Medicine A", "qty": "1 strip"},
                {"name": "Medicine B", "qty": "Standard"}
            ]
        }
        """

        # 3. Generate Content
        result = model.generate_content([myfile, prompt])
        
        # 4. Clean and Parse JSON
        clean_text = result.text.replace("```json", "").replace("```", "").strip()
        data = json.loads(clean_text)
        
        print(f"✅ AI Success! Found: {data}")
        return data
    except Exception as e:
     print(f"\n❌ AI CRASH ERROR: {e}")  # <--- Now it SCREAMS the error!