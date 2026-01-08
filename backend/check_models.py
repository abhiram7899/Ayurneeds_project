import google.generativeai as genai

# PASTE YOUR API KEY HERE
API_KEY = "AIzaSyA7lBFiWsDnB5fdWHVgfho-gMpPg36XQGE"
genai.configure(api_key=API_KEY)

print("Checking available models...")
try:
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            print(f"- {m.name}")
except Exception as e:
    print(f"Error: {e}")