import africastalking

username = "sandbox"
api_key = "YOUR_API_KEY"

africastalking.initialize(username, api_key)
sms = africastalking.SMS  # ⚠️ lazima iwe na ()

def send_sms(phone, message):
    try:
        response = sms.send(message, [phone])
        return response
    except Exception as e:
        print("SMS error:", e)
        return None