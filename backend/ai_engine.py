import os
import google.generativeai as genai
import json
import mimetypes
import PIL.Image

# 1. Configure API Key
API_KEY = os.getenv("GOOGLE_API_KEY")

if not API_KEY:
    print("❌ ERROR: GOOGLE_API_KEY is missing!")
else:
    genai.configure(api_key=API_KEY)

def analyze_prescription(image_path):
    try:
        # 2. Determine Mime Type (jpg, png, etc.)
        mime_type, _ = mimetypes.guess_type(image_path)
        if not mime_type:
            mime_type = "image/jpeg" # Default fallback

        # 3. Read the file as raw bytes (No upload step needed)
        with open(image_path, "rb") as f:
            image_data = f.read()

        # 4. Prepare the Data Payload
        image_part = {
            "mime_type": mime_type,
            "data": image_data
        }

        # 5. Initialize Model
        model = genai.GenerativeModel('gemini-1.5-flash')

        # 6. Send Request
        prompt = "Extract all medicine names from this prescription image. Return ONLY a JSON list of strings, like this: [\"Medicine A\", \"Medicine B\"]. Do not add any markdown formatting."
        
        response = model.generate_content([prompt, image_part])
        
        # 7. Clean and Parse Response
        clean_text = response.text.strip()
        
        # Remove markdown code blocks if present
        if clean_text.startswith("```"):
            clean_text = clean_text.replace("```json", "").replace("```", "")
            
        return json.loads(clean_text)

    except Exception as e:
        print(f"❌ AI Error: {e}")
        return []