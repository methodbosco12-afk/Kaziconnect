# services/email_service.py
from flask_mail import Message

mail = None  # placeholder

def init_mail(app_mail):
    global mail
    mail = app_mail

def send_email(to, subject, body, app):
    msg = Message(
        subject=subject,
        recipients=[to],
        sender=app.config["MAIL_USERNAME"]
    )
    msg.body = body
    mail.send(msg)