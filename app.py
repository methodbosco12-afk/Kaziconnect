
import atexit

from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_mail import Mail, Message
from services.sms_service import send_sms
from utils.notifications import notify_user
from flask_migrate import Migrate
from datetime import datetime, timedelta, timezone
from extensions import db, mail
from models import SupportMessage, User, FundiProfile, FeaturedRequest, OTP, ContactUnlock,IpBlock,ActivityLog,ProfileUpdate,Notification
import os
import time
from dotenv import load_dotenv
load_dotenv()
import random
import urllib.parse

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

def clean_skills(text):
    if not text:
        return None
    return text.lower().strip()

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
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db.init_app(app)
migrate = Migrate()
migrate.init_app(app, db)

@app.context_processor
def inject_now():
    return {'now': datetime.now(timezone.utc)}


# =========================
# MAIL CONFIG (WEKA KWANZA)
# =========================
app.config["MAIL_SERVER"] = "smtp.gmail.com"
app.config["MAIL_PORT"] = 587
app.config["MAIL_USE_TLS"] = True
app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME")
app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD")

# 🔥 HII IJE BAADA YA CONFIG
mail = Mail()
mail.init_app(app)

@app.route('/check_admin')
def check_admin():
    admin = User.query.filter_by(role='admin').first()

    if not admin:
        return "No admin found"

    return f"Admin exists: {admin.email}"

def expire_jobs():
    try:
        with app.app_context():
            now = datetime.now(timezone.utc)

            FundiProfile.query.filter(
                FundiProfile.featured_until.isnot(None),
                FundiProfile.featured_until < now
            ).update({FundiProfile.featured_until: None})

            FundiProfile.query.filter(
                FundiProfile.boost_until.isnot(None),
                FundiProfile.boost_until < now
            ).update({FundiProfile.boost_until: None})

            db.session.commit()
            print("✅ expiry ran")

    except Exception as e:
        print("EXPIRY ERROR:", e)

@app.route('/fix_db')
@admin_required
def fix_db():

    FundiProfile.query.filter(
        (FundiProfile.skills == None) |
        (FundiProfile.skills == "") |
        (FundiProfile.skills.ilike("%haijatajwa%")) |
        (FundiProfile.skills.ilike("%not specified%"))
    ).update({FundiProfile.skills: None}, synchronize_session=False)

    FundiProfile.query.filter(
        (FundiProfile.experience == None) |
        (FundiProfile.experience == "") |
        (FundiProfile.experience.ilike("%haijatajwa%")) |
        (FundiProfile.experience.ilike("%not specified%"))
    ).update({FundiProfile.experience: None}, synchronize_session=False)

    db.session.commit()

    return "Cleaned successfully"


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

    now = datetime.now(timezone.utc)

    # 🚫 kama hakuna search yoyote, usirudishe watu
    if not skills and not experience and not location:
        return render_template("search.html", results=[], now=now)

    # 🔥 CHUJA DATABASE KABLA YA KURUDISHA
    query = FundiProfile.query.filter(
        FundiProfile.skills.isnot(None),
        FundiProfile.skills != ""
    )

    # 🔍 STRICT FILTERS (HII NDIO MSAADA WA KWELI)
    if skills:
        query = query.filter(
        FundiProfile.skills.ilike(f"%{skills},%") |
        FundiProfile.skills.ilike(f"%,{skills}%") |
        FundiProfile.skills.ilike(f"% {skills} %") |
        FundiProfile.skills.ilike(f"{skills}")
    )

    if experience:
        query = query.filter(FundiProfile.experience.ilike(f"%{experience}%"))

    if location:
        query = query.filter(FundiProfile.location.ilike(f"%{location}%"))

    # 🚀 PATA RESULTS MOJA KWA MOJA
    results = query.limit(50).all()

    # ⭐ SORT (featured & boost juu)
    results.sort(
        key=lambda f: (
            1 if f.boost_until and f.boost_until > now else 0,
            1 if f.featured_until and f.featured_until > now else 0
        ),
        reverse=True
    )

    return render_template(
        "search.html",
        results=results,
        skills=skills,
        experience=experience,
        location=location,
        now=now
    )

