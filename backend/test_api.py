import google.generativeai as genai
import os

# 🔴 PASTE YOUR REAL KEY HERE 🔴
MY_KEY = "AIzaSyDCMqS_WJC2Dk1E9_KnW_h3DORdc1taol4"

print("------------------------------------------------")
print("🔍 CHECKING AVAILABLE MODELS...")

try:
    genai.configure(api_key=MY_KEY)
    
    print("📡 Connecting to Google...")
    
    # Ask Google what models are available
    available_models = []
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            available_models.append(m.name)
            print(f"   ✅ Found: {m.name}")

    print("\n------------------------------------------------")
    print(f"📊 Total Models Found: {len(available_models)}")
    print("------------------------------------------------")

except Exception as e:
    print("\n❌ API KEY FAILED!")
    print(f"Error Message: {e}")