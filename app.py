
from flask import Flask, render_template, request, redirect, url_for, session
from datetime import datetime, timedelta, timezone
from database import db
from models import User, FundiProfile, FeaturedRequest, OTP, ContactUnlock,IpBlock,ActivityLog,ProfileUpdate
import os
import time
from dotenv import load_dotenv
load_dotenv()
import random

import africastalking
from functools import wraps
from auth.admin_seed import create_admin


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):

        user_id = session.get('user_id')
        role = session.get('role')

        # 🔒 no session at all
        if not user_id or not role:
            return redirect(url_for('admin_login'))

        # 🔒 wrong role
        if role != 'admin':
            return redirect(url_for('admin_login'))

        # 🔒 optional extra safety (DB check)
        user = User.query.get(user_id)
        if not user or user.role != 'admin':
            session.clear()
            return redirect(url_for('admin_login'))

        return f(*args, **kwargs)

    return wrapper

def fundi_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if session.get('role') != 'fundi':
            return redirect(url_for('fundi_login'))
        return f(*args, **kwargs)
    return wrapper

def contractor_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if session.get('role') != 'contractor':
            return redirect(url_for('contractor_login'))
        return f(*args, **kwargs)
    return wrapper

username = os.getenv("AFRICASTALKING_USERNAME", "sandbox")
api_key = os.getenv("AFRICASTALKING_API_KEY")

if not api_key:
    raise Exception("AFRICASTALKING_API_KEY missing in environment variables")

africastalking.initialize(username, api_key)
sms = africastalking.SMS

from werkzeug.utils import secure_filename
from apscheduler.schedulers.background import BackgroundScheduler
from werkzeug.security import generate_password_hash, check_password_hash
def is_featured_active(fundi):
    return fundi.featured_until and fundi.featured_until > datetime.now(timezone.utc)

def is_boost_active(fundi):
    return fundi.boost_until and fundi.boost_until > datetime.now(timezone.utc) and is_featured_active(fundi)

def format_phone(phone):
    phone = phone.strip().replace(" ", "")

    if phone.startswith("0"):
        phone = "+255" + phone[1:]
    elif phone.startswith("255"):
        phone = "+" + phone
    elif not phone.startswith("+"):
        phone = "+" + phone

    return phone

def send_otp_sms(phone, otp):

    phone = format_phone(phone)

    if "@" in phone:
        print("Not a phone number")
        return

    message = f"Your OTP code is {otp}. It expires in 2 minutes."

    try:
        response = sms.send(message, [phone], "Kaziconnect")
        print("OTP sent successfully:", response)
    except Exception as e:
        print("SMS failed:", e)

app = Flask(__name__, instance_relative_config=True)
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SECRET_KEY'] = os.getenv("SECRET_KEY", "dev-secret-key")
uri = os.environ.get("DATABASE_URL")

if not uri:
    uri = "sqlite:///app.db"

if uri.startswith("postgres://"):
    uri = uri.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = uri

app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)

UPLOAD_FOLDER = 'static/images'
app.config[ 'UPLOAD_FOLDER'] = UPLOAD_FOLDER

db.init_app(app)

with app.app_context():
    db.create_all()

@app.context_processor
def inject_now():
    return {'now': datetime.now(timezone.utc)}

@app.route('/check_admin')
def check_admin():
    admin = User.query.filter_by(role='admin').first()

    if not admin:
        return "No admin found"

    return f"Admin exists: {admin.email}"

def expire_jobs():
    with app.app_context():

        now = datetime.now(timezone.utc)

        # 🔥 EXPIRE FEATURED
        FundiProfile.query.filter(
            FundiProfile.featured_until != None,
            FundiProfile.featured_until < now
        ).update({FundiProfile.featured_until: None})

        # 🚀 EXPIRE BOOST
        FundiProfile.query.filter(
            FundiProfile.boost_until != None,
            FundiProfile.boost_until < now
        ).update({FundiProfile.boost_until: None})

        # 🔐 EXPIRE CONTACT UNLOCKS (7 days)
        expired = ContactUnlock.query.filter(
            ContactUnlock.expires_at < now,
            ContactUnlock.status == "approved"
        ).all()

        for e in expired:
            e.status = "expired"
            e.is_paid = False

        db.session.commit()

        print("✅ All expiry jobs ran:", now)