@app.route('/results', methods=['GET'])
def results():

    skills = (request.args.get('skills') or '').strip().lower()
    experience = (request.args.get('experience') or '').strip().lower()
    location = request.args.get('location')

    query = FundiProfile.query

    # 🔥 skills (strict improved)
    if skills:
        query = query.filter(
            FundiProfile.skills.ilike(f"%{skills},%") |
            FundiProfile.skills.ilike(f"%,{skills}%") |
            FundiProfile.skills.ilike(f"% {skills} %") |
            FundiProfile.skills.ilike(f"{skills}")
        )

    # 🔥 experience (improved)
    if experience:
        query = query.filter(
            FundiProfile.experience.ilike(f"%{experience}%")
        )

    # 🔥 location (unchanged)
    if location:
        query = query.filter(
            FundiProfile.location.contains(location)
        )

    fundis = query.all()

    # 🚀 SORTING LOGIC (UNCHANGED)
    def sort_key(f):
        if f.boost_until and f.boost_until > datetime.now(timezone.utc):
            return 3
        elif f.featured_until and f.featured_until > datetime.now(timezone.utc):
            return 2
        else:
            return 1

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
        skills = clean_skills(request.form.get('skills'))
        experience = clean_skills(request.form.get('experience'))

        phone = request.form.get('phone').strip().replace(" ", "")
        email = request.form.get('email').lower().strip()
        location = request.form.get('location')

        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

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

        filepath = os.path.join(app.root_path, 'static', 'images', unique_name)
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

        # 👷 CREATE OR UPDATE PROFILE
        fundi = FundiProfile.query.filter_by(user_id=user.id).first()

        if fundi:
            fundi.name = name
            fundi.skills = skills.lower().strip()
            fundi.experience = experience
            fundi.phone = phone
            fundi.email = email
            fundi.location = location
            fundi.image = unique_name
        else:
            fundi = FundiProfile(
                user_id=user.id,
                name=name,
                skills=skills.lower().strip(),
                experience=experience,
                phone=phone,
                email=email,
                image=unique_name,
                location=location
            )
            db.session.add(fundi)

        db.session.commit()

        # 📩 SMS NOTIFICATION (PRODUCTION SAFE)
        try:
            send_sms(
                phone,
                "🎉 Karibu KaziConnect! Umefanikiwa kujisajili kama Fundi."
            )
        except Exception as e:
            print("SMS error:", e)

        return redirect(url_for('fundi_login'))

    return render_template("register_fundi.html")

@app.route('/my_profile')
def my_profile():

    if session.get('role') != 'fundi':
        return redirect(url_for('fundi_login'))

    user = User.query.get(session['user_id'])

    if not user:
        session.clear()
        return redirect(url_for('fundi_login'))

    fundi = FundiProfile.query.filter_by(user_id=user.id).first()

    if not fundi:
        return redirect(url_for('register_fundi'))

    return render_template("profile.html", fundi=fundi)

@app.route('/delete_fundi_account', methods=['POST'])
def delete_fundi_account():
    user_id = session.get('user_id')
    password = request.form.get('password')

    user = User.query.get(user_id)

    # 🔐 verify password
    if not user or not check_password_hash(user.password, password):
        flash("❌ Password si sahihi. Account haijafutwa.")
        return redirect(url_for('profile'))

    # 🧹 delete related data first (important)
    FundiProfile.query.filter_by(user_id=user_id).delete()
    User.query.filter_by(id=user_id).delete()

    db.session.commit()

    session.clear()

    flash("✅ Account imefutwa kikamilifu.")
    return redirect(url_for('home'))

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
        fundi.skills = clean_skills(request.form.get('skills'))
        fundi.experience = clean_skills(request.form.get('experience'))
        fundi.location = request.form.get('location')
        fundi.phone = request.form.get('phone')
        fundi.email = request.form.get('email')

        # 🔹 IMAGE UPDATE
        file = request.files.get('image')
        if file and file.filename != '':
            from werkzeug.utils import secure_filename
            import os

            filename = secure_filename(file.filename)
            unique_name = str(int(time.time())) + "_" + filename

            filepath = os.path.join(app.root_path, 'static', 'images', unique_name)

            file.save(filepath)

            print("Saved to:", filepath)

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


# 🔥 DASHBOARD
@app.route('/dashboard')
def dashboard():
    return render_template("dashboard.html")

