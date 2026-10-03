from app.db.session import SessionLocal
from app.models.user import User
from app.api.auth.router import verify_password, hash_password

def check():
    db = SessionLocal()
    test_emails = [
        'aryan@gmail.com', 'bharat@gmail.com', 'aman@gmail.com', 'saket@gmail.com',
        'priyanshu@gmail.com', 'neha@gmail.com', 'priya@gmail.com', 'sakshi@gmail.com',
        'sid@gmail.com', 'aditya@gmail.com'
    ]

    print("=== SAFE DIAGNOSTIC CHECK OF 10 TEST USERS IN DATABASE ===")
    for email in test_emails:
        u = db.query(User).filter(User.email == email).first()
        if not u:
            print(f"Email: {email:<22} | Exists: NO")
            continue
        has_hash = u.password_hash is not None and len(u.password_hash) > 0
        is_bcrypt = u.password_hash.startswith(('$2b$', '$2a$', '$2y$')) if has_hash else False
        is_123456789_valid = verify_password('123456789', u.password_hash) if has_hash else False
        print(f"Email: {email:<22} | Exists: YES | Active: {u.is_active} | Hash format: {'bcrypt' if is_bcrypt else 'invalid/none'} | Valid for 123456789: {is_123456789_valid}")

    db.close()

if __name__ == '__main__':
    check()
