from werkzeug.security import generate_password_hash
from models import User
from database import db

def create_admin():
    admin = User.query.filter_by(role='admin').first()

    if not admin:
        admin = User(
            email="methodbosco12@gmail.com",
            phone="0799978711",
            password=generate_password_hash("Method@123"),
            role="admin"
        )
        db.session.add(admin)
        db.session.commit()
        print("✅ Admin created")
    else:
        print("ℹ️ Admin already exists")