@app.route('/admin')
@admin_required
def admin_dashboard():

    from sqlalchemy import func

    # =========================
    # NEW ADDITIONS (HAZIHARIBU LOGIC YA ZAMANI)
    # =========================
    total_fundi = FundiProfile.query.count()
    total_users = User.query.count()

    now = datetime.now(timezone.utc)

    active_featured = FundiProfile.query.filter(
        FundiProfile.featured_until != None,
        FundiProfile.featured_until > now
    ).count()

    active_boosted = FundiProfile.query.filter(
        FundiProfile.boost_until != None,
        FundiProfile.boost_until > now
    ).count()

    recent_fundis = FundiProfile.query.order_by(
        FundiProfile.id.desc()
    ).limit(10).all()

    # =========================
    # LOGIC YAKO YA ZAMANI (UNCHANGED)
    # =========================

    # CONTACT PAYMENTS
    total_contacts = ContactUnlock.query.count()

    paid_contacts = ContactUnlock.query.filter_by(
        is_paid=True
    ).count()

    pending_contacts = ContactUnlock.query.filter_by(
        is_paid=False
    ).count()

    contact_earnings = db.session.query(
        func.sum(ContactUnlock.amount)
    ).filter_by(is_paid=True).scalar() or 0

    # FEATURED REQUESTS
    featured_pending = FeaturedRequest.query.filter_by(
        status="pending",
        type="featured"
    ).count()

    boost_pending = FeaturedRequest.query.filter_by(
        status="pending",
        type="boost"
    ).count()

    approved_featured = FeaturedRequest.query.filter_by(
        status="approved",
        type="featured"
    ).count()

    approved_boost = FeaturedRequest.query.filter_by(
        status="approved",
        type="boost"
    ).count()

    # TOTAL EARNINGS
    featured_earnings = approved_featured * 3000
    boost_earnings = approved_boost * 2000

    total_earnings = (
        contact_earnings +
        featured_earnings +
        boost_earnings
    )

    # =========================
    # RETURN TEMPLATE
    # =========================
    return render_template(
        "admin_dashboard.html",

        # OLD VARIABLES
        total_contacts=total_contacts,
        paid_contacts=paid_contacts,
        pending_contacts=pending_contacts,

        featured_pending=featured_pending,
        boost_pending=boost_pending,

        contact_earnings=contact_earnings,
        featured_earnings=featured_earnings,
        boost_earnings=boost_earnings,
        total_earnings=total_earnings,

        # NEW ADDITIONS
        total_fundi=total_fundi,
        total_users=total_users,
        active_featured=active_featured,
        active_boosted=active_boosted,
        recent_fundis=recent_fundis,
        now=now
    )

@app.route('/admin/fundis')
@admin_required
def admin_fundis():
    fundis = FundiProfile.query.order_by(FundiProfile.id.desc()).all()
    return render_template("admin_fundis.html", fundis=fundis)

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

@app.route('/profile')
def profile_redirect():
    if session.get('role') != 'fundi':
        return redirect(url_for('fundi_login'))

    user_id = session.get('user_id')

    if not user_id:
        return redirect(url_for('fundi_login'))

    fundi = FundiProfile.query.filter_by(user_id=user_id).first()

    if not fundi:
        return redirect(url_for('register_fundi'))

    return redirect(url_for('profile', id=fundi.id))

@app.route('/notifications')
def notifications_page():

    if 'user_id' not in session:
        return redirect(url_for('fundi_login'))

    user_id = session['user_id']

    notifications = Notification.query.filter_by(
        user_id=user_id
    ).order_by(Notification.id.desc()).all()

    return render_template(
        "notifications.html",
        notifications=notifications
    )

@app.route('/notifications/read/<int:id>')
def mark_as_read(id):

    if 'user_id' not in session:
        return redirect(url_for('fundi_login'))

    notif = Notification.query.get_or_404(id)

    if notif.user_id != session['user_id']:
        return "Not allowed"

    notif.is_read = True
    db.session.commit()

    return redirect(url_for('notifications_page'))

@app.route('/notifications/read_all')
def read_all():

    if 'user_id' not in session:
        return redirect(url_for('fundi_login'))

    Notification.query.filter_by(
        user_id=session['user_id'],
        is_read=False
    ).update({Notification.is_read: True})

    db.session.commit()

    return redirect(url_for('notifications_page'))

# 💼 HIRE FUNDI ROUTE
@app.route('/hire_fundi/<int:fundi_id>', methods=['POST'])
@contractor_required
def hire_fundi(fundi_id):

    fundi = FundiProfile.query.get_or_404(fundi_id)
    contractor_id = session['user_id']

    # 🔥 DATA TOKA FORM
    client_name = request.form.get('name')
    phone = request.form.get('phone')
    location = request.form.get('location')
    message = request.form.get('message')

    # ❌ validation
    if not client_name or not phone or not location:
        return "Tafadhali jaza taarifa zote"

    # ➕ SAVE REQUEST
    hire = HireRequest(
        fundi_id=fundi_id,
        contractor_id=contractor_id,
        client_name=client_name,
        phone=phone,
        location=location,
        message=message
    )

    db.session.add(hire)
    db.session.commit()

    # 🔔 NOTIFICATION KWA FUNDI
    notify_user(
        fundi.user_id,
        f"🔔 Una hire request mpya kutoka {client_name} ({location})"
    )

    # 📩 SMS kwa fundi
    try:
        send_sms(
            fundi.phone,
            f"New job request from {client_name} - check KaziConnect"
        )
    except:
        pass

    return "✅ Hire request sent successfully"


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

    # 🔔 HAPA NDIPO NOTIFICATION INAWEKWA
    fundi = FundiProfile.query.get(id)

    notify_user(
        fundi.user_id,
        "📢 Ombi lako la Featured limepokelewa, linasubiri approval."
    )

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