@app.route('/fix_db')
def fix_db():

    # skills
         FundiProfile.query.filter(
        (FundiProfile.skills == None) |
        (FundiProfile.skills == "") |
        (FundiProfile.skills == "Ujuzi") |
        (FundiProfile.skills == "ujuzi") |
        (FundiProfile.skills == "Haijatajwa")
    ).update(
        {FundiProfile.skills: "Not specified"},
        synchronize_session=False
    )

    # experience
         FundiProfile.query.filter(
        (FundiProfile.experience == None) |
        (FundiProfile.experience == "") |
        (FundiProfile.experience == "Uzoefu") |
        (FundiProfile.experience == "uzoefu") |
        (FundiProfile.experience == "Haijatajwa")
    ).update(
        {FundiProfile.experience: "Not specified"},
        synchronize_session=False
    )

         db.session.commit()

         return "✅ Database updated successfully"


# 🔥 HOME
@app.route('/')
def home():
    return redirect(url_for('dashboard'))

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():

    if request.method == 'POST':

        email = request.form.get('email')
        password = request.form.get('password')

        if not email or not password:
            return render_template("admin_login.html", error="All fields required")

        admin = User.query.filter_by(email=email, role='admin').first()

        if not admin or not admin.password:
            return render_template("admin_login.html", error="Invalid credentials")

        if not check_password_hash(admin.password, password):
            return render_template("admin_login.html", error="Invalid credentials")

        session.clear()
        session['user_id'] = admin.id
        session['role'] = 'admin'
        session.permanent = True

        return redirect(url_for('admin_dashboard'))

    return render_template("admin_login.html")


@app.route('/search', methods=['GET'])
def search():

    skills = (request.args.get('skills') or '').strip()
    experience = (request.args.get('experience') or '').strip()
    location = (request.args.get('location') or '').strip()

    # 🔁 clean redirect (important fix)
    if request.args and not request.args.get('submitted'):
        return redirect(url_for(
            'search',
            skills=skills,
            experience=experience,
            location=location,
            submitted=1
        ))

    query = FundiProfile.query
    if skills and skills.strip():
       query = query.filter(FundiProfile.skills.ilike(f"%{skills.strip()}%"))

    if experience and experience.strip():
       query = query.filter(FundiProfile.experience.ilike(f"%{experience.strip()}%"))
    
    if location and location.strip():
        query = query.filter(FundiProfile.location.ilike(f"%{location.strip()}%"))

    results = query.all()

    results = sorted(
        results,
        key=lambda f: f.featured_until is not None and f.featured_until > datetime.now(timezone.utc),
        reverse=True
    )

    return render_template("search.html", results=results)


@app.route('/results', methods=['GET'])
def results():

    skills = request.args.get('skills')
    experience = request.args.get('experience')
    location = request.args.get('location')

    query = FundiProfile.query

    # 🔥 filters
    if skills:
        query = query.filter(FundiProfile.skills.contains(skills))

    if experience:
        query = query.filter(FundiProfile.experience.contains(experience))

    if location:
        query = query.filter(FundiProfile.location.contains(location))

    fundis = query.all()

    # 🚀 SORTING LOGIC
    def sort_key(f):
        if f.boost_until and f.boost_until > datetime.now(timezone.utc):
            return 3   # 🚀 boost (juu kabisa)
        elif f.featured_until and f.featured_until > datetime.now(timezone.utc):
            return 2   # ⭐ featured
        else:
            return 1   # normal

    fundis = sorted(fundis, key=sort_key, reverse=True)

    return render_template(
        "results.html",
        results=fundis,
        now=datetime.now(timezone.utc)
    )

    # =========================
