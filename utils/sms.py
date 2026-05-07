import os
import africastalking
from dotenv import load_dotenv

load_dotenv()

username = os.getenv("AFRICASTALKING_USERNAME", "sandbox")
api_key = os.getenv("AFRICASTALKING_API_KEY")

if not api_key:
    raise Exception("Missing AFRICASTALKING_API_KEY")

africastalking.initialize(username, api_key)
sms = africastalking.SMS


def send_sms(phone, message):
    try:
        response = sms.send(message, [phone], "KaziConnect")
        print("📩 SMS sent successfully:", response)
        return response
    except Exception as e:
        print("❌ SMS error:", e)
        return None