@app.route('/admin/delete_fundi/<int:id>', methods=['POST'])
@admin_required
def delete_fundi_admin(id):

    fundi = FundiProfile.query.get_or_404(id)
    user = User.query.get(fundi.user_id)

    db.session.delete(fundi)

    if user:
        db.session.delete(user)

    db.session.commit()

    return redirect(url_for('admin_fundis'))


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

    # 🔔 NOTIFICATION (HAPA NDIPO INAWEKWA)
    notify_user(
        payment.contractor_id,
        "✅ Malipo yako yamekubaliwa. Sasa unaweza kuona contact ya fundi."
    )

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

@app.route("/send_support_message", methods=["POST"])
def send_support_message():
    try:
        channel = request.form.get("channel")
        name = request.form.get("name")
        phone = request.form.get("phone")
        subject = request.form.get("subject")
        message = request.form.get("message")

        full_msg = f"""
Jina: {name}
Simu: {phone}
Kichwa: {subject}

Ujumbe:
{message}
"""

        # WHATSAPP
        if channel == "whatsapp":
            whatsapp_number = "255799978711"
            encoded_msg = urllib.parse.quote(full_msg)
            url = f"https://wa.me/{whatsapp_number}?text={encoded_msg}"
            return redirect(url)

        # EMAIL
        elif channel == "email":
            msg = Message(
                subject=f"KaziConnect Support: {subject}",
                sender=app.config["MAIL_USERNAME"],
                recipients=[app.config["MAIL_USERNAME"]]  # 🔥 FIX
            )
            msg.body = full_msg

            mail.send(msg)

            return "✅ Email imetumwa successfully"

        return "❌ Channel haijulikani"

    except Exception as e:
        print("EMAIL ERROR:", e)
        return f"❌ Email failed: {str(e)}"

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/contact')
def contact():
    return render_template("contact.html")

@app.route('/settings', methods=['GET', 'POST'])
def settings():

    if 'user_id' not in session:
        return redirect(url_for('fundi_login'))

    user = User.query.get(session['user_id'])

    if request.method == 'POST':

        action = request.form.get("action")

        # =========================
        # 🔐 CHANGE PASSWORD
        # =========================
        if action == "change_password":

            current = request.form.get("current_password")
            new = request.form.get("new_password")
            confirm = request.form.get("confirm_password")

            if not check_password_hash(user.password, current):
                return "❌ Current password si sahihi"

            if new != confirm:
                return "❌ Password hazifanani"

            if len(new) < 6:
                return "❌ Password lazima iwe angalau 6"

            user.password = generate_password_hash(new)
            db.session.commit()

            return "✅ Password imebadilishwa"

        # =========================
        # 📱 UPDATE CONTACT INFO
        # =========================
        elif action == "update_contact":

            phone = request.form.get("phone")
            email = request.form.get("email")

            user.phone = phone
            user.email = email

            db.session.commit()

            return "✅ Contact updated"

        # =========================
        # 🔔 NOTIFICATIONS
        # =========================
        elif action == "notifications":

            user.sms_notifications = bool(request.form.get("sms_notifications"))
            user.email_notifications = bool(request.form.get("email_notifications"))

            db.session.commit()

            return "✅ Notification settings saved"

        # =========================
        # 🗑️ DELETE ACCOUNT
        # =========================
        elif action == "delete_account":

            password = request.form.get("password")

            if not check_password_hash(user.password, password):
                return "❌ Password si sahihi"

            FundiProfile.query.filter_by(user_id=user.id).delete()
            User.query.filter_by(id=user.id).delete()

            db.session.commit()
            session.clear()

            return redirect(url_for('home'))

    return render_template("settings.html", user=user)

if __name__ == "__main__":

    with app.app_context():
        db.create_all()

        admin = User.query.filter_by(role='admin').first()

        if not admin:
            from werkzeug.security import generate_password_hash

            admin = User(
                email="methodbosco12@gmail.com",
                phone="0700000000",
                password=generate_password_hash(
                    os.getenv("ADMIN_PASSWORD", "admin123")
                ),
                role="admin"
            )

            db.session.add(admin)
            db.session.commit()

            print("✅ Admin created")

        else:
            print("ℹ️ Admin already exists")

    # 🔥 START SCHEDULER
    scheduler = BackgroundScheduler()
    scheduler.add_job(expire_jobs, 'interval', minutes=3)
    scheduler.start()

    # 🔥 SAFE SHUTDOWN
    atexit.register(lambda: scheduler.shutdown())

    # 🔥 RUN FLASK
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, port=port, use_reloader=False)