# CONTACT UNLOCK ROUTES 💰
# =========================

@app.route('/request_contact/<int:fundi_id>', methods=['POST'])
@contractor_required
def request_contact(fundi_id):

    contractor_id = session['user_id']

    existing = ContactUnlock.query.filter_by(
        contractor_id=contractor_id,
        fundi_id=fundi_id
    ).first()

    if existing:
        return redirect(url_for('pay_contact', fundi_id=fundi_id))

    unlock = ContactUnlock(
        contractor_id=contractor_id,
        fundi_id=fundi_id,
        status="pending"
    )

    db.session.add(unlock)
    db.session.commit()

    return redirect(url_for('pay_contact', fundi_id=fundi_id))


@app.route('/pay_contact/<int:fundi_id>', methods=['GET'])
@contractor_required
def pay_contact(fundi_id):

    return render_template(
        "pay_contact.html",
        fundi_id=fundi_id,
        amount=500
    )

@app.route('/confirm_payment/<int:fundi_id>', methods=['POST'])
@contractor_required
def confirm_payment(fundi_id):

    contractor_id = session['user_id']

    unlock = ContactUnlock.query.filter_by(
        contractor_id=contractor_id,
        fundi_id=fundi_id,
        status="pending"
    ).first()

    if not unlock:
        return "Request not found"

    unlock.phone = request.form.get('phone')
    unlock.transaction_id = request.form.get('transaction_id')

    unlock.status = "pending"

    db.session.commit()

    return render_template("success_payment.html")


@app.route('/view_contact/<int:fundi_id>')
@contractor_required
def view_contact(fundi_id):

    fundi = FundiProfile.query.get_or_404(fundi_id)

    # 🚀 FORCE OPEN CONTACT (TEMP FIX)
    is_unlocked = True

    return render_template(
        "contact.html",
        fundi=fundi,
        is_unlocked=is_unlocked
    )

# 🔥 LOGIN (HII NDIO UNAWEKA HAPA)
@app.route('/login/contractor')
def contractor_login():

    if session.get('role') == 'contractor':
        return redirect(url_for('search'))

    guest_user = User(
        phone="guest_" + str(random.randint(10000, 99999)),
        role='contractor'
    )

    db.session.add(guest_user)
    db.session.commit()

    session.clear()
    session['user_id'] = guest_user.id
    session['role'] = 'contractor'
    session.permanent = True
    

    return redirect(url_for('search'))


@app.route('/login/fundi', methods=['GET', 'POST'])
def fundi_login():
    if request.method == 'POST':
        identifier = request.form['identifier']
        password = request.form['password']
        remember = request.form.get('remember')  # 🔥 muhimu

        # 🔍 detect email au phone
        if "@" in identifier:
            user = User.query.filter_by(email=identifier.lower().strip(), role='fundi').first()
        else:
            user = User.query.filter_by(phone=identifier.strip(), role='fundi').first()

        if user and check_password_hash(user.password, password):

            session.clear()
            session['user_id'] = user.id
            session['role'] = 'fundi'
            session.permanent = True
            

            # 🔥 REMEMBER ME LOGIC
            if remember:
                session.permanent = True   # itaishi siku 7 (uliyoset)
            else:
                session.permanent = False  # session inaisha browser ikifungwa

            return redirect(url_for('my_profile'))

        return render_template("fundi_login.html", error="Wrong credentials")

    return render_template("fundi_login.html")


