from app import app, db, User
from werkzeug.security import generate_password_hash

with app.app_context():

    old = User.query.filter_by(email="admin@gmail.com").first()
    if old:
        db.session.delete(old)
        db.session.commit()

    admin = User(
        email="admin@gmail.com",
        phone="0000",
        password=generate_password_hash("admin123"),
        role="admin"
    )

    db.session.add(admin)
    db.session.commit()

print("Admin ready")