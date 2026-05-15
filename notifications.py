from models import User, Notification
from extensions import db
from flask_mail import Message
from extensions import mail   # ✅ SIO from app

def send_sms(phone, message):
    print("SMS sent to:", phone)

def send_email(to_email, subject, body):
    msg = Message(subject, sender="yourgmail@gmail.com", recipients=[to_email])
    msg.body = body
    mail.send(msg)

def notify_user(user_id, message, send_sms_flag=True, send_email_flag=True):

    user = User.query.get(user_id)
    if not user:
        return

    notification = Notification(
        user_id=user_id,
        message=message,
        type="system",
        is_sent=False,
        is_read=False
    )

    db.session.add(notification)

    # SMS
    if send_sms_flag and user.phone and user.sms_notifications:
        send_sms(user.phone, message)

    # EMAIL
    if send_email_flag and user.email and user.email_notifications:
        send_email(user.email, "KaziConnect Notification", message)

    db.session.commit()