@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():

    ip = request.remote_addr

    # 🔥 CHECK IP BLOCK
    block = IpBlock.query.filter_by(ip=ip).first()

    if not block:
        block = IpBlock(ip=ip, blocked_until=None, count=1)
        db.session.add(block)
    else:
        block.count = (block.count or 0) + 1

    # 🚫 BLOCK AFTER 5 REQUESTS
    if block.count > 5:
        block.blocked_until = time.time() + 300  # 5 minutes block

    db.session.commit()

    # ⛔ STOP IF STILL BLOCKED
    if block.blocked_until and block.blocked_until > time.time():
        return "🚫 Too many requests. Try again later."

    if request.method == 'POST':

        identifier = request.form.get('identifier')

        # 👤 FIND USER
        if "@" in identifier:
            user = User.query.filter_by(email=identifier.lower().strip(), role='fundi').first()
        else:
            user = User.query.filter_by(phone=identifier.strip(), role='fundi').first()

        if not user:
            return render_template("forgot_password.html", error="Account not found")

        # 🔥 GENERATE OTP
        otp = str(random.randint(100000, 999999))
        hashed_otp = generate_password_hash(otp)

        # 🧹 DELETE OLD OTP
        OTP.query.filter_by(identifier=identifier).delete()

        new_otp = OTP(
            identifier=identifier,
            otp=hashed_otp,
            expiry=datetime.now(timezone.utc) + timedelta(seconds=120),
            resends=0
        )

        db.session.add(new_otp)
        db.session.commit()

        # 📩 SEND OTP
        clean_phone = format_phone(user.phone)
        send_otp_sms(clean_phone, otp)

        return redirect(url_for('verify_otp', identifier=identifier))

    return render_template("forgot_password.html")

@app.route('/verify_otp/<identifier>', methods=['GET', 'POST'])
def verify_otp(identifier):

    key = f"otp_attempts_{identifier}"
    last_key = f"otp_last_attempt_{identifier}"

    if request.method == 'POST':

        user_otp = request.form.get('otp')
        new_password = request.form.get('password')

        attempts = session.get(key, 0)
        last_attempt = session.get(last_key, 0)

        # 🔒 block after 5 attempts
        if attempts >= 5:
            if time.time() - last_attempt < 300:
                return "Too many attempts. Try again after 5 minutes"
            else:
                session[key] = 0  # reset

        data = OTP.query.filter_by(identifier=identifier).first()

        if not data:
            return render_template("verify_otp.html", error="OTP expired", identifier=identifier)

        if time.time() > data.expiry:
            db.session.delete(data)
            db.session.commit()
            return render_template("verify_otp.html", error="OTP expired", identifier=identifier)

        # ❌ wrong OTP
        if not check_password_hash(data.otp, user_otp):
            session[key] = attempts + 1
            session[last_key] = time.time()

            return render_template("verify_otp.html", error="Invalid OTP", identifier=identifier)

        # 🔒 password validation
        if len(new_password) < 6:
            return render_template("verify_otp.html", error="Password too short", identifier=identifier)

        # 👤 find user
        if "@" in identifier:
            user = User.query.filter_by(email=identifier.lower(), role='fundi').first()
        else:
            user = User.query.filter_by(phone=identifier, role='fundi').first()

        if not user:
            return render_template("verify_otp.html", error="User not found", identifier=identifier)

        # 🔐 save password
        user.password = generate_password_hash(new_password)
        db.session.commit()

        # 🧹 delete OTP
        db.session.delete(data)
        db.session.commit()

        # 🧹 reset attempts
        session.pop(key, None)
        session.pop(last_key, None)

        session['user_id'] = user.id

        return redirect(url_for('my_profile'))

    return render_template("verify_otp.html", identifier=identifier)

@app.route('/resend_otp/<identifier>')
def resend_otp(identifier):

    data = OTP.query.filter_by(identifier=identifier).first()

    if not data:
        return "OTP expired, restart process"

    if data.resends >= 3:
        return render_template(
            "verify_otp.html",
            error="Resend limit reached",
            identifier=identifier
        )

    raw_otp = str(random.randint(100000, 999999))
    hashed_otp = generate_password_hash(raw_otp)

    data.otp = hashed_otp
    data.expiry = time.time() + 120
    data.resends += 1

    db.session.commit()

    # 👤 pata user
    if "@" in identifier:
        user = User.query.filter_by(email=identifier.lower(), role='fundi').first()
    else:
        user = User.query.filter_by(phone=identifier, role='fundi').first()

    if not user:
        return "User not found"

    send_otp_sms(user.phone, raw_otp)

    return redirect(url_for('verify_otp', identifier=identifier))

