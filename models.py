
from database import db
from datetime import datetime


# 👤 USERS
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    phone = db.Column(db.String(20), unique=True, nullable=True)
    email = db.Column(db.String(120), unique=True, nullable=True)

    password = db.Column(db.String(255))
    role = db.Column(db.String(20))

    is_blocked = db.Column(db.Boolean, default=False)

# 👷 FUNDI PROFILE
class FundiProfile(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True)

    name = db.Column(db.String(100))
    skills = db.Column(db.String(200))
    experience = db.Column(db.String(200))
    phone = db.Column(db.String(20))
    email = db.Column(db.String(100))
    image = db.Column(db.String(200))
    location = db.Column(db.String(100))

    featured_until = db.Column(db.DateTime)
    boost_until = db.Column(db.DateTime)


# ⭐ FEATURE / BOOST REQUEST
class FeaturedRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    fundi_id = db.Column(db.Integer, db.ForeignKey('fundi_profile.id'))

    phone = db.Column(db.String(20))
    transaction_id = db.Column(db.String(100))

    amount = db.Column(db.Integer, default=5000)
    status = db.Column(db.String(20), default="pending")
    type = db.Column(db.String(20))  # featured / boost

    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# 🔐 OTP SYSTEM
class OTP(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    identifier = db.Column(db.String(120), nullable=False)
    otp = db.Column(db.String(255), nullable=False)  # hashed OTP
    expiry = db.Column(db.Float, nullable=False)
    resends = db.Column(db.Integer, default=0)


# 💰 CONTACT UNLOCK (500 TZS)
class ContactUnlock(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    contractor_id = db.Column(db.Integer, nullable=False)
    fundi_id = db.Column(db.Integer, nullable=False)

    amount = db.Column(db.Integer, default=300)

    status = db.Column(db.String(20), default="pending")
    # pending → waiting_payment → approved → rejected → expired

    phone = db.Column(db.String(20))
    transaction_id = db.Column(db.String(100))

    is_paid = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=True)


# 🧾 ADMIN LOGS
class ActivityLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer)
    action = db.Column(db.String(200))

    timestamp = db.Column(db.DateTime, default=datetime.utcnow)


# 🔒 IP BLOCKING (ANTI-BRUTE FORCE)
class IpBlock(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    ip = db.Column(db.String(50), unique=True, nullable=False)

    attempts = db.Column(db.Integer, default=0)
    last_attempt = db.Column(db.Float)
    blocked_until = db.Column(db.Float, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    count = db.Column(db.Integer, default=5)

from datetime import datetime
from database import db

class ProfileUpdate(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    fundi_id = db.Column(db.Integer, db.ForeignKey('fundi_profile.id'))
    
    field_changed = db.Column(db.String(50))
    old_value = db.Column(db.String(255))
    new_value = db.Column(db.String(255))

    created_at = db.Column(db.DateTime, default=datetime.utcnow)