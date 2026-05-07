from models import User, Notification
from database import db

from services.sms_service import send_sms
from services.email_service import send_email


def notify_user(user_id, message, send_sms_flag=True, send_email_flag=True):
    """
    Send in-app notification + optional SMS + Email
    """

    # 👤 get user
    user = User.query.get(user_id)
    if not user:
        return

    # 🔔 save in-app notification
    notification = Notification(
        user_id=user_id,
        message=message,
        type="system"
    )

    db.session.add(notification)

    # 📲 SMS notification
    if send_sms_flag and user.phone and getattr(user, "sms_notifications", False):
        try:
            send_sms(user.phone, message)
        except Exception as e:
            print("SMS error:", e)

    # 📧 EMAIL notification
    if send_email_flag and user.email and getattr(user, "email_notifications", False):
        try:
            send_email(user.email, "KaziConnect Notification", message)
        except Exception as e:
            print("Email error:", e)

    db.session.commit()