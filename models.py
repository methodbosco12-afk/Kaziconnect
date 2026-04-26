from database import db
from datetime import datetime, timezone


# 🕒 UTC helper (best practice)
def utc_now():
    return datetime.now(timezone.utc)


# 👤 USERS
class User(db.Model):
    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True)

    phone = db.Column(db.String(20), unique=True, nullable=True)
    email = db.Column(db.String(120), unique=True, nullable=True)

    password = db.Column(db.String(255))
    role = db.Column(db.String(20))

    is_blocked = db.Column(db.Boolean, default=False)


# 👷 FUNDI PROFILE
class FundiProfile(db.Model):
    __tablename__ = "fundi_profile"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey('users.id'),
        nullable=False,
        unique=True
    )

    name = db.Column(db.String(100))
    ujuzi = db.Column(db.String(200))
    uzoefu = db.Column(db.String(200))
    phone = db.Column(db.String(20))
    email = db.Column(db.String(100))
    image = db.Column(db.String(200))
    location = db.Column(db.String(100))

    featured_until = db.Column(db.DateTime)
    boost_until = db.Column(db.DateTime)


# ⭐ FEATURE / BOOST REQUEST
class FeaturedRequest(db.Model):
    __tablename__ = "featured_request"

    id = db.Column(db.Integer, primary_key=True)

    fundi_id = db.Column(db.Integer, db.ForeignKey('fundi_profile.id'))

    phone = db.Column(db.String(20))
    transaction_id = db.Column(db.String(100))

    amount = db.Column(db.Integer, default=5000)
    status = db.Column(db.String(20), default="pending")
    type = db.Column(db.String(20))  # featured / boost

    created_at = db.Column(db.DateTime, default=utc_now)


# 🔐 OTP SYSTEM
class OTP(db.Model):
    __tablename__ = "otp"

    id = db.Column(db.Integer, primary_key=True)

    identifier = db.Column(db.String(120), nullable=False)
    otp = db.Column(db.String(255), nullable=False)  # hashed OTP
    expiry = db.Column(db.Float, nullable=False)
    resends = db.Column(db.Integer, default=0)


# 💰 CONTACT UNLOCK
class ContactUnlock(db.Model):
    __tablename__ = "contact_unlock"

    id = db.Column(db.Integer, primary_key=True)

    contractor_id = db.Column(db.Integer, nullable=False)
    fundi_id = db.Column(db.Integer, nullable=False)

    amount = db.Column(db.Integer, default=300)

    status = db.Column(db.String(20), default="pending")
    # pending → waiting_payment → approved → rejected → expired

    phone = db.Column(db.String(20))
    transaction_id = db.Column(db.String(100))

    is_paid = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime, default=utc_now)
    expires_at = db.Column(db.DateTime, nullable=True)


# 🧾 ADMIN LOGS
class ActivityLog(db.Model):
    __tablename__ = "activity_log"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer)
    action = db.Column(db.String(200))

    timestamp = db.Column(db.DateTime, default=utc_now)


# 🔒 IP BLOCKING (ANTI-BRUTE FORCE)
class IpBlock(db.Model):
    __tablename__ = "ip_block"

    id = db.Column(db.Integer, primary_key=True)

    ip = db.Column(db.String(50), unique=True, nullable=False)

    attempts = db.Column(db.Integer, default=0)
    last_attempt = db.Column(db.Float)
    blocked_until = db.Column(db.Float, nullable=True)

    created_at = db.Column(db.DateTime, default=utc_now)
    count = db.Column(db.Integer, default=5)


# 🧾 PROFILE UPDATE LOG
class ProfileUpdate(db.Model):
    __tablename__ = "profile_update"

    id = db.Column(db.Integer, primary_key=True)

    fundi_id = db.Column(db.Integer, db.ForeignKey('fundi_profile.id'))

    field_changed = db.Column(db.String(50))
    old_value = db.Column(db.String(255))
    new_value = db.Column(db.String(255))

    created_at = db.Column(db.DateTime, default=utc_now)