@app.route('/register/fundi', methods=['GET', 'POST'])
def register_fundi():

    if request.method == 'POST':

        # 🔹 GET FORM DATA
        name = request.form.get('name')
        skills = request.form.get('skills')
        experience = request.form.get('experience')
        phone = request.form.get('phone').strip().replace(" ", "")
        email = request.form.get('email').lower().strip()
        location = request.form.get('location')

        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        if not skills:
          skills = "Not specified"

        if not experience:
           experience = "Not specified"

        # 🔒 PASSWORD MATCH
        if password != confirm_password:
            return render_template("register_fundi.html", error="Passwords do not match")

        # 🔒 PASSWORD LENGTH
        if len(password) < 6:
            return render_template("register_fundi.html", error="Password must be at least 6 characters")

        # 🔒 CHECK EXISTING USER
        existing_user = User.query.filter(
            (User.email == email) | (User.phone == phone)
        ).first()

        if existing_user:
            return render_template("register_fundi.html", error="Email or phone already exists")

        # 📸 IMAGE UPLOAD
        file = request.files.get('image')

        if not file or file.filename == "":
            return render_template("register_fundi.html", error="Please upload image")

        filename = secure_filename(file.filename)
        unique_name = str(int(time.time())) + "_" + filename
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_name)
        file.save(filepath)

        # 🔐 CREATE USER
        user = User(
            email=email,
            phone=phone,
            password=generate_password_hash(password),
            role='fundi'
        )

        db.session.add(user)
        db.session.commit()

        # 👷 CHECK IF PROFILE EXISTS (UPSERT LOGIC)
        existing_fundi = FundiProfile.query.filter_by(user_id=user.id).first()

        if existing_fundi:

            # 🔄 UPDATE EXISTING PROFILE
            existing_fundi.name = name
            existing_fundi.skills = skills
            existing_fundi.experience = experience
            existing_fundi.phone = phone
            existing_fundi.email = email
            existing_fundi.location = location
            existing_fundi.image = unique_name

        else:

            # ➕ CREATE NEW PROFILE
            fundi = FundiProfile(
                user_id=user.id,
                name=name,
                skills=skills,
                experience=experience,
                phone=phone,
                email=email,
                image=unique_name,
                location=location
            )
            db.session.add(fundi)

        db.session.commit()

        return redirect(url_for('fundi_login'))

    return render_template("register_fundi.html")

@app.route('/my_profile')
def my_profile():
    if 'user_id' not in session:
        return redirect(url_for('fundi_login'))

    fundi = FundiProfile.query.filter_by(user_id=session['user_id']).first()

    if not fundi:
        return "❌ Profile haijapatikana"

    return render_template(
        "profile.html",
        fundi=fundi,
        is_owner=True,        # 🔥 muhimu sana
        is_unlocked=True,     # 🔥 fundi ha-lockwi
        role='fundi'
    )

@app.route('/fundi/update_profile', methods=['GET', 'POST'])
@fundi_required
def update_profile():

    fundi = FundiProfile.query.filter_by(user_id=session['user_id']).first()
    user = User.query.get(session['user_id'])

    if not fundi:
        return "Profile not found"

    if request.method == 'POST':

        # 🔹 BASIC INFO
        fundi.name = request.form.get('name')
        fundi.skills = request.form.get('skills')
        fundi.experience = request.form.get('experience')
        fundi.location = request.form.get('location')
        fundi.phone = request.form.get('phone')
        fundi.email = request.form.get('email')

        # 🔹 IMAGE UPDATE
        file = request.files.get('image')
        if file and file.filename != '':
            from werkzeug.utils import secure_filename
            import os

            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

            fundi.image = filename

        # 🔐 PASSWORD UPDATE (SAFE)
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        # kama user ameandika password mpya
        if new_password:

            # hakikisha ameweka current password
            if not current_password:
                return "❌ Weka current password"

            # verify current password
            from werkzeug.security import check_password_hash, generate_password_hash

            if not check_password_hash(user.password, current_password):
                return "❌ Current password si sahihi"

            # confirm password
            if new_password != confirm_password:
                return "❌ Password hazifanani"

            # minimum length
            if len(new_password) < 6:
                return "❌ Password lazima iwe angalau herufi 6"

            # save new password
            user.password = generate_password_hash(new_password)

        db.session.commit()

        return redirect(url_for('my_profile'))

    return render_template("update_profile.html", fundi=fundi)

