from app.db.session import SessionLocal
from app.models.user import User
from app.api.auth.router import verify_password

def check_pass():
    db = SessionLocal()
    test_emails = [
        'aman@gmail.com', 'saket@gmail.com', 'priyanshu@gmail.com', 'neha@gmail.com',
        'priya@gmail.com', 'sakshi@gmail.com', 'sid@gmail.com', 'aditya@gmail.com'
    ]
    print("Checking 8 newer users with 'watchman_secure_dev_pass_123' vs '123456789':")
    for email in test_emails:
        u = db.query(User).filter(User.email == email).first()
        if u:
            v_old = verify_password('watchman_secure_dev_pass_123', u.password_hash)
            v_123 = verify_password('123456789', u.password_hash)
            print(f"{email}: watchman_secure_dev_pass_123={v_old}, 123456789={v_123}")
    db.close()

if __name__ == '__main__':
    check_pass()
