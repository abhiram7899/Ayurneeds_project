import os
import google.generativeai as genai
import json

# 1. Get the key from Vercel's Environment Variables
API_KEY = os.getenv("GOOGLE_API_KEY")

# 2. Check if the key exists
if not API_KEY:
    print("❌ ERROR: GOOGLE_API_KEY is missing from Environment Variables!")
else:
    # 3. Configure the AI
    genai.configure(api_key=API_KEY)

def analyze_prescription(image_path):
    try:
        # Load the model
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        # Load the image
        myfile = genai.upload_file(image_path)
        
        # Ask the AI
        result = model.generate_content(
            [myfile, "\n\n", "Extract all medicine names from this prescription image. Return ONLY a JSON list of strings, like this: [\"Medicine A\", \"Medicine B\"]. Do not add any markdown formatting or extra text."]
        )
        
        # Clean the text to ensure it's valid JSON
        clean_text = result.text.strip()
        # Remove markdown code blocks if present (```json ... ```)
        if clean_text.startswith("```"):
            clean_text = clean_text.replace("```json", "").replace("```", "")
        
        return json.loads(clean_text)

    except Exception as e:
        print(f"❌ AI Error: {e}")
        return []