@app.route('/my_requests')
def my_requests():

    if 'user_id' not in session:
        return redirect(url_for('fundi_login'))

    fundi = FundiProfile.query.filter_by(user_id=session['user_id']).first()

    requests = FeaturedRequest.query.filter_by(
        fundi_id=fundi.id
    ).order_by(FeaturedRequest.id.desc()).all()

    return render_template("my_requests.html", requests=requests)

@app.route('/delete_fundi/<int:id>')
@admin_required
def delete_fundi(id):
    user = User.query.get_or_404(id)
    fundi = FundiProfile.query.filter_by(user_id=user.id).first()

    if fundi:
        db.session.delete(fundi)

    db.session.delete(user)
    db.session.commit()

    return "Fundi deleted successfully"


# 🔥 DASHBOARD
@app.route('/dashboard')
def dashboard():
    return render_template("dashboard.html")

@app.route('/admin')
@admin_required
def admin_dashboard():

    from sqlalchemy import func

    # CONTACT PAYMENTS
    total_contacts = ContactUnlock.query.count()
    paid_contacts = ContactUnlock.query.filter_by(is_paid=True).count()
    pending_contacts = ContactUnlock.query.filter_by(is_paid=False).count()

    contact_earnings = db.session.query(func.sum(ContactUnlock.amount))\
        .filter_by(is_paid=True).scalar() or 0

    # FEATURED REQUESTS
    featured_pending = FeaturedRequest.query.filter_by(
        status="pending", type="featured"
    ).count()

    boost_pending = FeaturedRequest.query.filter_by(
        status="pending", type="boost"
    ).count()

    approved_featured = FeaturedRequest.query.filter_by(
        status="approved", type="featured"
    ).count()

    approved_boost = FeaturedRequest.query.filter_by(
        status="approved", type="boost"
    ).count()

    # TOTAL EARNINGS
    featured_earnings = approved_featured * 3000
    boost_earnings = approved_boost * 2000
    total_earnings = contact_earnings + featured_earnings + boost_earnings

    return render_template(
        "admin_dashboard.html",

        total_contacts=total_contacts,
        paid_contacts=paid_contacts,
        pending_contacts=pending_contacts,

        featured_pending=featured_pending,
        boost_pending=boost_pending,

        contact_earnings=contact_earnings,
        featured_earnings=featured_earnings,
        boost_earnings=boost_earnings,
        total_earnings=total_earnings
    )

# 🔥 LOGOUT
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('dashboard'))

@app.route('/profile/<int:id>')
def profile(id):

    fundi = FundiProfile.query.get_or_404(id)

    user_id = session.get('user_id')
    user = User.query.get(user_id) if user_id else None

    role = user.role if user else None

    is_owner = user and role == 'fundi' and fundi.user_id == user.id
    is_contractor = (role == 'contractor')

    print("DEBUG ROLE:", role)
    print("DEBUG CONTRACTOR:", is_contractor)

    template = "profile.html" if is_owner else "public_profile.html"

    return render_template(
        template,
        fundi=fundi,
        is_owner=is_owner,
        is_contractor=is_contractor,
        role=role,
        now=datetime.now(timezone.utc)
    )

