import os
import google.generativeai as genai
import json
import PIL.Image
import re

# 1. Configure API Key
API_KEY = os.getenv("GOOGLE_API_KEY")

if not API_KEY:
    print("❌ ERROR: GOOGLE_API_KEY is missing!")
else:
    genai.configure(api_key=API_KEY)

def analyze_prescription(image_path):
    try:
        print(f"🔍 AI Engine: Processing file at {image_path}")
        img = PIL.Image.open(image_path)
        
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        # 2. Stronger Prompt
        prompt = (
            "You are a pharmacist assistant. "
            "Extract all medicine names from this image. "
            "Return ONLY a raw JSON list of strings. "
            "Example output: [\"Dolo 650\", \"Pan 40\"]. "
            "Do not write any other words, context, or markdown."
        )
        
        response = model.generate_content([prompt, img])
        raw_text = response.text
        print(f"✅ AI Raw Response: {raw_text}") # Check this in Vercel logs if it fails!

        # 3. Smart Extraction (Regex) - Finds the list even if AI chats
        # Looks for anything between [ and ]
        match = re.search(r'\[.*\]', raw_text, re.DOTALL)
        
        if match:
            json_str = match.group()
            return json.loads(json_str)
        else:
            print("⚠️ Could not find JSON list in AI response.")
            return []

    except Exception as e:
        print(f"❌ AI CRASH: {e}")
        return []