# 💼 HIRE FUNDI ROUTE
@app.route('/hire_fundi/<int:fundi_id>', methods=['POST'])
@contractor_required
def hire_fundi(fundi_id):

    contractor_id = session['user_id']

    fundi = FundiProfile.query.get_or_404(fundi_id)

    # optional: avoid duplicate requests
    existing = FeaturedRequest.query.filter_by(
        fundi_id=fundi_id,
        type="hire",
        status="pending"
    ).first()

    if existing:
        return "Already requested"

    hire_request = FeaturedRequest(
        fundi_id=fundi_id,
        phone=None,
        transaction_id=None,
        status="pending",
        type="hire"
    )

    db.session.add(hire_request)
    db.session.commit()

    return "Hire request sent successfully"


@app.route('/boost_profile/<int:id>')
@admin_required
def boost_profile(id):
    fundi = FundiProfile.query.get_or_404(id)

    # 🔒 STRICT RULE: must be active featured
    if not is_featured_active(fundi):
        return "❌ Lazima uwe Featured active kabla ya Boost"

    fundi.boost_until = datetime.now(timezone.utc) + timedelta(days=3)

    db.session.commit()

    return "🚀 Profile boosted successfully!"

@app.route('/feature/<int:id>')
@admin_required
def feature_fundi(id):
    fundi = FundiProfile.query.get_or_404(id)
    
    fundi.featured_until = datetime.now(timezone.utc) + timedelta(days=30)

    db.session.commit()
    return "Fundi amefanywa Featured ⭐ kwa siku 30"

@app.route('/request_feature/<int:id>', methods=['POST'])
def request_feature(id):
    phone = request.form['phone']
    transaction_id = request.form['transaction_id']

    request_entry = FeaturedRequest(
        fundi_id=id,
        phone=phone,
        transaction_id=transaction_id,
        status="pending",
        type="featured"
    )

    db.session.add(request_entry)
    db.session.commit()

    return render_template("success.html", type="featured")

@app.route('/request_boost/<int:id>', methods=['POST'])
@fundi_required
def request_boost(id):

    fundi = FundiProfile.query.get_or_404(id)

    # 🔒 lazima awe featured kwanza
    if not is_featured_active(fundi):
      return "❌ Lazima ulipie Featured kwanza kabla ya Boost"

    phone = request.form['phone']
    transaction_id = request.form['transaction_id']

    request_entry = FeaturedRequest(
        fundi_id=id,
        phone=phone,
        transaction_id=transaction_id,
        status="pending",
        type="boost"
    )

    db.session.add(request_entry)
    db.session.commit()

    return render_template("success.html", type="boost")

@app.route('/admin/featured_requests')
@admin_required
def featured_requests():
    status = request.args.get('status')
    type_filter = request.args.get('type')

    query = FeaturedRequest.query

    if status:
        query = query.filter_by(status=status)

    if type_filter:
        query = query.filter_by(type=type_filter)

    requests = query.order_by(FeaturedRequest.id.desc()).all()

    return render_template("admin_requests.html", requests=requests)

@app.route('/admin/contact_payments')
@admin_required
def admin_contact_payments():

    log = ActivityLog(
        user_id=session.get('user_id'),
        action="Admin viewed contact payments"
    )
    db.session.add(log)
    db.session.commit()

    payments = ContactUnlock.query.order_by(ContactUnlock.id.desc()).all()

    return render_template("admin_contact.html", payments=payments)

@app.route('/admin/earnings')
@admin_required
def admin_earnings():

    from sqlalchemy import func

    # 💰 TOTAL CONTACT UNLOCK
    contact_total = db.session.query(func.sum(ContactUnlock.amount))\
        .filter_by(is_paid=True).scalar() or 0

    # 📊 FEATURED + BOOST (assume price)
    featured_total = FeaturedRequest.query.filter_by(
        status="approved", type="featured"
    ).count() * 3000

    boost_total = FeaturedRequest.query.filter_by(
        status="approved", type="boost"
    ).count() * 2000

    # 🔥 TOTAL EARNINGS
    total_earnings = contact_total + featured_total + boost_total

    # 📅 TODAY EARNINGS
    today = datetime.now(timezone.utc).date()

    today_contact = sum(
        p.amount for p in ContactUnlock.query.filter_by(is_paid=True).all()
        if p.id  # unaweza improve kwa created_at
    )

    # 📋 RECENT PAYMENTS
    recent_contacts = ContactUnlock.query.order_by(
        ContactUnlock.id.desc()
    ).limit(10).all()

    recent_features = FeaturedRequest.query.order_by(
        FeaturedRequest.id.desc()
    ).limit(10).all()

    return render_template(
        "admin_earnings.html",
        total_earnings=total_earnings,
        contact_total=contact_total,
        featured_total=featured_total,
        boost_total=boost_total,
        recent_contacts=recent_contacts,
        recent_features=recent_features
    )

@app.route('/admin/delete_fundi/<int:id>')
@admin_required
def delete_fundi_admin(id):

    fundi = FundiProfile.query.get_or_404(id)
    user = User.query.get(fundi.user_id)

    # delete fundi profile
    db.session.delete(fundi)

    # delete user pia
    if user:
        db.session.delete(user)

    db.session.commit()

    return "Fundi deleted successfully"

@app.route('/admin/block_user/<int:id>')
@admin_required
def block_user(id):

    user = User.query.get(id)

    if not user:
        return "User not found"

    user.is_blocked = True
    db.session.commit()

    # 🔥 LOG HAPA
    log = ActivityLog(
        user_id=session.get('user_id'),
        action=f"Blocked user {id}"
    )
    db.session.add(log)
    db.session.commit()

    return "User blocked"

@app.route('/admin/approve_feature/<int:id>')
@admin_required
def approve_feature(id):

    req = FeaturedRequest.query.get_or_404(id)
    fundi = FundiProfile.query.get(req.fundi_id)

    if req.type == "featured":
        fundi.featured_until = datetime.now(timezone.utc) + timedelta(days=30)

    elif req.type == "boost":

        if not is_featured_active(fundi):
            return "Must be featured first"

        fundi.boost_until = datetime.now(timezone.utc) + timedelta(days=3)

    req.status = "approved"

    db.session.commit()

    return redirect(url_for('admin_dashboard'))

@app.route('/admin/approve_contact/<int:id>')
@admin_required
def approve_contact(id):

    payment = ContactUnlock.query.get_or_404(id)

    payment.status = "approved"
    payment.is_paid = True
    payment.expires_at = datetime.now(timezone.utc) + timedelta(days=7)

    db.session.commit()

    return redirect(url_for('admin_dashboard'))

@app.route('/admin/reject_request/<int:id>')
@admin_required
def reject_request(id):

    req = FeaturedRequest.query.get_or_404(id)
    req.status = "rejected"

    db.session.commit()

    return redirect(url_for('featured_requests'))


@app.route('/admin/fundi_updates')
@admin_required
def fundi_updates():

    updates = ProfileUpdate.query.order_by(ProfileUpdate.id.desc()).all()

    return render_template("admin_updates.html", updates=updates)

@app.route('/admin/hire_requests')
@admin_required
def hire_requests():

    requests = FeaturedRequest.query.filter_by(type="hire")\
        .order_by(FeaturedRequest.id.desc()).all()

    return render_template("admin_hire_requests.html", requests=requests)

if __name__ == "__main__":

    with app.app_context():
        db.create_all()

        admin = User.query.filter_by(role='admin').first()

        if not admin:
            from werkzeug.security import generate_password_hash

            admin = User(
                email="methodbosco12@gmail.com",
                phone="0700000000",
                password=generate_password_hash(os.getenv("ADMIN_PASSWORD", "admin123")),
                role="admin"
            )

            db.session.add(admin)
            db.session.commit()

            print("✅ Admin created")
        else:
            print("ℹ️ Admin already exists")

    scheduler = BackgroundScheduler()
    scheduler.add_job(expire_jobs, 'interval', minutes=3)

    if os.environ.get("RUN_SCHEDULER") == "true":
      scheduler.start()

    import atexit
    atexit.register(lambda: scheduler.shutdown())

    port = int(os.environ.get("PORT", 5000))

    app.run(host="0.0.0.0", port=port)